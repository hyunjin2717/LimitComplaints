#!/usr/bin/env python3
"""
Collect and classify Reddit posts about AI rate limit complaints.

Tracks posts complaining about rate limits for Claude, Gemini, and Codex.
No LLM is used — classification is done with regex patterns and a scoring system.
Data is fetched from the Arctic Shift API (no Reddit API key required).
"""

import os
import re
import json
import time
import sys
from datetime import datetime, timedelta, timezone

import requests

# ── Paths ─────────────────────────────────────────────────────────────────────

ROOT = os.path.join(os.path.dirname(__file__), "..")
DATA_FILE = os.path.join(ROOT, "data", "complaints.json")

# ── Arctic Shift API ──────────────────────────────────────────────────────────

ARCTIC_SHIFT_BASE = "https://arctic-shift.photon-reddit.com/api"
ARCTIC_SHIFT_HEADERS = {
    "User-Agent": "RateLimitComplaintsTracker/1.0 (open-source monitoring project)"
}

# ── Reddit targets ────────────────────────────────────────────────────────────

SUBREDDITS = [
    "ClaudeAI",
    "GoogleGemini",
    "OpenAI",
    "ChatGPT",
    "LocalLLaMA",
    "artificial",
    "singularity",
    "MachineLearning",
    "programming",
    "github",
]

SEARCH_QUERIES = [
    "rate limit",
    "quota exceeded",
    "too many requests",
    "throttled",
    "usage limit",
]

# ── Rate-limit detection patterns ─────────────────────────────────────────────

RATE_LIMIT_PATTERNS = [
    r"rate[\s\-]?limit",
    r"\b429\b",
    r"too\s+many\s+requests",
    r"\bquota\b",
    r"throttl(?:ed|ing|e|s)?",
    r"usage[\s\-](?:limit|cap|quota)",
    r"(?:daily|monthly|hourly|api|token|request)[\s\-]limit",
    r"(?:limit|quota|cap)[\s\-](?:reached|exceeded|hit|maxed)",
    r"hit[\s\-]+(?:my|the|a|their)[\s\-]+(?:limit|quota|cap|wall)",
    r"reached[\s\-]+(?:my|the|a|their)[\s\-]+(?:limit|quota|cap)",
    r"(?:tokens?|requests?)[\s\-]per[\s\-](?:minute|hour|day)",
    r"\btpm\b",
    r"\brpm\b",
    r"cool[\s\-]?down",
    r"rate[\s\-]cap",
    r"usage[\s\-]cap",
    r"out\s+of\s+credits?",
    r"credits?\s+(?:ran\s+out|used\s+up|exhausted|depleted)",
    r"free[\s\-]tier[\s\-\w]*(?:limit|restrict|cap)",
    r"context[\s\-]window[\s\-\w]*(?:limit|exceed|hit)",
    r"maxed?\s+out",
    r"over\s+(?:the\s+)?limit",
]

# ── Negation patterns ─────────────────────────────────────────────────────────

NEGATION_PATTERNS = [
    r"no\s+rate\s+limit",
    r"without\s+(?:any\s+)?rate\s+limit",
    r"don'?t\s+have\s+(?:a\s+)?rate\s+limit",
    r"doesn'?t\s+have\s+(?:a\s+)?rate\s+limit",
    r"bypass(?:ing)?\s+(?:the\s+)?rate\s+limit",
    r"avoid(?:ing)?\s+(?:the\s+)?rate\s+limit",
    r"circumvent(?:ing)?\s+(?:the\s+)?rate\s+limit",
    r"workaround\s+(?:for\s+)?(?:the\s+)?rate\s+limit",
    r"how\s+to\s+(?:increase|get\s+around|avoid|bypass|work\s+around)\s+(?:the\s+)?rate\s+limit",
    r"(?:increase|raise|lift)\s+(?:my\s+|the\s+)?rate\s+limit",
    r"no\s+longer\s+(?:rate\s+)?limited",
]

# ── Complaint language ────────────────────────────────────────────────────────

