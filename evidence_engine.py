"""
QueueStorm Investigator — Evidence Engine.

Parses a complaint, searches transaction_history for the best-matching
entry, derives evidence_verdict, case_type, severity, and department
using deterministic rule-based logic.

This module is the core of the "investigator" — every decision is justified
by checking transaction_history against the complaint text.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from models import (
    AnalyzeTicketRequest,
    CaseType,
    Department,
    EvidenceVerdict,
    Severity,
    TransactionHistoryItem,
    TransactionStatus,
    TransactionType,
)


# ── Pattern Helpers ────────────────────────────────────────────────────────────

# Amount patterns: "BDT 500", "500 taka", "TK 500", "500tk", "500.00"
AMOUNT_PATTERNS = [
    re.compile(r"(?:BDT|TK|Tk|tk|৳)\s*(\d{1,10}(?:\.\d{1,2})?)", re.IGNORECASE),
    re.compile(r"(\d{1,10}(?:\.\d{1,2})?)\s*(?:taka|tk|টাকা)", re.IGNORECASE),
    re.compile(r"(?:amount of|amounting to|of)\s+(\d{1,10}(?:\.\d{1,2})?)", re.IGNORECASE),
    re.compile(r"(?:^|\s)(\d{1,10}(?:\.\d{1,2})?)(?:\s*(?:taka|tk|টাকা))?(?:\s|$|\.)", re.IGNORECASE),
]

# Counterparty patterns: phone numbers (11 digits, BD format), merchant/agent IDs
COUNTERPARTY_PHONE = re.compile(r"0\d{10}")
COUNTERPARTY_MERCHANT = re.compile(r"(?:merchant|shop|store|agent|user)\s*(?:id|name|account)?\s*[#:]?\s*(\w+)", re.IGNORECASE)
COUNTERPARTY_RAW = re.compile(r"(?:to|sent to|paid to|transferred to|received from)\s+(\w+(?:\s+\w+)?)", re.IGNORECASE)

# Time/date patterns
DATE_PATTERNS = [
    re.compile(r"(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})"),
    re.compile(r"(yesterday|today|last\s+(?:night|week|month|day)|(\d+)\s*(?:days?|hrs?|hours?|mins?|minutes?)\s*ago)", re.IGNORECASE),
    re.compile(r"(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s*(\d{4})?", re.IGNORECASE),
    re.compile(r"(\d{1,2})(?:st|nd|rd|th)?\s+(january|february|march|april|may|june|july|august|september|october|november|december),?\s*(\d{4})?", re.IGNORECASE),
]

# Transaction type keywords
TYPE_KEYWORDS = {
    TransactionType.transfer: ["transfer", "send", "sent", "bKash", "send money", "wrong number", "wrong person"],
    TransactionType.payment: ["payment", "pay", "paid", "bill", "purchase", "checkout", "merchant payment"],
    TransactionType.cash_in: ["cash in", "cashin", "deposit", "add money", "add fund", "top up"],
    TransactionType.cash_out: ["cash out", "cashout", "withdraw", "withdrawal"],
    TransactionType.settlement: ["settlement", "settle", "merchant settlement", "payout"],
    TransactionType.refund: ["refund", "return", "money back", "reversal"],
}

# Severity thresholds
SEVERITY_AMOUNT_THRESHOLDS = [
    (Severity.critical, 100_000),
    (Severity.high, 50_000),
    (Severity.medium, 5_000),
    (Severity.low, 0),
]

# Case-type → default department mapping
CASE_DEPARTMENT_MAP = {
    CaseType.wrong_transfer: Department.dispute_resolution,
    CaseType.payment_failed: Department.payments_ops,
    CaseType.refund_request: Department.payments_ops,
    CaseType.duplicate_payment: Department.payments_ops,
    CaseType.merchant_settlement_delay: Department.merchant_operations,
    CaseType.agent_cash_in_issue: Department.agent_operations,
    CaseType.phishing_or_social_engineering: Department.fraud_risk,
    CaseType.other: Department.customer_support,
}

# Case-type keywords for classification
CASE_TYPE_KEYWORDS = {
    CaseType.wrong_transfer: [
        "wrong number", "wrong person", "wrong account", "sent to wrong",
        "transferred to wrong", "mistakenly sent", "accidentally sent",
        "send to wrong", "wrong recipient", "wrong bKash",
        # Broader patterns for implicit wrong-transfer cases
        "didn't receive", "did not receive",
        # Bangla / Banglish
        "ভুল নম্বর", "ভুল নাম্বার", "ভুল নম্বরে", "ভুল পাঠানো",
        "vul number", "vul nomor", "bhul number",
    ],
    CaseType.payment_failed: [
        "payment failed", "transaction failed", "money deducted but",
        "amount deducted but", "charged but", "payment not completed",
        "payment unsuccessful", "payment didn't go through",
        "money taken but", "not received",
        # Bangla
        "পেমেন্ট failed", "পেমেন্ট ব্যর্থ", "টাকা কেটেছে কিন্তু",
        "টাকা কেটে নিয়েছে কিন্তু", "payment hoy nai",
    ],
    CaseType.refund_request: [
        "refund", "money back", "return my money", "give me back",
        "reverse the transaction", "refund request",
        # Bangla
        "ফেরত", "টাকা ফেরত", "ফেরত দিন", "ফেরত চাই",
        "টাকা ফেরত দিন", "refund korun",
    ],
    CaseType.duplicate_payment: [
        "duplicate", "charged twice", "deducted twice", "same payment",
        "double charged", "two times", "multiple times",
    ],
    CaseType.merchant_settlement_delay: [
        "settlement", "settle", "payout not received", "merchant settlement",
        "payment not settled", "due settlement",
    ],
    CaseType.agent_cash_in_issue: [
        "agent", "cash in", "cashin", "agent didn't", "agent not",
        "cash in not", "add money agent",
        # Bangla
        "এজেন্ট", "ক্যাশ ইন", "এজেন্ট ক্যাশ",
    ],
    CaseType.phishing_or_social_engineering: [
        "phishing", "scam", "fraud", "fake", "suspicious",
        "unknown number", "didn't authorize", "unauthorized",
        "hacked", "compromised", "otp", "pin", "stranger",
        "unknown person", "didn't make this", "not me",
        # Bangla
        "প্রতারনা", "স্ক্যাম", "জালিয়াতি", "অজানা নাম্বার",
        "পিন চেয়েছে", "ওটিপি চেয়েছে",
    ],
}


# ── Extraction Functions ──────────────────────────────────────────────────────

def extract_amount(text: str) -> Optional[float]:
    """Extract the first monetary amount mentioned in the text."""
    for pattern in AMOUNT_PATTERNS:
        match = pattern.search(text)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                continue
    return None


# Generic/stop words that are not valid counterparty identifiers
_GENERIC_WORDS = {
    "him", "her", "them", "someone", "somebody", "the bank", "bkash",
    "last", "the", "and", "a", "an", "for", "but", "with", "its", "has",
    "not", "been", "was", "had", "week", "month", "day", "this", "that",
    "from", "they", "are", "were", "will", "can", "all", "also", "very",
    "just", "then", "than", "more", "some", "such", "each", "which",
    "their", "there", "would", "could", "should", "about", "after",
    "said", "made", "make", "your", "into", "shop", "store", "agent",
    "user", "merchant", "name", "account", "number", "code", "id",
}


def _is_generic_word(word: str) -> bool:
    """Check if a word or phrase is a generic/stop word, not a real counterparty identifier.
    For multi-word phrases, returns True if ALL words are generic.
    """
    words = word.lower().split()
    return all(w in _GENERIC_WORDS for w in words)


def extract_counterparty(text: str) -> Optional[str]:
    """Extract a counterparty identifier (phone, merchant name, etc.) from the complaint."""
    phone_match = COUNTERPARTY_PHONE.search(text)
    if phone_match:
        return phone_match.group(0)

    merchant_match = COUNTERPARTY_MERCHANT.search(text)
    if merchant_match:
        name = merchant_match.group(1).strip()
        if not _is_generic_word(name):
            return name

    raw_match = COUNTERPARTY_RAW.search(text)
    if raw_match:
        name = raw_match.group(1).strip()
        # Skip generic words
        if not _is_generic_word(name):
            return name

    return None


def extract_transaction_type(text: str) -> Optional[TransactionType]:
    """Guess the transaction type from complaint keywords."""
    text_lower = text.lower()
    for tx_type, keywords in TYPE_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                return tx_type
    return None


def extract_time_reference(text: str) -> Optional[str]:
    """
    Attempt to extract a time reference from the complaint.
    Returns a simplified string like 'yesterday' or a date-time suggestion.
    """
    for pattern in DATE_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(0)
    return None


# ── Matching Logic ─────────────────────────────────────────────────────────────

def compute_amount_similarity(complaint_amount: float, tx_amount: float) -> float:
    """Compute a similarity score (0-1) for two amounts."""
    if tx_amount == 0 and complaint_amount == 0:
        return 1.0
    if tx_amount == 0:
        return 0.0
    ratio = min(complaint_amount, tx_amount) / max(complaint_amount, tx_amount)
    return ratio


def compute_time_proximity(tx_timestamp_str: str, complaint_time_ref: Optional[str]) -> float:
    """
    Compute a proxy score for time proximity.
    If no complaint time ref, assume moderate proximity (0.5).
    """
    if not complaint_time_ref:
        return 0.5

    try:
        tx_time = datetime.fromisoformat(tx_timestamp_str)
    except (ValueError, TypeError):
        return 0.5

    now = datetime.now(timezone.utc)
    tx_age_hours = abs((now - tx_time).total_seconds()) / 3600

    # Recent transactions are more likely to be relevant
    if tx_age_hours < 1:
        return 1.0
    elif tx_age_hours < 24:
        return 0.9
    elif tx_age_hours < 72:
        return 0.7
    elif tx_age_hours < 168:  # 1 week
        return 0.5
    elif tx_age_hours < 720:  # 30 days
        return 0.3
    else:
        return 0.1


def counterparty_match_score(complaint_cp: Optional[str], tx_cp: str) -> float:
    """Score how well a counterparty from complaint matches a transaction's counterparty."""
    if not complaint_cp:
        return 0.5  # no info, neutral
    complaint_cp_lower = complaint_cp.lower().replace(" ", "")
    tx_cp_lower = tx_cp.lower().replace(" ", "")
    if complaint_cp_lower == tx_cp_lower:
        return 1.0
    if complaint_cp_lower in tx_cp_lower or tx_cp_lower in complaint_cp_lower:
        return 0.8
    # Check phone numbers
    phone_match = re.search(r"0\d{10}", complaint_cp_lower)
    tx_phone_match = re.search(r"0\d{10}", tx_cp_lower)
    if phone_match and tx_phone_match and phone_match.group(0) == tx_phone_match.group(0):
        return 1.0
    return 0.2


