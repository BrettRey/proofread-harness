"""Aggregate, deduplicate, and generate the final report."""

from datetime import datetime, timezone
from pathlib import Path

from models import Finding


SEVERITY_ORDER = {'critical': 0, 'major': 1, 'minor': 2}


def deduplicate(findings: list[Finding]) -> list[Finding]:
    """Remove duplicate findings based on content hash.

    When two lenses flag the same issue, keep the one with higher severity.
    """
    seen: dict[str, Finding] = {}

    for f in findings:
        h = f.content_hash
        if h not in seen:
            seen[h] = f
        else:
            existing = seen[h]
            if SEVERITY_ORDER.get(f.severity, 9) < SEVERITY_ORDER.get(existing.severity, 9):
                seen[h] = f

    return list(seen.values())


def sort_findings(findings: list[Finding]) -> list[Finding]:
    """Sort by severity (critical first), then by line number."""
    return sorted(findings, key=lambda f: (SEVERITY_ORDER.get(f.severity, 9), f.line))


def group_by_severity(findings: list[Finding]) -> dict[str, list[Finding]]:
    """Group findings by severity level."""
    groups: dict[str, list[Finding]] = {'critical': [], 'major': [], 'minor': []}
    for f in findings:
        groups.setdefault(f.severity, []).append(f)
    return groups


def generate_report(
    input_file: Path,
    manuscript_type: str,
    linter_findings: list[Finding],
    llm_findings: list[Finding],
    coherence_findings: list[Finding],
    raw_count: int,
    lenses_used: list[str],
    clis_used: list[str],
    n_chunks: int,
    elapsed_total: float,
) -> str:
    """Generate the final markdown report."""
    all_llm = deduplicate(llm_findings)
    all_llm = sort_findings(all_llm)
    dedup_removed = raw_count - len(all_llm)

    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')

    lines = []
    lines.append(f'# Proofread Report: {input_file.name}')
    lines.append('')
    lines.append(f'**Date:** {now}')
    lines.append(f'**Manuscript Type:** {manuscript_type}')
    lines.append(f'**Lenses:** {", ".join(sorted(set(lenses_used)))}')
    lines.append(f'**CLIs:** {", ".join(sorted(set(clis_used)))}')
    lines.append(f'**Chunks processed:** {n_chunks}')
    lines.append(f'**Total findings:** {len(linter_findings) + len(all_llm) + len(coherence_findings)} '
                 f'(linter: {len(linter_findings)}, LLM: {len(all_llm)}, coherence: {len(coherence_findings)})')
    lines.append(f'**Duplicates removed:** {dedup_removed}')
    lines.append(f'**Wall-clock time:** {elapsed_total:.1f}s')
    lines.append('')

    # Linter results
    if linter_findings:
        lines.append('---')
        lines.append('')
        lines.append('## Linter Results (check-style.py)')
        lines.append('')
        lines.append('| # | Line | Issue | Context |')
        lines.append('|---|------|-------|---------|')
        for i, f in enumerate(linter_findings, 1):
            ctx = f.current_text[:60].replace('|', '\\|') if f.current_text else ''
            issue = f.suggested_fix[:60].replace('|', '\\|')
            lines.append(f'| {i} | {f.line} | {issue} | {ctx} |')
        lines.append('')

    # LLM findings by severity
    if all_llm:
        lines.append('---')
        lines.append('')
        lines.append('## LLM Findings')
        lines.append('')

        groups = group_by_severity(all_llm)
        for sev in ('critical', 'major', 'minor'):
            items = groups.get(sev, [])
            if not items:
                continue
            lines.append(f'### {sev.capitalize()} ({len(items)})')
            lines.append('')
            lines.append('| # | Line | Category | Lens | Current Text | Suggested Fix | Explanation |')
            lines.append('|---|------|----------|------|-------------|---------------|-------------|')
            for i, f in enumerate(items, 1):
                cur = f.current_text[:50].replace('|', '\\|')
                fix = f.suggested_fix[:50].replace('|', '\\|')
                exp = f.explanation[:60].replace('|', '\\|')
                lines.append(f'| {i} | {f.line} | {f.category} | {f.lens} | {cur} | {fix} | {exp} |')
            lines.append('')

    # Coherence findings
    if coherence_findings:
        lines.append('---')
        lines.append('')
        lines.append('## Coherence Notes')
        lines.append('')
        for i, f in enumerate(coherence_findings, 1):
            lines.append(f'{i}. **Line ~{f.line}** [{f.severity}]: {f.explanation}')
            if f.suggested_fix:
                lines.append(f'   - Fix: {f.suggested_fix}')
        lines.append('')

    # Statistics
    lines.append('---')
    lines.append('')
    lines.append('## Statistics')
    lines.append('')

    # Count by lens
    lens_counts: dict[str, int] = {}
    for f in all_llm:
        lens_counts[f.lens] = lens_counts.get(f.lens, 0) + 1
    for lens, count in sorted(lens_counts.items()):
        lines.append(f'- {lens}: {count} findings')
    lines.append(f'- Duplicates removed: {dedup_removed}')
    lines.append('')

    return '\n'.join(lines)
