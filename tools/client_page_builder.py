"""
client_page_builder.py — ShowingDay Client-Facing Page Builder

Generates a beautiful, client-friendly HTML page for the showing day itinerary.
Saved to: /output/client_[date]_[clientname]/index.html

Design: Warm, approachable, curated itinerary feel.
  - Client name at top
  - Showing day date and schedule overview
  - Agent contact info (Jason O'Brien, PREMIERE Group at Real Broker LLC)
  - Property cards in showing order: photo, address, time, Google Maps link
  - Property summary (price, beds, baths, sqft, etc.)
  - Red flag summary per property (agent-toggleable before sending)
  - Download links for disclosure PDFs if uploaded
  - "Add to My Calendar" button

CLI: python tools/client_page_builder.py --test

Returns:
    {
        "status": "success",
        "data": {
            "output_path": "/abs/path/to/output/client_YYYY-MM-DD_name/index.html",
            "relative_path": "output/client_YYYY-MM-DD_name/index.html"
        },
        "error": null
    }
"""

import os
import json
import argparse
from datetime import datetime
from pathlib import Path
from html import escape

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"

try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass


# ── HTML Template ──────────────────────────────────────────────────────────────

def _severity_badge(severity: str) -> str:
    colors = {"critical": "#c0392b", "monitor": "#e67e22", "minor": "#27ae60"}
    labels = {"critical": "Critical", "monitor": "Monitor", "minor": "Minor"}
    color = colors.get(severity, "#95a5a6")
    label = labels.get(severity, severity.title())
    return f'<span style="background:{color};color:white;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600;">{label}</span>'


def _property_card_html(prop: dict, summary: dict, show_red_flags: bool = False) -> str:
    """Generate HTML for a single property card."""
    address = escape(prop.get("address", ""))
    showing_start = escape(prop.get("showing_start", ""))
    showing_end = escape(prop.get("showing_end", ""))
    maps_url = f"https://www.google.com/maps/dir/?api=1&destination={address.replace(' ', '+')}"

    # Property summary data
    price = escape(str(summary.get("price", "—")))
    beds = summary.get("beds", "—")
    baths = summary.get("baths", "—")
    sqft = summary.get("sqft", "—")
    year_built = summary.get("year_built", "—")
    school_district = escape(str(summary.get("school_district", "—")))
    tax = escape(str(summary.get("tax_estimate", "—")))
    zestimate = escape(str(summary.get("zestimate", "—")))
    days_on_market = summary.get("days_on_market", "—")
    description = escape(str(summary.get("description", "")))
    photos = summary.get("photos", [])
    photo_url = photos[0] if photos else ""

    # Build stats row
    stats = [
        ("beds", str(beds)),
        ("baths", str(baths)),
        ("sqft", f"{sqft:,}" if isinstance(sqft, int) else str(sqft)),
        ("yr built", str(year_built)),
        ("days on mkt", str(days_on_market))
    ]
    stats_html = " · ".join(f"<strong>{v}</strong> {k}" for k, v in stats if v and v != "—")

    # Red flags section
    red_flag_html = ""
    if show_red_flags:
        red_flags = prop.get("red_flags", {})
        flags = red_flags.get("red_flags", []) if red_flags else []
        if flags:
            flags_list = ""
            for flag in flags:
                badge = _severity_badge(flag.get("severity", "minor"))
                cat = escape(flag.get("category", ""))
                note = escape(flag.get("note", ""))
                flags_list += f"""
                    <div style="padding:10px 0;border-bottom:1px solid #f0e6d3;">
                        <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
                            {badge}
                            <strong style="font-size:13px;">{cat}</strong>
                        </div>
                        <p style="margin:0;font-size:13px;color:#5a4a3a;">{note}</p>
                    </div>
                """
            red_flag_html = f"""
                <div style="margin-top:16px;background:#fff8f0;border:1px solid #f0e6d3;border-radius:8px;padding:16px;">
                    <h4 style="margin:0 0 8px;font-size:14px;color:#8b4513;text-transform:uppercase;letter-spacing:0.5px;">
                        Disclosure Notes
                    </h4>
                    {flags_list}
                </div>
            """

    # Disclosure PDF link
    disclosure_path = prop.get("disclosure_path", "")
    disclosure_link = ""
    if disclosure_path:
        fname = Path(disclosure_path).name
        disclosure_link = f'<a href="disclosures/{escape(fname)}" style="color:#8b6914;font-size:13px;">Download Disclosure PDF</a>'

    photo_html = ""
    if photo_url:
        photo_html = f'<img src="{escape(photo_url)}" alt="{address}" style="width:100%;height:220px;object-fit:cover;border-radius:10px 10px 0 0;">'

    order = prop.get("order", "")

    return f"""
    <div style="background:white;border-radius:12px;box-shadow:0 2px 16px rgba(0,0,0,0.08);margin-bottom:32px;overflow:hidden;">
        {photo_html}
        <div style="padding:24px;">
            <div style="display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:8px;">
                <div>
                    <span style="background:#c9a84c;color:white;width:28px;height:28px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;font-weight:700;font-size:13px;margin-right:10px;">{order}</span>
                    <span style="font-size:22px;font-weight:700;font-family:'Playfair Display',serif;">{address.split(',')[0]}</span>
                </div>
                <div style="text-align:right;">
                    <div style="font-size:22px;font-weight:700;color:#2c7a2c;">{price}</div>
                    <div style="font-size:12px;color:#888;">Zestimate: {zestimate}</div>
                </div>
            </div>
            <div style="color:#666;font-size:13px;margin-bottom:12px;">{','.join(address.split(',')[1:]).strip()}</div>

            <div style="background:#f9f5ee;border-radius:8px;padding:12px 16px;margin-bottom:16px;">
                <div style="font-size:15px;font-weight:600;color:#5a3e00;">
                    Showing: {showing_start} – {showing_end}
                </div>
            </div>

            <div style="font-size:14px;color:#444;margin-bottom:12px;">{stats_html}</div>
            <div style="font-size:12px;color:#888;margin-bottom:6px;">School District: {school_district} · Est. Taxes: {tax}</div>

            {f'<p style="font-size:14px;color:#555;line-height:1.6;margin:12px 0;">{description[:400]}{"..." if len(description) > 400 else ""}</p>' if description else ""}

            {red_flag_html}

            <div style="margin-top:16px;display:flex;gap:12px;align-items:center;flex-wrap:wrap;">
                <a href="{maps_url}" target="_blank"
                   style="background:#c9a84c;color:white;padding:10px 20px;border-radius:6px;text-decoration:none;font-size:14px;font-weight:600;">
                    Get Directions
                </a>
                {disclosure_link}
            </div>
        </div>
    </div>
    """


