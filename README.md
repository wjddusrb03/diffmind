# DiffMind - AI Code Review Memory

> [한국어 문서](README_KO.md)

**DiffMind** learns from your team's bug history and warns when similar patterns appear in new code changes.

## Why DiffMind?

```
ESLint:     "Variable used before declaration"                     (generic rule)
DiffMind:   "This pattern is 93% similar to a bug fixed in PR #142"   (team-specific)
```

Other tools check **generic rules**. DiffMind remembers **your team's actual past mistakes**.

## How It Works

```
git diff → embed code changes (sentence-transformers)
     ↓
compare against past bugfix history (TurboQuant compressed)
     ↓
"This pattern was a bug 3 months ago in PR #142" warning
     ↓
auto-run via VS Code / git hook / GitHub Action
```

---

## Installation

### CLI

```bash
git clone https://github.com/wjddusrb03/diffmind.git
cd diffmind
pip install -e .
```

### VS Code Extension

```bash
cd vscode-extension
npm install && npm run compile
npx @vscode/vsce package --no-dependencies
code --install-extension diffmind-0.1.1.vsix
```

Restart VS Code after installation. You'll see `🛡 DiffMind` in the status bar.

---

## VS Code Usage (Step-by-Step)

### Step 1: Open a Git Project

Open any folder that has a `.git` directory in VS Code.

### Step 2: Learn History (One-Time)

```
Ctrl+Shift+P → "DiffMind: Learn" → Enter
```

- Leave the date input **empty** to learn all history
- Or enter a date like `2024-01-01` to limit scope

### Step 3: Review Changes

After modifying any file:

```
Ctrl+Shift+D
```

**Where to see results:**

| Location | Content |
|---|---|
| **Status Bar** (bottom) | `✓ Clean` or `⚠ N warnings` |
| **Problems Panel** (`Ctrl+Shift+M`) | File-by-file warnings list |
| **Popup** | "Show Details" or "Show Problems" buttons |

### Step 4: Search Bug History

```
Ctrl+Shift+F6
```

Enter a query like `"null check"`, `"authentication error"`, or `"memory leak"`.

### Step 5: View Statistics

```
Ctrl+Shift+P → "DiffMind: Stats"
```

Shows total commits, bugfix ratio, top buggy files, and memory usage.

### Step 6: Auto-Review on Save (Optional)

```
Ctrl+Shift+P → "DiffMind: Toggle Auto-Review on Save"
```

When enabled, every file save triggers an automatic review.

### Right-Click Menu

Right-click in the editor to see:
- Review Current Changes
- AI Review
- Search Bug History

---

## Keyboard Shortcuts

| Shortcut | Action | Description |
|---|---|---|
| `Ctrl+Shift+D` | **Review** | Compare changes against past bugs |
| `Ctrl+Shift+A` | **AI Review** | LLM analysis + fix suggestions |
| `Ctrl+Shift+F6` | **Search** | Semantic search of bug history |
| `Ctrl+Shift+M` | **Problems** | View warnings list (VS Code built-in) |

---

## VS Code Settings

`Ctrl+,` → search "diffmind":

| Setting | Default | Description |
|---|---|---|
| `diffmind.pythonPath` | `python` | Python interpreter path |
| `diffmind.autoReviewOnSave` | `false` | Auto-review when saving files |
| `diffmind.threshold` | `0.75` | Similarity threshold (lower = more warnings) |
| `diffmind.aiProvider` | `claude` | LLM provider (claude/openai/ollama) |
| `diffmind.aiLanguage` | `en` | AI output language (en/ko) |
| `diffmind.maxWarningsPerHunk` | `3` | Max warnings per code hunk |
| `diffmind.showStatusBar` | `true` | Show status bar item |

---

## CLI Usage

### Quick Start

```bash
# 1. Learn from repository history (one-time)
diffmind learn .

# 2. Review current changes
diffmind review

# 3. Review only staged changes
diffmind review --staged

# 4. JSON output (for CI)
diffmind review --json

# 5. Search past changes
diffmind search "null check missing"

# 6. View statistics
diffmind stats

# 7. Install pre-commit hook
diffmind install --pre-commit

# 8. Generate GitHub Action
diffmind install --github-action
```

### Commands

| Command | Description |
|---|---|
| `diffmind learn [PATH]` | Learn bug patterns from git history |
| `diffmind review` | Review current changes against past bugs |
| `diffmind search "QUERY"` | Semantic search over diff history |
| `diffmind stats` | Show index statistics |
| `diffmind install` | Install git hooks / GitHub Action |

### Options

#### `diffmind learn`

