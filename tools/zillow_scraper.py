"""
zillow_scraper.py — ShowingDay Zillow Listing Data Scraper

Primary source for property listing data when Bridge API is not available.
Scrapes Zillow for: price, beds, baths, sqft, photos, tax, Zestimate, etc.

IMPORTANT: Zillow's scraping policies change frequently. If scraping fails,
this tool returns mock data and logs the error — the UI will show
"Data unavailable — enter manually" for affected fields.

When Bridge API access is confirmed, replace this module with bridge_api_fetcher.py.
Contact: BridgeAPI@bridgeinteractive.com

CLI: python tools/zillow_scraper.py --test
     python tools/zillow_scraper.py --address "1842 Lincoln Rd, Allegan, MI"

Returns:
    {
        "status": "success",
        "data": {
            "address": str,
            "price": str,
            "price_history": [...],
            "days_on_market": int,
            "beds": int,
            "baths": float,
            "sqft": int,
            "lot_size": str,
            "year_built": int,
            "last_sold_date": str,
            "last_sold_price": str,
            "description": str,
            "school_district": str,
            "tax_estimate": str,
            "zestimate": str,
            "photos": [...],
            "zillow_url": str,
            "data_source": "zillow" | "mock"
        },
        "error": null
    }
"""

import os
import json
import argparse
import time
import random
import re
from pathlib import Path
from urllib.parse import quote_plus

BASE_DIR = Path(__file__).resolve().parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

# Optional imports — gracefully degrade if not installed
try:
    import requests
    from bs4 import BeautifulSoup
    SCRAPING_AVAILABLE = True
except ImportError:
    SCRAPING_AVAILABLE = False

# User-Agent rotation to reduce bot detection
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
]


# ── Mock data ──────────────────────────────────────────────────────────────────

def _build_mock_listing(address: str) -> dict:
    """Return realistic mock listing data for testing/fallback."""
    return {
        "address": address,
        "price": "$289,900",
        "price_history": [
            {"date": "2026-01-15", "event": "Listed", "price": "$299,900"},
            {"date": "2026-02-20", "event": "Price Reduced", "price": "$289,900"}
        ],
        "days_on_market": 48,
        "beds": 3,
        "baths": 2.0,
        "sqft": 1842,
        "lot_size": "0.42 acres",
        "year_built": 1998,
        "last_sold_date": "2017-06-12",
        "last_sold_price": "$187,500",
        "description": (
            "Charming 3-bedroom ranch on nearly half an acre in a quiet rural setting. "
            "Updated kitchen with granite counters and stainless appliances. "
            "Primary suite with walk-in closet. Full unfinished basement — "
            "great potential. New roof (2019), furnace (2021). Attached 2-car garage. "
            "Backyard borders wooded area. Close to schools and downtown Allegan."
        ),
        "school_district": "Allegan Public Schools",
        "tax_estimate": "$3,240/yr",
        "zestimate": "$294,500",
        "photos": [
            "https://photos.zillowstatic.com/fp/mock-photo-1.jpg",
            "https://photos.zillowstatic.com/fp/mock-photo-2.jpg"
        ],
        "zillow_url": f"https://www.zillow.com/homes/{quote_plus(address)}",
        "data_source": "mock"
    }


# ── Zillow scraper ─────────────────────────────────────────────────────────────

def _scrape_zillow(address: str) -> dict | None:
    """
    Attempt to scrape listing data from Zillow.

    TODO: Implement real scraping logic. Zillow is heavily bot-protected.
    Recommended approaches (in order of reliability):
      1. Use a scraping service/proxy (ScraperAPI, Bright Data, etc.)
      2. Use Zillow's unofficial search API endpoint
      3. Direct HTML scraping with rotating user agents + delays

    Current status: Returns None (triggers mock fallback).

    Implementation guidance:
    ─────────────────────────
    # Step 1: Search Zillow for the address
    search_url = f"https://www.zillow.com/search/easy-intent/api/search"
    # OR: https://www.zillow.com/homes/{encoded_address}_rb/

    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.zillow.com/"
    }

    # Step 2: Parse the response for listing JSON
    # Zillow embeds listing data as JSON in a <script id="__NEXT_DATA__"> tag
    soup = BeautifulSoup(response.text, "lxml")
    script = soup.find("script", {"id": "__NEXT_DATA__"})
    if script:
        data = json.loads(script.string)
        # Navigate: data["props"]["pageProps"]["componentProps"]["gdpClientCache"]
        # Structure changes frequently — inspect Zillow HTML to find current path

    # Step 3: Extract fields and return structured dict
    ─────────────────────────
    """
    # TODO: Implement scraping (see docstring above)
    return None


def get_listing_data(address: str) -> dict:
    """
    Main entry point: get listing data for a property address.

    Tries Zillow scraper first; falls back to mock data on any failure.

    Args:
        address: Full property address string.

    Returns standard ShowingDay tool response.
    """
    if not address or not address.strip():
        return {"status": "failure", "data": None, "error": "Address is required"}

    address = address.strip()

    # Try real scraping
    if SCRAPING_AVAILABLE:
        try:
            result = _scrape_zillow(address)
            if result:
                return {"status": "success", "data": result, "error": None}
        except Exception as e:
            print(f"[zillow_scraper] Scraping failed for {address}: {e} — falling back to mock data")

    # Fall back to mock data
    print(f"[zillow_scraper] Returning mock data for: {address}")
    mock = _build_mock_listing(address)
    return {"status": "success", "data": mock, "error": None}


# ── CLI ────────────────────────────────────────────────────────────────────────

def _run_tests():
    print("Testing zillow_scraper (mock mode)...")

    # Test 1: basic call returns success
    result = get_listing_data("1842 Lincoln Rd, Allegan, MI 49010")
    assert result["status"] == "success", f"Test 1 failed: {result}"
    data = result["data"]
    for field in ["address", "price", "beds", "baths", "sqft", "year_built", "zestimate", "photos"]:
        assert field in data, f"Test 1 failed: missing field '{field}'"
    print("  PASS — get_listing_data() returns all required fields")
    print(f"  Price: {data['price']}, Beds: {data['beds']}, Baths: {data['baths']}, Sqft: {data['sqft']}")

    # Test 2: empty address returns failure
    result = get_listing_data("")
    assert result["status"] == "failure", "Test 2 failed: empty address should return failure"
    print("  PASS — empty address returns failure")

    # Test 3: mock data has expected structure
    assert isinstance(data["photos"], list), "Test 3 failed: photos should be list"
    assert isinstance(data["price_history"], list), "Test 3 failed: price_history should be list"
    print("  PASS — data structure is correct (photos and price_history are lists)")

    print("\nAll zillow_scraper tests passed.")
    print("(Note: Real Zillow scraping is stubbed — implement _scrape_zillow() for live data)")
    print("\nSample listing data:")
    print(json.dumps(result["data"], indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ShowingDay Zillow Listing Scraper")
    parser.add_argument("--test", action="store_true", help="Run self-tests")
    parser.add_argument("--address", type=str, help="Property address to look up")
    args = parser.parse_args()

    if args.test:
        _run_tests()
    elif args.address:
        result = get_listing_data(args.address)
        print(json.dumps(result, indent=2))
    else:
        parser.print_help()
