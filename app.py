"""
app.py — ShowingDay Flask Application Entry Point

Local web app for Jason O'Brien — PREMIERE Group at Real Broker LLC
Serving the agent-facing UI and all API endpoints.

Run: python app.py
Access: http://localhost:5000

All credentials loaded from .env via python-dotenv.
Session state lives in session_state.json (single source of truth).
"""

import os
import json
import time
import traceback
from pathlib import Path
from datetime import datetime
from functools import wraps

from flask import Flask, request, jsonify, send_from_directory, send_file, abort, redirect, session, url_for
from flask_cors import CORS
from dotenv import load_dotenv

# ── Load environment ────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# ── Flask setup ─────────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder=str(BASE_DIR / "ui"), static_url_path="")
app.secret_key = os.getenv("FLASK_SECRET_KEY", "showingday-dev-key-change-in-production")
CORS(app)

# Handle HTTPS when behind Vercel/nginx proxy
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# ── Tool imports ────────────────────────────────────────────────────────────────
import sys
sys.path.insert(0, str(BASE_DIR / "tools"))

from session_logger import (
    get_session, update_session, reset_session,
    archive_session, log_tool_call, update_property_status
)
from route_optimizer import optimize_route
from crm_client_lookup import lookup_client
from calendar_manager import create_showing_events, confirm_event, decline_event, export_ics
from apination_webhook import parse_webhook_payload
from zillow_scraper import get_listing_data
from disclosure_analyzer import analyze_disclosure
from client_page_builder import build_client_page
from gmail_sender import send_client_email, generate_email_draft


# ── Helper: retry wrapper ────────────────────────────────────────────────────────
def with_retry(fn, *args, max_attempts=3, **kwargs):
    """
    Execute fn with up to max_attempts tries, with exponential backoff.
    Logs failures to run_log.json.
    """
    delays = [0, 5, 15]
    last_error = None
    for attempt in range(max_attempts):
        if attempt > 0:
            time.sleep(delays[attempt])
        try:
            result = fn(*args, **kwargs)
            if result.get("status") == "success":
                return result
            last_error = result.get("error", "Unknown error")
        except Exception as e:
            last_error = str(e)
            traceback.print_exc()

    return {"status": "failure", "data": None, "error": f"Failed after {max_attempts} attempts: {last_error}"}


def api_error(message: str, status_code: int = 500) -> tuple:
    """Return a JSON error response."""
    return jsonify({"status": "error", "error": message}), status_code


# ── Startup ────────────────────────────────────────────────────────────────────
def startup_check():
    """Read session state on startup and log to console."""
    session = get_session()
    print("\n" + "="*60)
    print("ShowingDay — Starting up")
    print(f"Session status: {session.get('status', 'unknown')}")
    if session.get("client"):
        print(f"Active client:  {session['client'].get('name', 'unknown')}")
    if session.get("session_date"):
        print(f"Session date:   {session['session_date']}")
    prop_count = len(session.get("properties", []))
    if prop_count:
        confirmed = sum(1 for p in session["properties"] if p.get("status") == "confirmed")
        print(f"Properties:     {prop_count} total, {confirmed} confirmed")
    maps_key = os.getenv("GOOGLE_MAPS_API_KEY", "")
    print(f"Google Maps:    {'configured' if maps_key else 'NOT configured — mock mode'}")
    print(f"Anthropic API:  {'configured' if os.getenv('ANTHROPIC_API_KEY') else 'NOT configured — mock mode'}")
    print(f"GHL API:        {'configured' if os.getenv('GHL_API_KEY') else 'NOT configured'}")
    print(f"Access UI at:   http://localhost:{os.getenv('PORT', 5000)}")
    print("="*60 + "\n")


# ── Static UI ──────────────────────────────────────────────────────────────────

@app.route("/")
def landing():
    """Serve the marketing landing page."""
    return send_from_directory(str(BASE_DIR / "ui"), "landing.html")


@app.route("/login")
def login_page():
    """Serve the login page."""
    return send_from_directory(str(BASE_DIR / "ui"), "login.html")


@app.route("/app")
def app_page():
    """Serve the agent-facing UI."""
    return send_from_directory(str(BASE_DIR / "ui"), "index.html")


