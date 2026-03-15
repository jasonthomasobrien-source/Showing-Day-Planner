"""
calendar_manager.py — ShowingDay Google Calendar Manager

Creates, updates, and deletes Google Calendar events for showing sessions.
Each showing gets two events:
  1. The showing itself:  "🏠 TENTATIVE — Showing: [Address]"
  2. A travel block:      "🚗 Drive to [Address]"

On confirmation, TENTATIVE prefix is removed and event status → CONFIRMED.
On decline, both events are deleted.

OAuth flow: credentials loaded from GOOGLE_CALENDAR_CREDENTIALS_JSON in .env.
Token is cached in token_calendar.json (gitignored) after first auth.

CLI: python tools/calendar_manager.py --test

TODO: Complete OAuth implementation — see get_credentials() below.
"""

import os
import json
import argparse
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

CALENDAR_CREDENTIALS_JSON = os.getenv("GOOGLE_CALENDAR_CREDENTIALS_JSON", "")
CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar"]
TOKEN_FILE = BASE_DIR / "token_calendar.json"

# Target calendar — uses primary calendar by default.
# Can be overridden with a specific calendar ID.
CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "primary")


# ── OAuth credentials ─────────────────────────────────────────────────────────

def get_credentials():
    """
    Get (or refresh) Google OAuth2 credentials for Calendar API access.

    TODO: Complete implementation:
      1. Parse GOOGLE_CALENDAR_CREDENTIALS_JSON from .env into a credentials dict
      2. Check if token_calendar.json exists and is valid
      3. If expired, refresh using refresh_token
      4. If no token, run the OAuth2 browser flow and save token
      5. Return the credentials object

    Requires: google-auth, google-auth-oauthlib, google-auth-httplib2

    Example (uncomment when ready):
    ─────────────────────────────────
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request

    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), CALENDAR_SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            creds_data = json.loads(CALENDAR_CREDENTIALS_JSON)
            flow = InstalledAppFlow.from_client_config(creds_data, CALENDAR_SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return creds
    ─────────────────────────────────
    """
    # TODO: Implement OAuth flow (see docstring above)
    raise NotImplementedError(
        "Google Calendar OAuth not yet configured. "
        "Set GOOGLE_CALENDAR_CREDENTIALS_JSON in .env and implement get_credentials(). "
        "See tools/calendar_manager.py for implementation guide."
    )


def _get_calendar_service():
    """
    Build and return the Google Calendar API service client.
    TODO: Uncomment when get_credentials() is implemented.
    """
    # from googleapiclient.discovery import build
    # creds = get_credentials()
    # return build("calendar", "v3", credentials=creds)
    raise NotImplementedError("Calendar service requires get_credentials() implementation")


# ── Event creation ────────────────────────────────────────────────────────────

def create_showing_events(route: list, client_name: str, session_date: str) -> dict:
    """
    Create tentative Google Calendar events for all showings and travel blocks.

    For each stop in the route, creates:
      - Travel block (if not first stop): "🚗 Drive to [Address]"
      - Showing block: "🏠 TENTATIVE — Showing: [Address]"

    Args:
        route: List of route stop dicts from route_optimizer.py
        client_name: Client's full name (included in event description)
        session_date: Date string "YYYY-MM-DD"

    Returns:
        {
            "status": "success",
            "data": {
                "created_events": [
                    {"event_id": str, "type": "showing"|"travel", "address": str}
                ]
            },
            "error": null
        }

    TODO: Implement calendar event creation:
    ─────────────────────────────────────────
    service = _get_calendar_service()
    created = []

    for stop in route:
        address = stop["address"]
        date_prefix = session_date  # "2026-03-21"

        # Parse times from route (format: "1:00 PM" → combine with session_date)
        showing_start_dt = datetime.strptime(
            f"{session_date} {stop['showing_start']}", "%Y-%m-%d %I:%M %p"
        )
        showing_end_dt = datetime.strptime(
            f"{session_date} {stop['showing_end']}", "%Y-%m-%d %I:%M %p"
        )

        # Create travel block (if not first stop)
        if stop.get("order", 1) > 1 and stop.get("travel_to_next_minutes"):
            travel_end = showing_start_dt
            travel_start = travel_end - timedelta(minutes=stop["travel_to_next_minutes"])
            travel_event = {
                "summary": f"🚗 TENTATIVE — Drive to {address.split(',')[0]}",
                "description": f"Travel to showing at {address}\nClient: {client_name}",
                "start": {"dateTime": travel_start.isoformat(), "timeZone": "America/Detroit"},
                "end": {"dateTime": travel_end.isoformat(), "timeZone": "America/Detroit"},
                "status": "tentative",
                "reminders": {"useDefault": False}
            }
            travel_result = service.events().insert(calendarId=CALENDAR_ID, body=travel_event).execute()
            created.append({"event_id": travel_result["id"], "type": "travel", "address": address})

        # Create showing block
        showing_event = {
            "summary": f"🏠 TENTATIVE — Showing: {address.split(',')[0]}",
            "description": f"Showing at {address}\nClient: {client_name}\nStatus: Tentative",
            "start": {"dateTime": showing_start_dt.isoformat(), "timeZone": "America/Detroit"},
            "end": {"dateTime": showing_end_dt.isoformat(), "timeZone": "America/Detroit"},
            "status": "tentative",
            "location": address,
            "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": 30}]}
        }
        show_result = service.events().insert(calendarId=CALENDAR_ID, body=showing_event).execute()
        created.append({"event_id": show_result["id"], "type": "showing", "address": address})

    return {"status": "success", "data": {"created_events": created}, "error": None}
    ─────────────────────────────────────────
    """
    # TODO: Remove this stub and uncomment implementation above
    return {
        "status": "failure",
        "data": None,
        "error": "Google Calendar not yet configured. See tools/calendar_manager.py."
    }


