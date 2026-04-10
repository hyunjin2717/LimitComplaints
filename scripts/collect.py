#!/usr/bin/env python3
"""
Collect and classify Reddit posts about AI rate limit complaints.

Tracks posts complaining about rate limits for Claude, Gemini, and Codex.
No LLM is used — classification is done with regex patterns and a scoring system.
"""

import os
import re
import json
import time
import sys
from datetime import datetime, timedelta, timezone

import praw
from praw.exceptions import PRAWException

# ── Paths ─────────────────────────────────────────────────────────────────────

ROOT = os.path.join(os.path.dirname(__file__), "..")
DATA_FILE = os.path.join(ROOT, "data", "complaints.json")

# ── Reddit targets ────────────────────────────────────────────────────────────

# Subreddits most likely to contain rate-limit complaints for these three models
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

# Search queries that reliably surface rate-limit posts
SEARCH_QUERIES = [
    '"rate limit"',
    '"quota exceeded"',
    '"too many requests"',
    '"throttled"',
    '"usage limit"',
]

# ── Rate-limit detection patterns ─────────────────────────────────────────────
# These regex patterns match the many ways users describe hitting rate limits.

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
# Posts that discuss rate limits without complaining (e.g. "how to bypass")
# are filtered out unless they also contain strong complaint language.

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
# Ordered by severity; scoring stops early once a tier matches.

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

# Fallback: if no model is found in text, infer from subreddit name
SUBREDDIT_MODEL_MAP = {
    "claudeai": ["claude"],
    "googlegemini": ["gemini"],
    "bard": ["gemini"],
}

# ── Classification functions ──────────────────────────────────────────────────


def _has_rate_limit(text: str) -> bool:
    """Return True if text contains any rate-limit related pattern."""
    return any(re.search(p, text) for p in RATE_LIMIT_PATTERNS)


def _is_negation_dominant(text: str) -> bool:
    """Return True if the post is primarily about NOT having or bypassing limits."""
    return any(re.search(p, text) for p in NEGATION_PATTERNS)


def compute_complaint_score(title: str, body: str) -> int:
    """
    Compute a complaint score for a post.

    Scoring rules:
      +3  rate limit mentioned in the title (high-signal)
      +3  strong complaint language present  (frustrated, broken, wtf…)
      +2  moderate complaint language        (can't use, stopped working…)
      +1  mild complaint language            (problem, issue, stuck…)
      +1  question mark + rate limit in title (frustrated question)
      +1  exclamation mark in title (emotional tone)

    Returns 0 if the post contains no rate-limit mention at all.
    Posts scoring < 2 are considered non-complaints (informational, neutral).
    """
    combined = (title + " " + body).lower()
    title_l = title.lower()

    # Gate: must mention rate limiting at all
    if not _has_rate_limit(combined):
        return 0

    # Negation filter: "no rate limits here" style posts
    if _is_negation_dominant(combined):
        # Still count if there's clear complaint language despite negation context
        if not any(w in combined for w in COMPLAINT_STRONG):
            return 0

    score = 0

    # Rate limit in title is a strong primary signal
    if _has_rate_limit(title_l):
        score += 3

    # Complaint language tiers (each tier checked independently)
    if any(w in combined for w in COMPLAINT_STRONG):
        score += 3

    if any(p in combined for p in COMPLAINT_MODERATE):
        score += 2

    if any(w in combined for w in COMPLAINT_MILD):
        score += 1

    # Emotional punctuation in title
    if "?" in title_l and _has_rate_limit(title_l):
        score += 1
    if "!" in title:
        score += 1

    return score


def detect_models(title: str, body: str, subreddit: str) -> list:
    """
    Return list of model names (from MODEL_PATTERNS keys) mentioned in the post.
    Falls back to SUBREDDIT_MODEL_MAP when no model keyword is found.
    """
    combined = (title + " " + body).lower()
    models = []

    for model, patterns in MODEL_PATTERNS.items():
        if any(re.search(p, combined) for p in patterns):
            models.append(model)

    if not models:
        models = SUBREDDIT_MODEL_MAP.get(subreddit.lower(), [])

    return models


def classify_post(title: str, body: str, subreddit: str):
    """
    Returns (models: list, score: int) if this is a rate-limit complaint, else None.

    A post qualifies when:
      1. complaint_score >= 2  (is actually complaining, not just asking)
      2. at least one model can be identified
    """
    score = compute_complaint_score(title, body)
    if score < 2:
        return None

    models = detect_models(title, body, subreddit)
    if not models:
        return None

    return models, score


# ── Reddit helpers ─────────────────────────────────────────────────────────────


def make_reddit() -> praw.Reddit:
    return praw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"],
        client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        user_agent="RateLimitComplaintsTracker/1.0 (open-source monitoring bot)",
    )


def fetch_subreddit_posts(
    reddit: praw.Reddit,
    subreddit_name: str,
    days_back: int,
    limit_per_query: int,
) -> dict:
    """
    Search a subreddit for rate-limit posts and return raw post dicts keyed by ID.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    # Reddit's time_filter: 'week' covers ~7 days, 'year' covers up to 1 year
    time_filter = "year" if days_back > 30 else "week"
    results = {}

    for query in SEARCH_QUERIES:
        try:
            sub = reddit.subreddit(subreddit_name)
            for post in sub.search(
                query,
                time_filter=time_filter,
                limit=limit_per_query,
                sort="new",
            ):
                if post.id in results:
                    continue
                created = datetime.fromtimestamp(post.created_utc, tz=timezone.utc)
                if created < cutoff:
                    continue
                results[post.id] = {
                    "title": post.title,
                    "body": (post.selftext or "")[:2000],
                    "subreddit": subreddit_name,
                    "created_utc": int(post.created_utc),
                    "score": post.score,
                    "url": f"https://reddit.com{post.permalink}",
                }
            # Polite delay between queries to stay well within rate limits
            time.sleep(0.6)

        except PRAWException as exc:
            print(
                f"  [WARN] PRAW error in r/{subreddit_name} q={query!r}: {exc}",
                file=sys.stderr,
            )
        except Exception as exc:
            print(
                f"  [WARN] Unexpected error in r/{subreddit_name} q={query!r}: {exc}",
                file=sys.stderr,
            )

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

    # Decide fetch window:
    #   - First ever run (empty DB)  → full 90-day sweep
    #   - Subsequent runs            → last 8 days (overlap to catch any gaps)
    is_initial = len(existing) == 0
    days_back = 90 if is_initial else 8
    limit_per_query = 500 if is_initial else 100

    print(
        f"Mode: {'initial 90-day' if is_initial else 'daily update'} | "
        f"days_back={days_back} | limit_per_query={limit_per_query}"
    )

    reddit = make_reddit()

    new_posts_seen = 0
    new_complaints = 0

    for sub_name in SUBREDDITS:
        print(f"Scanning r/{sub_name} …", flush=True)
        raw = fetch_subreddit_posts(reddit, sub_name, days_back, limit_per_query)
        print(f"  {len(raw)} candidate posts found")

        for post_id, post in raw.items():
            if post_id in existing:
                continue  # Already in database; skip

            new_posts_seen += 1
            result = classify_post(post["title"], post["body"], post["subreddit"])

            if result is None:
                continue  # Not a complaint or no model identified

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