def type_match_score(complaint_type: Optional[TransactionType], tx_type: TransactionType) -> float:
    """Score how well the complaint's guessed type matches the transaction type."""
    if not complaint_type:
        return 0.5
    return 1.0 if complaint_type == tx_type else 0.3


def find_best_matching_transaction(
    complaint: str,
    transaction_history: list[TransactionHistoryItem],
) -> tuple[Optional[TransactionHistoryItem], float, dict[str, float]]:
    """
    Find the transaction in history that best matches the complaint.
    Returns (best_tx, best_score, scores_breakdown).
    """
    if not transaction_history:
        return None, 0.0, {"reason": "no transaction history"}

    complaint_amount = extract_amount(complaint)
    complaint_cp = extract_counterparty(complaint)
    complaint_type = extract_transaction_type(complaint)
    complaint_time_ref = extract_time_reference(complaint)

    best_tx = None
    best_score = -1.0
    best_breakdown = {}

    for tx in transaction_history:
        amount_score = compute_amount_similarity(complaint_amount, tx.amount) if complaint_amount else 0.5
        time_score = compute_time_proximity(tx.timestamp, complaint_time_ref)
        cp_score = counterparty_match_score(complaint_cp, tx.counterparty)
        type_score = type_match_score(complaint_type, tx.type)

        # Weighted combination
        total_score = (
            amount_score * 0.35 +
            time_score * 0.15 +
            cp_score * 0.30 +
            type_score * 0.20
        )

        if total_score > best_score:
            best_score = total_score
            best_tx = tx
            best_breakdown = {
                "amount_score": round(amount_score, 3),
                "time_score": round(time_score, 3),
                "counterparty_score": round(cp_score, 3),
                "type_score": round(type_score, 3),
                "total_score": round(total_score, 3),
            }

    return best_tx, best_score, best_breakdown


