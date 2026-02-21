import hashlib
import hmac
from datetime import datetime, timezone
from typing import Any

import aiohttp

from .base import IssueInfo, PlatformProvider, PRInfo, RepoInfo


class CodebergProvider(PlatformProvider):
    @property
    def name(self) -> str:
        return "codeberg"

    @property
    def base_url(self) -> str:
        return "https://codeberg.org"

    @property
    def api_base_url(self) -> str:
        return "https://codeberg.org/api/v1"

    @property
    def url_pattern(self) -> str:
        return r"https://codeberg\.org/[\w\-]+/[\w\-]+(?:/(pull|issues)/\d+)?"

    def get_headers(self, token: str | None = None) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"token {token}"
        return headers

    async def fetch_repo(self, repo: str, token: str | None = None) -> RepoInfo | None:
        url = f"{self.api_base_url}/repos/{repo}"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=self.get_headers(token)) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
            except Exception:
                return None

        stargazers = data.get("stars_count", data.get("stargazers_count", 0))

        return RepoInfo(
            full_name=data.get("full_name", repo),
            description=data.get("description"),
            html_url=data.get("html_url", f"{self.base_url}/{repo}"),
            stargazers_count=int(stargazers or 0),
            forks_count=int(data.get("forks_count", 0) or 0),
            open_issues_count=int(data.get("open_issues_count", 0) or 0),
            language=data.get("language"),
            default_branch=data.get("default_branch", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )

    async def fetch_issue(
        self, repo: str, issue_number: str, token: str | None = None
    ) -> IssueInfo | None:
        url = f"{self.api_base_url}/repos/{repo}/issues/{issue_number}"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=self.get_headers(token)) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
            except Exception:
                return None

        labels = self._extract_labels(data.get("labels", []))
        number = data.get("number")
        if number is None:
            number = int(issue_number) if issue_number.isdigit() else 0

        return IssueInfo(
            number=int(number),
            title=data.get("title", ""),
            user_login=(data.get("user") or {}).get("login", ""),
            html_url=data.get("html_url", f"{self.base_url}/{repo}/issues/{issue_number}"),
            state=data.get("state", ""),
            body=data.get("body"),
            labels=labels,
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )

    async def fetch_pr(
        self, repo: str, pr_number: str, token: str | None = None
    ) -> PRInfo | None:
        url = f"{self.api_base_url}/repos/{repo}/pulls/{pr_number}"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=self.get_headers(token)) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
            except Exception:
                return None

        number = data.get("number")
        if number is None:
            number = int(pr_number) if pr_number.isdigit() else 0

        mergeable_state = data.get("mergeable_state")
        if mergeable_state is None:
            mergeable = data.get("mergeable")
            if isinstance(mergeable, bool):
                mergeable_state = "mergeable" if mergeable else "conflicting"

        return PRInfo(
            number=int(number),
            title=data.get("title", ""),
            user_login=(data.get("user") or {}).get("login", ""),
            html_url=data.get("html_url", f"{self.base_url}/{repo}/pull/{pr_number}"),
            state=data.get("state", ""),
            body=data.get("body"),
            head_ref=(data.get("head") or {}).get("ref", ""),
            base_ref=(data.get("base") or {}).get("ref", ""),
            merged=bool(data.get("merged", False)),
            mergeable_state=mergeable_state,
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )

    async def fetch_readme(
        self, repo: str, token: str | None = None
    ) -> dict[str, Any] | None:
        url = f"{self.api_base_url}/repos/{repo}/contents/README.md"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=self.get_headers(token)) as resp:
                    if resp.status != 200:
                        return None
                    return await resp.json()
            except Exception:
                return None

    async def fetch_issues_since(
        self, repo: str, since: str | None, token: str | None = None
    ) -> list[dict[str, Any]]:
        if not since:
            return []

        since_dt = self._parse_iso_datetime(since)
        if not since_dt:
            return []

        url = f"{self.api_base_url}/repos/{repo}/issues"
        params = {
            "state": "all",
            "page": 1,
            "limit": 10,
        }

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    url, params=params, headers=self.get_headers(token)
                ) as resp:
                    if resp.status != 200:
                        return []
                    items = await resp.json()
            except Exception:
                return []

        if not isinstance(items, list):
            return []

        new_items: list[dict[str, Any]] = []
        for item in items:
            created_at = self._parse_iso_datetime(item.get("created_at"))
            if not created_at:
                continue
            if created_at > since_dt:
                new_items.append(item)

        return new_items

    async def fetch_rate_limit(self, token: str | None = None) -> dict[str, Any] | None:
        return None

    def verify_webhook_signature(
        self, payload: bytes, signature: str, secret: bytes
    ) -> bool:
        if not signature:
            return False
        expected = "sha256=" + hmac.new(secret, payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)

    def parse_webhook_event(
        self, event_type: str, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        repo_info = payload.get("repository")
        if not isinstance(repo_info, dict):
            return None

        repo_full_name = repo_info.get("full_name")
        if not repo_full_name:
            return None

        sender = payload.get("sender")
        sender_login = sender.get("login") if isinstance(sender, dict) else None
        action = payload.get("action", "")

        normalized: dict[str, Any] = {
            "event_type": event_type,
            "action": action,
            "repo": repo_full_name,
            "sender": sender_login,
        }

        if event_type == "ping":
            return normalized

        if event_type == "issues":
            normalized["item_type"] = "issue"
            normalized["item"] = payload.get("issue")
            return normalized
        if event_type == "pull_request":
            normalized["item_type"] = "pull_request"
            normalized["item"] = payload.get("pull_request")
            return normalized
        if event_type == "issue_comment":
            normalized["item_type"] = "issue_comment"
            normalized["item"] = {
                "issue": payload.get("issue"),
                "comment": payload.get("comment"),
            }
            return normalized
        if event_type == "commit_comment":
            normalized["item_type"] = "commit_comment"
            normalized["item"] = payload.get("comment")
            return normalized
        if event_type == "discussion":
            normalized["item_type"] = "discussion"
            normalized["item"] = payload.get("discussion")
            return normalized
        if event_type == "discussion_comment":
            normalized["item_type"] = "discussion_comment"
            normalized["item"] = {
                "discussion": payload.get("discussion"),
                "comment": payload.get("comment"),
            }
            return normalized
        if event_type == "fork":
            normalized["item_type"] = "fork"
            normalized["item"] = payload.get("forkee")
            return normalized
        if event_type == "pull_request_review_comment":
            normalized["item_type"] = "pull_request_review_comment"
            normalized["item"] = {
                "pull_request": payload.get("pull_request"),
                "comment": payload.get("comment"),
            }
            return normalized
        if event_type == "pull_request_review":
            normalized["item_type"] = "pull_request_review"
            normalized["item"] = {
                "pull_request": payload.get("pull_request"),
                "review": payload.get("review"),
            }
            return normalized
        if event_type == "pull_request_review_thread":
            normalized["item_type"] = "pull_request_review_thread"
            normalized["item"] = {
                "pull_request": payload.get("pull_request"),
                "thread": payload.get("thread"),
            }
            return normalized
        if event_type == "star":
            normalized["item_type"] = "star"
            normalized["item"] = {"starred_at": payload.get("starred_at")}
            return normalized
        if event_type == "create":
            normalized["item_type"] = "create"
            normalized["item"] = {
                "ref": payload.get("ref"),
                "ref_type": payload.get("ref_type"),
            }
            return normalized

        return None

    @staticmethod
    def _parse_iso_datetime(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            text = value.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(text)
        except Exception:
            return None
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed

    @staticmethod
    def _extract_labels(labels: Any) -> list[str]:
        if not isinstance(labels, list):
            return []

        output: list[str] = []
        for label in labels:
            if isinstance(label, dict):
                name = label.get("name")
                if name:
                    output.append(str(name))
            elif isinstance(label, str):
                output.append(label)
        return output
