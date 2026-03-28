"""Git log and diff parser for DiffMind."""

from __future__ import annotations

import os
import re
import subprocess
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from .models import DiffHunk

# ── Language detection ──────────────────────────────────────────────

LANG_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".cpp": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
    ".scala": "scala",
    ".r": "r",
    ".sql": "sql",
    ".sh": "shell",
    ".bash": "shell",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".json": "json",
    ".toml": "toml",
    ".xml": "xml",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".vue": "vue",
    ".svelte": "svelte",
}


def detect_language(file_path: str) -> str:
    """Detect programming language from file extension."""
    _, ext = os.path.splitext(file_path.lower())
    return LANG_MAP.get(ext, "unknown")


# ── Bugfix detection ────────────────────────────────────────────────

BUGFIX_PATTERNS = [
    # Conventional commits
    re.compile(r"^fix(\(.+\))?[!:]", re.IGNORECASE),
    re.compile(r"^bugfix(\(.+\))?[!:]", re.IGNORECASE),
    re.compile(r"^hotfix(\(.+\))?[!:]", re.IGNORECASE),
    # Issue references
    re.compile(r"fix(es|ed)?\s+#\d+", re.IGNORECASE),
    re.compile(r"closes?\s+#\d+", re.IGNORECASE),
    re.compile(r"resolves?\s+#\d+", re.IGNORECASE),
]

BUGFIX_KEYWORDS = [
    "fix", "bug", "hotfix", "patch", "resolve", "repair",
    "수정", "버그", "핫픽스", "고침", "해결", "오류",
]


def detect_bugfix(commit_message: str, labels: Optional[List[str]] = None) -> bool:
    """Determine if a commit is a bug fix."""
    msg = commit_message.strip()

    # Priority 1: PR labels
    if labels:
        label_lower = [l.lower() for l in labels]
        if any(kw in label_lower for kw in ("bug", "hotfix", "bugfix")):
            return True

    # Priority 2: Conventional commit patterns
    for pat in BUGFIX_PATTERNS:
        if pat.search(msg):
            return True

    # Priority 3: Keyword in message
    msg_lower = msg.lower()
    if any(kw in msg_lower for kw in BUGFIX_KEYWORDS):
        return True

    # Priority 4: Revert commits imply previous was buggy
    if msg_lower.startswith("revert"):
        return True

    return False


# ── PR number extraction ────────────────────────────────────────────

_PR_PATTERN = re.compile(r"#(\d+)")


def extract_pr_number(commit_message: str) -> Optional[int]:
    """Extract PR/issue number from commit message."""
    m = _PR_PATTERN.search(commit_message)
    return int(m.group(1)) if m else None


# ── Git command helpers ─────────────────────────────────────────────

def _run_git(args: List[str], repo_path: str = ".") -> str:
    """Run a git command and return stdout."""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=repo_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        raise RuntimeError(f"Git command failed: {e}")


# ── Diff hunk parsing ──────────────────────────────────────────────

_HUNK_HEADER = re.compile(r"^@@\s+.+\s+@@(.*)$")


def _parse_diff_text(diff_text: str, commit_hash: str, commit_message: str,
                     author: str, timestamp: datetime, is_bugfix: bool,
                     pr_number: Optional[int]) -> List[DiffHunk]:
    """Parse unified diff text into DiffHunk objects."""
    hunks: List[DiffHunk] = []
    current_file = None
    old_lines: List[str] = []
    new_lines: List[str] = []
    ctx_lines: List[str] = []
    hunk_header = ""

    def _flush():
        nonlocal old_lines, new_lines, ctx_lines, hunk_header
        if current_file and (old_lines or new_lines):
            hunks.append(DiffHunk(
                commit_hash=commit_hash,
                file_path=current_file,
                language=detect_language(current_file),
                old_code="\n".join(old_lines),
                new_code="\n".join(new_lines),
                context="\n".join(ctx_lines[-6:]),  # keep last 6 context lines
                commit_message=commit_message,
                author=author,
                timestamp=timestamp,
                is_bugfix=is_bugfix,
                hunk_header=hunk_header,
                pr_number=pr_number,
            ))
        old_lines = []
        new_lines = []
        ctx_lines = []
        hunk_header = ""

    for line in diff_text.split("\n"):
        # New file
        if line.startswith("diff --git"):
            _flush()
            # extract file path from "diff --git a/path b/path"
            parts = line.split(" b/", 1)
            if len(parts) == 2:
                current_file = parts[1].strip()
            else:
                current_file = None
        elif line.startswith("+++") or line.startswith("---"):
            continue  # skip file headers
        elif _HUNK_HEADER.match(line):
            _flush()
            hunk_header = line
        elif line.startswith("-") and not line.startswith("---"):
            old_lines.append(line[1:])
        elif line.startswith("+") and not line.startswith("+++"):
            new_lines.append(line[1:])
        else:
            # Context line
            if line.startswith(" "):
                ctx_lines.append(line[1:])
            elif line.strip():
                ctx_lines.append(line)

    _flush()
    return hunks


