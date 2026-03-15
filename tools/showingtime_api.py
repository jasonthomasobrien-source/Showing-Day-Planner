"""
showingtime_api.py — ShowingDay Direct ShowingTime API (PLACEHOLDER)

FUTURE FEATURE — Direct showing request submission via ShowingTime API.

STATUS: PLACEHOLDER — API access not yet confirmed.
Action required: Contact ShowingTime support to confirm API availability.

Current default: Manual request mode (agent submits via ShowingTime app/portal).
ShowingTime status updates are received automatically via API Nation → GHL webhook.
See: tools/apination_webhook.py and docs/apination_setup.md

When ShowingTime API access is confirmed:
  1. Get API credentials from ShowingTime
  2. Set SHOWINGTIME_API_KEY in .env
  3. Implement submit_showing_request() and get_request_status() below
  4. Update app.py route /api/request-showing to use this module

CLI: python tools/showingtime_api.py --test
"""

import os
import json
import argparse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

SHOWINGTIME_API_KEY = os.getenv("SHOWINGTIME_API_KEY", "")
SHOWINGTIME_API_BASE_URL = "https://api.showingtime.com/v1"  # Verify with ShowingTime support


def submit_showing_request(
    address: str,
    mls_number: str = None,
    requested_date: str = None,
    requested_start_time: str = None,
    requested_end_time: str = None,
    agent_name: str = "Jason O'Brien",
    agent_phone: str = None,
    client_name: str = None,
    notes: str = None
) -> dict:
    """
    Submit a showing request directly to ShowingTime.

    Args:
        address: Property address.
        mls_number: MLS listing number (improves lookup accuracy).
        requested_date: Date string "YYYY-MM-DD".
        requested_start_time: Requested start time "HH:MM" (24-hour).
        requested_end_time: Requested end time "HH:MM" (24-hour).
        agent_name: Requesting agent's name.
        agent_phone: Requesting agent's phone.
        client_name: Buyer's name.
        notes: Any notes for the seller/listing agent.

    Returns:
        {
            "status": "success",
            "data": {
                "request_id": str,
                "confirmation_number": str,
                "status": "pending" | "confirmed" | "declined",
                "address": str
            },
            "error": null
        }

    TODO: Implement when ShowingTime API access is confirmed:
    ─────────────────────────────────────────────────────────
    import requests

    if not SHOWINGTIME_API_KEY or SHOWINGTIME_API_KEY.startswith("placeholder"):
        return {
            "status": "failure",
            "data": None,
            "error": "SHOWINGTIME_API_KEY not configured. Contact ShowingTime support."
        }

    headers = {
        "Authorization": f"Bearer {SHOWINGTIME_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "listingAddress": address,
        "mlsNumber": mls_number,
        "requestedDate": requested_date,
        "requestedStartTime": requested_start_time,
        "requestedEndTime": requested_end_time,
        "requestingAgent": {
            "name": agent_name,
            "phone": agent_phone
        },
        "buyerName": client_name,
        "notes": notes
    }

    resp = requests.post(
        f"{SHOWINGTIME_API_BASE_URL}/showings/request",
        json=payload,
        headers=headers,
        timeout=15
    )
    resp.raise_for_status()
    data = resp.json()

    return {
        "status": "success",
        "data": {
            "request_id": data.get("id"),
            "confirmation_number": data.get("confirmationNumber"),
            "status": data.get("status", "pending").lower(),
            "address": address
        },
        "error": None
    }
    ─────────────────────────────────────────────────────────
    """
    return {
        "status": "failure",
        "data": {
            "manual_checklist": _generate_manual_checklist(
                address, mls_number, requested_date,
                requested_start_time, requested_end_time,
                agent_name, agent_phone
            )
        },
        "error": (
            "ShowingTime API not yet configured. "
            "Use manual_checklist in data to submit via ShowingTime app/portal. "
            "Contact ShowingTime support to confirm API access."
        )
    }


def get_request_status(request_id: str) -> dict:
    """
    Get the current status of a showing request from ShowingTime.

    Args:
        request_id: ShowingTime request ID returned from submit_showing_request().

    Returns:
        {
            "status": "success",
            "data": {
                "request_id": str,
                "status": "pending" | "confirmed" | "declined",
                "confirmation_number": str | None,
                "notes": str | None
            },
            "error": null
        }

    TODO: Implement when ShowingTime API access is confirmed:
    ─────────────────────────────────────────────────────────
    import requests
    resp = requests.get(
        f"{SHOWINGTIME_API_BASE_URL}/showings/{request_id}",
        headers={"Authorization": f"Bearer {SHOWINGTIME_API_KEY}"},
        timeout=10
    )
    resp.raise_for_status()
    data = resp.json()
    return {
        "status": "success",
        "data": {
            "request_id": request_id,
            "status": data.get("status", "unknown").lower(),
            "confirmation_number": data.get("confirmationNumber"),
            "notes": data.get("notes")
        },
        "error": None
    }
    ─────────────────────────────────────────────────────────
    """
    return {
        "status": "failure",
        "data": None,
        "error": "ShowingTime API not yet configured."
    }


def _generate_manual_checklist(
    address, mls_number, date, start_time, end_time, agent_name, agent_phone
) -> str:
    """
    Generate a formatted, copyable ShowingTime request block for manual submission.
    Always available — no API required.
    """
    lines = [
        "═══════════════════════════════════════",
        "   SHOWINGTIME REQUEST",
        "═══════════════════════════════════════",
        f"Address:      {address or '—'}",
        f"MLS Number:   {mls_number or 'Unknown'}",
        f"Date:         {date or '—'}",
        f"Time Window:  {start_time or '—'} – {end_time or '—'}",
        f"Agent Name:   {agent_name or '—'}",
        f"Agent Phone:  {agent_phone or '—'}",
        "═══════════════════════════════════════",
        "Submit at: showingtime.com or ShowingTime mobile app"
    ]
    return "\n".join(lines)


# ── CLI ────────────────────────────────────────────────────────────────────────

def _run_tests():
    print("Testing showingtime_api (placeholder)...")

    result = submit_showing_request(
        address="1842 Lincoln Rd, Allegan, MI 49010",
        mls_number="24012345",
        requested_date="2026-03-21",
        requested_start_time="13:00",
        requested_end_time="13:30",
        agent_name="Jason O'Brien"
    )
    assert result["status"] == "failure", "Test failed: should return failure until configured"
    assert "manual_checklist" in result.get("data", {}), "Test failed: should include manual_checklist"
    assert "1842 Lincoln Rd" in result["data"]["manual_checklist"], "Test failed: address not in checklist"
    print("  PASS — returns failure with manual_checklist when not configured")
    print("\n  Manual checklist output:")
    print(result["data"]["manual_checklist"])

    print("\nAll showingtime_api tests passed.")
    print("(Note: ShowingTime API is a placeholder — contact ShowingTime support to enable)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ShowingDay ShowingTime API (Placeholder)")
    parser.add_argument("--test", action="store_true", help="Run self-tests")
    args = parser.parse_args()

    if args.test:
        _run_tests()
    else:
        print(__doc__)
