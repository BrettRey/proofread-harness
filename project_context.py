"""Project-level context helpers for chapter-local proofreading runs."""

from __future__ import annotations

import re
from pathlib import Path


AUX_LABEL_RE = re.compile(
    r'\\newlabel\{([^}]+)\}\{\{([^}]*)\}\{([^}]*)\}\{([^}]*)\}\{([^}]*)\}'
)
TEX_LABEL_RE = re.compile(r'\\label\{([^}]+)\}')
BRACE_REF_RE = re.compile(r'\\(?:auto|page|v)?refp?\*?\{([^}]+)\}')
HYPERREF_RE = re.compile(r'\\hyperref\[([^\]]+)\]\{[^}]*\}')
LABEL_TOKEN_RE = re.compile(r'\b[a-zA-Z][\w.-]*:[\w.-]+\b')


def find_project_root(input_file: Path) -> Path | None:
    """Find the nearest ancestor that looks like a LaTeX project root."""
    current = input_file.resolve().parent
    for candidate in [current, *current.parents]:
        if (candidate / 'main.aux').exists() or (candidate / 'main.tex').exists():
            return candidate
    return None


def _parse_aux_labels(aux_path: Path) -> dict[str, dict]:
    """Parse `\\newlabel` entries from an aux file."""
    labels: dict[str, dict] = {}
    for line in aux_path.read_text(encoding='utf-8', errors='ignore').splitlines():
        match = AUX_LABEL_RE.match(line.strip())
        if not match:
            continue
        name, number, _page, title, anchor = match.groups()
        labels[name] = {
            'number': number,
            'title': title,
            'anchor': anchor,
            'source': str(aux_path),
        }
    return labels


def _parse_tex_labels(tex_path: Path) -> dict[str, dict]:
    """Parse `\\label{...}` entries from a tex file as a fallback."""
    labels: dict[str, dict] = {}
    for line in tex_path.read_text(encoding='utf-8', errors='ignore').splitlines():
        for match in TEX_LABEL_RE.finditer(line):
            name = match.group(1)
            labels.setdefault(
                name,
                {
                    'number': '',
                    'title': '',
                    'anchor': '',
                    'source': str(tex_path),
                },
            )
    return labels


def collect_project_labels(project_root: Path) -> dict[str, dict]:
    """Collect known labels from project aux files, falling back to tex labels."""
    labels: dict[str, dict] = {}

    aux_files = sorted(project_root.rglob('*.aux'))
    for aux_path in aux_files:
        labels.update(_parse_aux_labels(aux_path))

    if labels:
        return labels

    for tex_path in sorted(project_root.rglob('*.tex')):
        labels.update(_parse_tex_labels(tex_path))
    return labels


def extract_defined_labels(text: str) -> set[str]:
    """Extract labels defined in the provided tex text."""
    return {match.group(1) for match in TEX_LABEL_RE.finditer(text)}


def extract_referenced_labels(text: str) -> set[str]:
    """Extract label names referenced from the provided tex text."""
    refs = {match.group(1) for match in BRACE_REF_RE.finditer(text)}
    refs.update(match.group(1) for match in HYPERREF_RE.finditer(text))
    return refs


def build_project_reference_context(input_file: Path) -> dict:
    """Build chapter-external reference context for the coherence lens."""
    text = input_file.read_text(encoding='utf-8')
    project_root = find_project_root(input_file)
    if project_root is None:
        return {
            'project_root': None,
            'known_project_labels': {},
            'external_refs': [],
            'context_text': '',
        }

    project_labels = collect_project_labels(project_root)
    if not project_labels:
        return {
            'project_root': project_root,
            'known_project_labels': {},
            'external_refs': [],
            'context_text': '',
        }

    local_labels = extract_defined_labels(text)
    referenced_labels = extract_referenced_labels(text)
    external_refs = sorted(
        label for label in referenced_labels
        if label in project_labels and label not in local_labels
    )

    if not external_refs:
        return {
            'project_root': project_root,
            'known_project_labels': project_labels,
            'external_refs': [],
            'context_text': '',
        }

    lines = [
        'This chapter is part of a larger LaTeX project.',
        'Treat the following referenced labels as valid project targets even if their destination text is outside the supplied chapter.',
        'Do NOT flag any of these as missing or unresolved cross-references:',
        '',
    ]
    for label in external_refs:
        meta = project_labels.get(label, {})
        title = meta.get('title', '').strip()
        if title:
            lines.append(f'- {label} -> {title}')
        else:
            lines.append(f'- {label}')

    return {
        'project_root': project_root,
        'known_project_labels': project_labels,
        'external_refs': external_refs,
        'context_text': '\n'.join(lines),
    }


def extract_labels_from_snippet(text: str) -> set[str]:
    """Extract label tokens from a model finding snippet."""
    labels = {match.group(1) for match in BRACE_REF_RE.finditer(text)}
    labels.update(match.group(1) for match in HYPERREF_RE.finditer(text))
    labels.update(match.group(0) for match in LABEL_TOKEN_RE.finditer(text))
    return labels


def should_skip_coherence_finding(finding, known_external_refs: set[str]) -> bool:
    """Suppress cross-reference false positives when the label exists elsewhere in the project."""
    if finding.lens != 'coherence' or finding.category != 'quality':
        return False
    if not known_external_refs:
        return False

    explanation = finding.explanation.lower()
    if 'cross-reference' not in explanation and 'unresolved' not in explanation:
        return False

    haystack = '\n'.join([finding.current_text, finding.suggested_fix, finding.explanation])
    labels = extract_labels_from_snippet(haystack)
    return bool(labels) and labels.issubset(known_external_refs)
