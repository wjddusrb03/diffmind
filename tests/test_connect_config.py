"""Tests for DiffMind Connect configuration."""

from __future__ import annotations

import os
import pytest

from diffmind.connect.config import (
    ConnectConfig,
    DiscordConfig,
    GitHubConfig,
    LLMConfig,
    SlackConfig,
    generate_default_config,
    load_config,
)


class TestLLMConfig:
    def test_default_provider(self):
        cfg = LLMConfig()
        assert cfg.provider == "claude"

    def test_resolve_model_claude(self):
        cfg = LLMConfig(provider="claude")
        assert "claude" in cfg.resolve_model()

    def test_resolve_model_openai(self):
        cfg = LLMConfig(provider="openai")
        assert "gpt" in cfg.resolve_model()

    def test_resolve_model_ollama(self):
        cfg = LLMConfig(provider="ollama")
        assert "deepseek" in cfg.resolve_model()

    def test_resolve_model_custom(self):
        cfg = LLMConfig(provider="claude", model="claude-3-opus")
        assert cfg.resolve_model() == "claude-3-opus"

    def test_resolve_api_key_from_config(self):
        cfg = LLMConfig(api_key="sk-test")
        assert cfg.resolve_api_key() == "sk-test"

    def test_resolve_api_key_from_env(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env")
        cfg = LLMConfig(provider="claude")
        assert cfg.resolve_api_key() == "sk-env"

    def test_resolve_api_key_openai_env(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
        cfg = LLMConfig(provider="openai")
        assert cfg.resolve_api_key() == "sk-openai"

    def test_resolve_api_key_missing(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        cfg = LLMConfig(provider="claude")
        assert cfg.resolve_api_key() == ""

    def test_default_temperature(self):
        cfg = LLMConfig()
        assert cfg.temperature == 0.3


class TestGitHubConfig:
    def test_resolve_token_from_config(self):
        cfg = GitHubConfig(token="ghp-test")
        assert cfg.resolve_token() == "ghp-test"

    def test_resolve_token_from_env(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "ghp-env")
        cfg = GitHubConfig()
        assert cfg.resolve_token() == "ghp-env"

    def test_defaults(self):
        cfg = GitHubConfig()
        assert cfg.post_comments is True
        assert cfg.add_labels is True


class TestConnectConfig:
    def test_default_config(self):
        cfg = ConnectConfig()
        assert isinstance(cfg.llm, LLMConfig)
        assert isinstance(cfg.github, GitHubConfig)
        assert isinstance(cfg.slack, SlackConfig)
        assert isinstance(cfg.discord, DiscordConfig)


class TestLoadConfig:
    def test_load_from_nonexistent_dir(self, tmp_path):
        cfg = load_config(str(tmp_path))
        assert cfg.llm.provider == "claude"

    def test_load_from_empty_config(self, tmp_path):
        config_dir = tmp_path / ".diffmind"
        config_dir.mkdir()
        (config_dir / "config.yml").write_text("")
        cfg = load_config(str(tmp_path))
        assert cfg.llm.provider == "claude"

    def test_load_with_yaml(self, tmp_path):
        config_dir = tmp_path / ".diffmind"
        config_dir.mkdir()
        yaml_content = "llm:\n  provider: openai\n  temperature: 0.5\n"
        (config_dir / "config.yml").write_text(yaml_content)

        try:
            import yaml
            cfg = load_config(str(tmp_path))
            assert cfg.llm.provider == "openai"
            assert cfg.llm.temperature == 0.5
        except ImportError:
            # pyyaml not installed - still works with defaults
            cfg = load_config(str(tmp_path))
            assert cfg.llm.provider == "claude"

    def test_load_malformed_yaml(self, tmp_path):
        config_dir = tmp_path / ".diffmind"
        config_dir.mkdir()
        (config_dir / "config.yml").write_text("{{invalid yaml::")
        cfg = load_config(str(tmp_path))
        assert cfg.llm.provider == "claude"  # falls back to defaults


class TestGenerateDefaultConfig:
    def test_creates_config_file(self, tmp_path):
        path = generate_default_config(str(tmp_path))
        assert os.path.isfile(path)
        with open(path) as f:
            content = f.read()
        assert "provider" in content
        assert "webhook_url" in content

    def test_creates_diffmind_dir(self, tmp_path):
        generate_default_config(str(tmp_path))
        assert os.path.isdir(str(tmp_path / ".diffmind"))

    def test_config_contains_all_sections(self, tmp_path):
        path = generate_default_config(str(tmp_path))
        with open(path) as f:
            content = f.read()
        assert "llm:" in content
        assert "github:" in content
        assert "slack:" in content
        assert "discord:" in content