def confirm_event(event_id: str, address: str) -> dict:
    """
    Mark a showing as confirmed:
      - Remove "TENTATIVE — " prefix from title
      - Set event status to "confirmed"

    Args:
        event_id: Google Calendar event ID (from session_state.json)
        address: Property address (for display purposes)

    TODO: Implement:
    ─────────────────
    service = _get_calendar_service()
    event = service.events().get(calendarId=CALENDAR_ID, eventId=event_id).execute()
    event["summary"] = event["summary"].replace("🏠 TENTATIVE — Showing:", "🏠 Showing:").replace("🚗 TENTATIVE — Drive", "🚗 Drive")
    event["status"] = "confirmed"
    updated = service.events().update(calendarId=CALENDAR_ID, eventId=event_id, body=event).execute()
    return {"status": "success", "data": {"event_id": updated["id"]}, "error": None}
    ─────────────────
    """
    return {
        "status": "failure",
        "data": None,
        "error": "Google Calendar not yet configured."
    }


def decline_event(event_id: str, address: str) -> dict:
    """
    Delete a showing event (and its travel block) when a showing is declined.

    Args:
        event_id: Google Calendar event ID to delete
        address: Property address (for logging)

    TODO: Implement:
    ─────────────────
    service = _get_calendar_service()
    service.events().delete(calendarId=CALENDAR_ID, eventId=event_id).execute()
    return {"status": "success", "data": {"deleted_event_id": event_id}, "error": None}
    ─────────────────
    """
    return {
        "status": "failure",
        "data": None,
        "error": "Google Calendar not yet configured."
    }


def export_ics(route: list, client_name: str, session_date: str) -> dict:
    """
    Fallback: Export showing events as an .ics file for manual calendar import.
    Returns the ICS content as a string.

    This is used when Google Calendar API is unavailable.
    """
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//ShowingDay//EN"]

    for stop in route:
        address = stop["address"]
        # Parse times
        try:
            start_dt = datetime.strptime(
                f"{session_date} {stop['showing_start']}", "%Y-%m-%d %I:%M %p"
            )
            end_dt = datetime.strptime(
                f"{session_date} {stop['showing_end']}", "%Y-%m-%d %I:%M %p"
            )
        except ValueError:
            continue

        uid = f"showing-{session_date}-{stop['order']}@showingday"
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTART:{start_dt.strftime('%Y%m%dT%H%M%S')}",
            f"DTEND:{end_dt.strftime('%Y%m%dT%H%M%S')}",
            f"SUMMARY:Showing: {address.split(',')[0]}",
            f"DESCRIPTION:Property: {address}\\nClient: {client_name}",
            f"LOCATION:{address}",
            "STATUS:TENTATIVE",
            "END:VEVENT"
        ]

    lines.append("END:VCALENDAR")
    ics_content = "\r\n".join(lines)

    return {
        "status": "success",
        "data": {"ics_content": ics_content},
        "error": None
    }


# ── CLI ────────────────────────────────────────────────────────────────────────

def _run_tests():
    print("Testing calendar_manager (stub mode)...")

    # Test ICS export (this is fully functional as a fallback)
    mock_route = [
        {
            "order": 1,
            "address": "1842 Lincoln Rd, Allegan, MI 49010",
            "showing_start": "1:00 PM",
            "showing_end": "1:30 PM",
            "travel_to_next_minutes": 22
        },
        {
            "order": 2,
            "address": "728 Oak Grove Rd, Plainwell, MI 49080",
            "showing_start": "1:52 PM",
            "showing_end": "2:22 PM",
            "travel_to_next_minutes": None
        }
    ]

    result = export_ics(mock_route, "Sarah Johnson", "2026-03-21")
    assert result["status"] == "success", f"ICS export test failed: {result}"
    assert "BEGIN:VCALENDAR" in result["data"]["ics_content"], "ICS test failed: missing VCALENDAR"
    assert "Showing: 1842 Lincoln Rd" in result["data"]["ics_content"], "ICS test failed: missing event"
    print("  PASS — export_ics() generates valid ICS content")

    # Test that stubbed calendar functions return failure gracefully
    result2 = create_showing_events(mock_route, "Sarah Johnson", "2026-03-21")
    assert result2["status"] == "failure", "Expected failure for unimplemented calendar"
    print("  PASS — create_showing_events() returns failure gracefully when not configured")

    print("\nAll calendar_manager tests passed.")
    print("(Note: Google Calendar OAuth is stubbed — implement get_credentials() to enable)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ShowingDay Calendar Manager")
    parser.add_argument("--test", action="store_true", help="Run self-tests")
    args = parser.parse_args()

    if args.test:
        _run_tests()
    else:
        print("calendar_manager.py — use --test to run tests")
        print("Google Calendar API requires OAuth setup. See get_credentials() in this file.")