# ── Classification Functions ───────────────────────────────────────────────────

def determine_evidence_verdict(
    best_tx: Optional[TransactionHistoryItem],
    best_score: float,
    complaint: str,
    transaction_history: list[TransactionHistoryItem],
) -> EvidenceVerdict:
    """Determine the evidence verdict based on matching results."""
    if not transaction_history or not best_tx:
        return EvidenceVerdict.insufficient_data

    if best_score < 0.6:
        return EvidenceVerdict.insufficient_data

    complaint_lower = complaint.lower()

    # Check for inconsistency: if transaction is already reversed/refunded
    if best_tx.status == TransactionStatus.reversed:
        return EvidenceVerdict.inconsistent

    # Check for inconsistency: repeated transfers to same counterparty for "wrong transfer"
    if "wrong" in complaint_lower or "mistaken" in complaint_lower or "accidental" in complaint_lower:
        same_cp_count = sum(
            1 for tx in transaction_history
            if tx.counterparty.lower() == best_tx.counterparty.lower()
            and tx.transaction_id != best_tx.transaction_id
        )
        if same_cp_count >= 2:
            return EvidenceVerdict.inconsistent

    # Check for inconsistency: claiming non-receipt but transaction is completed
    if ("not receive" in complaint_lower or "didn't receive" in complaint_lower or "not get" in complaint_lower):
        if best_tx.status == TransactionStatus.completed and best_tx.type in (
            TransactionType.transfer, TransactionType.payment
        ):
            return EvidenceVerdict.inconsistent

    # Check for duplicate payment claim
    if "duplicate" in complaint_lower or "twice" in complaint_lower or "double" in complaint_lower:
        similar_amount_txs = [
            tx for tx in transaction_history
            if abs(tx.amount - best_tx.amount) < 1.0
            and tx.counterparty.lower() == best_tx.counterparty.lower()
        ]
        if len(similar_amount_txs) >= 2:
            return EvidenceVerdict.consistent
        else:
            return EvidenceVerdict.inconsistent

    # Check for refund request where transaction was already refunded
    if "refund" in complaint_lower:
        if best_tx.status == TransactionStatus.reversed:
            return EvidenceVerdict.inconsistent

    return EvidenceVerdict.consistent


