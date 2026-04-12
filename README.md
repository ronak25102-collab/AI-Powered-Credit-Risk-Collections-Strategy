# AI-Powered Credit Risk & Collections Strategy

<div align="center">

![Landing Page](./assets/landing-page.png)

**End-to-end delinquency prediction, borrower scoring, and operations-ready collections workflow — powered by machine learning and explainable AI.**

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React_18-61DAFB?style=flat-square&logo=react&logoColor=black)](https://reactjs.org)
[![scikit-learn](https://img.shields.io/badge/scikit--learn-F7931E?style=flat-square&logo=scikitlearn&logoColor=white)](https://scikit-learn.org)
[![Vite](https://img.shields.io/badge/Vite-646CFF?style=flat-square&logo=vite&logoColor=white)](https://vitejs.dev)

</div>

---

## 📸 Screenshots

<details>
<summary><strong>Dashboard — Collections Command Center</strong></summary>

![Dashboard](./assets/dashboard.png)

</details>

<details>
<summary><strong>Risk Queue — Sortable, Filterable Operations Table</strong></summary>

![Risk Queue](./assets/risk-queue.png)

</details>

<details>
<summary><strong>Prediction Studio — Borrower Risk Estimator + What-If Simulator</strong></summary>

![Prediction Studio](./assets/prediction-studio.png)

</details>

---

## Table of Contents

- [What This Project Does](#what-this-project-does)
- [Key Features](#key-features)
- [System Architecture](#system-architecture)
- [Technology Stack](#technology-stack)
- [Data Pipeline and Schema Logic](#data-pipeline-and-schema-logic)
- [Model Training and Scoring Logic](#model-training-and-scoring-logic)
- [Portfolio Workflow and Automation Engine](#portfolio-workflow-and-automation-engine)
- [API Reference](#api-reference)
- [Frontend Experience and UX](#frontend-experience-and-ux)
- [Security and RBAC](#security-and-rbac)
- [Run Locally](#run-locally)
- [Project Structure](#project-structure)
- [Troubleshooting](#troubleshooting)

---

## What This Project Does

A **production-grade** credit risk analytics platform that:

- Ingests financial tabular data from CSV/XLSX/XLS with schema normalization
- Performs EDA summaries and interaction diagnostics
- Trains **3 ML classifiers** and auto-selects the best candidate model
- Calibrates raw model probability with business-risk logic and stress-aware overrides
- Exposes a **FastAPI backend** for scoring, portfolio operations, monitoring, and governance
- Provides a **React dashboard** for queue handling, scenario simulation, and model insights

### Core Outcomes

| Capability | Description |
|---|---|
| 🎯 **Risk Scoring** | Probability + category (low/medium/high) |
| 🔍 **Explainability** | Driver impacts + human-readable explanations |
| 📋 **Collections Strategy** | Automated recommendations (priority, next steps) |
| ⚙️ **Workflow Operations** | Assign, status updates, snooze, follow-up scheduling, notes |
| 🤖 **Auto-Orchestration** | Rule-based automation with dry-run preview |
| 📊 **Model Monitoring** | Drift detection, override rate tracking, performance history |

---

## Key Features

### Landing Page
- 🎬 **Animated particle background** with peach-tone theme
- ⌨️ **Typing effect** on hero subtitle
- 📈 **Animated count-up statistics** (3 ML Models, 95% Accuracy, 5000+ Borrowers)
- 🎨 **Scroll-reveal animations** on feature cards

### Dashboard
- 📊 **KPI cards with sparkline mini-charts** — clickable, linking to filtered views
- 🔄 **Refresh button** with spin animation and toast feedback
- 📉 **Risk Pattern Trend chart** with decile distribution
- 🚨 **Alert Center** with severity-based badges
- 👤 **Owner workload** distribution bars

### Risk Queue
- 🔀 **Sortable table columns** — click any header to sort asc/desc
- 🔍 **Search, filter, and pagination** with URL persistence
- ⚡ **Inline workflow actions** — assign, contact, snooze in one click
- 📜 **Account timeline** with full event history and case notes
- 📤 **CSV export** and **batch scoring upload**
- 🤖 **Auto-orchestration** with preview/apply modes

### Prediction Studio
- 🧮 **Borrower Risk Estimator** with unit-aware inputs
- 🔮 **What-If Simulator** — stress-test income shifts, loan changes, missed payments
- 💾 **Save/load borrower profiles** (localStorage)
- 📊 **Risk gauge** with conic gradient visualization
- 🏷️ **Top risk drivers** with directional impact bars

### Model Insights
- 🏆 **Champion-Challenger governance** with one-click promotion
- 📉 **Drift Watch** — feature-level shift against training baseline
- 🔗 **Feature Correlation Map** (Chart.js)
- 📈 **Monitoring History** snapshots

### Global UX
- 🔔 **Toast notification system** — success/error/info with auto-dismiss
- 📊 **Top progress bar** — thin animated bar during API calls
- ✨ **Page transitions** — fade+slide between tabs
- ⌨️ **Keyboard shortcuts** — `Ctrl+K` (Quick Find), `Ctrl+Shift+N` (New Assessment)
- 💀 **Skeleton loaders** — structured loading states on all pages
- 📱 **Mobile responsive** — hamburger menu + slide-out sidebar
- 🛡️ **Error Boundary** — themed crash recovery fallback
- 🚫 **404 Page** — themed "Page Not Found" with navigation
- 🔗 **Open Graph meta tags** — rich LinkedIn/Twitter social previews
- ✦ **Custom SVG favicon** matching brand identity

---

## System Architecture

```
┌─────────────┐     X-User-Role      ┌──────────────────┐
│   React 18  │ ──────────────────►  │   FastAPI Server  │
│   (Vite)    │ ◄──────────────────  │   (Python 3.10+)  │
└─────────────┘    JSON responses    └──────────────────┘
                                            │
                                     ┌──────┴──────┐
                                     │  scikit-learn │
                                     │  Model Engine │
                                     └─────────────┘
```

**Startup Flow:**
1. Resolve dataset path (or fallback to synthetic generation)
2. Normalize and sanitize schema
3. Impute missing values
4. Train models and compute insights
5. Build scored portfolio records
6. Rehydrate persisted workflow state

---

## Technology Stack

### Backend
| Technology | Purpose |
|---|---|
| Python 3.10+ | Runtime |
| FastAPI | REST API framework |
| Pydantic v2 | Request/response validation |
| scikit-learn | Model training (LR, RF, GBM) |
| Pandas / NumPy | Data processing |
| joblib | Model serialization |
| openpyxl | Excel file support |

### Frontend
| Technology | Purpose |
|---|---|
| React 18 | UI framework |
| React Router v6 | Client-side routing |
| Vite | Build tool + HMR |
| Tailwind CSS | Utility-first styling |
| Chart.js | Data visualizations |
| Custom CSS | Glassmorphism, animations, toasts |

---

## Data Pipeline and Schema Logic

**Canonical feature schema:**

| Field | Type | Range | Description |
|---|---|---|---|
| income | float | 0–1,000,000 | Annualized income |
| credit_score | float/int | 300–850 | Credit score signal |
| credit_utilization | float | 0.0–1.0 | Credit utilization ratio |
| debt_to_income_ratio | float | 0.0–1.5 | Debt-to-income ratio |
| missed_payments | float/int | 0–60 | Missed payment count |
| repayment_history | float | 0.0–1.0 | On-time repayment ratio |
| delinquent (target) | int | 0 or 1 | Delinquency label |

**Optional features:** `age`, `loan_amount`, `years_experience`

**Normalization capabilities:**
- Alias-based column mapping (e.g. `Credit_Score`, `LoanAmount`)
- Approval-style target inversion for delinquency semantics
- Auto-derivation of missing fields (DTI/utilization from income + loan amount)
- Conservative proxy synthesis for missing behavioral fields

---

## Model Training and Scoring Logic

**Candidate models:** Logistic Regression · Random Forest · Gradient Boosting

**Selection strategy:**
- Train/validation/test split with fixed random seed
- Validation threshold sweep (0.30–0.70)
- Best model chosen by validation accuracy + F1, with ROC AUC as tiebreaker

**Engineered features:**
`utilization_dti_interaction` · `payment_stress_index` · `credit_pressure` · `income_buffer` · `credit_income_pressure` · `loan_to_income_ratio_raw` · `experience_credit_buffer`

**Scoring outputs:**
- `risk_probability`, `risk_score`, `risk_category`
- `model_probability`, `business_risk_index`
- `override_applied`, `override_reason`
- `top_drivers` (SHAP-style directional impacts)
- `collections_strategy` (strategy + priority + next steps)
- `explanation` (plain-language risk summary)

---

## Portfolio Workflow and Automation Engine

**Manual workflow actions:**
- Assign/unassign owner
- Update status (`new` → `assigned` → `in_progress` → `contacted` → `promise_to_pay` → `snoozed` → `escalated` → `resolved`)
- Schedule follow-up dates
- Snooze until date
- Add case notes with timeline tracking

**Auto-orchestration policies** (`POST /portfolio/workflow/auto`):

| Risk Profile | Action |
|---|---|
| High + severe indicators | Escalate + 24h follow-up |
| High + standard | Move to in_progress + 48h follow-up |
| Medium risk | Assign + 5-day follow-up |
| Low + inactive | Snooze for 14 days |

Supports `dry_run` preview mode before applying changes.

---

## API Reference

| Endpoint | Method | Permission | Description |
|---|---|---|---|
| `/health` | GET | public | Health check |
| `/insights` | GET | read | Dataset + model analytics |
| `/portfolio` | GET | read | Paginated portfolio with filters |
| `/portfolio/{id}` | GET | read | Single account with timeline |
| `/portfolio/{id}/workflow` | PATCH | workflow_update | Update case workflow |
| `/portfolio/workflow/auto` | POST | workflow_update | Auto-orchestration |
| `/portfolio/batch-score` | POST | batch_score | Batch CSV/Excel scoring |
| `/predict` | POST | predict | Single borrower risk prediction |
| `/alerts` | GET | read | Operational alerts |
| `/model-monitoring` | GET | read | Drift + override metrics |
| `/model-versions` | GET | read | Model registry |
| `/model-versions/promote` | POST | model_promote | Champion-challenger promotion |

---

## Frontend Experience and UX

| Route | Page | Purpose |
|---|---|---|
| `/` | Landing Page | Animated hero with particle background and CTAs |
| `/dashboard` | Dashboard | KPI overview, trend chart, alerts, action queue |
| `/risk-queue` | Risk Queue | Sortable table, workflow actions, timeline, batch scoring |
| `/prediction` | Prediction Studio | Single-case scoring, what-if simulation, saved profiles |
| `/insights` | Model Insights | Monitoring, drift, candidate comparison, governance |

**Interactive UX features:**
- Toast notifications on every mutation (assign, score, promote)
- Top progress bar during API calls
- Smooth page transitions between tabs
- Keyboard shortcuts: `Ctrl+K` (Quick Find) · `Ctrl+Shift+N` (New Assessment)
- Skeleton loaders with card-shaped placeholders
- Mobile hamburger menu with slide-out sidebar overlay

---

## Security and RBAC

| Role | Permissions |
|---|---|
| `analyst` | read, predict |
| `agent` | read, predict, workflow_update, batch_score |
| `manager` | All agent permissions + model_promote |

Role is sent via `X-User-Role` header. Unknown roles or disallowed actions return HTTP 403.

---

## Run Locally

### Prerequisites

- Python 3.10+
- Node.js 18+

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Optional dataset override:
```bash
set CREDIT_RISK_DATASET=..\loan_risk_prediction_dataset.csv
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

| Service | URL |
|---|---|
| Frontend | `http://localhost:5173` |
| Backend | `http://127.0.0.1:8000` |
| API Docs | `http://127.0.0.1:8000/docs` |

Optional API target override:
```bash
set VITE_API_URL=http://127.0.0.1:8000
```

---

## Project Structure

```
├── assets/                         # README screenshots
├── backend/
│   ├── main.py                     # FastAPI endpoints, RBAC, workflow engine
│   ├── model.py                    # Training, calibration, explainability
│   ├── data_processing.py          # Dataset loading, schema mapping, EDA
│   └── requirements.txt
├── frontend/
│   ├── public/
│   │   ├── favicon.svg             # Custom brand favicon (✦)
│   │   └── og-image.png            # Social preview image
│   ├── src/
│   │   ├── api.js                  # API client, role header, timeout
│   │   ├── App.jsx                 # Router shell, page transitions
│   │   ├── main.jsx                # Entry point, ErrorBoundary, ToastProvider
│   │   ├── index.css               # Full design system + animations
│   │   ├── components/
│   │   │   ├── NavBar.jsx          # Sidebar, keyboard shortcuts, mobile menu
│   │   │   ├── GlassCard.jsx       # Glassmorphism card wrapper
│   │   │   ├── KpiCard.jsx         # Dashboard KPI card with sparkline support
│   │   │   ├── ToastProvider.jsx   # Global toast notification system
│   │   │   ├── TopProgressBar.jsx  # Loading progress bar
│   │   │   ├── Sparkline.jsx       # Inline SVG mini-chart
│   │   │   ├── AnimatedCounter.jsx # Count-up animation on scroll
│   │   │   ├── TypingEffect.jsx    # Character-by-character typing
│   │   │   ├── ParticleBackground.jsx # Canvas particle animation
│   │   │   ├── SkeletonLoader.jsx  # Structured loading placeholder
│   │   │   └── ErrorBoundary.jsx   # React error boundary fallback
│   │   ├── pages/
│   │   │   ├── LandingPage.jsx     # Animated landing + hero section
│   │   │   ├── Dashboard.jsx       # KPIs, trend, alerts, action queue
│   │   │   ├── RiskQueue.jsx       # Sortable table, workflow, timeline
│   │   │   ├── RiskPrediction.jsx  # Risk estimator + what-if simulator
│   │   │   ├── Insights.jsx        # Monitoring, drift, governance
│   │   │   └── NotFound.jsx        # Themed 404 page
│   │   └── charts/                 # Chart.js adapters
│   └── index.html                  # OG meta tags + Twitter cards
└── README.md
```

---

## Troubleshooting

| Issue | Solution |
|---|---|
| Queue feels slow | Confirm frontend calls `/portfolio` with `summary_mode=light` |
| Auto-orchestration shows 0 updates | Check `already_orchestrated` counter — scope may be aligned |
| Prediction fails with ratio errors | Provide `credit_utilization` + `debt_to_income_ratio`, or `loan_amount` for auto-derivation |
| Dataset load issues | Verify target file exists; synthetic fallback is used automatically |
| PowerShell blocks npm | Use `npm.cmd run dev` instead |

---

## Notes and Extensibility

- Modular architecture designed for workshop and demo scenarios
- Can be extended with: database persistence, scheduled retraining, model registry backing store, async task queues
- Workflow state file (`backend/portfolio_workflow_state.json`) is operational state, not source code
- Social preview image and meta tags are ready for LinkedIn/Twitter sharing

---

<div align="center">

**Built with ❤️ using React, FastAPI, and scikit-learn**

</div>
