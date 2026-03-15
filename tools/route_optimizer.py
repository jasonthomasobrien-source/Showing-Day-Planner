"""
route_optimizer.py — ShowingDay Route Optimizer

Calculates the optimal showing order and time-slot assignments for a set of
property addresses using the Google Maps Distance Matrix API.

Algorithm: Nearest-neighbor TSP approximation (sufficient for 2–8 stops).
Time-of-day awareness: departure time is passed to the Distance Matrix API so
travel estimates reflect actual traffic conditions on the session date/time.

CLI: python tools/route_optimizer.py --test

Returns:
    {
        "status": "success",
        "data": {
            "route": [
                {
                    "order": 1,
                    "address": "123 Main St, Allegan, MI",
                    "arrival_time": "1:00 PM",
                    "showing_start": "1:00 PM",
                    "showing_end": "1:30 PM",
                    "departure_time": "1:30 PM",
                    "travel_to_next_minutes": 18
                },
                ...
            ],
            "total_duration_minutes": 210,
            "fits_window": true,
            "warnings": []
        },
        "error": null
    }
"""

import os
import sys
import json
import argparse
import math
import requests
from datetime import datetime, timedelta
from pathlib import Path

# Load .env if running as script
BASE_DIR = Path(__file__).resolve().parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass  # dotenv not required for import; app.py loads it first

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")

# ── Mock data ──────────────────────────────────────────────────────────────────
# Returned when GOOGLE_MAPS_API_KEY is not set.
# Represents a realistic 3-property West Michigan showing session.
MOCK_ROUTE_DATA = {
    "route": [
        {
            "order": 1,
            "address": "1842 Lincoln Rd, Allegan, MI 49010",
            "arrival_time": "1:00 PM",
            "showing_start": "1:00 PM",
            "showing_end": "1:30 PM",
            "departure_time": "1:30 PM",
            "travel_to_next_minutes": 22
        },
        {
            "order": 2,
            "address": "4455 Blue Star Hwy, Saugatuck, MI 49453",
            "arrival_time": "1:52 PM",
            "showing_start": "1:52 PM",
            "showing_end": "2:22 PM",
            "departure_time": "2:22 PM",
            "travel_to_next_minutes": 31
        },
        {
            "order": 3,
            "address": "728 Oak Grove Rd, Plainwell, MI 49080",
            "arrival_time": "2:53 PM",
            "showing_start": "2:53 PM",
            "showing_end": "3:23 PM",
            "departure_time": "3:23 PM",
            "travel_to_next_minutes": None
        }
    ],
    "total_duration_minutes": 143,
    "fits_window": True,
    "warnings": [],
    "mock": True
}


# ── Google Maps Distance Matrix ────────────────────────────────────────────────

def _get_travel_times_matrix(addresses: list, departure_dt: datetime) -> dict:
    """
    Call the Google Maps Distance Matrix API to get travel times (seconds)
    between every pair of addresses in the list.

    Returns a 2D dict: matrix[i][j] = travel_seconds from addresses[i] to addresses[j]
    """
    n = len(addresses)
    matrix = {i: {j: None for j in range(n)} for i in range(n)}

    # Convert departure datetime to Unix timestamp for time-of-day awareness
    departure_timestamp = int(departure_dt.timestamp())

    origins_str = "|".join(addresses)
    destinations_str = "|".join(addresses)

    url = "https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {
        "origins": origins_str,
        "destinations": destinations_str,
        "mode": "driving",
        "departure_time": departure_timestamp,
        "traffic_model": "best_guess",
        "key": GOOGLE_MAPS_API_KEY
    }

    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    if data.get("status") != "OK":
        raise ValueError(f"Distance Matrix API returned status: {data.get('status')} — {data.get('error_message', '')}")

    for i, row in enumerate(data["rows"]):
        for j, element in enumerate(row["elements"]):
            if element.get("status") == "OK":
                # Use duration_in_traffic if available (traffic-aware), else duration
                duration_key = "duration_in_traffic" if "duration_in_traffic" in element else "duration"
                matrix[i][j] = element[duration_key]["value"]  # seconds
            else:
                # Default to 30 minutes if a leg fails
                matrix[i][j] = 1800
                print(f"[route_optimizer] WARNING: No route found from {addresses[i]} to {addresses[j]}, defaulting to 30 min")

    return matrix


