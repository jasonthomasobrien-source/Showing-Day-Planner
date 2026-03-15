"""
session_logger.py — ShowingDay Session State & Run Log Manager

Reads and writes session_state.json (single source of truth for all session data)
and run_log.json (immutable append-only tool call log).

All other tools are stateless — this module owns all persistence.

CLI: python tools/session_logger.py --test
"""

import copy
import json
import os
import shutil
import sys
import argparse
from datetime import datetime
from pathlib import Path

# ── Path resolution ────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
SESSION_FILE = BASE_DIR / "session_state.json"
RUN_LOG_FILE = BASE_DIR / "run_log.json"
ARCHIVE_DIR = BASE_DIR / "sessions" / "archive"

EMPTY_SESSION = {
    "session_id": None,
    "session_date": None,
    "client": None,
    "properties": [],
    "calendar_events": [],
    "tool_calls": [],
    "status": "idle"
}


# ── Core read/write ────────────────────────────────────────────────────────────

def get_session() -> dict:
    """
    Return the full current session state dict.
    If session_state.json is missing or corrupt, returns a fresh empty session.
    """
    try:
        if SESSION_FILE.exists():
            with open(SESSION_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Backfill any missing top-level keys from EMPTY_SESSION
            for key, default in EMPTY_SESSION.items():
                if key not in data:
                    data[key] = copy.deepcopy(default)
            return data
        else:
            return copy.deepcopy(EMPTY_SESSION)
    except (json.JSONDecodeError, OSError) as e:
        print(f"[session_logger] WARNING: Could not read session_state.json: {e}. Returning empty session.")
        return copy.deepcopy(EMPTY_SESSION)


def _write_session(state: dict) -> None:
    """Write session state to disk (internal use only).
    Silently skips on read-only filesystems (e.g. Vercel serverless)."""
    try:
        SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, default=str)
    except OSError as e:
        print(f"[session_logger] WARNING: Could not write session_state.json (read-only fs?): {e}")


def update_session(updates: dict) -> dict:
    """
    Merge a dict of updates into the current session state and persist.

    Shallow merge at the top level. For nested objects (like 'client'),
    pass the full replacement object.

    Returns the updated session state.
    """
    state = get_session()
    state.update(updates)
    _write_session(state)
    return state


# ── Property helpers ───────────────────────────────────────────────────────────

def update_property_status(address: str, status: str, extra_fields: dict = None) -> dict:
    """
    Find a property in session state by address (case-insensitive substring match)
    and update its status field.

    Also accepts optional extra_fields dict to merge additional keys onto the property.

    Valid statuses: pending, requested, tentative, confirmed, declined, auto-updated

    Returns {"status": "success|failure", "data": updated_property|None, "error": null|str}
    """
    state = get_session()
    matched = None

    for prop in state.get("properties", []):
        prop_address = prop.get("address", "")
        if address.lower().strip() in prop_address.lower() or prop_address.lower() in address.lower().strip():
            prop["status"] = status
            prop["status_updated_at"] = datetime.utcnow().isoformat()
            if extra_fields:
                prop.update(extra_fields)
            matched = prop
            break

    if matched is None:
        return {
            "status": "failure",
            "data": None,
            "error": f"Property not found in session for address: {address}"
        }

    _write_session(state)
    return {"status": "success", "data": matched, "error": None}


def add_property(address: str, mls_number: str = None, max_showing_minutes: int = 30) -> dict:
    """
    Add a new property to the session properties list.
    Returns the updated session state.
    """
    state = get_session()
    prop = {
        "address": address,
        "mls_number": mls_number,
        "max_showing_minutes": max_showing_minutes,
        "status": "pending",
        "status_updated_at": datetime.utcnow().isoformat(),
        "calendar_event_id": None,
        "travel_event_id": None,
        "showing_start": None,
        "showing_end": None,
        "arrival_time": None,
        "departure_time": None,
        "travel_to_next_minutes": None,
        "order": len(state.get("properties", [])) + 1,
        "property_data": None,
        "disclosure_path": None,
        "red_flags": None
    }
    state.setdefault("properties", []).append(prop)
    _write_session(state)
    return {"status": "success", "data": prop, "error": None}


# ── Calendar event tracking ────────────────────────────────────────────────────

def add_calendar_event(event_id: str, event_type: str, address: str, title: str) -> dict:
    """
    Log a Google Calendar event ID to session state.
    event_type: "showing" | "travel"
    """
    state = get_session()
    event_entry = {
        "event_id": event_id,
        "event_type": event_type,
        "address": address,
        "title": title,
        "created_at": datetime.utcnow().isoformat()
    }
    state.setdefault("calendar_events", []).append(event_entry)

    # Also update the property record
    for prop in state.get("properties", []):
        if prop.get("address", "").lower() == address.lower():
            if event_type == "showing":
                prop["calendar_event_id"] = event_id
            elif event_type == "travel":
                prop["travel_event_id"] = event_id

    _write_session(state)
    return {"status": "success", "data": event_entry, "error": None}


# ── Run log ────────────────────────────────────────────────────────────────────

