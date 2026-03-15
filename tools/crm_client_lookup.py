"""
crm_client_lookup.py — ShowingDay CRM Client Lookup

Searches for a client contact by name, trying:
  1. Lofty CRM (primary)
  2. GoHighLevel / Lead Connector (fallback)
  3. Manual entry prompt (last resort)

Both CRM API calls are currently stubbed with TODO comments.
The GHL search uses GHL_API_KEY and GHL_LOCATION_ID from .env.

CLI: python tools/crm_client_lookup.py --test
     python tools/crm_client_lookup.py --name "Sarah Johnson"

Returns:
    {
        "status": "success",
        "data": {
            "name": "Sarah Johnson",
            "email": "sarah@example.com",
            "phone": "(616) 555-0123",
            "crm_source": "lofty" | "ghl" | "manual"
        },
        "error": null
    }
"""

import os
import json
import argparse
import requests
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

LOFTY_API_KEY = os.getenv("LOFTY_API_KEY", "")
GHL_API_KEY = os.getenv("GHL_API_KEY", "")
GHL_LOCATION_ID = os.getenv("GHL_LOCATION_ID", "")


# ── Lofty CRM ─────────────────────────────────────────────────────────────────

def search_lofty(name: str) -> dict | None:
    """
    Search Lofty CRM contacts by name.

    TODO: Implement Lofty API integration.
    Steps:
      1. Confirm API endpoint with Lofty support or admin panel
      2. Auth: Bearer token using LOFTY_API_KEY
      3. Search endpoint (likely): GET /api/v1/contacts?search={name}
      4. Parse response: extract first_name, last_name, email, phone
      5. Return contact dict or None if not found

    Returns contact dict or None.
    """
    if not LOFTY_API_KEY:
        return None

    # TODO: Replace with actual Lofty API call
    # Example structure (verify with Lofty docs):
    #
    # headers = {"Authorization": f"Bearer {LOFTY_API_KEY}"}
    # resp = requests.get(
    #     "https://api.lofty.com/v1/contacts",
    #     params={"search": name, "limit": 5},
    #     headers=headers,
    #     timeout=10
    # )
    # resp.raise_for_status()
    # contacts = resp.json().get("data", {}).get("contacts", [])
    # if contacts:
    #     c = contacts[0]
    #     return {
    #         "name": f"{c['firstName']} {c['lastName']}",
    #         "email": c.get("email", ""),
    #         "phone": c.get("phone", ""),
    #         "crm_source": "lofty"
    #     }
    # return None

    print(f"[crm_client_lookup] Lofty search stubbed — LOFTY_API_KEY set but API not yet implemented")
    return None


def search_ghl(name: str) -> dict | None:
    """
    Search GoHighLevel (Lead Connector) contacts by name.

    Uses GHL_API_KEY and GHL_LOCATION_ID from .env.

    TODO: Uncomment and test the GHL API call below.
    GHL API docs: https://highlevel.stoplight.io/docs/integrations/

    Returns contact dict or None.
    """
    if not GHL_API_KEY or not GHL_LOCATION_ID:
        return None

    # TODO: Uncomment and verify this GHL API call
    # try:
    #     headers = {
    #         "Authorization": f"Bearer {GHL_API_KEY}",
    #         "Content-Type": "application/json",
    #         "Version": "2021-07-28"
    #     }
    #     resp = requests.get(
    #         f"https://services.leadconnectorhq.com/contacts/",
    #         params={
    #             "locationId": GHL_LOCATION_ID,
    #             "query": name,
    #             "limit": 5
    #         },
    #         headers=headers,
    #         timeout=10
    #     )
    #     resp.raise_for_status()
    #     data = resp.json()
    #     contacts = data.get("contacts", [])
    #     if contacts:
    #         c = contacts[0]
    #         full_name = f"{c.get('firstName', '')} {c.get('lastName', '')}".strip()
    #         return {
    #             "name": full_name or name,
    #             "email": c.get("email", ""),
    #             "phone": c.get("phone", ""),
    #             "crm_source": "ghl"
    #         }
    # except requests.RequestException as e:
    #     print(f"[crm_client_lookup] GHL API error: {e}")
    # return None

    print(f"[crm_client_lookup] GHL search stubbed — GHL_API_KEY set but API not yet enabled")
    return None


# ── Main lookup function ───────────────────────────────────────────────────────

def lookup_client(name: str) -> dict:
    """
    Search for a client by name: Lofty → GHL → manual entry fallback.

    Args:
        name: Client's full name or partial name to search.

    Returns standard ShowingDay tool response.
    """
    if not name or not name.strip():
        return {"status": "failure", "data": None, "error": "Client name is required"}

    name = name.strip()

    # 1. Try Lofty
    try:
        lofty_result = search_lofty(name)
        if lofty_result:
            return {"status": "success", "data": lofty_result, "error": None}
    except Exception as e:
        print(f"[crm_client_lookup] Lofty search failed: {e}")

    # 2. Try GHL
    try:
        ghl_result = search_ghl(name)
        if ghl_result:
            return {"status": "success", "data": ghl_result, "error": None}
    except Exception as e:
        print(f"[crm_client_lookup] GHL search failed: {e}")

    # 3. Manual entry fallback
    # Return a "not_found" status with the searched name so the UI can
    # display a manual entry form pre-populated with the name they typed.
    return {
        "status": "success",
        "data": {
            "name": name,
            "email": "",
            "phone": "",
            "crm_source": "manual",
            "not_found": True
        },
        "error": None
    }


# ── CLI ────────────────────────────────────────────────────────────────────────

def _run_tests():
    """Self-test for crm_client_lookup."""
    print("Testing crm_client_lookup (stub mode — CRM APIs not yet implemented)...")

    # Test 1: empty name
    result = lookup_client("")
    assert result["status"] == "failure", "Test 1 failed: empty name should return failure"
    print("  PASS — empty name returns failure")

    # Test 2: name not in either CRM falls back to manual
    result = lookup_client("Test Client Nobody")
    assert result["status"] == "success", f"Test 2 failed: {result}"
    assert result["data"]["crm_source"] == "manual", "Test 2 failed: should fall back to manual"
    assert result["data"]["not_found"] == True, "Test 2 failed: should set not_found"
    print("  PASS — unfound name returns manual fallback with not_found=True")

    # Test 3: returned data has required fields
    result = lookup_client("Jason O'Brien")
    for field in ["name", "email", "phone", "crm_source"]:
        assert field in result["data"], f"Test 3 failed: missing field {field}"
    print("  PASS — response always contains name, email, phone, crm_source")

    print("\nAll crm_client_lookup tests passed.")
    print("(Note: Lofty and GHL APIs are stubbed — implement search_lofty() and search_ghl() to enable real CRM lookup)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ShowingDay CRM Client Lookup")
    parser.add_argument("--test", action="store_true", help="Run self-tests")
    parser.add_argument("--name", type=str, help="Client name to look up")
    args = parser.parse_args()

    if args.test:
        _run_tests()
    elif args.name:
        result = lookup_client(args.name)
        print(json.dumps(result, indent=2))
    else:
        parser.print_help()
