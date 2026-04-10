# AI Rate Limit Complaints Tracker

Automatically tracks Reddit posts complaining about rate limits for **Claude** (Anthropic), **Gemini** (Google), and **Codex** (OpenAI).

- **Initial data**: last 90 days of Reddit posts
- **Auto-updates**: every day at 06:00 UTC via GitHub Actions
- **Hosted**: GitHub Pages (`docs/` folder)
- **No AI used**: classification is done with regex patterns and a scoring algorithm

---

## Setup

### 1. Create a Reddit API application

1. Go to <https://www.reddit.com/prefs/apps> and log in
2. Click **"Create another app…"**
3. Fill in:
   - **Name**: anything (e.g. `RateLimitTracker`)
   - **Type**: `script`
   - **Redirect URI**: `http://localhost:8080` (not used, but required)
4. Click **Create app**
5. Note the **client ID** (shown below the app name, looks like `abc123def456`) and the **client secret**

### 2. Add GitHub Secrets

In your repository: **Settings → Secrets and variables → Actions → New repository secret**

| Secret name            | Value                    |
|------------------------|--------------------------|
| `REDDIT_CLIENT_ID`     | Your Reddit client ID    |
| `REDDIT_CLIENT_SECRET` | Your Reddit client secret|

### 3. Enable GitHub Pages

**Settings → Pages → Source: Deploy from a branch → Branch: `main`, Folder: `/docs`**

Save. GitHub Pages will be live at `https://<your-username>.github.io/<repo-name>/`.

### 4. Run the first collection

Go to **Actions → Update Rate Limit Complaints → Run workflow**.

The first run fetches the last **90 days** of data. Subsequent runs (scheduled or manual) only fetch the last 8 days and merge new posts into the database.

---

## Project structure

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

## Classification algorithm (no LLM)

### 1. Rate-limit detection

Regex patterns match the many ways users describe hitting rate limits:

| Pattern type | Examples |
|---|---|
| Direct terms | `rate limit`, `rate limited`, `429`, `quota`, `throttled` |
| Indirect | `hit the limit`, `usage cap`, `out of credits`, `TPM`, `RPM` |
| Context | `tokens per minute`, `requests per hour`, `cooldown` |

### 2. Complaint scoring (threshold: ≥ 2 points)

| Signal | Points |
|---|---|
| Rate limit keyword in post **title** | +3 |
| **Strong** complaint language (`frustrated`, `broken`, `absurd`, `wtf`…) | +3 |
| **Moderate** complaint language (`can't use`, `stopped working`, `constantly`…) | +2 |
| **Mild** complaint language (`problem`, `issue`, `stuck`…) | +1 |
| Question mark + rate limit in title (frustrated question) | +1 |
| Exclamation mark in title | +1 |

Posts scoring **< 2** are discarded as informational or neutral:
- ✗ "What are Claude's rate limits?" → score 1 (no complaint language)
- ✓ "Claude rate limits are absolutely ridiculous" → score 6

### 3. Negation filter

Posts containing phrases like "no rate limit", "bypass rate limits", or "how to avoid rate limits" are excluded (unless they also contain strong complaint language).

### 4. Model detection

Regex patterns identify which model is mentioned:

| Model | Keywords / patterns |
|---|---|
| Claude | `claude`, `anthropic`, `haiku`, `sonnet`, `opus`, `claude-3`, `claude-4` |
| Gemini | `gemini`, `google ai`, `ai studio`, `vertex ai`, `bard`, `gemini pro/flash/ultra` |
| Codex | `codex`, `openai codex`, `codex cli`, `codex agent` |

A single post can count for multiple models. If no model keyword is found, the subreddit name is used as a fallback (e.g. posts in r/ClaudeAI → Claude).

### 5. Subreddits monitored

`ClaudeAI`, `GoogleGemini`, `OpenAI`, `ChatGPT`, `LocalLLaMA`, `artificial`, `singularity`, `MachineLearning`, `programming`, `github`

### 6. Search queries used

`"rate limit"`, `"quota exceeded"`, `"too many requests"`, `"throttled"`, `"usage limit"`

---

## Graphs

| Graph | Description |
|---|---|
| **Weekly trend** | Line chart — complaint posts per week for each model, last 13 weeks |
| **90-day total** | Bar chart — cumulative complaint count per model |

Graphs are regenerated on every update and committed directly to `docs/`.

---

## License

MIT
