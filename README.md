# Market Morning Desk

**AI Market Intelligence & Trading Tutor**

An automated system that collects overnight US/HK market data and news,
analyzes it macro → market → sector → company → trade implication, teaches
you how professional investors think, and emails you a compact HTML
research note every morning before the Hong Kong market opens.

This is **not** a stock-news aggregator and **not** a trading bot. It never
places trades. It ranks information aggressively (5–10 minutes of reading),
separates FACT from INTERPRETATION from TRADE IMPLICATION, and includes a
"Learn One Thing Today" section tied to the actual day's market action.

---

## 1. Quick start (zero API keys required)

```bash
git clone <this-repo>
cd market-morning-desk
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run the full pipeline end-to-end using bundled sample data
# (tests/fixtures/*.json) - no external API keys needed.
python main.py morning --mock --no-email --date 2026-09-09
```

This will:
1. Load mock market data, news, and a macro calendar from `tests/fixtures/`.
2. Run the full collection → dedup → scoring → LLM analysis → rendering pipeline.
3. Save the finished HTML report to `outbox/morning_report_2026-09-09.html`.
4. Persist everything to a local SQLite database at `data/market_morning_desk.db`.

Open `outbox/morning_report_2026-09-09.html` in a browser to see a complete
sample report (regime call, market dashboard, sector/theme map, 5 top
stories, company radar, 0–3 trade ideas, macro risk calendar, "Learn One
Thing Today", terminology, and full source citations).

Run the test suite (57 tests, all offline/mocked):

```bash
python -m pytest tests/ -v
```

---

## 2. What "MOCK_MODE" means

`MOCK_MODE=true` (the default) makes **every** external provider
(market data, news, macro calendar, LLM, email) read from
`tests/fixtures/*.json` or produce deterministic, data-driven canned output
instead of calling a real API. This lets you:

- Demo the entire product with zero signups/API keys.
- Run the test suite in CI without secrets.
- Verify your own config changes (new themes, new watchlist tickers, new
  scoring weights) produce sane output before spending real API credits.

Set `MOCK_MODE=false` (or omit it and configure real provider keys) to use
live data. Each provider independently falls back to its mock implementation
if its required API key is missing (see `src/providers/factory.py`) - the
pipeline never crashes for a missing *optional* key.

---

## 3. Sending yourself a real test email

1. Copy `.env.example` to `.env` and fill in:
   ```
   MOCK_MODE=false
   EMAIL_TO=you@example.com
   EMAIL_FROM=morning-desk@yourdomain.com
   EMAIL_PROVIDER=resend
   RESEND_API_KEY=re_xxx...
   ```
   (Get a free Resend API key at https://resend.com - verify a sending
   domain, or use their shared test sender for a quick check.)
2. Run:
   ```bash
   python main.py morning --mock          # keep MOCK_MODE for data, but...
   # ...or, to send a REAL email using mock market/news data (fastest way
   # to test email deliverability without wiring up all real data providers):
   EMAIL_PROVIDER=resend MOCK_MODE=true EMAIL_TO=you@example.com python main.py morning --mock
   ```
   The `EMAIL_TO`/`EMAIL_PROVIDER`/`RESEND_API_KEY` env vars are read
   independently of `MOCK_MODE`, so you can test real email delivery with
   mock data, or real data with a mock (file-written) email - mix and match
   while you wire things up incrementally.
3. Without `EMAIL_TO` set, the pipeline still runs fully and saves the
   report HTML to `outbox/` - it just skips the send step (logged, not an
   error) so you're never blocked from generating a report.

**SMTP fallback**: set `EMAIL_PROVIDER=smtp` and `SMTP_HOST` /
`SMTP_PORT` / `SMTP_USERNAME` / `SMTP_PASSWORD` instead of Resend.

---

## 4. Which API keys are required vs optional

| Provider | Required? | Env var(s) | Notes |
|---|---|---|---|
| Email delivery | **Required for real emails** | `EMAIL_TO`, `EMAIL_FROM`, `EMAIL_PROVIDER`, `RESEND_API_KEY` (or `SMTP_*`) | Without it, reports still generate and save to `outbox/`. |
| LLM (analysis) | **Required for non-mock analysis** | `LLM_PROVIDER`, `LLM_MODEL`, `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` | Falls back to the deterministic mock analyzer if missing. |
| Market data | Optional | none (yfinance is keyless) | yfinance is best-effort/unofficial; see recommended vendors below for production reliability. |
| News | Optional | `NEWSAPI_KEY` | RSS feeds (Reuters, CNBC, etc. - see `config/sources.yaml`) work with no key at all. |
| Macro calendar | Optional | `FRED_API_KEY` | Free signup at https://fred.stlouisfed.org/docs/api/api_key.html. Without it, macro calendar collection is skipped gracefully (logged, non-fatal). |
| SEC filings | Optional | none | `src/collectors/sec.py` uses SEC EDGAR's free, keyless API. |
| HKEX filings | Not implemented | — | See §8 below - documented placeholder interface. |

**Nothing is required to demo the product.** `MOCK_MODE=true` (the
default) needs zero keys.

---

## 5. Recommended real providers for production

| Need | Recommended | Why |
|---|---|---|
| Market data | **Polygon.io** or **Finnhub** | Official REST APIs with SLAs; yfinance (bundled, keyless) is fine for personal use but unofficial and rate-limit-fragile. |
| News | **Finnhub company/market news** or **NewsAPI.org** | Reasonable free tiers; RSS (bundled, keyless) covers Reuters/CNBC/etc. for zero cost. |
| Macro calendar | **FRED** (bundled) for data series + a paid calendar vendor (Trading Economics/Econoday) for consensus "expected" figures, which FRED does not provide. |
| LLM | **Anthropic Claude** (current Claude model family) or **OpenAI GPT** | Both are wired up (`src/providers/real_llm.py`); pick whichever you already have API access to. |
| Email | **Resend** | Modern deliverability-focused API, generous free tier, simple domain verification. |

---

## 6. Configuration - change themes/watchlist without touching code

Everything user-editable lives in `config/*.yaml`:

- **`config/settings.yaml`** — schedule labels, report section sizes
  (`top_news`, `macro_stories`, `trade_ideas_max`, etc.), scoring weights,
  data-quality thresholds, LLM/email provider selection, DB path.
- **`config/themes.yaml`** — add/edit/remove themes. Each theme has
  `keywords` (for rule-based news tagging), `tickers`, `related_etfs`,
  `upstream`/`downstream`/`drivers`/`risks` (used to generate causal-chain
  reasoning in story analysis). **Add a new theme by copying an existing
  block and editing the fields - no Python changes needed.**
- **`config/watchlist.yaml`** — the company watch universe, grouped
  `us` / `hk_china` / `optional_foreign`. Add a ticker+name pair to get it
  included in Company Radar / trade-idea eligibility.
- **`config/assets.yaml`** — the market-data dashboard universe, grouped
  by section (indices, rates, FX, commodities, ETFs). Add a `{symbol,
  display}` pair to track a new asset.
- **`config/sources.yaml`** — the source-tier registry (Tier 1 primary /
  Tier 2 high-quality media / Tier 3 secondary / Tier 4 social-disabled).
  Add an RSS feed here and it's automatically picked up by
  `build_news_providers()` in non-mock mode.

Example: to add "Nuclear / Uranium" as a new theme, copy the
`gold_precious_metals` block in `config/themes.yaml`, rename the key/name,
and fill in keywords/tickers/drivers/risks. It will automatically flow
through scoring, theme analysis, and the Sector & Theme Map section of the
email on the next run.

---

## 7. Switching LLM provider

Set in `.env` (or as real environment variables):

```
LLM_PROVIDER=anthropic       # or: openai | mock
LLM_MODEL=claude-sonnet-5    # any current Anthropic/OpenAI model id
ANTHROPIC_API_KEY=sk-ant-...
```

or

```
LLM_PROVIDER=openai
LLM_MODEL=gpt-5.1
OPENAI_API_KEY=sk-...
```

No code changes needed - `src/providers/factory.py::build_llm_provider()`
reads these at startup. All prompts are provider-agnostic (they ask for
JSON-only output and instruct the model to treat all article content as
untrusted data, never instructions - see `src/analysis/llm_client.py`).

To add a **new** LLM provider (e.g. a future model family), implement
`src/providers/llm_base.py::LLMProvider` (one method: `generate_json`) and
add a branch in `build_llm_provider()`.

---

## 8. Known V1 limitations (documented, not hidden)

- **HKEX company announcements**: HKEX does not offer a public,
  terms-friendly bulk API. Building a scraper would be brittle and could
  violate their terms of use. `src/collectors/hkex.py` ships a clean
  `HkexAnnouncementsProvider` interface that currently returns an empty
  list - swap in a licensed data vendor's implementation when available.
  The rest of the Morning Desk (scoring, theme analysis, rendering)
  requires zero changes when this is filled in.
- **SEC EDGAR collector** (`src/collectors/sec.py`) ships a minimal,
  best-effort real implementation (keyless, rate-limit-friendly) -
  extend `fetch()` with EDGAR's full-text search API for production use.
- **FRED-based macro calendar** provides release **dates** and **previous**
  values reliably, but not analyst **consensus/"expected"** figures (FRED
  doesn't have those) - wire up a paid calendar vendor if you need that.
- **Yesterday's Calls Review** (Section 22) computes subsequent price move
  and a qualitative "thesis intact?" flag, but does not yet compute true
  max-favorable/max-adverse-excursion (would require intraday price
  history) - fields exist in the schema (`YesterdayReviewItem`) and are
  `None` until a provider capable of intraday history is wired in.

None of these block the core acceptance criteria - the pipeline runs
end-to-end and produces a complete report without any of them.

---

## 9. Scheduling

### Option A — GitHub Actions (recommended, needs no server)

See `.github/workflows/morning.yml`. It triggers at `30 23 * * *` UTC,
which is **07:30 Asia/Singapore** (GitHub Actions cron is always UTC;
Singapore has no DST so this offset is constant: SGT = UTC+8).

Set repository secrets: `EMAIL_TO`, `EMAIL_FROM`, `EMAIL_PROVIDER`,
`RESEND_API_KEY` (or `SMTP_*`), `LLM_PROVIDER`, `LLM_MODEL`,
`ANTHROPIC_API_KEY`/`OPENAI_API_KEY`, and optionally `NEWSAPI_KEY` /
`FRED_API_KEY` / `POLYGON_API_KEY` / `FINNHUB_API_KEY`.

You can also trigger it manually from the Actions tab
(`workflow_dispatch`), optionally forcing `MOCK_MODE=true` or a specific
`--date`.

### Option B — Local cron (personal machine always on before market open)

```cron
# Asia/Singapore 07:30 local time, every weekday
30 7 * * 1-5 cd /path/to/market-morning-desk && /path/to/.venv/bin/python main.py morning >> logs/cron.log 2>&1
```//
(Use your system's actual local timezone in the cron time if it isn't
already Asia/Singapore - `crontab` uses the machine's local TZ.)

### Option C — In-process blocking scheduler

`src/scheduler/jobs.py::run_blocking_scheduler()` sleeps until the
configured `email_time` (from `config/settings.yaml`) each day in
Asia/Singapore time, then runs the job. Useful inside a long-running
container; a real cron/systemd timer is simpler and more restart-resilient
for a personal machine.

---

## 10. CLI reference

```bash
python main.py morning                      # full run, real providers, sends email
python main.py morning --mock                # full run, mock providers, sends email (if EMAIL_TO set)
python main.py morning --mock --no-email     # full run, mock providers, saves HTML to outbox/, no send
python main.py morning --date 2026-09-09     # run for a specific date
python main.py collect / analyze / render / send   # staged aliases (see main.py docstring)
```

---

## 11. Project structure

```
market-morning-desk/
  main.py                    CLI entry point
  config/                    User-editable YAML (settings/themes/watchlist/assets/sources)
  src/
    collectors/               Orchestration: fetch -> hand to processing
    providers/                Abstract interfaces + mock + real implementations
    processing/                Normalize, dedup, entity/theme mapping, scoring, clustering, quality gate
    analysis/                  LLM-backed analysis modules (regime, theme, story, company, trade, learning, editor)
    models/                    Pydantic schemas (schemas.py) + SQLAlchemy models (database.py)
    reports/                   Jinja2 HTML renderer + templates/morning_email.html
    email/                     Email dispatch wrapper
    scheduler/                 Scheduling helpers
    utils/                     config/time/logging/retry
    pipeline.py                End-to-end orchestration (the actual "run everything" function)
  tests/                      57 tests + tests/fixtures/*.json (mock data)
  .github/workflows/morning.yml
  outbox/                      Generated reports land here (gitignored)
  data/                        SQLite database (gitignored)
  logs/                        Per-run logs (gitignored)
```

---

## 12. Database

SQLite (via SQLAlchemy), path configurable via `DATABASE_PATH` env var or
`config/settings.yaml` `database.path`. Tables: `market_snapshots`,
`news_articles`, `news_clusters`, `analysis_results`, `themes`,
`theme_daily_views`, `company_events`, `trade_ideas`, `macro_events`,
`reports`, `learning_concepts`, `system_runs`, `source_records`. Raw data
is stored per run_date so any report can be regenerated/audited later, and
re-running the same `--date` overwrites that date's rows cleanly instead
of erroring or duplicating.

---

## 13. Design principles this codebase enforces

- **Signal over noise**: hard caps on section sizes (5 top stories, 3
  macro stories, 5 company radar items, max 3 trade ideas - all
  configurable, all enforced by Pydantic validators, not just convention).
- **Fact vs. interpretation vs. trade implication**: every `StoryAnalysis`
  has separate `fact` / `why_it_matters` / market-impact fields; prompts
  explicitly instruct the LLM to hedge uncertain causal claims.
- **No forced trades**: `TradeIdeaList` allows zero ideas; the email
  renders a clear "NO HIGH-CONVICTION SETUP TODAY" box when empty.
- **Source traceability**: every `NewsCluster`/`StoryAnalysis` carries
  `source_ids`/`source_names`/`urls`; a data-quality check flags stories
  missing citations rather than silently rendering them.
- **Hallucination guardrails**: all LLM output is JSON-schema-validated
  (Pydantic) before it's allowed into a report; a failed validation falls
  back to a safe, clearly-labeled degraded value rather than propagating
  bad data. Untrusted article text is explicitly marked as DATA, not
  instructions, in every prompt (prompt-injection defense).
- **Degraded-mode transparency**: `run_quality_checks()` flags stale/
  missing market data, missing sources, or a failed news pipeline, and the
  email renders a visible "DATA QUALITY WARNING" banner rather than
  silently sending a misleadingly normal-looking report.

---

## 14. Disclaimer

This report is an AI-assisted research and learning tool, not financial
advice. Information may be incomplete or inaccurate. Verify critical
information from primary sources before trading.
