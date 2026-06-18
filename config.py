"""Configuration loading and validation."""

from copy import deepcopy
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None


# Built-in lens definitions
BASE_LENSES = [
    {'name': 'grammar', 'cli': 'codex', 'scope': 'chunk', 'enabled': True},
    {'name': 'argument', 'cli': 'codex', 'scope': 'chunk', 'enabled': True},
    {'name': 'grounding', 'cli': 'codex', 'scope': 'chunk', 'enabled': True},
    {'name': 'housestyle', 'cli': 'codex', 'scope': 'chunk', 'enabled': True},
    {'name': 'coherence', 'cli': 'codex', 'scope': 'document', 'enabled': True},
]

# Default lens profiles by manuscript type
MANUSCRIPT_LENS_DEFAULTS = {
    'paper': {
        'grammar': True,
        'argument': True,
        'grounding': True,
        'housestyle': True,
        'coherence': True,
    },
    'textbook': {
        'grammar': True,
        'argument': False,
        'grounding': False,
        'housestyle': True,
        'coherence': True,
    },
    'langsci': {
        'grammar': True,
        'argument': False,
        'grounding': False,
        'housestyle': True,
        'coherence': False,
    },
}

# Defaults for config keys
DEFAULTS = {
    'manuscript_type': 'paper',
    'lenses': [
        {'name': 'grammar', 'cli': 'codex', 'scope': 'chunk', 'enabled': True},
        {'name': 'argument', 'cli': 'codex', 'scope': 'chunk', 'enabled': True},
        {'name': 'grounding', 'cli': 'codex', 'scope': 'chunk', 'enabled': True},
        {'name': 'housestyle', 'cli': 'codex', 'scope': 'chunk', 'enabled': True},
        {'name': 'coherence', 'cli': 'codex', 'scope': 'document', 'enabled': True},
    ],
    'chunking': {
        'max_paragraphs': 8,
        'overlap_paragraphs': 1,
    },
    'dispatch': {
        'parallelism': 6,
        'timeout_seconds': 120,
        'retry_on_failure': 1,
        'temp_dir': '/tmp/proofread-harness',
    },
    'output': {
        'dir': 'proofread-output',
        'report_name': 'proofread-report.md',
        'save_raw': True,
    },
}

VALID_CLIS = {'codex', 'gemini', 'claude', 'copilot'}
VALID_SCOPES = {'chunk', 'document'}
VALID_LENSES = {'grammar', 'argument', 'grounding', 'housestyle', 'coherence'}
VALID_MANUSCRIPT_TYPES = set(MANUSCRIPT_LENS_DEFAULTS)


def _default_lenses(manuscript_type: str) -> list[dict]:
    """Return built-in lenses with the profile defaults applied."""
    enabled_by_lens = MANUSCRIPT_LENS_DEFAULTS[manuscript_type]
    lenses = []
    for lens in BASE_LENSES:
        lens_copy = dict(lens)
        lens_copy['enabled'] = enabled_by_lens.get(lens_copy['name'], lens_copy.get('enabled', True))
        lenses.append(lens_copy)
    return lenses


def _merge_lenses(config_lenses: list[dict] | None, manuscript_type: str) -> list[dict]:
    """Merge explicit lens config onto the manuscript-profile defaults."""
    merged_by_name = {lens['name']: lens for lens in _default_lenses(manuscript_type)}
    base_order = [lens['name'] for lens in BASE_LENSES]

    if not config_lenses:
        return list(merged_by_name.values())

    extras = []
    for lens in config_lenses:
        lens_copy = dict(lens)
        name = lens_copy.get('name')
        if name in merged_by_name:
            merged = dict(merged_by_name[name])
            merged.update(lens_copy)
            merged_by_name[name] = merged
        else:
            extras.append(lens_copy)

    return [merged_by_name[name] for name in base_order] + extras


def load_config(config_path: Path | None = None) -> dict:
    """Load config from YAML file, falling back to defaults."""
    config = {}

    if config_path and config_path.exists():
        if yaml is None:
            print("pyyaml not installed. Install with: pip3 install pyyaml", file=sys.stderr)
            print("Using defaults instead.", file=sys.stderr)
        else:
            with open(config_path) as f:
                config = yaml.safe_load(f) or {}

    manuscript_type = config.get('manuscript_type', DEFAULTS['manuscript_type'])
    result = {
        'manuscript_type': manuscript_type,
        'lenses': _merge_lenses(config.get('lenses'), manuscript_type),
    }

    # Merge non-lens keys with defaults
    for key, default in DEFAULTS.items():
        if key in {'manuscript_type', 'lenses'}:
            continue
        if key in config:
            if isinstance(default, dict):
                merged = deepcopy(default)
                merged.update(config[key])
                result[key] = merged
            else:
                result[key] = deepcopy(config[key])
        else:
            result[key] = deepcopy(default)

    # Copy non-default keys
    for key in config:
        if key not in result:
            result[key] = deepcopy(config[key])

    _validate(result)
    return result


def _validate(config: dict) -> None:
    """Validate config values."""
    if config['manuscript_type'] not in VALID_MANUSCRIPT_TYPES:
        print(
            f"Unknown manuscript_type: {config['manuscript_type']}. "
            f'Valid: {VALID_MANUSCRIPT_TYPES}',
            file=sys.stderr,
        )
        sys.exit(1)

    for lens in config['lenses']:
        if lens['name'] not in VALID_LENSES:
            print(f"Unknown lens: {lens['name']}. Valid: {VALID_LENSES}", file=sys.stderr)
            sys.exit(1)
        if lens.get('cli', 'codex') not in VALID_CLIS:
            print(f"Unknown CLI for lens {lens['name']}: {lens['cli']}. Valid: {VALID_CLIS}", file=sys.stderr)
            sys.exit(1)
        if lens.get('scope', 'chunk') not in VALID_SCOPES:
            print(f"Unknown scope for lens {lens['name']}: {lens['scope']}. Valid: {VALID_SCOPES}", file=sys.stderr)
            sys.exit(1)


def get_enabled_lenses(config: dict, filter_names: list[str] | None = None) -> list[dict]:
    """Get enabled lenses, unless the caller explicitly requests a lens subset."""
    if filter_names:
        return [l for l in config['lenses'] if l['name'] in filter_names]
    return [l for l in config['lenses'] if l.get('enabled', True)]


def override_cli(config: dict, cli: str) -> dict:
    """Override the CLI for all lenses."""
    for lens in config['lenses']:
        lens['cli'] = cli
    return config


def set_manuscript_type(config: dict, manuscript_type: str) -> dict:
    """Apply a built-in manuscript profile to the current lens configuration."""
    config['manuscript_type'] = manuscript_type
    enabled_by_lens = MANUSCRIPT_LENS_DEFAULTS[manuscript_type]
    for lens in config['lenses']:
        if lens['name'] in enabled_by_lens:
            lens['enabled'] = enabled_by_lens[lens['name']]
    return config
