"""CLI dispatch for proofreading lenses."""

import re
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    from jinja2 import Environment, FileSystemLoader
except ImportError:
    print("Missing dependency: pip3 install jinja2", file=sys.stderr)
    sys.exit(1)

from models import Chunk, Finding, LensResult

HARNESS_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = HARNESS_DIR / 'templates'

# CLI command patterns (stdin-based)
CLI_COMMANDS = {
    'codex': 'cat "{prompt_file}" | codex exec -c model_reasoning_effort="low" --skip-git-repo-check -o "{output_file}" -',
    'gemini': 'cat "{prompt_file}" | gemini --yolo -o text -',
    'claude': 'cat "{prompt_file}" | claude --dangerously-skip-permissions -p -',
    'copilot': 'cat "{prompt_file}" | copilot -p -',
}


def _render_chunk_prompt(lens_name: str, chunk: Chunk, manuscript_type: str = 'paper') -> str:
    """Render a Jinja2 prompt template for a chunk-level lens."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        keep_trailing_newline=True,
    )
    template = env.get_template(f'{lens_name}.md.j2')
    return template.render(chunk=chunk, manuscript_type=manuscript_type)


def _render_coherence_prompt(
    full_document: str,
    manuscript_type: str = 'paper',
    project_reference_context: str = '',
) -> str:
    """Render the coherence lens prompt with the full document."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        keep_trailing_newline=True,
    )
    template = env.get_template('coherence.md.j2')
    return template.render(
        full_document=full_document,
        manuscript_type=manuscript_type,
        project_reference_context=project_reference_context,
    )


def _parse_findings(raw_output: str, lens_name: str, chunk_id: str) -> list[Finding]:
    """Parse pipe-delimited findings from CLI output."""
    findings = []
    finding_re = re.compile(
        r'FINDING\|'
        r'line:(\d+)\|'
        r'severity:(critical|major|minor)\|'
        r'category:(\w+)\|'
        r'current:(.+?)\|'
        r'fix:(.+?)\|'
        r'explanation:(.+)'
    )

    for line in raw_output.split('\n'):
        line = line.strip()
        m = finding_re.match(line)
        if m:
            findings.append(Finding(
                line=int(m.group(1)),
                severity=m.group(2),
                category=m.group(3),
                lens=lens_name,
                current_text=m.group(4),
                suggested_fix=m.group(5),
                explanation=m.group(6),
                chunk_id=chunk_id,
            ))

    return findings


def _has_explicit_no_findings(raw_output: str) -> bool:
    """Return True when the model explicitly outputs a standalone NO_FINDINGS line."""
    return any(line.strip() == 'NO_FINDINGS' for line in raw_output.splitlines())


def _run_cli(cli: str, prompt: str, timeout: int, temp_dir: str) -> tuple[str, bool, str | None]:
    """Run a CLI command with the given prompt. Returns (output, success, error)."""
    temp_path = Path(temp_dir)
    temp_path.mkdir(parents=True, exist_ok=True)

    # Write prompt to temp file
    with tempfile.NamedTemporaryFile(
        mode='w', suffix='.md', dir=str(temp_path), delete=False
    ) as f:
        f.write(prompt)
        prompt_file = f.name

    with tempfile.NamedTemporaryFile(
        mode='w', suffix='.txt', dir=str(temp_path), delete=False
    ) as f:
        output_file = f.name

    cmd_template = CLI_COMMANDS.get(cli)
    if not cmd_template:
        return '', False, f'Unknown CLI: {cli}'

    cmd = cmd_template.format(prompt_file=prompt_file, output_file=output_file)

    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout,
        )
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        if stdout and stderr:
            output = f'{result.stdout}\n{result.stderr}'
        elif stdout:
            output = result.stdout
        else:
            output = result.stderr

        final_output = Path(output_file).read_text(encoding='utf-8').strip()
        if final_output:
            output = final_output

        if result.returncode != 0:
            error = stderr or f'CLI exited with code {result.returncode}'
            return output, False, error

        return output, True, None
    except subprocess.TimeoutExpired:
        return '', False, f'CLI timed out after {timeout}s'
    except Exception as e:
        return '', False, str(e)
    finally:
        Path(prompt_file).unlink(missing_ok=True)
        Path(output_file).unlink(missing_ok=True)


