"""Document chunking for LaTeX and Markdown sources."""

import re
from pathlib import Path
from models import Chunk


# LaTeX section commands in order of depth
LATEX_SECTION_COMMANDS = [
    r'\\section\*?\{',
    r'\\subsection\*?\{',
    r'\\subsubsection\*?\{',
]

LATEX_SECTION_RE = re.compile(
    r'\\(section|subsection|subsubsection)\*?\{([^}]+)\}'
)

# Markdown ATX headings: "# Title", "## Title", etc.
MARKDOWN_SECTION_RE = re.compile(
    r'^(#{1,6})\s+(.+?)(?:\s+#+\s*)?$'
)

# Environments to skip entirely (not prose)
SKIP_ENVS = {
    'equation', 'equation*', 'align', 'align*', 'gather', 'gather*',
    'tikzpicture', 'lstlisting', 'verbatim', 'figure', 'table',
}


def extract_section_title(line: str) -> str | None:
    """Extract section title from a line, or None."""
    latex = LATEX_SECTION_RE.search(line)
    if latex:
        return latex.group(2).strip()

    markdown = MARKDOWN_SECTION_RE.match(line.strip())
    if markdown:
        return markdown.group(2).strip()

    return None


def _match_section_boundary(line: str) -> tuple[str, int] | None:
    """Return (title, level) for a recognized section heading."""
    latex = LATEX_SECTION_RE.search(line)
    if latex:
        cmd = latex.group(1)
        level = {'section': 1, 'subsection': 2, 'subsubsection': 3}[cmd]
        return latex.group(2).strip(), level

    markdown = MARKDOWN_SECTION_RE.match(line.strip())
    if markdown:
        level = len(markdown.group(1))
        return markdown.group(2).strip(), level

    return None


def find_section_boundaries(lines: list[str]) -> list[dict]:
    """Find all section/subsection boundaries with line numbers.

    Returns list of dicts: {title, level, start_line, end_line}
    """
    boundaries = []
    for i, line in enumerate(lines):
        match = _match_section_boundary(line)
        if match:
            title, level = match
            boundaries.append({
                'title': title,
                'level': level,
                'start_line': i,
            })

    # Set end_line for each section (up to the next section or EOF)
    for j, b in enumerate(boundaries):
        if j + 1 < len(boundaries):
            b['end_line'] = boundaries[j + 1]['start_line'] - 1
        else:
            b['end_line'] = len(lines) - 1

    return boundaries


def split_into_paragraphs(lines: list[str], start_offset: int) -> list[dict]:
    """Split lines into paragraphs (separated by blank lines).

    Returns list of dicts: {content, start_line, end_line}
    where start_line/end_line are 1-indexed line numbers in the source file.
    """
    paragraphs = []
    current_lines = []
    current_start = None

    for i, line in enumerate(lines):
        line_num = start_offset + i + 1  # 1-indexed

        if line.strip() == '':
            if current_lines:
                paragraphs.append({
                    'content': '\n'.join(current_lines),
                    'start_line': current_start,
                    'end_line': line_num - 1,
                })
                current_lines = []
                current_start = None
        else:
            if current_start is None:
                current_start = line_num
            current_lines.append(line)

    # Don't forget the last paragraph
    if current_lines:
        paragraphs.append({
            'content': '\n'.join(current_lines),
            'start_line': current_start,
            'end_line': start_offset + len(lines),
        })

    return paragraphs


def chunk_document(filepath: str | Path, max_paragraphs: int = 8) -> list[Chunk]:
    """Chunk a LaTeX document into proofreading units.

    Strategy:
    1. Find section boundaries
    2. Split each section into paragraphs
    3. If a section has > max_paragraphs, split into sub-chunks
    4. Add overlap context (last paragraph of previous chunk)
    """
    path = Path(filepath)
    text = path.read_text(encoding='utf-8')
    lines = text.split('\n')

    sections = find_section_boundaries(lines)

    if not sections:
        # No sections found -- treat whole document as one section
        sections = [{'title': 'Document', 'level': 0, 'start_line': 0, 'end_line': len(lines) - 1}]

    chunks = []

    for sec in sections:
        sec_lines = lines[sec['start_line']:sec['end_line'] + 1]
        paragraphs = split_into_paragraphs(sec_lines, sec['start_line'])

        if not paragraphs:
            continue

        # Build section path for ID
        section_path = sec['title']

        if len(paragraphs) <= max_paragraphs:
            # Single chunk for this section
            content = '\n\n'.join(p['content'] for p in paragraphs)
            chunk_id = _make_id(section_path, 0)
            chunks.append(Chunk(
                id=chunk_id,
                content=content,
                start_line=paragraphs[0]['start_line'],
                end_line=paragraphs[-1]['end_line'],
                section_path=section_path,
            ))
        else:
            # Split into sub-chunks
            for j in range(0, len(paragraphs), max_paragraphs):
                sub = paragraphs[j:j + max_paragraphs]
                content = '\n\n'.join(p['content'] for p in sub)
                chunk_id = _make_id(section_path, j // max_paragraphs)
                chunks.append(Chunk(
                    id=chunk_id,
                    content=content,
                    start_line=sub[0]['start_line'],
                    end_line=sub[-1]['end_line'],
                    section_path=section_path,
                ))

    # Add overlap context
    for i, chunk in enumerate(chunks):
        if i > 0:
            prev_paras = chunks[i - 1].content.split('\n\n')
            chunk.context_before = prev_paras[-1] if prev_paras else ''
        if i < len(chunks) - 1:
            next_paras = chunks[i + 1].content.split('\n\n')
            chunk.context_after = next_paras[0] if next_paras else ''

    return chunks


def _make_id(section_title: str, sub_index: int) -> str:
    """Create a chunk ID from section title and sub-index."""
    slug = re.sub(r'[^a-z0-9]+', '-', section_title.lower()).strip('-')[:30]
    return f"{slug}-{sub_index}"
