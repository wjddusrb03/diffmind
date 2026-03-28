"""Tests for DiffMind Connect CLI commands."""

from __future__ import annotations

import os

import pytest
from click.testing import CliRunner

from diffmind.cli import main


class TestConnectInit:
    def test_init_creates_config(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(main, ["connect", "init", "--path", str(tmp_path)])
        assert result.exit_code == 0
        assert "[OK]" in result.output
        assert os.path.isfile(str(tmp_path / ".diffmind" / "config.yml"))

    def test_init_config_content(self, tmp_path):
        runner = CliRunner()
        runner.invoke(main, ["connect", "init", "--path", str(tmp_path)])
        with open(str(tmp_path / ".diffmind" / "config.yml")) as f:
            content = f.read()
        assert "provider:" in content
        assert "webhook_url:" in content


class TestConnectHelp:
    def test_connect_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["connect", "--help"])
        assert result.exit_code == 0
        assert "ai-review" in result.output
        assert "github" in result.output
        assert "slack" in result.output
        assert "discord" in result.output
        assert "init" in result.output

    def test_ai_review_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["connect", "ai-review", "--help"])
        assert result.exit_code == 0
        assert "--provider" in result.output
        assert "--lang" in result.output

    def test_github_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["connect", "github", "--help"])
        assert result.exit_code == 0
        assert "--pr" in result.output

    def test_slack_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["connect", "slack", "--help"])
        assert result.exit_code == 0
        assert "--webhook" in result.output

    def test_discord_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["connect", "discord", "--help"])
        assert result.exit_code == 0
        assert "--webhook" in result.output


class TestAIReviewCLI:
    def test_ai_review_no_index(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(main, [
            "connect", "ai-review", "--path", str(tmp_path)
        ])
        assert result.exit_code != 0

    def test_ai_review_provider_choices(self):
        runner = CliRunner()
        # Invalid provider should fail
        result = runner.invoke(main, [
            "connect", "ai-review", "--provider", "invalid"
        ])
        assert result.exit_code != 0

    def test_ai_review_lang_choices(self):
        runner = CliRunner()
        result = runner.invoke(main, [
            "connect", "ai-review", "--lang", "invalid"
        ])
        assert result.exit_code != 0


class TestSlackCLI:
    def test_slack_no_webhook(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(main, [
            "connect", "slack", "--test", "--path", str(tmp_path)
        ])
        assert result.exit_code != 0
        assert "webhook" in result.output.lower() or "error" in result.output.lower()


class TestDiscordCLI:
    def test_discord_no_webhook(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(main, [
            "connect", "discord", "--test", "--path", str(tmp_path)
        ])
        assert result.exit_code != 0
