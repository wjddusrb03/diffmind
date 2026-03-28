"""Tests for DiffMind Connect Slack and Discord notifications."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from diffmind.models import ReviewComment, ReviewReport
from diffmind.connect.slack import SlackNotifier
from diffmind.connect.discord import DiscordNotifier
from diffmind.connect.config import SlackConfig, DiscordConfig


def _make_report(overall_risk="HIGH", **kwargs):
    defaults = dict(
        comments=[
            ReviewComment(
                file_path="src/auth.py", line_range="L42",
                risk_level="HIGH", summary="Null check removed",
                explanation="dangerous", suggestion="add check",
                suggested_code="if x:", past_bug_reference="abc",
                confidence=0.9,
            ),
        ],
        summary="One issue found.",
        provider="claude",
        model_used="test-model",
        total_warnings_analyzed=1,
        false_positives=0,
    )
    defaults.update(kwargs)
    return ReviewReport(overall_risk=overall_risk, **defaults)


# ── Slack Tests ──────────────────────────────────────────────────

class TestSlackNotifier:
    def test_init_with_url(self):
        n = SlackNotifier(webhook_url="https://hooks.slack.com/test")
        assert n.webhook_url == "https://hooks.slack.com/test"

    def test_init_from_config(self):
        cfg = SlackConfig(
            webhook_url="https://hooks.slack.com/cfg",
            channel="#reviews",
            min_risk="HIGH",
        )
        n = SlackNotifier(config=cfg)
        assert n.channel == "#reviews"
        assert n.min_risk == "HIGH"

    def test_missing_url_raises(self):
        with pytest.raises(ValueError, match="webhook"):
            SlackNotifier(webhook_url="")

    def test_should_notify_high(self):
        n = SlackNotifier(webhook_url="http://test", min_risk="HIGH")
        assert n._should_notify("HIGH") is True
        assert n._should_notify("MEDIUM") is False
        assert n._should_notify("LOW") is False

    def test_should_notify_medium(self):
        n = SlackNotifier(webhook_url="http://test", min_risk="MEDIUM")
        assert n._should_notify("HIGH") is True
        assert n._should_notify("MEDIUM") is True
        assert n._should_notify("LOW") is False

    def test_should_notify_low(self):
        n = SlackNotifier(webhook_url="http://test", min_risk="LOW")
        assert n._should_notify("HIGH") is True
        assert n._should_notify("LOW") is True

    def test_should_notify_clean(self):
        n = SlackNotifier(webhook_url="http://test", min_risk="HIGH")
        assert n._should_notify("CLEAN") is False

    def test_send_skips_below_threshold(self):
        n = SlackNotifier(webhook_url="http://test", min_risk="HIGH")
        report = _make_report(overall_risk="LOW")
        result = n.send_alert(report)
        assert result is False  # Skipped, not sent

    def test_build_payload_structure(self):
        n = SlackNotifier(webhook_url="http://test", channel="#review")
        report = _make_report()
        payload = n._build_payload(report, "https://pr", "fix login", "Alice")

        assert "blocks" in payload
        assert payload["channel"] == "#review"
        # Should have header block
        assert any(b["type"] == "header" for b in payload["blocks"])

    def test_build_payload_with_pr_info(self):
        n = SlackNotifier(webhook_url="http://test")
        report = _make_report()
        payload = n._build_payload(report, "https://github.com/pr/1", "PR Title", "Bob")

        blocks_text = json.dumps(payload)
        assert "PR Title" in blocks_text
        assert "Bob" in blocks_text

    def test_build_payload_no_pr(self):
        n = SlackNotifier(webhook_url="http://test")
        report = _make_report()
        payload = n._build_payload(report, "", "", "")
        assert "blocks" in payload

    def test_build_payload_limits_comments(self):
        comments = [
            ReviewComment(
                file_path=f"file{i}.py", line_range="", risk_level="HIGH",
                summary=f"issue {i}", explanation="", suggestion="",
                suggested_code="", past_bug_reference="", confidence=0.9,
            )
            for i in range(10)
        ]
        n = SlackNotifier(webhook_url="http://test")
        report = _make_report(comments=comments)
        payload = n._build_payload(report, "", "", "")
        # Should limit to 5 comments max
        blocks_text = json.dumps(payload)
        # Count file mentions (max 5 shown in detail section)
        shown_count = sum(1 for i in range(10) if f"file{i}.py" in blocks_text)
        assert shown_count <= 6  # 5 in detail + possible summary mention


# ── Discord Tests ────────────────────────────────────────────────

class TestDiscordNotifier:
    def test_init_with_url(self):
        n = DiscordNotifier(webhook_url="https://discord.com/api/webhooks/test")
        assert "discord" in n.webhook_url

    def test_init_from_config(self):
        cfg = DiscordConfig(
            webhook_url="https://discord.com/api/webhooks/cfg",
            min_risk="MEDIUM",
            mention_role="123456",
        )
        n = DiscordNotifier(config=cfg)
        assert n.min_risk == "MEDIUM"
        assert n.mention_role == "123456"

    def test_missing_url_raises(self):
        with pytest.raises(ValueError, match="webhook"):
            DiscordNotifier(webhook_url="")

    def test_should_notify_high(self):
        n = DiscordNotifier(webhook_url="http://test", min_risk="HIGH")
        assert n._should_notify("HIGH") is True
        assert n._should_notify("MEDIUM") is False

    def test_should_notify_medium(self):
        n = DiscordNotifier(webhook_url="http://test", min_risk="MEDIUM")
        assert n._should_notify("HIGH") is True
        assert n._should_notify("MEDIUM") is True

    def test_send_skips_below_threshold(self):
        n = DiscordNotifier(webhook_url="http://test", min_risk="HIGH")
        report = _make_report(overall_risk="LOW")
        result = n.send_alert(report)
        assert result is False

    def test_build_payload_structure(self):
        n = DiscordNotifier(webhook_url="http://test")
        report = _make_report()
        payload = n._build_payload(report, "https://pr", "fix login", "Alice")

        assert "embeds" in payload
        assert len(payload["embeds"]) == 1
        embed = payload["embeds"][0]
        assert "title" in embed
        assert "color" in embed
        assert "fields" in embed

    def test_build_payload_color_high(self):
        n = DiscordNotifier(webhook_url="http://test")
        report = _make_report(overall_risk="HIGH")
        payload = n._build_payload(report, "", "", "")
        assert payload["embeds"][0]["color"] == 0xFF0000  # Red

    def test_build_payload_color_medium(self):
        n = DiscordNotifier(webhook_url="http://test")
        report = _make_report(overall_risk="MEDIUM")
        payload = n._build_payload(report, "", "", "")
        assert payload["embeds"][0]["color"] == 0xFFAA00  # Orange

    def test_build_payload_mention_role(self):
        n = DiscordNotifier(webhook_url="http://test", mention_role="789")
        report = _make_report(overall_risk="HIGH")
        payload = n._build_payload(report, "", "", "")
        assert "<@&789>" in payload["content"]

    def test_build_payload_no_mention_low_risk(self):
        n = DiscordNotifier(webhook_url="http://test", min_risk="LOW", mention_role="789")
        report = _make_report(overall_risk="LOW")
        payload = n._build_payload(report, "", "", "")
        # mention_role only triggers for HIGH risk
        assert "<@&789>" not in payload.get("content", "")

    def test_build_payload_pr_info(self):
        n = DiscordNotifier(webhook_url="http://test")
        report = _make_report()
        payload = n._build_payload(report, "https://github.com/pr", "Title", "Dev")
        desc = payload["embeds"][0]["description"]
        assert "Title" in desc
        assert "Dev" in desc

    def test_build_payload_limits_fields(self):
        comments = [
            ReviewComment(
                file_path=f"f{i}.py", line_range="", risk_level="MEDIUM",
                summary=f"s{i}", explanation="", suggestion="",
                suggested_code="", past_bug_reference="", confidence=0.5,
            )
            for i in range(10)
        ]
        n = DiscordNotifier(webhook_url="http://test")
        report = _make_report(overall_risk="MEDIUM", comments=comments)
        payload = n._build_payload(report, "", "", "")
        assert len(payload["embeds"][0]["fields"]) <= 5
