from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Literal, Optional

import numpy as np
import pandas as pd
from fastapi import FastAPI, File, HTTPException, Query, UploadFile, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from data_processing import (
    FEATURE_COLUMNS,
    OPTIONAL_FEATURE_COLUMNS,
    TARGET_COLUMN,
    _sanitize_dataframe,
    _standardize_schema,
)
from model import CreditRiskModel, initialize_model_system

WORKFLOW_STATE_PATH = Path(__file__).resolve().parent / "portfolio_workflow_state.json"
WORKFLOW_STATUS_VALUES = {
    "new",
    "assigned",
    "in_progress",
    "contacted",
    "promise_to_pay",
    "snoozed",
    "escalated",
    "resolved",
}
AUTO_WORKFLOW_OWNER_POOL = ("Agent Prime", "Agent Nova", "Agent Delta", "Agent Orion")

ROLE_PERMISSIONS: Dict[str, set[str]] = {
    "analyst": {"read", "predict"},
    "agent": {"read", "predict", "workflow_update", "batch_score"},
    "manager": {
        "read",
        "predict",
        "workflow_update",
        "batch_score",
        "model_promote",
    },
}

app = FastAPI(
    title="AI-Powered Credit Risk & Collections Strategy",
    description=(
        "Predict delinquency risk and expose actionable analytics insights for credit collections."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class PredictionRequest(BaseModel):
    income: float = Field(..., gt=0, le=1_000_000)
    income_period: Literal["annual", "monthly"] = "annual"
    credit_score: int = Field(..., ge=300, le=850)
    credit_utilization: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    debt_to_income_ratio: Optional[float] = Field(default=None, ge=0.0, le=1.5)
    missed_payments: int = Field(..., ge=0, le=60)
    repayment_history: float = Field(..., ge=0.0, le=1.0)
    age: Optional[int] = Field(default=None, ge=18, le=100)
    loan_amount: Optional[float] = Field(default=None, ge=0.0, le=2_000_000)
    years_experience: Optional[float] = Field(default=None, ge=0.0, le=60.0)


class WorkflowUpdateRequest(BaseModel):
    status: Optional[
        Literal[
            "new",
            "assigned",
            "in_progress",
            "contacted",
            "promise_to_pay",
            "snoozed",
            "escalated",
            "resolved",
        ]
    ] = None
    owner: Optional[str] = Field(default=None, min_length=1, max_length=80)
    follow_up_at: Optional[datetime] = None
    snoozed_until: Optional[datetime] = None
    note: Optional[str] = Field(default=None, min_length=1, max_length=500)


class WorkflowAutomationRequest(BaseModel):
    scope: Literal["high", "all"] = "high"
    limit: int = Field(default=2000, ge=1, le=10000)
    include_snoozed: bool = False
    dry_run: bool = False


class ModelPromotionRequest(BaseModel):
    challenger_model: Literal["logistic_regression", "random_forest", "gradient_boosting"]
    rationale: Optional[str] = Field(default=None, max_length=300)


class AppState:
    model: Optional[CreditRiskModel] = None
    insights: Optional[Dict[str, Any]] = None
    dataset: Optional[pd.DataFrame] = None
    portfolio_records: Optional[list[Dict[str, Any]]] = None
    portfolio_index: Optional[Dict[str, Dict[str, Any]]] = None
    monitoring_snapshots: Optional[list[Dict[str, Any]]] = None
    model_registry: Optional[list[Dict[str, Any]]] = None
    startup_error: Optional[str] = None


state = AppState()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_role(x_user_role: Optional[str]) -> str:
    if not x_user_role:
        return "manager"

    normalized = str(x_user_role).strip().lower()
    if normalized not in ROLE_PERMISSIONS:
        raise HTTPException(
            status_code=403,
            detail=f"Unknown role '{x_user_role}'. Allowed roles: {', '.join(sorted(ROLE_PERMISSIONS))}.",
        )
    return normalized


def _ensure_permission(role: str, permission: str) -> None:
    allowed = ROLE_PERMISSIONS.get(role, set())
    if permission not in allowed:
        raise HTTPException(
            status_code=403,
            detail=f"Role '{role}' does not have permission '{permission}'.",
        )


def _coerce_datetime_to_utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc).isoformat()
    return value.astimezone(timezone.utc).isoformat()


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _serialize_workflow_snapshot(record: Dict[str, Any]) -> Dict[str, Any]:
    timeline = record.get("timeline")
    clean_timeline = []
    if isinstance(timeline, list):
        clean_timeline = [entry for entry in timeline if isinstance(entry, dict)][-80:]

    return {
        "workflow_status": record.get("workflow_status", "new"),
        "assigned_to": record.get("assigned_to"),
        "follow_up_at": record.get("follow_up_at"),
        "snoozed_until": record.get("snoozed_until"),
        "last_updated_at": record.get("last_updated_at"),
        "timeline": clean_timeline,
    }


def _load_workflow_state() -> Dict[str, Dict[str, Any]]:
    if not WORKFLOW_STATE_PATH.exists():
        return {}

    try:
        payload = json.loads(WORKFLOW_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    accounts = payload.get("accounts")
    if isinstance(accounts, dict):
        return accounts
    return {}


def _save_workflow_state(records: list[Dict[str, Any]]) -> None:
    accounts = {
        str(record["account_id"]): _serialize_workflow_snapshot(record)
        for record in records
        if isinstance(record, dict) and "account_id" in record
    }

    payload = {
        "saved_at": _utc_now_iso(),
        "accounts": accounts,
    }

    try:
        WORKFLOW_STATE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError:
        # Workflow persistence failure should not block API responses.
        pass


def _apply_saved_workflow_state(
    records: list[Dict[str, Any]],
    saved_snapshots: Dict[str, Dict[str, Any]],
) -> None:
    if not saved_snapshots:
        return

    for record in records:
        snapshot = saved_snapshots.get(str(record.get("account_id")))
        if not isinstance(snapshot, dict):
            continue

        status = snapshot.get("workflow_status")
        if isinstance(status, str) and status in WORKFLOW_STATUS_VALUES:
            record["workflow_status"] = status

        owner = snapshot.get("assigned_to")
        if isinstance(owner, str) and owner.strip():
            record["assigned_to"] = owner.strip()
        elif owner is None:
            record["assigned_to"] = None

        follow_up_at = snapshot.get("follow_up_at")
        if isinstance(follow_up_at, str):
            record["follow_up_at"] = follow_up_at

        snoozed_until = snapshot.get("snoozed_until")
        if isinstance(snoozed_until, str):
            record["snoozed_until"] = snoozed_until

        last_updated_at = snapshot.get("last_updated_at")
        if isinstance(last_updated_at, str):
            record["last_updated_at"] = last_updated_at

        timeline = snapshot.get("timeline")
        if isinstance(timeline, list):
            record["timeline"] = [entry for entry in timeline if isinstance(entry, dict)][-80:]


def _normalize_prediction_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(payload)

    income_value = float(normalized["income"])
    if normalized.get("income_period") == "monthly":
        income_value *= 12.0
    normalized["income"] = income_value

    loan_amount = normalized.get("loan_amount")
    if normalized.get("debt_to_income_ratio") is None:
        if loan_amount is not None:
            normalized["debt_to_income_ratio"] = float(min(max(loan_amount / max(income_value, 1.0), 0.0), 1.5))
        else:
            raise HTTPException(
                status_code=422,
                detail=(
                    "debt_to_income_ratio is required when loan_amount is not provided. "
                    "Provide either loan_amount or debt_to_income_ratio."
                ),
            )

    if normalized.get("credit_utilization") is None:
        if loan_amount is not None:
            denominator = max(income_value + loan_amount, 1.0)
            normalized["credit_utilization"] = float(min(max(loan_amount / denominator, 0.0), 1.0))
        else:
            raise HTTPException(
                status_code=422,
                detail=(
                    "credit_utilization is required when loan_amount is not provided. "
                    "Provide either loan_amount or credit_utilization."
                ),
            )

    normalized.pop("income_period", None)
    return normalized


def _portfolio_action_recommendation(record: Dict[str, Any]) -> str:
    workflow_status = str(record.get("workflow_status", "new"))
    if workflow_status == "resolved":
        return "Case resolved. Continue passive monitoring for recurrence." 
    if workflow_status == "snoozed":
        return "Snoozed case. Re-open on snooze expiry with fresh contact attempt."
    if workflow_status == "contacted":
        return "Contact complete. Track commitment and schedule follow-up."

    if record["risk_category"] == "high":
        return "Immediate outreach with repayment restructuring options."
    if record["risk_category"] == "medium":
        return "Schedule proactive reminder and monitor payment behavior weekly."
    return "Keep on standard monitoring cadence."


def _build_auto_owner_load(records: list[Dict[str, Any]]) -> Dict[str, int]:
    owner_load = {owner: 0 for owner in AUTO_WORKFLOW_OWNER_POOL}
    for record in records:
        if str(record.get("workflow_status", "new")) == "resolved":
            continue

        owner = str(record.get("assigned_to") or "").strip()
        if owner in owner_load:
            owner_load[owner] += 1

    return owner_load


def _pick_auto_owner(owner_load: Dict[str, int]) -> str:
    selected_owner = min(owner_load.items(), key=lambda item: (item[1], item[0]))[0]
    owner_load[selected_owner] += 1
    return selected_owner


def _future_iso(days: int = 0, hours: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days, hours=hours)).isoformat()


def _plan_automated_workflow_update(
    record: Dict[str, Any],
    owner_load: Dict[str, int],
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)

    current_owner = str(record.get("assigned_to") or "").strip() or None
    current_status = str(record.get("workflow_status", "new"))
    current_follow_up = record.get("follow_up_at") if isinstance(record.get("follow_up_at"), str) else None
    current_snoozed_until = (
        record.get("snoozed_until") if isinstance(record.get("snoozed_until"), str) else None
    )

    risk_category = str(record.get("risk_category", "low"))
    risk_score = float(record.get("risk_score", 0.0))
    missed_payments = int(record.get("missed_payments", 0))
    follow_up_dt = _parse_datetime(current_follow_up)
    needs_follow_up = follow_up_dt is None or follow_up_dt <= now

    next_owner = current_owner
    next_status = current_status
    next_follow_up = current_follow_up
    next_snoozed_until = current_snoozed_until
    reasons: list[str] = []

    if current_status == "resolved":
        return {
            "changed": False,
            "owner": current_owner,
            "status": current_status,
            "follow_up_at": current_follow_up,
            "snoozed_until": current_snoozed_until,
            "reason": "already resolved",
        }

    if next_owner is None and risk_category in {"high", "medium"}:
        next_owner = _pick_auto_owner(owner_load)
        reasons.append("owner balanced")

    if risk_category == "high":
        next_snoozed_until = None
        if risk_score >= 82.0 or missed_payments >= 5:
            if current_status in {"new", "assigned", "in_progress", "snoozed"}:
                next_status = "escalated"
                reasons.append("escalation policy")
            if needs_follow_up:
                next_follow_up = _future_iso(hours=24)
                reasons.append("24h follow-up")
        else:
            if current_status in {"new", "assigned", "snoozed"}:
                next_status = "in_progress"
                reasons.append("active outreach")
            if needs_follow_up:
                next_follow_up = _future_iso(days=2)
                reasons.append("48h follow-up")

    elif risk_category == "medium":
        next_snoozed_until = None
        if current_status in {"new", "snoozed"}:
            next_status = "assigned"
            reasons.append("preventive assignment")
        if needs_follow_up:
            next_follow_up = _future_iso(days=5)
            reasons.append("weekly monitoring")

    else:
        if current_status in {"new", "assigned", "in_progress"} and current_follow_up is None:
            next_status = "snoozed"
            next_snoozed_until = _future_iso(days=14)
            next_follow_up = None
            reasons.append("low-risk snooze")

    changed = (
        next_owner != current_owner
        or next_status != current_status
        or next_follow_up != current_follow_up
        or next_snoozed_until != current_snoozed_until
    )

    return {
        "changed": changed,
        "owner": next_owner,
        "status": next_status,
        "follow_up_at": next_follow_up,
        "snoozed_until": next_snoozed_until,
        "reason": ", ".join(reasons) if reasons else "automation rules",
    }


def _append_timeline_event(
    record: Dict[str, Any],
    event_type: str,
    description: str,
    actor: str,
) -> None:
    timeline = record.setdefault("timeline", [])
    if not isinstance(timeline, list):
        timeline = []
        record["timeline"] = timeline

    timestamp = _utc_now_iso()
    timeline.append(
        {
            "event_id": f"{record['account_id']}-{int(datetime.now(timezone.utc).timestamp() * 1000)}",
            "event_type": event_type,
            "description": description,
            "actor": actor,
            "created_at": timestamp,
        }
    )

    if len(timeline) > 80:
        del timeline[:-80]


async def _read_uploaded_tabular_file(file: UploadFile) -> pd.DataFrame:
    filename = str(file.filename or "batch_upload").lower()
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        if filename.endswith(".xlsx") or filename.endswith(".xls"):
            return pd.read_excel(BytesIO(contents), engine="openpyxl")

        decoded = contents.decode("utf-8", errors="replace")
        for separator in [",", ";", "\t"]:
            candidate = pd.read_csv(BytesIO(decoded.encode("utf-8")), sep=separator)
            if candidate.shape[1] > 1:
                return candidate

        return pd.read_csv(BytesIO(decoded.encode("utf-8")))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Unable to parse uploaded file: {exc}") from exc


def _prepare_batch_dataframe_for_scoring(raw_dataframe: pd.DataFrame) -> pd.DataFrame:
    standardized = _standardize_schema(raw_dataframe)
    missing_columns = [column for column in FEATURE_COLUMNS if column not in standardized.columns]
    if missing_columns:
        raise HTTPException(
            status_code=422,
            detail=(
                "Uploaded file is missing required columns after schema mapping: "
                f"{', '.join(missing_columns)}"
            ),
        )

    if TARGET_COLUMN not in standardized.columns:
        standardized[TARGET_COLUMN] = np.nan

    selected_columns = FEATURE_COLUMNS + [
        column for column in OPTIONAL_FEATURE_COLUMNS if column in standardized.columns
    ] + [TARGET_COLUMN]

    prepared = _sanitize_dataframe(standardized[selected_columns])

    fill_columns = FEATURE_COLUMNS + [
        column for column in OPTIONAL_FEATURE_COLUMNS if column in prepared.columns
    ]
    for column in fill_columns:
        median_value = float(prepared[column].median(skipna=True))
        if np.isnan(median_value):
            if state.model and column in state.model.optional_feature_defaults:
                median_value = float(state.model.optional_feature_defaults[column])
            else:
                median_value = 0.0
        prepared[column] = prepared[column].fillna(median_value)

    return prepared


def _build_alerts(records: list[Dict[str, Any]], limit: int = 100) -> list[Dict[str, Any]]:
    alerts: list[Dict[str, Any]] = []
    now = datetime.now(timezone.utc)

    for record in records:
        account_id = str(record.get("account_id", ""))
        account_name = str(record.get("account_name", account_id))
        workflow_status = str(record.get("workflow_status", "new"))
        assigned_to = record.get("assigned_to")
        risk_category = str(record.get("risk_category", "low"))
        risk_score = float(record.get("risk_score", 0.0))
        missed_payments = int(record.get("missed_payments", 0))

        follow_up_at_raw = record.get("follow_up_at")
        follow_up_at = _parse_datetime(follow_up_at_raw)

        if risk_category == "high" and not assigned_to and workflow_status != "resolved":
            alerts.append(
                {
                    "alert_id": f"ALRT-{account_id}-UNASSIGNED",
                    "severity": "high",
                    "account_id": account_id,
                    "account_name": account_name,
                    "title": "High-risk account is unassigned",
                    "description": "Assign an owner immediately to avoid collections delay.",
                    "recommended_action": "Assign account and initiate outreach within 24 hours.",
                    "risk_score": round(risk_score, 2),
                    "created_at": _utc_now_iso(),
                }
            )

        if follow_up_at is not None and follow_up_at <= now and workflow_status != "resolved":
            alerts.append(
                {
                    "alert_id": f"ALRT-{account_id}-FOLLOWUP-OVERDUE",
                    "severity": "medium",
                    "account_id": account_id,
                    "account_name": account_name,
                    "title": "Follow-up overdue",
                    "description": f"Scheduled follow-up at {follow_up_at.isoformat()} has passed.",
                    "recommended_action": "Execute pending contact task and update timeline.",
                    "risk_score": round(risk_score, 2),
                    "created_at": _utc_now_iso(),
                }
            )

        if workflow_status == "contacted" and follow_up_at is None:
            alerts.append(
                {
                    "alert_id": f"ALRT-{account_id}-NO-FOLLOWUP",
                    "severity": "medium",
                    "account_id": account_id,
                    "account_name": account_name,
                    "title": "Contacted case missing follow-up",
                    "description": "Borrower was contacted but no follow-up date is set.",
                    "recommended_action": "Set a follow-up date to maintain collections cadence.",
                    "risk_score": round(risk_score, 2),
                    "created_at": _utc_now_iso(),
                }
            )

        if missed_payments >= 5 and workflow_status in {"new", "assigned"}:
            alerts.append(
                {
                    "alert_id": f"ALRT-{account_id}-MISSED-PAYMENT-SPIKE",
                    "severity": "high",
                    "account_id": account_id,
                    "account_name": account_name,
                    "title": "Missed-payment spike unresolved",
                    "description": "Critical payment behavior detected with no active mitigation workflow.",
                    "recommended_action": "Escalate case and evaluate restructuring options.",
                    "risk_score": round(risk_score, 2),
                    "created_at": _utc_now_iso(),
                }
            )

    severity_rank = {"high": 2, "medium": 1, "low": 0}
    alerts.sort(
        key=lambda item: (
            severity_rank.get(str(item.get("severity")), 0),
            float(item.get("risk_score", 0.0)),
        ),
        reverse=True,
    )
    return alerts[:limit]


def _build_model_monitoring_snapshot(
    records: list[Dict[str, Any]],
    insights: Dict[str, Any],
) -> Dict[str, Any]:
    model_performance = insights.get("model_performance", {}) if isinstance(insights, dict) else {}
    statistical_summary = insights.get("statistical_summary", {}) if isinstance(insights, dict) else {}

    if records:
        risk_scores = np.asarray([float(item.get("risk_score", 0.0)) for item in records], dtype=float)
        high_risk_share = float(np.mean([1.0 if item.get("risk_category") == "high" else 0.0 for item in records]))
        override_rate = float(np.mean([1.0 if item.get("override_applied") else 0.0 for item in records]))
    else:
        risk_scores = np.asarray([0.0], dtype=float)
        high_risk_share = 0.0
        override_rate = 0.0

    drift_rows = []
    for feature in FEATURE_COLUMNS:
        baseline = statistical_summary.get(feature, {}) if isinstance(statistical_summary, dict) else {}
        baseline_mean = float(baseline.get("mean", 0.0))
        baseline_std = float(baseline.get("std", 0.0))

        current_values = [float(item.get(feature, 0.0)) for item in records if item.get(feature) is not None]
        current_mean = float(np.mean(current_values)) if current_values else baseline_mean

        if baseline_std > 1e-8:
            drift_z_score = abs(current_mean - baseline_mean) / baseline_std
        else:
            drift_z_score = 0.0

        drift_rows.append(
            {
                "feature": feature,
                "baseline_mean": round(baseline_mean, 6),
                "current_mean": round(current_mean, 6),
                "z_score": round(float(drift_z_score), 4),
                "drift_flag": bool(drift_z_score >= 1.0),
            }
        )

    average_drift_z = float(np.mean([row["z_score"] for row in drift_rows])) if drift_rows else 0.0

    return {
        "timestamp": _utc_now_iso(),
        "selected_model": model_performance.get("selected_model"),
        "accuracy": model_performance.get("accuracy"),
        "roc_auc": model_performance.get("roc_auc"),
        "decision_threshold": model_performance.get("decision_threshold"),
        "calibration_mode": model_performance.get("calibration_mode"),
        "average_risk_score": round(float(np.mean(risk_scores)), 2),
        "high_risk_share": round(high_risk_share, 4),
        "override_rate": round(override_rate, 4),
        "average_drift_z": round(average_drift_z, 4),
        "drift_rows": drift_rows,
    }


def _append_monitoring_snapshot(snapshot: Dict[str, Any]) -> None:
    if state.monitoring_snapshots is None:
        state.monitoring_snapshots = []

    state.monitoring_snapshots.append(
        {
            "timestamp": snapshot.get("timestamp"),
            "average_risk_score": snapshot.get("average_risk_score"),
            "high_risk_share": snapshot.get("high_risk_share"),
            "override_rate": snapshot.get("override_rate"),
            "average_drift_z": snapshot.get("average_drift_z"),
        }
    )

    if len(state.monitoring_snapshots) > 120:
        state.monitoring_snapshots = state.monitoring_snapshots[-120:]


def _initialize_model_registry(model_metrics: Dict[str, Any]) -> list[Dict[str, Any]]:
    selected_model = str(model_metrics.get("selected_model", "logistic_regression"))
    candidates = model_metrics.get("model_candidates", {})
    now = _utc_now_iso()

    registry: list[Dict[str, Any]] = [
        {
            "version_id": f"model-{selected_model}-champion",
            "model_name": selected_model,
            "status": "champion",
            "accuracy": model_metrics.get("accuracy"),
            "roc_auc": model_metrics.get("roc_auc"),
            "decision_threshold": model_metrics.get("decision_threshold"),
            "created_at": now,
            "notes": "Auto-selected champion from training pipeline.",
        }
    ]

    for model_name, stats in candidates.items():
        if model_name == selected_model:
            continue
        registry.append(
            {
                "version_id": f"model-{model_name}-challenger",
                "model_name": model_name,
                "status": "challenger",
                "accuracy": stats.get("validation_accuracy"),
                "roc_auc": stats.get("roc_auc"),
                "decision_threshold": stats.get("decision_threshold"),
                "created_at": now,
                "notes": "Validation challenger awaiting promotion.",
            }
        )

    return registry


def _build_portfolio_records(model: CreditRiskModel, dataset: pd.DataFrame) -> list[Dict[str, Any]]:
    probabilities = model.score_dataframe(dataset)

    records: list[Dict[str, Any]] = []
    for index, (row, probability) in enumerate(zip(dataset.to_dict(orient="records"), probabilities), start=1):
        risk_probability = float(probability)
        risk_score = float(risk_probability * 100.0)

        category, override_applied, override_reason = model._risk_category(
            probability=risk_probability,
            missed_payments=float(row["missed_payments"]),
        )
        if override_applied:
            risk_probability = max(risk_probability, 0.75)
            risk_score = float(risk_probability * 100.0)

        annual_income = float(row["income"])
        created_at = _utc_now_iso()
        record = {
            "account_id": f"ACC-{index:05d}",
            "account_name": f"Borrower {index:05d}",
            "risk_probability": round(risk_probability, 4),
            "risk_score": round(risk_score, 2),
            "risk_category": category,
            "override_applied": override_applied,
            "override_reason": override_reason,
            "annual_income": round(annual_income, 2),
            "monthly_income": round(annual_income / 12.0, 2),
            "loan_amount": round(float(row.get("loan_amount", 0.0)), 2),
            "credit_score": int(round(float(row["credit_score"]))),
            "debt_to_income_ratio": round(float(row["debt_to_income_ratio"]), 4),
            "credit_utilization": round(float(row["credit_utilization"]), 4),
            "missed_payments": int(round(float(row["missed_payments"]))),
            "repayment_history": round(float(row["repayment_history"]), 4),
            "years_experience": round(float(row.get("years_experience", 0.0)), 1),
            "age": int(round(float(row.get("age", 40.0)))),
            "workflow_status": "new",
            "assigned_to": None,
            "follow_up_at": None,
            "snoozed_until": None,
            "last_updated_at": created_at,
            "timeline": [],
        }
        record["recommended_action"] = _portfolio_action_recommendation(record)
        records.append(record)

    records.sort(key=lambda item: item["risk_probability"], reverse=True)
    return records


def _build_risk_decile_rows(records: list[Dict[str, Any]], bucket_count: int = 10) -> list[Dict[str, Any]]:
    rows = [
        {
            "label": str(index + 1).zfill(2),
            "low": 0,
            "medium": 0,
            "high": 0,
        }
        for index in range(bucket_count)
    ]

    if not records:
        return rows

    sorted_records = sorted(records, key=lambda item: float(item.get("risk_score", 0.0)))
    bucket_size = max(1, (len(sorted_records) + bucket_count - 1) // bucket_count)

    for index, record in enumerate(sorted_records):
        bucket_index = min(bucket_count - 1, index // bucket_size)
        category = str(record.get("risk_category", "low")).lower()
        if category not in {"low", "medium", "high"}:
            category = "low"
        rows[bucket_index][category] += 1

    return rows


@app.on_event("startup")
def startup_event() -> None:
    dataset_path = os.getenv("CREDIT_RISK_DATASET")
    try:
        initialized = initialize_model_system(data_path=dataset_path)
        state.model = initialized["model"]
        state.insights = initialized["insights"]
        state.dataset = initialized["dataset"]
        state.portfolio_records = _build_portfolio_records(state.model, state.dataset)
        _apply_saved_workflow_state(state.portfolio_records, _load_workflow_state())
        state.portfolio_index = {
            str(record["account_id"]): record
            for record in state.portfolio_records
        }
        state.model_registry = _initialize_model_registry(
            state.insights.get("model_performance", {}) if state.insights else {}
        )
        initial_snapshot = _build_model_monitoring_snapshot(
            records=state.portfolio_records,
            insights=state.insights or {},
        )
        state.monitoring_snapshots = []
        _append_monitoring_snapshot(initial_snapshot)
        state.startup_error = None
    except Exception as exc:  # pragma: no cover - defensive startup guard
        state.model = None
        state.insights = None
        state.dataset = None
        state.portfolio_records = None
        state.portfolio_index = None
        state.monitoring_snapshots = None
        state.model_registry = None
        state.startup_error = str(exc)


@app.get("/")
def root() -> Dict[str, str]:
    return {
        "project": "AI-Powered Credit Risk & Collections Strategy",
        "message": "Use /insights for analytics and /predict for risk scoring.",
    }


@app.get("/health")
def health() -> Dict[str, Any]:
    return {
        "status": "ok" if state.model is not None else "degraded",
        "model_ready": state.model is not None,
        "startup_error": state.startup_error,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/auth/roles")
def get_auth_roles(x_user_role: Optional[str] = Header(default=None, alias="X-User-Role")) -> Dict[str, Any]:
    resolved_role = _resolve_role(x_user_role)
    return {
        "current_role": resolved_role,
        "permissions": sorted(ROLE_PERMISSIONS.get(resolved_role, set())),
        "available_roles": {
            role: sorted(permissions)
            for role, permissions in ROLE_PERMISSIONS.items()
        },
        "generated_at": _utc_now_iso(),
    }


@app.get("/insights")
def get_insights(x_user_role: Optional[str] = Header(default=None, alias="X-User-Role")) -> Dict[str, Any]:
    role = _resolve_role(x_user_role)
    _ensure_permission(role, "read")

    if state.startup_error is not None:
        raise HTTPException(status_code=503, detail=f"Startup failed: {state.startup_error}")
    if state.insights is None:
        raise HTTPException(status_code=503, detail="Insights are not available yet.")

    payload = dict(state.insights)
    payload["generated_at"] = datetime.now(timezone.utc).isoformat()
    return payload


@app.get("/portfolio")
def get_portfolio(
    risk: Optional[str] = Query(default=None, pattern="^(low|medium|high)$"),
    status: Optional[str] = Query(
        default=None,
        pattern="^(new|assigned|in_progress|contacted|promise_to_pay|snoozed|escalated|resolved)$",
    ),
    search: Optional[str] = None,
    summary_mode: Literal["full", "light"] = Query(default="full"),
    limit: int = Query(default=200, ge=1, le=10000),
    offset: int = Query(default=0, ge=0, le=200000),
    x_user_role: Optional[str] = Header(default=None, alias="X-User-Role"),
) -> Dict[str, Any]:
    role = _resolve_role(x_user_role)
    _ensure_permission(role, "read")

    if state.startup_error is not None:
        raise HTTPException(status_code=503, detail=f"Startup failed: {state.startup_error}")
    if state.portfolio_records is None:
        raise HTTPException(status_code=503, detail="Portfolio records are not available yet.")

    records = state.portfolio_records

    if risk is not None:
        records = [record for record in records if record["risk_category"] == risk]

    if status is not None:
        records = [record for record in records if record.get("workflow_status") == status]

    if search:
        needle = search.strip().lower()
        if needle:
            records = [
                record
                for record in records
                if needle in record["account_id"].lower()
                or needle in record["account_name"].lower()
                or needle in record["risk_category"].lower()
                or needle in str(record.get("workflow_status", "")).lower()
                or needle in str(record.get("assigned_to") or "").lower()
            ]

    total_records = len(records)
    slice_start = min(offset, total_records)
    slice_end = min(slice_start + limit, total_records)

    sliced_records = []
    for record in records[slice_start:slice_end]:
        compact = dict(record)
        timeline = compact.get("timeline", [])
        compact["timeline_count"] = len(timeline) if isinstance(timeline, list) else 0
        compact["latest_event"] = timeline[-1] if isinstance(timeline, list) and timeline else None
        compact.pop("timeline", None)
        sliced_records.append(compact)

    risk_counts = {
        "low": int(sum(1 for record in records if record["risk_category"] == "low")),
        "medium": int(sum(1 for record in records if record["risk_category"] == "medium")),
        "high": int(sum(1 for record in records if record["risk_category"] == "high")),
    }
    workflow_counts = {
        workflow_status: int(
            sum(1 for record in records if record.get("workflow_status") == workflow_status)
        )
        for workflow_status in sorted(WORKFLOW_STATUS_VALUES)
    }

    now = datetime.now(timezone.utc)
    due_followups = 0
    for record in records:
        follow_up_at = _parse_datetime(record.get("follow_up_at"))
        if follow_up_at is not None and follow_up_at <= now and record.get("workflow_status") != "resolved":
            due_followups += 1

    average_score = (
        float(np.mean([float(record["risk_score"]) for record in records]))
        if records
        else 0.0
    )
    include_heavy_summary = summary_mode == "full"

    return {
        "summary": {
            "total_records": total_records,
            "high_priority": risk_counts["high"],
            "risk_counts": risk_counts,
            "risk_deciles": _build_risk_decile_rows(records) if include_heavy_summary else [],
            "workflow_counts": workflow_counts,
            "due_followups": due_followups,
            "alert_count": len(_build_alerts(records, limit=5000)) if include_heavy_summary else 0,
            "average_risk_score": round(average_score, 2),
            "summary_mode": summary_mode,
        },
        "records": sliced_records,
        "pagination": {
            "offset": slice_start,
            "limit": limit,
            "returned_records": len(sliced_records),
            "has_more": slice_end < total_records,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/alerts")
def get_alerts(
    limit: int = Query(default=80, ge=1, le=1000),
    x_user_role: Optional[str] = Header(default=None, alias="X-User-Role"),
) -> Dict[str, Any]:
    role = _resolve_role(x_user_role)
    _ensure_permission(role, "read")

    if state.startup_error is not None:
        raise HTTPException(status_code=503, detail=f"Startup failed: {state.startup_error}")
    if state.portfolio_records is None:
        raise HTTPException(status_code=503, detail="Portfolio records are not available yet.")

    alerts = _build_alerts(state.portfolio_records, limit=limit)
    severity_counts = {
        "high": int(sum(1 for item in alerts if item.get("severity") == "high")),
        "medium": int(sum(1 for item in alerts if item.get("severity") == "medium")),
        "low": int(sum(1 for item in alerts if item.get("severity") == "low")),
    }

    return {
        "summary": {
            "total_alerts": len(alerts),
            "severity_counts": severity_counts,
        },
        "alerts": alerts,
        "generated_at": _utc_now_iso(),
    }


@app.get("/model-monitoring")
def get_model_monitoring(x_user_role: Optional[str] = Header(default=None, alias="X-User-Role")) -> Dict[str, Any]:
    role = _resolve_role(x_user_role)
    _ensure_permission(role, "read")

    if state.startup_error is not None:
        raise HTTPException(status_code=503, detail=f"Startup failed: {state.startup_error}")
    if state.portfolio_records is None or state.insights is None:
        raise HTTPException(status_code=503, detail="Monitoring data is not available yet.")

    current_snapshot = _build_model_monitoring_snapshot(
        records=state.portfolio_records,
        insights=state.insights,
    )
    _append_monitoring_snapshot(current_snapshot)

    recent_history = state.monitoring_snapshots[-30:] if state.monitoring_snapshots else []
    return {
        "current": current_snapshot,
        "history": recent_history,
        "generated_at": _utc_now_iso(),
    }


@app.get("/model-versions")
def get_model_versions(x_user_role: Optional[str] = Header(default=None, alias="X-User-Role")) -> Dict[str, Any]:
    role = _resolve_role(x_user_role)
    _ensure_permission(role, "read")

    if state.startup_error is not None:
        raise HTTPException(status_code=503, detail=f"Startup failed: {state.startup_error}")
    if state.model_registry is None:
        raise HTTPException(status_code=503, detail="Model registry is not available yet.")

    champion = next((item for item in state.model_registry if item.get("status") == "champion"), None)
    challengers = [item for item in state.model_registry if item.get("status") == "challenger"]

    return {
        "champion": champion,
        "challengers": challengers,
        "registry": state.model_registry,
        "generated_at": _utc_now_iso(),
    }


@app.post("/model-versions/promote")
def promote_model_version(
    request: ModelPromotionRequest,
    x_user_role: Optional[str] = Header(default=None, alias="X-User-Role"),
) -> Dict[str, Any]:
    role = _resolve_role(x_user_role)
    _ensure_permission(role, "model_promote")

    if state.startup_error is not None:
        raise HTTPException(status_code=503, detail=f"Startup failed: {state.startup_error}")
    if state.model_registry is None:
        raise HTTPException(status_code=503, detail="Model registry is not available yet.")

    challenger = next(
        (
            item
            for item in state.model_registry
            if item.get("model_name") == request.challenger_model and item.get("status") == "challenger"
        ),
        None,
    )
    if challenger is None:
        raise HTTPException(status_code=404, detail=f"Challenger {request.challenger_model} not found.")

    now = _utc_now_iso()
    for item in state.model_registry:
        if item.get("status") == "champion":
            item["status"] = "archived"
            item["notes"] = f"Archived after promoting {request.challenger_model}."
            item["updated_at"] = now

    challenger["status"] = "champion"
    challenger["updated_at"] = now
    challenger["notes"] = request.rationale or "Promoted from challenger to champion."

    for item in state.model_registry:
        if item.get("status") == "archived" and item.get("model_name") != request.challenger_model:
            if item.get("model_name") in {"logistic_regression", "random_forest", "gradient_boosting"}:
                item["status"] = "challenger"

    return {
        "champion": challenger,
        "registry": state.model_registry,
        "generated_at": now,
    }


@app.post("/portfolio/batch-score")
async def batch_score_portfolio(
    file: UploadFile = File(...),
    limit: int = Query(default=2000, ge=1, le=20_000),
    x_user_role: Optional[str] = Header(default=None, alias="X-User-Role"),
) -> Dict[str, Any]:
    role = _resolve_role(x_user_role)
    _ensure_permission(role, "batch_score")

    if state.startup_error is not None:
        raise HTTPException(status_code=503, detail=f"Startup failed: {state.startup_error}")
    if state.model is None:
        raise HTTPException(status_code=503, detail="Model is not ready.")

    raw_dataframe = await _read_uploaded_tabular_file(file)
    prepared_dataframe = _prepare_batch_dataframe_for_scoring(raw_dataframe)
    probabilities = state.model.score_dataframe(prepared_dataframe)

    scored_records: list[Dict[str, Any]] = []
    for index, (row, probability) in enumerate(
        zip(prepared_dataframe.to_dict(orient="records"), probabilities),
        start=1,
    ):
        risk_probability = float(probability)
        risk_score = float(risk_probability * 100.0)
        category, override_applied, override_reason = state.model._risk_category(
            probability=risk_probability,
            missed_payments=float(row["missed_payments"]),
        )

        scored_records.append(
            {
                "row_id": index,
                "risk_probability": round(risk_probability, 4),
                "risk_score": round(risk_score, 2),
                "risk_category": category,
                "override_applied": override_applied,
                "override_reason": override_reason,
                "credit_score": int(round(float(row["credit_score"]))),
                "income": round(float(row["income"]), 2),
                "loan_amount": round(float(row.get("loan_amount", 0.0)), 2),
                "debt_to_income_ratio": round(float(row["debt_to_income_ratio"]), 4),
                "credit_utilization": round(float(row["credit_utilization"]), 4),
                "missed_payments": int(round(float(row["missed_payments"]))),
                "repayment_history": round(float(row["repayment_history"]), 4),
            }
        )

    scored_records.sort(key=lambda item: item["risk_probability"], reverse=True)
    clipped_records = scored_records[:limit]

    risk_counts = {
        "low": int(sum(1 for item in scored_records if item["risk_category"] == "low")),
        "medium": int(sum(1 for item in scored_records if item["risk_category"] == "medium")),
        "high": int(sum(1 for item in scored_records if item["risk_category"] == "high")),
    }

    return {
        "summary": {
            "uploaded_rows": int(len(raw_dataframe)),
            "scored_rows": int(len(scored_records)),
            "returned_rows": int(len(clipped_records)),
            "risk_counts": risk_counts,
            "average_risk_score": (
                round(float(np.mean([item["risk_score"] for item in scored_records])), 2)
                if scored_records
                else 0.0
            ),
        },
        "records": clipped_records,
        "generated_at": _utc_now_iso(),
    }


def _get_portfolio_record_or_404(account_id: str) -> Dict[str, Any]:
    if state.portfolio_index is None:
        raise HTTPException(status_code=503, detail="Portfolio records are not available yet.")

    normalized_account_id = account_id.strip().upper()
    record = state.portfolio_index.get(normalized_account_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Account {normalized_account_id} not found.")
    return record


@app.get("/portfolio/{account_id}")
def get_portfolio_account(
    account_id: str,
    x_user_role: Optional[str] = Header(default=None, alias="X-User-Role"),
) -> Dict[str, Any]:
    role = _resolve_role(x_user_role)
    _ensure_permission(role, "read")

    if state.startup_error is not None:
        raise HTTPException(status_code=503, detail=f"Startup failed: {state.startup_error}")

    record = _get_portfolio_record_or_404(account_id)
    return {
        "record": record,
        "generated_at": _utc_now_iso(),
    }


@app.patch("/portfolio/{account_id}/workflow")
def update_portfolio_workflow(
    account_id: str,
    request: WorkflowUpdateRequest,
    x_user_role: Optional[str] = Header(default=None, alias="X-User-Role"),
) -> Dict[str, Any]:
    role = _resolve_role(x_user_role)
    _ensure_permission(role, "workflow_update")

    if state.startup_error is not None:
        raise HTTPException(status_code=503, detail=f"Startup failed: {state.startup_error}")
    if state.portfolio_records is None:
        raise HTTPException(status_code=503, detail="Portfolio records are not available yet.")

    record = _get_portfolio_record_or_404(account_id)
    payload = request.model_dump(exclude_unset=True)
    if not payload:
        raise HTTPException(status_code=422, detail="No workflow fields were provided to update.")

    changed = False
    actor = str(record.get("assigned_to") or "collections_agent")

    if "owner" in payload:
        owner_value = payload["owner"]
        next_owner = owner_value.strip() if isinstance(owner_value, str) else None
        if next_owner != record.get("assigned_to"):
            changed = True
            record["assigned_to"] = next_owner
            if next_owner:
                if record.get("workflow_status") == "new":
                    record["workflow_status"] = "assigned"
                _append_timeline_event(
                    record=record,
                    event_type="assignment",
                    description=f"Account assigned to {next_owner}.",
                    actor=next_owner,
                )
            else:
                _append_timeline_event(
                    record=record,
                    event_type="assignment",
                    description="Account unassigned.",
                    actor=actor,
                )
        if next_owner:
            actor = next_owner

    if "status" in payload:
        next_status = payload["status"]
        if next_status != record.get("workflow_status"):
            changed = True
            record["workflow_status"] = next_status
            _append_timeline_event(
                record=record,
                event_type="status_change",
                description=f"Workflow status changed to {next_status.replace('_', ' ')}.",
                actor=actor,
            )

    if "follow_up_at" in payload:
        follow_up_at = payload["follow_up_at"]
        follow_up_iso = _coerce_datetime_to_utc_iso(follow_up_at) if follow_up_at is not None else None
        if follow_up_iso != record.get("follow_up_at"):
            changed = True
            record["follow_up_at"] = follow_up_iso
            if follow_up_iso is not None:
                _append_timeline_event(
                    record=record,
                    event_type="follow_up",
                    description=f"Follow-up scheduled for {follow_up_iso}.",
                    actor=actor,
                )

    if "snoozed_until" in payload:
        snoozed_until = payload["snoozed_until"]
        snoozed_iso = _coerce_datetime_to_utc_iso(snoozed_until) if snoozed_until is not None else None
        if snoozed_iso != record.get("snoozed_until"):
            changed = True
            record["snoozed_until"] = snoozed_iso
            if snoozed_iso is not None:
                record["workflow_status"] = "snoozed"
                _append_timeline_event(
                    record=record,
                    event_type="snooze",
                    description=f"Case snoozed until {snoozed_iso}.",
                    actor=actor,
                )

    if "note" in payload and isinstance(payload["note"], str):
        note = payload["note"].strip()
        if note:
            changed = True
            _append_timeline_event(
                record=record,
                event_type="note",
                description=note,
                actor=actor,
            )

    if not changed:
        return {
            "record": record,
            "updated": False,
            "timestamp": _utc_now_iso(),
        }

    record["last_updated_at"] = _utc_now_iso()
    record["recommended_action"] = _portfolio_action_recommendation(record)
    _save_workflow_state(state.portfolio_records)

    return {
        "record": record,
        "updated": True,
        "timestamp": _utc_now_iso(),
    }


@app.post("/portfolio/workflow/auto")
def auto_orchestrate_portfolio_workflow(
    request: WorkflowAutomationRequest,
    x_user_role: Optional[str] = Header(default=None, alias="X-User-Role"),
) -> Dict[str, Any]:
    role = _resolve_role(x_user_role)
    _ensure_permission(role, "workflow_update")

    if state.startup_error is not None:
        raise HTTPException(status_code=503, detail=f"Startup failed: {state.startup_error}")
    if state.portfolio_records is None:
        raise HTTPException(status_code=503, detail="Portfolio records are not available yet.")

    records = state.portfolio_records
    owner_load = _build_auto_owner_load(records)
    now = datetime.now(timezone.utc)

    candidate_records = [
        record
        for record in records
        if str(record.get("workflow_status", "new")) != "resolved"
    ]

    if request.scope == "high":
        candidate_records = [
            record for record in candidate_records if str(record.get("risk_category", "low")) == "high"
        ]

    candidate_records.sort(key=lambda item: float(item.get("risk_score", 0.0)), reverse=True)
    matched_scope_count = len(candidate_records)

    summary = {
        "scope": request.scope,
        "matched_scope": matched_scope_count,
        "evaluated": 0,
        "updated": 0,
        "unchanged": 0,
        "already_orchestrated": 0,
        "skipped_snoozed": 0,
        "assigned": 0,
        "escalated": 0,
        "followups_scheduled": 0,
        "snoozed": 0,
        "dry_run": request.dry_run,
    }

    preview: list[Dict[str, Any]] = []

    for record in candidate_records:
        if summary["evaluated"] >= request.limit:
            break

        snoozed_until = _parse_datetime(record.get("snoozed_until"))
        if (
            not request.include_snoozed
            and snoozed_until is not None
            and snoozed_until > now
            and str(record.get("risk_category", "low")) != "high"
        ):
            summary["skipped_snoozed"] += 1
            continue

        summary["evaluated"] += 1
        plan = _plan_automated_workflow_update(record, owner_load)
        if not plan["changed"]:
            summary["unchanged"] += 1
            summary["already_orchestrated"] += 1

            if len(preview) < 80:
                preview.append(
                    {
                        "account_id": str(record.get("account_id")),
                        "risk_category": str(record.get("risk_category", "low")),
                        "risk_score": float(record.get("risk_score", 0.0)),
                        "owner": str(record.get("assigned_to") or ""),
                        "status": str(record.get("workflow_status", "new")),
                        "follow_up_at": record.get("follow_up_at"),
                        "reason": "already aligned with automation policy",
                        "changed": False,
                    }
                )
            continue

        previous_owner = str(record.get("assigned_to") or "").strip() or None
        previous_status = str(record.get("workflow_status", "new"))
        previous_follow_up = record.get("follow_up_at")

        summary["updated"] += 1
        if plan["owner"] != previous_owner:
            summary["assigned"] += 1
        if plan["status"] == "escalated" and previous_status != "escalated":
            summary["escalated"] += 1
        if plan["follow_up_at"] != previous_follow_up and plan["follow_up_at"] is not None:
            summary["followups_scheduled"] += 1
        if plan["status"] == "snoozed" and previous_status != "snoozed":
            summary["snoozed"] += 1

        if len(preview) < 80:
            preview.append(
                {
                    "account_id": str(record.get("account_id")),
                    "risk_category": str(record.get("risk_category", "low")),
                    "risk_score": float(record.get("risk_score", 0.0)),
                    "owner": plan["owner"],
                    "status": plan["status"],
                    "follow_up_at": plan["follow_up_at"],
                    "reason": plan["reason"],
                    "changed": True,
                }
            )

        if request.dry_run:
            continue

        record["assigned_to"] = plan["owner"]
        record["workflow_status"] = plan["status"]
        record["follow_up_at"] = plan["follow_up_at"]
        record["snoozed_until"] = plan["snoozed_until"]
        record["last_updated_at"] = _utc_now_iso()
        record["recommended_action"] = _portfolio_action_recommendation(record)

        actor = str(plan["owner"] or "workflow_automation")
        change_notes = []
        if plan["owner"] != previous_owner:
            change_notes.append(f"owner: {previous_owner or 'unassigned'} -> {plan['owner']}")
        if plan["status"] != previous_status:
            change_notes.append(f"status: {previous_status} -> {plan['status']}")
        if plan["follow_up_at"] != previous_follow_up and plan["follow_up_at"] is not None:
            change_notes.append(f"follow-up: {plan['follow_up_at']}")

        description = "Auto workflow update"
        if change_notes:
            description += f" ({'; '.join(change_notes)})"
        description += f". Policy: {plan['reason']}."

        _append_timeline_event(
            record=record,
            event_type="automation",
            description=description,
            actor=actor,
        )

    if not request.dry_run and summary["updated"]:
        _save_workflow_state(records)

    return {
        "summary": summary,
        "preview": preview,
        "generated_at": _utc_now_iso(),
    }


@app.post("/predict")
def predict(
    request: PredictionRequest,
    x_user_role: Optional[str] = Header(default=None, alias="X-User-Role"),
) -> Dict[str, Any]:
    role = _resolve_role(x_user_role)
    _ensure_permission(role, "predict")

    if state.startup_error is not None:
        raise HTTPException(status_code=503, detail=f"Startup failed: {state.startup_error}")
    if state.model is None:
        raise HTTPException(status_code=503, detail="Model is not ready.")

    normalized_payload = _normalize_prediction_payload(request.model_dump())
    prediction = state.model.predict(normalized_payload)
    return {
        "risk_score": prediction["risk_score"],
        "risk_probability": prediction["risk_probability"],
        "model_probability": prediction.get("model_probability"),
        "business_risk_index": prediction.get("business_risk_index"),
        "top_drivers": prediction.get("top_drivers", []),
        "collections_strategy": prediction.get("collections_strategy", {}),
        "risk_category": prediction["risk_category"],
        "override_applied": prediction["override_applied"],
        "override_reason": prediction["override_reason"],
        "explanation": prediction["explanation"],
        "timestamp": prediction["timestamp"],
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
