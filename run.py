#!/usr/bin/env python3.11
"""Proofreading harness: chunk-by-lens multi-pass proofreading.

Breaks a LaTeX document into chunks, runs each chunk through multiple
focused lenses (each a separate CLI call to codex/gemini/claude/copilot),
then aggregates and deduplicates findings into a single report.

Usage:
    python run.py paper.tex
    python run.py chapter.tex --manuscript-type textbook
    python run.py chapter.tex --manuscript-type langsci
    python run.py paper.tex --lenses grammar,housestyle --cli codex
    python run.py paper.tex --dry-run
    python run.py paper.tex --resume
"""

import argparse
import json
import sys
import time
from pathlib import Path

# Add harness directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent))

from chunker import chunk_document
from config import (
    VALID_MANUSCRIPT_TYPES,
    get_enabled_lenses,
    load_config,
    override_cli,
    set_manuscript_type,
)
from dispatcher import dispatch_all, dispatch_coherence
from ignore_rules import load_ignore_rules, should_ignore_finding
from linter import run_linter
from aggregator import generate_report
from project_context import build_project_reference_context, should_skip_coherence_finding
from state import (
    load_state, save_state, init_state,
    is_task_done, mark_task_done, check_file_changed,
)
from utils import (
    build_example_line_flags,
    build_ignore_line_flags,
    build_structured_line_flags,
    normalize_latex_quotes,
    should_skip_grammar_finding,
    should_skip_housestyle_finding,
    should_skip_line_ignored_finding,
)


