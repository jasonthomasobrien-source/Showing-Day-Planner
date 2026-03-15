"""
test_tools.py — ShowingDay Tool Test Suite

Runs tests for all ShowingDay tools. Each tool has a --test CLI mode
which is also callable from this test runner.

Run: python tests/test_tools.py
Or:  python tests/test_tools.py --tool route_optimizer
"""

import sys
import os
import json
import unittest
import argparse
import tempfile
from pathlib import Path

# Add tools to path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "tools"))

# Load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass


# ── session_logger tests ───────────────────────────────────────────────────────
class TestSessionLogger(unittest.TestCase):

    def setUp(self):
        """Redirect session files to a fresh temp directory for each test."""
        import session_logger as sl
        import uuid
        self._sl = sl
        self._tmpdir = tempfile.mkdtemp()
        self._orig_session = sl.SESSION_FILE
        self._orig_log = sl.RUN_LOG_FILE
        # Each test gets a truly unique path using UUID
        uid = uuid.uuid4().hex
        sl.SESSION_FILE = Path(self._tmpdir) / f"session_{uid}.json"
        sl.RUN_LOG_FILE = Path(self._tmpdir) / f"run_log_{uid}.json"

    def tearDown(self):
        """Restore original file paths and clean up real session file."""
        self._sl.SESSION_FILE = self._orig_session
        self._sl.RUN_LOG_FILE = self._orig_log
        # Reset the real session_state.json so other test classes don't see leftover state
        self._sl.reset_session()

    def test_get_session_missing_file_returns_empty(self):
        s = self._sl.get_session()
        self.assertEqual(s["status"], "idle")
        self.assertIsNone(s["client"])
        self.assertEqual(s["properties"], [])

    def test_update_session_merges_and_persists(self):
        self._sl.update_session({"session_date": "2026-03-21", "status": "active"})
        s = self._sl.get_session()
        self.assertEqual(s["session_date"], "2026-03-21")
        self.assertEqual(s["status"], "active")

    def test_add_and_update_property_status(self):
        self._sl.add_property("123 Main St, Allegan, MI")
        result = self._sl.update_property_status("123 Main St", "confirmed")
        self.assertEqual(result["status"], "success")
        s = self._sl.get_session()
        self.assertEqual(s["properties"][0]["status"], "confirmed")

    def test_update_unknown_address_returns_failure(self):
        result = self._sl.update_property_status("999 Nonexistent Ave", "confirmed")
        self.assertEqual(result["status"], "failure")

    def test_log_tool_call(self):
        self._sl.log_tool_call(
            "route_optimizer",
            {"addresses": ["a", "b"]},
            {"status": "success", "data": {}, "error": None}
        )
        with open(self._sl.RUN_LOG_FILE) as f:
            log = json.load(f)
        self.assertEqual(len(log), 1)
        self.assertEqual(log[0]["tool"], "route_optimizer")
        self.assertEqual(log[0]["result_status"], "success")

    def test_reset_session(self):
        self._sl.update_session({"session_date": "2026-03-21", "status": "active"})
        self._sl.reset_session()
        s = self._sl.get_session()
        self.assertEqual(s["status"], "idle")
        self.assertIsNone(s["session_date"])

    def test_archive_session(self):
        self._sl.update_session({"session_date": "2026-03-21", "status": "active"})
        self._sl.update_session({"client": {"name": "Sarah Johnson"}})
        result = self._sl.archive_session()
        self.assertEqual(result["status"], "success")
        archive_path = Path(result["data"]["archive_path"])
        self.assertTrue(archive_path.exists())