def dispatch_one(
    chunk: Chunk,
    lens: dict,
    config: dict,
) -> LensResult:
    """Run one lens on one chunk."""
    lens_name = lens['name']
    cli = lens.get('cli', 'codex')
    timeout = config['dispatch']['timeout_seconds']
    temp_dir = config['dispatch']['temp_dir']

    prompt = _render_chunk_prompt(lens_name, chunk, config.get('manuscript_type', 'paper'))

    start = time.time()
    raw_output, success, error = _run_cli(cli, prompt, timeout, temp_dir)
    elapsed = time.time() - start

    findings = []
    if success:
        findings = _parse_findings(raw_output, lens_name, chunk.id)
        if not findings and _has_explicit_no_findings(raw_output):
            findings = []

    return LensResult(
        lens_name=lens_name,
        chunk_id=chunk.id,
        cli_used=cli,
        raw_output=raw_output,
        findings=findings,
        elapsed_seconds=elapsed,
        success=success,
        error=error,
    )


def dispatch_coherence(
    full_document: str,
    lens: dict,
    config: dict,
    project_reference_context: str = '',
) -> LensResult:
    """Run the coherence lens on the full document."""
    cli = lens.get('cli', 'codex')
    timeout = config['dispatch']['timeout_seconds'] * 2  # Give coherence more time
    temp_dir = config['dispatch']['temp_dir']

    prompt = _render_coherence_prompt(
        full_document,
        config.get('manuscript_type', 'paper'),
        project_reference_context,
    )

    start = time.time()
    raw_output, success, error = _run_cli(cli, prompt, timeout, temp_dir)
    elapsed = time.time() - start

    findings = []
    if success:
        findings = _parse_findings(raw_output, 'coherence', 'document')
        if not findings and _has_explicit_no_findings(raw_output):
            findings = []

    return LensResult(
        lens_name='coherence',
        chunk_id='document',
        cli_used=cli,
        raw_output=raw_output,
        findings=findings,
        elapsed_seconds=elapsed,
        success=success,
        error=error,
    )


def dispatch_all(
    chunks: list[Chunk],
    lenses: list[dict],
    config: dict,
    skip_fn=None,
) -> list[LensResult]:
    """Dispatch all chunk-lens pairs in parallel.

    skip_fn: callable(chunk_id, lens_name) -> bool, for resumability
    """
    parallelism = config['dispatch']['parallelism']
    chunk_lenses = [l for l in lenses if l.get('scope', 'chunk') == 'chunk']
    results = []

    tasks = []
    for chunk in chunks:
        for lens in chunk_lenses:
            if skip_fn and skip_fn(chunk.id, lens['name']):
                continue
            tasks.append((chunk, lens))

    if not tasks:
        print('  All chunk-level tasks already completed.')
        return results

    print(f'  Dispatching {len(tasks)} chunk-lens calls ({parallelism} parallel)...')

    with ThreadPoolExecutor(max_workers=parallelism) as pool:
        futures = {
            pool.submit(dispatch_one, chunk, lens, config): (chunk.id, lens['name'])
            for chunk, lens in tasks
        }
        for future in as_completed(futures):
            chunk_id, lens_name = futures[future]
            try:
                result = future.result()
                n = len(result.findings)
                status = 'OK' if result.success else 'FAIL'
                print(f'    {chunk_id} x {lens_name}: {status} ({n} findings, {result.elapsed_seconds:.1f}s)')
                results.append(result)
            except Exception as e:
                print(f'    {chunk_id} x {lens_name}: ERROR ({e})')
                results.append(LensResult(
                    lens_name=lens_name,
                    chunk_id=chunk_id,
                    cli_used='',
                    raw_output='',
                    success=False,
                    error=str(e),
                ))

    return results
