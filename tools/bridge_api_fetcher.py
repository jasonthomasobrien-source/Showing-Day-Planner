"""
bridge_api_fetcher.py — ShowingDay Bridge API Fetcher (PLACEHOLDER)

FUTURE REPLACEMENT FOR zillow_scraper.py

Bridge Interactive (owned by Zillow Group, part of ShowingTime+) provides
direct MLS listing data via a RESO-certified API. When WMLS grants Bridge API
access, this module replaces zillow_scraper.py for reliable MLS-direct data.

STATUS: PLACEHOLDER — Do not use in production until Bridge API access is confirmed.

To activate:
  1. Confirm Bridge API credentials with developer
     (check if provisioned via existing IDX agreement)
  2. Contact: BridgeAPI@bridgeinteractive.com
  3. Set BRIDGE_API_KEY in .env
  4. Implement the functions below
  5. Update app.py to import from bridge_api_fetcher instead of zillow_scraper

API Documentation: https://bridgedataoutput.com/docs/

CLI: python tools/bridge_api_fetcher.py --test
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

BRIDGE_API_KEY = os.getenv("BRIDGE_API_KEY", "")
BRIDGE_API_BASE_URL = "https://api.bridgedataoutput.com/api/v2"


def get_listing_data(address: str = None, mls_number: str = None) -> dict:
    """
    Fetch MLS listing data from Bridge API.

    This function has the same interface as zillow_scraper.get_listing_data()
    so it can be swapped in as a drop-in replacement.

    Args:
        address: Property address string (used to search if mls_number not available)
        mls_number: MLS listing number (preferred — more precise than address search)

    Returns standard ShowingDay tool response (same structure as zillow_scraper).

    TODO: Implement when Bridge API access is confirmed:
    ─────────────────────────────────────────────────────
    import requests

    if not BRIDGE_API_KEY or BRIDGE_API_KEY.startswith("placeholder"):
        return {
            "status": "failure",
            "data": None,
            "error": "BRIDGE_API_KEY not configured. Contact BridgeAPI@bridgeinteractive.com."
        }

    headers = {"Authorization": f"Bearer {BRIDGE_API_KEY}"}

    if mls_number:
        # Search by MLS number (most precise)
        resp = requests.get(
            f"{BRIDGE_API_BASE_URL}/OData/listings",
            params={"$filter": f"ListingId eq '{mls_number}'"},
            headers=headers,
            timeout=15
        )
    else:
        # Search by address
        resp = requests.get(
            f"{BRIDGE_API_BASE_URL}/OData/listings",
            params={"$filter": f"UnparsedAddress eq '{address}'"},
            headers=headers,
            timeout=15
        )

    resp.raise_for_status()
    data = resp.json()
    listings = data.get("value", [])

    if not listings:
        return {
            "status": "failure",
            "data": None,
            "error": f"No listing found for: {address or mls_number}"
        }

    listing = listings[0]
    return {
        "status": "success",
        "data": {
            "address": listing.get("UnparsedAddress", address),
            "price": f"${listing.get('ListPrice', 0):,}",
            "beds": listing.get("BedroomsTotal"),
            "baths": listing.get("BathroomsTotalInteger"),
            "sqft": listing.get("LivingArea"),
            "lot_size": f"{listing.get('LotSizeAcres', 0):.2f} acres",
            "year_built": listing.get("YearBuilt"),
            "days_on_market": listing.get("DaysOnMarket"),
            "description": listing.get("PublicRemarks", ""),
            "school_district": listing.get("ElementarySchoolDistrict", ""),
            "tax_estimate": f"${listing.get('TaxAnnualAmount', 0):,.0f}/yr",
            "photos": [m.get("MediaURL") for m in listing.get("Media", [])[:10] if m.get("MediaURL")],
            "mls_number": listing.get("ListingId"),
            "data_source": "bridge_api"
        },
        "error": None
    }
    ─────────────────────────────────────────────────────
    """
    return {
        "status": "failure",
        "data": None,
        "error": (
            "Bridge API is not yet configured. "
            "Contact BridgeAPI@bridgeinteractive.com to confirm API access. "
            "Until then, zillow_scraper.py is used for listing data."
        )
    }


def get_disclosure_documents(mls_number: str) -> dict:
    """
    Fetch disclosure documents associated with a listing from Bridge API.

    This is a potential future capability — confirm with Bridge API whether
    disclosure documents are accessible via the WMLS integration.

    Args:
        mls_number: MLS listing number.

    Returns list of disclosure document URLs or download paths.

    TODO: Implement when Bridge API access is confirmed and documents confirmed available.
    """
    return {
        "status": "failure",
        "data": None,
        "error": "Bridge API disclosure document access not yet confirmed."
    }


# ── CLI ────────────────────────────────────────────────────────────────────────

def _run_tests():
    print("Testing bridge_api_fetcher (placeholder)...")

    result = get_listing_data("1842 Lincoln Rd, Allegan, MI 49010")
    assert result["status"] == "failure", "Test failed: should return failure until configured"
    assert "BridgeAPI@bridgeinteractive.com" in result["error"], "Test failed: error should include contact info"
    print("  PASS — returns failure with contact info when not configured")

    print("\nAll bridge_api_fetcher tests passed.")
    print("(Note: Bridge API is a placeholder — contact BridgeAPI@bridgeinteractive.com to enable)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ShowingDay Bridge API Fetcher (Placeholder)")
    parser.add_argument("--test", action="store_true", help="Run self-tests")
    args = parser.parse_args()

    if args.test:
        _run_tests()
    else:
        print(__doc__)