# ── route_optimizer tests ──────────────────────────────────────────────────────
class TestRouteOptimizer(unittest.TestCase):

    def setUp(self):
        from route_optimizer import optimize_route, MOCK_ROUTE_DATA
        self.optimize_route = optimize_route
        self.MOCK_ROUTE_DATA = MOCK_ROUTE_DATA

    def test_empty_addresses_returns_failure(self):
        result = self.optimize_route([], "Plainwell, MI", "2026-03-21 13:00")
        self.assertEqual(result["status"], "failure")

    def test_mock_mode_returns_success(self):
        # Force mock mode by temporarily unsetting the key
        orig = os.environ.pop("GOOGLE_MAPS_API_KEY", None)
        try:
            result = self.optimize_route(
                addresses=["1842 Lincoln Rd, Allegan, MI", "728 Oak Grove Rd, Plainwell, MI"],
                start_address="Plainwell, MI",
                session_datetime="2026-03-21 13:00"
            )
            self.assertEqual(result["status"], "success")
            self.assertEqual(len(result["data"]["route"]), 2)
        finally:
            if orig:
                os.environ["GOOGLE_MAPS_API_KEY"] = orig

    def test_route_has_required_fields(self):
        orig = os.environ.pop("GOOGLE_MAPS_API_KEY", None)
        try:
            result = self.optimize_route(
                addresses=["123 Main St, Allegan, MI"],
                start_address="Plainwell, MI",
                session_datetime="2026-03-21 13:00"
            )
            stop = result["data"]["route"][0]
            for field in ["order", "address", "arrival_time", "showing_start", "showing_end", "departure_time"]:
                self.assertIn(field, stop, f"Missing field: {field}")
        finally:
            if orig:
                os.environ["GOOGLE_MAPS_API_KEY"] = orig

    def test_start_loaded_direction(self):
        orig = os.environ.pop("GOOGLE_MAPS_API_KEY", None)
        try:
            result = self.optimize_route(
                addresses=["A, MI", "B, MI"],
                start_address="C, MI",
                session_datetime="2026-03-21 13:00",
                direction="start-loaded"
            )
            self.assertEqual(result["status"], "success")
        finally:
            if orig:
                os.environ["GOOGLE_MAPS_API_KEY"] = orig

    def test_fits_window_key_present(self):
        orig = os.environ.pop("GOOGLE_MAPS_API_KEY", None)
        try:
            result = self.optimize_route(
                addresses=["1842 Lincoln Rd, Allegan, MI"],
                start_address="Plainwell, MI",
                session_datetime="2026-03-21 13:00",
                window_end_time="18:00"
            )
            self.assertIn("fits_window", result["data"])
        finally:
            if orig:
                os.environ["GOOGLE_MAPS_API_KEY"] = orig


# ── crm_client_lookup tests ────────────────────────────────────────────────────
class TestCrmClientLookup(unittest.TestCase):

    def setUp(self):
        from crm_client_lookup import lookup_client
        self.lookup_client = lookup_client

    def test_empty_name_returns_failure(self):
        result = self.lookup_client("")
        self.assertEqual(result["status"], "failure")

    def test_whitespace_name_returns_failure(self):
        result = self.lookup_client("   ")
        self.assertEqual(result["status"], "failure")

    def test_unfound_client_returns_manual_fallback(self):
        result = self.lookup_client("Nobody Whodoesntexist XYZABC123")
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["data"]["crm_source"], "manual")
        self.assertTrue(result["data"]["not_found"])

    def test_response_has_required_fields(self):
        result = self.lookup_client("Test Person")
        for field in ["name", "email", "phone", "crm_source"]:
            self.assertIn(field, result["data"])


# ── apination_webhook tests ────────────────────────────────────────────────────
class TestApinationWebhook(unittest.TestCase):

    def setUp(self):
        from apination_webhook import parse_webhook_payload, STATUS_MAP
        self.parse = parse_webhook_payload
        self.STATUS_MAP = STATUS_MAP

    def test_valid_confirmed_payload(self):
        payload = {
            "type": "showingtime_status",
            "data": {
                "address": "1842 Lincoln Rd, Allegan, MI 49010",
                "status": "confirmed",
                "timestamp": "2026-03-21T14:32:00Z"
            }
        }
        result = self.parse(payload)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["data"]["status"], "confirmed")

    def test_valid_declined_payload(self):
        payload = {"address": "728 Oak Grove Rd, Plainwell, MI", "status": "declined"}
        result = self.parse(payload)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["data"]["status"], "declined")

    def test_empty_payload_returns_failure(self):
        result = self.parse({})
        self.assertEqual(result["status"], "failure")

    def test_none_payload_returns_failure(self):
        result = self.parse(None)
        self.assertEqual(result["status"], "failure")

    def test_status_normalization(self):
        for raw, expected in [
            ("approved", "confirmed"),
            ("accepted", "confirmed"),
            ("denied", "declined"),
            ("cancelled", "declined"),
            ("canceled", "declined"),
        ]:
            payload = {"address": "Test Addr, MI", "status": raw}
            result = self.parse(payload)
            self.assertEqual(result["data"]["status"], expected, f"'{raw}' should map to '{expected}'")

    def test_missing_address_returns_failure(self):
        payload = {"status": "confirmed"}
        result = self.parse(payload)
        self.assertEqual(result["status"], "failure")

    def test_confirmation_number_extracted(self):
        payload = {
            "data": {
                "address": "Test St, MI",
                "status": "confirmed",
                "confirmation_number": "ST-12345"
            }
        }
        result = self.parse(payload)
        self.assertEqual(result["data"]["confirmation_number"], "ST-12345")