def determine_case_type(complaint: str, best_tx: Optional[TransactionHistoryItem]) -> CaseType:
    """Classify the case type from complaint text and transaction context."""
    complaint_lower = complaint.lower()

    # Check phishing/scam first (safety priority)
    for keyword in CASE_TYPE_KEYWORDS[CaseType.phishing_or_social_engineering]:
        if keyword in complaint_lower:
            return CaseType.phishing_or_social_engineering

    # Check wrong transfer
    for keyword in CASE_TYPE_KEYWORDS[CaseType.wrong_transfer]:
        if keyword in complaint_lower:
            return CaseType.wrong_transfer

    # Check duplicate payment
    for keyword in CASE_TYPE_KEYWORDS[CaseType.duplicate_payment]:
        if keyword in complaint_lower:
            return CaseType.duplicate_payment

    # Check refund request
    for keyword in CASE_TYPE_KEYWORDS[CaseType.refund_request]:
        if keyword in complaint_lower:
            return CaseType.refund_request

    # Check agent cash-in issue (before payment_failed since 'transaction failed' is too broad)
    for keyword in CASE_TYPE_KEYWORDS[CaseType.agent_cash_in_issue]:
        if keyword in complaint_lower:
            return CaseType.agent_cash_in_issue

    # Check payment failed
    for keyword in CASE_TYPE_KEYWORDS[CaseType.payment_failed]:
        if keyword in complaint_lower:
            return CaseType.payment_failed

    # Check merchant settlement delay
    for keyword in CASE_TYPE_KEYWORDS[CaseType.merchant_settlement_delay]:
        if keyword in complaint_lower:
            return CaseType.merchant_settlement_delay

    # Try to infer from best_tx type
    if best_tx:
        if best_tx.type == TransactionType.refund:
            return CaseType.refund_request
        if best_tx.type == TransactionType.settlement:
            return CaseType.merchant_settlement_delay
        if best_tx.status == TransactionStatus.failed and best_tx.type in (
            TransactionType.payment, TransactionType.transfer
        ):
            return CaseType.payment_failed

    return CaseType.other


