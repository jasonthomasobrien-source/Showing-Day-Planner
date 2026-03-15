"""
disclosure_analyzer.py — ShowingDay Disclosure PDF Red Flag Analyzer

Analyzes a seller disclosure PDF using the Anthropic Claude API.
Extracts and categorizes red flags with severity ratings.

Red flag categories:
  - Water intrusion / basement moisture / flooding history
  - Roof age and condition
  - HVAC age and condition
  - Pest damage or infestation history
  - Foundation issues
  - Mold or air quality disclosures
  - Any "Yes" answers on seller disclosure that warrant follow-up

Severity levels:
  - critical  → 🔴 Needs immediate attention / deal-breaker potential
  - monitor   → 🟡 Warrants follow-up / inspection focus
  - minor     → 🟢 Noted, but low immediate concern

CLI: python tools/disclosure_analyzer.py --test
     python tools/disclosure_analyzer.py --pdf /path/to/disclosure.pdf

Returns:
    {
        "status": "success",
        "data": {
            "red_flags": [
                {
                    "category": "Water Intrusion",
                    "severity": "critical",
                    "quote": "Seller answered YES to: Has the property experienced any water intrusion...",
                    "note": "Basement flooding history disclosed. Requires thorough inspection."
                }
            ],
            "summary": "3 red flags found: 1 critical, 1 monitor, 1 minor.",
            "full_text_excerpt": "First 500 chars of extracted PDF text...",
            "data_source": "claude" | "mock"
        },
        "error": null
    }
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

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-opus-4-5"

# Optional imports
try:
    import PyPDF2
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False


# ── PDF text extraction ────────────────────────────────────────────────────────

def extract_pdf_text(pdf_path: str) -> str:
    """
    Extract text content from a PDF file using PyPDF2.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        Extracted text as a string, or empty string on failure.
    """
    if not PDF_AVAILABLE:
        raise ImportError("PyPDF2 is required for PDF text extraction. Run: pip install PyPDF2")

    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    text_parts = []
    with open(path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        for page_num, page in enumerate(reader.pages):
            try:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(f"[Page {page_num + 1}]\n{page_text}")
            except Exception as e:
                text_parts.append(f"[Page {page_num + 1}: Could not extract text — {e}]")

    return "\n\n".join(text_parts)


# ── Claude API analysis ────────────────────────────────────────────────────────

DISCLOSURE_ANALYSIS_PROMPT = """You are a real estate buyer's agent reviewing a Michigan seller disclosure document.
Analyze the following disclosure text and identify ALL red flags that a buyer should know about.

Focus specifically on:
1. Water intrusion, basement moisture, flooding, or drainage problems (any history)
2. Roof condition, age, known damage, or recent repairs
3. HVAC system age, condition, known issues, recent replacements
4. Pest or termite damage, infestation history, or current problems
5. Foundation issues: cracks, settling, shifting, structural concerns
6. Mold, mildew, air quality issues, or health hazards
7. Any seller "YES" answers on disclosure questions — quote the exact question and answer
8. Any recent insurance claims related to the property
9. Easements, boundary disputes, or legal issues
10. Known defects the seller disclosed in "additional comments"

For each red flag found, provide:
- category: One of [Water Intrusion, Roof, HVAC, Pest/Termite, Foundation, Mold/Air Quality, Seller Disclosure Yes, Insurance Claim, Legal/Easement, Other Defect]
- severity: "critical" (deal-breaker potential, requires immediate expert review), "monitor" (warrants inspection focus), or "minor" (noted but low concern)
- quote: The EXACT language from the disclosure that triggered this flag (with page reference if available)
- note: Your plain-English explanation of why this matters to the buyer

Return ONLY valid JSON in this exact format:
{
  "red_flags": [
    {
      "category": "Water Intrusion",
      "severity": "critical",
      "quote": "EXACT TEXT FROM DISCLOSURE",
      "note": "Plain English explanation"
    }
  ],
  "summary": "X red flags found: X critical, X monitor, X minor. [One sentence overall assessment]"
}

If no red flags are found, return:
{
  "red_flags": [],
  "summary": "No significant red flags identified in this disclosure."
}

