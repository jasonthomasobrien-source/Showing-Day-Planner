# CLAUDE.md — Showing Day Planner
**Project:** ShowingDay  
**Owner:** Jason O'Brien — PREMIERE Group at Real Broker LLC  
**Type:** On-demand local web application (runs locally, agent-built)  
**Last Updated:** 2026-03-15  
**Version:** 1.1

---

## 1. Project Overview

ShowingDay is a personal showing-day planning tool for a buyer's agent. When a client wants to tour multiple properties in a single session, this app handles everything: CRM client lookup, route optimization, time-slot allocation, calendar management, confirmation tracking, property research, and client delivery.

**The agent enters:**
- A client name (looked up from Lofty or GHL — contact details auto-filled)
- A list of property addresses to show
- A date and availability window (e.g., Saturday 1:00 PM – 6:00 PM)
- A starting location (default: Plainwell, MI home address)
- Their preferred showing direction (start-loaded vs. end-loaded)
- Max appointment length per showing

**The system produces:**
- An optimized showing route with real-time travel times between each stop
- Tentative Google Calendar blocks for each showing + travel buffers
- ShowingTime request checklist (manual mode) with auto-status updates via webhook
- On-confirmation: property research summary (Zillow) + disclosure review
- A client-facing showing day web page + calendar invite option

---

## 2. Workflow

The agent follows this numbered process. Claude Code executes each step in order, confirms before advancing where noted, and logs all outcomes to `run_log.json`.

### Step 1 — Collect Session Inputs

**1a — Client Lookup (CRM)**
- [ ] Agent types client name in the session start screen
- [ ] Call `crm_client_lookup.py` — search Lofty first, then GHL if not found
- [ ] Auto-fill: client full name, email address, phone number
- [ ] Display pulled contact details for agent to confirm before proceeding
- [ ] If client not found in either CRM, offer manual entry fallback
- [ ] Store client details in `session_state.json` under `client`

**1b — Session Details**
- [ ] One or more client property addresses (paste or enter line by line)
- [ ] Session date
- [ ] Start time and end time of availability window
- [ ] Starting location (default: Plainwell, MI from `DEFAULT_START_ADDRESS` in `.env`; offer override field)
- [ ] Preferred scheduling direction: **Start-loaded** (first showing ASAP) or **End-loaded** (last showing ends at window close)
- [ ] Max showing length per property (default: 30 minutes; agent can override per-property)

### Step 2 — Optimize Route
- [ ] Call Google Maps Distance Matrix API with all addresses + starting location
- [ ] Calculate travel time between every pair of addresses (time-of-day-aware using session date/time)
- [ ] Solve for optimal showing order (shortest total drive time, TSP approximation)
- [ ] Assign showing time slots based on scheduling direction preference and max showing length
- [ ] Display the proposed route in the UI: order, address, arrival time, showing window, departure time, drive time to next stop
- [ ] Flag if the schedule is too tight (total time exceeds availability window) and suggest:
  - Remove the last property
  - Shorten max showing length across all properties
  - Extend availability window

**Confirm with agent before proceeding.** Agent can drag-reorder stops or adjust times manually.

### Step 3 — Request Showings via ShowingTime

ShowingTime direct API access is unconfirmed. Default mode is manual request with webhook-based auto-status updates via API Nation + GHL.

**Manual Request Mode (current default):**
- [ ] Generate a ShowingTime request checklist per property: address, MLS number (if known), requested date, requested time window, agent name, agent phone
- [ ] Display as a formatted, copyable block per property for agent to submit manually in ShowingTime app or portal
- [ ] Each property gets a status toggle in the UI: **Requested / Confirmed / Declined / Pending**

**Status Update — Automatic (via API Nation + GHL webhook):**
- [ ] ShowingDay listens at `/webhook/showingtime` for incoming status events from GHL
- [ ] `apination_webhook.py` parses the payload: extracts property address, new status (confirmed/declined), timestamp
- [ ] Auto-updates property status in `session_state.json` without agent intervention
- [ ] Triggers Step 5 (calendar update) and Step 6 (property research) automatically on CONFIRMED events
- [ ] Displays an in-app notification: "✅ 123 Main St — Confirmed automatically"

