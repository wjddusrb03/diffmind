"""Core data models for DiffMind."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class DiffHunk:
    """A single code change unit extracted from a git diff."""

    commit_hash: str
    file_path: str
    language: str
    old_code: str
    new_code: str
    context: str
    commit_message: str
    author: str
    timestamp: datetime
    is_bugfix: bool
    hunk_header: str = ""
    pr_number: Optional[int] = None
    labels: List[str] = field(default_factory=list)

    def to_embedding_text(self) -> str:
        """Generate text for embedding."""
        parts = [f"[{self.language}] {self.file_path}"]
        if self.old_code.strip():
            parts.append(f"Removed:\n{self.old_code}")
        if self.new_code.strip():
            parts.append(f"Added:\n{self.new_code}")
        if self.context.strip():
            parts.append(f"Context:\n{self.context}")
        parts.append(f"Message: {self.commit_message}")
        return "\n".join(parts)

    def short_hash(self) -> str:
        return self.commit_hash[:7]

    def time_str(self) -> str:
        return self.timestamp.strftime("%Y-%m-%d")


@dataclass
class ReviewWarning:
    """A warning produced by comparing current diff against past bugs."""

    current_hunk: DiffHunk
    similar_hunk: DiffHunk
    similarity: float
    risk_level: str  # "HIGH", "MEDIUM", "LOW"
    reason: str

    @property
    def risk_emoji(self) -> str:
        return {"HIGH": "\U0001f534", "MEDIUM": "\U0001f7e1", "LOW": "\U0001f7e2"}.get(
            self.risk_level, ""
        )


@dataclass
class DiffMindIndex:
    """The learned index containing compressed embeddings of past diffs."""

    hunks: List[DiffHunk]
    compressed: object  # CompressedVectors from TurboQuant
    quantizer: object  # TurboQuantizer
    model_name: str
    embedding_dim: int
    total_commits: int
    bugfix_commits: int
    files_tracked: int
    languages: List[str]
    raw_memory_bytes: int
    compressed_memory_bytes: int
    learn_time: float
    last_learned_commit: str = ""