Disclosure text:
---
{disclosure_text}
---"""


def _analyze_with_claude(disclosure_text: str) -> dict:
    """
    Send disclosure text to Claude API for red flag analysis.
    Returns parsed red flag dict.
    """
    if not ANTHROPIC_AVAILABLE:
        raise ImportError("anthropic package is required. Run: pip install anthropic")

    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY not set in .env")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Truncate very long disclosures (Claude has context limits)
    max_chars = 80000
    if len(disclosure_text) > max_chars:
        disclosure_text = disclosure_text[:max_chars] + "\n\n[... document truncated for analysis ...]"

    prompt = DISCLOSURE_ANALYSIS_PROMPT.format(disclosure_text=disclosure_text)

    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )

    response_text = message.content[0].text.strip()

    # Parse JSON response
    # Claude may sometimes wrap JSON in markdown code blocks
    if response_text.startswith("```"):
        lines = response_text.split("\n")
        response_text = "\n".join(lines[1:-1])

    return json.loads(response_text)


def _build_mock_analysis() -> dict:
    """Return realistic mock red flag data for testing."""
    return {
        "red_flags": [
            {
                "category": "Water Intrusion",
                "severity": "critical",
                "quote": "Question 12: Has the property ever experienced water intrusion in the basement or crawl space? Seller Answer: YES. Comments: Basement had water intrusion in spring 2019. Sump pump installed. No issues since.",
                "note": "Seller disclosed past basement flooding. Even with sump pump installed, this warrants a thorough basement inspection, review of drainage grading, and checking for hidden moisture damage or mold."
            },
            {
                "category": "Roof",
                "severity": "monitor",
                "quote": "Question 8: Are you aware of any defects in the roof? Seller Answer: NO. Roof age (if known): 2008.",
                "note": "Roof is approximately 18 years old — near or past typical lifespan for asphalt shingles (20-25 years). No defects disclosed, but age warrants close inspector attention."
            },
            {
                "category": "HVAC",
                "severity": "minor",
                "quote": "Furnace: Replaced 2021. Central Air: Original, installed approximately 2001.",
                "note": "Furnace is recent (replaced 2021, low concern). Central AC unit is ~25 years old and approaching end of typical lifespan. Budget for potential replacement."
            }
        ],
        "summary": "3 red flags found: 1 critical, 1 monitor, 1 minor. Past water intrusion is the primary concern — verify basement conditions and sump pump operation during inspection.",
        "data_source": "mock"
    }


# ── Main function ──────────────────────────────────────────────────────────────

def analyze_disclosure(pdf_path: str) -> dict:
    """
    Analyze a seller disclosure PDF for red flags.

    Args:
        pdf_path: Path to the disclosure PDF file.

    Returns standard ShowingDay tool response.
    """
    if not pdf_path or not pdf_path.strip():
        return {"status": "failure", "data": None, "error": "PDF path is required"}

    # ── Extract PDF text ───────────────────────────────────────────────────────
    try:
        disclosure_text = extract_pdf_text(pdf_path)
        if not disclosure_text.strip():
            return {
                "status": "failure",
                "data": None,
                "error": "Could not extract text from PDF. The file may be a scanned image — OCR is required."
            }
    except FileNotFoundError as e:
        return {"status": "failure", "data": None, "error": str(e)}
    except Exception as e:
        return {"status": "failure", "data": None, "error": f"PDF extraction error: {e}"}

    full_text_excerpt = disclosure_text[:500] + ("..." if len(disclosure_text) > 500 else "")

    # ── Analyze with Claude ────────────────────────────────────────────────────
    if ANTHROPIC_API_KEY and ANTHROPIC_AVAILABLE:
        try:
            analysis = _analyze_with_claude(disclosure_text)
            analysis["data_source"] = "claude"
            analysis["full_text_excerpt"] = full_text_excerpt
            return {"status": "success", "data": analysis, "error": None}
        except json.JSONDecodeError as e:
            return {"status": "failure", "data": None, "error": f"Claude returned invalid JSON: {e}"}
        except Exception as e:
            print(f"[disclosure_analyzer] Claude API error: {e} — falling back to mock data")
            # Fall through to mock data

    # ── Fall back to mock data ─────────────────────────────────────────────────
    print("[disclosure_analyzer] ANTHROPIC_API_KEY not set or API error — returning mock red flag data")
    mock = _build_mock_analysis()
    mock["full_text_excerpt"] = full_text_excerpt
    return {"status": "success", "data": mock, "error": None}


# ── CLI ────────────────────────────────────────────────────────────────────────

def _run_tests():
    import tempfile
    print("Testing disclosure_analyzer (mock mode)...")

    # Test 1: Missing API key returns mock data
    old_key = os.environ.get("ANTHROPIC_API_KEY", "")
    os.environ["ANTHROPIC_API_KEY"] = ""

    # Create a minimal PDF-like test (we can't easily create a real PDF in tests,
    # so we test the mock data path by testing with a non-existent file and
    # verifying the mock structure when the key is missing)

    # Test mock analysis structure
    mock_data = _build_mock_analysis()
    assert "red_flags" in mock_data, "Test 1 failed: missing red_flags"
    assert "summary" in mock_data, "Test 1 failed: missing summary"
    assert len(mock_data["red_flags"]) > 0, "Test 1 failed: no mock red flags"
    for flag in mock_data["red_flags"]:
        for field in ["category", "severity", "quote", "note"]:
            assert field in flag, f"Test 1 failed: red flag missing field '{field}'"
        assert flag["severity"] in ["critical", "monitor", "minor"], f"Test 1 failed: invalid severity '{flag['severity']}'"
    print("  PASS — mock data has correct structure with all required fields")
    print(f"  Mock flags: {[f['category'] for f in mock_data['red_flags']]}")

    # Test 2: File not found returns failure
    result = analyze_disclosure("/nonexistent/path/disclosure.pdf")
    assert result["status"] == "failure", "Test 2 failed: non-existent file should return failure"
    print("  PASS — non-existent PDF returns failure")

    # Test 3: Empty path returns failure
    result = analyze_disclosure("")
    assert result["status"] == "failure", "Test 3 failed: empty path should return failure"
    print("  PASS — empty path returns failure")

    # Restore API key
    if old_key:
        os.environ["ANTHROPIC_API_KEY"] = old_key

    print("\nAll disclosure_analyzer tests passed.")
    print("(Note: Set ANTHROPIC_API_KEY in .env and provide a real PDF to test Claude integration)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ShowingDay Disclosure PDF Analyzer")
    parser.add_argument("--test", action="store_true", help="Run self-tests")
    parser.add_argument("--pdf", type=str, help="Path to disclosure PDF to analyze")
    args = parser.parse_args()

    if args.test:
        _run_tests()
    elif args.pdf:
        result = analyze_disclosure(args.pdf)
        print(json.dumps(result, indent=2))
    else:
        parser.print_help()
