# ShowingDay — Developer Handoff Guide

**Project:** ShowingDay — Showing Day Planner
**Owner:** Jason O'Brien, PREMIERE Group at Real Broker LLC
**Built:** 2026-03-15
**Stack:** Python 3.11+ / Flask / Vanilla JS / Google Maps API

---

## 1. Local Setup

```bash
# 1. Clone / open the project
cd "Showing Day Planner"

# 2. Create a virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up environment variables
cp .env.example .env
# Edit .env and fill in your credentials (see Section 3)

# 5. Run the app
python app.py

# 6. Open browser
open http://localhost:5000
```

The app starts in mock mode if `GOOGLE_MAPS_API_KEY` is not set — a realistic sample 3-property route is returned so the full UI can be tested without any API credentials.

---

## 2. What's Built vs. What's Stubbed

### Fully Functional

| Component | File | Status |
|---|---|---|
| Flask app + all routes | `app.py` | Complete |
| Session state persistence | `tools/session_logger.py` | Complete |
| Route optimizer | `tools/route_optimizer.py` | Complete (mock mode when no API key) |
| API Nation webhook parser | `tools/apination_webhook.py` | Complete |
| Disclosure analyzer | `tools/disclosure_analyzer.py` | Complete (mock mode when no API key) |
| Client page builder | `tools/client_page_builder.py` | Complete |
| Calendar ICS export fallback | `tools/calendar_manager.py` | Complete |
| Agent UI | `ui/index.html`, `ui/style.css`, `ui/app.js` | Complete |
| Test suite | `tests/test_tools.py` | Complete |

### Stubbed — Needs Implementation

| Component | File | What's Needed |
|---|---|---|
| CRM — Lofty API | `tools/crm_client_lookup.py` | Implement `search_lofty()`: confirm endpoint with Lofty support, use `LOFTY_API_KEY` |
| CRM — GHL API | `tools/crm_client_lookup.py` | Uncomment and test `search_ghl()`: uses `GHL_API_KEY` + `GHL_LOCATION_ID` |
| Google Calendar OAuth | `tools/calendar_manager.py` | Implement `get_credentials()`: follow OAuth2 guide in file, requires `GOOGLE_CALENDAR_CREDENTIALS_JSON` |
| Gmail OAuth | `tools/gmail_sender.py` | Implement `get_credentials()`: same pattern as Calendar, requires `GMAIL_CREDENTIALS_JSON` |
| Zillow scraper | `tools/zillow_scraper.py` | Implement `_scrape_zillow()`: Zillow is bot-protected — recommend ScraperAPI or similar proxy service |
| Bridge API | `tools/bridge_api_fetcher.py` | PLACEHOLDER — wait for Bridge API access confirmation |
| ShowingTime API | `tools/showingtime_api.py` | PLACEHOLDER — wait for ShowingTime API access confirmation |

---

## 3. Credentials Setup

All credentials live in `.env`. Never commit `.env` to git.

Copy `.env.example` to `.env` and fill in values:

| Key | Required For | Where to Get It |
|---|---|---|
| `GOOGLE_MAPS_API_KEY` | Route optimization (live mode) | Google Cloud Console → APIs & Services → Credentials. Enable: Distance Matrix API, Maps JavaScript API |
| `GOOGLE_CALENDAR_CREDENTIALS_JSON` | Calendar integration | Google Cloud Console → OAuth 2.0 Client IDs → Desktop App |
| `GMAIL_CREDENTIALS_JSON` | Email delivery | Same Google Cloud project as Calendar |
| `LOFTY_API_KEY` | Lofty CRM lookup | Lofty Admin → Settings → Integrations → API |
| `GHL_API_KEY` | GHL CRM lookup + webhooks | GHL → Settings → Integrations → API Keys |
| `GHL_LOCATION_ID` | GHL CRM | GHL → Settings → Business Info → Location ID |
| `ANTHROPIC_API_KEY` | Disclosure PDF analysis | https://console.anthropic.com → API Keys |
| `DEFAULT_START_ADDRESS` | Pre-fill starting location | Set to Jason's home/office address in Plainwell, MI |
| `FLASK_SECRET_KEY` | Flask session security | Generate: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `SHOWINGTIME_API_KEY` | (placeholder) | Contact ShowingTime support |
| `BRIDGE_API_KEY` | (placeholder) | Contact BridgeAPI@bridgeinteractive.com |

---

## 4. Running Tests

```bash
# Run all tests
python tests/test_tools.py

# Run tests for a specific tool
python tests/test_tools.py --tool route_optimizer
python tests/test_tools.py --tool session_logger

# Run a tool's own --test mode
python tools/route_optimizer.py --test
python tools/session_logger.py --test
python tools/apination_webhook.py --test
python tools/zillow_scraper.py --test
python tools/disclosure_analyzer.py --test
python tools/client_page_builder.py --test
python tools/gmail_sender.py --test
python tools/bridge_api_fetcher.py --test
python tools/showingtime_api.py --test
```

All tests run in mock mode — no API keys required. The route optimizer returns a realistic sample 3-property West Michigan route, and the disclosure analyzer returns sample red flag data.

---

## 5. Architecture Overview

```
app.py  ←→  Tools (stateless)  ←→  session_state.json
  ↕                                       ↕
ui/index.html  (fetch API calls)     run_log.json
```

**Key architectural decisions:**

