# LangSci Mode

Compact mode spec for using `tools/proofread-harness/` on Language Science Press proofreading assignments.

## Purpose

This mode is for **external proofreader** work on near-final LangSci chapters. It is **not** for developmental editing, argument critique, or authorial prose optimization.

Default profile: `manuscript_type: langsci`

Enabled by default:
- `grammar`
- `housestyle`

Disabled by default:
- `argument`
- `grounding`
- `coherence`

Reason: LangSci proofreading asks for conservative copy-editing and reference/example cleanup, not substantive revision.

## What To Flag

- Clear sentence-level grammar problems
- Inconsistent British vs. American spelling within the chapter
- `Section`, `Table`, `Figure` not capitalized in cross-references when present as words
- Spacing after punctuation and parentheses
- Badly formed parentheses in citations/references
- Reference-list issues:
  - `et al.` used in the list of references
  - first names abbreviated where full first names should appear
  - subtitles not capitalized
  - proper nouns not capitalized
  - German nouns not capitalized
  - extraneous bibliography information
  - malformed series title/series number formatting
- Gloss/example issues:
  - italicized parentheses/brackets/subscripts/footnote marks
  - full-sentence examples missing final punctuation in source and translation
  - fragment examples incorrectly punctuated
  - broken gloss alignment
- LangSci summary-rule violations:
  - bold used for emphasis
  - underline used for emphasis
  - vertical table rules
  - acknowledgements in a footnote rather than final section
  - footnote number before punctuation

## What Not To Flag

- Margin spillover / overfull lines
- Developmental or structural rewrite suggestions
- Argument quality, theoretical framing, or source-grounding critique
- Mere stylistic alternatives when the prose is already grammatical
- Preferences from the local project house style that are not LangSci rules

## Current Rule Sources

- Newer proofreader guidelines: `https://langsci.github.io/guidelines/latexguidelines/LangSci-guidelines-proofreading.pdf`
  - PDF metadata observed locally: created `2019-05-20`
- Newer full guidelines: `https://langsci.github.io/guidelines/latexguidelines/LangSci-guidelines.pdf`
  - PDF metadata observed locally: created `2020-03-06`

These are newer than the older 2015 PDFs in `~/Documents/Mendeley Desktop/`.

## Recommended Invocation

```bash
python tools/proofread-harness/run.py chapter.tex \
  --config tools/proofread-harness/langsci-proofread.yaml
```

If you want a document-level pass just for cross-reference sanity, re-enable `coherence` manually, but keep its findings conservative.