# ── zillow_scraper tests ───────────────────────────────────────────────────────
class TestZillowScraper(unittest.TestCase):

    def setUp(self):
        from zillow_scraper import get_listing_data, _build_mock_listing
        self.get_listing = get_listing_data
        self.build_mock = _build_mock_listing

    def test_empty_address_returns_failure(self):
        result = self.get_listing("")
        self.assertEqual(result["status"], "failure")

    def test_valid_address_returns_success_with_mock(self):
        result = self.get_listing("1842 Lincoln Rd, Allegan, MI 49010")
        self.assertEqual(result["status"], "success")
        data = result["data"]
        for field in ["address", "price", "beds", "baths", "sqft", "year_built", "zestimate", "photos"]:
            self.assertIn(field, data)

    def test_photos_is_list(self):
        result = self.get_listing("728 Oak Grove Rd, Plainwell, MI")
        self.assertIsInstance(result["data"]["photos"], list)

    def test_price_history_is_list(self):
        result = self.get_listing("123 Test St, MI")
        self.assertIsInstance(result["data"]["price_history"], list)

    def test_data_source_key_present(self):
        result = self.get_listing("Any Address, MI")
        self.assertIn("data_source", result["data"])


# ── disclosure_analyzer tests ──────────────────────────────────────────────────
class TestDisclosureAnalyzer(unittest.TestCase):

    def setUp(self):
        from disclosure_analyzer import analyze_disclosure, _build_mock_analysis
        self.analyze = analyze_disclosure
        self.build_mock = _build_mock_analysis

    def test_empty_path_returns_failure(self):
        result = self.analyze("")
        self.assertEqual(result["status"], "failure")

    def test_nonexistent_file_returns_failure(self):
        result = self.analyze("/nonexistent/path/file.pdf")
        self.assertEqual(result["status"], "failure")

    def test_mock_data_structure(self):
        mock = self.build_mock()
        self.assertIn("red_flags", mock)
        self.assertIn("summary", mock)
        for flag in mock["red_flags"]:
            for field in ["category", "severity", "quote", "note"]:
                self.assertIn(field, flag)
            self.assertIn(flag["severity"], ["critical", "monitor", "minor"])

    def test_mock_data_has_at_least_one_flag(self):
        mock = self.build_mock()
        self.assertGreater(len(mock["red_flags"]), 0)


# ── calendar_manager tests ─────────────────────────────────────────────────────
class TestCalendarManager(unittest.TestCase):

    def setUp(self):
        from calendar_manager import export_ics, create_showing_events
        self.export_ics = export_ics
        self.create_showing_events = create_showing_events

    def test_export_ics_valid_output(self):
        route = [
            {"order": 1, "address": "1842 Lincoln Rd, Allegan, MI", "showing_start": "1:00 PM", "showing_end": "1:30 PM", "travel_to_next_minutes": 20},
            {"order": 2, "address": "728 Oak Grove Rd, Plainwell, MI", "showing_start": "1:50 PM", "showing_end": "2:20 PM", "travel_to_next_minutes": None},
        ]
        result = self.export_ics(route, "Sarah Johnson", "2026-03-21")
        self.assertEqual(result["status"], "success")
        self.assertIn("BEGIN:VCALENDAR", result["data"]["ics_content"])
        self.assertIn("BEGIN:VEVENT", result["data"]["ics_content"])

    def test_create_showing_events_returns_failure_when_unconfigured(self):
        result = self.create_showing_events([], "Client", "2026-03-21")
        self.assertEqual(result["status"], "failure")


# ── client_page_builder tests ──────────────────────────────────────────────────
class TestClientPageBuilder(unittest.TestCase):

    def setUp(self):
        from client_page_builder import build_client_page
        self.build = build_client_page
        self.mock_session = {
            "session_date": "2026-03-21",
            "client": {"name": "Sarah Johnson", "email": "sarah@example.com"},
            "properties": [
                {
                    "address": "1842 Lincoln Rd, Allegan, MI 49010",
                    "order": 1,
                    "status": "confirmed",
                    "showing_start": "1:00 PM",
                    "showing_end": "1:30 PM",
                    "red_flags": None
                }
            ]
        }

    def test_builds_html_file(self):
        result = self.build(self.mock_session, {})
        self.assertEqual(result["status"], "success")
        output_path = Path(result["data"]["output_path"])
        self.assertTrue(output_path.exists())
        # Cleanup
        import shutil
        shutil.rmtree(str(output_path.parent), ignore_errors=True)

    def test_html_contains_client_name(self):
        result = self.build(self.mock_session, {})
        content = Path(result["data"]["output_path"]).read_text()
        self.assertIn("Sarah Johnson", content)
        # Cleanup
        import shutil
        shutil.rmtree(str(Path(result["data"]["output_path"]).parent), ignore_errors=True)

    def test_html_contains_agent_name(self):
        result = self.build(self.mock_session, {})
        content = Path(result["data"]["output_path"]).read_text()
        self.assertIn("Jason O'Brien", content)
        # Cleanup
        import shutil
        shutil.rmtree(str(Path(result["data"]["output_path"]).parent), ignore_errors=True)


