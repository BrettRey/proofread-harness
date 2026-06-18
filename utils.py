"""Shared utilities for the proofreading harness."""

import re


STRUCTURED_LAYOUT_ENV_RE = re.compile(
    r'\\(begin|end)\{'
    r'(tabular|tabular\*|tabularx|array|align|align\*|aligned|alignedat|gather|gather\*)'
    r'\}'
)
EXAMPLE_START_RE = re.compile(r'^\s*\\ea(?:\b|\[)')
EXAMPLE_END_RE = re.compile(r'\\z\b')
IGNORE_COMMENT_RE = re.compile(r'(?<!\\)%\s*proofread:ignore\b')


def strip_latex(text: str) -> str:
    """Strip LaTeX commands to extract prose. Borrowed from check-style.py."""
    text = re.sub(r'(?<!\\)%.*', '', text)
    text = re.sub(
        r'\\begin\{(equation|align|verbatim|lstlisting|tikzpicture)\*?\}.*?\\end\{\1\*?\}',
        '', text, flags=re.DOTALL,
    )
    text = re.sub(r'\\[a-zA-Z]+\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\[a-zA-Z]+', '', text)
    text = re.sub(r'[{}~\\]', ' ', text)
    return text


def strip_comments(line: str) -> str:
    """Strip LaTeX comments from a single line, respecting escaped percent signs."""
    return re.sub(r'(?<!\\)%.*', '', line)


def normalize_latex_quotes(text: str) -> tuple[str, int]:
    r"""Normalize ``...'' quote pairs to \enquote{...} on a working copy."""
    pattern = re.compile(r"``([^`\n]+?)''")
    quote_count = 0
    normalized_lines = []

    for line in text.splitlines():
        def repl(match: re.Match) -> str:
            nonlocal quote_count
            quote_count += 1
            return f'\\enquote{{{match.group(1)}}}'

        normalized_lines.append(pattern.sub(repl, line))

    normalized = '\n'.join(normalized_lines)
    if text.endswith('\n'):
        normalized += '\n'
    return normalized, quote_count


def is_prose_line(line: str) -> bool:
    """Check if a line is prose (not a command, comment, or blank)."""
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.startswith('%'):
        return False
    if stripped.startswith('\\begin{') or stripped.startswith('\\end{'):
        return False
    if stripped.startswith('\\ea') or stripped.startswith('\\z'):
        return False
    return True


def build_structured_line_flags(lines: list[str]) -> list[bool]:
    """Mark lines that belong to table-like or aligned display layouts."""
    flags = []
    layout_depth = 0

    for line in lines:
        line_no_comments = strip_comments(line)
        matches = STRUCTURED_LAYOUT_ENV_RE.findall(line_no_comments)
        begins = sum(1 for kind, _ in matches if kind == 'begin')
        ends = sum(1 for kind, _ in matches if kind == 'end')
        inline_layout_row = '&' in line_no_comments and '\\\\' in line_no_comments
        in_structured_layout = layout_depth > 0 or begins > 0 or inline_layout_row
        flags.append(in_structured_layout)
        layout_depth = max(0, layout_depth + begins - ends)

    return flags


def build_example_line_flags(lines: list[str]) -> list[bool]:
    """Mark lines that occur inside numbered linguistic examples (`\\ea` ... `\\z`)."""
    flags = []
    example_depth = 0

    for line in lines:
        line_no_comments = strip_comments(line)
        starts_example = 1 if EXAMPLE_START_RE.search(line_no_comments) else 0
        ends_example = len(EXAMPLE_END_RE.findall(line_no_comments))
        in_example = example_depth > 0 or starts_example > 0
        flags.append(in_example)
        example_depth = max(0, example_depth + starts_example - ends_example)

    return flags


def build_ignore_line_flags(lines: list[str]) -> list[bool]:
    """Mark lines suppressed by inline `% proofread:ignore` directives."""
    flags = []
    ignore_next_content = False

    for line in lines:
        stripped = line.strip()
        comment_match = IGNORE_COMMENT_RE.search(line)
        is_comment_only = stripped.startswith('%')
        has_content = bool(strip_comments(line).strip())

        ignore_this_line = bool(comment_match and not is_comment_only)
        if ignore_next_content and has_content:
            ignore_this_line = True
            ignore_next_content = False

        flags.append(ignore_this_line)

        if comment_match and is_comment_only:
            ignore_next_content = True

    return flags


def should_skip_line_ignored_finding(finding, ignore_flags: list[bool]) -> bool:
    """Skip findings on lines explicitly ignored in the source."""
    idx = finding.line - 1
    if idx < 0 or idx >= len(ignore_flags):
        return False
    return ignore_flags[idx]


def should_skip_grammar_finding(finding, source_lines: list[str]) -> bool:
    """Filter recurring false positives from the grammar lens."""
    if finding.lens != 'grammar' or finding.category != 'grammar':
        return False

    idx = finding.line - 1
    if idx < 0 or idx >= len(source_lines):
        return False

    line = strip_latex(strip_comments(source_lines[idx])).lower()
    haystack = ' '.join([finding.current_text, finding.suggested_fix, finding.explanation]).lower()

    teacher_voice_case = (
        re.search(r'\b(?:most\s+)?(?:english|language)\s+teachers\b', line)
        and re.search(r'\b(we|our|us)\b', line)
        and ('antecedent' in haystack or 'pronoun' in haystack or 'shift from' in haystack)
    )
    if teacher_voice_case:
        return True

    recoverable_go_without_case = (
        "can't go without" in line
        and ('required complement after “without' in haystack or "required complement after 'without" in haystack)
    )
    if recoverable_go_without_case:
        return True

    return False


def should_skip_housestyle_finding(
    finding,
    source_lines: list[str],
    structured_flags: list[bool],
    example_flags: list[bool],
) -> bool:
    """Filter recurring false positives from the housestyle lens."""
    if finding.lens != 'housestyle' or finding.category != 'style':
        return False

    idx = finding.line - 1
    if idx < 0 or idx >= len(source_lines):
        return False

    line = source_lines[idx]
    explanation = finding.explanation.lower()
    semantic_macro_case = (
        'semantic macro' in explanation
        or '\\mention{' in finding.suggested_fix
        or '\\term{' in finding.suggested_fix
    )
    if not semantic_macro_case:
        return False

    if structured_flags[idx] and ('\\textit{' in line or '\\emph{' in line):
        return True

    if example_flags[idx] and ('\\textit{' in line or '\\emph{' in line):
        return True

    if '\\textit{' in line and '\\emph{' in line:
        return True

    return False
