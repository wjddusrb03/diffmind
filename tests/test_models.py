"""Tests for DiffMind data models."""

from datetime import datetime

from diffmind.models import DiffHunk, DiffMindIndex, ReviewWarning


def _make_hunk(**kwargs):
    defaults = dict(
        commit_hash="abc1234567890",
        file_path="src/main.py",
        language="python",
        old_code="x = None",
        new_code="x = get_value()",
        context="def foo():\n    return x",
        commit_message="fix: null check",
        author="Alice",
        timestamp=datetime(2024, 3, 15, 10, 30),
        is_bugfix=True,
    )
    defaults.update(kwargs)
    return DiffHunk(**defaults)


class TestDiffHunk:
    def test_creation(self):
        h = _make_hunk()
        assert h.commit_hash == "abc1234567890"
        assert h.file_path == "src/main.py"
        assert h.language == "python"
        assert h.is_bugfix is True

    def test_to_embedding_text(self):
        h = _make_hunk()
        text = h.to_embedding_text()
        assert "[python]" in text
        assert "src/main.py" in text
        assert "Removed:" in text
        assert "Added:" in text
        assert "fix: null check" in text

    def test_embedding_text_no_old_code(self):
        h = _make_hunk(old_code="", new_code="import os")
        text = h.to_embedding_text()
        assert "Removed:" not in text
        assert "Added:" in text

    def test_short_hash(self):
        h = _make_hunk()
        assert h.short_hash() == "abc1234"

    def test_time_str(self):
        h = _make_hunk()
        assert h.time_str() == "2024-03-15"

    def test_default_fields(self):
        h = _make_hunk()
        assert h.pr_number is None
        assert h.labels == []
        assert h.hunk_header == ""

    def test_with_pr_number(self):
        h = _make_hunk(pr_number=42)
        assert h.pr_number == 42


class TestReviewWarning:
    def test_risk_emoji_high(self):
        w = ReviewWarning(
            current_hunk=_make_hunk(),
            similar_hunk=_make_hunk(),
            similarity=0.95,
            risk_level="HIGH",
            reason="test",
        )
        assert "HIGH" in w.risk_level

    def test_risk_emoji_medium(self):
        w = ReviewWarning(
            current_hunk=_make_hunk(),
            similar_hunk=_make_hunk(),
            similarity=0.85,
            risk_level="MEDIUM",
            reason="test",
        )
        assert w.risk_level == "MEDIUM"

    def test_risk_emoji_low(self):
        w = ReviewWarning(
            current_hunk=_make_hunk(),
            similar_hunk=_make_hunk(),
            similarity=0.76,
            risk_level="LOW",
            reason="test",
        )
        assert w.risk_level == "LOW"


class TestDiffMindIndex:
    def test_creation(self):
        idx = DiffMindIndex(
            hunks=[],
            compressed=None,
            quantizer=None,
            model_name="test-model",
            embedding_dim=384,
            total_commits=100,
            bugfix_commits=30,
            files_tracked=50,
            languages=["python", "javascript"],
            raw_memory_bytes=10000,
            compressed_memory_bytes=5000,
            learn_time=2.5,
        )
        assert idx.total_commits == 100
        assert idx.bugfix_commits == 30
        assert idx.last_learned_commit == ""
