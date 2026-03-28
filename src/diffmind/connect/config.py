"""Configuration loader for DiffMind Connect."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LLMConfig:
    """LLM provider configuration."""

    provider: str = "claude"  # claude, openai, ollama
    model: str = ""  # auto-selected if empty
    api_key: str = ""  # from env if empty
    base_url: str = ""  # for ollama / custom endpoints
    temperature: float = 0.3
    max_tokens: int = 2048
    language: str = "en"  # en, ko for output language

    def resolve_model(self) -> str:
        """Return model name, using defaults per provider."""
        if self.model:
            return self.model
        defaults = {
            "claude": "claude-sonnet-4-20250514",
            "openai": "gpt-4o",
            "ollama": "deepseek-coder:6.7b",
        }
        return defaults.get(self.provider, "claude-sonnet-4-20250514")

    def resolve_api_key(self) -> str:
        """Return API key from config or environment."""
        if self.api_key:
            return self.api_key
        env_map = {
            "claude": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
        }
        env_var = env_map.get(self.provider, "")
        return os.environ.get(env_var, "")


@dataclass
class GitHubConfig:
    """GitHub integration configuration."""

    token: str = ""  # from env GITHUB_TOKEN if empty
    repo: str = ""  # owner/repo
    post_comments: bool = True
    add_labels: bool = True

    def resolve_token(self) -> str:
        if self.token:
            return self.token
        return os.environ.get("GITHUB_TOKEN", "")


@dataclass
class SlackConfig:
    """Slack notification configuration."""

    webhook_url: str = ""
    channel: str = ""
    min_risk: str = "MEDIUM"  # HIGH, MEDIUM, LOW
    mention_users: bool = False


@dataclass
class DiscordConfig:
    """Discord notification configuration."""

    webhook_url: str = ""
    min_risk: str = "HIGH"
    mention_role: str = ""


@dataclass
class ConnectConfig:
    """Root configuration for DiffMind Connect."""

    llm: LLMConfig = field(default_factory=LLMConfig)
    github: GitHubConfig = field(default_factory=GitHubConfig)
    slack: SlackConfig = field(default_factory=SlackConfig)
    discord: DiscordConfig = field(default_factory=DiscordConfig)


def load_config(repo_path: str = ".") -> ConnectConfig:
    """Load configuration from .diffmind/config.yml or defaults.

    Falls back to environment variables and sensible defaults.
    """
    config_path = os.path.join(repo_path, ".diffmind", "config.yml")
    config = ConnectConfig()

    if os.path.isfile(config_path):
        try:
            import yaml

            with open(config_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

            if "llm" in data:
                for k, v in data["llm"].items():
                    if hasattr(config.llm, k):
                        setattr(config.llm, k, v)
            if "github" in data:
                for k, v in data["github"].items():
                    if hasattr(config.github, k):
                        setattr(config.github, k, v)
            if "slack" in data:
                for k, v in data["slack"].items():
                    if hasattr(config.slack, k):
                        setattr(config.slack, k, v)
            if "discord" in data:
                for k, v in data["discord"].items():
                    if hasattr(config.discord, k):
                        setattr(config.discord, k, v)
        except ImportError:
            pass  # pyyaml not installed → use defaults
        except Exception:
            pass  # malformed config → use defaults

    return config


def generate_default_config(repo_path: str = ".") -> str:
    """Generate a default .diffmind/config.yml file."""
    config_dir = os.path.join(repo_path, ".diffmind")
    os.makedirs(config_dir, exist_ok=True)
    config_path = os.path.join(config_dir, "config.yml")

    content = """\
# DiffMind Connect Configuration
# https://github.com/wjddusrb03/diffmind

llm:
  provider: claude          # claude, openai, ollama
  model: ""                 # auto-select (claude-sonnet-4-20250514, gpt-4o, etc.)
  api_key: ""               # reads from ANTHROPIC_API_KEY / OPENAI_API_KEY env
  base_url: ""              # for ollama: http://localhost:11434
  temperature: 0.3
  max_tokens: 2048
  language: en              # en or ko

github:
  token: ""                 # reads from GITHUB_TOKEN env
  repo: ""                  # owner/repo
  post_comments: true
  add_labels: true

slack:
  webhook_url: ""
  channel: ""
  min_risk: MEDIUM          # HIGH, MEDIUM, LOW

discord:
  webhook_url: ""
  min_risk: HIGH
  mention_role: ""
"""

    with open(config_path, "w", encoding="utf-8") as f:
        f.write(content)

    return config_path