# ── Main parsers ────────────────────────────────────────────────────

# Separator that won't appear in normal git output
_SEP = "<<DIFFMIND_SEP>>"
_COMMIT_FORMAT = f"%H{_SEP}%an{_SEP}%aI{_SEP}%s"


def parse_git_log(repo_path: str = ".", since: Optional[str] = None,
                  until: Optional[str] = None, branch: str = "HEAD",
                  since_commit: Optional[str] = None) -> Tuple[List[DiffHunk], int, int]:
    """Parse git log into DiffHunk list.

    Returns:
        (hunks, total_commits, bugfix_commits)
    """
    args = [
        "log", branch,
        f"--format={_COMMIT_FORMAT}",
        "-p",  # include diff
        "--diff-filter=MRA",  # Modified, Renamed, Added
        "--no-merges",
    ]
    if since:
        args.append(f"--since={since}")
    if until:
        args.append(f"--until={until}")
    if since_commit:
        args.append(f"{since_commit}..HEAD")

    raw = _run_git(args, repo_path)
    if not raw.strip():
        return [], 0, 0

    hunks: List[DiffHunk] = []
    total_commits = 0
    bugfix_commits = 0

    # Split by commit boundaries
    commit_blocks = re.split(r"^(?=\w{40}" + re.escape(_SEP) + r")", raw, flags=re.MULTILINE)

    for block in commit_blocks:
        block = block.strip()
        if not block:
            continue

        # Parse header line
        lines = block.split("\n", 1)
        header = lines[0]
        diff_text = lines[1] if len(lines) > 1 else ""

        parts = header.split(_SEP)
        if len(parts) < 4:
            continue

        commit_hash = parts[0].strip()
        author = parts[1].strip()
        timestamp_str = parts[2].strip()
        message = parts[3].strip()

        # Parse timestamp
        try:
            ts = datetime.fromisoformat(timestamp_str)
        except (ValueError, TypeError):
            ts = datetime.now(timezone.utc)

        is_bugfix = detect_bugfix(message)
        pr_number = extract_pr_number(message)

        total_commits += 1
        if is_bugfix:
            bugfix_commits += 1

        # Parse diff hunks
        commit_hunks = _parse_diff_text(
            diff_text, commit_hash, message, author, ts, is_bugfix, pr_number
        )
        hunks.extend(commit_hunks)

    return hunks, total_commits, bugfix_commits


def parse_current_diff(repo_path: str = ".", staged: bool = False) -> List[DiffHunk]:
    """Parse the current working diff (staged or unstaged)."""
    args = ["diff"]
    if staged:
        args.append("--cached")

    diff_text = _run_git(args, repo_path)
    if not diff_text.strip():
        return []

    now = datetime.now(timezone.utc)
    return _parse_diff_text(
        diff_text,
        commit_hash="WORKING",
        commit_message="(current changes)",
        author="(you)",
        timestamp=now,
        is_bugfix=False,
        pr_number=None,
    )


def get_head_commit(repo_path: str = ".") -> str:
    """Get the current HEAD commit hash."""
    result = _run_git(["rev-parse", "HEAD"], repo_path)
    return result.strip()
