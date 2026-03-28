"""Tests for DiffMind Connect prompt templates."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from diffmind.models import DiffHunk, ReviewWarning, ReviewComment
from diffmind.connect.prompts import (
    build_review_prompt,
    build_summary_prompt,
    format_diff,
)


NOW = datetime(2025, 6, 1, tzinfo=timezone.utc)


def _make_hunk(**kwargs):
    defaults = dict(
        commit_hash="abc1234",
        file_path="src/auth.py",
        language="python",
        old_code="old = 1",
        new_code="new = 2",
        context="context here",
        commit_message="fix: null check",
        author="Alice",
        timestamp=NOW,
        is_bugfix=True,
    )
    defaults.update(kwargs)
    return DiffHunk(**defaults)


def _make_warning(current_kwargs=None, past_kwargs=None, **extra):
    ck = current_kwargs or {}
    pk = past_kwargs or {"commit_hash": "def5678", "is_bugfix": True}
    current = _make_hunk(**ck)
    past = _make_hunk(**pk)
    return ReviewWarning(
        current_hunk=current,
        similar_hunk=past,
        similarity=extra.get("similarity", 0.92),
        risk_level=extra.get("risk_level", "HIGH"),
        reason="test reason",
    )


class TestFormatDiff:
    def test_basic(self):
        result = format_diff("old line", "new line")
        assert "- old line" in result
        assert "+ new line" in result

    def test_empty(self):
        result = format_diff("", "")
        assert result == "(no code changes)"

    def test_multiline(self):
        old = "a\nb\nc"
        new = "x\ny\nz"
        result = format_diff(old, new)
        assert "- a" in result
        assert "+ z" in result

    def test_max_lines(self):
        old = "\n".join(f"old{i}" for i in range(50))
        result = format_diff(old, "", max_lines=5)
        lines = [l for l in result.split("\n") if l.startswith("-")]
        assert len(lines) <= 5

    def test_whitespace_only_skipped(self):
        result = format_diff("  \n  ", "  \n  ")
        assert result == "(no code changes)"


class TestBuildReviewPrompt:
    def test_returns_tuple(self):
        w = _make_warning()
        system, user = build_review_prompt(w)
        assert isinstance(system, str)
        assert isinstance(user, str)

    def test_english_prompt_content(self):
        w = _make_warning()
        system, user = build_review_prompt(w, language="en")
        assert "senior code reviewer" in system
        assert "src/auth.py" in user
        assert "92%" in user

    def test_korean_prompt_content(self):
        w = _make_warning()
        system, user = build_review_prompt(w, language="ko")
        assert "시니어" in system
        assert "src/auth.py" in user

    def test_pr_number_included(self):
        w = _make_warning(
            past_kwargs={"commit_hash": "def5678", "pr_number": 42, "is_bugfix": True}
        )
        _, user = build_review_prompt(w)
        assert "#42" in user

    def test_no_pr_number(self):
        w = _make_warning()
        _, user = build_review_prompt(w)
        assert "PR:" not in user or "PR: #" not in user

    def test_json_format_requested(self):
        w = _make_warning()
        _, user = build_review_prompt(w)
        assert "risk_level" in user
        assert "suggested_code" in user

    def test_different_languages(self):
        w = _make_warning(
            current_kwargs={"language": "javascript", "file_path": "app.js"}
        )
        _, user = build_review_prompt(w)
        assert "app.js" in user

    def test_long_code_included(self):
        long_code = "x = 1\n" * 20
        w = _make_warning(current_kwargs={"new_code": long_code})
        _, user = build_review_prompt(w)
        assert "x = 1" in user


class TestBuildSummaryPrompt:
    def test_empty_comments(self):
        result = build_summary_prompt([])
        assert "0" in result

    def test_with_comments(self):
        comments = [
            ReviewComment(
                file_path="a.py", line_range="", risk_level="HIGH",
                summary="null check missing", explanation="", suggestion="",
                suggested_code="", past_bug_reference="abc", confidence=0.9,
            ),
            ReviewComment(
                file_path="b.py", line_range="", risk_level="FALSE_POSITIVE",
                summary="safe change", explanation="", suggestion="",
                suggested_code="", past_bug_reference="def", confidence=0.8,
            ),
        ]
        result = build_summary_prompt(comments)
        assert "2" in result  # count
        assert "1" in result  # false positives
        assert "HIGH" in result

    def test_korean_summary(self):
        comments = [
            ReviewComment(
                file_path="a.py", line_range="", risk_level="MEDIUM",
                summary="test", explanation="", suggestion="",
                suggested_code="", past_bug_reference="abc", confidence=0.5,
            ),
        ]
        result = build_summary_prompt(comments, language="ko")
        assert "분석된 경고" in result
