"""Data classes for the proofreading harness."""

from dataclasses import dataclass, field
import hashlib


@dataclass
class Chunk:
    id: str
    content: str
    start_line: int
    end_line: int
    section_path: str
    context_before: str = ""
    context_after: str = ""

    @property
    def line_count(self):
        return self.end_line - self.start_line + 1


@dataclass
class Finding:
    line: int
    category: str  # style | grammar | quality | latex | grounding
    severity: str  # critical | major | minor
    lens: str
    current_text: str
    suggested_fix: str
    explanation: str
    chunk_id: str = ""

    @property
    def content_hash(self) -> str:
        normalized = f"{self.current_text[:100].lower().strip()}|{self.category}|{self.line // 5}"
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]


@dataclass
class LensResult:
    lens_name: str
    chunk_id: str
    cli_used: str
    raw_output: str
    findings: list[Finding] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    success: bool = True
    error: str | None = None
