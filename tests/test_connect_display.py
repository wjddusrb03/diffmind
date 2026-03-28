"""Tests for AI review display formatting."""

from __future__ import annotations

import json

import pytest

from diffmind.models import ReviewComment, ReviewReport
from diffmind.display import display_ai_review, display_ai_review_json


def _make_report(**kwargs):
    defaults = dict(
        comments=[
            ReviewComment(
                file_path="src/auth.py", line_range="L42-L58",
                risk_level="HIGH", summary="Null check removed",
                explanation="The null check protected against NoneType.",
                suggestion="Add null check back.",
                suggested_code="if user is None:\n    raise ValueError",
                past_bug_reference="abc1234 - fix: null check (PR #42)",
                confidence=0.95,
            ),
        ],
        overall_risk="HIGH",
        summary="One high risk pattern.",
        provider="claude",
        model_used="claude-sonnet-4-20250514",
        total_warnings_analyzed=1,
        false_positives=0,
    )
    defaults.update(kwargs)
    return ReviewReport(**defaults)


class TestDisplayAIReview:
    def test_basic_output(self):
        report = _make_report()
        output = display_ai_review(report)
        assert "AI Review Report" in output
        assert "HIGH" in output
        assert "src/auth.py" in output

    def test_empty_report(self):
        report = _make_report(
            comments=[], overall_risk="CLEAN",
            total_warnings_analyzed=0,
        )
        output = display_ai_review(report)
        assert "No warnings" in output

    def test_includes_explanation(self):
        report = _make_report()
        output = display_ai_review(report)
        assert "NoneType" in output

    def test_includes_suggestion(self):
        report = _make_report()
        output = display_ai_review(report)
        assert "Add null check" in output

    def test_includes_suggested_code(self):
        report = _make_report()
        output = display_ai_review(report)
        assert "if user is None" in output

    def test_includes_provider(self):
        report = _make_report()
        output = display_ai_review(report)
        assert "claude" in output

    def test_includes_confidence(self):
        report = _make_report()
        output = display_ai_review(report)
        assert "95%" in output

    def test_includes_summary(self):
        report = _make_report()
        output = display_ai_review(report)
        assert "high risk pattern" in output

    def test_false_positive_mark(self):
        report = _make_report(
            comments=[
                ReviewComment(
                    file_path="a.py", line_range="", risk_level="FALSE_POSITIVE",
                    summary="safe", explanation="ok", suggestion="none",
                    suggested_code="", past_bug_reference="abc",
                    confidence=0.8,
                ),
            ],
            overall_risk="CLEAN",
            false_positives=1,
        )
        output = display_ai_review(report)
        assert "[OK]" in output

    def test_multiple_comments(self):
        comments = [
            ReviewComment(
                file_path=f"file{i}.py", line_range="",
                risk_level=["HIGH", "MEDIUM", "LOW"][i % 3],
                summary=f"issue{i}", explanation="e", suggestion="s",
                suggested_code="", past_bug_reference="ref",
                confidence=0.5,
            )
            for i in range(3)
        ]
        report = _make_report(comments=comments, total_warnings_analyzed=3)
        output = display_ai_review(report)
        assert "file0.py" in output
        assert "file1.py" in output
        assert "file2.py" in output


class TestDisplayAIReviewJSON:
    def test_valid_json(self):
        report = _make_report()
        output = display_ai_review_json(report)
        data = json.loads(output)
        assert data["overall_risk"] == "HIGH"
        assert len(data["comments"]) == 1

    def test_json_structure(self):
        report = _make_report()
        data = json.loads(display_ai_review_json(report))
        assert "provider" in data
        assert "model" in data
        assert "summary" in data
        assert "comments" in data
        comment = data["comments"][0]
        assert "file" in comment
        assert "risk_level" in comment
        assert "confidence" in comment

    def test_empty_json(self):
        report = _make_report(comments=[], overall_risk="CLEAN")
        data = json.loads(display_ai_review_json(report))
        assert data["overall_risk"] == "CLEAN"
        assert len(data["comments"]) == 0

    def test_json_unicode(self):
        report = _make_report(summary="한국어 요약 테스트")
        output = display_ai_review_json(report)
        assert "한국어" in output
