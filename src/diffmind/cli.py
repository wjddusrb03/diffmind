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


# ── Connect subcommands ────────────────────────────────────────────

@main.group()
def connect():
    """DiffMind Connect - LLM review, GitHub, Slack, Discord integrations.

    \b
    Examples:
        diffmind connect ai-review --staged
        diffmind connect github --pr 42
        diffmind connect slack --test
        diffmind connect init
    """
    pass


@connect.command("init")
@click.option("--path", default=".", help="Repository path")
def connect_init(path):
    """Generate default .diffmind/config.yml configuration."""
    from .connect.config import generate_default_config

    config_path = generate_default_config(path)
    print(f"[OK] Config generated at {config_path}")
    print("  Edit the file to set your API keys and preferences.")


@connect.command("ai-review")
@click.option("--staged", is_flag=True, help="Only review staged changes")
@click.option("--threshold", default=0.75, type=float, help="Similarity threshold")
@click.option("-k", default=3, type=int, help="Max warnings per hunk")
@click.option("--provider", default="claude",
              type=click.Choice(["claude", "openai", "ollama"]),
              help="LLM provider")
@click.option("--model", default="", help="Model name (auto-selected if empty)")
@click.option("--lang", default="en", type=click.Choice(["en", "ko"]),
              help="Output language")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.option("--fail-on", type=click.Choice(["high", "medium", "low"]),
              default=None, help="Exit with code 1 if risk >= level")
@click.option("--path", default=".", help="Repository path")
def ai_review(staged, threshold, k, provider, model, lang, as_json, fail_on, path):
    """AI-powered review: LLM analyzes DiffMind warnings.

    Combines DiffMind's bug pattern detection with LLM analysis
    to provide detailed code review comments with fix suggestions.

    \b
    Examples:
        diffmind connect ai-review --staged
        diffmind connect ai-review --provider openai --lang ko
        diffmind connect ai-review --json --fail-on high
    """
    from .connect.config import load_config
    from .connect.llm import LLMReviewer
    from .display import display_ai_review, display_ai_review_json
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

    if not warnings:
        print("No similar bug patterns found. Skipping AI analysis.")
        return

    # Load config and create LLM reviewer
    config = load_config(path)
    config.llm.provider = provider
    if model:
        config.llm.model = model
    config.llm.language = lang

    try:
        reviewer = LLMReviewer(config=config)
    except Exception as e:
        print(f"[ERROR] Failed to initialize LLM: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Analyzing {len(warnings)} warnings with {provider}...")
    report = reviewer.analyze_all(warnings)

    if as_json:
        print(display_ai_review_json(report))
    else:
        print(display_ai_review(report))

    # Exit code for CI
    if fail_on and report.overall_risk != "CLEAN":
        levels = {"high": 3, "medium": 2, "low": 1}
        fail_level = levels.get(fail_on, 0)
        risk_level = levels.get(report.overall_risk.lower(), 0)
        if risk_level >= fail_level:
            sys.exit(1)


@connect.command("github")
@click.option("--pr", "pr_number", required=True, type=int, help="PR number")
@click.option("--staged", is_flag=True, help="Only review staged changes")
@click.option("--threshold", default=0.75, type=float, help="Similarity threshold")
@click.option("--provider", default="claude",
              type=click.Choice(["claude", "openai", "ollama"]),
              help="LLM provider")
@click.option("--fail-on", default="high",
              type=click.Choice(["high", "medium", "low"]))
@click.option("--path", default=".", help="Repository path")
def github_review(pr_number, staged, threshold, provider, fail_on, path):
    """Post AI review on a GitHub PR.

    \b
    Examples:
        diffmind connect github --pr 42
        diffmind connect github --pr 42 --provider openai
    """
    from .connect.config import load_config
    from .connect.github_bot import GitHubBot
    from .connect.llm import LLMReviewer
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
        threshold=threshold, hunks=current_hunks,
    )

    config = load_config(path)
    config.llm.provider = provider

    try:
        reviewer = LLMReviewer(config=config)
        report = reviewer.analyze_all(warnings)
    except Exception as e:
        print(f"[ERROR] LLM analysis failed: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        bot = GitHubBot(config=config.github)
        url = bot.post_review(pr_number, report)
        print(f"[OK] Review posted: {url}")
    except Exception as e:
        print(f"[ERROR] GitHub posting failed: {e}", file=sys.stderr)
        sys.exit(1)


@connect.command("slack")
@click.option("--test", "test_mode", is_flag=True, help="Send test message")
@click.option("--webhook", default="", help="Slack webhook URL")
@click.option("--path", default=".", help="Repository path")
def slack_notify(test_mode, webhook, path):
    """Send alerts to Slack.

    \b
    Examples:
        diffmind connect slack --test --webhook https://hooks.slack.com/...
        diffmind connect slack --test
    """
    from .connect.config import load_config
    from .connect.slack import SlackNotifier

    config = load_config(path)
    url = webhook or config.slack.webhook_url
    if not url:
        print("[ERROR] Slack webhook URL required. "
              "Use --webhook or set in .diffmind/config.yml", file=sys.stderr)
        sys.exit(1)

    config.slack.webhook_url = url

    try:
        notifier = SlackNotifier(config=config.slack)
        if test_mode:
            ok = notifier.send_test()
            if ok:
                print("[OK] Test message sent to Slack.")
            else:
                print("[ERROR] Failed to send test message.", file=sys.stderr)
                sys.exit(1)
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)


@connect.command("discord")
@click.option("--test", "test_mode", is_flag=True, help="Send test message")
@click.option("--webhook", default="", help="Discord webhook URL")
@click.option("--path", default=".", help="Repository path")
def discord_notify(test_mode, webhook, path):
    """Send alerts to Discord.

    \b
    Examples:
        diffmind connect discord --test --webhook https://discord.com/api/webhooks/...
        diffmind connect discord --test
    """
    from .connect.config import load_config
    from .connect.discord import DiscordNotifier

    config = load_config(path)
    url = webhook or config.discord.webhook_url
    if not url:
        print("[ERROR] Discord webhook URL required. "
              "Use --webhook or set in .diffmind/config.yml", file=sys.stderr)
        sys.exit(1)

    config.discord.webhook_url = url

    try:
        notifier = DiscordNotifier(config=config.discord)
        if test_mode:
            ok = notifier.send_test()
            if ok:
                print("[OK] Test message sent to Discord.")
            else:
                print("[ERROR] Failed to send test message.", file=sys.stderr)
                sys.exit(1)
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