# ── gmail_sender tests ─────────────────────────────────────────────────────────
class TestGmailSender(unittest.TestCase):

    def setUp(self):
        from gmail_sender import send_client_email, generate_email_draft
        self.send = send_client_email
        self.draft = generate_email_draft

    def test_send_returns_failure_when_unconfigured(self):
        result = self.send("test@example.com", "Test", "http://localhost", "March 21")
        self.assertEqual(result["status"], "failure")
        self.assertIn("draft_preview", result.get("data", {}))

    def test_draft_always_works(self):
        result = self.draft("Sarah Johnson", "http://localhost:5000/output/test", "March 21, 2026")
        self.assertEqual(result["status"], "success")
        self.assertIn("html_body", result["data"])
        self.assertIn("plain_text", result["data"])
        self.assertIn("Sarah Johnson", result["data"]["plain_text"])


# ── bridge_api_fetcher tests ───────────────────────────────────────────────────
class TestBridgeApiFetcher(unittest.TestCase):

    def setUp(self):
        from bridge_api_fetcher import get_listing_data
        self.get_listing = get_listing_data

    def test_returns_failure_when_unconfigured(self):
        result = self.get_listing("123 Test St, MI")
        self.assertEqual(result["status"], "failure")
        self.assertIn("BridgeAPI@bridgeinteractive.com", result["error"])


# ── showingtime_api tests ──────────────────────────────────────────────────────
class TestShowingTimeApi(unittest.TestCase):

    def setUp(self):
        from showingtime_api import submit_showing_request
        self.submit = submit_showing_request

    def test_returns_failure_with_manual_checklist(self):
        result = self.submit("123 Main St, MI", requested_date="2026-03-21")
        self.assertEqual(result["status"], "failure")
        self.assertIn("manual_checklist", result.get("data", {}))
        self.assertIn("123 Main St", result["data"]["manual_checklist"])


# ── Test runner ────────────────────────────────────────────────────────────────
def run_all_tests(verbose=True):
    """Run all test suites and return pass/fail count."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    test_classes = [
        TestSessionLogger,
        TestRouteOptimizer,
        TestCrmClientLookup,
        TestApinationWebhook,
        TestZillowScraper,
        TestDisclosureAnalyzer,
        TestCalendarManager,
        TestClientPageBuilder,
        TestGmailSender,
        TestBridgeApiFetcher,
        TestShowingTimeApi,
    ]

    for cls in test_classes:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2 if verbose else 1)
    result = runner.run(suite)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ShowingDay Tool Tests")
    parser.add_argument("--tool", type=str, help="Run tests for specific tool only")
    parser.add_argument("--quiet", action="store_true", help="Less verbose output")
    args = parser.parse_args()

    if args.tool:
        # Run single tool's --test mode
        tool_map = {
            "session_logger": "tools/session_logger.py",
            "route_optimizer": "tools/route_optimizer.py",
            "crm_client_lookup": "tools/crm_client_lookup.py",
            "calendar_manager": "tools/calendar_manager.py",
            "apination_webhook": "tools/apination_webhook.py",
            "zillow_scraper": "tools/zillow_scraper.py",
            "disclosure_analyzer": "tools/disclosure_analyzer.py",
            "client_page_builder": "tools/client_page_builder.py",
            "gmail_sender": "tools/gmail_sender.py",
            "bridge_api_fetcher": "tools/bridge_api_fetcher.py",
            "showingtime_api": "tools/showingtime_api.py",
        }
        if args.tool in tool_map:
            os.system(f"python {BASE_DIR / tool_map[args.tool]} --test")
        else:
            print(f"Unknown tool: {args.tool}")
            print(f"Available: {', '.join(tool_map.keys())}")
    else:
        result = run_all_tests(verbose=not args.quiet)
        sys.exit(0 if result.wasSuccessful() else 1)
