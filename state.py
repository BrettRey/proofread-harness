"""Resumability via JSON state file."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def compute_file_hash(filepath: Path) -> str:
    """SHA-256 hash of a file's contents."""
    content = filepath.read_bytes()
    return hashlib.sha256(content).hexdigest()[:16]


def load_state(state_path: Path) -> dict:
    """Load state from JSON file, or return empty state."""
    if state_path.exists():
        with open(state_path) as f:
            return json.load(f)
    return {}


def save_state(state_path: Path, state: dict) -> None:
    """Save state to JSON file."""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with open(state_path, 'w') as f:
        json.dump(state, f, indent=2)


def init_state(input_file: Path, config: dict) -> dict:
    """Initialize a new state dict."""
    return {
        'input_file': str(input_file),
        'input_hash': compute_file_hash(input_file),
        'started': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'completed': {},
        'linter_done': False,
        'coherence_done': False,
    }


def is_task_done(state: dict, chunk_id: str, lens_name: str) -> bool:
    """Check if a chunk-lens pair has been completed."""
    key = f"{chunk_id}|{lens_name}"
    return state.get('completed', {}).get(key, {}).get('status') == 'done'


def mark_task_done(state: dict, chunk_id: str, lens_name: str, n_findings: int, raw_file: str = '') -> None:
    """Mark a chunk-lens pair as completed."""
    key = f"{chunk_id}|{lens_name}"
    if 'completed' not in state:
        state['completed'] = {}
    state['completed'][key] = {
        'status': 'done',
        'findings': n_findings,
        'file': raw_file,
        'timestamp': datetime.now(timezone.utc).isoformat(timespec='seconds'),
    }


def check_file_changed(state: dict, input_file: Path) -> bool:
    """Check if the input file has changed since the state was created."""
    current_hash = compute_file_hash(input_file)
    return current_hash != state.get('input_hash', '')
