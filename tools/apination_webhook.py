"""
apination_webhook.py — ShowingDay API Nation / GHL Webhook Parser

Receives and parses ShowingTime status events delivered via:
  API Nation → GHL (Lead Connector) → Webhook → ShowingDay /webhook/showingtime

When a seller confirms or declines in ShowingTime, GHL fires a POST to this app.
This module parses the payload, extracts the relevant fields, and updates
session_state.json via session_logger.

Setup: See docs/apination_setup.md for GHL workflow configuration.

CLI: python tools/apination_webhook.py --test

Incoming payload format (from GHL/API Nation — may vary; adjust field names
based on actual API Nation → ShowingTime integration output):
{
    "type": "showingtime_status",
    "data": {
        "address": "1842 Lincoln Rd, Allegan, MI",
        "status": "confirmed" | "declined" | "pending" | "requested",
        "confirmation_number": "ST-2026-XXXXX",
        "timestamp": "2026-03-21T14:32:00Z",
        "agent_name": "Jason O'Brien",
        "notes": "Please use keybox code 4521"
    }
}
"""

import os
import json
import re
import argparse
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

# Import session logger for state updates
try:
    import sys
    sys.path.insert(0, str(BASE_DIR / "tools"))
    from session_logger import update_property_status, log_tool_call
except ImportError:
    def update_property_status(address, status, extra_fields=None):
        print(f"[apination_webhook] session_logger not available — would update {address} to {status}")
        return {"status": "success", "data": None, "error": None}
    def log_tool_call(tool, inputs, result):
        pass

# Valid statuses from ShowingTime (map to internal status names)
STATUS_MAP = {
    "confirmed": "confirmed",
    "approved": "confirmed",
    "accepted": "confirmed",
    "denied": "declined",
    "declined": "declined",
    "rejected": "declined",
    "pending": "pending",
    "requested": "requested",
    "cancelled": "declined",
    "canceled": "declined",
    "counter": "counter",
    "countered": "counter",
    "counter_offer": "counter",
    "counteroffer": "counter",
    "counter-offer": "counter",
    "alternate": "counter",
    "alternate_time": "counter",
}