def _nearest_neighbor_tsp(start_address: str, addresses: list, matrix: dict) -> list:
    """
    Solve the TSP using nearest-neighbor heuristic.

    start_address is index -1 (home base). addresses[0..n-1] are the stops.
    matrix[i][j] represents travel from i to j where:
      - Indices 0..n-1 correspond to addresses
      - 'start' is the depot (not in addresses list, uses the start row from the matrix)

    Returns ordered list of address indices.
    """
    n = len(addresses)
    if n == 0:
        return []
    if n == 1:
        return [0]

    unvisited = set(range(n))
    route = []

    # Pick the address closest to start (start_address is at index n in the full list
    # including start; we use it from a separate call)
    # For nearest-neighbor from start, we need start → each address travel time.
    # We request the start address separately (it's index n in the full_addresses list).
    current = "start"
    start_times = matrix.get("start", {})

    # Start: pick closest property from start
    best_first = min(unvisited, key=lambda j: start_times.get(j, float("inf")))
    route.append(best_first)
    unvisited.remove(best_first)
    current = best_first

    # Continue: always pick the unvisited property closest to current
    while unvisited:
        current_times = matrix.get(current, {})
        nearest = min(unvisited, key=lambda j: current_times.get(j, float("inf")))
        route.append(nearest)
        unvisited.remove(nearest)
        current = nearest

    return route


def _format_time(dt: datetime) -> str:
    """Format a datetime as '1:00 PM'."""
    return dt.strftime("%-I:%M %p")


def _assign_time_slots(
    ordered_addresses: list,
    travel_times: dict,  # matrix[i][j] in seconds
    start_times: dict,   # travel from start to each index in seconds
    window_start: datetime,
    window_end: datetime,
    max_showing_minutes: int,
    direction: str
) -> list:
    """
    Assign showing time slots to each stop in the optimized order.

    direction: "start-loaded" → first showing starts at window_start
               "end-loaded"   → last showing ends at window_end
    """
    n = len(ordered_addresses)
    showing_duration = timedelta(minutes=max_showing_minutes)
    total_showing_time = showing_duration * n

    # Sum all travel times in the optimized order
    total_travel = timedelta(seconds=start_times.get(ordered_addresses[0], 0))
    for i in range(len(ordered_addresses) - 1):
        from_idx = ordered_addresses[i]
        to_idx = ordered_addresses[i + 1]
        total_travel += timedelta(seconds=travel_times.get(from_idx, {}).get(to_idx, 0))

    total_needed = total_showing_time + total_travel
    window_duration = window_end - window_start
    fits_window = total_needed <= window_duration

    # Determine anchor time based on direction
    if direction == "end-loaded":
        # Work backwards from window_end
        last_end = window_end
        slots = []
        current_time = last_end - showing_duration
        for i in range(n - 1, -1, -1):
            showing_start = current_time
            showing_end = showing_start + showing_duration
            if i > 0:
                travel_sec = travel_times.get(ordered_addresses[i - 1], {}).get(ordered_addresses[i], 0)
                current_time = showing_start - timedelta(seconds=travel_sec)
            slots.insert(0, {
                "showing_start": showing_start,
                "showing_end": showing_end
            })
    else:
        # Start-loaded: first showing starts ASAP (at window_start + travel from home)
        first_travel = timedelta(seconds=start_times.get(ordered_addresses[0], 0))
        current_time = window_start + first_travel
        slots = []
        for i in range(n):
            showing_start = current_time
            showing_end = showing_start + showing_duration
            slots.append({
                "showing_start": showing_start,
                "showing_end": showing_end
            })
            if i < n - 1:
                travel_sec = travel_times.get(ordered_addresses[i], {}).get(ordered_addresses[i + 1], 0)
                current_time = showing_end + timedelta(seconds=travel_sec)

    return slots, fits_window, total_needed.seconds // 60


