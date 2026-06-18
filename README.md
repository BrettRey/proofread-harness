# proofread-harness

A multi-pass proofreading harness for LaTeX manuscripts. It breaks a document
into subsection-sized chunks, runs each chunk through several focused "lenses"
(grammar, house style, and others), aggregates and de-duplicates the findings,
and writes a single Markdown report with line numbers.

The guiding idea: a single proofreading pass spreads attention thin. Several
narrow passes, each told to look for one kind of problem and to ignore the
rest, catch more.

It includes a **`langsci` profile** that encodes the
[Language Science Press proofreading guidelines](https://langsci.github.io/guidelines/latexguidelines/LangSci-guidelines-proofreading.pdf)
for conservative, external-proofreader copy-editing.

## How it works

Each lens is a separate call to a coding-assistant CLI you already have
installed (`codex`, `gemini`, `claude`, or `copilot`). The harness shells out
to whichever CLI a lens is configured to use, so it runs on your existing
subscription rather than a metered API key. Nothing is sent anywhere except
through the CLI you choose.

```
input.tex
   │
   ├─ optional static linter pass (skipped if none configured)
   │
   ├─ chunk into ~8-paragraph sections (with overlap)
   │
   ├─ per chunk × per lens  ──►  CLI call  ──►  raw findings
   │      grammar, housestyle, argument, grounding   (chunk-level)
   │
   ├─ coherence lens over the whole document         (document-level)
   │
   └─ aggregate + de-duplicate  ──►  proofread-report.md
```

The five lenses:

| Lens | Scope | What it looks for |
|------|-------|-------------------|
| `grammar` | chunk | Sentence-level grammar, agreement, punctuation |
| `housestyle` | chunk | House-style and (in `langsci` mode) LangSci formatting/reference rules |
| `argument` | chunk | Argument gaps, unsupported claims |
| `grounding` | chunk | Claims that should be cited or are at risk of fabrication |
| `coherence` | document | Cross-references, terminology drift, structural consistency |

## Manuscript profiles

`--manuscript-type` (or `manuscript_type:` in a config file) sets which lenses
are on by default:

- **`paper`** — all five lenses (research-article default).
- **`textbook`** — grammar + housestyle + coherence; argument and grounding off.
- **`langsci`** — grammar + housestyle only. Argument, grounding, and coherence
  are off because external LangSci proofreading is conservative copy-editing,
  not developmental revision. See [`LANGSCI_MODE.md`](LANGSCI_MODE.md) for the
  exact rule set this profile applies.

## Requirements

- Python 3.11+
- `jinja2` and `pyyaml` (`pip install -r requirements.txt`)
- At least one assistant CLI on your `PATH`: `codex`, `gemini`, `claude`, or
  `copilot`. The default config uses `codex` for every lens; change the `cli:`
  field per lens to mix and match (for example, a long-context model for the
  document-level coherence lens).

## Usage

```bash
pip install -r requirements.txt

# Research paper, all lenses
python run.py paper.tex

# LangSci external proofreading
python run.py chapter.tex --config langsci-proofread.yaml
#   or equivalently:
python run.py chapter.tex --manuscript-type langsci

# Pick lenses / CLI explicitly
python run.py paper.tex --lenses grammar,housestyle --cli codex

# See the chunks and the first prompt without dispatching anything
python run.py paper.tex --dry-run

# Resume an interrupted run
python run.py paper.tex --resume
```

The report lands in `proofread-output/proofread-report.md` next to the input
file. Raw per-lens output is kept under `proofread-output/raw/` for debugging.

### Useful flags

| Flag | Effect |
|------|--------|
| `--manuscript-type {paper,textbook,langsci}` | Built-in profile |
| `--lenses a,b,c` | Run only these lenses |
| `--cli {codex,gemini,claude,copilot}` | Force one CLI for all lenses |
| `--parallelism N` | Max concurrent CLI calls |
| `--dry-run` | Show chunks + first prompt, dispatch nothing |
| `--resume` | Continue a previous run |
| `--no-linter` | Skip the static linter pass |
| `--no-coherence` | Skip the document-level lens |

## Configuration

Copy `config-schema.yaml`, edit it, and pass it with `--config`. It controls the
manuscript profile, per-lens CLI and enable/disable, chunk size, parallelism,
timeouts, and output paths. Per-project suppressions go in a
`proofread-ignore.yaml` beside the manuscript (format documented at the top of
`config-schema.yaml`).

### Optional static linter

If you have a static style checker (a `check-style.py`-style script), the
harness will run it first and fold its findings into the report. It looks for
`.house-style/check-style.py` near the input file, then at the path in the
`PROOFREAD_LINTER` environment variable. If neither exists, the linter pass is
silently skipped. No linter is bundled here.

## Caveats

- The lenses are LLM-driven. Treat the report as a **first pass for a human**,
  not a verdict. Verify before acting, especially on anything numeric or
  bibliographic.
- It expects LaTeX **source**. It can't read a PDF; chunking keys off `\section`
  and paragraph structure.
- This is independent software. It is **not** an official Language Science Press
  tool; the `langsci` profile simply encodes their published proofreading rules.

## License

MIT. See [`LICENSE`](LICENSE).