def determine_severity(
    complaint_amount: Optional[float],
    case_type: CaseType,
    evidence_verdict: EvidenceVerdict,
    best_tx: Optional[TransactionHistoryItem],
) -> Severity:
    """Determine severity based on amount, case type, and evidence."""
    # Phishing is always at least high
    if case_type == CaseType.phishing_or_social_engineering:
        return Severity.critical

    # Inconsistent evidence → bump severity
    base_severity = Severity.low
    if evidence_verdict == EvidenceVerdict.inconsistent:
        base_severity = Severity.medium

    # Determine amount
    amount = complaint_amount
    if amount is None and best_tx:
        amount = best_tx.amount
    if amount is None:
        amount = 0

    # For duplicate payment, double the amount to account for both charges
    if case_type == CaseType.duplicate_payment and evidence_verdict == EvidenceVerdict.consistent:
        if amount is not None and amount > 0:
            amount = amount * 2

    # Apply amount thresholds
    for sev, threshold in SEVERITY_AMOUNT_THRESHOLDS:
        if amount >= threshold:
            amount_severity = sev
            break
    else:
        amount_severity = Severity.low

    # Take the higher of base and amount severity
    severity_order = [Severity.low, Severity.medium, Severity.high, Severity.critical]
    base_idx = severity_order.index(base_severity)
    amount_idx = severity_order.index(amount_severity)

    return severity_order[max(base_idx, amount_idx)]