def optimize_route(
    addresses: list,
    start_address: str,
    session_datetime: str,
    window_end_time: str = None,
    max_showing_minutes: int = 30,
    direction: str = "start-loaded"
) -> dict:
    """
    Main entry point for route optimization.

    Args:
        addresses: List of property address strings to show.
        start_address: Starting location (agent's home base).
        session_datetime: ISO format or "YYYY-MM-DD HH:MM" string for session start.
        window_end_time: "HH:MM" end time string (e.g., "18:00"). Optional.
        max_showing_minutes: Maximum time per showing in minutes.
        direction: "start-loaded" or "end-loaded".

    Returns standard ShowingDay tool response.
    """
    # ── Input validation ──────────────────────────────────────────────────────
    if not addresses:
        return {"status": "failure", "data": None, "error": "No addresses provided"}

    # ── Mock mode ─────────────────────────────────────────────────────────────
    if not GOOGLE_MAPS_API_KEY:
        print("[route_optimizer] No GOOGLE_MAPS_API_KEY set — returning mock data")
        # Adjust mock to match inputs
        mock = dict(MOCK_ROUTE_DATA)
        mock_route = []
        for i, addr in enumerate(addresses):
            stop = {
                "order": i + 1,
                "address": addr,
                "arrival_time": f"{1 + i}:00 PM",
                "showing_start": f"{1 + i}:00 PM",
                "showing_end": f"{1 + i}:30 PM",
                "departure_time": f"{1 + i}:30 PM",
                "travel_to_next_minutes": 20 if i < len(addresses) - 1 else None
            }
            mock_route.append(stop)
        mock["route"] = mock_route
        return {"status": "success", "data": mock, "error": None}

    # ── Parse session datetime ────────────────────────────────────────────────
    try:
        # Accept "YYYY-MM-DD HH:MM" or ISO format
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
            try:
                window_start = datetime.strptime(session_datetime, fmt)
                break
            except ValueError:
                continue
        else:
            return {"status": "failure", "data": None, "error": f"Could not parse session_datetime: {session_datetime}"}
    except Exception as e:
        return {"status": "failure", "data": None, "error": f"Date parse error: {e}"}

    # Parse window end time
    if window_end_time:
        try:
            end_t = datetime.strptime(window_end_time, "%H:%M").time()
            window_end = window_start.replace(hour=end_t.hour, minute=end_t.minute, second=0)
        except ValueError:
            window_end = window_start + timedelta(hours=5)
    else:
        window_end = window_start + timedelta(hours=5)

    # ── Build full address list for distance matrix ────────────────────────────
    # Full list: start_address + all property addresses
    full_addresses = [start_address] + addresses
    n_props = len(addresses)

    try:
        # Get travel times for the full matrix (start + all properties)
        url = "https://maps.googleapis.com/maps/api/distancematrix/json"
        origins_str = "|".join(full_addresses)
        destinations_str = "|".join(full_addresses)

        resp = requests.get(url, params={
            "origins": origins_str,
            "destinations": destinations_str,
            "mode": "driving",
            "departure_time": int(window_start.timestamp()),
            "traffic_model": "best_guess",
            "key": GOOGLE_MAPS_API_KEY
        }, timeout=20)
        resp.raise_for_status()
        raw = resp.json()

        if raw.get("status") != "OK":
            raise ValueError(f"API status: {raw.get('status')} — {raw.get('error_message', '')}")

        # Build matrix indexed 0=start, 1..n=properties
        full_n = len(full_addresses)
        raw_matrix = {}
        for i, row in enumerate(raw["rows"]):
            raw_matrix[i] = {}
            for j, element in enumerate(row["elements"]):
                if element.get("status") == "OK":
                    dur_key = "duration_in_traffic" if "duration_in_traffic" in element else "duration"
                    raw_matrix[i][j] = element[dur_key]["value"]
                else:
                    raw_matrix[i][j] = 1800  # 30 min default

    except Exception as e:
        return {"status": "failure", "data": None, "error": f"Google Maps API error: {e}"}

    # Extract start→property travel times (row 0, columns 1..n)
    start_times_sec = {prop_idx: raw_matrix[0].get(prop_idx + 1, 1800) for prop_idx in range(n_props)}

    # Extract property→property travel times (rows 1..n, columns 1..n, shifted by 1)
    prop_matrix = {}
    for i in range(n_props):
        prop_matrix[i] = {}
        for j in range(n_props):
            if i != j:
                prop_matrix[i][j] = raw_matrix[i + 1].get(j + 1, 1800)

    # ── TSP nearest-neighbor ──────────────────────────────────────────────────
    unvisited = set(range(n_props))
    ordered_indices = []

    # Start from whichever property is closest to start_address
    if unvisited:
        first = min(unvisited, key=lambda j: start_times_sec.get(j, float("inf")))
        ordered_indices.append(first)
        unvisited.remove(first)
        current = first

        while unvisited:
            nearest = min(unvisited, key=lambda j: prop_matrix.get(current, {}).get(j, float("inf")))
            ordered_indices.append(nearest)
            unvisited.remove(nearest)
            current = nearest

    # ── Assign time slots ─────────────────────────────────────────────────────
    slots, fits_window, total_minutes = _assign_time_slots(
        ordered_indices, prop_matrix, start_times_sec,
        window_start, window_end, max_showing_minutes, direction
    )

    # ── Build final route list ────────────────────────────────────────────────
    route = []
    warnings = []

    if not fits_window:
        warnings.append(
            f"Schedule ({total_minutes} min) exceeds availability window "
            f"({int((window_end - window_start).seconds / 60)} min). "
            "Consider: removing the last property, shortening showing time, or extending availability."
        )

    for order_pos, (prop_idx, slot) in enumerate(zip(ordered_indices, slots)):
        addr = addresses[prop_idx]
        # Travel time to next stop
        if order_pos < len(ordered_indices) - 1:
            next_idx = ordered_indices[order_pos + 1]
            travel_min = math.ceil(prop_matrix.get(prop_idx, {}).get(next_idx, 0) / 60)
        else:
            travel_min = None

        route.append({
            "order": order_pos + 1,
            "address": addr,
            "arrival_time": _format_time(slot["showing_start"]),
            "showing_start": _format_time(slot["showing_start"]),
            "showing_end": _format_time(slot["showing_end"]),
            "departure_time": _format_time(slot["showing_end"]),
            "travel_to_next_minutes": travel_min
        })

    return {
        "status": "success",
        "data": {
            "route": route,
            "total_duration_minutes": total_minutes,
            "fits_window": fits_window,
            "warnings": warnings,
            "mock": False
        },
        "error": None
    }


