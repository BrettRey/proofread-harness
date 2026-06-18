"""Known-issue suppression for proofreading findings."""

from __future__ import annotations

from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None


IGNORE_FILENAMES = (
    'proofread-ignore.yaml',
    'proofread-ignore.yml',
    '.proofread-ignore.yaml',
    '.proofread-ignore.yml',
)


def load_ignore_rules(input_file: Path, project_root: Path | None = None) -> list[dict]:
    """Load known-issue rules from the chapter directory and project root."""
    if yaml is None:
        return []

    candidates = []
    seen = set()
    for base in (project_root, input_file.parent):
        if base is None:
            continue
        for filename in IGNORE_FILENAMES:
            path = (base / filename).resolve()
            if path.exists() and path not in seen:
                candidates.append(path)
                seen.add(path)

    rules = []
    for path in candidates:
        data = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
        entries = data if isinstance(data, list) else data.get('ignore', [])
        for entry in entries:
            if isinstance(entry, dict):
                rule = dict(entry)
                rule['_source'] = str(path)
                rules.append(rule)

    return rules


def should_ignore_finding(finding, input_file: Path, rules: list[dict]) -> bool:
    """Return True when a finding matches a known-issue suppression rule."""
    input_name = input_file.name
    input_path = str(input_file)

    for rule in rules:
        if _matches_rule(finding, input_name, input_path, rule):
            return True
    return False


def _matches_rule(finding, input_name: str, input_path: str, rule: dict) -> bool:
    file_rule = rule.get('file')
    if file_rule:
        file_rule = str(file_rule)
        if input_name != file_rule and not input_path.endswith(file_rule):
            return False

    if rule.get('lens') and finding.lens != rule['lens']:
        return False
    if rule.get('category') and finding.category != rule['category']:
        return False
    if rule.get('severity') and finding.severity != rule['severity']:
        return False

    line_rule = rule.get('line')
    if line_rule is not None and finding.line != int(line_rule):
        return False

    haystack = '\n'.join([
        finding.current_text,
        finding.suggested_fix,
        finding.explanation,
    ]).lower()

    if not _contains_match(haystack, rule.get('contains')):
        return False
    if not _contains_match(finding.current_text.lower(), rule.get('current_contains')):
        return False
    if not _contains_match(finding.suggested_fix.lower(), rule.get('fix_contains')):
        return False
    if not _contains_match(finding.explanation.lower(), rule.get('explanation_contains')):
        return False

    return True


def _contains_match(haystack: str, needle: str | None) -> bool:
    if needle is None:
        return True
    return str(needle).lower() in haystack