def determine_recommended_next_action(
    case_type: CaseType,
    severity: Severity,
    evidence_verdict: EvidenceVerdict,
    human_review_required: bool,
) -> str:
    """Generate a recommended next action based on case analysis."""
    if human_review_required:
        actions = {
            CaseType.wrong_transfer: "Escalate to dispute resolution team for manual review and trace the transaction to the recipient. Initiate fund recovery process if applicable.",
            CaseType.phishing_or_social_engineering: "Immediately escalate to fraud/risk team. Flag the account for suspicious activity. Do not process any refund or reversal without manual verification.",
            CaseType.payment_failed: "Escalate to payments operations for manual verification. Check payment gateway logs and confirm transaction status with the partner bank.",
            CaseType.refund_request: "Route to payments operations for manual review. Verify the original transaction and refund eligibility before proceeding.",
            CaseType.duplicate_payment: "Escalate to payments operations to verify duplicate charges and initiate reversal of the extra charge.",
            CaseType.merchant_settlement_delay: "Route to merchant operations for manual investigation. Check settlement batch logs and payment gateway reports.",
            CaseType.agent_cash_in_issue: "Escalate to agent operations for verification. Check agent balance and transaction logs.",
            CaseType.other: "Review ticket details and route to the appropriate department for manual handling.",
        }
        return actions.get(case_type, "Escalate for manual review.")

    if evidence_verdict == EvidenceVerdict.insufficient_data:
        return "Request additional transaction details from the customer, including transaction ID, date, amount, and counterparty information."

    if evidence_verdict == EvidenceVerdict.inconsistent:
        return "Review the transaction history carefully. The evidence does not fully support the complaint. Contact the customer for clarification."

    standard_actions = {
        CaseType.wrong_transfer: "Trace the transaction and initiate standard fund recovery process. Keep the customer informed of progress.",
        CaseType.payment_failed: "Verify with the payment gateway. If the payment failed, the amount will be auto-reversed within 24-48 hours. Inform the customer.",
        CaseType.refund_request: "Verify refund eligibility against the transaction. Process the refund through official channels if eligible.",
        CaseType.duplicate_payment: "Verify the duplicate charge and initiate reversal of the extra amount through standard procedures.",
        CaseType.merchant_settlement_delay: "Check the settlement schedule and payment gateway reports. Provide the customer with the expected settlement date.",
        CaseType.agent_cash_in_issue: "Verify the agent transaction logs. If confirmed, process the cash-in through standard procedures.",
        CaseType.phishing_or_social_engineering: "Flag for monitoring. Provide security guidance to the customer without confirming any refund.",
        CaseType.other: "Review the ticket and take appropriate action based on standard operating procedures.",
    }
    return standard_actions.get(case_type, "Review and process per standard procedures.")


# ── Main Entry Point ───────────────────────────────────────────────────────────

def investigate(request: AnalyzeTicketRequest) -> dict:
    """
    Main evidence investigation function.
    Takes an AnalyzeTicketRequest and returns a dict with all evidence findings.
    """
    complaint = request.complaint
    tx_history = request.transaction_history or []

    # Step 1: Find best matching transaction
    best_tx, best_score, match_breakdown = find_best_matching_transaction(complaint, tx_history)

    # Step 2: Determine evidence verdict
    evidence_verdict = determine_evidence_verdict(best_tx, best_score, complaint, tx_history)

    # Step 3: Classify case type
    case_type = determine_case_type(complaint, best_tx)

    # Step 4: Extract amount for severity
    complaint_amount = extract_amount(complaint)
    if complaint_amount is None and best_tx:
        complaint_amount = best_tx.amount

    # Step 5: Determine severity
    severity = determine_severity(complaint_amount, case_type, evidence_verdict, best_tx)

    # Step 6: Determine department
    department = CASE_DEPARTMENT_MAP.get(case_type, Department.customer_support)

    # Step 7: Determine if human review is needed
    human_review_required = (
        case_type == CaseType.phishing_or_social_engineering
        or case_type == CaseType.wrong_transfer
        or case_type == CaseType.duplicate_payment
        or evidence_verdict in (EvidenceVerdict.inconsistent, EvidenceVerdict.insufficient_data)
        or (complaint_amount is not None and complaint_amount >= 50000)
        or severity in (Severity.high, Severity.critical)
        or (best_tx is not None and best_tx.status == TransactionStatus.pending)
    )

    # Step 8: Generate agent summary
    agent_summary = generate_agent_summary(
        request, best_tx, evidence_verdict, case_type, severity, department, match_breakdown
    )

    # Step 9: Generate recommended next action
    recommended_next_action = determine_recommended_next_action(
        case_type, severity, evidence_verdict, human_review_required
    )

    # Step 10: Generate customer reply (safe)
    customer_reply = generate_customer_reply(
        case_type, evidence_verdict, severity, human_review_required, complaint
    )

    # Step 11: Build reason codes
    reason_codes = build_reason_codes(
        evidence_verdict, case_type, severity, human_review_required, best_tx, match_breakdown
    )

    return {
        "ticket_id": request.ticket_id,
        "relevant_transaction_id": best_tx.transaction_id if best_tx else None,
        "evidence_verdict": evidence_verdict.value,
        "case_type": case_type.value,
        "severity": severity.value,
        "department": department.value,
        "agent_summary": agent_summary,
        "recommended_next_action": recommended_next_action,
        "customer_reply": customer_reply,
        "human_review_required": human_review_required,
        "confidence": round(min(best_score + 0.1, 1.0), 2) if best_tx else 0.3,
        "reason_codes": reason_codes,
    }