def main():
    parser = argparse.ArgumentParser(
        description='Proofreading harness: multi-pass chunk-by-lens proofreading',
    )
    parser.add_argument('input', type=Path, help='LaTeX file to proofread')
    parser.add_argument('--config', type=Path, default=None, help='YAML config file')
    parser.add_argument(
        '--manuscript-type',
        type=str,
        choices=sorted(VALID_MANUSCRIPT_TYPES),
        default=None,
        help='Built-in proofreading profile (paper, textbook, or langsci)',
    )
    parser.add_argument('--lenses', type=str, default=None,
                        help='Comma-separated lens names (grammar,argument,grounding,housestyle,coherence)')
    parser.add_argument('--cli', type=str, default=None,
                        help='Override CLI for all lenses (codex,gemini,claude,copilot)')
    parser.add_argument('--output-dir', type=Path, default=None, help='Output directory')
    parser.add_argument('--parallelism', type=int, default=None, help='Max parallel CLI calls')
    parser.add_argument('--timeout-seconds', type=int, default=None, help='Max seconds per chunk-level CLI call')
    parser.add_argument('--dry-run', action='store_true', help='Show chunks and prompts, don\'t dispatch')
    parser.add_argument('--resume', action='store_true', help='Resume from previous run')
    parser.add_argument('--no-linter', action='store_true', help='Skip check-style.py linter')
    parser.add_argument('--no-coherence', action='store_true', help='Skip coherence lens')
    args = parser.parse_args()

    input_file = args.input.resolve()
    if not input_file.exists():
        print(f'File not found: {input_file}', file=sys.stderr)
        sys.exit(1)

    # Load config
    config = load_config(args.config)

    if args.manuscript_type:
        set_manuscript_type(config, args.manuscript_type)

    # Apply CLI overrides
    if args.cli:
        override_cli(config, args.cli)
    if args.parallelism:
        config['dispatch']['parallelism'] = args.parallelism
    if args.timeout_seconds:
        config['dispatch']['timeout_seconds'] = args.timeout_seconds

    project_context = build_project_reference_context(input_file)
    ignore_rules = load_ignore_rules(input_file, project_context.get('project_root'))

    # Determine output directory
    output_dir = args.output_dir or (input_file.parent / config['output']['dir'])
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = output_dir / 'raw'
    raw_dir.mkdir(exist_ok=True)

    # Get lenses
    filter_names = args.lenses.split(',') if args.lenses else None
    lenses = get_enabled_lenses(config, filter_names)
    lens_names = [l['name'] for l in lenses]

    print(f'Input:       {input_file.name}')
    print(f'Type:        {config["manuscript_type"]}')
    print(f'Lenses:      {", ".join(lens_names)}')
    if project_context['external_refs']:
        print(f'Project Refs: {len(project_context["external_refs"])} external labels resolved')
    if ignore_rules:
        print(f'Ignore Rules: {len(ignore_rules)} loaded')
    print(f'Output:      {output_dir}')
    print(f'Parallelism: {config["dispatch"]["parallelism"]}')
    print()

    working_file = input_file
    original_text = input_file.read_text(encoding='utf-8')
    normalized_text, quote_autofix_count = normalize_latex_quotes(original_text)
    if quote_autofix_count:
        working_dir = output_dir / '_working'
        working_dir.mkdir(exist_ok=True)
        working_file = working_dir / input_file.name
        working_file.write_text(normalized_text, encoding='utf-8')
        print(f'Preflight:   normalized {quote_autofix_count} LaTeX quote pair(s) on a working copy')
        print()

    # State management
    state_path = output_dir / 'state.json'
    if args.resume:
        state = load_state(state_path)
        if state and check_file_changed(state, input_file):
            print('WARNING: Input file has changed since last run. Starting fresh.')
            state = init_state(input_file, config)
        elif not state:
            state = init_state(input_file, config)
        else:
            print('Resuming from previous run.')
    else:
        state = init_state(input_file, config)

    start_time = time.time()

    # Step 1: Linter
    linter_findings = []
    if not args.no_linter and not state.get('linter_done'):
        print('Step 1: Running check-style.py linter...')
        linter_findings = run_linter(working_file)
        source_lines = working_file.read_text(encoding='utf-8').splitlines()
        ignore_flags = build_ignore_line_flags(source_lines)
        linter_findings = [
            finding for finding in linter_findings
            if not should_skip_line_ignored_finding(finding, ignore_flags)
            and not should_ignore_finding(finding, input_file, ignore_rules)
        ]
        print(f'  Found {len(linter_findings)} linter violations.')
        state['linter_done'] = True
        save_state(state_path, state)
    elif state.get('linter_done'):
        print('Step 1: Linter already done (resuming).')
    else:
        print('Step 1: Linter skipped.')
    print()

    # Step 2: Chunk the document
    print('Step 2: Chunking document...')
    max_paras = config['chunking']['max_paragraphs']
    chunks = chunk_document(working_file, max_paragraphs=max_paras)
    print(f'  {len(chunks)} chunks created.')
    for c in chunks:
        print(f'    {c.id}: lines {c.start_line}-{c.end_line} ({c.section_path})')
    print()

    if args.dry_run:
        print('--- DRY RUN: showing first chunk x first lens prompt ---')
        if chunks and lenses:
            from dispatcher import _render_chunk_prompt
            prompt = _render_chunk_prompt(
                lenses[0]['name'],
                chunks[0],
                config.get('manuscript_type', 'paper'),
            )
            print(prompt[:2000])
            if len(prompt) > 2000:
                print(f'... ({len(prompt)} chars total)')
        print('--- End dry run ---')
        return

    # Step 3: Dispatch chunk-level lenses
    print('Step 3: Dispatching chunk-level lenses...')
    chunk_lenses = [l for l in lenses if l.get('scope', 'chunk') == 'chunk']

    def skip_fn(chunk_id, lens_name):
        return is_task_done(state, chunk_id, lens_name)

    results = dispatch_all(chunks, chunk_lenses, config, skip_fn=skip_fn)

    # Save raw output and update state
    source_lines = working_file.read_text(encoding='utf-8').splitlines()
    structured_flags = build_structured_line_flags(source_lines)
    example_flags = build_example_line_flags(source_lines)
    ignore_flags = build_ignore_line_flags(source_lines)
    all_llm_findings = []
    for r in results:
        if r.findings:
            r.findings = [
                finding for finding in r.findings
                if not should_skip_line_ignored_finding(finding, ignore_flags)
                and not should_skip_grammar_finding(finding, source_lines)
                and not should_skip_housestyle_finding(
                    finding,
                    source_lines,
                    structured_flags,
                    example_flags,
                )
                and not should_ignore_finding(finding, input_file, ignore_rules)
            ]
        all_llm_findings.extend(r.findings)
        if r.success:
            mark_task_done(state, r.chunk_id, r.lens_name, len(r.findings))

        if config['output'].get('save_raw') and r.raw_output:
            raw_file = raw_dir / f'{r.chunk_id}_{r.lens_name}.txt'
            raw_file.write_text(r.raw_output)

    save_state(state_path, state)
    raw_count = len(all_llm_findings)
    print(f'  {raw_count} raw findings from chunk-level lenses.')
    print()

    # Step 4: Coherence lens (full document)
    coherence_findings = []
    doc_lenses = [l for l in lenses if l.get('scope') == 'document']
    if doc_lenses and not args.no_coherence and not state.get('coherence_done'):
        print('Step 4: Running coherence lens on full document...')
        full_text = working_file.read_text(encoding='utf-8')
        coherence_result = dispatch_coherence(
            full_text,
            doc_lenses[0],
            config,
            project_context['context_text'],
        )
        coherence_result.findings = [
            finding for finding in coherence_result.findings
            if not should_skip_coherence_finding(
                finding,
                set(project_context['external_refs']),
            )
            and not should_ignore_finding(finding, input_file, ignore_rules)
        ]
        coherence_findings = coherence_result.findings
        print(f'  {len(coherence_findings)} coherence findings.')

        if config['output'].get('save_raw') and coherence_result.raw_output:
            raw_file = raw_dir / 'coherence.txt'
            raw_file.write_text(coherence_result.raw_output)

        state['coherence_done'] = True
        save_state(state_path, state)
    else:
        print('Step 4: Coherence lens skipped or already done.')
    print()

    # Step 5: Aggregate and generate report
    print('Step 5: Generating report...')
    elapsed = time.time() - start_time

    clis_used = list({r.cli_used for r in results if r.cli_used})
    report = generate_report(
        input_file=input_file,
        manuscript_type=config['manuscript_type'],
        linter_findings=linter_findings,
        llm_findings=all_llm_findings,
        coherence_findings=coherence_findings,
        raw_count=raw_count,
        lenses_used=lens_names,
        clis_used=clis_used,
        n_chunks=len(chunks),
        elapsed_total=elapsed,
    )

    report_path = output_dir / config['output']['report_name']
    report_path.write_text(report)
    print(f'  Report written to: {report_path}')
    print()

    # Summary
    from aggregator import deduplicate
    deduped = deduplicate(all_llm_findings)
    print('=' * 50)
    print('SUMMARY')
    print('=' * 50)
    print(f'  Linter findings:    {len(linter_findings)}')
    print(f'  LLM findings:       {len(deduped)} (from {raw_count} raw, {raw_count - len(deduped)} duplicates removed)')
    print(f'  Coherence findings: {len(coherence_findings)}')
    print(f'  Total:              {len(linter_findings) + len(deduped) + len(coherence_findings)}')
    print(f'  Wall-clock time:    {elapsed:.1f}s')
    print(f'  Report:             {report_path}')
    print('=' * 50)


if __name__ == '__main__':
    main()