@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    """
    Authenticate with demo credentials.

    Body: {"email": "demo@showingday.app", "password": "demo1234"}
    """
    body = request.get_json() or {}
    email = body.get("email", "").strip().lower()
    password = body.get("password", "")
    DEMO_EMAIL = os.getenv("DEMO_EMAIL", "demo@showingday.app")
    DEMO_PASSWORD = os.getenv("DEMO_PASSWORD", "demo1234")
    if email == DEMO_EMAIL.lower() and password == DEMO_PASSWORD:
        return jsonify({"status": "success", "redirect": "/app"})
    return jsonify({"status": "failure", "error": "Invalid credentials"}), 401


@app.route("/api/auth/logout", methods=["POST"])
def auth_logout():
    """Log out the current session."""
    return jsonify({"status": "success"})


# ── Clients endpoints ──────────────────────────────────────────────────────────

CLIENTS_FILE = BASE_DIR / "clients.json"


def _read_clients() -> dict:
    """Read clients.json. Returns empty structure on any failure."""
    try:
        if CLIENTS_FILE.exists():
            with open(CLIENTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {"clients": [], "last_updated": None}


def _write_clients(data: dict) -> bool:
    """Write clients.json. Returns False on read-only filesystem."""
    try:
        CLIENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CLIENTS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        return True
    except OSError:
        return False


def _compute_client_fields(client: dict) -> dict:
    """Add computed summary fields to a client dict."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    sessions = client.get("sessions", [])
    past = [s for s in sessions if s.get("date", "") < today]
    future = [s for s in sessions if s.get("date", "") >= today]
    last_date = max((s["date"] for s in past), default=None)
    next_date = min((s["date"] for s in future), default=None)
    client["total_sessions"] = len(sessions)
    client["past_sessions"] = len(past)
    client["future_sessions"] = len(future)
    client["last_showing_date"] = last_date
    client["next_showing_date"] = next_date
    return client


def _scan_archived_sessions(existing_ids: set) -> list:
    """
    Scan sessions/archive/ for completed sessions whose clients are not yet
    in clients.json and return stub client entries for them.
    """
    stubs = []
    archive_dir = BASE_DIR / "sessions" / "archive"
    if not archive_dir.exists():
        return stubs

    for session_dir in archive_dir.iterdir():
        if not session_dir.is_dir():
            continue
        state_file = session_dir / "session_state.json"
        if not state_file.exists():
            continue
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                sess = json.load(f)
            client_data = sess.get("client")
            if not client_data or not client_data.get("name"):
                continue
            cname = client_data["name"]
            # Build a stable ID from the name
            safe = cname.lower().replace(" ", "_")
            cid = f"client_{safe}_archived"
            if cid in existing_ids:
                continue
            existing_ids.add(cid)
            props = sess.get("properties", [])
            stub = {
                "id": cid,
                "name": cname,
                "email": client_data.get("email", ""),
                "phone": client_data.get("phone", ""),
                "crm_source": client_data.get("crm_source", "manual"),
                "added_date": sess.get("session_date", ""),
                "sessions": [{
                    "session_id": sess.get("session_id", session_dir.name),
                    "date": sess.get("session_date", ""),
                    "status": "completed",
                    "properties_shown": len(props),
                    "properties": [p["address"] for p in props if p.get("address")]
                }]
            }
            stubs.append(stub)
        except Exception:
            continue
    return stubs


@app.route("/api/clients", methods=["GET"])
def get_clients():
    """
    Return all clients with computed summary fields.
    Merges clients.json with stubs from archived sessions.
    Never crashes — returns empty list on any failure.
    """
    try:
        data = _read_clients()
        clients = data.get("clients", [])

        existing_ids = {c["id"] for c in clients}
        stubs = _scan_archived_sessions(existing_ids)
        all_clients = clients + stubs

        # Add computed fields
        all_clients = [_compute_client_fields(c) for c in all_clients]

        return jsonify({"status": "success", "data": {"clients": all_clients}})
    except Exception:
        return jsonify({"status": "success", "data": {"clients": []}})


@app.route("/api/clients", methods=["POST"])
def add_or_update_client():
    """
    Add or update a client in clients.json.
    Body: {name, email, phone, crm_source}
    """
    try:
        body = request.get_json() or {}
        name = (body.get("name") or "").strip()
        if not name:
            return api_error("name is required", 400)

        email = (body.get("email") or "").strip()
        phone = (body.get("phone") or "").strip()
        crm_source = (body.get("crm_source") or "manual").strip()

        data = _read_clients()
        clients = data.get("clients", [])

        # Check for existing client by name (case-insensitive)
        existing = next(
            (c for c in clients if c.get("name", "").lower() == name.lower()),
            None
        )

        if existing:
            # Update fields but preserve sessions
            existing["email"] = email or existing.get("email", "")
            existing["phone"] = phone or existing.get("phone", "")
            existing["crm_source"] = crm_source
            new_client = existing
        else:
            ts = int(datetime.utcnow().timestamp())
            safe = name.lower().replace(" ", "_")
            new_client = {
                "id": f"client_{safe}_{ts}",
                "name": name,
                "email": email,
                "phone": phone,
                "crm_source": crm_source,
                "added_date": datetime.utcnow().strftime("%Y-%m-%d"),
                "sessions": []
            }
            clients.append(new_client)

        data["clients"] = clients
        data["last_updated"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

        persisted = _write_clients(data)
        result = _compute_client_fields(dict(new_client))

        resp = {"status": "success", "data": result}
        if not persisted:
            resp["note"] = "Persistence unavailable on this filesystem."
        return jsonify(resp)

    except Exception as e:
        return api_error(f"Add client failed: {e}")


@app.route("/api/clients/<client_id>/session", methods=["POST"])
def link_session_to_client(client_id):
    """
    Link a completed session to a client record.
    Body: {session_id, date, status, properties_shown, properties}
    """
    try:
        body = request.get_json() or {}
        data = _read_clients()
        clients = data.get("clients", [])

        client = next((c for c in clients if c.get("id") == client_id), None)
        if not client:
            return api_error(f"Client {client_id} not found", 404)

        session_entry = {
            "session_id": body.get("session_id", ""),
            "date": body.get("date", ""),
            "status": body.get("status", "completed"),
            "properties_shown": body.get("properties_shown", 0),
            "properties": body.get("properties", [])
        }

        sessions = client.get("sessions", [])
        # Avoid duplicates by session_id
        if session_entry["session_id"]:
            sessions = [s for s in sessions if s.get("session_id") != session_entry["session_id"]]
        sessions.append(session_entry)
        client["sessions"] = sessions

        data["last_updated"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        _write_clients(data)

        return jsonify({"status": "success", "data": _compute_client_fields(dict(client))})

    except Exception as e:
        return api_error(f"Link session failed: {e}")


@app.route("/api/clients/<client_id>", methods=["DELETE"])
def delete_client(client_id):
    """Remove a client from clients.json."""
    try:
        data = _read_clients()
        clients = data.get("clients", [])
        original_count = len(clients)
        clients = [c for c in clients if c.get("id") != client_id]

        if len(clients) == original_count:
            return api_error(f"Client {client_id} not found", 404)

        data["clients"] = clients
        data["last_updated"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        _write_clients(data)

        return jsonify({"status": "success", "data": {"deleted": client_id}})

    except Exception as e:
        return api_error(f"Delete client failed: {e}")


@app.route("/output/<path:filename>")
def serve_output(filename):
    """Serve generated client pages from the output directory."""
    output_dir = BASE_DIR / "output"
    full_path = output_dir / filename
    if not full_path.exists():
        abort(404)
    return send_from_directory(str(output_dir), filename)


# ── Config endpoint ────────────────────────────────────────────────────────────

@app.route("/api/config")
def get_config():
    """
    Return non-sensitive configuration for the frontend.
    Maps API key is passed here so the UI can initialize Google Maps.
    """
    return jsonify({
        "maps_key": os.getenv("GOOGLE_MAPS_API_KEY", ""),
        "default_start_address": os.getenv("DEFAULT_START_ADDRESS", "Plainwell, MI 49080"),
        "features": {
            "google_maps": bool(os.getenv("GOOGLE_MAPS_API_KEY")),
            "google_calendar": bool(os.getenv("GOOGLE_CALENDAR_CREDENTIALS_JSON")),
            "gmail": bool(os.getenv("GMAIL_CREDENTIALS_JSON")),
            "crm_lofty": bool(os.getenv("LOFTY_API_KEY")),
            "crm_ghl": bool(os.getenv("GHL_API_KEY")),
            "anthropic": bool(os.getenv("ANTHROPIC_API_KEY"))
        }
    })


# ── Session endpoints ──────────────────────────────────────────────────────────

@app.route("/api/session", methods=["GET"])
def get_session_route():
    """Return current session state."""
    try:
        session = get_session()
        return jsonify({"status": "success", "data": session})
    except Exception as e:
        return api_error(f"Could not read session: {e}")


@app.route("/api/session/update", methods=["POST"])
def update_session_route():
    """Merge updates into session state."""
    try:
        data = request.get_json()
        if not data:
            return api_error("No data provided", 400)
        updated = update_session(data)
        return jsonify({"status": "success", "data": updated})
    except Exception as e:
        return api_error(f"Session update failed: {e}")


@app.route("/api/session/reset", methods=["POST"])
def reset_session_route():
    """Reset session to empty state."""
    try:
        result = reset_session()
        return jsonify(result)
    except Exception as e:
        return api_error(f"Session reset failed: {e}")


@app.route("/api/session/archive", methods=["POST"])
def archive_session_route():
    """Archive the current session and reset."""
    try:
        result = archive_session()
        return jsonify(result)
    except Exception as e:
        return api_error(f"Session archive failed: {e}")


# ── Route optimization ─────────────────────────────────────────────────────────

@app.route("/api/optimize-route", methods=["POST"])
def optimize_route_route():
    """
    Calculate optimized showing route.

    Body:
    {
        "addresses": ["123 Main St, Allegan, MI", ...],
        "start_address": "Plainwell, MI",
        "session_datetime": "2026-03-21 13:00",
        "window_end_time": "18:00",
        "max_showing_minutes": 30,
        "direction": "start-loaded"
    }
    """
    try:
        body = request.get_json() or {}
        addresses = body.get("addresses", [])
        start_address = body.get("start_address") or os.getenv("DEFAULT_START_ADDRESS", "Plainwell, MI")
        session_datetime = body.get("session_datetime", "")
        window_end_time = body.get("window_end_time")
        max_showing_minutes = int(body.get("max_showing_minutes", 30))
        direction = body.get("direction", "start-loaded")
        return_address = body.get("return_address") or None

        if not addresses:
            return api_error("No addresses provided", 400)
        if not session_datetime:
            return api_error("session_datetime is required", 400)

        result = with_retry(
            optimize_route,
            addresses=addresses,
            start_address=start_address,
            session_datetime=session_datetime,
            window_end_time=window_end_time,
            max_showing_minutes=max_showing_minutes,
            direction=direction,
            return_address=return_address
        )

        log_tool_call("route_optimizer", body, result)

        # On success, update session state with route data
        if result["status"] == "success":
            session_updates = {
                "session_date": session_datetime.split(" ")[0] if " " in session_datetime else session_datetime,
                "status": "route_optimized",
                "route": result["data"]["route"]
            }
            # Sync properties list with route
            current_session = get_session()
            existing_props = {p["address"]: p for p in current_session.get("properties", [])}
            new_props = []
            for stop in result["data"]["route"]:
                addr = stop["address"]
                prop = existing_props.get(addr, {
                    "address": addr,
                    "status": "pending",
                    "calendar_event_id": None,
                    "travel_event_id": None,
                    "property_data": None,
                    "disclosure_path": None,
                    "red_flags": None,
                    "mls_number": None
                })
                prop.update({
                    "order": stop["order"],
                    "arrival_time": stop["arrival_time"],
                    "showing_start": stop["showing_start"],
                    "showing_end": stop["showing_end"],
                    "departure_time": stop["departure_time"],
                    "travel_to_next_minutes": stop["travel_to_next_minutes"]
                })
                new_props.append(prop)
            session_updates["properties"] = new_props
            update_session(session_updates)

        return jsonify(result)

    except Exception as e:
        traceback.print_exc()
        return api_error(f"Route optimization failed: {e}")


# ── CRM client lookup ──────────────────────────────────────────────────────────

@app.route("/api/client-lookup", methods=["POST"])
def client_lookup_route():
    """
    Look up a client by name in Lofty → GHL → manual fallback.

    Body: {"name": "Sarah Johnson"}
    """
    try:
        body = request.get_json() or {}
        name = body.get("name", "").strip()

        if not name:
            return api_error("Client name is required", 400)

        result = with_retry(lookup_client, name)
        log_tool_call("crm_client_lookup", {"name": name}, result)

        # Store client in session on success
        if result["status"] == "success" and not result["data"].get("not_found"):
            update_session({"client": result["data"]})

        return jsonify(result)

    except Exception as e:
        return api_error(f"Client lookup failed: {e}")


# ── Calendar management ────────────────────────────────────────────────────────

@app.route("/api/calendar/create", methods=["POST"])
def calendar_create_route():
    """
    Create tentative Google Calendar events for all showings.
    Falls back to ICS export if Calendar API unavailable.

    Body: {"route": [...], "client_name": "Sarah Johnson", "session_date": "2026-03-21"}
    """
    try:
        body = request.get_json() or {}
        route = body.get("route", [])
        session = get_session()
        client_name = body.get("client_name") or (session.get("client") or {}).get("name", "Client")
        session_date = body.get("session_date") or session.get("session_date", "")

        if not route:
            return api_error("Route data is required", 400)

        result = with_retry(create_showing_events, route, client_name, session_date)
        log_tool_call("calendar_manager.create", body, result)

        # If Calendar API fails, offer ICS fallback
        if result["status"] == "failure":
            ics_result = export_ics(route, client_name, session_date)
            return jsonify({
                "status": "fallback",
                "data": ics_result.get("data"),
                "error": result["error"],
                "fallback_note": "Google Calendar not configured. ICS file generated for manual import."
            })

        return jsonify(result)

    except Exception as e:
        return api_error(f"Calendar create failed: {e}")


@app.route("/api/calendar/update", methods=["POST"])
def calendar_update_route():
    """
    Confirm a showing event (remove TENTATIVE prefix).

    Body: {"event_id": "...", "address": "...", "action": "confirm"}
    """
    try:
        body = request.get_json() or {}
        event_id = body.get("event_id", "")
        address = body.get("address", "")
        action = body.get("action", "confirm")

        if not event_id:
            return api_error("event_id is required", 400)

        if action == "confirm":
            result = with_retry(confirm_event, event_id, address)
        else:
            result = {"status": "failure", "data": None, "error": f"Unknown action: {action}"}

        log_tool_call("calendar_manager.update", body, result)
        return jsonify(result)

    except Exception as e:
        return api_error(f"Calendar update failed: {e}")


@app.route("/api/calendar/delete", methods=["POST"])
def calendar_delete_route():
    """
    Delete a showing event when declined.

    Body: {"event_id": "...", "address": "..."}
    """
    try:
        body = request.get_json() or {}
        event_id = body.get("event_id", "")
        address = body.get("address", "")

        if not event_id:
            return api_error("event_id is required", 400)

        result = with_retry(decline_event, event_id, address)
        log_tool_call("calendar_manager.delete", body, result)
        return jsonify(result)

    except Exception as e:
        return api_error(f"Calendar delete failed: {e}")


# ── Webhook receiver ───────────────────────────────────────────────────────────

@app.route("/webhook/showingtime", methods=["POST"])
def showingtime_webhook():
    """
    Receive ShowingTime status updates from GHL via API Nation.
    Auto-updates session state — no agent intervention required.

    See: docs/apination_setup.md for webhook configuration.
    """
    try:
        # Accept both JSON and form data
        if request.is_json:
            payload = request.get_json()
        else:
            payload = request.form.to_dict()

        if not payload:
            return api_error("Empty webhook payload", 400)

        result = parse_webhook_payload(payload)
        log_tool_call("apination_webhook", {"source": "POST /webhook/showingtime"}, result)

        if result["status"] == "success":
            parsed = result["data"]
            # If confirmed, mark for property research trigger
            if parsed["status"] == "confirmed":
                update_session({"pending_research": parsed.get("address")})

            return jsonify({
                "status": "ok",
                "message": f"Status updated: {parsed.get('address')} → {parsed.get('status')}"
            })
        else:
            return api_error(result.get("error", "Webhook parse failed"), 400)

    except Exception as e:
        traceback.print_exc()
        return api_error(f"Webhook processing failed: {e}")


# ── Property research ──────────────────────────────────────────────────────────

@app.route("/api/property-research", methods=["POST"])
def property_research_route():
    """
    Fetch Zillow listing data for a property.

    Body: {"address": "1842 Lincoln Rd, Allegan, MI"}
    """
    try:
        body = request.get_json() or {}
        address = body.get("address", "").strip()

        if not address:
            return api_error("Address is required", 400)

        result = with_retry(get_listing_data, address)
        log_tool_call("zillow_scraper", {"address": address}, result)

        # Store property data in session
        if result["status"] == "success":
            session = get_session()
            for prop in session.get("properties", []):
                if prop.get("address", "").lower() == address.lower():
                    prop["property_data"] = result["data"]
            update_session({"properties": session.get("properties", [])})

        return jsonify(result)

    except Exception as e:
        return api_error(f"Property research failed: {e}")


# ── Disclosure analysis ────────────────────────────────────────────────────────

@app.route("/api/analyze-disclosure", methods=["POST"])
def analyze_disclosure_route():
    """
    Analyze a disclosure PDF for red flags.

    Accepts multipart/form-data with 'pdf' file field and 'address' field.
    """
    import tempfile

    try:
        address = request.form.get("address", "")
        pdf_file = request.files.get("pdf")

        if not pdf_file:
            return api_error("PDF file is required", 400)

        # Save uploaded file to temp location
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            pdf_file.save(tmp.name)
            tmp_path = tmp.name

        result = with_retry(analyze_disclosure, tmp_path)
        log_tool_call("disclosure_analyzer", {"address": address, "filename": pdf_file.filename}, result)

        # Optionally save the PDF to output directory
        if address:
            session = get_session()
            session_date = session.get("session_date", datetime.utcnow().strftime("%Y-%m-%d"))
            client = (session.get("client") or {}).get("name", "client")
            safe_client = client.lower().replace(" ", "_")
            output_dir = BASE_DIR / "output" / f"client_{session_date}_{safe_client}" / "disclosures"
            output_dir.mkdir(parents=True, exist_ok=True)
            safe_addr = address.replace(" ", "_").replace(",", "").replace("/", "_")[:40]
            dest = output_dir / f"{safe_addr}.pdf"
            import shutil
            shutil.copy2(tmp_path, dest)

            # Update property record with disclosure path and red flags
            if result["status"] == "success":
                for prop in session.get("properties", []):
                    if address.lower() in prop.get("address", "").lower():
                        prop["disclosure_path"] = str(dest)
                        prop["red_flags"] = result.get("data")
                update_session({"properties": session["properties"]})

        # Clean up temp file
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

        return jsonify(result)

    except Exception as e:
        traceback.print_exc()
        return api_error(f"Disclosure analysis failed: {e}")


# ── Client page builder ────────────────────────────────────────────────────────

@app.route("/api/build-client-page", methods=["POST"])
def build_client_page_route():
    """
    Generate the client-facing showing day HTML page.

    Body: {"show_red_flags": false}
    """
    try:
        body = request.get_json() or {}
        show_red_flags = body.get("show_red_flags", False)

        session = get_session()

        # Build property summaries dict
        property_summaries = {}
        for prop in session.get("properties", []):
            addr = prop.get("address", "")
            if prop.get("property_data"):
                property_summaries[addr] = prop["property_data"]

        result = build_client_page(session, property_summaries, show_red_flags)
        log_tool_call("client_page_builder", {"show_red_flags": show_red_flags}, result)

        if result["status"] == "success":
            update_session({"client_page_path": result["data"]["output_path"]})

        return jsonify(result)

    except Exception as e:
        return api_error(f"Client page build failed: {e}")


# ── Gmail sender ───────────────────────────────────────────────────────────────

@app.route("/api/send-client-email", methods=["POST"])
def send_client_email_route():
    """
    Send the client page link via Gmail.

    Body: {
        "to_email": "sarah@example.com",
        "client_name": "Sarah Johnson",
        "page_url": "http://localhost:5000/output/..."
    }
    """
    try:
        body = request.get_json() or {}
        session = get_session()

        client = session.get("client") or {}
        to_email = body.get("to_email") or client.get("email", "")
        client_name = body.get("client_name") or client.get("name", "")
        page_url = body.get("page_url") or session.get("client_page_path", "")
        session_date = session.get("session_date", "")

        # Format date for email
        try:
            date_obj = datetime.strptime(session_date, "%Y-%m-%d")
            session_date_display = date_obj.strftime("%B %-d, %Y")
        except Exception:
            session_date_display = session_date

        if not to_email:
            return api_error("to_email is required (check CRM lookup or enter manually)", 400)

        result = with_retry(send_client_email, to_email, client_name, page_url, session_date_display)
        log_tool_call("gmail_sender", {"to": to_email}, result)

        # If Gmail fails, always return the draft for manual sending
        if result["status"] == "failure":
            draft_result = generate_email_draft(client_name, page_url, session_date_display)
            return jsonify({
                "status": "fallback",
                "data": draft_result.get("data"),
                "error": result["error"],
                "fallback_note": "Gmail not configured. Use the email draft above to send manually."
            })

        return jsonify(result)

    except Exception as e:
        return api_error(f"Email send failed: {e}")


# ── Property status toggle ─────────────────────────────────────────────────────

@app.route("/api/property/status", methods=["POST"])
def update_property_status_route():
    """
    Manually update a property's showing status.

    Body: {"address": "...", "status": "confirmed|declined|pending|requested"}
    """
    try:
        body = request.get_json() or {}
        address = body.get("address", "")
        status = body.get("status", "")

        valid_statuses = ["pending", "requested", "tentative", "confirmed", "declined"]
        if status not in valid_statuses:
            return api_error(f"Invalid status. Must be one of: {valid_statuses}", 400)

        result = update_property_status(address, status)
        log_tool_call("session_logger.update_property_status", body, result)
        return jsonify(result)

    except Exception as e:
        return api_error(f"Status update failed: {e}")


# ── Google Calendar OAuth & Events ─────────────────────────────────────────────

GCAL_SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']


def _build_gcal_flow(redirect_uri):
    """Build Google OAuth2 flow from credentials JSON env var."""
    creds_json = os.getenv('GOOGLE_CALENDAR_CREDENTIALS_JSON', '')
    if not creds_json:
        return None
    try:
        from google_auth_oauthlib.flow import Flow
        creds_dict = json.loads(creds_json)
        return Flow.from_client_config(creds_dict, scopes=GCAL_SCOPES, redirect_uri=redirect_uri)
    except Exception:
        return None


def _gcal_redirect_uri():
    """Build OAuth callback URI — handles HTTPS proxy on Vercel."""
    proto = request.headers.get('X-Forwarded-Proto', request.scheme)
    return f"{proto}://{request.host}/auth/google/calendar/callback"


@app.route('/auth/google/calendar')
def google_calendar_auth():
    """Step 1 of Google Calendar OAuth — redirect to Google consent screen."""
    if request.scheme == 'http' and not request.headers.get('X-Forwarded-Proto'):
        os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
    else:
        os.environ.pop('OAUTHLIB_INSECURE_TRANSPORT', None)

    flow = _build_gcal_flow(_gcal_redirect_uri())
    if not flow:
        return redirect('/app?cal_error=no_credentials')

    auth_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )
    session['gcal_oauth_state'] = state
    return redirect(auth_url)


@app.route('/auth/google/calendar/callback')
def google_calendar_callback():
    """Step 2 of Google Calendar OAuth — exchange code for token."""
    if request.scheme == 'http' and not request.headers.get('X-Forwarded-Proto'):
        os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

    flow = _build_gcal_flow(_gcal_redirect_uri())
    if not flow:
        return redirect('/app?cal_error=no_credentials')

    try:
        # When behind HTTPS proxy, request.url arrives as http — fix it
        auth_response = request.url
        if request.headers.get('X-Forwarded-Proto') == 'https':
            auth_response = auth_response.replace('http://', 'https://', 1)

        flow.fetch_token(authorization_response=auth_response)
        creds = flow.credentials
        session['calendar_token'] = {
            'token': creds.token,
            'refresh_token': creds.refresh_token,
            'token_uri': creds.token_uri,
            'client_id': creds.client_id,
            'client_secret': creds.client_secret,
            'scopes': list(creds.scopes) if creds.scopes else GCAL_SCOPES
        }
        return redirect('/app?cal_connected=1')
    except Exception as e:
        app.logger.error(f"Google Calendar OAuth error: {e}")
        return redirect('/app?cal_error=oauth_failed')


@app.route('/api/calendar/auth-status')
def calendar_auth_status():
    """Check if Google Calendar is connected for this session."""
    return jsonify({'authenticated': bool(session.get('calendar_token'))})


@app.route('/api/calendar/disconnect', methods=['POST'])
def calendar_disconnect():
    """Remove Google Calendar token from session."""
    session.pop('calendar_token', None)
    return jsonify({'status': 'success'})


@app.route('/api/calendar/events')
def calendar_events_for_date():
    """
    Fetch Google Calendar events for a given date.
    Query params:
      date      — YYYY-MM-DD
      tz_offset — e.g. "-05:00" (browser's local timezone offset)
    """
    date_str = request.args.get('date', '')
    tz_offset = request.args.get('tz_offset', '-05:00')

    if not date_str:
        return jsonify({'status': 'failure', 'error': 'date required', 'data': {'events': []}})

    token_dict = session.get('calendar_token')
    if not token_dict:
        return jsonify({'status': 'failure', 'error': 'not_authenticated', 'data': {'events': []}})

    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from google.auth.transport.requests import Request as GoogleAuthRequest

        creds = Credentials(
            token=token_dict['token'],
            refresh_token=token_dict.get('refresh_token'),
            token_uri=token_dict.get('token_uri', 'https://oauth2.googleapis.com/token'),
            client_id=token_dict['client_id'],
            client_secret=token_dict['client_secret'],
            scopes=token_dict.get('scopes', GCAL_SCOPES)
        )

        if creds.expired and creds.refresh_token:
            creds.refresh(GoogleAuthRequest())
            session['calendar_token'] = {**token_dict, 'token': creds.token}

        service = build('calendar', 'v3', credentials=creds)

        events_result = service.events().list(
            calendarId='primary',
            timeMin=f"{date_str}T00:00:00{tz_offset}",
            timeMax=f"{date_str}T23:59:59{tz_offset}",
            singleEvents=True,
            orderBy='startTime',
            maxResults=50
        ).execute()

        events = []
        for ev in events_result.get('items', []):
            start = ev['start'].get('dateTime', ev['start'].get('date', ''))
            end   = ev['end'].get('dateTime', ev['end'].get('date', ''))
            events.append({
                'id':      ev['id'],
                'title':   ev.get('summary', 'Busy'),
                'start':   start,
                'end':     end,
                'all_day': 'date' in ev['start'],
                'color':   ev.get('colorId')
            })

        return jsonify({'status': 'success', 'data': {'events': events}})

    except Exception as e:
        app.logger.error(f"Calendar events fetch error: {e}")
        return jsonify({'status': 'failure', 'error': str(e), 'data': {'events': []}})


# ── Error handlers ─────────────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    return api_error("Endpoint not found", 404)


@app.errorhandler(405)
def method_not_allowed(e):
    return api_error("Method not allowed", 405)


@app.errorhandler(500)
def internal_error(e):
    return api_error(f"Internal server error: {e}", 500)


# ── Entry point ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    startup_check()
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_ENV", "development") == "development"
    app.run(host="0.0.0.0", port=port, debug=debug)
