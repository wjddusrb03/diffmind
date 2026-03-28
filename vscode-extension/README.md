# DiffMind for VS Code

> AI Code Review Memory - learns from your team's bug history and warns when similar patterns appear.

## Features

- **Inline Warnings**: Bug pattern warnings appear directly in VS Code's Problems panel
- **AI Review**: LLM-powered analysis with fix suggestions (Claude/OpenAI/Ollama)
- **Auto-Review on Save**: Optionally review changes every time you save
- **Search Bug History**: Semantic search over past bug fixes
- **Status Bar**: Quick overview of review status
- **WebView Reports**: Detailed review reports in side panels

## Quick Start

1. Install DiffMind CLI: `pip install diffmind`
2. Install this extension
3. Open a git repository in VS Code
4. Run **DiffMind: Learn Repository History** (Ctrl+Shift+P → "DiffMind: Learn")
5. Make changes and run **DiffMind: Review Current Changes** (Ctrl+Shift+D)

## Commands

| Command | Shortcut | Description |
|---------|----------|-------------|
| DiffMind: Learn Repository History | - | Learn from git history |
| DiffMind: Review Current Changes | Ctrl+Shift+D | Review all unstaged changes |
| DiffMind: Review Staged Changes | - | Review only staged changes |
| DiffMind: AI Review (LLM Analysis) | Ctrl+Shift+A | AI-powered deep analysis |
| DiffMind: Search Bug History | Ctrl+Shift+F6 | Semantic search over past bugs |
| DiffMind: Show Statistics | - | Show index statistics |
| DiffMind: Toggle Auto-Review on Save | - | Enable/disable auto-review |

## Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `diffmind.pythonPath` | `python` | Python interpreter path |
| `diffmind.autoReviewOnSave` | `false` | Auto-review when saving files |
| `diffmind.threshold` | `0.75` | Similarity threshold (0-1) |
| `diffmind.aiProvider` | `claude` | LLM provider (claude/openai/ollama) |
| `diffmind.aiLanguage` | `en` | Output language (en/ko) |
| `diffmind.maxWarningsPerHunk` | `3` | Max warnings per code hunk |
| `diffmind.showStatusBar` | `true` | Show status bar item |

## Context Menu

Right-click in any editor to access:
- DiffMind: Review Current Changes
- DiffMind: AI Review
- DiffMind: Search Bug History

## Requirements

- Python 3.9+ with `diffmind` package installed
- Git repository
- For AI Review: API key for Claude/OpenAI, or Ollama running locally
