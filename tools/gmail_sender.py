"""
gmail_sender.py — ShowingDay Gmail Email Sender

Sends the client-facing showing day page link and calendar invites via Gmail API.
OAuth credentials loaded from GMAIL_CREDENTIALS_JSON in .env.

CLI: python tools/gmail_sender.py --test

TODO: Implement Gmail OAuth (similar to calendar_manager.py OAuth flow).

Returns:
    {
        "status": "success",
        "data": {
            "message_id": str,
            "to": str,
            "subject": str
        },
        "error": null
    }
"""

import os
import json
import argparse
import base64
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

BASE_DIR = Path(__file__).resolve().parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

GMAIL_CREDENTIALS_JSON = os.getenv("GMAIL_CREDENTIALS_JSON", "")
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
TOKEN_FILE = BASE_DIR / "token_gmail.json"

# Agent contact info — sourced from CLAUDE.md
AGENT_NAME = "Jason O'Brien"
AGENT_TITLE = "PREMIERE Group at Real Broker LLC"
AGENT_SIGNATURE = f"""
<br><br>
--<br>
<strong>{AGENT_NAME}</strong><br>
{AGENT_TITLE}<br>
Allegan County, West Michigan
"""


# ── OAuth flow ─────────────────────────────────────────────────────────────────

def get_credentials():
    """
    Get (or refresh) Gmail OAuth2 credentials.

    TODO: Implement Gmail OAuth (same pattern as calendar_manager.py):
    ─────────────────────────────────────────────────────────────────
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request

    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), GMAIL_SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            creds_data = json.loads(GMAIL_CREDENTIALS_JSON)
            flow = InstalledAppFlow.from_client_config(creds_data, GMAIL_SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return creds
    ─────────────────────────────────────────────────────────────────
    """
    raise NotImplementedError(
        "Gmail OAuth not yet configured. "
        "Set GMAIL_CREDENTIALS_JSON in .env and implement get_credentials(). "
        "See tools/gmail_sender.py for implementation guide."
    )


def _get_gmail_service():
    """Build and return the Gmail API service client."""
    # from googleapiclient.discovery import build
    # creds = get_credentials()
    # return build("gmail", "v1", credentials=creds)
    raise NotImplementedError("Gmail service requires get_credentials() implementation")


def _build_email_html(client_name: str, page_url: str, session_date: str) -> str:
    """Build the HTML body for the client email."""
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family: Arial, sans-serif; color: #2d2416; max-width: 600px; margin: 0 auto; padding: 20px;">
    <div style="background: linear-gradient(135deg, #2c1810, #5a3e00); padding: 32px; border-radius: 12px; text-align: center; margin-bottom: 24px;">
        <h1 style="color: white; font-size: 24px; margin: 0 0 8px;">Your Showing Day is Ready!</h1>
        <p style="color: #c9a84c; margin: 0; font-size: 16px;">{session_date}</p>
    </div>

    <p>Hi {client_name},</p>

    <p>Your personalized showing day itinerary is ready. I've put together everything you need for our tour — property details, schedules, and directions all in one place.</p>

    <div style="text-align: center; margin: 32px 0;">
        <a href="{page_url}"
           style="background: #c9a84c; color: white; padding: 16px 40px; border-radius: 8px; text-decoration: none; font-size: 18px; font-weight: 600; display: inline-block;">
            View Your Showing Day Page
        </a>
    </div>

    <p>Feel free to reach out with any questions before our session. I'm looking forward to showing you these homes!</p>

    {AGENT_SIGNATURE}
