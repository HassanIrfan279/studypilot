"""Tutor tool: find the best YouTube explainer videos for a topic (YouTube Data API v3)."""
import requests

import db
from config import YOUTUBE_API_KEY


def find_videos(topic: str, n: int = 3):
    key = f"yt:{topic.lower()}"
    cached = db.cache_get(key)
    if cached is not None:
        return cached
    if not YOUTUBE_API_KEY:
        return []
    try:
        r = requests.get("https://www.googleapis.com/youtube/v3/search", timeout=10, params={
            "part": "snippet", "q": f"{topic} explained", "type": "video", "maxResults": n,
            "safeSearch": "strict", "videoEmbeddable": "true", "relevanceLanguage": "en",
            "key": YOUTUBE_API_KEY})
        r.raise_for_status()
    except Exception:
        return []
    videos = [{"video_id": it["id"]["videoId"], "title": it["snippet"]["title"],
               "channel": it["snippet"]["channelTitle"],
               "thumbnail": it["snippet"]["thumbnails"]["medium"]["url"],
               "url": f"https://www.youtube.com/watch?v={it['id']['videoId']}"}
              for it in r.json().get("items", [])]
    db.cache_set(key, videos)
    return videos
