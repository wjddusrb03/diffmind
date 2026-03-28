# DiffMind - AI Code Review Memory

> [한국어 문서](README_KO.md)

**DiffMind** learns from your team's bug history and warns when similar patterns appear in new code changes. Powered by semantic embeddings + LLM analysis.

## How It Works

```
git diff → embed changed code (sentence-transformers)
     ↓
search past bugfix history (TurboQuant compressed)
     ↓
"This pattern was a bug 3 months ago in PR #142" warning
     ↓
LLM analyzes + suggests fix code (Claude / GPT / Ollama)
     ↓
auto-run via VS Code / git hook / GitHub Action
```

## Installation

```bash
# Core CLI
git clone https://github.com/wjddusrb03/diffmind.git
cd diffmind
pip install -e .

# With LLM integration (Claude + OpenAI)
pip install -e ".[llm]"

# With all integrations (GitHub, Slack, Discord)
pip install -e ".[connect]"
```

### VS Code Extension

```bash
# Option 1: Install from .vsix file
cd vscode-extension
npm install && npm run compile
npx @vscode/vsce package --allow-missing-repository
code --install-extension diffmind-0.1.0.vsix

# Option 2: Open in VS Code and press F5 to debug
```

## Quick Start

### CLI

```bash
# 1. Learn from repository history (one-time)
diffmind learn . --since 2024-01-01

# 2. Review current changes
diffmind review --staged

# 3. AI-powered review with fix suggestions
diffmind connect ai-review --staged --provider claude

# 4. Search past changes
diffmind search "null check missing" --lang python

# 5. View statistics
diffmind stats

# 6. Install pre-commit hook (auto-review on every commit)
diffmind install --pre-commit
```

### VS Code

```
Ctrl+Shift+P → "DiffMind: Learn"        ← one-time setup
Ctrl+Shift+D                              ← review changes
Ctrl+Shift+A                              ← AI review with LLM
Ctrl+Shift+F6                             ← search bug history
Right-click → DiffMind menu               ← context menu
```

## Commands

### Core CLI

| Command | Description |
|---|---|
| `diffmind learn [PATH]` | Learn from git history |
| `diffmind review` | Review current changes against past bugs |
| `diffmind search QUERY` | Semantic search over diff history |
| `diffmind stats` | Show index statistics |
| `diffmind install` | Install git hooks / GitHub Action |

### Connect (Integrations)

| Command | Description |
|---|---|
| `diffmind connect ai-review` | LLM-powered review with fix suggestions |
| `diffmind connect github --pr N` | Auto-post AI review on GitHub PR |
| `diffmind connect slack --test` | Send alerts to Slack |
| `diffmind connect discord --test` | Send alerts to Discord |
| `diffmind connect init` | Generate config file |

### VS Code Extension

| Command | Shortcut | Description |
|---|---|---|
| DiffMind: Learn | - | Learn repository history |
| DiffMind: Review | `Ctrl+Shift+D` | Review changes → Problems panel |
| DiffMind: Review Staged | - | Review only staged changes |
| DiffMind: AI Review | `Ctrl+Shift+A` | LLM analysis → WebView panel |
| DiffMind: Search | `Ctrl+Shift+F6` | Search bug history |
| DiffMind: Stats | - | Show index statistics |
| DiffMind: Toggle Auto-Review | - | Auto-review on file save |

## Key Features

- **Team Bug Memory**: Learns your team's specific bug patterns, not generic rules
- **LLM Analysis**: Claude/GPT/Ollama analyzes warnings and suggests fix code
- **VS Code Integration**: Inline warnings, WebView panels, status bar, auto-review on save
- **Semantic Search**: Search by meaning, not keywords ("authentication error" finds auth bugs)
- **TurboQuant Compression**: ~2x memory savings for large repositories
- **GitHub PR Bot**: Auto-post AI review comments on pull requests
- **Slack / Discord Alerts**: Real-time notifications for risky patterns
- **Git Hook / GitHub Action**: Auto-review on every commit or PR
- **Incremental Learning**: Only process new commits with `--update`
- **Bilingual**: English and Korean support for AI reviews
- **Multi-language**: Supports Python, JavaScript, TypeScript, Java, Go, Rust, C/C++, and 30+ languages

## AI Review (Connect)

DiffMind Connect combines pattern detection with LLM analysis:

```bash
# Review with Claude (default)
diffmind connect ai-review --staged

# Review with OpenAI
diffmind connect ai-review --staged --provider openai

# Review with local Ollama (free, offline)
diffmind connect ai-review --staged --provider ollama

# Korean output
diffmind connect ai-review --staged --lang ko

# JSON for CI pipelines
diffmind connect ai-review --staged --json --fail-on high
```

**Output example:**
```
============================================================
  DiffMind AI Review Report
  Provider: claude (claude-sonnet-4-20250514)
  Overall risk: HIGH
============================================================

[!!!] HIGH: src/auth/login.py
  Confidence: 95%

  Summary: Null check removed - NoneType error likely

  Explanation:
    The same pattern caused a NoneType error in PR #142.
    The user object null check was removed.

  Suggested fix:
    if user is None:
        raise ValueError("User not found")
```

### GitHub PR Bot

```bash
# Post AI review as PR comment
diffmind connect github --pr 42

# Set up in GitHub Action
ANTHROPIC_API_KEY=${{ secrets.ANTHROPIC_API_KEY }}
diffmind connect ai-review --staged --json --fail-on high
```

### Notifications