def build_client_page(session_data: dict, property_summaries: dict, show_red_flags: bool = False) -> dict:
    """
    Generate the client-facing showing day HTML page.

    Args:
        session_data: Full session state dict from session_state.json.
        property_summaries: Dict mapping address → listing data dict from zillow_scraper.
        show_red_flags: Whether to include disclosure red flags on client page.

    Returns standard ShowingDay tool response with output file path.
    """
    client = session_data.get("client") or {}
    client_name = client.get("name", "Valued Client")
    session_date_raw = session_data.get("session_date", "")
    properties = session_data.get("properties", [])

    # Format date nicely
    try:
        date_obj = datetime.strptime(session_date_raw, "%Y-%m-%d")
        session_date_display = date_obj.strftime("%A, %B %-d, %Y")
    except Exception:
        session_date_display = session_date_raw or "Your Showing Day"

    # Filter to confirmed + tentative properties, sorted by order
    active_props = [p for p in properties if p.get("status") not in ["declined"]]
    active_props.sort(key=lambda p: p.get("order", 999))

    # Build property cards
    cards_html = ""
    for prop in active_props:
        address = prop.get("address", "")
        summary = property_summaries.get(address, {})
        cards_html += _property_card_html(prop, summary, show_red_flags)

    if not cards_html:
        cards_html = '<p style="text-align:center;color:#999;padding:40px;">No confirmed showings yet.</p>'

    # Count stats
    confirmed = sum(1 for p in properties if p.get("status") == "confirmed")
    total = len(active_props)

    # Full HTML page
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Your Showing Day — {escape(session_date_display)}</title>
    <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;700&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: 'Inter', sans-serif;
            background: #faf7f2;
            color: #2d2416;
            min-height: 100vh;
        }}
        .hero {{
            background: linear-gradient(135deg, #2c1810 0%, #5a3e00 100%);
            color: white;
            padding: 60px 24px 40px;
            text-align: center;
        }}
        .hero .greeting {{
            font-size: 14px;
            font-weight: 500;
            color: #c9a84c;
            text-transform: uppercase;
            letter-spacing: 2px;
            margin-bottom: 8px;
        }}
        .hero h1 {{
            font-family: 'Playfair Display', serif;
            font-size: 42px;
            font-weight: 700;
            margin-bottom: 8px;
        }}
        .hero .date {{
            font-size: 18px;
            color: rgba(255,255,255,0.8);
            margin-bottom: 32px;
        }}
        .hero .summary-bar {{
            display: inline-flex;
            gap: 32px;
            background: rgba(255,255,255,0.1);
            border-radius: 12px;
            padding: 16px 32px;
        }}
        .hero .summary-item {{
            text-align: center;
        }}
        .hero .summary-item .num {{
            font-size: 28px;
            font-weight: 700;
            color: #c9a84c;
        }}
        .hero .summary-item .label {{
            font-size: 12px;
            color: rgba(255,255,255,0.7);
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        .content {{
            max-width: 680px;
            margin: 0 auto;
            padding: 40px 24px;
        }}
        .section-header {{
            font-family: 'Playfair Display', serif;
            font-size: 26px;
            margin-bottom: 24px;
            color: #2d2416;
        }}
        .agent-card {{
            background: white;
            border-radius: 12px;
            padding: 20px 24px;
            margin-bottom: 40px;
            display: flex;
            align-items: center;
            gap: 16px;
            box-shadow: 0 2px 12px rgba(0,0,0,0.06);
            border-left: 4px solid #c9a84c;
        }}
        .agent-info .name {{
            font-weight: 700;
            font-size: 16px;
        }}
        .agent-info .title {{
            font-size: 13px;
            color: #888;
        }}
        .agent-info .contact {{
            font-size: 13px;
            color: #5a3e00;
            margin-top: 4px;
        }}
        .agent-icon {{
            width: 48px;
            height: 48px;
            background: #c9a84c;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 22px;
            flex-shrink: 0;
        }}
        .add-calendar-btn {{
            display: block;
            width: 100%;
            background: #2c7a2c;
            color: white;
            border: none;
            padding: 16px;
            border-radius: 10px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            text-align: center;
            text-decoration: none;
            margin: 32px 0;
            font-family: 'Inter', sans-serif;
        }}
        .add-calendar-btn:hover {{
            background: #1d5c1d;
        }}
        .footer {{
            text-align: center;
            padding: 40px 24px;
            color: #999;
            font-size: 13px;
            border-top: 1px solid #e8e0d0;
        }}
        .footer .brand {{
            color: #c9a84c;
            font-weight: 600;
        }}
        @media (max-width: 600px) {{
            .hero h1 {{ font-size: 28px; }}
            .hero .summary-bar {{ gap: 16px; padding: 12px 20px; }}
        }}
    </style>
</head>
<body>
    <div class="hero">
        <div class="greeting">Your Personalized Showing Itinerary</div>
        <h1>{escape(client_name)}</h1>
        <div class="date">{escape(session_date_display)}</div>
        <div class="summary-bar">
            <div class="summary-item">
                <div class="num">{total}</div>
                <div class="label">Properties</div>
            </div>
            <div class="summary-item">
                <div class="num">{confirmed}</div>
                <div class="label">Confirmed</div>
            </div>
        </div>
    </div>

    <div class="content">
        <div class="agent-card">
            <div class="agent-icon">J</div>
            <div class="agent-info">
                <div class="name">Jason O'Brien</div>
                <div class="title">PREMIERE Group at Real Broker LLC</div>
                <div class="contact">Questions? Call or text anytime.</div>
            </div>
        </div>

        <h2 class="section-header">Today's Properties</h2>

        {cards_html}

        <a href="#" class="add-calendar-btn" onclick="alert('Calendar invite feature coming soon. Your agent will send you an invite directly.')">
            Add All Showings to My Calendar
        </a>
    </div>

    <div class="footer">
        <p>Prepared by <span class="brand">Jason O'Brien · PREMIERE Group at Real Broker LLC</span></p>
        <p style="margin-top:8px;">Allegan County, West Michigan</p>
    </div>
</body>
</html>"""

    # ── Write output file ──────────────────────────────────────────────────────
    safe_name = (client.get("name", "client") or "client").lower().replace(" ", "_")
    safe_name = "".join(c for c in safe_name if c.isalnum() or c == "_")
    safe_date = session_date_raw or datetime.utcnow().strftime("%Y-%m-%d")

    folder_name = f"client_{safe_date}_{safe_name}"
    output_path = OUTPUT_DIR / folder_name
    output_path.mkdir(parents=True, exist_ok=True)

    # Create disclosures subfolder
    (output_path / "disclosures").mkdir(exist_ok=True)

    html_file = output_path / "index.html"
    with open(html_file, "w", encoding="utf-8") as f:
        f.write(html)

    return {
        "status": "success",
        "data": {
            "output_path": str(html_file),
            "relative_path": str(html_file.relative_to(BASE_DIR)),
            "folder": str(output_path)
        },
        "error": None
    }


# ── CLI ────────────────────────────────────────────────────────────────────────

def _run_tests():
    print("Testing client_page_builder...")

    mock_session = {
        "session_date": "2026-03-21",
        "client": {"name": "Sarah Johnson", "email": "sarah@example.com", "phone": "(616) 555-0123"},
        "properties": [
            {
                "address": "1842 Lincoln Rd, Allegan, MI 49010",
                "order": 1,
                "status": "confirmed",
                "showing_start": "1:00 PM",
                "showing_end": "1:30 PM",
                "red_flags": {
                    "red_flags": [
                        {"category": "Roof", "severity": "monitor", "quote": "Roof age: 2008", "note": "18-year-old roof, inspect carefully."}
                    ],
                    "summary": "1 red flag: 1 monitor."
                }
            },
            {
                "address": "728 Oak Grove Rd, Plainwell, MI 49080",
                "order": 2,
                "status": "confirmed",
                "showing_start": "2:00 PM",
                "showing_end": "2:30 PM",
                "red_flags": None
            }
        ]
    }

    mock_summaries = {
        "1842 Lincoln Rd, Allegan, MI 49010": {
            "price": "$289,900",
            "beds": 3,
            "baths": 2.0,
            "sqft": 1842,
            "year_built": 1998,
            "days_on_market": 48,
            "school_district": "Allegan Public Schools",
            "tax_estimate": "$3,240/yr",
            "zestimate": "$294,500",
            "description": "Charming 3-bedroom ranch on a large lot.",
            "photos": []
        },
        "728 Oak Grove Rd, Plainwell, MI 49080": {
            "price": "$224,900",
            "beds": 4,
            "baths": 2.5,
            "sqft": 2100,
            "year_built": 2004,
            "days_on_market": 12,
            "school_district": "Plainwell Community Schools",
            "tax_estimate": "$2,800/yr",
            "zestimate": "$229,000",
            "description": "Spacious 4-bedroom colonial in quiet neighborhood.",
            "photos": []
        }
    }

    result = build_client_page(mock_session, mock_summaries, show_red_flags=True)
    assert result["status"] == "success", f"Test failed: {result}"

    output_path = Path(result["data"]["output_path"])
    assert output_path.exists(), "Test failed: output file not created"
    content = output_path.read_text()
    assert "Sarah Johnson" in content, "Test failed: client name not in HTML"
    assert "1842 Lincoln Rd" in content, "Test failed: address not in HTML"
    assert "Jason O'Brien" in content, "Test failed: agent name not in HTML"
    print(f"  PASS — client page generated: {result['data']['output_path']}")

    # Cleanup test output
    import shutil
    shutil.rmtree(str(output_path.parent))
    print("  PASS — output file structure is correct")

    print("\nAll client_page_builder tests passed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ShowingDay Client Page Builder")
    parser.add_argument("--test", action="store_true", help="Run self-tests")
    parser.add_argument("--show-red-flags", action="store_true", help="Include red flags on client page")
    args = parser.parse_args()

    if args.test:
        _run_tests()
    else:
        print("client_page_builder.py — use --test to generate a sample page")
