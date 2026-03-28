"""Tests for DiffMind reviewer."""

from datetime import datetime

from diffmind.reviewer import classify_risk, generate_reason
from diffmind.models import DiffHunk


def _make_hunk(is_bugfix=True, **kwargs):
    defaults = dict(
        commit_hash="abc1234567890",
        file_path="src/main.py",
        language="python",
        old_code="x = None",
        new_code="x = get_value()",
        context="def foo():",
        commit_message="fix: null check",
        author="Alice",
        timestamp=datetime(2024, 3, 15),
        is_bugfix=is_bugfix,
    )
    defaults.update(kwargs)
    return DiffHunk(**defaults)


class TestClassifyRisk:
    def test_high_bugfix_90(self):
        h = _make_hunk(is_bugfix=True)
        assert classify_risk(0.95, h) == "HIGH"

    def test_high_bugfix_exact_90(self):
        h = _make_hunk(is_bugfix=True)
        assert classify_risk(0.90, h) == "HIGH"

    def test_medium_bugfix_85(self):
        h = _make_hunk(is_bugfix=True)
        assert classify_risk(0.85, h) == "MEDIUM"

    def test_medium_bugfix_80(self):
        h = _make_hunk(is_bugfix=True)
        assert classify_risk(0.80, h) == "MEDIUM"

    def test_low_non_bugfix_85(self):
        h = _make_hunk(is_bugfix=False)
        assert classify_risk(0.85, h) == "LOW"

    def test_low_bugfix_75(self):
        h = _make_hunk(is_bugfix=True)
        assert classify_risk(0.75, h) == "LOW"

    def test_low_non_bugfix_70(self):
        h = _make_hunk(is_bugfix=False)
        assert classify_risk(0.70, h) == "LOW"


class TestGenerateReason:
    def test_bugfix_reason(self):
        current = _make_hunk()
        past = _make_hunk(author="Bob", commit_message="fix: crash on login")
        reason = generate_reason(current, past, 0.92)
        assert "92%" in reason
        assert "Bob" in reason
        assert "fix: crash on login" in reason

    def test_non_bugfix_reason(self):
        current = _make_hunk()
        past = _make_hunk(is_bugfix=False, commit_message="refactor: extract method")
        reason = generate_reason(current, past, 0.80)
        assert "Similar change" in reason
        assert "refactor: extract method" in reason

    def test_bugfix_with_pr(self):
        current = _make_hunk()
        past = _make_hunk(pr_number=42)
        reason = generate_reason(current, past, 0.90)
        assert "#42" in reason

    def test_reason_includes_file(self):
        current = _make_hunk()
        past = _make_hunk(file_path="src/auth/login.py")
        reason = generate_reason(current, past, 0.85)
        assert "src/auth/login.py" in reason