> **Setup note:** To enable automatic status updates, configure API Nation to connect ShowingTime → Lead Connector (GHL) and set the outbound webhook URL to `http://[your-app-url]/webhook/showingtime`. See `docs/apination_setup.md` for step-by-step instructions.

### Step 4 — Add Tentative Calendar Blocks
For each showing in the session:
- [ ] Create a Google Calendar event titled: `🏠 TENTATIVE — Showing: [Street Address]`
- [ ] Event duration: assigned showing time window
- [ ] Add a travel block before each showing: title `🚗 Drive to [Street Address]` with duration = Google Maps travel time from prior stop
- [ ] Set all events as **tentative** (status: `TENTATIVE` in Google Calendar API)
- [ ] Add event description: property address, MLS number if known, client name
- [ ] Log all calendar event IDs to `session_state.json`

### Step 5 — Monitor & Apply Confirmation Status

Triggered by agent manually toggling status in the UI, or automatically by the GHL webhook.

**When a showing is marked CONFIRMED:**
- [ ] Update Google Calendar event: remove "TENTATIVE —" from title, set status to `CONFIRMED`
- [ ] Update associated travel block: remove "TENTATIVE" prefix
- [ ] Trigger Step 6 (property research) for that address automatically

**When a showing is marked DECLINED:**
- [ ] Delete the Google Calendar showing event for that address
- [ ] Delete the associated travel block
- [ ] Auto-reschedule: recalculate travel times and compress remaining showings to eliminate unnecessary gaps
- [ ] Display updated schedule in UI — prompt agent to confirm before applying calendar changes
- [ ] Flag any showings whose requested times have shifted and may need re-requesting via ShowingTime

### Step 6 — Property Research (On Confirmation)
For each confirmed showing address:
- [ ] Call `zillow_scraper.py` to pull listing data
- [ ] Generate a structured property summary:
  - Current list price and price history
  - Days on market
  - Beds / baths / square footage / lot size
  - Year built
  - Last sold date and price
  - Notable features from listing description
  - School district
  - Property tax estimate
  - Zillow Zestimate (if available)

**Disclosure Review:**
- [ ] Prompt agent to upload disclosure PDF via UI drag-and-drop (manual for v1)
- [ ] Run disclosure through Claude API (`disclosure_analyzer.py`): identify and flag red flags:
  - Water intrusion / basement moisture / flooding history
  - Roof age and condition
  - HVAC age and condition
  - Pest damage or infestation history
  - Foundation issues
  - Mold or air quality disclosures
  - Any "Yes" answers on seller disclosure that warrant follow-up
- [ ] Output a **Red Flag Summary** with exact disclosure language quoted and severity flagged: 🔴 Critical / 🟡 Monitor / 🟢 Minor

> **Future upgrade — Bridge API:** Bridge Interactive (owned by Zillow Group, part of ShowingTime+) provides direct MLS listing data via a RESO-certified API. When/if WMLS grants Bridge API access, replace `zillow_scraper.py` with `bridge_api_fetcher.py` for reliable MLS-direct listing data and potential disclosure document access. Confirm with developer whether Bridge API credentials are already provisioned through the existing IDX agreement. Placeholder credential: `BRIDGE_API_KEY` in `.env`. Contact: BridgeAPI@bridgeinteractive.com.