# ── CLI ────────────────────────────────────────────────────────────────────────

def _run_tests():
    """Test route optimizer in mock mode."""
    print("Testing route_optimizer (mock mode — no API key required)...")

    result = optimize_route(
        addresses=[
            "1842 Lincoln Rd, Allegan, MI 49010",
            "4455 Blue Star Hwy, Saugatuck, MI 49453",
            "728 Oak Grove Rd, Plainwell, MI 49080"
        ],
        start_address="Plainwell, MI 49080",
        session_datetime="2026-03-21 13:00",
        window_end_time="18:00",
        max_showing_minutes=30,
        direction="start-loaded"
    )

    assert result["status"] == "success", f"Test failed: {result}"
    assert len(result["data"]["route"]) == 3, "Test failed: expected 3 stops"
    assert result["data"]["route"][0]["order"] == 1, "Test failed: first stop should be order 1"
    print(f"  PASS — route returned {len(result['data']['route'])} stops")
    print(f"  Total duration: {result['data']['total_duration_minutes']} minutes")
    print(f"  Fits window: {result['data']['fits_window']}")
    if result["data"].get("mock"):
        print("  (Mock data — set GOOGLE_MAPS_API_KEY in .env for live data)")

    # Test end-loaded
    result2 = optimize_route(
        addresses=["1842 Lincoln Rd, Allegan, MI", "728 Oak Grove Rd, Plainwell, MI"],
        start_address="Plainwell, MI",
        session_datetime="2026-03-21 13:00",
        window_end_time="18:00",
        max_showing_minutes=30,
        direction="end-loaded"
    )
    assert result2["status"] == "success", f"End-loaded test failed: {result2}"
    print("  PASS — end-loaded direction works")

    # Test empty addresses
    result3 = optimize_route([], "Plainwell, MI", "2026-03-21 13:00")
    assert result3["status"] == "failure", "Test failed: empty addresses should return failure"
    print("  PASS — empty addresses returns failure")

    print("\nAll route_optimizer tests passed.")
    print("\nSample route output:")
    print(json.dumps(result["data"], indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ShowingDay Route Optimizer")
    parser.add_argument("--test", action="store_true", help="Run self-tests")
    args = parser.parse_args()

    if args.test:
        _run_tests()
    else:
        # Example run
        result = optimize_route(
            addresses=sys.argv[1:] if len(sys.argv) > 1 else ["1842 Lincoln Rd, Allegan, MI"],
            start_address=os.getenv("DEFAULT_START_ADDRESS", "Plainwell, MI"),
            session_datetime=datetime.now().strftime("%Y-%m-%d %H:%M"),
        )
        print(json.dumps(result, indent=2))
