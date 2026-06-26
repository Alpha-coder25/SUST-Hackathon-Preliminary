"""
QueueStorm Investigator — Pydantic models for request/response schemas.
All field names and enum values match the problem statement exactly (case-sensitive).
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ── Enums ──────────────────────────────────────────────────────────────────────

class Language(str, Enum):
    en = "en"
    bn = "bn"
    mixed = "mixed"


class Channel(str, Enum):
    in_app_chat = "in_app_chat"
    call_center = "call_center"
    email = "email"
    merchant_portal = "merchant_portal"
    field_agent = "field_agent"


class UserType(str, Enum):
    customer = "customer"
    merchant = "merchant"
    agent = "agent"
    unknown = "unknown"


class TransactionType(str, Enum):
    transfer = "transfer"
    payment = "payment"
    cash_in = "cash_in"
    cash_out = "cash_out"
    settlement = "settlement"
    refund = "refund"


class TransactionStatus(str, Enum):
    completed = "completed"
    failed = "failed"
    pending = "pending"
    reversed = "reversed"


class EvidenceVerdict(str, Enum):
    consistent = "consistent"
    inconsistent = "inconsistent"
    insufficient_data = "insufficient_data"


class CaseType(str, Enum):
    wrong_transfer = "wrong_transfer"
    payment_failed = "payment_failed"
    refund_request = "refund_request"
    duplicate_payment = "duplicate_payment"
    merchant_settlement_delay = "merchant_settlement_delay"
    agent_cash_in_issue = "agent_cash_in_issue"
    phishing_or_social_engineering = "phishing_or_social_engineering"
    other = "other"


class Severity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class Department(str, Enum):
    customer_support = "customer_support"
    dispute_resolution = "dispute_resolution"
    payments_ops = "payments_ops"
    merchant_operations = "merchant_operations"
    agent_operations = "agent_operations"
    fraud_risk = "fraud_risk"


# ── Request Models ─────────────────────────────────────────────────────────────

class TransactionHistoryItem(BaseModel):
    transaction_id: str
    timestamp: str  # ISO8601
    type: TransactionType
    amount: float
    counterparty: str
    status: TransactionStatus


class AnalyzeTicketRequest(BaseModel):
    ticket_id: str = Field(..., min_length=1, max_length=256)
    complaint: str = Field(..., min_length=1, max_length=10000)
    language: Optional[Language] = None
    channel: Optional[Channel] = None
    user_type: Optional[UserType] = None
    campaign_context: Optional[str] = Field(None, max_length=500)
    transaction_history: Optional[list[TransactionHistoryItem]] = None
    metadata: Optional[dict] = None

    @field_validator("complaint")
    @classmethod
    def complaint_not_empty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("complaint must not be empty or whitespace-only")
        return v

    @field_validator("transaction_history")
    @classmethod
    def validate_transaction_amounts(cls, v: Optional[list[TransactionHistoryItem]]) -> Optional[list[TransactionHistoryItem]]:
        if v is not None:
            for item in v:
                if item.amount < 0:
                    raise ValueError(f"transaction amount cannot be negative for {item.transaction_id}")
        return v


# ── Response Models ────────────────────────────────────────────────────────────

class AnalyzeTicketResponse(BaseModel):
    ticket_id: str
    relevant_transaction_id: Optional[str]
    evidence_verdict: EvidenceVerdict
    case_type: CaseType
    severity: Severity
    department: Department
    agent_summary: str
    recommended_next_action: str
    customer_reply: str
    human_review_required: bool
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    reason_codes: Optional[list[str]] = None


class HealthResponse(BaseModel):
    status: str = "ok"


# ── Error Response ─────────────────────────────────────────────────────────────

class ErrorResponse(BaseModel):
    detail: str
    error_code: Optional[str] = None
