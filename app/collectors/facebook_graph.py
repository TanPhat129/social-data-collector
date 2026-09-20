"""Collector for Facebook Graph API sources the configured token may access."""
from datetime import datetime
import json
from urllib.parse import urlencode
from urllib.request import urlopen

from app.collectors.base import BaseCollector
from app.schemas import RawPost, Source


class FacebookGraphCollector(BaseCollector):
    def __init__(self, access_token: str, api_version: str = "v22.0", max_posts: int = 100):
        if not access_token:
            raise ValueError("FACEBOOK_ACCESS_TOKEN is required for FacebookGraphCollector")
        self.access_token, self.api_version = access_token, api_version
        self.max_posts = max_posts

    def _request(self, url: str) -> dict:
        separator = "&" if "?" in url else "?"
        with urlopen(f"{url}{separator}{urlencode({'access_token': self.access_token})}", timeout=30) as response:
            payload = json.load(response)
        if "error" in payload:
            raise RuntimeError(f"Facebook Graph API error: {payload['error'].get('message', payload['error'])}")
        return payload

    @staticmethod
    def _timestamp(value: str | None) -> datetime | None:
        return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None

    def collect(self, source: Source) -> list[RawPost]:
        if source.platform.lower() != "facebook":
            return []
        object_id = source.external_id or source.id
        fields = "id,message,created_time,permalink_url"
        url = f"https://graph.facebook.com/{self.api_version}/{object_id}/feed?{urlencode({'fields': fields, 'limit': min(self.max_posts, 100)})}"
        posts: list[RawPost] = []
        while url and len(posts) < self.max_posts:
            payload = self._request(url)
            for item in payload.get("data", []):
                content = item.get("message", "").strip()
                if content:
                    posts.append(RawPost(post_id=item["id"], source=source, content=content,
                        posted_at=self._timestamp(item.get("created_time")), post_url=item.get("permalink_url")))
            url = payload.get("paging", {}).get("next")
        return posts[:self.max_posts]