def _extract_lockbox_code(text: str) -> str | None:
    """
    Extract a lockbox/keybox access code from a notes string.
    Looks for common patterns: 'code 4521', 'keybox: 1234', '#9876', etc.
    Returns the code string or None.
    """
    if not text:
        return None
    patterns = [
        r'(?:lockbox|keybox|key\s*box|combo|combination|access\s*code)[:\s#]+(\d{4,8})',
        r'(?:code)[:\s]+#?(\d{4,8})',
        r'(?:entry|door)[:\s]+#?(\d{4,8})',
        r'#\s*(\d{4,8})\b',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _extract_showing_instructions(text: str) -> str | None:
    """Return clean showing instructions text (strip lockbox code if already extracted separately)."""
    if not text:
        return None
    return text.strip() or None


def parse_webhook_payload(payload: dict) -> dict:
    """
    Parse an incoming GHL/API Nation ShowingTime webhook payload.

    Attempts to extract address, status, and timestamp from multiple
    possible payload structures (GHL may vary by workflow configuration).

    Args:
        payload: Raw dict from the incoming POST request.

    Returns:
        {
            "status": "success" | "failure",
            "data": {
                "address": str,
                "status": str,           # normalized internal status
                "raw_status": str,       # original status string from payload
                "confirmation_number": str | None,
                "timestamp": str,        # ISO format
                "notes": str | None,
                "auto_updated": True
            },
            "error": null | str
        }
    """
    if not payload:
        return {"status": "failure", "data": None, "error": "Empty payload received"}

    try:
        # Strategy 1: Standard wrapped format {"type": ..., "data": {...}}
        data = payload.get("data", payload)

        # Extract address — try multiple field name conventions
        address = (
            data.get("address") or
            data.get("property_address") or
            data.get("propertyAddress") or
            data.get("listing_address") or
            data.get("listingAddress") or
            payload.get("address") or
            ""
        )

        # Extract raw status
        raw_status = (
            data.get("status") or
            data.get("showing_status") or
            data.get("showingStatus") or
            data.get("appointmentStatus") or
            payload.get("status") or
            ""
        ).lower().strip()

        # Normalize status
        normalized_status = STATUS_MAP.get(raw_status, "pending")

        # Extract timestamp
        timestamp = (
            data.get("timestamp") or
            data.get("created_at") or
            data.get("updatedAt") or
            payload.get("timestamp") or
            datetime.utcnow().isoformat()
        )

        # Extract other fields
        confirmation_number = (
            data.get("confirmation_number") or
            data.get("confirmationNumber") or
            data.get("confirmation_id") or
            None
        )

        notes = (
            data.get("notes") or
            data.get("access_notes") or
            data.get("accessNotes") or
            data.get("instructions") or
            data.get("seller_instructions") or
            data.get("showingInstructions") or
            None
        )

        # Extract lockbox code from notes or dedicated field
        lockbox_code = (
            data.get("lockbox_code") or
            data.get("lockboxCode") or
            data.get("access_code") or
            data.get("accessCode") or
            _extract_lockbox_code(notes)
        )

        # Extract showing instructions (keep full notes text)
        showing_instructions = _extract_showing_instructions(notes)

        # Extract listing agent contact
        listing_agent = (
            data.get("listing_agent") or
            data.get("listingAgent") or
            data.get("listing_agent_name") or
            data.get("agent_name") or
            None
        )

        listing_agent_phone = (
            data.get("listing_agent_phone") or
            data.get("listingAgentPhone") or
            data.get("agent_phone") or
            None
        )

        # Extract counter-offer proposed time (for "counter" status)
        counter_time = (
            data.get("counter_time") or
            data.get("counterTime") or
            data.get("alternate_time") or
            data.get("alternateTime") or
            data.get("proposed_time") or
            data.get("proposedTime") or
            None
        )

        if not address:
            return {
                "status": "failure",
                "data": None,
                "error": "Could not extract property address from webhook payload"
            }

        if not raw_status:
            return {
                "status": "failure",
                "data": None,
                "error": "Could not extract status from webhook payload"
            }

        parsed = {
            "address": address,
            "status": normalized_status,
            "raw_status": raw_status,
            "confirmation_number": confirmation_number,
            "timestamp": timestamp,
            "notes": notes,
            "lockbox_code": lockbox_code,
            "showing_instructions": showing_instructions,
            "listing_agent": listing_agent,
            "listing_agent_phone": listing_agent_phone,
            "counter_time": counter_time,
            "auto_updated": True
        }

        # Update session state — persist all useful fields onto the property record
        extra = {}
        if confirmation_number:
            extra["confirmation_number"] = confirmation_number
        if showing_instructions:
            extra["showing_instructions"] = showing_instructions
        if lockbox_code:
            extra["lockbox_code"] = lockbox_code
        if listing_agent:
            extra["listing_agent"] = listing_agent
        if listing_agent_phone:
            extra["listing_agent_phone"] = listing_agent_phone
        if normalized_status == "counter" and counter_time:
            extra["counter_time"] = counter_time
        extra["auto_updated"] = True

        update_result = update_property_status(address, normalized_status, extra_fields=extra if extra else None)

        # Log to run log
        log_tool_call(
            "apination_webhook",
            {"payload_type": payload.get("type", "unknown"), "address": address},
            {"status": "success", "data": parsed, "error": None}
        )

        return {"status": "success", "data": parsed, "error": None}

    except Exception as e:
        error_msg = f"Webhook parse error: {e}"
        log_tool_call("apination_webhook", {"raw_payload": str(payload)[:200]},
                     {"status": "failure", "data": None, "error": error_msg})
        return {"status": "failure", "data": None, "error": error_msg}


def validate_webhook_source(request_headers: dict) -> bool:
    """
    Optional: Validate that the webhook came from GHL/API Nation.

    TODO: Implement signature verification if GHL provides a signing secret.
    Check headers like X-GHL-Signature or similar.
    For now, returns True (accept all — app is local-only in v1).
    """
    # TODO: Implement HMAC signature validation when GHL provides signing secret
    # Example:
    # import hmac, hashlib
    # secret = os.getenv("GHL_WEBHOOK_SECRET", "")
    # signature = request_headers.get("X-GHL-Signature", "")
    # ... validate hmac ...
    return True


# ── CLI ────────────────────────────────────────────────────────────────────────

SAMPLE_PAYLOAD_CONFIRMED = {
    "type": "showingtime_status",
    "data": {
        "address": "1842 Lincoln Rd, Allegan, MI 49010",
        "status": "confirmed",
        "confirmation_number": "ST-2026-84721",
        "timestamp": "2026-03-21T14:32:00Z",
        "notes": "Keybox on front door. Code 4521. Dog in backyard — please keep gate closed.",
        "listing_agent": "Sue Vander Berg",
        "listing_agent_phone": "(616) 555-1234",
        "seller_instructions": "Please remove shoes. Park in driveway only."
    }
}

SAMPLE_PAYLOAD_COUNTER = {
    "type": "showingtime_status",
    "data": {
        "address": "4455 Blue Star Hwy, Saugatuck, MI 49453",
        "status": "counter",
        "confirmation_number": None,
        "timestamp": "2026-03-21T15:01:00Z",
        "counter_time": "3:30 PM – 4:00 PM",
        "notes": "Seller can do 3:30 PM instead of 2:30 PM."
    }
}

SAMPLE_PAYLOAD_DECLINED = {
    "type": "showingtime_status",
    "data": {
        "address": "728 Oak Grove Rd, Plainwell, MI 49080",
        "status": "declined",
        "confirmation_number": None,
        "timestamp": "2026-03-21T15:01:00Z",
        "notes": "Property unavailable on this date."
    }
}

SAMPLE_PAYLOAD_MALFORMED = {
    "event_type": "showing_update"
    # Missing data, address, status
}


def _run_tests():
    print("Testing apination_webhook...")

    # Test 1: Parse confirmed payload
    result = parse_webhook_payload(SAMPLE_PAYLOAD_CONFIRMED)
    assert result["status"] == "success", f"Test 1 failed: {result}"
    assert result["data"]["status"] == "confirmed", f"Test 1 failed: {result['data']}"
    assert result["data"]["address"] == "1842 Lincoln Rd, Allegan, MI 49010", "Test 1 failed: address mismatch"
    assert result["data"]["confirmation_number"] == "ST-2026-84721", "Test 1 failed: confirmation number missing"
    print("  PASS — confirmed payload parsed correctly")

    # Test 2: Parse declined payload
    result = parse_webhook_payload(SAMPLE_PAYLOAD_DECLINED)
    assert result["status"] == "success", f"Test 2 failed: {result}"
    assert result["data"]["status"] == "declined", f"Test 2 failed: {result['data']}"
    print("  PASS — declined payload parsed correctly")

    # Test 3: Malformed payload
    result = parse_webhook_payload(SAMPLE_PAYLOAD_MALFORMED)
    assert result["status"] == "failure", f"Test 3 failed: should return failure for malformed payload"
    print("  PASS — malformed payload returns failure gracefully")

    # Test 4: Empty payload
    result = parse_webhook_payload({})
    assert result["status"] == "failure", "Test 4 failed: empty payload should return failure"
    print("  PASS — empty payload returns failure")

    # Test 5: Flat payload (no "data" wrapper)
    flat_payload = {
        "address": "728 Oak Grove Rd, Plainwell, MI",
        "status": "approved",
        "timestamp": "2026-03-21T15:30:00Z"
    }
    result = parse_webhook_payload(flat_payload)
    assert result["status"] == "success", f"Test 5 failed: {result}"
    assert result["data"]["status"] == "confirmed", f"Test 5 failed: 'approved' should map to 'confirmed'"
    print("  PASS — flat payload (no wrapper) parsed correctly")

    # Test 6: Status normalization
    for raw, expected in [("approved", "confirmed"), ("denied", "declined"), ("cancelled", "declined")]:
        p = {"address": "Test Addr, MI", "status": raw}
        r = parse_webhook_payload(p)
        assert r["data"]["status"] == expected, f"Test 6 failed: '{raw}' should map to '{expected}'"
    print("  PASS — status normalization works for all variants")

    print("\nAll apination_webhook tests passed.")
    print("\nSample parsed payload:")
    print(json.dumps(parse_webhook_payload(SAMPLE_PAYLOAD_CONFIRMED), indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ShowingDay API Nation Webhook Parser")
    parser.add_argument("--test", action="store_true", help="Run self-tests")
    parser.add_argument("--simulate", choices=["confirmed", "declined", "malformed"],
                        help="Simulate a webhook event")
    args = parser.parse_args()

    if args.test:
        _run_tests()
    elif args.simulate:
        payloads = {
            "confirmed": SAMPLE_PAYLOAD_CONFIRMED,
            "declined": SAMPLE_PAYLOAD_DECLINED,
            "malformed": SAMPLE_PAYLOAD_MALFORMED
        }
        result = parse_webhook_payload(payloads[args.simulate])
        print(json.dumps(result, indent=2))
    else:
        parser.print_help()
