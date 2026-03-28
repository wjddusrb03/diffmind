# DiffMind - AI Code Review Memory

**DiffMind** learns from your team's bug history and warns when similar patterns appear in new code changes.

## How It Works

```
git diff → embed changed code
     ↓
search past bugfix history (TurboQuant compressed)
     ↓
"This pattern was a bug 3 months ago in PR #142" warning
     ↓
auto-run via git hook or GitHub Action
```

## Installation

```bash
# From source
git clone https://github.com/wjddusrb03/diffmind.git
cd diffmind
pip install -e .
```

## Quick Start

```bash
# 1. Learn from repository history (one-time)
diffmind learn . --since 2024-01-01

# 2. Install pre-commit hook (one-time)
diffmind install --pre-commit

# 3. Now every commit is auto-reviewed!
git commit -m "update login"
# DiffMind: reviewing staged changes...
# [!!!] HIGH RISK: src/auth/login.py (93% similar to bugfix a1b2c3d)

# 4. Manual review
diffmind review --staged

# 5. Search past changes
diffmind search "null check missing" --lang python

# 6. View statistics
diffmind stats

# 7. Incremental update
diffmind learn --update
```

## Commands

| Command | Description |
|---|---|
| `diffmind learn [PATH]` | Learn from git history |
| `diffmind review` | Review current changes against past bugs |
| `diffmind search QUERY` | Semantic search over diff history |
| `diffmind stats` | Show index statistics |
| `diffmind install` | Install automation hooks |

## Key Features

- **Team Bug Memory**: Learns your team's specific bug patterns, not generic rules
- **Semantic Search**: Search by meaning, not keywords ("authentication error" finds auth bugs)
- **TurboQuant Compression**: ~2x memory savings for large repositories
- **Asymmetric Scoring**: Search without decompressing vectors
- **Git Hook / GitHub Action**: Auto-review on every commit or PR
- **Incremental Learning**: Only process new commits with `--update`
- **Multi-language**: Supports Python, JavaScript, TypeScript, Java, Go, Rust, C/C++, and more

## How It Detects Bugs

DiffMind identifies bugfix commits by:
1. PR labels (`bug`, `hotfix`)
2. Issue references (`fix #123`, `closes #456`)
3. Conventional commits (`fix:`, `bugfix:`, `hotfix:`)
4. Keywords (`fix`, `bug`, `resolve`, `수정`, `버그`)
5. Revert commits

## Options

### `diffmind learn`
- `--since DATE` - Learn from commits after date
- `--bugfix-only` - Only learn bugfix commits
- `--model NAME` - Embedding model (default: all-MiniLM-L6-v2)
- `--bits N` - Compression bits: 2, 3, or 4 (default: 3)
- `--update` - Incremental learn (only new commits)

### `diffmind review`
- `--staged` - Only review staged changes
- `--threshold N` - Similarity threshold (default: 0.75)
- `--fail-on LEVEL` - Exit code 1 if risk >= level (high/medium/low)
- `--json` - JSON output for CI integration

### `diffmind search`
- `--file PATH` - Filter by file path
- `--author NAME` - Filter by author
- `--lang LANG` - Filter by language
- `--bugfix-only` - Only bugfix commits

## vs Other Tools

| Tool | What It Does | What DiffMind Does |
|---|---|---|
| ESLint/Pylint | General rule violations | Team-specific patterns |
| GitHub Copilot | Code generation | Bug pattern memory |
| CodeRabbit | Generic AI review | Project-specific learning |
| SonarQube | Static analysis | Semantic similarity search |
| `git log --grep` | Keyword search | Meaning-based search |

## Dependencies

- [langchain-turboquant](https://pypi.org/project/langchain-turboquant/) - Vector compression
- [sentence-transformers](https://www.sbert.net/) - Embedding models
- [Click](https://click.palletsprojects.com/) - CLI framework

## License

MIT