| Option | Description | Example |
|---|---|---|
| `--since DATE` | Learn only after this date | `--since 2024-01-01` |
| `--until DATE` | Learn only before this date | `--until 2024-12-31` |
| `--branch NAME` | Specific branch only | `--branch main` |
| `--bugfix-only` | Only bugfix commits | |
| `--model NAME` | Embedding model | `--model all-MiniLM-L6-v2` |
| `--bits N` | Compression bits (2, 3, 4) | `--bits 3` (default) |
| `--update` | Incremental learn (new commits only) | |

#### `diffmind review`

| Option | Description | Example |
|---|---|---|
| `--staged` | Only staged changes | |
| `--threshold N` | Similarity threshold (0-1) | `--threshold 0.80` |
| `-k N` | Max similar items per warning | `-k 5` |
| `--fail-on LEVEL` | Exit 1 if risk >= level | `--fail-on high` |
| `--json` | JSON output | |

#### `diffmind search`

| Option | Description | Example |
|---|---|---|
| `-k N` | Number of results | `-k 10` |
| `--file PATH` | Filter by file path | `--file src/auth/` |
| `--author NAME` | Filter by author | `--author "john"` |
| `--lang LANG` | Filter by language | `--lang python` |
| `--bugfix-only` | Only bugfix commits | |

---

## Real-World Scenarios

### Individual Developer

```bash
git add .
diffmind review --staged     # check before committing
git commit -m "feat: ..."
```

### Team (Pre-Commit Hook)

```bash
# Team lead sets up once
diffmind learn . --since 2024-01-01
diffmind install --pre-commit

# Every team member's commit is auto-reviewed
git commit -m "update handler"
# → DiffMind: reviewing staged changes...
# → [!!!] HIGH RISK: 93% similar to bug in PR #142
```

### CI/CD (GitHub Action)

```yaml
name: DiffMind Review
on:
  pull_request:
    types: [opened, synchronize]

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install & Review
        run: |
          pip install diffmind
          diffmind learn . --since 6months
          diffmind review --staged --fail-on high
```

---

## Bug Detection

DiffMind identifies bugfix commits by:

| Criteria | Examples |
|---|---|
| Conventional Commits | `fix:`, `bugfix:`, `hotfix:` prefix |
| Issue references | `fix #123`, `closes #456`, `resolves #789` |
| Keywords | `fix`, `bug`, `resolve`, `patch` |
| PR labels | `bug`, `hotfix` |
| Revert commits | Reverted commits = bug fixes |

## Risk Classification

| Risk | Condition | VS Code Display | Meaning |
|---|---|---|---|
| **HIGH** | ≥90% similar + bugfix commit | Red error | Very likely same bug |
| **MEDIUM** | ≥80% similar + bugfix commit | Yellow warning | Needs attention |
| **LOW** | ≥75% similar | Blue info | Reference only |

---

## vs Other Tools

| Tool | What It Does | What DiffMind Does |
|---|---|---|
| ESLint/Pylint | Generic rule violations | **Team-specific** bug patterns |
| GitHub Copilot | Code generation | Bug pattern **memory** |
| CodeRabbit | Generic AI review | **Project-specific** learned review |
| SonarQube | Static analysis | **Semantic** similarity analysis |
| `git log --grep` | Keyword search | **Meaning-based** search |

---

## Architecture

```
src/diffmind/
├── cli.py              # Click CLI (learn, review, search, stats, install)
├── models.py           # DiffHunk, ReviewWarning data models
├── parser.py           # Git log/diff parser, bugfix detection
├── indexer.py          # Embedding + TurboQuant compression
├── reviewer.py         # Similarity-based review engine
├── searcher.py         # Semantic search
├── storage.py          # Index persistence (.diffmind/index.pkl)
├── display.py          # Terminal + JSON formatting
└── hooks.py            # Git hooks + GitHub Action generation

vscode-extension/
├── src/extension.ts    # VS Code extension (TypeScript)
└── package.json        # Extension manifest

tests/                  # 318 tests
```

## Tech Stack

- [langchain-turboquant](https://pypi.org/project/langchain-turboquant/) - 3-bit vector quantization
- [sentence-transformers](https://www.sbert.net/) - all-MiniLM-L6-v2 embeddings (384 dim)
- [Click](https://click.palletsprojects.com/) - CLI framework
- NumPy - Vector operations
- TypeScript - VS Code Extension API

## Tests

```bash
pytest tests/ -v
```

## FAQ

**Q: "No diff hunks found" error**
A: The project has too few git commits. You need at least 3-5 commits.

**Q: Learning takes too long**
A: Use `--since 2024-01-01` to limit the date range.

**Q: VS Code warnings not showing**
A: Run `Ctrl+Shift+P` → `Developer: Reload Window` and try again.

**Q: How to use AI Review?**
A: Set `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` env variable, then press `Ctrl+Shift+A`.

## License

MIT
