"""Tests for DiffMind Connect GitHub bot."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from diffmind.models import ReviewComment, ReviewReport
from diffmind.connect.github_bot import GitHubBot
from diffmind.connect.config import GitHubConfig


def _make_report(**kwargs):
    defaults = dict(
        comments=[
            ReviewComment(
                file_path="src/auth.py",
                line_range="L42-L58",
                risk_level="HIGH",
                summary="Null check removed",
                explanation="The null check was protecting against NoneType error",
                suggestion="Add back the null check",
                suggested_code="if user is None:\n    raise ValueError",
                past_bug_reference="abc1234 - fix: null check (PR #42)",
                confidence=0.95,
            ),
            ReviewComment(
                file_path="src/api.py",
                line_range="L10-L15",
                risk_level="FALSE_POSITIVE",
                summary="Safe change",
                explanation="Coincidental similarity",
                suggestion="No action needed",
                suggested_code="",
                past_bug_reference="def5678 - fix: timeout",
                confidence=0.8,
            ),
        ],
        overall_risk="HIGH",
        summary="One high risk pattern found.",
        provider="claude",
        model_used="claude-sonnet-4-20250514",
        total_warnings_analyzed=2,
        false_positives=1,
    )
    defaults.update(kwargs)
    return ReviewReport(**defaults)


class TestGitHubBotInit:
    def test_init_with_token_and_repo(self):
        bot = GitHubBot(token="ghp-test", repo="owner/repo")
        assert bot.token == "ghp-test"
        assert bot.repo == "owner/repo"

    def test_init_from_env(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "ghp-env")
        bot = GitHubBot(repo="owner/repo")
        assert bot.token == "ghp-env"

    def test_init_from_config(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "ghp-cfg")
        cfg = GitHubConfig(repo="org/project")
        bot = GitHubBot(config=cfg)
        assert bot.repo == "org/project"

    def test_missing_token_raises(self, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        with pytest.raises(ValueError, match="token"):
            GitHubBot(repo="owner/repo")

    def test_missing_repo_raises(self):
        with pytest.raises(ValueError, match="repo"):
            GitHubBot(token="ghp-test")


class TestReviewBodyFormatting:
    def test_format_review_body_basic(self):
        bot = GitHubBot(token="test", repo="a/b")
        report = _make_report()
        body = bot._format_review_body(report)

        assert "DiffMind AI Review" in body
        assert "HIGH" in body
        assert "src/auth.py" in body
        assert "Null check removed" in body

    def test_format_skips_false_positives_in_detail(self):
        bot = GitHubBot(token="test", repo="a/b")
        report = _make_report()
        body = bot._format_review_body(report)

        # FALSE_POSITIVE appears in table but not in detailed ### sections
        assert "Safe change" in body  # in table
        # The detailed section (### headings) should NOT have FALSE_POSITIVE
        lines = body.split("\n")
        detail_headings = [l for l in lines if l.startswith("### ")]
        false_pos_detail = [h for h in detail_headings if "FALSE_POSITIVE" in h]
        assert len(false_pos_detail) == 0

    def test_format_includes_suggestion_code(self):
        bot = GitHubBot(token="test", repo="a/b")
        report = _make_report()
        body = bot._format_review_body(report)
        assert "if user is None" in body
        assert "```suggestion" in body

    def test_format_clean_report(self):
        bot = GitHubBot(token="test", repo="a/b")
        report = _make_report(
            comments=[], overall_risk="CLEAN",
            summary="No issues.", total_warnings_analyzed=0, false_positives=0,
        )
        body = bot._format_review_body(report)
        assert "CLEAN" in body

    def test_format_includes_provider_info(self):
        bot = GitHubBot(token="test", repo="a/b")
        report = _make_report()
        body = bot._format_review_body(report)
        assert "claude" in body

    def test_format_includes_past_bug_reference(self):
        bot = GitHubBot(token="test", repo="a/b")
        report = _make_report()
        body = bot._format_review_body(report)
        assert "abc1234" in body
        assert "PR #42" in body


class TestCheckStatus:
    def test_check_status_format(self):
        bot = GitHubBot(token="test", repo="a/b")

        # Mock the API request
        bot._api_request = MagicMock(return_value={"url": "https://api.github.com/status"})

        report = _make_report(overall_risk="HIGH")
        bot.post_check_status("sha123", report, fail_on="HIGH")

        call_args = bot._api_request.call_args
        assert call_args[0][0] == "POST"
        body = call_args[0][2]
        assert body["state"] == "failure"
        assert "diffmind" in body["context"]

    def test_check_status_pass(self):
        bot = GitHubBot(token="test", repo="a/b")
        bot._api_request = MagicMock(return_value={"url": ""})

        report = _make_report(overall_risk="LOW")
        bot.post_check_status("sha123", report, fail_on="HIGH")

        body = bot._api_request.call_args[0][2]
        assert body["state"] == "success"
