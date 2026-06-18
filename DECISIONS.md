# Decisions Log — Proofread Harness

2026-03-16 — CLI dispatch over API. Uses subscription credits (codex/gemini/claude/copilot) rather than Anthropic API. Avoids separate billing; matches autoresearch pattern.

2026-03-16 — Chunk-by-lens architecture. Break document into subsection-sized chunks, run each through focused lenses with explicit NOT-lists. Core insight: single-pass proofreading spreads attention thin; multiple focused passes catch more.

2026-03-16 — Pipe-delimited output format. `FINDING|line:N|severity:...|...` More robust than JSON for LLM output; degrades gracefully (one malformed line doesn't corrupt the rest).

2026-03-16 — Five lenses: grammar, argument, grounding, housestyle, coherence. First four are chunk-level; coherence is document-level. Modeled on Language Landscapes editorial review pattern (Lesser/Mendelson/McPhee).

2026-03-16 — python3.11 shebang. Default python3.14 lacks jinja2/pyyaml. Could install there instead.

2026-03-16 — Manuscript type profiles (paper vs textbook). Textbook disables argument and grounding lenses by default; allows longer paragraphs. Added after initial build during live testing on Language Landscapes.

2026-03-18 — Added `langsci` manuscript profile for external Language Science Press proofreading. Defaults to grammar + housestyle only; disables argument, grounding, and coherence because LangSci proofreading is conservative copy-editing, not developmental revision.

2026-03-18 — LangSci mode follows the newer guideline PDFs linked from `langsci.github.io` (proofreading PDF created 2019-05-20; full guidelines PDF created 2020-03-06), not the older 2015 Mendeley copies.
