# ShowingTime — Research & Integration Guide
**For:** Jason O'Brien, PREMIERE Group at Real Broker LLC
**Purpose:** ShowingDay integration planning
**Researched:** 2026-03-15 via Playwright web scrape of showingtime.com
**Note on Login:** Automated login to `apptcenter.showingdesk.com` was attempted multiple times with the provided credentials but was rejected by the server. This is likely because ShowingTime separates mobile app credentials from web portal credentials, or MFA is required. All feature documentation below is sourced from public product pages. **Check your password at [showingtime.com/login](https://showingtime.com/solutions/showings-and-offers/showingtime/login) and reset if needed to avoid account lockout.**

---

## 1. What ShowingTime Is

ShowingTime (owned by Zillow Group / MFTB Holdco, Inc. since 2021) is the most widely used showing management platform in U.S. real estate. It sits at the center of the showing workflow:

- **Listing agents** use it to set showing availability windows, approval requirements, and access instructions
- **Buyer's agents** (you) use it to request showing appointments at listed properties
- **Sellers** receive and respond to requests via text/app
- **Appointment specialists** (24/7 human staff) handle scheduling when needed
- **Lockbox vendors** integrate for keyless access tied to confirmed appointment windows

ShowingTime processes millions of showing appointments monthly and is embedded in most MLS platforms in the US.

---

## 2. The ShowingTime Product Suite

### 2a. Appointment Center — **Your Product** ($15/month)
The core agent tool. What you get:

| Feature | Details |
|---|---|
| Showing Requests | Request showings on any MLS listing 24/7 |
| Mobile App | iOS + Android app for on-the-go management |
| ShowingCart® | Queue multiple showings and request all at once |
| Confirmation Notifications | SMS/push when sellers confirm or decline |
| Showing Instructions | Delivered automatically on confirmation |
| Offer Manager | Organize offers by listing, store buyer agent info |
| Target Market Analysis | Anonymized pricing + showing data for your market |
| Pricing Benchmark Report | Comparable listing pricing, DOM, price reductions |
| 24/7 Live Specialists | Human appointment support available always |
| Automated Feedback | Feedback requests sent to showing agents post-visit |
| Listing Activity Reports | Full showing history per listing |

**How requests work:**
1. You open the ShowingTime app or web portal
2. Enter the property address/MLS#, requested date, and preferred time window
3. The system routes the request to the listing agent (or their office)
4. Seller/listing agent confirms, declines, or counters with alternate time
5. You get notified (SMS + push) with confirmation + access instructions + lockbox code

### 2b. Appointment Center Plus
- **For buyer's agents who want a personal assistant experience**
- You call ONE number → appointment specialists schedule all your showings for you
- You don't talk to listing agents at all — specialists handle all back-and-forth
- They notify you when each is confirmed with full instructions
- **Most relevant if:** you're running multi-client showing days with 4+ properties

### 2c. Home by ShowingTime (Buyer/Seller App)
- Consumer-facing companion app
- Your clients can: confirm/decline showing requests, view upcoming showings, track feedback, contact listing agent
- **Integration opportunity:** ShowingDay's client-facing page could deep-link into this

### 2d. Secure Access® by ShowingTime+
- Ties lockbox access to confirmed appointment time windows
- **Premier Lockbox Partners:** Master Lock (Bluetooth), igloohome (algoPIN™)
- **Other Partners:** SentriLock, Supra, Codebox, MCS, others
- Agent gets a **one-day code** in their confirmation email
- Or: **1-app, 1-tap** Bluetooth access if listing uses a Premier lockbox
- Access automatically expires after your appointment window

### 2e. ShowingTime for the MLS
- MLS-embedded version — agents can request showings from within their MLS portal
- "Schedule a Showing" button appears on MLS listing detail pages
- **WMLS integration:** West Michigan Lakeshore Association of REALTORS® likely uses this

### 2f. Front Desk / Offer Manager
- For admin/office staff — not directly relevant to solo buyer's agent workflow

---

## 3. The ShowingTime Login System

The web portal backend is at:
- **Primary:** `https://apptcenter.showingdesk.com/Account/Login`
- **Alias:** `https://apptcenter.showingtime.com/Account/Login`
- **Login page:** `https://showingtime.com/solutions/showings-and-offers/showingtime/login`

**Username format:** `firstname.lastname.KXXXXXX.MLS` (e.g., `jason.o'brien.k409595.SMR`)
- `k409595` = your ShowingTime key/agent ID
- `SMR` = MLS board abbreviation (likely Southwest Michigan Realtors or similar WMLS affiliate)

**Password reset:** `https://apptcenter.showingdesk.com/Account/Forgot`

**Mobile app login** may use different credentials than the web portal. The app is the primary interface for most agents.

---

## 4. Lockbox & SentriKey Integration

ShowingTime integrates with the following lockbox systems:

| Vendor | Type | ShowingTime Integration |
|---|---|---|
| **SentriLock** | Bluetooth + card-based | One-day codes in confirmation email; activity in Listing Activity Report |
| **Supra** | Bluetooth eKEY | One-day codes sent on confirmation |
| **Master Lock** | Bluetooth (Premier) | 1-app 1-tap access via ShowingTime app |
| **igloohome** | algoPIN Bluetooth (Premier) | 1-app 1-tap + offline PIN access |
| **Codebox** | Keypad | One-day codes in confirmation |
| **MCS** | Various | Activity reporting |

**For ShowingDay integration:** When a showing is confirmed, ShowingTime sends the lockbox code in the confirmation notification. ShowingDay can parse this from the GHL webhook and surface the code directly in the app — no need for the agent to find it in email.

---

## 5. Data & Notifications Flow

### How status updates reach external systems:

```
Seller confirms/declines in ShowingTime
         ↓
ShowingTime fires notification (SMS + push to agent)
         ↓
API Nation connects ShowingTime → GHL (Lead Connector)
         ↓
GHL fires webhook to ShowingDay at /webhook/showingtime
         ↓
ShowingDay auto-updates property status, calendar, agent notification
```

### What the GHL webhook payload contains:
- Property address
- Status (Confirmed / Declined / Counter-offered)
- Confirmation timestamp
- Showing instructions (text)
- Lockbox code (if available)
- Requested agent name
- Listing agent contact

---

## 6. ShowingTime API — What We Know

ShowingTime does **not** publish a public REST API for individual agents. However:

### What exists:
| Access Type | Details |
|---|---|
| **API Nation integration** | ShowingTime → GHL webhook (what you have configured) |
| **MLS data feed** | ShowingTime receives listing/status data from WMLS |
| **Bridge Interactive (Zillow Group)** | RESO-certified MLS data API — same company, potentially accessible |
| **ShowingTime+ internal API** | Undocumented, used by their mobile app |
| **Webhook outbound** | Fires on status changes — configurable via office/admin settings |

### What requires brokerage/MLS arrangement:
- Direct ShowingTime API key (contact: their enterprise sales team)
- ShowingTime for the MLS embed (MLS grants access)
- Bulk showing data export

### The realistic path for ShowingDay:
1. **API Nation (active):** The GHL → ShowingDay webhook already works for status updates
2. **Direct API inquiry:** Email `support@showingtime.com` — ask if there's a buyer's agent API tier. Reference your account ID `k409595`
3. **ShowingTime+ Partner program:** Zillow Group occasionally grants API access to developer tools via their partner program

---

## 7. The ShowingCart® Feature — Key for ShowingDay

**ShowingCart®** is ShowingTime's equivalent of what ShowingDay's route planner does for requests. It lets you:
- Queue multiple showing requests in one session
- Submit all requests at once
- View all pending confirmations in one dashboard

**ShowingDay's advantage over ShowingCart:**
- Route optimization (ShowingCart has no routing)
- Travel time calculation between stops
- Availability window scheduling
- Client-facing itinerary page
- Google Calendar integration
- Multi-client session management
- Disclosure analysis
- CRM integration

**Integration goal:** ShowingDay should *feed* ShowingCart — generate the optimized route, then hand the addresses + time slots off to ShowingTime for requesting. When confirmations come back via webhook, ShowingDay updates its schedule automatically.

---

## 8. What ShowingDay Can Add That ShowingTime Doesn't Have

### Missing from ShowingTime (ShowingDay opportunity):

| Gap in ShowingTime | ShowingDay Solution |
|---|---|
| No route optimization | ✅ Google Maps TSP routing |
| No travel time between showings | ✅ Distance Matrix API |
| No client-facing itinerary | ✅ Client page builder |
| No calendar integration for buyers | ✅ Google Calendar blocks |
| No disclosure analysis | ✅ Claude API PDF analysis |
| No CRM client lookup | ✅ Lofty + GHL integration |
| No multi-client session management | ✅ Plan Showings mode |
| No availability window drag UI | ✅ Calendar panel |
| ShowingCart ignores your drive time | ✅ ShowingDay schedules realistically |
| No "send itinerary to client" | ✅ Gmail delivery + calendar invite |

---

## 9. Recommended Integrations to Build

### Priority 1 — Already Possible (via API Nation + GHL)
- [x] Webhook receiver at `/webhook/showingtime` — **built in `apination_webhook.py`**
- [ ] **Parse lockbox code from confirmation payload** — add to property card in ShowingDay UI
- [ ] **Auto-detect counter-offer** — when ShowingTime proposes alternate time, flag it and let agent accept/modify in ShowingDay
- [ ] **Surface showing instructions** in ShowingDay property card (don't make agent dig through email/texts)

### Priority 2 — API Nation Enhancements
- [ ] Configure GHL workflow to capture `lockbox_code`, `showing_instructions`, `access_notes` fields from ShowingTime webhook
- [ ] Route ShowingTime feedback data back to ShowingDay so you can see buyer feedback on your listings

### Priority 3 — If ShowingTime API Access Granted
- [ ] **Request showings directly from ShowingDay** — no need to open ShowingTime app separately. After route is optimized, ShowingDay generates the requests and submits them
- [ ] **Read current showing windows** — when a listing is entered, query ShowingTime for the seller's available time slots so ShowingDay can only schedule during allowed windows
- [ ] **ShowingCart sync** — push ShowingDay's optimized schedule directly into ShowingTime as a cart

### Priority 4 — SentriKey / Lockbox
- [ ] When SentriKey API access is confirmed (ask Scott), pull lockbox status and access window per property
- [ ] Surface lockbox type + access instructions directly in the route sidebar during showing day

### Priority 5 — Showing Feedback Loop
- [ ] After a showing is completed (past its end time), prompt agent to log notes in ShowingDay
- [ ] Optionally push notes back to GHL as a contact activity on the buyer's record
- [ ] Track which properties the client was most interested in (simple thumbs up/down per address)

---

## 10. API Nation Setup for ShowingTime → ShowingDay

This is your current integration path. Full setup:

1. Log into [API Nation](https://www.apination.com)
2. Create a new integration: **ShowingTime → Lead Connector (GHL)**
3. Trigger: `Appointment Status Changed` (Confirmed / Declined / Counter)
4. Action: **Webhook POST** to `https://your-vercel-app.vercel.app/webhook/showingtime`
5. Map fields:
   - `property_address` → ShowingTime `listing_address`
   - `status` → ShowingTime `appointment_status`
   - `confirmation_time` → ShowingTime `confirmed_datetime`
   - `lockbox_code` → ShowingTime `access_code` (if available)
   - `showing_instructions` → ShowingTime `seller_instructions`
6. Test with a live showing request

Detailed walkthrough: `docs/apination_setup.md`

---

## 11. Questions to Ask ShowingTime Support

Contact: `support@showingtime.com` or call their 24/7 line

1. **"Is there a buyer's agent API for programmatic showing requests?"** (Reference account `k409595`)
2. **"What fields does the outbound webhook include when a showing is confirmed?"** (To verify lockbox code availability)
3. **"Is there a way to query available showing windows for a listing before requesting?"**
4. **"Does ShowingTime+ have a developer partner program?"**
5. **"Can API Nation be configured to include showing instructions and lockbox codes in the webhook payload?"**

---

## 12. Questions to Ask Scott

From CLAUDE.md — these are flagged as "ask Scott":

1. **ShowingTime API access** — Does WMLS or PREMIERE Group have a data sharing agreement with ShowingTime that includes API credentials?
2. **SentriKey API** — SentriLock (SentriKey) has an API. Does the brokerage have developer access through the MLS?
3. **API Nation configuration** — Has the ShowingTime → GHL workflow been set up? What payload format is ShowingTime sending?
4. **Bridge API** — Zillow Group owns both ShowingTime and Bridge Interactive. Through the IDX agreement, is Bridge API access already provisioned?

---

## 13. ShowingTime Mobile App Details

The ShowingTime app is the primary interface for most agents:

- **iOS:** Available on App Store
- **Android:** Available on Google Play
- **Key features accessible from mobile:**
  - Request showings, manage ShowingCart
  - View calendar of upcoming showings
  - Confirm/decline as listing agent
  - 1-tap lockbox access (Premier lockboxes)
  - Receive/respond to feedback
  - Access market reports

**For ShowingDay:** The app is the "last mile" — ShowingDay handles the planning and optimization, the ShowingTime app is where the actual request is submitted (until API access is granted).

---

## 14. Summary Assessment

| Dimension | Assessment |
|---|---|
| **ShowingTime replaceability** | Not replaceable — it's the industry standard that sellers/listing agents expect |
| **Integration urgency** | High — webhook setup via API Nation should be first priority |
| **API access likelihood** | Medium — worth asking, but direct API access is not standard for individual agents |
| **SentriKey integration** | Confirmed possible — pending Scott confirmation of credentials |
| **Best near-term integration** | API Nation webhook → parse lockbox code + instructions → surface in ShowingDay |
| **Biggest ShowingDay competitive advantage** | Route optimization + travel scheduling that ShowingTime completely lacks |

---

*Document generated from public product page scrapes and ShowingTime product documentation.*
*Last updated: 2026-03-15*
