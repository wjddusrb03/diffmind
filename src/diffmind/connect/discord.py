"""Discord notification integration for DiffMind."""

from __future__ import annotations

import json
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from ..models import ReviewReport
from .config import DiscordConfig


class DiscordNotifier:
    """Send DiffMind review alerts to Discord channels via webhook.

    Usage:
        notifier = DiscordNotifier(webhook_url="https://discord.com/api/webhooks/...")
        notifier.send_alert(report, pr_url="https://github.com/...")
    """

    def __init__(
        self,
        webhook_url: str = "",
        min_risk: str = "HIGH",
        mention_role: str = "",
        config: Optional[DiscordConfig] = None,
    ):
        if config:
            self.webhook_url = config.webhook_url
            self.min_risk = config.min_risk.upper()
            self.mention_role = config.mention_role
        else:
            self.webhook_url = webhook_url
            self.min_risk = min_risk.upper()
            self.mention_role = mention_role

        if not self.webhook_url:
            raise ValueError("Discord webhook URL is required.")

    def _should_notify(self, risk: str) -> bool:
        """Check if the risk level meets the minimum threshold."""
        order = {"HIGH": 3, "MEDIUM": 2, "LOW": 1, "CLEAN": 0}
        return order.get(risk.upper(), 0) >= order.get(self.min_risk, 3)

    def send_alert(
        self,
        report: ReviewReport,
        pr_url: str = "",
        pr_title: str = "",
        author: str = "",
    ) -> bool:
        """Send a review alert to Discord.

        Args:
            report: The AI-generated ReviewReport.
            pr_url: Optional link to the PR.
            pr_title: Optional PR title.
            author: Optional PR author.

        Returns:
            True if message was sent, False if skipped or failed.
        """
        if not self._should_notify(report.overall_risk):
            return False

        payload = self._build_payload(report, pr_url, pr_title, author)
        data = json.dumps(payload).encode()

        req = Request(self.webhook_url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")

        try:
            with urlopen(req) as resp:
                # Discord returns 204 No Content on success
                return resp.status in (200, 204)
        except HTTPError:
            return False

    def _build_payload(
        self,
        report: ReviewReport,
        pr_url: str,
        pr_title: str,
        author: str,
    ) -> dict:
        """Build Discord embed message payload."""
        color_map = {
            "HIGH": 0xFF0000,     # Red
            "MEDIUM": 0xFFAA00,   # Orange
            "LOW": 0x00CC00,      # Green
            "CLEAN": 0x00CC00,
        }

        risk_emoji = {
            "HIGH": "\U0001f534",
            "MEDIUM": "\U0001f7e1",
            "LOW": "\U0001f7e2",
        }

        emoji = risk_emoji.get(report.overall_risk, "\u26a0\ufe0f")
        title = f"{emoji} DiffMind: {report.overall_risk} Risk Detected"

        # Build fields from comments
        fields = []
        real_comments = [
            c for c in report.comments if c.risk_level != "FALSE_POSITIVE"
        ]
        for c in real_comments[:5]:
            c_emoji = risk_emoji.get(c.risk_level, "")
            fields.append({
                "name": f"{c_emoji} {c.risk_level}: {c.file_path}",
                "value": c.summary[:200],
                "inline": False,
            })

        # PR info
        description_parts = []
        if pr_title:
            description_parts.append(f"**PR**: {pr_title}")
        if author:
            description_parts.append(f"**Author**: {author}")
        if pr_url:
            description_parts.append(f"**Link**: [View PR]({pr_url})")

        description_parts.append(
            f"\n**Warnings**: {report.total_warnings_analyzed} | "
            f"**False Positives**: {report.false_positives}"
        )

        embed = {
            "title": title,
            "description": "\n".join(description_parts),
            "color": color_map.get(report.overall_risk, 0xFFAA00),
            "fields": fields,
            "footer": {
                "text": (
                    f"DiffMind + {report.provider} | {report.summary[:100]}"
                ),
            },
        }

        content = ""
        if self.mention_role and report.overall_risk == "HIGH":
            content = f"<@&{self.mention_role}> "

        return {
            "content": content,
            "embeds": [embed],
        }

    def send_test(self) -> bool:
        """Send a test message to verify webhook configuration."""
        payload = {
            "content": (
                "\u2705 DiffMind Discord integration is working! "
                "You will receive alerts when risky code patterns are detected."
            ),
        }
        data = json.dumps(payload).encode()
        req = Request(self.webhook_url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")

        try:
            with urlopen(req) as resp:
                return resp.status in (200, 204)
        except HTTPError:
            return False
