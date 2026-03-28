"""Slack notification integration for DiffMind."""

from __future__ import annotations

import json
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from ..models import ReviewReport
from .config import SlackConfig


class SlackNotifier:
    """Send DiffMind review alerts to Slack channels via webhook.

    Usage:
        notifier = SlackNotifier(webhook_url="https://hooks.slack.com/services/...")
        notifier.send_alert(report, pr_url="https://github.com/...")
    """

    def __init__(
        self,
        webhook_url: str = "",
        channel: str = "",
        min_risk: str = "MEDIUM",
        config: Optional[SlackConfig] = None,
    ):
        if config:
            self.webhook_url = config.webhook_url
            self.channel = config.channel
            self.min_risk = config.min_risk.upper()
        else:
            self.webhook_url = webhook_url
            self.channel = channel
            self.min_risk = min_risk.upper()

        if not self.webhook_url:
            raise ValueError("Slack webhook URL is required.")

    def _should_notify(self, risk: str) -> bool:
        """Check if the risk level meets the minimum threshold."""
        order = {"HIGH": 3, "MEDIUM": 2, "LOW": 1, "CLEAN": 0}
        return order.get(risk.upper(), 0) >= order.get(self.min_risk, 2)

    def send_alert(
        self,
        report: ReviewReport,
        pr_url: str = "",
        pr_title: str = "",
        author: str = "",
    ) -> bool:
        """Send a review alert to Slack.

        Args:
            report: The AI-generated ReviewReport.
            pr_url: Optional link to the PR.
            pr_title: Optional PR title.
            author: Optional PR author.

        Returns:
            True if message was sent, False if skipped (below threshold).
        """
        if not self._should_notify(report.overall_risk):
            return False

        payload = self._build_payload(report, pr_url, pr_title, author)
        data = json.dumps(payload).encode()

        req = Request(self.webhook_url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")

        try:
            with urlopen(req) as resp:
                return resp.status == 200
        except HTTPError:
            return False

    def _build_payload(
        self,
        report: ReviewReport,
        pr_url: str,
        pr_title: str,
        author: str,
    ) -> dict:
        """Build Slack Block Kit message payload."""
        risk_emoji = {
            "HIGH": ":red_circle:",
            "MEDIUM": ":large_yellow_circle:",
            "LOW": ":large_green_circle:",
            "CLEAN": ":white_check_mark:",
        }

        emoji = risk_emoji.get(report.overall_risk, ":warning:")
        title = f"{emoji} DiffMind: {report.overall_risk} Risk Detected"

        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": title},
            },
        ]

        # PR info section
        if pr_url or pr_title:
            pr_text = ""
            if pr_title:
                pr_text += f"*PR*: {pr_title}\n"
            if author:
                pr_text += f"*Author*: {author}\n"
            if pr_url:
                pr_text += f"*Link*: <{pr_url}|View PR>\n"

            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": pr_text.strip()},
            })

        # Warning details
        real_comments = [
            c for c in report.comments if c.risk_level != "FALSE_POSITIVE"
        ]
        if real_comments:
            details = []
            for c in real_comments[:5]:  # Max 5 to avoid overflow
                r_emoji = risk_emoji.get(c.risk_level, "")
                details.append(
                    f"{r_emoji} *{c.risk_level}*: `{c.file_path}`\n"
                    f"  {c.summary}"
                )

            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "\n\n".join(details),
                },
            })

        # Summary
        blocks.append({"type": "divider"})
        summary_text = (
            f"*Summary*: {report.summary}\n"
            f"Warnings: {report.total_warnings_analyzed} | "
            f"False positives: {report.false_positives}\n"
            f"_Analyzed by DiffMind + {report.provider}_"
        )
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": summary_text},
        })

        payload = {"blocks": blocks}
        if self.channel:
            payload["channel"] = self.channel

        return payload

    def send_test(self) -> bool:
        """Send a test message to verify webhook configuration."""
        payload = {
            "text": (
                ":white_check_mark: DiffMind Slack integration is working! "
                "You will receive alerts when risky code patterns are detected."
            ),
        }
        if self.channel:
            payload["channel"] = self.channel

        data = json.dumps(payload).encode()
        req = Request(self.webhook_url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")

        try:
            with urlopen(req) as resp:
                return resp.status == 200
        except HTTPError:
            return False
