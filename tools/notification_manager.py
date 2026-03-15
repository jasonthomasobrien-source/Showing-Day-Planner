"""
notification_manager.py — ShowingDay Notification Stub

Sends agent and client notifications on showing status changes.
Currently stubbed — delivery requires ShowingTime/SentriKey API access.

Status: PENDING API CONFIRMATION — contact Scott re: ShowingTime + SentriKey notification webhooks.

Supported triggers: requested, confirmed, rescheduled, canceled
Delivery channels: sms (via Twilio stub), email (via Gmail stub)

CLI: python tools/notification_manager.py --test
"""

import sys
import json
import argparse


def notify_agent(trigger: str, property_address: str, session_data: dict, channels: list) -> dict:
    """
    Notify the agent of a status change.

    Args:
        trigger: One of 'requested', 'confirmed', 'rescheduled', 'canceled'
        property_address: The address of the property whose status changed
        session_data: Full session_state dict for context (client, date, etc.)
        channels: List of delivery channels e.g. ['sms', 'email']

    Returns standard ShowingDay tool response dict.

    TODO: Implement when API access confirmed
      SMS: integrate Twilio or ShowingTime native SMS
      Email: use gmail_sender.py
    """
    print(f"[notification_manager] STUB: would notify agent — {trigger} for {property_address} via {channels}")
    return {
        "status": "stub",
        "data": {
            "party": "agent",
            "trigger": trigger,
            "address": property_address,
            "channels": channels
        },
        "error": None
    }


def notify_client(trigger: str, property_address: str, session_data: dict, channels: list) -> dict:
    """
    Notify the client of a status change.

    Args:
        trigger: One of 'requested', 'confirmed', 'rescheduled', 'canceled'
        property_address: The address of the property whose status changed
        session_data: Full session_state dict for context (client name, email, phone, etc.)
        channels: List of delivery channels e.g. ['sms', 'email']

    Returns standard ShowingDay tool response dict.

    TODO: Implement when API access confirmed
      SMS: use client phone from session_data['client']['phone'] via Twilio or GHL
      Email: use gmail_sender.py with client email from session_data['client']['email']
    """
    client = session_data.get("client", {}) if session_data else {}
    client_name = client.get("name", "Client")
    print(f"[notification_manager] STUB: would notify client ({client_name}) — {trigger} for {property_address} via {channels}")
    return {
        "status": "stub",
        "data": {
            "party": "client",
            "trigger": trigger,
            "address": property_address,
            "channels": channels
        },
        "error": None
    }


def handle_status_change(
    trigger: str,
    property_address: str,
    session_data: dict,
    notification_prefs: dict
) -> dict:
    """
    Called whenever a showing status changes.

    Reads notification preferences and fires the appropriate
    agent/client notifications on the configured channels.

    Args:
        trigger: One of 'requested', 'confirmed', 'rescheduled', 'canceled'
        property_address: The address of the affected property
        session_data: Full session_state dict
        notification_prefs: Dict from settings localStorage.
                            Keys like 'notif-confirmed-agent-sms': True

    Returns:
        {
            "status": "success",
            "data": [list of notify_agent/notify_client results],
            "error": null
        }
    """
    results = []

    for party in ['agent', 'client']:
        channels = []
        if notification_prefs.get(f'notif-{trigger}-{party}-sms'):
            channels.append('sms')
        if notification_prefs.get(f'notif-{trigger}-{party}-email'):
            channels.append('email')
        if channels:
            if party == 'agent':
                results.append(notify_agent(trigger, property_address, session_data, channels))
            else:
                results.append(notify_client(trigger, property_address, session_data, channels))

    return {"status": "success", "data": results, "error": None}


# ── CLI ────────────────────────────────────────────────────────────────────────

def _run_tests():
    """Self-test in stub mode."""
    print("Testing notification_manager (stub mode — no API keys required)...")

    # Test handle_status_change with some prefs enabled
    test_prefs = {
        'notif-confirmed-agent-sms': True,
        'notif-confirmed-agent-email': True,
        'notif-confirmed-client-email': True,
        'notif-canceled-agent-sms': True,
    }
    test_session = {
        "client": {"name": "Sarah Johnson", "email": "sarah@example.com", "phone": "(616) 555-0100"},
        "session_date": "2026-03-21"
    }

    result = handle_status_change(
        trigger='confirmed',
        property_address='1842 Lincoln Rd, Allegan, MI 49010',
        session_data=test_session,
        notification_prefs=test_prefs
    )
    assert result["status"] == "success", f"Test failed: {result}"
    assert len(result["data"]) == 2, f"Expected 2 results (agent + client), got {len(result['data'])}"
    print(f"  PASS — confirmed trigger fired {len(result['data'])} notification(s)")

    result2 = handle_status_change(
        trigger='canceled',
        property_address='728 Oak Grove Rd, Plainwell, MI 49080',
        session_data=test_session,
        notification_prefs=test_prefs
    )
    assert result2["status"] == "success"
    assert len(result2["data"]) == 1, f"Expected 1 result (agent SMS only), got {len(result2['data'])}"
    print(f"  PASS — canceled trigger fired {len(result2['data'])} notification(s)")

    # Test with no prefs enabled — should fire nothing
    result3 = handle_status_change(
        trigger='requested',
        property_address='123 Main St, Plainwell, MI',
        session_data=test_session,
        notification_prefs={}
    )
    assert len(result3["data"]) == 0, "Expected 0 results when no prefs set"
    print("  PASS — no prefs set → no notifications fired")

    print("\nAll notification_manager tests passed.")
    print("Note: All delivery is STUBBED. Configure ShowingTime/SentriKey API access to enable real delivery.")
    print("Contact Scott re: ShowingTime + SentriKey notification webhooks.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ShowingDay Notification Manager")
    parser.add_argument("--test", action="store_true", help="Run self-tests")
    args = parser.parse_args()

    if args.test:
        _run_tests()
    else:
        print("notification_manager stub — no API keys configured")
        print("Status: PENDING API CONFIRMATION")
        print("Contact Scott re: ShowingTime + SentriKey notification webhooks")
        print("\nUsage: python tools/notification_manager.py --test")
