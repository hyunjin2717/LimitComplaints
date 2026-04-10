# AI Rate Limit Complaints Tracker

> A public dashboard that automatically tracks and visualizes how often developers complain about rate limits for **Claude** (Anthropic), **Gemini** (Google), and **Codex** (OpenAI) on Reddit.

[![Auto-Updated Daily](https://img.shields.io/badge/auto--updated-daily-brightgreen)](../../actions)
[![GitHub Pages](https://img.shields.io/badge/hosted-GitHub%20Pages-blue)](../../)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow)](LICENSE)

---

## What is this?

This project collects Reddit posts where developers hit rate limits with AI APIs and turns them into easy-to-read graphs. It answers questions like:

- Which AI provider gets the most complaints about rate limits?
- Is the situation getting better or worse over time?
- When do complaint spikes happen?

Data is fetched daily via the [Arctic Shift API](https://arctic-shift.photon-reddit.com) — a public Reddit archive. **No Reddit API key required.** No AI or LLMs are used in classification — everything runs on regex patterns and a scoring algorithm.

---

## Live Dashboard

The dashboard is hosted on GitHub Pages and updates automatically every day at 06:00 UTC.

**[View the live dashboard →](https://your-username.github.io/LimitComplaints/)**

---

## Screenshots

| Weekly Trend | 90-Day Total |
|---|---|
| Line chart — complaints per week per model | Bar chart — cumulative complaint count |

---

## How It Works

1. **Collect** — Reddit is searched daily for posts mentioning rate limits across 10 major AI subreddits
2. **Classify** — Each post is scored for complaint strength using regex patterns (no AI needed)
3. **Filter** — Low-signal or off-topic posts are discarded
4. **Visualize** — Graphs are generated and published to GitHub Pages automatically

### Subreddits monitored

`r/ClaudeAI`, `r/GoogleGemini`, `r/OpenAI`, `r/ChatGPT`, `r/LocalLLaMA`, `r/artificial`, `r/singularity`, `r/MachineLearning`, `r/programming`, `r/github`

### Search queries used

`"rate limit"`, `"quota exceeded"`, `"too many requests"`, `"throttled"`, `"usage limit"`

---

## Classification Algorithm

Posts are classified entirely with deterministic rules — no LLMs involved.

### Step 1 — Rate-limit detection

Regex patterns match the many ways users describe hitting rate limits:

| Pattern type | Examples |
|---|---|
| Direct terms | `rate limit`, `rate limited`, `429`, `quota`, `throttled` |
| Indirect | `hit the limit`, `usage cap`, `out of credits`, `TPM`, `RPM` |
| Context | `tokens per minute`, `requests per hour`, `cooldown` |

### Step 2 — Complaint scoring (threshold: ≥ 2 points)

| Signal | Points |
|---|---|
| Rate limit keyword in post **title** | +3 |
| **Strong** complaint language (`frustrated`, `broken`, `absurd`, `wtf`…) | +3 |
| **Moderate** complaint language (`can't use`, `stopped working`, `constantly`…) | +2 |
| **Mild** complaint language (`problem`, `issue`, `stuck`…) | +1 |
| Question mark + rate limit in title | +1 |
| Exclamation mark in title | +1 |

Examples:
- "What are Claude's rate limits?" → score 1 → **discarded** (informational)
- "Claude rate limits are absolutely ridiculous" → score 6 → **counted**

### Step 3 — Negation filter

Posts containing phrases like `"no rate limit"`, `"bypass rate limits"`, or `"how to avoid rate limits"` are excluded unless they also contain strong complaint language.

### Step 4 — Model detection

| Model | Keywords / patterns |
|---|---|
| Claude | `claude`, `anthropic`, `haiku`, `sonnet`, `opus`, `claude-3`, `claude-4` |
| Gemini | `gemini`, `google ai`, `ai studio`, `vertex ai`, `bard`, `gemini pro/flash/ultra` |
| Codex | `codex`, `openai codex`, `codex cli`, `codex agent` |

A single post can count for multiple models. If no model keyword is found, the subreddit name is used as a fallback (e.g. posts in `r/ClaudeAI` → Claude).

---

## Project Structure

```
.
├── .github/workflows/update.yml   # Daily GitHub Actions cron job
├── scripts/
│   ├── collect.py                 # Fetch Reddit posts + classify
│   └── generate_graph.py          # Generate graphs + HTML
├── data/
│   └── complaints.json            # Persistent post database (auto-updated)
├── docs/                          # GitHub Pages output
│   ├── index.html
│   ├── graph_weekly.png
│   └── graph_total.png
└── requirements.txt
```

---

## Self-Hosting Setup

No API keys or accounts needed. Just fork and deploy.

### 1. Fork this repository

Click **Fork** at the top of this page.

### 2. Enable GitHub Pages

In your forked repo: **Settings → Pages → Source: Deploy from a branch → Branch: `main`, Folder: `/docs`**

Your dashboard will be live at `https://<your-username>.github.io/<repo-name>/`.

### 3. Run the first collection

Go to **Actions → Update Rate Limit Complaints → Run workflow**.

The first run fetches the last **90 days** of data. All subsequent runs (daily or manual) fetch only the last 8 days and merge new posts into the existing database.

---

## Data

- **Source**: [Arctic Shift API](https://arctic-shift.photon-reddit.com) — a public Reddit archive, no API key needed
- **Initial backfill**: last 90 days of Reddit posts
- **Ongoing updates**: every day at 06:00 UTC via GitHub Actions
- **Storage**: a single `data/complaints.json` file committed to the repository
- **Deduplication**: posts are keyed by Reddit post ID — no duplicates

---

## Contributing

Contributions are welcome. If you'd like to suggest new subreddits, improve the classification patterns, or add support for more AI providers, feel free to open an issue or pull request.

---

## License

[MIT](LICENSE)
