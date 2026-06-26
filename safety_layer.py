"""
QueueStorm Investigator — Safety Layer.

Enforces safety rules on all generated responses BEFORE they are returned:
  - Never asks for PIN/OTP/password/full card number
  - Never confirms a refund/reversal/unblock (use neutral language)
  - Never redirects customer to unofficial third parties
  - Neutralizes prompt injection from complaint text
  - Forces human_review_required for phishing cases
"""

from __future__ import annotations

import re
from typing import Optional

from models import CaseType, Department


# ── Prohibited Pattern Detection ───────────────────────────────────────────────

# Patterns that request sensitive information
SENSITIVE_INFO_PATTERNS = [
    re.compile(r"(?:please|kindly|you need to|we need you to|could you|can you)\s*(?:provide|share|send|enter|give|tell)\s*(?:your\s+)?(?:pin|otp|password|mpin|passcode|security code|verification code|full card number|cvv|cvc)", re.IGNORECASE),
    re.compile(r"(?:ask|request|require|need)\s*(?:for\s+)?(?:your\s+)?(?:pin|otp|password|mpin|passcode|security code|verification code|full card number|cvv|cvc)", re.IGNORECASE),
    re.compile(r"\b(?:otp|pin|mpin|password)\s+(?:has been sent|will be sent|is required|is needed|must be provided|must be entered|must be shared|must be given)\b", re.IGNORECASE),
    re.compile(r"(?:send|share|provide|enter|give|tell)\s+(?:me|us|the system)\s+(?:your\s+)?(?:pin|otp|password|mpin|passcode|security code|verification code)", re.IGNORECASE),
]

# Patterns that promise/confirm refund, reversal, or unblock
REFUND_PROMISE_PATTERNS = [
    re.compile(r"(?:we|our team|the system)\s+(?:will|shall|are going to)\s+(?:refund|reverse|return|credit back|give back|reimburse|unblock|release)", re.IGNORECASE),
    re.compile(r"(?:your|the)\s+(?:refund|reversal|return|reimbursement|unblock)\s+(?:has been|will be|is being)\s+(?:processed|initiated|completed|approved)", re.IGNORECASE),
    re.compile(r"(?:we will|we'll|we shall)\s+(?:process|initiate|complete|approve|issue)\s+(?:a|the|your)\s+(?:refund|reversal|return)", re.IGNORECASE),
    re.compile(r"\byou will receive\b\s+(?:a\s+)?(?:refund|reversal|reimbursement|the amount)", re.IGNORECASE),
]

# Patterns that redirect to unofficial third parties
THIRD_PARTY_REDIRECT_PATTERNS = [
    re.compile(r"(?:contact|reach|call|message|reach out to)\s+(?!our|the|customer support|official|authorized|designated)(?:\w+)\s+(?:at|on|via)\s+(?:\d{10,}|[\w.]+@[\w.]+|www\.)", re.IGNORECASE),
    re.compile(r"(?:go to|visit|check)\s+(?!our|the)(?:\w+)\s+(?:website|site|page|portal|app)(?:\s+(?:at|on)\s+[\w./-]+)?", re.IGNORECASE),
    re.compile(r"(?:outside\s+our|not\s+our|third.party|external)\s+(?:support|channel|service)", re.IGNORECASE),
]


def contains_sensitive_request(text: str) -> bool:
    """Check if text asks for PIN/OTP/password/full card number."""
    for pattern in SENSITIVE_INFO_PATTERNS:
        if pattern.search(text):
            return True
    return False


def contains_refund_promise(text: str) -> bool:
    """Check if text promises or confirms a refund/reversal/unblock."""
    for pattern in REFUND_PROMISE_PATTERNS:
        if pattern.search(text):
            return True
    return False


def contains_third_party_redirect(text: str) -> bool:
    """Check if text redirects to unofficial third parties."""
    for pattern in THIRD_PARTY_REDIRECT_PATTERNS:
        if pattern.search(text):
            return True
    return False


# ── Safe replacements ──────────────────────────────────────────────────────────

