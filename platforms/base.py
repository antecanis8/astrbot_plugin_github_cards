"""Base classes and data models for platform abstraction."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class RepoInfo:
    """Repository information."""

    full_name: str
    description: str | None
    html_url: str
    stargazers_count: int
    forks_count: int
    open_issues_count: int
    language: str | None
    default_branch: str
    created_at: str
    updated_at: str


@dataclass
class IssueInfo:
    """Issue information."""

    number: int
    title: str
    user_login: str
    html_url: str
    state: str
    body: str | None
    labels: list[str]
    created_at: str
    updated_at: str


@dataclass
class PRInfo:
    """Pull Request information."""

    number: int
    title: str
    user_login: str
    html_url: str
    state: str
    body: str | None
    head_ref: str
    base_ref: str
    merged: bool
    mergeable_state: str | None
    created_at: str
    updated_at: str


class PlatformProvider(ABC):
    """Abstract base class for platform providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Platform name (e.g., 'github', 'codeberg')."""
        ...

    @property
    @abstractmethod
    def base_url(self) -> str:
        """Base URL for the platform (e.g., 'https://github.com')."""
        ...

    @property
    @abstractmethod
    def api_base_url(self) -> str:
        """API base URL (e.g., 'https://api.github.com')."""
        ...

    @property
    @abstractmethod
    def url_pattern(self) -> str:
        """Regex pattern to match repository URLs."""
        ...

    @abstractmethod
    def get_headers(self, token: str | None = None) -> dict[str, str]:
        """Get HTTP headers for API requests.

        Args:
            token: Optional API token for authentication.

        Returns:
            Dictionary of HTTP headers.
        """
        ...

    @abstractmethod
    async def fetch_repo(self, repo: str, token: str | None = None) -> RepoInfo | None:
        """Fetch repository information.

        Args:
            repo: Repository in 'owner/name' format.
            token: Optional API token.

        Returns:
            RepoInfo or None if not found.
        """
        ...

    @abstractmethod
    async def fetch_issue(
        self, repo: str, issue_number: str, token: str | None = None
    ) -> IssueInfo | None:
        """Fetch issue information.

        Args:
            repo: Repository in 'owner/name' format.
            issue_number: Issue number.
            token: Optional API token.

        Returns:
            IssueInfo or None if not found.
        """
        ...

    @abstractmethod
    async def fetch_pr(
        self, repo: str, pr_number: str, token: str | None = None
    ) -> PRInfo | None:
        """Fetch pull request information.

        Args:
            repo: Repository in 'owner/name' format.
            pr_number: PR number.
            token: Optional API token.

        Returns:
            PRInfo or None if not found.
        """
        ...

    @abstractmethod
    async def fetch_readme(
        self, repo: str, token: str | None = None
    ) -> dict[str, Any] | None:
        """Fetch repository README.

        Args:
            repo: Repository in 'owner/name' format.
            token: Optional API token.

        Returns:
            README data dict or None if not found.
        """
        ...

    @abstractmethod
    async def fetch_issues_since(
        self, repo: str, since: str | None, token: str | None = None
    ) -> list[dict[str, Any]]:
        """Fetch issues created since a given timestamp.

        Args:
            repo: Repository in 'owner/name' format.
            since: ISO timestamp or None for first fetch.
            token: Optional API token.

        Returns:
            List of issue/PR data dicts.
        """
        ...

    @abstractmethod
    async def fetch_rate_limit(
        self, token: str | None = None
    ) -> dict[str, Any] | None:
        """Fetch API rate limit information.

        Args:
            token: Optional API token.

        Returns:
            Rate limit data dict or None.
        """
        ...

    @abstractmethod
    def verify_webhook_signature(
        self, payload: bytes, signature: str, secret: bytes
    ) -> bool:
        """Verify webhook signature.

        Args:
            payload: Raw request body.
            signature: Signature header value.
            secret: Webhook secret.

        Returns:
            True if signature is valid.
        """
        ...

    @abstractmethod
    def parse_webhook_event(
        self, event_type: str, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Parse webhook event payload.

        Args:
            event_type: Event type header value.
            payload: Parsed JSON payload.

        Returns:
            Normalized event data or None if unsupported.
        """
        ...
