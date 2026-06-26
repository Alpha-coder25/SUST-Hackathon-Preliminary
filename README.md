# QueueStorm Investigator — Codex Team

## Overview
QueueStorm Investigator is a fintech support-ops ticket investigation API service built for the SUST CSE Carnival 2026 Codex Community Hackathon. It accepts customer support tickets (complaints + transaction history), performs deterministic evidence-based reasoning to match complaints to transaction records, classifies case types/departments/severity, and generates safe, policy-compliant customer replies — all without ever asking for PIN/OTP or promising unauthorized refunds.

## Tech Stack
- **Language/framework:** Python 3.11 + FastAPI
- **AI approach:** Pure rule-based (deterministic evidence engine). No external LLM API calls required.
- **Validation:** Pydantic v2 (strict schema enforcement)
- **Safety:** Dedicated safety layer with regex-based violation detection and neutralization

## Setup & Run

```bash
git clone <repo-url>
cd <repo>
pip install -r requirements.txt
cp .env.example .env   # fill in your own keys locally (optional)
uvicorn main:app --host 0.0.0.0 --port 8000
```

## Docker (fallback)

```bash
docker build -t queuestorm-team .
docker run -p 8000:8000 --env-file judging.env queuestorm-team
```

## Live Endpoint
- Base URL: http://localhost:8000 (or your deployed URL)
- GET /health → `{"status": "ok"}`
- POST /analyze-ticket → see schema below

## API Schema

### POST /analyze-ticket — Request

| Field | Type | Required | Notes |
|---|---|---|---|
| ticket_id | string | ✅ | Unique identifier |
| complaint | string | ✅ | Free-text complaint (min 1 char) |
| language | enum | ❌ | `en`, `bn`, or `mixed` |
| channel | enum | ❌ | `in_app_chat`, `call_center`, `email`, `merchant_portal`, `field_agent` |
| user_type | enum | ❌ | `customer`, `merchant`, `agent`, `unknown` |
| campaign_context | string | ❌ | Optional campaign identifier |
| transaction_history | array[object] | ❌ | Array of transaction objects |
| metadata | object | ❌ | Free-form metadata |

### POST /analyze-ticket — Response

| Field | Type | Notes |
|---|---|---|
| ticket_id | string | Echoed from request |
| relevant_transaction_id | string or null | Best-matching transaction ID |
| evidence_verdict | enum | `consistent`, `inconsistent`, `insufficient_data` |
| case_type | enum | `wrong_transfer`, `payment_failed`, `refund_request`, `duplicate_payment`, `merchant_settlement_delay`, `agent_cash_in_issue`, `phishing_or_social_engineering`, `other` |
| severity | enum | `low`, `medium`, `high`, `critical` |
| department | enum | `customer_support`, `dispute_resolution`, `payments_ops`, `merchant_operations`, `agent_operations`, `fraud_risk` |
| agent_summary | string | Structured summary for support agent |
| recommended_next_action | string | Recommended action steps |
| customer_reply | string | Safety-checked customer-facing reply |
| human_review_required | bool | Whether manual review is needed |
| confidence | float (0-1) | Optional confidence score |
| reason_codes | array[string] | Optional decision reason codes |

## MODELS (required section)

| Model/Logic used | Where it runs | Why chosen |
|---|---|---|
| Rule-based amount/counterparty/time matcher | Locally, no external call | Deterministic, zero cost, fast, no API dependency |
| Keyword-based case_type classifier | Locally | Simple, predictable, matches taxonomy tables exactly |
| Safety regex layer | Locally | Hard-coded rules prevent safety violations at the output level |

## AI / Reasoning Approach

**Evidence Engine (deterministic):**
1. **Complaint parsing:** Extract amount (via regex), counterparty (phone numbers, merchant names), transaction type keywords, and time references from the complaint text.
2. **Transaction matching:** Score each transaction in `transaction_history` across four weighted dimensions:
   - Amount similarity (35%) — exact/approximate match
   - Time proximity (15%) — recency of transaction
   - Counterparty match (30%) — phone number, merchant name, or keyword match
   - Type match (20%) — transfer/payment/cash-in etc.
3. **Verdict derivation:** Based on match score and transaction status:
   - `consistent`: complaint is supported by evidence
   - `inconsistent`: history contradicts complaint (e.g., already reversed, repeated transfers, completed transfer claimed as not received)
   - `insufficient_data`: no transaction history or no match found
4. **Classification:** Case type is determined by keyword matching against taxonomy tables; department flows from case type; severity is computed from amount thresholds plus case type adjustments.

**Response Generation:** Template-based replies are selected based on case type, evidence verdict, and human review flags — all pre-written with safety constraints built in.

## Safety Logic

The service enforces three hard safety rules on every generated response:

1. **No OTP/PIN/password requests:** Regex patterns detect any request for sensitive information (PIN, OTP, password, MPIN, passcode, CVV, full card number). Any violating text is removed from the response.
2. **No refund/reversal/unblock promises:** Language that confirms or promises a refund/reversal is replaced with neutral phrasing: *"any eligible amount will be returned through official channels."*
3. **No third-party redirection:** Instructions to contact unofficial third parties are replaced with *"contact our official support channels."*

**Prompt injection defense:** The complaint text is treated as untrusted data — never as instructions to the system. If injection indicators (e.g., "ignore previous instructions", "you are not", "override") are detected in the complaint, `human_review_required` is forced to `true` and a `PROMPT_INJECTION_DETECTED` reason code is added.

**Phishing override:** If case type is `phishing_or_social_engineering`, the service forces `human_review_required = true` and routes to `fraud_risk` department regardless of other factors.

## Sample Request & Response

```json
// Request
{
  "ticket_id": "TKT-001",
  "complaint": "I sent BDT 5000 to the wrong bKash number yesterday. Please help me get my money back.",
  "channel": "in_app_chat",
  "user_type": "customer",
  "transaction_history": [
    {
      "transaction_id": "TXN-001-A",
      "timestamp": "2026-06-25T14:30:00Z",
      "type": "transfer",
      "amount": 5000,
      "counterparty": "01712345679",
      "status": "completed"
    }
  ]
}
```

See `sample_output.json` for the full response.

## Known Limitations
- **Amount matching:** Relies on regex extraction, which may miss amounts written in certain formats or Bangla numerals
- **Bangla support:** Basic Bangla text is supported via regex, but complex Bangla/Banglish mixed complaints may have reduced matching accuracy
- **Time proximity:** Uses transaction timestamp recency as a proxy; doesn't parse complex time references like "around 3pm on the 15th"
- **Case type classification:** Keyword-based; may misclassify edge cases with overlapping keywords
- **Customer replies:** Template-based; less nuanced than an LLM-generated reply but deterministic and safe

## Environment Variables
See `.env.example` for required variable names (no real values committed).

## Confirmations
- ✅ No real customer data used (synthetic only)
- ✅ No secrets committed to this repository