COMPLAINT_STRONG = [
    "frustrated", "frustrating", "frustration",
    "annoying", "annoyed",
    "ridiculous", "absurd", "outrageous",
    "terrible", "awful", "horrible",
    "unacceptable", "inexcusable",
    "hate ", "useless", "worthless",
    "broken", "unusable", "pathetic",
    "embarrassing", "disgrace", "trash", "garbage",
    "ugh", "wtf", "wth", "smh", "ffs",
    "joke", "pointless",
]

COMPLAINT_MODERATE = [
    "can't use", "cannot use",
    "can't access", "cannot access",
    "won't work", "doesn't work",
    "not working", "stopped working",
    "keeps hitting", "keeps getting", "keeps blocking",
    "every time i", "every single time",
    "constantly", "always getting",
    "getting blocked", "getting throttled", "getting rate",
    "blocking me", "stopping me", "ruining",
    "severely limited", "barely usable",
]

COMPLAINT_MILD = [
    "problem", "issue", "stuck",
    "blocked", "restricted", "limited",
    "error ", "fail", "unable",
    "disappointed", "unfortunate",
]

# ── Model detection patterns ──────────────────────────────────────────────────

MODEL_PATTERNS = {
    "claude": [
        r"\bclaude\b",
        r"\banthropics?\b",
        r"\bhaiku\b",
        r"\bsonnet\b",
        r"\bopus\b",
        r"claude[\s\-]?(?:3|4|3\.5|3\.7|instant)",
    ],
    "gemini": [
        r"\bgemini\b",
        r"\bgoogle[\s\-]?ai\b",
        r"\bai[\s\-]?studio\b",
        r"\baistudio\b",
        r"\bvertex[\s\-]?ai\b",
        r"gemini[\s\-]?(?:pro|flash|ultra|nano|1\.5|2\.0|2)",
        r"\bbard\b",
    ],
    "codex": [
        r"\bcodex\b",
        r"openai[\s\-]?codex",
        r"codex[\s\-](?:cli|agent)",
    ],
}

SUBREDDIT_MODEL_MAP = {
    "claudeai": ["claude"],
    "googlegemini": ["gemini"],
    "bard": ["gemini"],
}

# ── Classification functions ──────────────────────────────────────────────────


def _has_rate_limit(text: str) -> bool:
    return any(re.search(p, text) for p in RATE_LIMIT_PATTERNS)


def _is_negation_dominant(text: str) -> bool:
    return any(re.search(p, text) for p in NEGATION_PATTERNS)


def compute_complaint_score(title: str, body: str) -> int:
    combined = (title + " " + body).lower()
    title_l = title.lower()

    if not _has_rate_limit(combined):
        return 0

    if _is_negation_dominant(combined):
        if not any(w in combined for w in COMPLAINT_STRONG):
            return 0

    score = 0

    if _has_rate_limit(title_l):
        score += 3

    if any(w in combined for w in COMPLAINT_STRONG):
        score += 3

    if any(p in combined for p in COMPLAINT_MODERATE):
        score += 2

    if any(w in combined for w in COMPLAINT_MILD):
        score += 1

    if "?" in title_l and _has_rate_limit(title_l):
        score += 1
    if "!" in title:
        score += 1

    return score


def detect_models(title: str, body: str, subreddit: str) -> list:
    combined = (title + " " + body).lower()
    models = []

    for model, patterns in MODEL_PATTERNS.items():
        if any(re.search(p, combined) for p in patterns):
            models.append(model)

    if not models:
        models = SUBREDDIT_MODEL_MAP.get(subreddit.lower(), [])

    return models


def classify_post(title: str, body: str, subreddit: str):
    score = compute_complaint_score(title, body)
    if score < 2:
        return None

    models = detect_models(title, body, subreddit)
    if not models:
        return None

    return models, score


# ── Arctic Shift API helpers ──────────────────────────────────────────────────


