"""Integration with an optional check-style.py linter.

The linter is an optional, house-style-specific static checker. It is not
shipped with this harness. If none is found the linter pass is skipped and the
LLM lenses run on their own. Point the harness at your own linter with the
PROOFREAD_LINTER environment variable.
"""

import os
import re
import subprocess
from pathlib import Path
from models import Finding


# Search paths for check-style.py, relative to the input file
LINTER_SEARCH = [
    '.house-style/check-style.py',
    '../../.house-style/check-style.py',
]


def find_linter(input_file: Path) -> Path | None:
    """Find check-style.py near the input file or via $PROOFREAD_LINTER."""
    # Check relative to input file
    for rel in LINTER_SEARCH:
        candidate = input_file.parent / rel
        if candidate.exists():
            return candidate.resolve()

    # Explicit override via environment variable
    env_path = os.environ.get('PROOFREAD_LINTER')
    if env_path:
        candidate = Path(env_path).expanduser()
        if candidate.exists():
            return candidate.resolve()

    return None


def run_linter(input_file: Path) -> list[Finding]:
    """Run check-style.py and parse its output into Finding objects."""
    linter_path = find_linter(input_file)
    if not linter_path:
        print("  check-style.py not found; skipping linter pass.")
        return []

    try:
        result = subprocess.run(
            ['python3', str(linter_path), str(input_file)],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        print("  Linter timed out.")
        return []

    output = result.stdout + result.stderr
    return _parse_linter_output(output)


def _parse_linter_output(output: str) -> list[Finding]:
    """Parse check-style.py output into Finding objects."""
    findings = []
    lines = output.split('\n')

    # Pattern: "  Line 42: issue description"
    line_re = re.compile(r'^\s+Line (\d+): (.+)$')
    # Context line follows: "    context text..."
    context_re = re.compile(r'^\s{4,}(.+)$')

    i = 0
    while i < len(lines):
        m = line_re.match(lines[i])
        if m:
            line_num = int(m.group(1))
            issue = m.group(2)

            # Check for context on next line
            context = ''
            if i + 1 < len(lines):
                cm = context_re.match(lines[i + 1])
                if cm:
                    context = cm.group(1).strip()
                    i += 1

            # Determine severity
            severity = 'minor'
            if 'CRITICAL' in issue.upper() or '---' in issue:
                severity = 'major'

            findings.append(Finding(
                line=line_num,
                category='style',
                severity=severity,
                lens='linter',
                current_text=context,
                suggested_fix=issue,
                explanation=f'check-style.py: {issue}',
                chunk_id='linter',
            ))
        i += 1

    return findings
