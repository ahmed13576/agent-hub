"""
Agent Hub - GitHub Scraper

Scrapes GitHub repositories using the Search API and direct repo tracking.
Outputs items in the unified schema for downstream processing.
"""

import logging
from typing import Optional

from src.config import config
from src.clients.http_client import HttpClient
from src.scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"


class GitHubScraper(BaseScraper):
    """
    Scrapes GitHub repositories via:
    1. Search API queries (from sources.yaml github.search_queries)
    2. Direct repo tracking (from sources.yaml github.tracked_repos)
    """

    def __init__(self, http_client: Optional[HttpClient] = None):
        self._client = http_client or HttpClient(use_proxy=False)
        self._token = config.github_token
        self._sources = config.sources.get("github", {})

    def _auth_headers(self) -> dict:
        """Build GitHub API auth headers."""
        headers = {"Accept": "application/vnd.github.v3+json"}
        if self._token:
            headers["Authorization"] = f"token {self._token}"
        return headers

    def scrape(self) -> list[dict]:
        """
        Run all GitHub scraping tasks and return unified schema items.

        Returns:
            List of item dicts.
        """
        items = []
        seen_repos = set()  # Track full_name for de-duplication

        # 1. Search queries
        search_queries = self._sources.get("search_queries", [])
        for query in search_queries:
            try:
                results = self._search_repos(query)
                for repo in results:
                    full_name = repo.get("full_name", "")
                    if full_name in seen_repos:
                        continue
                    seen_repos.add(full_name)
                    items.append(self._repo_to_item(repo))
            except Exception as e:
                logger.warning(f"GitHub search failed for query '{query}': {e}")

        # 2. Tracked repos
        tracked_repos = self._sources.get("tracked_repos", [])
        for repo_path in tracked_repos:
            if repo_path in seen_repos:
                continue
            try:
                repo = self._fetch_repo(repo_path)
                if repo:
                    seen_repos.add(repo_path)
                    items.append(self._repo_to_item(repo))
            except Exception as e:
                logger.warning(f"GitHub fetch failed for repo '{repo_path}': {e}")

        logger.info(f"GitHub scraper: {len(items)} repos collected ({len(seen_repos)} unique)")
        return items

    def _search_repos(self, query: str) -> list[dict]:
        """
        Search GitHub repositories by query string.

        Args:
            query: Search query string.

        Returns:
            List of repo dicts from the API response.
        """
        url = f"{GITHUB_API_BASE}/search/repositories"
        params = {
            "q": query,
            "sort": "updated",
            "order": "desc",
            "per_page": 30,
        }

        try:
            response = self._client.get(url, headers=self._auth_headers(), params=params)
            data = response.json()
            repos = data.get("items", [])
            logger.debug(f"GitHub search '{query}': {len(repos)} results")
            return repos
        except Exception as e:
            logger.warning(f"GitHub search API error for '{query}': {e}")
            return []

    def _fetch_repo(self, repo_path: str) -> Optional[dict]:
        """
        Fetch a specific repository by owner/repo path.

        Args:
            repo_path: Repository path in 'owner/repo' format.

        Returns:
            Repo dict or None on failure.
        """
        url = f"{GITHUB_API_BASE}/repos/{repo_path}"
        try:
            response = self._client.get(url, headers=self._auth_headers())
            return response.json()
        except Exception as e:
            logger.warning(f"GitHub repo fetch error for '{repo_path}': {e}")
            return None

    def _repo_to_item(self, repo: dict) -> dict:
        """
        Convert a GitHub API repo dict to our unified item schema.

        Args:
            repo: Raw repo dict from GitHub API.

        Returns:
            Unified schema item dict.
        """
        full_name = repo.get("full_name", "unknown/unknown")
        description = repo.get("description") or ""
        topics = repo.get("topics", [])
        html_url = repo.get("html_url", f"https://github.com/{full_name}")

        raw_content = f"{full_name}: {description}"
        if topics:
            raw_content += " | Topics: " + ", ".join(topics)

        readme_snippet = repo.get("readme", "")
        if readme_snippet:
            raw_content += f" | README: {readme_snippet}"

        return self._make_item(
            source="github",
            title=full_name,
            url=html_url,
            description=description,
            author=repo.get("owner", {}).get("login", "unknown"),
            metadata={
                "stars": repo.get("stargazers_count", 0),
                "forks": repo.get("forks_count", 0),
                "language": repo.get("language"),
                "topics": topics,
                "updated_at": repo.get("updated_at"),
                "created_at": repo.get("created_at"),
                "open_issues": repo.get("open_issues_count", 0),
                "watchers": repo.get("watchers_count", 0),
                "license": (repo.get("license") or {}).get("spdx_id"),
            },
            tags=topics,
            raw_content=raw_content,
        )