def generate_agent_summary(
    request: AnalyzeTicketRequest,
    best_tx: Optional[TransactionHistoryItem],
    evidence_verdict: EvidenceVerdict,
    case_type: CaseType,
    severity: Severity,
    department: Department,
    match_breakdown: dict,
) -> str:
    """Generate a structured summary for the agent."""
    ticket_id = request.ticket_id
    channel = request.channel.value if request.channel else "unknown"
    user_type = request.user_type.value if request.user_type else "unknown"

    lines = [
        f"Ticket {ticket_id} — {case_type.value.replace('_', ' ').title()}",
        f"Channel: {channel} | User: {user_type} | Severity: {severity.value} | Dept: {department.value}",
        f"Evidence: {evidence_verdict.value.replace('_', ' ').title()}",
    ]

    if best_tx:
        lines.append(
            f"Matched Tx: {best_tx.transaction_id} | "
            f"Amount: {best_tx.amount} | "
            f"Type: {best_tx.type.value} | "
            f"Status: {best_tx.status.value} | "
            f"Counterparty: {best_tx.counterparty} | "
            f"Score: {match_breakdown.get('total_score', 'N/A')}"
        )
    else:
        lines.append("No matching transaction found.")

    lines.append(f"Complaint excerpt: {request.complaint[:150]}...")
    return "\n".join(lines)


