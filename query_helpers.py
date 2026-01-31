from __future__ import annotations

import re
from typing import Any, Awaitable, Callable, Literal

try:
    from . import formatters
except ImportError:  # pragma: no cover - fallback for direct module import
    import formatters

PlatformName = Literal["github", "codeberg"]
FetchFunc = Callable[[str, str], Awaitable[dict[str, Any] | None]]

_ISSUE_REF_RE = re.compile(r"^([\w\-]+/[\w\-]+)(?:#|\s+)(\d+)$")
_SLASH_REF_RE = re.compile(r"^([\w\-]+/[\w\-]+)/(\d+)$")


def parse_repo_number(reference: str) -> tuple[str | None, str | None]:
    """Parse a repo reference like 'owner/repo#123', 'owner/repo 123', or 'owner/repo/123'.

    Returns (repo, number) or (None, None) if not matched.
    """
    value = (reference or "").strip()
    if not value:
        return None, None

    match = _ISSUE_REF_RE.match(value)
    if match:
        return match.group(1), match.group(2)

    match = _SLASH_REF_RE.match(value)
    if match:
        return match.group(1), match.group(2)

    return None, None


async def resolve_issue_or_pr_details(
    *,
    platform: PlatformName,
    repo: str,
    number: str,
    fetch_issue: FetchFunc,
    fetch_pr: FetchFunc,
) -> str | None:
    """Fetch and format Issue/PR details.

    Tries issue first; if not found, falls back to PR.
    Returns formatted message text, or None if neither exists.
    """
    issue_data = await fetch_issue(repo, number)
    if issue_data:
        # Some platforms (or APIs) represent PRs as a special kind of issue.
        # For the quick command, treat this as PR and show PR details directly.
        if "pull_request" in issue_data:
            pr_data = await fetch_pr(repo, number)
            if pr_data:
                return formatters.format_pr_details(repo, pr_data, platform=platform)
        return formatters.format_issue_details(repo, issue_data, platform=platform)

    pr_data = await fetch_pr(repo, number)
    if pr_data:
        return formatters.format_pr_details(repo, pr_data, platform=platform)

    return None