1. **Stateless tools.** Every tool in `tools/` is stateless — they take inputs and return outputs. All session state lives in `session_state.json` managed by `session_logger.py`.

2. **Retry wrapper.** `app.py` wraps every tool call in `with_retry()` which retries up to 3 times with exponential backoff (5s, 15s). Failures are logged to `run_log.json`.

3. **Mock mode everywhere.** When API keys are missing, every tool returns realistic mock data rather than crashing. The UI degrades gracefully.

4. **Single page app.** `ui/index.html` is a single HTML file with 4 screens navigated via JS. No build system — just Flask serving static files.

5. **Session polling.** `app.js` polls `/api/session` every 10 seconds. When it detects property status changes (via `sessionHash()`), it shows webhook notifications in the UI.

---

## 6. Implementing the Missing Pieces

### Google Calendar OAuth

Open `tools/calendar_manager.py` and find `get_credentials()`. The implementation guide is in the docstring. In summary:

```python
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# Parse credentials from .env
creds_data = json.loads(os.getenv("GOOGLE_CALENDAR_CREDENTIALS_JSON"))
flow = InstalledAppFlow.from_client_config(creds_data, CALENDAR_SCOPES)
creds = flow.run_local_server(port=0)
# Save token to token_calendar.json
```

First run will open a browser for OAuth consent. After that, token is refreshed automatically.

### GHL CRM Integration

Open `tools/crm_client_lookup.py` and find `search_ghl()`. Uncomment the API call — it's already written and commented out, just needs testing with real credentials:

```python
# GHL_API_KEY and GHL_LOCATION_ID must be set in .env
headers = {"Authorization": f"Bearer {GHL_API_KEY}", "Version": "2021-07-28"}
resp = requests.get("https://services.leadconnectorhq.com/contacts/", ...)
```

### Zillow Scraper

Zillow actively blocks scrapers. Recommended approach:
1. Sign up for [ScraperAPI](https://www.scraperapi.com/) or [Bright Data](https://brightdata.com/)
2. Route requests through their proxy service
3. Parse the `__NEXT_DATA__` JSON embedded in Zillow's HTML

Alternatively, wait for Bridge API access (more reliable than scraping).

---

## 7. Vercel Deployment

### What Works Today on Vercel

- All API routes (Flask WSGI works on Vercel Python runtime)
- UI serving (`ui/` static files)
- Tool functions that don't require file system write access
- Webhook receiver (`/webhook/showingtime`)

### What Needs a Database for Production

`session_state.json` and `run_log.json` are local files. Vercel's serverless functions don't have persistent filesystem access between requests.

**Recommended solution: Vercel KV (Redis)**

1. Enable Vercel KV in your Vercel project settings
2. Update `tools/session_logger.py` to use Vercel KV:
   ```python
   import os
   from vercel_kv import KV  # npm package or Python client

   def get_session():
       data = KV.get("showingday:session")
       return json.loads(data) if data else dict(EMPTY_SESSION)

   def _write_session(state):
       KV.set("showingday:session", json.dumps(state))
   ```
3. Same pattern for `run_log.json`

**Alternative:** Use a Supabase free tier PostgreSQL database and store session as JSON in a `sessions` table.

### Environment Variables on Vercel

Set all `.env` variables in Vercel Dashboard → Project Settings → Environment Variables. Do not commit `.env` to git.

### Deployment command

```bash
# Install Vercel CLI
npm i -g vercel

# Deploy
vercel

# Production deploy
vercel --prod
```

---

## 8. Key Files Reference

| File | Purpose |
|---|---|
| `app.py` | Flask entry point, all API routes |
| `tools/session_logger.py` | All session state I/O |
| `tools/route_optimizer.py` | Google Maps TSP route calculation |
| `tools/crm_client_lookup.py` | CRM search (Lofty → GHL → manual) |
| `tools/calendar_manager.py` | Google Calendar CRUD + ICS export |
| `tools/apination_webhook.py` | Webhook receiver and parser |
| `tools/zillow_scraper.py` | Listing data (stub → Bridge API upgrade path) |
| `tools/disclosure_analyzer.py` | Claude API PDF red flag analysis |
| `tools/client_page_builder.py` | Client HTML page generation |
| `tools/gmail_sender.py` | Gmail delivery |
| `tools/bridge_api_fetcher.py` | Placeholder for MLS-direct data |
| `tools/showingtime_api.py` | Placeholder for direct API integration |
| `ui/index.html` | Single-page agent app |
| `ui/style.css` | Full CSS (navy/gold design system) |
| `ui/app.js` | All JS: state, API calls, map, poll |
| `session_state.json` | Runtime session (gitignored) |
| `run_log.json` | Append-only tool call log (gitignored) |
| `output/` | Generated client pages (gitignored) |
| `sessions/archive/` | Completed session archives (gitignored) |

---

## 9. Contact & Notes

- **Owner:** Jason O'Brien, PREMIERE Group at Real Broker LLC, Plainwell / Allegan County, West Michigan
- **ShowingTime API:** Contact ShowingTime support to confirm API availability before building `showingtime_api.py`
- **Bridge API:** Contact BridgeAPI@bridgeinteractive.com — check if credentials are provisioned via existing IDX agreement
- **Lofty API:** Contact Lofty support or check Lofty Admin → Settings → Integrations
- **API Nation webhook:** Follow `docs/apination_setup.md` after app is live and accessible via URL