</body>
</html>"""


# ── Main send function ─────────────────────────────────────────────────────────

def send_client_email(
    to_email: str,
    client_name: str,
    page_url: str,
    session_date: str
) -> dict:
    """
    Send the showing day page link to the client via Gmail.

    Args:
        to_email: Client's email address (from CRM lookup).
        client_name: Client's full name.
        page_url: URL or local path to the generated client page.
        session_date: Session date string for the email subject.

    Returns standard ShowingDay tool response.

    TODO: Remove stub and uncomment implementation below when OAuth is set up.
    ─────────────────────────────────────────────────────────────────────────────
    service = _get_gmail_service()

    message = MIMEMultipart("alternative")
    message["Subject"] = f"Your Showing Day Itinerary — {session_date}"
    message["From"] = "me"
    message["To"] = to_email

    html_body = _build_email_html(client_name, page_url, session_date)
    message.attach(MIMEText(html_body, "html"))

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()

    return {
        "status": "success",
        "data": {
            "message_id": sent["id"],
            "to": to_email,
            "subject": f"Your Showing Day Itinerary — {session_date}"
        },
        "error": None
    }
    ─────────────────────────────────────────────────────────────────────────────
    """
    # TODO: Remove this stub when Gmail OAuth is configured
    return {
        "status": "failure",
        "data": {
            "to": to_email,
            "subject": f"Your Showing Day Itinerary — {session_date}",
            "draft_preview": _build_email_html(client_name, page_url, session_date)
        },
        "error": "Gmail not yet configured. Set GMAIL_CREDENTIALS_JSON in .env. Email draft is available in data.draft_preview."
    }


def generate_email_draft(client_name: str, page_url: str, session_date: str) -> dict:
    """
    Generate the email draft for manual copy-paste when Gmail API is unavailable.
    Always functional — no credentials required.
    """
    html_body = _build_email_html(client_name, page_url, session_date)
    plain_text = (
        f"Hi {client_name},\n\n"
        f"Your personalized showing day itinerary for {session_date} is ready.\n\n"
        f"View it here: {page_url}\n\n"
        f"Feel free to reach out with any questions. Looking forward to our tour!\n\n"
        f"-- {AGENT_NAME}\n{AGENT_TITLE}"
    )

    return {
        "status": "success",
        "data": {
            "subject": f"Your Showing Day Itinerary — {session_date}",
            "to": "",
            "html_body": html_body,
            "plain_text": plain_text
        },
        "error": None
    }


# ── CLI ────────────────────────────────────────────────────────────────────────

def _run_tests():
    print("Testing gmail_sender (stub mode)...")

    # Test 1: send returns failure with helpful message
    result = send_client_email(
        "sarah@example.com", "Sarah Johnson",
        "http://localhost:5000/output/client_2026-03-21_sarah_johnson/index.html",
        "March 21, 2026"
    )
    assert result["status"] == "failure", "Test 1 failed: should return failure until OAuth configured"
    assert "draft_preview" in result.get("data", {}), "Test 1 failed: should include draft_preview"
    print("  PASS — send_client_email() returns failure with draft_preview when unconfigured")

    # Test 2: generate_email_draft always works
    result = generate_email_draft(
        "Sarah Johnson",
        "http://localhost:5000/output/client_2026-03-21_sarah",
        "March 21, 2026"
    )
    assert result["status"] == "success", f"Test 2 failed: {result}"
    assert "html_body" in result["data"], "Test 2 failed: missing html_body"
    assert "plain_text" in result["data"], "Test 2 failed: missing plain_text"
    assert "Sarah Johnson" in result["data"]["plain_text"], "Test 2 failed: client name not in email"
    print("  PASS — generate_email_draft() always generates email content")

    print("\nAll gmail_sender tests passed.")
    print("(Note: Gmail OAuth is stubbed — implement get_credentials() to enable sending)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ShowingDay Gmail Sender")
    parser.add_argument("--test", action="store_true", help="Run self-tests")
    parser.add_argument("--draft", action="store_true", help="Generate email draft")
    args = parser.parse_args()

    if args.test:
        _run_tests()
    elif args.draft:
        result = generate_email_draft("Your Client", "http://localhost:5000/output/example", "Today")
        print(result["data"]["plain_text"])
    else:
        parser.print_help()
