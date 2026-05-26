"""
pr_review/__main__.py
======================
Entry point: python -m pr_review [options]

Usage:
  # Review staged changes
  python -m pr_review

  # Review a specific commit
  python -m pr_review --commit abc1234

  # Review a diff file
  python -m pr_review --diff path/to/file.diff

  # Run only specific agents
  python -m pr_review --agents logic,security

  # Use local LLM
  python -m pr_review --provider local

  # Compact output (for CI)
  python -m pr_review --format compact

  # Exit code: 1 if any errors found, 0 otherwise
"""

from __future__ import annotations
import sys
import os
import argparse
import logging

# Load .env if present — before any other imports that read env vars
def _load_env():
    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, _, v = line.partition('=')
                    os.environ.setdefault(k.strip(), v.strip())

_load_env()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.llm import Provider
from pr_review.supervisor import review_staged, review_commit, review_diff
from pr_review.renderers.cli import print_full, print_compact


def main():
    parser = argparse.ArgumentParser(
        prog        = "review-pr",
        description = "Multi-agent PR review tool",
    )

    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--staged", action="store_true", default=True,
        help="Review staged git changes (default)"
    )
    source.add_argument(
        "--commit", metavar="SHA",
        help="Review a specific commit"
    )
    source.add_argument(
        "--diff", metavar="FILE",
        help="Review a diff file (use - for stdin)"
    )

    parser.add_argument(
        "--agents", metavar="LIST",
        help="Comma-separated list of agents to run: logic,security,style,tests,docs"
    )
    parser.add_argument(
        "--provider", choices=["anthropic", "local"],
        default=os.getenv("DEFAULT_PROVIDER", "anthropic"),
        help="LLM provider (default: anthropic)"
    )
    parser.add_argument(
        "--format", choices=["full", "compact"],
        default="full",
        help="Output format (default: full)"
    )
    parser.add_argument(
        "--workers", type=int, default=10,
        help="Max concurrent agent threads (default: 10)"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable debug logging"
    )
    parser.add_argument(
        "--caller-dir", metavar="DIR", default=None,
        help=argparse.SUPPRESS   # internal — set by the bash wrapper
    )

    args = parser.parse_args()
    caller_cwd = args.caller_dir or os.getcwd()

    # Logging
    level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(
        level  = level,
        format = "%(levelname)s  %(name)s  %(message)s",
    )

    # Provider
    provider = Provider.ANTHROPIC if args.provider == "anthropic" else Provider.LOCAL

    # Agents filter
    agents = None
    if args.agents:
        agents = [a.strip() for a in args.agents.split(",")]
        valid  = {"logic", "security", "style", "tests", "docs"}
        bad    = set(agents) - valid
        if bad:
            print(f"Unknown agent(s): {bad}. Valid: {valid}", file=sys.stderr)
            sys.exit(2)

    # Get the diff
    try:
        if args.commit:
            result = review_commit(args.commit, provider=provider, agents=agents,
                                   cwd=caller_cwd)
        elif args.diff:
            if args.diff == "-":
                diff_text = sys.stdin.read()
            else:
                with open(args.diff) as f:
                    diff_text = f.read()
            result = review_diff(diff_text, provider=provider, agents=agents,
                                 max_workers=args.workers)
        else:
            result = review_staged(provider=provider, agents=agents,
                                   cwd=caller_cwd)

    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(130)

    # Render
    if args.format == "compact":
        print_compact(result)
    else:
        print_full(result)

    # Exit code: 1 if any blocking errors, 0 otherwise
    sys.exit(1 if result.has_blockers else 0)


if __name__ == "__main__":
    main()
