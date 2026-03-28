"""CLI interface for DiffMind."""

from __future__ import annotations

import sys

import click

from . import __version__


@click.group()
@click.version_option(__version__, prog_name="diffmind")
def main():
    """DiffMind - AI Code Review Memory.

    Learns from your team's bug history and warns when similar
    patterns appear in new code changes.
    """
    pass


@main.command()
@click.argument("path", default=".")
@click.option("--since", default=None, help="Learn from commits after date (e.g. 2024-01-01)")
@click.option("--until", default=None, help="Learn from commits before date")
@click.option("--branch", default="HEAD", help="Git branch to analyze")
@click.option("--bugfix-only", is_flag=True, help="Only learn from bugfix commits")
@click.option("--model", default=None, help="Embedding model name")
@click.option("--bits", default=3, type=click.IntRange(2, 4), help="Compression bits (2-4)")
@click.option("--update", is_flag=True, help="Incremental learn (only new commits)")
def learn(path, since, until, branch, bugfix_only, model, bits, update):
    """Learn from git repository history.

    Parses commit diffs, generates embeddings, and builds a compressed
    index for fast similarity search.

    \b
    Examples:
        diffmind learn .
        diffmind learn . --since 2024-01-01
        diffmind learn . --bugfix-only --bits 4
        diffmind learn --update
    """
    from .indexer import DEFAULT_MODEL, learn as do_learn, incremental_learn
    from .storage import index_exists, load_index, save_index

    model_name = model or DEFAULT_MODEL

    try:
        if update and index_exists(path):
            idx = load_index(path)
            idx = incremental_learn(idx, path, model_name=model_name)
        else:
            idx = do_learn(
                repo_path=path,
                model_name=model_name,
                bits=bits,
                since=since,
                until=until,
                branch=branch,
                bugfix_only=bugfix_only,
            )

        saved_path = save_index(idx, path)
        print(f"\n[OK] Index saved to {saved_path}")
        print(f"  {len(idx.hunks)} diff hunks indexed")
        print(f"  {idx.total_commits} commits ({idx.bugfix_commits} bugfixes)")

    except RuntimeError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)


@main.command()
@click.option("--staged", is_flag=True, help="Only review staged changes")
@click.option("--threshold", default=0.75, type=float, help="Similarity threshold (0-1)")
@click.option("-k", default=3, type=int, help="Max warnings per hunk")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.option("--fail-on", type=click.Choice(["high", "medium", "low"]),
              default=None, help="Exit with code 1 if risk >= level")
@click.option("--path", default=".", help="Repository path")
def review(staged, threshold, k, as_json, fail_on, path):
    """Review current changes against learned bug patterns.

    Compares your current diff (staged or unstaged) against past bug
    fixes to find similar patterns.

    \b
    Examples:
        diffmind review
        diffmind review --staged
        diffmind review --staged --fail-on high
        diffmind review --threshold 0.8 --json
    """
    from .display import display_review_report
    from .parser import parse_current_diff
    from .reviewer import review as do_review
    from .storage import load_index

    try:
        index = load_index(path)
    except FileNotFoundError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    current_hunks = parse_current_diff(path, staged=staged)
    if not current_hunks:
        print("No changes to review.")
        return

    warnings = do_review(
        index, repo_path=path, staged=staged,
        threshold=threshold, top_k=k, hunks=current_hunks,
    )

    report = display_review_report(warnings, len(current_hunks), as_json=as_json)
    print(report)

    # Exit code for CI
    if fail_on and warnings:
        levels = {"high": 3, "medium": 2, "low": 1}
        fail_level = levels.get(fail_on, 0)
        max_risk = max(
            levels.get(w.risk_level.lower(), 0) for w in warnings
        )
        if max_risk >= fail_level:
            sys.exit(1)


@main.command()
@click.argument("query")
@click.option("-k", default=5, type=int, help="Number of results")
@click.option("--file", "file_path", default=None, help="Filter by file path")
@click.option("--author", default=None, help="Filter by author")
@click.option("--lang", default=None, help="Filter by language")
@click.option("--bugfix-only", is_flag=True, help="Only bugfix commits")
@click.option("--path", default=".", help="Repository path")
def search(query, k, file_path, author, lang, bugfix_only, path):
    """Semantic search over past diff history.

    Search your codebase history using natural language queries.

    \b
    Examples:
        diffmind search "null check missing"
        diffmind search "authentication error" --lang python
        diffmind search "API timeout" --author "Kim" --bugfix-only
    """
    from .display import display_search_results
    from .searcher import search as do_search
    from .storage import load_index

    try:
        index = load_index(path)
    except FileNotFoundError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    results = do_search(
        query, index, k=k,
        file_path=file_path,
        author=author,
        language=lang,
        bugfix_only=bugfix_only,
    )

    output = display_search_results(results)
    print(output)


@main.command()
@click.option("--path", default=".", help="Repository path")
def stats(path):
    """Show index statistics.

    Displays summary of learned patterns, top bugfix files,
    and contributor statistics.
    """
    from .display import display_stats
    from .storage import load_index

    try:
        index = load_index(path)
    except FileNotFoundError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    output = display_stats(index)
    print(output)


@main.command()
@click.option("--pre-commit", is_flag=True, help="Install pre-commit hook")
@click.option("--github-action", is_flag=True, help="Generate GitHub Action workflow")
@click.option("--fail-on", default="high",
              type=click.Choice(["high", "medium", "low"]),
              help="Risk level to fail on")
@click.option("--path", default=".", help="Repository path")
def install(pre_commit, github_action, fail_on, path):
    """Install automation hooks.

    \b
    Examples:
        diffmind install --pre-commit
        diffmind install --github-action
        diffmind install --pre-commit --fail-on medium
    """
    from .hooks import generate_github_action, install_pre_commit

    if not pre_commit and not github_action:
        print("Specify --pre-commit and/or --github-action")
        return

    if pre_commit:
        try:
            hook_path = install_pre_commit(path, fail_on=fail_on)
            print(f"[OK] Pre-commit hook installed at {hook_path}")
        except FileNotFoundError as e:
            print(f"[ERROR] {e}", file=sys.stderr)

    if github_action:
        action_path = generate_github_action(path, fail_on=fail_on)
        print(f"[OK] GitHub Action generated at {action_path}")


if __name__ == "__main__":
    main()
