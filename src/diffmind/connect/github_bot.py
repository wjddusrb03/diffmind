"""GitHub integration - post AI review comments on PRs."""

from __future__ import annotations

import json
import os
from typing import List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from ..models import ReviewComment, ReviewReport
from .config import GitHubConfig


class GitHubBot:
    """Post DiffMind AI review results as GitHub PR comments.

    Can work with or without PyGithub:
      - With PyGithub: full PR review with inline comments
      - Without PyGithub: simple PR comments via REST API

    Usage:
        bot = GitHubBot(token="ghp_...", repo="owner/repo")
        bot.post_review(pr_number=42, report=report)
    """

    def __init__(
        self,
        token: str = "",
        repo: str = "",
        config: Optional[GitHubConfig] = None,
    ):
        if config:
            self.token = config.resolve_token()
            self.repo = config.repo
            self.post_comments = config.post_comments
            self.add_labels = config.add_labels
        else:
            self.token = token or os.environ.get("GITHUB_TOKEN", "")
            self.repo = repo
            self.post_comments = True
            self.add_labels = True

        if not self.token:
            raise ValueError(
                "GitHub token required. Set GITHUB_TOKEN env var or pass token=."
            )
        if not self.repo:
            raise ValueError(
                "GitHub repo required (format: owner/repo). "
                "Set in config or pass repo=."
            )

    def _api_request(
        self, method: str, endpoint: str, body: dict = None
    ) -> dict:
        """Make a GitHub API request."""
        url = f"https://api.github.com/repos/{self.repo}/{endpoint}"
        data = json.dumps(body).encode() if body else None
        req = Request(url, data=data, method=method)
        req.add_header("Authorization", f"token {self.token}")
        req.add_header("Accept", "application/vnd.github.v3+json")
        if data:
            req.add_header("Content-Type", "application/json")

        try:
            with urlopen(req) as resp:
                return json.loads(resp.read().decode())
        except HTTPError as e:
            error_body = e.read().decode() if e.fp else ""
            raise RuntimeError(
                f"GitHub API error {e.code}: {error_body}"
            ) from e

    def post_review(
        self,
        pr_number: int,
        report: ReviewReport,
    ) -> str:
        """Post a review comment on a GitHub PR.

        Args:
            pr_number: The PR number to comment on.
            report: The AI-generated ReviewReport.

        Returns:
            URL of the posted comment.
        """
        body = self._format_review_body(report)

        result = self._api_request(
            "POST",
            f"issues/{pr_number}/comments",
            {"body": body},
        )

        # Add labels if configured
        if self.add_labels and report.overall_risk != "CLEAN":
            label = f"diffmind:{report.overall_risk.lower()}-risk"
            try:
                self._api_request(
                    "POST",
                    f"issues/{pr_number}/labels",
                    {"labels": [label]},
                )
            except RuntimeError:
                pass  # Label might not exist, that's ok

        return result.get("html_url", "")

    def _format_review_body(self, report: ReviewReport) -> str:
        """Format ReviewReport as a GitHub-flavored markdown comment."""
        risk_emoji = {
            "HIGH": "\U0001f534",
            "MEDIUM": "\U0001f7e1",
            "LOW": "\U0001f7e2",
            "CLEAN": "\u2705",
            "FALSE_POSITIVE": "\u2705",
        }

        lines = []
        lines.append(f"## \U0001f50d DiffMind AI Review")
        lines.append("")

        overall_emoji = risk_emoji.get(report.overall_risk, "")
        lines.append(
            f"**Overall Risk**: {overall_emoji} {report.overall_risk} "
            f"| **Warnings**: {report.total_warnings_analyzed} "
            f"| **False Positives**: {report.false_positives}"
        )
        lines.append("")

        if report.comments:
            # Summary table
            lines.append("| Risk | File | Summary |")
            lines.append("|------|------|---------|")
            for c in report.comments:
                emoji = risk_emoji.get(c.risk_level, "")
                lines.append(
                    f"| {emoji} {c.risk_level} | `{c.file_path}` | {c.summary} |"
                )
            lines.append("")

            # Detailed comments
            for c in report.comments:
                if c.risk_level == "FALSE_POSITIVE":
                    continue

                emoji = risk_emoji.get(c.risk_level, "")
                lines.append(f"### {emoji} {c.risk_level}: `{c.file_path}`")
                lines.append("")
                lines.append(f"> **Past bug**: {c.past_bug_reference}")
                lines.append("")
                lines.append(c.explanation)
                lines.append("")

                if c.suggestion:
                    lines.append(f"**Suggestion**: {c.suggestion}")
                    lines.append("")

                if c.suggested_code:
                    lines.append("```suggestion")
                    lines.append(c.suggested_code)
                    lines.append("```")
                    lines.append("")

                lines.append("---")
                lines.append("")

        # Summary
        lines.append(f"**Summary**: {report.summary}")
        lines.append("")
        lines.append(
            f"*Analyzed by DiffMind + {report.provider} ({report.model_used})*"
        )

        return "\n".join(lines)

    def post_check_status(
        self,
        sha: str,
        report: ReviewReport,
        fail_on: str = "HIGH",
    ) -> str:
        """Post a commit status check.

        Args:
            sha: The commit SHA to post status on.
            report: The AI-generated ReviewReport.
            fail_on: Risk level threshold to fail ("HIGH", "MEDIUM", "LOW").

        Returns:
            URL of the status.
        """
        risk_order = {"HIGH": 3, "MEDIUM": 2, "LOW": 1, "CLEAN": 0}
        fail_level = risk_order.get(fail_on.upper(), 3)
        actual_level = risk_order.get(report.overall_risk, 0)

        state = "failure" if actual_level >= fail_level else "success"
        description = (
            f"DiffMind: {report.overall_risk} risk "
            f"({report.total_warnings_analyzed} warnings, "
            f"{report.false_positives} false positives)"
        )

        result = self._api_request(
            "POST",
            f"statuses/{sha}",
            {
                "state": state,
                "description": description[:140],
                "context": "diffmind/ai-review",
            },
        )
        return result.get("url", "")
