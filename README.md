# QueueStorm Investigator — Codex Team

> **SUST CSE Carnival 2026 · Codex Community Hackathon · Online Preliminary**
> A fintech support-ops ticket investigation API service built in 4.5 hours.

---

## Table of Contents

- [Overview](#overview)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Quick Start](#quick-start)
- [Setup Methods](#setup-methods)
  - [1. Direct Python](#1-direct-python)
  - [2. Setup Script (setup.sh)](#2-setup-script-setupsh)
  - [3. Docker](#3-docker)
  - [4. Docker Compose (recommended)](#4-docker-compose-recommended)
- [API Documentation](#api-documentation)
  - [GET /health](#get-health)
  - [POST /analyze-ticket](#post-analyze-ticket)
- [Evidence Engine](#evidence-engine)
- [Safety Layer](#safety-layer)
- [Monitoring Stack](#monitoring-stack)
- [Testing](#testing)
- [MODELS / AI Approach](#models--ai-approach)
- [Environment Variables](#environment-variables)
- [Sample Request & Response](#sample-request--response)
- [Known Limitations](#known-limitations)
- [Security & Compliance](#security--compliance)

---

## Overview

QueueStorm Investigator is a **REST API service** that automatically investigates fintech customer support tickets. It accepts a customer complaint plus their transaction history, then:

1. **Parses** the complaint to extract amount, counterparty, transaction type, and time references
2. **Matches** the complaint against transaction history using a 4-dimensional weighted scoring algorithm
3. **Determines** an evidence verdict (`consistent`, `inconsistent`, or `insufficient_data`)
4. **Classifies** the issue into 1 of 8 case types with appropriate severity and department routing
5. **Generates** a safe, policy-compliant customer reply — no PIN/OTP requests, no refund promises
6. **Flags** cases requiring human review (phishing, high-value, inconsistent evidence)

**Key differentiator:** Pure deterministic rule-based engine — no external LLM API calls. Zero cost, zero latency, fully auditable.

---

## Tech Stack

| Component | Technology | Why Chosen |
|-----------|-----------|------------|
| **Language** | Python 3.11+ | Wide ecosystem, strong typing support |
| **Web Framework** | FastAPI 0.115 | Auto OpenAPI docs, async, Pydantic integration |
| **Validation** | Pydantic v2 | Strict schema enforcement, custom validators |
| **Server** | Uvicorn 0.30 | High-performance ASGI server |
| **AI/Logic** | Pure rule-based (regex + scoring) | Deterministic, zero cost, no API dependency |
| **Safety** | Custom regex layer | Hard-coded rules prevent safety violations |
| **Metrics (optional)** | Prometheus FastAPI Instrumentator | Exposes `/metrics` for Prometheus scraping |
| **Container** | Docker / Docker Compose | Multi-stage build, under 200MB final image |

---

## Project Structure

```
.
├── main.py                 # FastAPI application entry point (routes, error handlers)
├── models.py               # Pydantic models (request/response schemas, enums)
├── evidence_engine.py      # Core reasoning engine (parsing, matching, classification)
├── safety_layer.py         # Safety checks (sensitive info, refund promises, injection)
├── test_runner.py          # Automated test suite (loads sample_cases.json)
│
├── requirements.txt        # Python dependencies
├── Dockerfile              # Multi-stage Docker build
├── docker-compose.yml      # Docker Compose (API + Prometheus + Grafana)
├── .env.example            # Environment variable template
├── .dockerignore           # Docker build context exclusions
├── setup.sh                # Auto-setup script (venv + deps + run)
│
├── sample_cases.json       # 10 sample test cases with expected outputs
├── sample_output.json      # Full sample response for TKT-001
│
├── prometheus/
│   └── prometheus.yml      # Prometheus scrape configuration
│
├── grafana/
│   ├── datasources/
│   │   └── datasource.yml  # Prometheus datasource provisioning
│   └── dashboards/
│       ├── dashboards.yml  # Dashboard auto-loading config
│       └── queuestorm_overview.json  # Pre-built monitoring dashboard
│
└── video_script_technical_specs.txt  # Video walkthrough script (12-15 min)
```

---

## Quick Start

### Prerequisites

- **Python 3.11+** (recommended) or Python 3.9+
- **Docker** (optional, for containerized deployment)
- **Git** (to clone the repository)

### 30-Second Test

```bash
# Install and run in one command
pip install -r requirements.txt && uvicorn main:app --host 0.0.0.0 --port 8000

# In another terminal, test it
curl http://localhost:8000/health
# → {"status":"ok"}
```

---

## Setup Methods

### 1. Direct Python

```bash
# Clone the repository
git clone <repo-url>
cd <project-directory>

# (Recommended) Create a virtual environment
python -m venv .venv
source .venv/bin/activate          # Linux/macOS
# .venv\Scripts\activate           # Windows

# Install dependencies
pip install -r requirements.txt

# (Optional) Create .env from template
cp .env.example .env

# Start the server
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

The API will be available at **http://localhost:8000**.

---

### 2. Setup Script (setup.sh)

The `setup.sh` script handles everything automatically: checks Python version, creates a virtual environment, installs dependencies, and starts the server.

```bash
# Make executable (if needed)
chmod +x setup.sh

# Install deps & start server
./setup.sh

# Install deps, start server & run tests
./setup.sh --test

# Show help
./setup.sh --help
```

**What the script does:**
1. Checks for Python 3.11+ (warns but continues with older versions)
2. Creates a virtual environment at `.venv/` (if not exists)
3. Installs all dependencies from `requirements.txt`
4. Creates `.env` from `.env.example` (if not exists)
5. Starts the API server on `0.0.0.0:8000`
6. Waits up to 30 seconds for the server to become healthy
7. With `--test`, runs the full test suite after startup

---

### 3. Docker

```bash
# Build the image (~200MB, multi-stage)
docker build -t queuestorm-investigator:latest .

# Run the container
docker run -d \
  --name queuestorm-api \
  -p 8000:8000 \
  --restart unless-stopped \
  queuestorm-investigator:latest

# Check health
curl http://localhost:8000/health
```

**Note:** The Docker image uses a non-root user (`appuser`) for security. Health check is built in — the container reports healthy within 60s of cold start.

---

### 4. Docker Compose (recommended)

The `docker-compose.yml` orchestrates the full stack with optional monitoring.

```bash
# Start just the API server
docker compose up -d

# Start the full stack with Prometheus + Grafana monitoring
docker compose --profile monitoring up -d

# View logs
docker compose logs -f queuestorm-api

# Stop everything
docker compose down

# Stop and remove volumes (wipes Prometheus/Grafana data)
docker compose down -v
```

**Service ports:**

| Service | Default Port | Notes |
|---------|-------------|-------|
| QueueStorm API | `8000` | Main API — configure with `API_PORT=9000 docker compose up -d` |
| Prometheus | `9090` | Only with `--profile monitoring` |
| Grafana | `3000` | Login: `admin`/`admin` (configure with env vars) |

**Monitoring access (when profile is active):**
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000 (Dashboard: "QueueStorm Investigator — API Overview")

---

## API Documentation

### GET /health

Returns the service health status.

**Response:**
```json
{
  "status": "ok"
}
```

**Status codes:** `200 OK`

---

### POST /analyze-ticket

Analyzes a customer support ticket against transaction history.

**Request Schema:**

| Field | Type | Required | Default | Constraints |
|-------|------|----------|---------|-------------|
| `ticket_id` | string | ✅ | — | 1-256 characters |
| `complaint` | string | ✅ | — | 1-10,000 characters |
| `language` | enum | ❌ | — | `en`, `bn`, `mixed` |
| `channel` | enum | ❌ | — | `in_app_chat`, `call_center`, `email`, `merchant_portal`, `field_agent` |
| `user_type` | enum | ❌ | — | `customer`, `merchant`, `agent`, `unknown` |
| `campaign_context` | string | ❌ | — | Max 500 characters |
| `transaction_history` | array | ❌ | `[]` | Array of transaction objects (see below) |
| `metadata` | object | ❌ | — | Free-form key-value pairs |

**Transaction History Item:**

| Field | Type | Constraints |
|-------|------|-------------|
| `transaction_id` | string | Required |
| `timestamp` | string | ISO8601 format (e.g., `2026-06-25T14:30:00Z`) |
| `type` | enum | `transfer`, `payment`, `cash_in`, `cash_out`, `settlement`, `refund` |
| `amount` | float | Must be >= 0 |
| `counterparty` | string | Phone number, merchant ID, or account identifier |
| `status` | enum | `completed`, `failed`, `pending`, `reversed` |

**Response Schema:**

| Field | Type | Notes |
|-------|------|-------|
| `ticket_id` | string | Echoed from request |
| `relevant_transaction_id` | string or null | Best-matching transaction, or `null` if none found |
| `evidence_verdict` | enum | `consistent`, `inconsistent`, `insufficient_data` |
| `case_type` | enum | See case types below |
| `severity` | enum | `low`, `medium`, `high`, `critical` |
| `department` | enum | See departments below |
| `agent_summary` | string | Structured multi-line summary for support agents |
| `recommended_next_action` | string | Actionable next steps for the support team |
| `customer_reply` | string | Safety-checked response for the customer |
| `human_review_required` | bool | `true` if manual review is needed |
| `confidence` | float or null | 0.0 to 1.0 (optional) |
| `reason_codes` | array of strings | Decision reason codes (optional) |

**Case Types:**

| Case Type | Description | Default Department |
|-----------|-------------|-------------------|
| `wrong_transfer` | Sent money to wrong recipient | dispute_resolution |
| `payment_failed` | Payment failed but money deducted | payments_ops |
| `refund_request` | Customer requesting a refund | payments_ops |
| `duplicate_payment` | Charged multiple times for same transaction | payments_ops |
| `merchant_settlement_delay` | Merchant payout delayed | merchant_operations |
| `agent_cash_in_issue` | Agent cash-in problem | agent_operations |
| `phishing_or_social_engineering` | Suspected fraud/scam | fraud_risk |
| `other` | Unclassified issue | customer_support |

**Error Responses:**

| Scenario | Status Code | Error Code |
|----------|-------------|------------|
| Missing required field (ticket_id, complaint) | `422` | Pydantic validation error |
| Empty or whitespace-only complaint | `422` | `EMPTY_COMPLAINT` |
| Negative transaction amount | `422` | Validation error |
| Complaint exceeds 10,000 characters | `422` | Pydantic string_too_long |
| Malformed JSON | `400` | `VALIDATION_ERROR` |
| Internal server error | `500` | `INTERNAL_ERROR` (no stack trace exposed) |

---

## Evidence Engine

The evidence engine (`evidence_engine.py`) is a **deterministic rule-based system** that operates in 7 steps:

### Step 1: Complaint Parsing

Extracts 4 data points using regex patterns:

- **Amount**: Patterns for `BDT 500`, `500 taka`, `৳500`, `500tk`, Bengali numerals (৫০০)
- **Counterparty**: Bangladeshi phone numbers (01XXXXXXXXX), merchant names, agent IDs — with stop-word filtering
- **Transaction type**: Keywords mapping to 6 types (transfer, payment, cash_in, cash_out, settlement, refund)
- **Time reference**: Relative terms (yesterday, last week), date patterns, and relative time expressions

### Step 2: Transaction Matching

Each transaction in history is scored against the complaint across 4 weighted dimensions:

| Dimension | Weight | Scoring Logic |
|-----------|--------|---------------|
| Amount similarity | **35%** | Exact match = 1.0, proportional ratio for partial matches |
| Counterparty match | **30%** | Exact phone/name = 1.0, partial match = 0.8, no info = 0.5, different = 0.2 |
| Transaction type match | **20%** | Same type = 1.0, different = 0.3, no type extracted = 0.5 |
| Time proximity | **15%** | < 1hr = 1.0, < 24hr = 0.9, < 72hr = 0.7, < 1 week = 0.5, < 30 days = 0.3, older = 0.1 |

### Step 3: Evidence Verdict

- **Score < 0.6** → `insufficient_data`
- **Transaction already reversed** → `inconsistent`
- **Wrong transfer with repeated transfers** → `inconsistent`
- **Claiming non-receipt but completed** → `inconsistent`
- **Claiming duplicate but not found** → `inconsistent`
- **Refund request already reversed** → `inconsistent`
- **Otherwise** → `consistent`

### Step 4: Case Type Classification

Keyword matching in priority order (checked first wins):
1. `phishing_or_social_engineering` (safety priority)
2. `wrong_transfer`
3. `duplicate_payment`
4. `refund_request`
5. `agent_cash_in_issue`
6. `payment_failed`
7. `merchant_settlement_delay`
8. Falls back to transaction type inference
9. Falls further to `other`

### Step 5: Severity

| Amount Range | Severity |
|-------------|----------|
| ≥ 100,000 | `critical` |
| ≥ 50,000 | `high` |
| ≥ 5,000 | `medium` |
| < 5,000 | `low` |

Adjustments: Phishing → `critical`, inconsistent evidence → minimum `medium`, duplicate payments → effective amount doubled.

### Step 6: Department

Derived directly from case type via lookup table (see [Case Types table](#case-types) above).

### Step 7: Human Review

Required if **any** of these conditions is true:
- Case type is `phishing_or_social_engineering`, `wrong_transfer`, or `duplicate_payment`
- Evidence is `inconsistent` or `insufficient_data`
- Amount ≥ 50,000
- Severity is `high` or `critical`
- Transaction status is `pending`

---

## Safety Layer

The safety layer (`safety_layer.py`) runs on every generated response **before** it's returned. It enforces 3 hard rules:

### Rule 1: No Sensitive Information Requests

4 regex patterns detect requests for: PIN, OTP, password, MPIN, passcode, security code, CVV, full card number. Offending text is stripped and replaced with safe alternatives.

### Rule 2: No Refund/Reversal Promises

4 regex patterns detect language confirming or promising refunds, reversals, or unblocks. These are replaced with neutral phrasing:
> "any eligible amount will be returned through official channels"

### Rule 3: No Third-Party Redirection

3 regex patterns detect instructions to contact unofficial third parties. These are replaced with:
> "contact our official support channels"

### Prompt Injection Defense

The complaint text is treated as **untrusted data** — never as instructions. The safety layer checks for 16 injection indicators including:
- `ignore previous instructions`, `ignore all`, `forget your`, `you are not`
- `system prompt`, `you are a`, `act as`, `pretend`, `from now on`
- `override`, `disregard`, `do not follow`, `do not obey`
- `new instructions`, `new rule`, `you must`, `you will`

If any indicator is found: `human_review_required = true` + `PROMPT_INJECTION_DETECTED` reason code appended.

### Phishing Override

If case type is `phishing_or_social_engineering`:
- Forces `human_review_required = true`
- Routes to `fraud_risk` department
- Sends security-focused customer reply (no refund confirmation)

---

## Monitoring Stack

The optional monitoring stack provides real-time observability via **Prometheus** + **Grafana**.

### Enabling Monitoring

```bash
docker compose --profile monitoring up -d
```

### Metrics Endpoint

The API exposes `/metrics` (Prometheus format) when `ENABLE_METRICS=true`. This is auto-enabled in Docker Compose.

### Grafana Dashboard

A pre-built dashboard (`queuestorm_overview.json`) is auto-provisioned with 7 panels:

| Panel | Description |
|-------|-------------|
| **Request Rate** | Requests per second (rate over 5 min) |
| **Request Duration** | p50 / p95 / p99 latency percentiles |
| **Status Code Breakdown** | Pie chart of response status codes |
| **Active Requests** | Current in-flight requests (gauge) |
| **Response Size** | Average response size over time |
| **Health Check** | Service up/down indicator (1 = healthy) |
| **Total Requests** | Cumulative request count |

---

## Testing

### Automated Test Suite

```bash
# Ensure the server is running
python test_runner.py
```

The test runner:
1. Loads 10 sample test cases from `sample_cases.json`
2. Sends each case to `/analyze-ticket`
3. Compares 6 key fields against expected values
4. Validates safety rule compliance in customer replies
5. Reports pass/fail with timing

### Sample Test Cases

| # | Ticket | Scenario | Verdict | Severity |
|---|--------|----------|---------|----------|
| 1 | TKT-001 | Wrong transfer to wrong bKash number | consistent | medium |
| 2 | TKT-002 | Payment failed with money deducted | consistent | low |
| 3 | TKT-003 | Refund request for defective product | consistent | low |
| 4 | TKT-004 | Duplicate payment charged twice | consistent | medium |
| 5 | TKT-005 | Merchant settlement delay | consistent | medium |
| 6 | TKT-006 | Agent cash-in failure | consistent | low |
| 7 | TKT-007 | Phishing / social engineering | insufficient_data | critical |
| 8 | TKT-008 | Claiming non-receipt but completed | inconsistent | medium |
| 9 | TKT-009 | No memory of transaction | insufficient_data | low |
| 10 | TKT-010 | Bangla complaint (wrong transfer) | consistent | low |

### Edge Case Validation

Additional tests confirm:
- Prompt injection detection → `human_review_required: true` + `PROMPT_INJECTION_DETECTED`
- Empty complaint → HTTP 422
- Missing required fields → HTTP 422
- Negative transaction amounts → HTTP 422
- No transaction history → `insufficient_data` + human review flagged
- Health check → HTTP 200 `{"status":"ok"}`

All tests pass with **average response time < 10ms**.

---

## MODELS / AI Approach

| Model/Logic | Where It Runs | Why Chosen |
|-------------|---------------|------------|
| Rule-based amount/counterparty/time matcher | Locally, no external call | Deterministic, zero cost, fast, no API dependency |
| Keyword-based case_type classifier | Locally, no external call | Simple, predictable, matches taxonomy tables exactly |
| Weighted scoring algorithm (4 dimensions) | Locally, no external call | Transparent, auditable scoring with configurable weights |
| Safety regex layer | Locally, no external call | Hard-coded rules prevent safety violations at the output level |
| Template-based response generator | Locally, no external call | Guaranteed safe phrasing, no prompt injection risk |

**Why not an LLM?** The problem statement explicitly allows rule-based systems. A deterministic approach eliminates:
- API costs and rate limits
- Latency from external calls
- Prompt injection vulnerabilities
- Non-deterministic behavior (same input = same output every time)
- Dependency on third-party API availability

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `8000` | Server port |
| `LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `ENABLE_METRICS` | `false` | Enable Prometheus `/metrics` endpoint (`true`/`false`) |

**Optional (for monitoring):**

| Variable | Default | Description |
|----------|---------|-------------|
| `API_PORT` | `8000` | Docker API port mapping |
| `PROMETHEUS_PORT` | `9090` | Docker Prometheus port mapping |
| `GRAFANA_PORT` | `3000` | Docker Grafana port mapping |
| `GRAFANA_ADMIN_USER` | `admin` | Grafana admin username |
| `GRAFANA_ADMIN_PASSWORD` | `admin` | Grafana admin password |

Copy `.env.example` to `.env` and customize as needed. No API keys are required.

---

## Sample Request & Response

### Request

```json
{
  "ticket_id": "TKT-001",
  "complaint": "I sent BDT 5000 to the wrong bKash number yesterday. The number was 01712345678 but I accidentally sent it to 01712345679. Please help me get my money back.",
  "language": "en",
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

### Response

```json
{
  "ticket_id": "TKT-001",
  "relevant_transaction_id": "TXN-001-A",
  "evidence_verdict": "consistent",
  "case_type": "wrong_transfer",
  "severity": "medium",
  "department": "dispute_resolution",
  "agent_summary": "Ticket TKT-001 — Wrong Transfer\nChannel: in_app_chat | User: customer | Severity: medium | Dept: dispute_resolution\nEvidence: Consistent\nMatched Tx: TXN-001-A | Amount: 5000 | Type: transfer | Status: completed | Counterparty: 01712345679 | Score: 0.9\nComplaint excerpt: I sent BDT 5000 to the wrong bKash number yesterday...",
  "recommended_next_action": "Escalate to dispute resolution team for manual review and trace the transaction to the recipient. Initiate fund recovery process if applicable.",
  "customer_reply": "Dear Customer, we are sorry to hear about the wrong transfer. We have noted the details and our dispute resolution team will review the matter. If eligible, any applicable amount will be returned through official channels as per our policy. We will contact you through our official support channels within 24-48 hours with an update.",
  "human_review_required": true,
  "confidence": 0.93,
  "reason_codes": [
    "EVIDENCE_CONSISTENT",
    "CASE_TYPE_WRONG_TRANSFER",
    "TX_STATUS_COMPLETED",
    "HUMAN_REVIEW_REQUIRED"
  ]
}
```

See `sample_output.json` for a complete reference.

---

## Known Limitations

- **Amount matching:** Relies on regex extraction; may miss amounts written in certain formats or complex Bengali numeral representations
- **Bangla support:** Basic Bangla text is supported via regex keywords, but complex Bangla/Banglish mixed complaints may have reduced matching accuracy
- **Time proximity:** Uses transaction timestamp recency as a proxy; doesn't parse complex time references like "around 3pm on the 15th"
- **Case type classification:** Keyword-based; may misclassify edge cases with overlapping keywords (e.g., a complaint containing both "refund" and "wrong number")
- **Customer replies:** Template-based; less nuanced than an LLM-generated reply but guaranteed deterministic and safe
- **Counterparty extraction:** Stop-word filtering may miss valid counterparty names that happen to match generic words

---

## Security & Compliance

- ✅ **No secrets in repository** — Only `.env.example` with variable names, no real values
- ✅ **No PII logging** — Logging omits full PII, secrets, and API keys
- ✅ **Input validation** — Strict Pydantic validation with length limits (10,000 chars for complaint, 256 for ticket_id)
- ✅ **Safe error handling** — Generic error messages, no stack traces in production responses
- ✅ **Non-root container** — Docker image runs as `appuser` (UID 1001)
- ✅ **Prompt injection defense** — Complaint treated as data, never as instructions
- ✅ **No sensitive info requests** — Safety layer strips PIN/OTP/password requests
- ✅ **No unauthorized refund promises** — All refund language neutralized
- ✅ **No third-party redirects** — All external links replaced with official channels
- ✅ **No real customer data** — All test data is synthetic
- ✅ **Synthetic data only** — All sample cases use fictional transactions and complaints

---

## Confirmations

- ✅ No real customer data used (synthetic only)
- ✅ No secrets committed to this repository
- ✅ All dependencies listed in `requirements.txt`
- ✅ Docker image < 200MB, no GPU required
- ✅ `/health` endpoint responds within 60s of cold start
- ✅ All 10 public sample cases pass
- ✅ Safety rules verified across all responses

---

*Built for SUST CSE Carnival 2026 — Codex Community Hackathon Preliminary Round*
