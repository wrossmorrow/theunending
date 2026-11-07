from __future__ import annotations

import base64
import time
from typing import Any

import httpx
import jwt

from .settings import PublishSettings

GITHUB_API_BASE_URL = "https://api.github.com"


class GithubPublisher:
    """Publishes draft content to a GitHub repository via a GitHub App installation."""

    def __init__(
        self,
        app_id: str,
        client_id: str,
        installation_id: str,
        private_key: str,
        owner: str,
        repo: str,
        base_branch: str = "main",
    ) -> None:
        self.app_id = app_id
        self.client_id = client_id
        self.installation_id = installation_id
        self.private_key = private_key
        self.owner = owner
        self.repo = repo
        self.base_branch = base_branch

    def _installation_token(self) -> str:
        now = int(time.time())
        jwt_token = jwt.encode(
            {
                "iss": self.app_id,
                "iat": now,
                "exp": now + 60,
                "nbf": now - 10,
                "installation_id": int(self.installation_id),
                "aud": "api.github.com",
            },
            key=self.private_key,
            algorithm="RS256",
        )
        response = httpx.post(
            url=f"{GITHUB_API_BASE_URL}/app/installations/{self.installation_id}/access_tokens",
            headers={
                "accept": "application/vnd.github+json",
                "user-agent": "theunending-publish",
                "authorization": f"Bearer {jwt_token}",
            },
        )
        response.raise_for_status()
        return str(response.json()["token"])

    def _headers(self, token: str) -> dict[str, str]:
        return {
            "authorization": f"Bearer {token}",
            "accept": "application/vnd.github+json",
            "x-github-api-version": "2022-11-28",
            "user-agent": "theunending-publish",
        }

    def create_branch(self, branch: str, token: str, sha: str) -> None:
        response = httpx.post(
            url=f"{GITHUB_API_BASE_URL}/repos/{self.owner}/{self.repo}/git/refs",
            headers=self._headers(token),
            json={"ref": f"refs/heads/{branch}", "sha": sha},
        )
        if response.status_code == 422:
            # the branch already exists, nothing to do
            return
        response.raise_for_status()

    def add_files(self, files: dict[str, str], branch: str, token: str) -> None:
        for path, content in files.items():
            response = httpx.put(
                url=f"{GITHUB_API_BASE_URL}/repos/{self.owner}/{self.repo}/contents/{path.lstrip('/')}",
                headers=self._headers(token),
                json={
                    "message": f"publish draft {self.repo}",
                    "content": base64.b64encode(content.encode("utf-8")).decode(
                        "ascii"
                    ),
                    "branch": branch,
                },
            )
            response.raise_for_status()

    def open_pr(
        self,
        branch: str,
        title: str,
        body: str,
        token: str,
        base: str = "main",
    ) -> str:
        response = httpx.post(
            url=f"{GITHUB_API_BASE_URL}/repos/{self.owner}/{self.repo}/pulls",
            headers=self._headers(token),
            json={
                "title": title,
                "head": branch,
                "base": base,
                "body": body,
            },
        )
        response.raise_for_status()
        return str(response.json()["html_url"])

    def _default_branch_sha(self, token: str, branch: str) -> str:
        response = httpx.get(
            url=f"{GITHUB_API_BASE_URL}/repos/{self.owner}/{self.repo}/git/ref/heads/{branch}",
            headers=self._headers(token),
        )
        response.raise_for_status()
        return str(response.json()["object"]["sha"])

    def create_draft_pr(
        self,
        files: dict[str, str],
        *,
        title: str,
        body: str,
        branch: str,
        base: str = "main",
    ) -> str:
        token = self._installation_token()
        sha = self._default_branch_sha(token, base)
        self.create_branch(branch, token, sha)
        self.add_files(files, branch, token)
        return self.open_pr(branch, title, body, token, base)


def draft_files(
    settings: PublishSettings, draft_manifest: dict[str, Any]
) -> dict[str, str]:
    """Map draft manifest contents to files to add to the draft branch."""

    files: dict[str, str] = {}

    post_draft = draft_manifest.get("post_draft")
    if post_draft:
        files[f"_drafts/{settings.POST_NAME}.md"] = post_draft

    return files