def neutral_refund_replacement(match: re.Match) -> str:
    """Replace refund-confirming language with neutral phrasing."""
    text = match.group(0).lower()
    if "refund" in text or "reimburse" in text or "return" in text or "credit" in text:
        return "any eligible amount will be returned through official channels"
    if "reverse" in text or "reversal" in text:
        return "any eligible reversal will be processed through official channels"
    if "unblock" in text or "release" in text:
        return "any eligible action will be taken through official channels"
    return text


# ── Main Safety Check Function ─────────────────────────────────────────────────

def apply_safety_layer(
    response: dict,
    raw_complaint: str,
) -> dict:
    """
    Apply all safety checks to the response dict.
    Modifies fields in-place and returns the sanitized response.
    """
    # ── Step 1: Force phishing overrides ──
    if response.get("case_type") == CaseType.phishing_or_social_engineering.value:
        response["human_review_required"] = True
        response["department"] = Department.fraud_risk.value

    # ── Step 2: Check all text fields for violations ──
    text_fields = ["agent_summary", "recommended_next_action", "customer_reply"]

    for field in text_fields:
        text = response.get(field, "")
        if not text:
            continue

        # Check sensitive info requests
        if contains_sensitive_request(text):
            # Replace with safe version
            response[field] = _sanitize_sensitive_info(text)

        # Check refund promises
        if contains_refund_promise(text):
            response[field] = _sanitize_refund_promises(response[field])

        # Check third-party redirects
        if contains_third_party_redirect(text):
            response[field] = _sanitize_third_party_redirects(response[field])

    # ── Step 3: Check for prompt injection indicators in complaint ──
    injection_indicators = [
        "ignore previous", "ignore all", "forget your", "you are not",
        "system prompt", "you are a", "act as", "pretend", "from now on",
        "override", "disregard", "do not follow", "do not obey",
        "new instructions", "new rule", "you must", "you will",
    ]
    complaint_lower = raw_complaint.lower()
    found_injection = any(indicator in complaint_lower for indicator in injection_indicators)

    if found_injection:
        # Reinforce safety in output — don't change what we already generated,
        # but flag it for human review
        response["human_review_required"] = True
        if "PROMPT_INJECTION_DETECTED" not in (response.get("reason_codes") or []):
            codes = response.get("reason_codes") or []
            codes.append("PROMPT_INJECTION_DETECTED")
            response["reason_codes"] = codes

    return response


def _sanitize_sensitive_info(text: str) -> str:
    """Remove or replace any request for sensitive information.
    Applies all patterns iteratively to handle overlapping matches.
    """
    any_match = False
    for pattern in SENSITIVE_INFO_PATTERNS:
        if pattern.search(text):
            any_match = True
            # Remove the sensitive request
            text = pattern.sub("", text)
    # Clean up artifacts from all patterns at once
    if any_match:
        text = re.sub(r"\s{2,}", " ", text)
        text = re.sub(r",\s*,", ",", text)
        text = re.sub(r"\.\s*\.", ".", text)
        text = re.sub(r"\s+\.", ".", text)
        text = re.sub(r"\.\s+", ". ", text)
        text = text.strip()
        if not text:
            text = "Please use our official support channels for verification."
    return text


def _sanitize_refund_promises(text: str) -> str:
    """Replace refund-confirming language with neutral phrasing."""
    for pattern in REFUND_PROMISE_PATTERNS:
        text = pattern.sub(neutral_refund_replacement, text)
    return text


def _sanitize_third_party_redirects(text: str) -> str:
    """Remove third-party redirect instructions."""
    for pattern in THIRD_PARTY_REDIRECT_PATTERNS:
        text = pattern.sub("contact our official support channels", text)
    return text


# ── Integrated safety check for generated replies ─────────────────────────────

def validate_customer_reply_safety(reply: str) -> tuple[bool, list[str]]:
    """
    Validate a customer reply against all safety rules.
    Returns (is_safe, list_of_violations).
    """
    violations = []

    if contains_sensitive_request(reply):
        violations.append("SENSITIVE_INFO_REQUEST")

    if contains_refund_promise(reply):
        violations.append("REFUND_PROMISE")

    if contains_third_party_redirect(reply):
        violations.append("THIRD_PARTY_REDIRECT")

    return len(violations) == 0, violations
