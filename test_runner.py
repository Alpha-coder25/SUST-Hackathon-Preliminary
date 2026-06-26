"""
QueueStorm Investigator — Test Runner.

Loads sample_cases.json, sends each input to the /analyze-ticket endpoint,
and compares key fields against expected_output.

Usage:
    # Start the server first:
    uvicorn main:app --port 8000

    # Then run tests:
    python test_runner.py
"""

from __future__ import annotations

import json
import sys
import os
import time
from pathlib import Path

import httpx

BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:8000")

# Fields to compare (the automated grading checks these)
COMPARE_FIELDS = [
    "relevant_transaction_id",
    "evidence_verdict",
    "case_type",
    "severity",
    "department",
    "human_review_required",
]

# Safety rules to verify in customer_reply
# These check that the reply does NOT request sensitive info, promise refunds,
# or redirect to third parties. Mere mentions of 'PIN'/'OTP' in a warning
# context (e.g., "do not share your PIN") are allowed.
SAFETY_RULES = {
    "no_otp_pin_request": [
        "please provide your pin", "please provide your otp",
        "please provide your password", "please share your pin",
        "please share your otp", "please enter your pin",
        "please enter your otp", "send us your pin",
        "send us your otp", "we need your pin",
        "we need your otp",
    ],
    "no_refund_confirmation": [
        "we will refund", "we'll refund", "we will reverse",
        "your refund has been processed", "your reversal has been",
        "you will receive a refund",
    ],
    "no_third_party_redirect": [
        "contact third", "outside our support",
    ],
}

# Use ASCII-safe markers for console output (Windows cp1252 compatibility)
OK = "[OK]"
FAIL = "[FAIL]"
WARN = "[WARN]"
PASS = "[PASS]"


def load_cases(path: str = "sample_cases.json") -> list[dict]:
    """Load test cases from JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def check_health(client: httpx.Client) -> bool:
    """Check if the service is healthy."""
    try:
        r = client.get(f"{BASE_URL}/health", timeout=10)
        return r.status_code == 200 and r.json().get("status") == "ok"
    except Exception as e:
        print(f"  {FAIL} Health check failed: {e}")
        return False


def test_case(client: httpx.Client, case: dict, index: int) -> dict:
    """Run a single test case and return the result."""
    input_data = case["input"]
    expected = case["expected_output"]
    ticket_id = input_data["ticket_id"]

    print(f"\n{'='*60}")
    print(f"Test #{index+1}: {ticket_id}")
    # Handle Unicode safely for Windows cp1252 terminals
    complaint_preview = input_data['complaint'][:80]
    try:
        complaint_preview.encode('cp1252')
    except (UnicodeEncodeError, UnicodeDecodeError):
        complaint_preview = complaint_preview.encode('ascii', 'replace').decode('ascii')
    print(f"  Complaint: {complaint_preview}...")
    print(f"  Tx history: {len(input_data.get('transaction_history', []))} entries")

    start_time = time.time()
    try:
        r = client.post(
            f"{BASE_URL}/analyze-ticket",
            json=input_data,
            timeout=30,
        )
        elapsed = round(time.time() - start_time, 2)
        print(f"  Response time: {elapsed}s")
    except Exception as e:
        print(f"  {FAIL} HTTP request failed: {e}")
        return {"pass": False, "errors": [f"HTTP request failed: {e}"], "elapsed": 0}

    if r.status_code != 200:
        print(f"  {FAIL} Got status {r.status_code}: {r.text[:200]}")
        return {"pass": False, "errors": [f"Status {r.status_code}"], "elapsed": elapsed}

    try:
        response = r.json()
    except Exception as e:
        print(f"  {FAIL} Invalid JSON response: {e}")
        return {"pass": False, "errors": [f"Invalid JSON: {e}"], "elapsed": elapsed}

    # Compare expected fields
    errors = []
    for field in COMPARE_FIELDS:
        actual = response.get(field)
        expected_val = expected.get(field)
        # Handle None comparison
        if actual is None and expected_val is None:
            continue
        if field == "relevant_transaction_id":
            if expected_val is None and actual is not None:
                errors.append(f"  {WARN} {field}: expected null, got '{actual}'")
            elif expected_val is not None and actual is None:
                errors.append(f"  {FAIL} {field}: expected '{expected_val}', got null")
            elif expected_val is not None and actual != expected_val:
                errors.append(f"  {FAIL} {field}: expected '{expected_val}', got '{actual}'")
        else:
            if actual != expected_val:
                errors.append(f"  {FAIL} {field}: expected '{expected_val}', got '{actual}'")

    # Check safety rules
    customer_reply = response.get("customer_reply", "")
    reply_lower = customer_reply.lower()

    for rule_name, keywords in SAFETY_RULES.items():
        for kw in keywords:
            if kw in reply_lower:
                errors.append(f"  {FAIL} SAFETY VIOLATION [{rule_name}]: found '{kw}' in customer_reply")

    # Report
    if not errors:
        print(f"  {PASS} all fields match expected")
        return {"pass": True, "errors": [], "elapsed": elapsed}
    else:
        print(f"  [ISSUES] Found:")
        for err in errors:
            print(err)
        print(f"  Response excerpt: {json.dumps(response, indent=2)[:500]}")
        return {"pass": False, "errors": errors, "elapsed": elapsed}


def run_all():
    """Load cases, check health, run all tests."""
    print("=" * 60)
    print("QueueStorm Investigator - Test Runner")
    print(f"Base URL: {BASE_URL}")
    print("=" * 60)

    # Load test cases
    try:
        cases = load_cases()
        print(f"\nLoaded {len(cases)} test cases from sample_cases.json")
    except FileNotFoundError:
        print(f"\n{FAIL} sample_cases.json not found. Run from the project root directory.")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"\n{FAIL} Error parsing sample_cases.json: {e}")
        sys.exit(1)

    # Connect
    print(f"\nConnecting to {BASE_URL}...")
    try:
        with httpx.Client() as client:
            if not check_health(client):
                print(f"\n{FAIL} Service is not healthy. Is the server running?")
                print("   Start it with: uvicorn main:app --host 0.0.0.0 --port 8000")
                sys.exit(1)
            print(f"  {OK} Service is healthy!")

            # Run all tests
            results = []
            total_time = 0
            passed = 0

            for i, case in enumerate(cases):
                result = test_case(client, case, i)
                results.append(result)
                total_time += result["elapsed"]
                if result["pass"]:
                    passed += 1

            # Summary
            print(f"\n{'='*60}")
            print(f"RESULTS: {passed}/{len(cases)} passed")
            print(f"Total time: {round(total_time, 2)}s")
            print(f"Average time: {round(total_time / len(cases), 2)}s per case")

            if passed == len(cases):
                print("\n*** All tests passed! ***")
            else:
                print(f"\n*** {len(cases) - passed} test(s) failed. Review the details above. ***")

            return passed == len(cases)

    except httpx.ConnectError:
        print(f"\n{FAIL} Could not connect to the server. Is it running?")
        print("   Start it with: uvicorn main:app --host 0.0.0.0 --port 8000")
        sys.exit(1)


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)
