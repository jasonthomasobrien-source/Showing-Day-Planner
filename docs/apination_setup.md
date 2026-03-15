# API Nation + GHL Webhook Setup Guide

**ShowingDay — Automatic Showing Status Updates**

This guide walks you through connecting ShowingTime → API Nation → GoHighLevel (GHL/Lead Connector) → ShowingDay so that showing confirmations and declines update automatically in your session — no manual status toggling required.

---

## Overview

```
ShowingTime (seller confirms/declines)
    ↓
API Nation (middleware connector)
    ↓
GHL / Lead Connector (workflow automation)
    ↓ POST /webhook/showingtime
ShowingDay (auto-updates session state)
```

When this is configured:
- Seller confirms in ShowingTime → ShowingDay shows "🟢 Confirmed" and triggers property research
- Seller declines in ShowingTime → ShowingDay shows "🔴 Declined" and removes calendar event

---

## Prerequisites

- [ ] ShowingDay app is running and accessible at a URL (local: `http://localhost:5000`, or deployed)
- [ ] GHL (GoHighLevel / Lead Connector) account with API access
- [ ] `GHL_API_KEY` and `GHL_LOCATION_ID` set in `.env`
- [ ] API Nation account with ShowingTime integration enabled

---

## Step 1 — Confirm ShowingTime is Connected to API Nation

1. Log in to [API Nation](https://www.apination.com/)
2. Navigate to **Integrations**
3. Search for **ShowingTime** in the available connectors
4. If not yet activated: click **Activate** and connect your ShowingTime account
5. Verify the integration can read showing status events

> **Screenshot placeholder:** API Nation → Integrations → ShowingTime activated

---

## Step 2 — Connect ShowingTime → Lead Connector in API Nation

1. In API Nation, create a new **Automation/Zap**
2. **Trigger:** ShowingTime — "Showing Status Changed" (or equivalent event)
3. **Action:** Lead Connector (GHL) — "Send Webhook" or "Create/Update Contact"
4. Map the fields:
   - ShowingTime address → GHL contact field or webhook payload field
   - ShowingTime status (confirmed/declined) → GHL payload

> **Screenshot placeholder:** API Nation automation: ShowingTime trigger → GHL action

---

## Step 3 — Create a GHL Workflow to Fire the Webhook

1. Log in to GoHighLevel (your Lead Connector account)
2. Navigate to **Automation → Workflows**
3. Click **+ New Workflow**
4. Set the **Trigger:**
   - Trigger type: **Webhook** (from API Nation) or **Custom Trigger**
   - Configure to receive the ShowingTime status event from API Nation
5. Add an **Action:** Webhook / HTTP Request
   - Method: `POST`
   - URL: `http://[your-app-url]/webhook/showingtime`
     - Local: `http://localhost:5000/webhook/showingtime`
     - If using a tunnel (see Step 5): `https://[tunnel-url]/webhook/showingtime`
   - Headers:
     ```
     Content-Type: application/json
     ```
   - Body (JSON): Map GHL fields to this structure:
     ```json
     {
       "type": "showingtime_status",
       "data": {
         "address": "{{contact.address or custom_field.showing_address}}",
         "status": "{{custom_field.showing_status}}",
         "confirmation_number": "{{custom_field.confirmation_number}}",
         "timestamp": "{{now}}",
         "notes": "{{custom_field.access_notes}}"
       }
     }
     ```
   - Adjust field names based on how API Nation maps the ShowingTime data into GHL

6. Click **Save** and **Publish** the workflow

> **Screenshot placeholder:** GHL Workflow: Webhook trigger → HTTP action → ShowingDay URL

---

## Step 4 — Configure the Webhook URL in ShowingDay

In your `.env` file, no additional configuration is needed — ShowingDay automatically listens at `/webhook/showingtime`.

Verify the endpoint is active by sending a test POST:

```bash
curl -X POST http://localhost:5000/webhook/showingtime \
  -H "Content-Type: application/json" \
  -d '{
    "type": "showingtime_status",
    "data": {
      "address": "1842 Lincoln Rd, Allegan, MI 49010",
      "status": "confirmed",
      "confirmation_number": "TEST-001",
      "timestamp": "2026-03-21T14:00:00Z"
    }
  }'
```

**Expected response:**
```json
{
  "status": "ok",
  "message": "Status updated: 1842 Lincoln Rd, Allegan, MI 49010 → confirmed"
}
```

If the property is in your active session, you'll see it auto-update in the UI.

---

## Step 5 — Expose Local App to the Internet (for testing)

GHL needs to reach your ShowingDay app. During local development, use a tunnel:

### Option A — ngrok (recommended for testing)

```bash
# Install ngrok: https://ngrok.com/download
ngrok http 5000
```

Copy the HTTPS URL (e.g., `https://abc123.ngrok-free.app`) and use it as your webhook URL in Step 3.

### Option B — Vercel deployment

Deploy ShowingDay to Vercel for a stable public URL:
```bash
vercel deploy
```

Use the Vercel URL as your webhook URL. Note: Vercel serverless functions require session state to be stored in a database (Vercel KV) — see `docs/developer_handoff.md` for details.

---

## Step 6 — Test End-to-End

1. Start a showing session in ShowingDay (set up client, addresses, optimize route)
2. Go to ShowingTime and find one of the properties you're requesting
3. Have the test seller confirm or decline
4. Watch ShowingDay — within a few seconds, the status badge should update and a notification should appear in the webhook strip at the top

**If the status doesn't update:**
- Check GHL workflow execution logs
- Check API Nation automation history
- Verify your webhook URL is correct and reachable
- Check ShowingDay console for incoming POST requests (run in debug mode: `FLASK_ENV=development python app.py`)
- Check `run_log.json` for webhook events

---

## Payload Format Reference

ShowingDay's `apination_webhook.py` is flexible and tries multiple field name conventions. The minimum required payload is:

```json
{
  "address": "property address string",
  "status": "confirmed | declined | pending | requested"
}
```

Full payload with all fields:
```json
{
  "type": "showingtime_status",
  "data": {
    "address": "1842 Lincoln Rd, Allegan, MI 49010",
    "status": "confirmed",
    "confirmation_number": "ST-2026-84721",
    "timestamp": "2026-03-21T14:32:00Z",
    "notes": "Keybox on front door. Dog in yard."
  }
}
```

**Status values accepted:**
| ShowingTime Value | ShowingDay Normalized | Behavior |
|---|---|---|
| confirmed, approved, accepted | confirmed | Triggers property research, updates calendar |
| declined, denied, rejected, cancelled | declined | Removes calendar event |
| pending | pending | Updates badge only |
| requested | requested | Updates badge only |

---

## Troubleshooting

| Problem | Likely Cause | Fix |
|---|---|---|
| Webhook not received | App not accessible from internet | Set up ngrok tunnel or deploy to Vercel |
| Status not updating in UI | Property address doesn't match session | Verify exact address format matches what's in your session |
| GHL workflow not firing | Workflow not published or trigger misconfigured | Check GHL workflow is Published and trigger is correct |
| API Nation automation not running | ShowingTime not connected or event not triggered | Check API Nation automation history |
| `{"status": "failure"}` response | Malformed payload | Check payload structure against reference above |

---

## Notes

- ShowingDay accepts both flat payloads and nested `{"data": {...}}` structures
- Address matching is case-insensitive and uses substring matching
- All webhook events are logged to `run_log.json`
- The webhook strip notification in the UI disappears after 8 seconds but the status change persists
