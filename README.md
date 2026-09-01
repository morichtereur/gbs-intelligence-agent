# GBS Intelligence Agent

> Automated competitor & client intelligence for GBS / Finance Transformation consulting.
> Weekly consulting-style dashboard + email brief — fully automated via cron, powered by the Claude API.

[![CI](https://github.com/morichtereur/gbs-intelligence-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/morichtereur/gbs-intelligence-agent/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

**Built by [Moritz Richter](https://www.linkedin.com/in/moritz-richter-28297119a/)**

[**▶ Live demo dashboard**](https://morichtereur.github.io/gbs-intelligence-agent/) · built from illustrative sample data, no setup needed

[![Intelligence Explorer dashboard](docs/dashboard.png)](https://morichtereur.github.io/gbs-intelligence-agent/)

---

## Try it in 30 seconds

No API key, no email account, no feeds:

```bash
git clone https://github.com/morichtereur/gbs-intelligence-agent.git
cd gbs-intelligence-agent
pip3 install -r requirements.txt
python3 demo.py
```

Then open `output/DEMO/intelligence_explorer.html` and `output/DEMO/newsletter_full.html` in a browser.
The demo's competitor signals are real publications by the firms (verified links); the client companies are fictional. It runs the real rendering pipeline.

---

## How it works

The agent monitors public sources for strategic signals relevant to **Global Business Services (GBS)**, **Global Capability Centers (GCC)**, and **Agentic AI** — and turns them into a curated weekly intelligence product.

```mermaid
flowchart LR
    A[Google Alerts<br/>RSS feeds] --> B[intel_ingest_stdlib.py<br/>filter · dedupe · tag]
    B --> C[(SQLite)]
    C --> D[summarize_new_links.py<br/>Claude: score 1–3 + summarize]
    D --> C
    C --> E[generate_dashboard.py<br/>Intelligence Explorer]
    C --> F[weekly_newsletter_output.py<br/>HTML email brief]
    F --> G[send_newsletter.py<br/>Gmail SMTP]
```

**Every Monday morning, automatically:**
1. Ingest 50+ RSS feeds across competitor firms, analyst houses (HFS, Everest, SSON, Gartner), and client companies
2. Filter noise up front — job posts, people profiles, stock trackers, stale resurfaced pages, blocked domains
3. Score each article 1–3 for strategic relevance with Claude, using an advisory-lens prompt for client signals
4. Render the email brief (highest-signal articles only) and the dashboard
5. Rebuild the browsable edition archive (`output/archive.html`)
6. Send the brief by email — every edition stays archived by calendar week

---

## What you get

### Intelligence Explorer

A standalone consulting-style HTML dashboard focused on the consultancies — no server, no framework, just open it in a browser:

- **Answer-first headline** derived from the week's data (top theme, most active firm)
- **Firm × theme matrix** showing where competitors publish, grouped by cluster (**MBB · Big4 · Accenture**), with firm logos
- **Themes follow the CFO agenda**: Finance strategy · GBS · GCC · Controlling & FP&A, with agentic AI as the cross-cutting layer
- **Signal list in two groups**, each ranked by relevance: **Market moves** (offerings, alliances, M&A — may demand a competitive response) and **Research & viewpoints** (surveys and thought leadership — to read, cite, and benchmark against); classification comes from the scoring model
- Each title links straight to the source, with the firm logo, AI summary, and source domain
- Theme filter and full-text search, keyboard shortcuts (`/` search · `Esc` reset), print-friendly, provenance note in the footer

Client signals stay in the email brief; the dashboard deliberately keeps only the competitor view.

### Email brief

<img src="docs/newsletter.png" width="420" alt="Weekly newsletter">

Inline-styled HTML email (renders in Outlook/Gmail), grouped by firm, high-relevance signals only, with a separate client-signals section, a one-click feedback link in the footer (set `INTEL_FEEDBACK_EMAIL`), and plain-text fallback.

### Edition archive

`output/archive.html` — an index of every past edition (week, signal counts, links to that week's dashboard and email), rebuilt on every run. Drop the whole `output/` folder on a shared drive and the team can browse back through the quarter.

---

## Relevance scoring

Each article is scored by Claude before summarizing:

| Score | Label | Meaning | Newsletter |
|---|---|---|---|
| 3 | ★ HIGH | Direct strategic signal: new offering, GBS/AI publication, C-suite move, M&A | ✅ |
| 2 | MED | Indirect signal: market commentary, trend piece | Explorer only |
| 1 | LOW | Weak signal: generic news | Explorer only |
| 0 | SKIP | Job post, stock tracker, ETF filing, economic indicator | Discarded |

Running cost is small: the default model is Claude Haiku and a weekly run scores at most `INTEL_MAX_SUMMARIZE` (30) short snippets — typically a few cents per week.

---

## Built to run unattended

Design decisions for a pipeline that runs from cron with nobody watching:

- **Fail closed.** Any failed stage or feed fetch stops the run before delivery — a partial newsletter is never sent (`INTEL_FAIL_ON_FEED_ERROR=0` opts out).
- **Edition numbering survives failures.** The counter is committed only after the email actually goes out, so a crashed run doesn't burn an edition.
- **Transient API errors don't kill the run.** Claude calls retry on rate limits and 5xx with exponential backoff.
- **Duplicates collapse.** The same article arriving through several alert feeds is stored once per feed but shown once — deduplicated by canonical URL (tracking parameters and Google redirects stripped).
- **Precise tagging.** Keywords match on word boundaries, so `erp` never fires inside "excerpt"; articles matching no theme are dropped before they cost an API call.
- **Everything is inspectable.** Plain SQLite, plain HTML output archived per calendar week, one log file.

---

## Setup

### 1. Clone and install
```bash
git clone https://github.com/morichtereur/gbs-intelligence-agent.git
cd gbs-intelligence-agent
pip3 install -r requirements.txt
chmod +x run_weekly.sh
```

### 2. Configure API keys
```bash
export ANTHROPIC_API_KEY="sk-ant-..."          # https://console.anthropic.com
export GMAIL_USER="your@gmail.com"
export GMAIL_APP_PASSWORD="xxxx xxxx xxxx xxxx"  # https://myaccount.google.com/apppasswords
export INTEL_RECIPIENTS="recipient@email.com"
```

Add to `~/.zshrc` or `~/.bashrc` for persistence.

### 3. Create alerts and configure feeds

```bash
cp sources.example.json sources.json
```

Create alerts at [google.com/alerts](https://www.google.com/alerts) with **Deliver to: RSS feed**, copy the feed URLs into `sources.json`, and add the firm names to `competitor_sources` or `client_sources`.

The quality of the whole product starts with the alert queries. Three rules that work well in practice:

1. **Scope competitor alerts to the firm's own domain** (`site:`) — you want what they *publish*, not what journalists write about them.
2. **One alert per firm per theme**, named `Firm_Theme` — the `source` name drives grouping and the dashboard matrix.
3. **Quote multi-word phrases.** Unquoted words explode the noise.

Competitor monitoring (one per firm × theme):
```
site:mckinsey.com ("global business services" OR "shared services" OR "integrated business services")
site:mckinsey.com ("agentic AI" OR "AI agents" OR "autonomous agents")
site:bcg.com ("capability center" OR "GCC" OR "nearshoring")
site:bain.com ("operating model" OR "service delivery model")
site:deloitte.com ("finance transformation" OR "shared services" OR "GBS")
site:accenture.com ("intelligent operations" OR "agentic" OR "managed services")
site:kpmg.com ("FP&A" OR "financial controlling" OR "planning and forecasting")
```

Client monitoring (one per account × angle):
```
"CompanyName" ("CFO" OR "chief financial officer" OR "finance transformation")
"CompanyName" ("shared services" OR "capability center" OR "outsourcing")
"CompanyName" ("restructuring" OR "cost reduction" OR "ERP" OR "S/4HANA")
```

Everything an alert returns still passes the pipeline's own filters: word-boundary keyword tagging (`tag_rules`), career/people-page exclusions, the stock-noise domain blocklist, and Claude's relevance scoring.

### 4. Run
```bash
bash run_weekly.sh
```

Output in `output/CW_YYYY_WW/`:
- `intelligence_explorer.html` — the dashboard
- `newsletter_full.html` — full email (open in browser to preview)
- `newsletter_block.html` / `newsletter_block.txt` — article blocks only
- `client_signals.html` — client signals only

### 5. Schedule (every Monday 07:30)
```bash
(crontab -l 2>/dev/null; echo "30 5 * * 1 cd /path/to/gbs-intelligence-agent && bash run_weekly.sh >> logs/weekly.log 2>&1") | crontab -
```
Adjust UTC offset for your timezone.

---

## Customization

### Make it yours
All branding is optional and off by default, so the tool ships neutral:

```bash
export INTEL_BRAND="Competitor Intelligence"            # dashboard masthead
export INTEL_BRAND_CONTEXT="a GBS transformation team at Acme Consulting"  # scoring prompt audience
export INTEL_OWNER_NAME="Your Name"                     # dashboard footer
export INTEL_OWNER_TITLE="Consultant"
export INTEL_OWNER_EMAIL="you@example.com"
export INTEL_ORG_NAME="Acme Consulting"                 # newsletter header
export INTEL_CONTACT_NAME="Your Name"                   # newsletter contact card
export INTEL_CONTACT_EMAIL="you@example.com"
```

### Add a company to track
In `sources.json`:
```json
{
  "source": "CompanyName_Finance",
  "url": "https://www.google.com/alerts/feeds/YOUR_ID/FEED_ID"
}
```
Add `"CompanyName"` to `competitor_sources` or `client_sources`.

### Add blocked domains (noise filter)
```json
"blocked_domains": ["gurufocus.com", "marketbeat.com"]
```

### Change newsletter score threshold
```bash
export INTEL_MIN_SCORE=2   # include MED signals (default: 3)
```

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | **Required.** Claude API key |
| `GMAIL_USER` | — | Gmail sender |
| `GMAIL_APP_PASSWORD` | — | Gmail App Password |
| `INTEL_RECIPIENTS` | — | Comma-separated recipients |
| `INTEL_DB_PATH` | `intel.db` | SQLite database |
| `INTEL_SOURCES_PATH` | `sources.json` | Feed and tagging configuration |
| `INTEL_FAIL_ON_FEED_ERROR` | `1` | Stop before delivery when a feed fails |
| `INTEL_WINDOW_DAYS` | `7` | Newsletter lookback window |
| `INTEL_MAX_AGE_DAYS` | `60` | Drop feed entries published longer ago than this (0 disables) |
| `INTEL_MIN_SCORE` | `3` | Minimum relevance score for the newsletter |
| `INTEL_MAX_SUMMARIZE` | `30` | Max articles to summarize per run |
| `INTEL_MAX_PER_SOURCE` | `2` | Max newsletter articles per source |
| `INTEL_DASHBOARD_WEEKS` | `4` | Explorer lookback in weeks |
| `CLAUDE_MODEL` | `claude-haiku-4-5-20251001` | Claude model |
| `CLAUDE_MAX_RETRIES` | `3` | API retries on rate limits / transient errors |
| `INTEL_BRAND` | `Competitor Intelligence` | Dashboard masthead |
| `INTEL_BRAND_CONTEXT` | generic consulting team | Audience framing in the scoring prompt |
| `INTEL_OWNER_NAME` / `_TITLE` / `_EMAIL` | — | Dashboard footer identity (hidden if unset) |
| `INTEL_ORG_NAME` | `GBS Intelligence Agent` | Newsletter header |
| `INTEL_CONTACT_NAME` / `_ROLE` / `_EMAIL` | — | Newsletter contact card (hidden if unset) |
| `INTEL_FEEDBACK_EMAIL` | contact email | Address behind the newsletter's feedback link (hidden if unset) |
| `INTEL_PHOTO_PATH` | `photo.jpg` | Footer photo path |
| `INTEL_DEMO_LABEL` | — | Adds a badge to the masthead (used by `demo.py`) |

---

## Stack

- **Python 3.10+** — standard library + `requests`, no heavy dependencies
- **SQLite** — lightweight local database
- **Claude Haiku** ([Anthropic](https://anthropic.com)) — fast, cheap scoring + summarization
- **Gmail SMTP** — newsletter delivery
- **Google Alerts** — RSS feed source (free)
- **Vanilla HTML/CSS/JS** — dashboard, no framework needed

---

## License

MIT — free to use, modify, and distribute.

---

*Built as a personal project to automate competitive intelligence for GBS and finance transformation consulting. The demo's competitor signals link to real publications by the named firms (summaries are condensed); the client companies in the demo are fictional. Firm logos are rendered as favicons from each firm's own domain. Contributions welcome.*