```bash
# Slack
diffmind connect slack --test --webhook https://hooks.slack.com/services/...

# Discord
diffmind connect discord --test --webhook https://discord.com/api/webhooks/...
```

### Configuration

```bash
# Generate config file
diffmind connect init
# → .diffmind/config.yml
```

```yaml
llm:
  provider: claude          # claude, openai, ollama
  language: ko              # en or ko
github:
  token: ""                 # or GITHUB_TOKEN env
  repo: owner/repo
slack:
  webhook_url: ""
  min_risk: MEDIUM
discord:
  webhook_url: ""
  min_risk: HIGH
```

## VS Code Extension Details

### What You See

- **Status Bar** (bottom-left): `🛡 DiffMind` → click to review
- **Problems Panel**: HIGH = red error, MEDIUM = yellow warning
- **WebView Panel**: Beautiful AI review report with fix suggestions
- **Context Menu**: Right-click → DiffMind review/search

### Settings

Open `Ctrl+,` → search "diffmind":

| Setting | Default | Description |
|---|---|---|
| `diffmind.pythonPath` | `python` | Python interpreter path |
| `diffmind.autoReviewOnSave` | `false` | Auto-review when saving |
| `diffmind.threshold` | `0.75` | Similarity threshold (0-1) |
| `diffmind.aiProvider` | `claude` | LLM provider |
| `diffmind.aiLanguage` | `en` | AI output language (en/ko) |
| `diffmind.maxWarningsPerHunk` | `3` | Max warnings per hunk |
| `diffmind.showStatusBar` | `true` | Show status bar item |

## How It Detects Bugs

DiffMind identifies bugfix commits by:
1. PR labels (`bug`, `hotfix`)
2. Issue references (`fix #123`, `closes #456`)
3. Conventional commits (`fix:`, `bugfix:`, `hotfix:`)
4. Keywords (`fix`, `bug`, `resolve`, `수정`, `버그`)
5. Revert commits

## Risk Classification

| Risk | Condition | Meaning |
|---|---|---|
| **HIGH** | ≥90% similar + bugfix commit | Very likely same bug |
| **MEDIUM** | ≥80% similar + bugfix commit | Needs attention |
| **LOW** | ≥75% similar | Reference only |

## CLI Options

### `diffmind learn`
- `--since DATE` / `--until DATE` - Date range
- `--branch NAME` - Specific branch
- `--bugfix-only` - Only bugfix commits
- `--model NAME` - Embedding model (default: all-MiniLM-L6-v2)
- `--bits N` - Compression bits: 2, 3, or 4 (default: 3)
- `--update` - Incremental learn

### `diffmind review`
- `--staged` - Only staged changes
- `--threshold N` - Similarity threshold (default: 0.75)
- `--fail-on LEVEL` - Exit 1 if risk >= level
- `--json` - JSON output

### `diffmind search`
- `--file PATH` - Filter by file
- `--author NAME` - Filter by author
- `--lang LANG` - Filter by language
- `--bugfix-only` - Only bugfix commits

### `diffmind connect ai-review`
- `--provider [claude|openai|ollama]` - LLM provider
- `--model NAME` - Model override
- `--lang [en|ko]` - Output language
- `--json` - JSON output
- `--fail-on LEVEL` - CI exit code

## vs Other Tools

| Tool | What It Does | What DiffMind Does |
|---|---|---|
| ESLint/Pylint | General rule violations | Team-specific bug patterns |
| GitHub Copilot | Code generation | Bug pattern memory |
| CodeRabbit | Generic AI review | Project-specific + LLM analysis |
| SonarQube | Static analysis | Semantic similarity + fix suggestions |
| `git log --grep` | Keyword search | Meaning-based search |

## Architecture

```
src/diffmind/
├── cli.py              # Click CLI (learn, review, search, stats, install, connect)
├── models.py           # DiffHunk, ReviewWarning, ReviewComment, ReviewReport
├── parser.py           # Git log/diff parser, bugfix detection
├── indexer.py          # Embedding + TurboQuant compression
├── reviewer.py         # Similarity-based review engine
├── searcher.py         # Semantic search
├── storage.py          # Pickle-based index persistence
├── display.py          # Terminal + JSON formatting
├── hooks.py            # Git hooks + GitHub Action generation
└── connect/
    ├── llm.py          # LLM reviewer (Claude/OpenAI/Ollama)
    ├── github_bot.py   # GitHub PR comments
    ├── slack.py        # Slack webhook alerts
    ├── discord.py      # Discord webhook alerts
    ├── config.py       # YAML config + env vars
    └── prompts.py      # Bilingual prompt templates

vscode-extension/
├── src/extension.ts    # VS Code extension
└── package.json        # Extension manifest

tests/                  # 440 tests
```

## Dependencies

**Core:**
- [langchain-turboquant](https://pypi.org/project/langchain-turboquant/) - Vector compression
- [sentence-transformers](https://www.sbert.net/) - Embedding models
- [Click](https://click.palletsprojects.com/) - CLI framework

**Optional (Connect):**
- [anthropic](https://github.com/anthropics/anthropic-sdk-python) - Claude API
- [openai](https://github.com/openai/openai-python) - OpenAI API
- [PyGithub](https://github.com/PyGithub/PyGithub) - GitHub API

## Tests

```bash
# Run all 440 tests
pytest tests/ -v

# Test categories:
# - Unit tests: models, parser, reviewer, display, storage, hooks
# - Integration: real git repos, real sentence-transformers
# - E2E: full CLI workflows, stress tests
# - Connect: LLM, GitHub, Slack, Discord, config, prompts
```

## License

MIT
