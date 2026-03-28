"""Tests for DiffMind CLI."""

from click.testing import CliRunner

from diffmind.cli import main


class TestCLI:
    def test_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "DiffMind" in result.output

    def test_version(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_learn_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["learn", "--help"])
        assert result.exit_code == 0
        assert "--since" in result.output
        assert "--bugfix-only" in result.output

    def test_review_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["review", "--help"])
        assert result.exit_code == 0
        assert "--staged" in result.output
        assert "--fail-on" in result.output

    def test_search_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["search", "--help"])
        assert result.exit_code == 0
        assert "--author" in result.output
        assert "--lang" in result.output

    def test_stats_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["stats", "--help"])
        assert result.exit_code == 0

    def test_install_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["install", "--help"])
        assert result.exit_code == 0
        assert "--pre-commit" in result.output
        assert "--github-action" in result.output

    def test_review_no_index(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(main, ["review", "--path", "."])
            assert result.exit_code != 0
            assert "No DiffMind index" in result.output or "ERROR" in result.output

    def test_search_no_index(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(main, ["search", "test", "--path", "."])
            assert result.exit_code != 0

    def test_stats_no_index(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(main, ["stats", "--path", "."])
            assert result.exit_code != 0

    def test_install_no_flags(self):
        runner = CliRunner()
        result = runner.invoke(main, ["install"])
        assert "Specify" in result.output