def log_tool_call(tool_name: str, input_data: dict, result: dict) -> dict:
    """
    Append a tool call record to run_log.json.
    Includes timestamp, tool name, inputs, result status, and any error message.
    """
    try:
        if RUN_LOG_FILE.exists():
            with open(RUN_LOG_FILE, "r", encoding="utf-8") as f:
                log = json.load(f)
        else:
            log = []

        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "tool": tool_name,
            "input": input_data,
            "result_status": result.get("status", "unknown"),
            "error": result.get("error"),
            "data_summary": _summarize_result(result)
        }
        log.append(entry)

        try:
            RUN_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(RUN_LOG_FILE, "w", encoding="utf-8") as f:
                json.dump(log, f, indent=2, default=str)
        except OSError as e:
            print(f"[session_logger] WARNING: Could not write run_log.json (read-only fs?): {e}")

        return {"status": "success", "data": entry, "error": None}

    except Exception as e:
        print(f"[session_logger] WARNING: Could not write to run_log.json: {e}")
        return {"status": "failure", "data": None, "error": str(e)}


def _summarize_result(result: dict) -> str:
    """Create a short human-readable summary of a tool result for the log."""
    if result.get("status") == "success":
        data = result.get("data")
        if isinstance(data, dict):
            return f"success — {list(data.keys())}"
        elif isinstance(data, list):
            return f"success — {len(data)} items"
        else:
            return "success"
    else:
        return f"failure: {result.get('error', 'unknown error')}"


# ── Reset & archive ────────────────────────────────────────────────────────────

def reset_session() -> dict:
    """
    Reset session_state.json to empty state.
    Does NOT archive — call archive_session() first if needed.
    """
    empty = copy.deepcopy(EMPTY_SESSION)
    _write_session(empty)
    return {"status": "success", "data": empty, "error": None}


def archive_session() -> dict:
    """
    Archive completed session files to sessions/archive/[date]_[client]/.
    Copies session_state.json and run_log.json to archive, then resets session.
    """
    state = get_session()
    date_str = state.get("session_date") or datetime.utcnow().strftime("%Y-%m-%d")
    client = state.get("client") or {}
    client_name = client.get("name", "unknown").replace(" ", "_").lower()

    archive_folder_name = f"{date_str}_{client_name}"
    archive_path = ARCHIVE_DIR / archive_folder_name

    # Avoid overwriting an existing archive by appending a counter
    counter = 1
    base_path = archive_path
    while archive_path.exists():
        archive_path = Path(f"{base_path}_{counter}")
        counter += 1

    archive_path.mkdir(parents=True, exist_ok=True)

    archived_files = []
    for src_file in [SESSION_FILE, RUN_LOG_FILE]:
        if src_file.exists():
            dest = archive_path / src_file.name
            shutil.copy2(src_file, dest)
            archived_files.append(str(dest))

    reset_session()

    return {
        "status": "success",
        "data": {
            "archive_path": str(archive_path),
            "archived_files": archived_files
        },
        "error": None
    }


# ── CLI self-test ──────────────────────────────────────────────────────────────

def _run_tests():
    """Self-test for session_logger. Uses a temporary session file."""
    import tempfile

    print("Running session_logger self-test...")

    # Temporarily redirect to a temp dir
    global SESSION_FILE, RUN_LOG_FILE
    original_session = SESSION_FILE
    original_log = RUN_LOG_FILE

    with tempfile.TemporaryDirectory() as tmpdir:
        SESSION_FILE = Path(tmpdir) / "session_state.json"
        RUN_LOG_FILE = Path(tmpdir) / "run_log.json"

        # Test 1: get_session on missing file returns empty
        s = get_session()
        assert s["status"] == "idle", "Test 1 failed: default status should be idle"
        print("  PASS — get_session() returns empty state when file missing")

        # Test 2: update_session merges correctly
        update_session({"session_date": "2026-03-15", "status": "active"})
        s = get_session()
        assert s["session_date"] == "2026-03-15", "Test 2 failed"
        assert s["status"] == "active", "Test 2 failed"
        print("  PASS — update_session() merges and persists")

        # Test 3: add_property and update_property_status
        add_property("123 Maple St, Allegan, MI", max_showing_minutes=30)
        result = update_property_status("123 Maple St", "confirmed")
        assert result["status"] == "success", f"Test 3 failed: {result}"
        s = get_session()
        assert s["properties"][0]["status"] == "confirmed", "Test 3 failed: status not updated"
        print("  PASS — add_property() and update_property_status() work")

        # Test 4: update_property_status on unknown address returns failure
        result = update_property_status("999 Unknown Ave", "confirmed")
        assert result["status"] == "failure", "Test 4 failed"
        print("  PASS — update_property_status() returns failure for unknown address")

        # Test 5: log_tool_call appends to run log
        log_tool_call("route_optimizer", {"addresses": ["a", "b"]}, {"status": "success", "data": {}, "error": None})
        with open(RUN_LOG_FILE) as f:
            log = json.load(f)
        assert len(log) == 1, "Test 5 failed"
        assert log[0]["tool"] == "route_optimizer", "Test 5 failed"
        print("  PASS — log_tool_call() appends to run_log.json")

        # Test 6: reset_session
        reset_session()
        s = get_session()
        assert s["status"] == "idle", "Test 6 failed"
        print("  PASS — reset_session() resets to empty state")

    # Restore
    SESSION_FILE = original_session
    RUN_LOG_FILE = original_log

    print("\nAll session_logger tests passed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ShowingDay Session Logger")
    parser.add_argument("--test", action="store_true", help="Run self-tests")
    args = parser.parse_args()

    if args.test:
        _run_tests()
    else:
        print("Current session state:")
        print(json.dumps(get_session(), indent=2))
