# AI-Powered Credit Risk & Collections Strategy

A full-stack financial analytics application that predicts customer delinquency risk and surfaces business-ready insights for collections teams.

## Project Overview

This project simulates a real-world credit analytics workflow:

- Loads a credit-risk dataset from CSV if available, with automatic synthetic fallback for demos.
- Automatically detects common dataset files in the project root, including `loan_risk_prediction_dataset.csv`.
- Performs EDA with median imputation, statistical profiling, and feature-correlation insights.
- Trains and validates multiple classifiers (Logistic Regression, Random Forest, Gradient Boosting) with a validation-tuned decision threshold, then keeps the best model by holdout performance.
- Exposes a FastAPI backend for analytics insights, portfolio workflow operations, and real-time risk prediction.
- Delivers a modern React + Tailwind dashboard with workflow-first queue actions, case timeline tracking, and interactive scenario simulation.

## Tech Stack

- Frontend: React (Vite), Tailwind CSS, Chart.js
- Backend: Python, FastAPI
- Data Processing: Pandas, NumPy
- Machine Learning: scikit-learn (Logistic Regression, Random Forest, Gradient Boosting + StandardScaler)

## Key Insights

- Behavioral features dominate risk prediction over static financial metrics.
- High debt-to-income ratio and missed payments jointly indicate elevated delinquency risk.
- Delinquency intervention should prioritize payment behavior signals for early collections action.

## Features

### Data Analysis (EDA)

- Missing value handling with median imputation.
- Statistical summaries for all required variables:
  - income
  - credit_score
  - credit_utilization
  - debt_to_income_ratio
  - missed_payments
  - repayment_history
- Correlation-based feature importance and interaction-based logic insights.

### Model Implementation

- Train, validation, and holdout-test split with reproducible random seed.
- StandardScaler preprocessing plus engineered interaction features.
- Candidate-model training (Logistic Regression, Random Forest, Gradient Boosting) with best-model selection by validation metrics.
- Decision threshold tuning on validation data before final holdout scoring.
- Adaptive low/medium/high banding using score quantiles to avoid one-sided portfolio categorization when class balance is skewed.
- Risk output as probability and category:
  - low: below learned low-risk quantile threshold
  - medium: between learned low/high thresholds
  - high: above learned high-risk quantile threshold

### Rule-Based Edge Logic

- If missed_payments > 5, risk category is overridden to high.
- Severe debt-stress patterns are also overridden to high (for example DTI >= 100% with low repayment history).
- Stress-aware calibration handles model/business divergence for visibly risky profiles.
- For approval-style loan datasets missing behavioral fields, repayment-behavior proxies are derived conservatively to reduce synthetic over-penalization.
- Explanation output includes business-readable reasoning, for example:
  - "High risk due to high missed payments and DTI pressure."

### API Endpoints

- `GET /insights`
  - Returns EDA summaries, feature relationships, model performance, and dashboard chart payloads.
- `GET /portfolio`
  - Returns portfolio records with filtering (`risk`, `status`, `search`, `limit`) and operational summary (risk counts, workflow counts, due follow-ups).
- `GET /portfolio/{account_id}`
  - Returns full account-level detail, including timeline activity events.
- `PATCH /portfolio/{account_id}/workflow`
  - Updates workflow state (owner assignment, status, follow-up date, snooze date, and notes).
  - Persists workflow state snapshots in backend storage (`portfolio_workflow_state.json`).
- `POST /portfolio/batch-score`
  - Uploads CSV/XLSX borrower files and returns scored rows with risk band summary.
- `GET /alerts`
  - Returns prioritized operational alerts (unassigned high risk, overdue follow-ups, unresolved payment spikes).
- `GET /model-monitoring`
  - Returns live model monitoring metrics (override rate, drift z-scores, risk share trend history).
- `GET /model-versions`
  - Returns champion/challenger model registry metadata.
- `POST /model-versions/promote`
  - Promotes challenger metadata to champion status for governance workflow simulation.
- `GET /auth/roles`
  - Returns role and permission metadata for RBAC-aware UI behavior.
- `POST /predict`
  - Input: customer profile fields with unit-aware income (`income_period=monthly|annual`).
  - Supports optional `loan_amount` for auto-calculation of utilization and DTI when ratios are omitted.
  - Output: risk score, probability, risk category, override metadata, top drivers, strategy recommendation, and explanation.

## Project Structure

```text
backend/
  main.py
  model.py
  data_processing.py
  requirements.txt

frontend/
  src/
    components/
    pages/
    charts/
```

## Frontend Experience

- White and peach workspace theme with high-contrast operational surfaces.
- Staggered reveal transitions and purpose-built hover interactions.
- Risk Queue supports workflow actions directly in-table:
  - Assign owner
  - Mark contacted
  - Snooze case
  - Change workflow status
- Borrower timeline panel includes:
  - Event history per account
  - Notes capture with timestamps and actor metadata
- Dashboard includes:
  - KPI cards (Accounts Scored, High Risk Share, Avg Credit Score)
  - Operational tracking (due follow-ups and contacted workload)
  - Portfolio risk trend chart
  - Prioritized action queue with owner + workflow state
  - Alert center panel for urgent operational exceptions
- Prediction page includes:
  - Full input form with explicit units (monthly or yearly income)
  - Optional auto-calculation for DTI/utilization from income + loan amount
  - Risk score gauge (0 to 100%)
  - Color-coded risk category and explanation
  - What-if simulator for scenario testing (income shift, loan delta, missed-payment delta, repayment shift)
  - Driver-impact bars and collections strategy recommendation panel
- Insights page includes:
  - Model monitoring diagnostics (override rate, drift watch, historical snapshots)
  - Champion-challenger model governance card with promotion action
- Sidebar includes role switcher (`Analyst`, `Collections Agent`, `Manager`) for RBAC testing.

## How to Run Locally

## 1. Backend Setup

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Optional dataset path via environment variable:

```bash
set CREDIT_RISK_DATASET=..\loan_risk_prediction_dataset.csv
```

You can also point `CREDIT_RISK_DATASET` to `.xlsx` or `.xls` files; the backend automatically maps common column variants (for example `Income`, `Credit_Score`, `Delinquent_Account`) to the model schema.

If you do not set `CREDIT_RISK_DATASET`, the backend now auto-checks common files in this order:

1. `backend/data/credit_risk_dataset.csv`
2. `loan_risk_prediction_dataset.csv` (project root)
3. `Delinquency_prediction_dataset.csv` (project root)

If no dataset file is found, the backend generates synthetic data automatically.

## 2. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Frontend runs on `http://localhost:5173` by default.

If your API runs elsewhere, set:

```bash
VITE_API_URL=http://127.0.0.1:8000
```

RBAC note:

- Frontend sends role using `X-User-Role` header from sidebar selector.
- Endpoint permissions:
  - `analyst`: read + predict
  - `agent`: read + predict + workflow update + batch scoring
  - `manager`: full permissions, including model promotion

## 3. Open the App

- Frontend: `http://localhost:5173`
- Backend docs: `http://127.0.0.1:8000/docs`

## Screenshots

Add screenshots after running the app:

- `screenshots/dashboard-overview.png`
- `screenshots/risk-prediction.png`
- `screenshots/insights-page.png`

## Notes

- Designed for portfolio analytics demos and collections strategy workshops.
- Architecture is modular and can be extended to support model versioning, batch scoring, and database-backed persistence.