### Step 7 — Build Client-Facing Showing Day Page
Once all showings are confirmed (or agent manually triggers delivery):
- [ ] Generate a client-facing HTML page saved to `/output/client_[date]_[clientname]/index.html`
- [ ] Page includes:
  - Showing day date, schedule overview, and agent contact info (Jason O'Brien, PREMIERE Group)
  - Each confirmed property in order: address, photo (Zillow), showing time, Google Maps link
  - Property summary per address
  - Red flag disclosure summary (agent toggles visibility per property before sending)
  - Download link for disclosure PDF(s) if uploaded
- [ ] Generate shareable Google Calendar invite(s) the client can add to their own calendar (one event per confirmed showing, no travel blocks)
- [ ] Pre-fill client email from CRM lookup in Step 1
- [ ] Send page URL and calendar invite to client via Gmail using `gmail_sender.py`

### Step 8 — Session Complete
- [ ] All confirmed showings show no "TENTATIVE" prefix in calendar
- [ ] All declined showings removed from calendar
- [ ] Client page delivered (or saved for later)
- [ ] `session_state.json` reflects final status of every property
- [ ] Agent receives in-app summary: X confirmed, X declined, X pending

**Success Criteria:**
- [ ] Zero tentative events remain for fully resolved showings
- [ ] No unnecessary calendar gaps between confirmed showings
- [ ] Client page renders correctly and all links work
- [ ] All tool calls logged with success/failure in `run_log.json`
- [ ] Client email sourced from CRM, not manually typed

---

## 3. Agent Rules

### General Behavior
- Always read `session_state.json` at startup. If a session is in progress, resume from last known state — never restart from scratch.
- Display a status dashboard at the top of the UI at all times: session date, client name, property count, confirmed/declined/pending counts.
- Never modify Google Calendar events without explicit agent confirmation first, except for deletions triggered by a "Declined" status the agent just entered.
- Never send anything to the client without the agent explicitly clicking "Send to Client."
- Always preserve the full session in `session_state.json` — every property, every status change, every calendar event ID, every tool call result.

### Planning Requirements
Before executing any multi-step action (route calculation, calendar write, client delivery), output a brief plan:
```
PLAN:
1. [What I'm about to do]
2. [What API/tool I'm calling]
3. [What I expect to happen]
4. [What I'll do if it fails]
Proceed? (yes to continue)
```
For fully automated steps with no destructive action, skip the confirmation prompt but still log the plan to `run_log.json`.

### Error Handling & Self-Healing
For every tool call or API request:
1. **Attempt** the operation normally
2. **On failure:** log the error with full response body to `run_log.json`, display plain-English error in the UI
3. **Retry** up to 2 additional times with exponential backoff (5s, 15s)
4. **On 3rd failure:** mark the step as `FAILED` in `session_state.json`, present fallback option to the agent, and continue with degraded functionality
5. **Never crash silently.** Every failure must be visible in the UI.

### API Availability Fallbacks
| Service | If Available | If Unavailable |
|---|---|---|
| Lofty CRM | Pull client info automatically | Try GHL; else manual entry |
| GHL / Lead Connector | Pull client info + receive webhooks | Manual client entry; manual status toggles |
| API Nation webhook | Auto-update showing status | Agent toggles status manually in UI |
| Google Maps | Real-time travel time routing | Prompt agent to enter drive times manually |
| Zillow Scraper | Pull listing data + photos | Display "Data unavailable — enter manually" |
| Google Calendar | Create/update/delete events | Export `.ics` file for manual import |
| Gmail | Send client page + invite | Display copyable link + message draft |
| Bridge API *(future)* | Replace Zillow scraper with MLS-direct data | Stay on Zillow scraper |

### Session State Rules
- `session_state.json` is the single source of truth for all session data
- Write to it after every status change, calendar event creation, or tool call
- Must contain: session date, client object (name/email/phone/crm_source), all properties with status, all calendar event IDs, all tool call results
- Never delete `session_state.json` — archive completed sessions to `/sessions/archive/`

---

## 4. Tools

### Tool Table

| Tool | File | Purpose | Input | Output |
|---|---|---|---|---|
| CRM Client Lookup | `tools/crm_client_lookup.py` | Search Lofty then GHL for client by name | Client name string | Name, email, phone, crm_source |
| Route Optimizer | `tools/route_optimizer.py` | Optimal showing order + travel times | Addresses, start location, date/time | Ordered route, per-leg travel time, total duration |
| Google Calendar | `tools/calendar_manager.py` | Create, update, delete calendar events | Event details, credentials | Event ID, confirmation |
| API Nation Webhook | `tools/apination_webhook.py` | Receive ShowingTime status events via GHL | Incoming POST payload | Parsed status update (address, status, timestamp) |
| Zillow Scraper | `tools/zillow_scraper.py` | Primary listing data source | Property address | Listing dict (price, beds, baths, photos, history, Zestimate) |
| Disclosure Analyzer | `tools/disclosure_analyzer.py` | Analyze disclosure PDF for red flags via Claude API | PDF file path | Structured red flag report (JSON) |
| Client Page Builder | `tools/client_page_builder.py` | Generate static HTML showing day page | Session data, property summaries | `index.html` in `/output/` |
| Gmail Sender | `tools/gmail_sender.py` | Email client page link + calendar invite | Recipient email, message body | Send status |
| Session Logger | `tools/session_logger.py` | Read/write session state and run log | Key-value updates | Updated `session_state.json`, `run_log.json` |
| Bridge API Fetcher *(placeholder)* | `tools/bridge_api_fetcher.py` | MLS-direct listing data when Bridge API access confirmed | MLS number or address, `BRIDGE_API_KEY` | Listing dict, disclosure PDF path |
| ShowingTime API *(placeholder)* | `tools/showingtime_api.py` | Direct showing request submission if API access granted | Property address, time slot, credentials | Request status, confirmation number |

### Tool Development Rules
- Every tool must be independently runnable from the command line: `python tools/[tool].py --test`
- Every tool must return: `{"status": "success|failure", "data": ..., "error": null|"message"}`
- No tool should have side effects outside its declared scope
- Credentials always loaded from `.env` — never hardcoded
- Tools are stateless; all state lives in `session_state.json`

### MCP Servers
| Server | Purpose | Status |
|---|---|---|
| Google Calendar MCP | Calendar read/write | Use if available; fallback to `calendar_manager.py` with OAuth |
| Gmail MCP | Send client delivery emails | Use if available; fallback to `gmail_sender.py` |

### External APIs & Credentials
| API | Purpose | `.env` Key |
|---|---|---|
| Google Maps Distance Matrix | Travel time + route optimization | `GOOGLE_MAPS_API_KEY` |
| Google Calendar API | Calendar CRUD | `GOOGLE_CALENDAR_CREDENTIALS_JSON` |
| Gmail API | Send emails | `GMAIL_CREDENTIALS_JSON` |
| Lofty CRM API | Client contact lookup | `LOFTY_API_KEY` |
| GHL / Lead Connector API | Client contact lookup + webhook receiver | `GHL_API_KEY`, `GHL_LOCATION_ID` |
| ShowingTime API *(placeholder)* | Direct showing requests if access granted | `SHOWINGTIME_API_KEY` |
| Bridge API *(placeholder)* | MLS listing data when access confirmed | `BRIDGE_API_KEY` |

---

## 5. CRM Integration

Jason uses two overlapping CRM platforms: **Lofty** (IDX/client-facing, team-wide at PREMIERE Group) and **GHL / Lead Connector** (personal marketing automation). Both are integrated in v1 for client lookup only.

### v1 Scope — Client Lookup Only
`crm_client_lookup.py` search logic:
1. Search Lofty contacts by name (first + last)
2. If found → return name, email, phone; store `crm_source: "lofty"`
3. If not found → search GHL contacts by name
4. If found → return name, email, phone; store `crm_source: "ghl"`
5. If not found → present manual entry form; store `crm_source: "manual"`

Always display pulled contact details in the UI for agent confirmation. Never silently use CRM data.

### v2 Scope — Future CRM Actions (do not build in v1)
| Action | Platform | Trigger |
|---|---|---|
| Log showing activity note to contact record | Lofty + GHL | Session complete |
| Move buyer to "Toured Properties" pipeline stage | Lofty + GHL | Session complete |
| Trigger post-showing follow-up SMS/email sequence | GHL | Session complete |
| Flag contact as Homes for Heroes eligible | Lofty + GHL | Manual or on lookup |

### API Nation + GHL Webhook
API Nation connects ShowingTime → Lead Connector (GHL). When a seller confirms or declines in ShowingTime, GHL fires a webhook to ShowingDay, triggering automatic status updates — no manual toggling required.

**Configuration steps (see `docs/apination_setup.md`):**
1. Activate Lead Connector → ShowingTime integration in API Nation
2. In GHL, create a workflow: trigger on ShowingTime status event → webhook action
3. Set webhook URL to `http://[your-app-url]/webhook/showingtime`
4. `apination_webhook.py` parses incoming payload and updates session state

---

## 6. Project Context

### Who This Is For
Jason O'Brien — licensed REALTOR® and buyer's agent, PREMIERE Group at Real Broker LLC, Plainwell / Allegan County, West Michigan. Personal productivity tool. No multi-user auth needed for v1.

### Default Configuration
- **Default start address:** Plainwell, MI (exact address in `.env` as `DEFAULT_START_ADDRESS`)
- **Default max showing length:** 30 minutes (overridable per session and per property)
- **Default scheduling direction:** Start-loaded
- **Primary showing platform:** ShowingTime (manual mode until API confirmed)
- **Primary listing data:** Zillow scraper (Bridge API upgrade path documented)
- **CRM lookup order:** Lofty → GHL → manual

### Known Placeholders — Confirm Before Building
| Item | Status | Action |
|---|---|---|
| ShowingTime API | Unconfirmed | Contact ShowingTime support |
| Bridge API / MLS data | Placeholder | Confirm with developer; contact BridgeAPI@bridgeinteractive.com |
| Lofty API key | Needs confirmation | Check Lofty admin panel or contact Lofty support |
| GHL API key + Location ID | Available | GHL Settings → Integrations |
| API Nation webhook | Manual config needed | Follow `docs/apination_setup.md` after app is live |

### Market Context
- West Michigan rural/suburban market — properties 10–30+ minutes apart
- Showing windows on weekends typical (Saturday/Sunday 1–6 PM)
- Seller ShowingTime response times: immediate to several hours — app must be comfortable in a "waiting" state

### Homes for Heroes
Jason is affiliated with Homes for Heroes. In v2, flag Hero clients (healthcare, military, law enforcement, education, firefighter/EMS) so showing summaries and client pages can include relevant program notes.

---

## 7. File Structure

```
showingday/
├── CLAUDE.md                        ← This file
├── .env                             ← All credentials (never commit to git)
├── .env.example                     ← Credential template
├── app.py                           ← Main Flask/FastAPI entry point
├── session_state.json               ← Active session state (runtime)
├── run_log.json                     ← Tool call log (runtime)
│
├── tools/
│   ├── crm_client_lookup.py         ← Lofty → GHL → manual client lookup
│   ├── route_optimizer.py           ← Google Maps route + travel times
│   ├── calendar_manager.py          ← Google Calendar CRUD
│   ├── apination_webhook.py         ← Receive ShowingTime status via GHL webhook
│   ├── zillow_scraper.py            ← Primary listing data source
│   ├── disclosure_analyzer.py       ← Claude API: PDF red flag analysis
│   ├── client_page_builder.py       ← Generate client-facing HTML page
│   ├── gmail_sender.py              ← Send client delivery email
│   ├── session_logger.py            ← session_state.json + run_log.json I/O
│   ├── bridge_api_fetcher.py        ← PLACEHOLDER: MLS data via Bridge API
│   └── showingtime_api.py           ← PLACEHOLDER: Direct ShowingTime API
│
├── ui/
│   ├── index.html                   ← Agent-facing app UI
│   ├── style.css
│   └── app.js
│
├── docs/
│   └── apination_setup.md           ← API Nation + GHL webhook config guide
│
├── output/
│   └── client_[date]_[name]/        ← Client-facing pages
│       ├── index.html
│       └── disclosures/
│           └── [address].pdf
│
├── sessions/
│   └── archive/                     ← Completed sessions
│       └── [date]_[client]/
│           ├── session_state.json
│           └── run_log.json
│
├── tests/
│   └── test_tools.py
│
└── requirements.txt
```

---

## 8. UI Design Direction

**Agent-facing UI:** Premium ops tool. Dark-themed, map-forward, data-dense but clean. Dispatch board meets luxury real estate branding.

- **Color palette:** Deep navy `#0D1B2A` base, warm gold `#C9A84C` accents, clean white text
- **Typography:** Sharp display font (DM Serif Display or Playfair Display) for property addresses; clean mono or sans for times and data
- **Session start:** CRM lookup field is the first element on screen — name search with instant results, confirmation card showing pulled contact info
- **Route display:** Interactive Google Maps embed with numbered stop markers + sidebar showing sequence, times, and status badge per property
- **Status badges:** 🟡 Tentative / 🟢 Confirmed / 🔴 Declined / ⚪ Pending / 🔄 Auto-updated via webhook
- **Live webhook feed:** Subtle notification strip showing incoming status updates when API Nation is connected

**Client-facing page:** Lighter, warm, approachable. Curated itinerary feel — not a data dump. Client name at top, clean property cards with photos and times, single prominent "Add to My Calendar" button.

---

## 9. Iteration Log

| Run # | Date | Notes | Issues | Status |
|---|---|---|---|---|
| 1 | | Phase 1: Route planner + UI scaffold | | |
| 2 | | Phase 2: CRM client lookup (Lofty + GHL) | | |
| 3 | | Phase 3: Google Calendar integration | | |
| 4 | | Phase 4: Zillow scraper + disclosure analyzer | | |
| 5 | | Phase 5: Client page builder + Gmail send | | |
| 6 | | Phase 6: API Nation webhook receiver | | |
| 7 | | Phase 7: Bridge API swap-in (when access confirmed) | | |

---

## Build Order for Claude Code

Build in this exact sequence. Complete and test each phase before starting the next.

**Phase 1 — Core Route Planner**
1. Scaffold full project structure, `.env.example`, and `app.py`
2. Build `route_optimizer.py` using Google Maps Distance Matrix API
3. Build agent UI with address input, time window, and schedule direction controls
4. Display optimized route on embedded Google Map with sidebar schedule

**Phase 2 — CRM Client Lookup**
5. Build `crm_client_lookup.py` — Lofty first, GHL fallback, manual entry last
6. Add session start screen: client name search → confirmation card → proceed
7. Store client object (name, email, phone, crm_source) in `session_state.json`

**Phase 3 — Calendar Integration**
8. Build `calendar_manager.py` with Google Calendar OAuth
9. Implement tentative event creation (showing blocks + travel blocks)
10. Implement event update (confirmed) and delete (declined) logic
11. Add status toggle UI per property

**Phase 4 — Property Research**
12. Build `zillow_scraper.py` as primary listing data source
13. Build `disclosure_analyzer.py` using Claude API with PDF input
14. Add drag-and-drop disclosure upload to UI
15. Display property summary + red flag report on confirmation

**Phase 5 — Client Delivery**
16. Build `client_page_builder.py` — pre-fill client email from session state
17. Build `gmail_sender.py`
18. Add "Send to Client" button and preview modal in UI

**Phase 6 — Webhook Integration**
19. Build `apination_webhook.py` POST endpoint at `/webhook/showingtime`
20. Write `docs/apination_setup.md` with full API Nation + GHL configuration walkthrough
21. Test end-to-end: ShowingTime status change → API Nation → GHL → webhook → ShowingDay auto-update

**Phase 7 — Placeholders (build only when access confirmed)**
22. `bridge_api_fetcher.py` — swap in for `zillow_scraper.py` when Bridge API access granted
23. `showingtime_api.py` — direct showing request submission if ShowingTime API becomes available