def fetch_subreddit_posts(
    subreddit_name: str,
    days_back: int,
    limit_per_query: int,
) -> dict:
    """
    Search a subreddit for rate-limit posts via Arctic Shift API.
    Returns raw post dicts keyed by post ID.

    Arctic Shift API docs: https://arctic-shift.photon-reddit.com/api
    No API key required.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    after_ts = int(cutoff.timestamp())
    results = {}

    for query in SEARCH_QUERIES:
        # Arctic Shift paginates via `after` timestamp of the oldest post seen
        page_after = None
        fetched = 0

        while fetched < limit_per_query:
            batch = min(100, limit_per_query - fetched)
            params = {
                "subreddit": subreddit_name,
                "q": query,
                "after": str(after_ts),
                "limit": str(batch),
                "sort": "desc",
            }
            if page_after is not None:
                params["before"] = str(page_after)

            try:
                resp = requests.get(
                    f"{ARCTIC_SHIFT_BASE}/posts/search",
                    params=params,
                    headers=ARCTIC_SHIFT_HEADERS,
                    timeout=30,
                )
                resp.raise_for_status()
                posts = resp.json().get("data", [])
            except requests.RequestException as exc:
                print(
                    f"  [WARN] Arctic Shift error in r/{subreddit_name} "
                    f"q={query!r}: {exc}",
                    file=sys.stderr,
                )
                break

            if not posts:
                break

            for post in posts:
                post_id = post.get("id")
                if not post_id or post_id in results:
                    continue
                results[post_id] = {
                    "title": post.get("title", ""),
                    "body": (post.get("selftext") or "")[:2000],
                    "subreddit": post.get("subreddit", subreddit_name),
                    "created_utc": int(post.get("created_utc", 0)),
                    "score": post.get("score", 0),
                    "url": f"https://reddit.com{post.get('permalink', '')}",
                }

            fetched += len(posts)

            # If we got fewer than requested, there are no more pages
            if len(posts) < batch:
                break

            # Paginate: use created_utc of the oldest post in this batch
            oldest_ts = min(int(p.get("created_utc", 0)) for p in posts)
            if oldest_ts <= after_ts:
                break
            page_after = oldest_ts

            # Polite delay between paginated requests
            time.sleep(1.0)

        # Delay between queries for the same subreddit
        time.sleep(1.0)

    return results


# ── Data persistence ──────────────────────────────────────────────────────────


def load_data() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {}
    data.setdefault("metadata", {})
    data.setdefault("posts", {})
    return data


def save_data(data: dict) -> None:
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    data = load_data()
    existing = data["posts"]

    is_initial = len(existing) == 0
    days_back = 90 if is_initial else 8
    limit_per_query = 500 if is_initial else 100

    print(
        f"Mode: {'initial 90-day' if is_initial else 'daily update'} | "
        f"days_back={days_back} | limit_per_query={limit_per_query}"
    )
    print("Data source: Arctic Shift API (no Reddit API key required)")

    new_posts_seen = 0
    new_complaints = 0

    for sub_name in SUBREDDITS:
        print(f"Scanning r/{sub_name} …", flush=True)
        raw = fetch_subreddit_posts(sub_name, days_back, limit_per_query)
        print(f"  {len(raw)} candidate posts found")

        for post_id, post in raw.items():
            if post_id in existing:
                continue

            new_posts_seen += 1
            result = classify_post(post["title"], post["body"], post["subreddit"])

            if result is None:
                continue

            models, score = result
            new_complaints += 1

            existing[post_id] = {
                "title": post["title"],
                "subreddit": post["subreddit"],
                "created_utc": post["created_utc"],
                "score": post["score"],
                "url": post["url"],
                "models": models,
                "complaint_score": score,
                "fetched_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            }

    data["metadata"]["last_updated"] = datetime.now(timezone.utc).isoformat()
    data["metadata"]["total_posts_analyzed"] = (
        data["metadata"].get("total_posts_analyzed", 0) + new_posts_seen
    )
    data["metadata"]["total_complaints"] = len(existing)

    save_data(data)

    print(
        f"\nDone. New posts scanned: {new_posts_seen} | "
        f"New complaints added: {new_complaints} | "
        f"DB total: {len(existing)}"
    )


if __name__ == "__main__":
    main()