def generate_customer_reply(
    case_type: CaseType,
    evidence_verdict: EvidenceVerdict,
    severity: Severity,
    human_review_required: bool,
    complaint: str,
) -> str:
    """
    Generate a safe customer reply.
    NEVER promises refunds, NEVER asks for OTP/PIN, NEVER redirects to third parties.
    """
    complaint_lower = complaint.lower()

    # Check for phishing/scam — most restrictive
    if case_type == CaseType.phishing_or_social_engineering:
        return (
            "Dear Customer, thank you for reporting this concern. "
            "We take your security seriously and have escalated this to our specialized team for investigation. "
            "Please do not share any personal information, PIN, OTP, or passwords with anyone. "
            "Our team will review the matter and get back to you through official channels within 24-48 hours. "
            "If you notice any unauthorized activity, please continue to report through our official support channels. "
            "Thank you for your patience."
        )

    # Human review required — generic, safe reply
    if human_review_required:
        return (
            "Dear Customer, thank you for reaching out to us. "
            "We understand your concern and have logged your complaint for detailed review. "
            "Our team will investigate the matter thoroughly and will contact you through official channels "
            "within 24-48 hours with an update. "
            "Please rest assured that if any eligible amount is involved, it will be returned through official channels "
            "as per our standard procedures. "
            "We appreciate your patience and understanding."
        )

    # Insufficient data
    if evidence_verdict == EvidenceVerdict.insufficient_data:
        return (
            "Dear Customer, thank you for contacting us. "
            "To help us investigate your concern effectively, please provide additional details "
            "such as the transaction ID, exact amount, date, and the recipient or counterparty involved. "
            "You can share these details securely through our official in-app support chat or email. "
            "Once we have the necessary information, we will review and update you promptly."
        )

    # Inconsistent evidence
    if evidence_verdict == EvidenceVerdict.inconsistent:
        return (
            "Dear Customer, thank you for bringing this to our attention. "
            "After reviewing your account, our records show transaction details that differ from your description. "
            "We would like to understand your concern better. "
            "Please reach out to us through our official support channels with any additional context you may have. "
            "Our team will review the matter and provide further assistance."
        )

    # Standard cases
    standard_replies = {
        CaseType.wrong_transfer: (
            "Dear Customer, we are sorry to hear about the wrong transfer. "
            "We have noted the details and our dispute resolution team will review the matter. "
            "If eligible, any applicable amount will be returned through official channels as per our policy. "
            "We will contact you through our official support channels within 24-48 hours with an update."
        ),
        CaseType.payment_failed: (
            "Dear Customer, we understand your concern about the failed payment. "
            "Our records show the transaction details. Please note that if a payment fails, "
            "any deducted amount is typically auto-reversed within 24-48 hours through official channels. "
            "Our payments team is reviewing your case and will provide an update shortly."
        ),
        CaseType.refund_request: (
            "Dear Customer, thank you for reaching out regarding a refund. "
            "We have received your request and our payments team will review the eligibility of the transaction. "
            "If any amount is eligible, it will be returned through official channels as per our standard procedures. "
            "We will update you through our official support channels within 24-48 hours."
        ),
        CaseType.duplicate_payment: (
            "Dear Customer, we apologize for the inconvenience caused by the duplicate charge. "
            "Our payments team is reviewing the transaction and will process any necessary corrections. "
            "Any eligible amount will be returned through official channels. "
            "We will keep you updated through our official support channels."
        ),
        CaseType.merchant_settlement_delay: (
            "Dear Customer, thank you for reporting the settlement delay. "
            "Our merchant operations team is reviewing the settlement schedule for your account. "
            "We will provide an update on the expected timeline through our official support channels. "
            "We appreciate your patience and understanding."
        ),
        CaseType.agent_cash_in_issue: (
            "Dear Customer, we are sorry for the inconvenience with the agent cash-in. "
            "Our agent operations team is reviewing the transaction logs to verify the details. "
            "We will contact you through our official support channels with an update shortly."
        ),
        CaseType.other: (
            "Dear Customer, thank you for contacting us. "
            "We have received your complaint and our customer support team is reviewing the details. "
            "We will get back to you through our official support channels within 24-48 hours. "
            "Thank you for your patience."
        ),
    }

    return standard_replies.get(
        case_type,
        "Dear Customer, thank you for contacting us. We have received your complaint and will review it promptly. "
        "Our team will contact you through official channels with an update."
    )


def build_reason_codes(
    evidence_verdict: EvidenceVerdict,
    case_type: CaseType,
    severity: Severity,
    human_review_required: bool,
    best_tx: Optional[TransactionHistoryItem],
    match_breakdown: dict,
) -> list[str]:
    """Build a list of reason codes explaining the decision."""
    codes = []

    verdict_map = {
        EvidenceVerdict.consistent: "EVIDENCE_CONSISTENT",
        EvidenceVerdict.inconsistent: "EVIDENCE_INCONSISTENT",
        EvidenceVerdict.insufficient_data: "INSUFFICIENT_DATA",
    }
    codes.append(verdict_map.get(evidence_verdict, "UNKNOWN_VERDICT"))

    codes.append(f"CASE_TYPE_{case_type.value.upper()}")

    if best_tx:
        codes.append(f"TX_STATUS_{best_tx.status.value.upper()}")

    if human_review_required:
        codes.append("HUMAN_REVIEW_REQUIRED")

    if severity in (Severity.high, Severity.critical):
        codes.append("HIGH_SEVERITY")

    return codes
