"""Hook installation for DiffMind."""

from __future__ import annotations

import os
import stat

PRE_COMMIT_TEMPLATE = '''#!/bin/sh
# DiffMind pre-commit hook
# Installed by: diffmind install --pre-commit

echo "DiffMind: reviewing staged changes..."
result=$(diffmind review --staged --fail-on {fail_on} 2>&1)
exit_code=$?

if [ $exit_code -ne 0 ]; then
    echo ""
    echo "$result"
    echo ""
    echo "[DiffMind] {fail_on_upper} risk patterns found!"
    echo "  Run 'diffmind review --staged' for details"
    echo "  Use 'git commit --no-verify' to skip (not recommended)"
    exit 1
fi

echo "[DiffMind] OK - no {fail_on} risk patterns found"
'''

GITHUB_ACTION_TEMPLATE = '''name: DiffMind Review
on:
  pull_request:
    types: [opened, synchronize]

jobs:
  diffmind-review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install DiffMind
        run: pip install diffmind

      - name: Learn repository history
        run: diffmind learn . --since 6months

      - name: Review PR changes
        run: diffmind review --staged --fail-on {fail_on}
'''


def install_pre_commit(repo_path: str = ".", fail_on: str = "high") -> str:
    """Install a pre-commit hook.

    Args:
        repo_path: Path to git repository.
        fail_on: Risk level to fail on ("high", "medium", "low").

    Returns:
        Path to installed hook.
    """
    git_dir = os.path.join(os.path.abspath(repo_path), ".git")
    if not os.path.isdir(git_dir):
        raise FileNotFoundError(
            f"Not a git repository: {repo_path}\n"
            f"Expected .git directory at {git_dir}"
        )

    hooks_dir = os.path.join(git_dir, "hooks")
    os.makedirs(hooks_dir, exist_ok=True)

    hook_path = os.path.join(hooks_dir, "pre-commit")

    # Check for existing hook
    if os.path.exists(hook_path):
        with open(hook_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        if "DiffMind" not in content:
            # Backup existing hook
            backup_path = hook_path + ".backup"
            os.rename(hook_path, backup_path)
            print(f"  Existing hook backed up to {backup_path}")

    # Write hook
    hook_content = PRE_COMMIT_TEMPLATE.format(
        fail_on=fail_on,
        fail_on_upper=fail_on.upper(),
    )
    with open(hook_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(hook_content)

    # Make executable
    st = os.stat(hook_path)
    os.chmod(hook_path, st.st_mode | stat.S_IEXEC)

    return hook_path


def generate_github_action(repo_path: str = ".",
                           fail_on: str = "high") -> str:
    """Generate a GitHub Action workflow file.

    Returns:
        Path to generated workflow file.
    """
    workflows_dir = os.path.join(
        os.path.abspath(repo_path), ".github", "workflows"
    )
    os.makedirs(workflows_dir, exist_ok=True)

    action_path = os.path.join(workflows_dir, "diffmind.yml")
    content = GITHUB_ACTION_TEMPLATE.format(fail_on=fail_on)

    with open(action_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)

    return action_path
