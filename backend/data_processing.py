from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd

FEATURE_COLUMNS = [
    "income",
    "credit_score",
    "credit_utilization",
    "debt_to_income_ratio",
    "missed_payments",
    "repayment_history",
]
OPTIONAL_FEATURE_COLUMNS = [
    "age",
    "loan_amount",
    "years_experience",
]
TARGET_COLUMN = "delinquent"
REQUIRED_COLUMNS = FEATURE_COLUMNS + [TARGET_COLUMN]

BEHAVIORAL_FEATURES = ["missed_payments", "repayment_history"]
FINANCIAL_FEATURES = [
    "income",
    "credit_score",
    "credit_utilization",
    "debt_to_income_ratio",
]

BOUNDS = {
    "income": (0.0, 1_000_000.0),
    "credit_score": (300.0, 850.0),
    "credit_utilization": (0.0, 1.0),
    "debt_to_income_ratio": (0.0, 1.5),
    "missed_payments": (0.0, 60.0),
    "repayment_history": (0.0, 1.0),
    "age": (18.0, 100.0),
    "loan_amount": (0.0, 2_000_000.0),
    "years_experience": (0.0, 60.0),
    "delinquent": (0.0, 1.0),
}

BACKEND_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = BACKEND_DIR.parent
DEFAULT_DATA_PATH = BACKEND_DIR / "data" / "credit_risk_dataset.csv"
DEFAULT_DATA_CANDIDATES = [
    DEFAULT_DATA_PATH,
    WORKSPACE_ROOT / "loan_risk_prediction_dataset.csv",
    WORKSPACE_ROOT / "Delinquency_prediction_dataset.csv",
    WORKSPACE_ROOT / "delinquency_prediction_dataset.csv",
]

COLUMN_ALIASES = {
    "age": ["age", "applicant_age"],
    "income": ["income", "annual_income", "applicant_income"],
    "loan_amount": ["loan_amount", "loanamount", "amount", "requested_amount"],
    "credit_score": ["credit_score", "creditscore", "fico_score", "cibil_score"],
    "years_experience": ["years_experience", "yearsexperience", "experience_years"],
    "credit_utilization": ["credit_utilization", "utilization", "credit_utilization_ratio"],
    "debt_to_income_ratio": ["debt_to_income_ratio", "dti", "debtincome_ratio", "loan_to_income_ratio"],
    "missed_payments": ["missed_payments", "missedpayments", "payment_missed_count"],
    "repayment_history": ["repayment_history", "repaymentratio", "payment_history_ratio"],
    "delinquent": [
        "delinquent",
        "delinquent_account",
        "target",
        "default",
        "loan_approved",
        "loanapproved",
        "approval_status",
        "loan_status",
    ],
}

APPROVAL_STYLE_TARGET_COLUMNS = {
    "loanapproved",
    "loanapprovedflag",
    "loanapproval",
    "approvalstatus",
    "approved",
    "isapproved",
    "loanstatus",
}


@dataclass
class PreparedDataset:
    raw: pd.DataFrame
    cleaned: pd.DataFrame
    imputation_report: Dict[str, Dict[str, Any]]


def _sigmoid(values: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-values))


def generate_synthetic_dataset(sample_size: int = 2500, random_state: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(random_state)

    missed_payments = np.clip(rng.poisson(1.2, sample_size), 0, 12).astype(float)
    debt_to_income_ratio = np.clip(rng.normal(0.34 + (missed_payments * 0.03), 0.12, sample_size), 0.02, 0.95)
    credit_utilization = np.clip(rng.beta(2.3, 3.0, sample_size) + (missed_payments * 0.025), 0.03, 0.99)
    repayment_history = np.clip(
        rng.normal(0.9 - (missed_payments * 0.05), 0.1, sample_size),
        0.2,
        1.0,
    )
    credit_score = np.clip(
        rng.normal(720 - (missed_payments * 24) - (debt_to_income_ratio * 85), 58, sample_size),
        300,
        850,
    )
    income = np.clip(
        rng.normal(72_000 - (missed_payments * 4_300) - (debt_to_income_ratio * 23_000), 18_000, sample_size),
        18_000,
        250_000,
    )

    # Behavioral variables are intentionally stronger drivers than financial variables.
    logit = (
        -4.8
        + (0.95 * missed_payments)
        + (4.5 * debt_to_income_ratio)
        + (3.0 * (1 - repayment_history))
        + (1.2 * credit_utilization)
        - (0.0000075 * income)
        - (0.0045 * (credit_score - 650.0))
    )
    probabilities = np.clip(_sigmoid(logit), 0.01, 0.99)
    delinquent = rng.binomial(1, probabilities, sample_size).astype(float)

    dataset = pd.DataFrame(
        {
            "income": income,
            "credit_score": credit_score,
            "credit_utilization": credit_utilization,
            "debt_to_income_ratio": debt_to_income_ratio,
            "missed_payments": missed_payments,
            "repayment_history": repayment_history,
            "delinquent": delinquent,
        }
    )

    missing_rates = {
        "income": 0.03,
        "credit_score": 0.02,
        "credit_utilization": 0.04,
        "debt_to_income_ratio": 0.05,
        "missed_payments": 0.02,
        "repayment_history": 0.03,
    }
    for column, rate in missing_rates.items():
        mask = rng.random(sample_size) < rate
        dataset.loc[mask, column] = np.nan

    return dataset


def _sanitize_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    sanitized = dataframe.copy()

    numeric_columns = FEATURE_COLUMNS + [
        column for column in OPTIONAL_FEATURE_COLUMNS if column in sanitized.columns
    ]
    for column in numeric_columns:
        sanitized[column] = pd.to_numeric(sanitized[column], errors="coerce")

    if TARGET_COLUMN not in sanitized.columns:
        sanitized[TARGET_COLUMN] = np.nan
    sanitized[TARGET_COLUMN] = pd.to_numeric(sanitized[TARGET_COLUMN], errors="coerce")

    for column, (lower, upper) in BOUNDS.items():
        if column in sanitized.columns:
            sanitized[column] = sanitized[column].clip(lower=lower, upper=upper)

    return sanitized


def _normalize_column_name(value: str) -> str:
    return "".join(character for character in str(value).strip().lower() if character.isalnum())


def _resolve_data_path(data_path: Optional[str]) -> Optional[Path]:
    if data_path:
        requested_path = Path(data_path).expanduser()
        return requested_path if requested_path.exists() and requested_path.is_file() else None

    for candidate in DEFAULT_DATA_CANDIDATES:
        if candidate.exists() and candidate.is_file():
            return candidate

    return None


def _get_source_series(
    dataframe: pd.DataFrame,
    normalized_to_original: Dict[str, str],
    aliases: list[str],
) -> Optional[pd.Series]:
    for alias in aliases:
        normalized_alias = _normalize_column_name(alias)
        if normalized_alias in normalized_to_original:
            return dataframe[normalized_to_original[normalized_alias]]
    return None


def _coerce_target_series(target_series: pd.Series, source_column: str) -> pd.Series:
    normalized_source = _normalize_column_name(source_column)
    numeric_target = pd.to_numeric(target_series, errors="coerce")

    if normalized_source in APPROVAL_STYLE_TARGET_COLUMNS:
        if numeric_target.notna().sum() > 0:
            return 1.0 - numeric_target.clip(lower=0.0, upper=1.0)

        normalized_values = target_series.astype(str).str.strip().str.lower()
        mapped = normalized_values.map(
            {
                "approved": 0.0,
                "accept": 0.0,
                "accepted": 0.0,
                "yes": 0.0,
                "y": 0.0,
                "true": 0.0,
                "1": 0.0,
                "rejected": 1.0,
                "declined": 1.0,
                "deny": 1.0,
                "denied": 1.0,
                "no": 1.0,
                "n": 1.0,
                "false": 1.0,
                "0": 1.0,
            }
        )
        if mapped.notna().sum() > 0:
            return mapped

    return numeric_target


def _derive_loan_schema_features(
    source_dataframe: pd.DataFrame,
    normalized_to_original: Dict[str, str],
    standardized: pd.DataFrame,
) -> None:
    loan_amount_source = _get_source_series(
        source_dataframe,
        normalized_to_original,
        ["loan_amount", "loanamount", "amount"],
    )
    loan_amount = (
        pd.to_numeric(loan_amount_source, errors="coerce") if loan_amount_source is not None else None
    )

    years_experience_source = _get_source_series(
        source_dataframe,
        normalized_to_original,
        ["years_experience", "yearsexperience", "experience_years"],
    )
    years_experience = (
        pd.to_numeric(years_experience_source, errors="coerce")
        if years_experience_source is not None
        else None
    )

    employment_type = _get_source_series(
        source_dataframe,
        normalized_to_original,
        ["employment_type", "employmenttype", "employment_status"],
    )

    income = pd.to_numeric(standardized["income"], errors="coerce") if "income" in standardized.columns else None
    credit_score = (
        pd.to_numeric(standardized["credit_score"], errors="coerce")
        if "credit_score" in standardized.columns
        else None
    )

    if "debt_to_income_ratio" not in standardized.columns and loan_amount is not None and income is not None:
        safe_income = income.where(income > 0.0, np.nan)
        dti = (loan_amount / safe_income).clip(lower=0.0, upper=1.5)
        standardized["debt_to_income_ratio"] = dti

    if "credit_utilization" not in standardized.columns:
        if loan_amount is not None and income is not None:
            safe_income = income.where(income > 0.0, np.nan)
            denominator = safe_income + loan_amount.clip(lower=0.0)
            utilization = (loan_amount / denominator).clip(lower=0.0, upper=1.0)
            standardized["credit_utilization"] = utilization
        elif "debt_to_income_ratio" in standardized.columns:
            dti = pd.to_numeric(standardized["debt_to_income_ratio"], errors="coerce")
            standardized["credit_utilization"] = (dti / (1.0 + dti)).clip(lower=0.0, upper=1.0)

    if "missed_payments" not in standardized.columns:
        dti = (
            pd.to_numeric(standardized["debt_to_income_ratio"], errors="coerce")
            if "debt_to_income_ratio" in standardized.columns
            else pd.Series(np.nan, index=source_dataframe.index, dtype=float)
        )
        utilization = (
            pd.to_numeric(standardized["credit_utilization"], errors="coerce")
            if "credit_utilization" in standardized.columns
            else pd.Series(np.nan, index=source_dataframe.index, dtype=float)
        )

        score_penalty = pd.Series(np.nan, index=source_dataframe.index, dtype=float)
        if credit_score is not None:
            score_penalty = ((680.0 - credit_score) / 120.0).clip(lower=0.0, upper=4.0)

        experience_penalty = pd.Series(np.nan, index=source_dataframe.index, dtype=float)
        if years_experience is not None:
            experience_penalty = ((10.0 - years_experience) / 10.0).clip(lower=0.0, upper=3.0)

        employment_risk = pd.Series(0.25, index=source_dataframe.index, dtype=float)
        if employment_type is not None:
            employment_risk = (
                employment_type.astype(str)
                .str.strip()
                .str.lower()
                .map(
                    {
                        "salaried": 0.12,
                        "self-employed": 0.28,
                        "self employed": 0.28,
                        "unemployed": 0.55,
                    }
                )
                .fillna(0.25)
                .astype(float)
            )

        # Keep synthetic behavior signals conservative when source data does not contain repayment behavior.
        missed_payments = (
            0.35
            + (1.35 * dti.fillna(0.40))
            + (0.55 * utilization.fillna(0.30))
            + (0.95 * score_penalty.fillna(0.80))
            + (0.45 * experience_penalty.fillna(0.40))
            + (1.45 * employment_risk)
        ).clip(lower=0.0, upper=8.0)
        standardized["missed_payments"] = missed_payments


def _read_tabular_dataset(dataset_path: Path) -> pd.DataFrame:
    signature = dataset_path.read_bytes()[:4]
    suffix = dataset_path.suffix.lower()

    # Some spreadsheet files are renamed as .csv; ZIP signature indicates workbook format.
    if signature.startswith(b"PK") or suffix in {".xlsx", ".xls"}:
        return pd.read_excel(dataset_path, engine="openpyxl")

    parse_attempts = [
        ("utf-8", ","),
        ("utf-8-sig", ","),
        ("cp1252", ","),
        ("latin1", ","),
        ("utf-8", ";"),
        ("cp1252", ";"),
        ("latin1", ";"),
        ("utf-8", "\t"),
        ("cp1252", "\t"),
    ]

    best_dataframe: Optional[pd.DataFrame] = None
    best_column_count = 0
    for encoding, separator in parse_attempts:
        try:
            candidate = pd.read_csv(dataset_path, encoding=encoding, sep=separator)
            if candidate.shape[1] > best_column_count:
                best_dataframe = candidate
                best_column_count = candidate.shape[1]
        except Exception:
            continue

    if best_dataframe is not None and best_column_count > 1:
        return best_dataframe

    return pd.read_csv(dataset_path, encoding="latin1")


def _derive_repayment_history_from_months(dataframe: pd.DataFrame) -> Optional[pd.Series]:
    month_columns = [
        column for column in dataframe.columns if _normalize_column_name(column).startswith("month")
    ]
    if not month_columns:
        return None

    month_values = dataframe[month_columns].astype(str).apply(lambda series: series.str.strip().str.lower())
    month_values = month_values.replace(
        {
            "on-time": 1.0,
            "on time": 1.0,
            "ontime": 1.0,
            "paid": 1.0,
            "late": 0.4,
            "missed": 0.0,
            "default": 0.0,
        }
    )
    numeric_month_values = month_values.apply(pd.to_numeric, errors="coerce")
    repayment_history = numeric_month_values.mean(axis=1, skipna=True)

    if repayment_history.notna().sum() == 0:
        return None

    return repayment_history.clip(lower=0.0, upper=1.0)


def _standardize_schema(dataframe: pd.DataFrame) -> pd.DataFrame:
    normalized_to_original = {
        _normalize_column_name(column): column for column in dataframe.columns
    }

    standardized = pd.DataFrame(index=dataframe.index)
    for canonical_name, aliases in COLUMN_ALIASES.items():
        source_column = None
        for alias in aliases:
            normalized_alias = _normalize_column_name(alias)
            if normalized_alias in normalized_to_original:
                source_column = normalized_to_original[normalized_alias]
                break

        if source_column is not None:
            source_series = dataframe[source_column]
            if canonical_name == TARGET_COLUMN:
                source_series = _coerce_target_series(source_series, source_column)
            standardized[canonical_name] = source_series

    if "repayment_history" not in standardized.columns:
        month_based_repayment = _derive_repayment_history_from_months(dataframe)
        if month_based_repayment is not None:
            standardized["repayment_history"] = month_based_repayment

    _derive_loan_schema_features(
        source_dataframe=dataframe,
        normalized_to_original=normalized_to_original,
        standardized=standardized,
    )

    if "repayment_history" not in standardized.columns and "missed_payments" in standardized.columns:
        missed = pd.to_numeric(standardized["missed_payments"], errors="coerce")
        repayment_history = 0.9 - (missed.clip(lower=0.0, upper=14.0) / 14.0)

        if "credit_score" in standardized.columns:
            credit_score = pd.to_numeric(standardized["credit_score"], errors="coerce")
            credit_bonus = ((credit_score - 650.0) / 700.0).clip(lower=-0.08, upper=0.12)
            repayment_history = repayment_history + credit_bonus.fillna(0.0)

        if "debt_to_income_ratio" in standardized.columns:
            dti = pd.to_numeric(standardized["debt_to_income_ratio"], errors="coerce")
            dti_penalty = ((dti - 0.7).clip(lower=0.0, upper=0.5)) * 0.12
            repayment_history = repayment_history - dti_penalty.fillna(0.0)

        standardized["repayment_history"] = repayment_history.clip(0.0, 1.0)

    return standardized


def load_financial_dataset(
    data_path: Optional[str] = None,
    sample_size: int = 2500,
    random_state: int = 42,
) -> pd.DataFrame:
    selected_path = _resolve_data_path(data_path)

    if selected_path is not None:
        source_dataframe = _read_tabular_dataset(selected_path)
        dataframe = _standardize_schema(source_dataframe)
    else:
        dataframe = generate_synthetic_dataset(sample_size=sample_size, random_state=random_state)

    missing_columns = [column for column in FEATURE_COLUMNS if column not in dataframe.columns]
    if missing_columns:
        raise ValueError(
            "Dataset missing required feature columns: "
            f"{', '.join(missing_columns)}. Available columns: {', '.join(dataframe.columns)}"
        )

    if TARGET_COLUMN not in dataframe.columns:
        dataframe[TARGET_COLUMN] = np.nan

    selected_columns = REQUIRED_COLUMNS + [
        column for column in OPTIONAL_FEATURE_COLUMNS if column in dataframe.columns
    ]
    return _sanitize_dataframe(dataframe[selected_columns])


def _derive_target_from_features(dataframe: pd.DataFrame) -> pd.Series:
    normalized_missed = _normalize_array(dataframe["missed_payments"].to_numpy(dtype=float))
    dti = dataframe["debt_to_income_ratio"].to_numpy(dtype=float)
    utilization = dataframe["credit_utilization"].to_numpy(dtype=float)
    repayment_inverse = 1.0 - dataframe["repayment_history"].to_numpy(dtype=float)

    credit_score_scaled = (dataframe["credit_score"].to_numpy(dtype=float) - 300.0) / 550.0
    credit_penalty = 1.0 - np.clip(credit_score_scaled, 0.0, 1.0)
    income_penalty = 1.0 - _normalize_array(dataframe["income"].to_numpy(dtype=float))

    proxy = (
        0.28 * normalized_missed
        + 0.26 * dti
        + 0.18 * repayment_inverse
        + 0.12 * utilization
        + 0.10 * credit_penalty
        + 0.06 * income_penalty
    )

    threshold = float(np.quantile(proxy, 0.65))
    labels = (proxy >= threshold).astype(int)

    if int(np.min(labels)) == int(np.max(labels)):
        labels = (proxy >= float(np.mean(proxy))).astype(int)

    return pd.Series(labels, index=dataframe.index, dtype=int)


def median_impute(dataframe: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Dict[str, Any]]]:
    imputed = dataframe.copy()
    report: Dict[str, Dict[str, Any]] = {}

    feature_columns = FEATURE_COLUMNS + [
        column for column in OPTIONAL_FEATURE_COLUMNS if column in imputed.columns
    ]
    for column in feature_columns:
        missing_before = int(imputed[column].isna().sum())
        median_value = float(imputed[column].median())
        if np.isnan(median_value):
            median_value = 0.0
        imputed[column] = imputed[column].fillna(median_value)
        report[column] = {
            "missing_before": float(missing_before),
            "imputed_with_median": median_value,
        }

    target_missing = int(imputed[TARGET_COLUMN].isna().sum())
    target_non_null = imputed[TARGET_COLUMN].dropna()

    if target_non_null.empty:
        imputed[TARGET_COLUMN] = _derive_target_from_features(imputed)
        report[TARGET_COLUMN] = {
            "missing_before": float(target_missing),
            "imputed_with_mode": None,
            "imputation_strategy": "derived_from_features",
        }
        return imputed, report

    target_mode = float(target_non_null.mode().iloc[0])
    if target_missing:
        imputed[TARGET_COLUMN] = imputed[TARGET_COLUMN].fillna(target_mode)

    imputed[TARGET_COLUMN] = imputed[TARGET_COLUMN].round().astype(int)

    if int(imputed[TARGET_COLUMN].nunique()) < 2:
        imputed[TARGET_COLUMN] = _derive_target_from_features(imputed)
        report[TARGET_COLUMN] = {
            "missing_before": float(target_missing),
            "imputed_with_mode": target_mode,
            "imputation_strategy": "fallback_derived_from_features",
        }
        return imputed, report

    report[TARGET_COLUMN] = {
        "missing_before": float(target_missing),
        "imputed_with_mode": target_mode,
        "imputation_strategy": "mode",
    }

    return imputed, report


def prepare_dataset(data_path: Optional[str] = None) -> PreparedDataset:
    raw_dataframe = load_financial_dataset(data_path=data_path)
    cleaned_dataframe, imputation_report = median_impute(raw_dataframe)

    return PreparedDataset(
        raw=raw_dataframe,
        cleaned=cleaned_dataframe,
        imputation_report=imputation_report,
    )


def _build_statistical_summary(dataframe: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    summary: Dict[str, Dict[str, float]] = {}

    for column in FEATURE_COLUMNS:
        series = dataframe[column]
        summary[column] = {
            "min": float(series.min()),
            "q1": float(series.quantile(0.25)),
            "median": float(series.median()),
            "mean": float(series.mean()),
            "q3": float(series.quantile(0.75)),
            "max": float(series.max()),
            "std": float(series.std(ddof=0)),
        }

    return summary


def _normalize_array(values: np.ndarray) -> np.ndarray:
    value_min = float(np.min(values))
    value_max = float(np.max(values))
    if np.isclose(value_min, value_max):
        return np.full_like(values, 0.5, dtype=float)
    return (values - value_min) / (value_max - value_min)


def _risk_proxy_probabilities(dataframe: pd.DataFrame) -> np.ndarray:
    normalized_missed = _normalize_array(dataframe["missed_payments"].to_numpy(dtype=float))
    utilization = dataframe["credit_utilization"].to_numpy(dtype=float)
    dti = dataframe["debt_to_income_ratio"].to_numpy(dtype=float)
    repayment_inverse = 1.0 - dataframe["repayment_history"].to_numpy(dtype=float)

    proxy = (
        0.35 * normalized_missed
        + 0.30 * dti
        + 0.20 * utilization
        + 0.15 * repayment_inverse
    )
    return np.clip(proxy, 0.0, 1.0)


def _categorize_risk(probabilities: np.ndarray) -> np.ndarray:
    categories = np.where(
        probabilities < 0.33,
        "low",
        np.where(probabilities <= 0.67, "medium", "high"),
    )
    return categories


def _build_utilization_vs_delinquency(dataframe: pd.DataFrame) -> list[Dict[str, Any]]:
    bins = [0.0, 0.2, 0.4, 0.6, 0.8, 1.01]
    labels = ["0-20%", "20-40%", "40-60%", "60-80%", "80-100%"]

    temp = dataframe.copy()
    temp["bucket"] = pd.cut(
        temp["credit_utilization"],
        bins=bins,
        labels=labels,
        include_lowest=True,
        right=False,
    )

    grouped = (
        temp.groupby("bucket", observed=False)[TARGET_COLUMN]
        .agg(["count", "sum", "mean"])
        .reset_index()
    )

    chart_data = []
    for row in grouped.to_dict(orient="records"):
        delinquent_count = int(row["sum"])
        total_count = int(row["count"])
        chart_data.append(
            {
                "bucket": str(row["bucket"]),
                "count": total_count,
                "delinquent": delinquent_count,
                "non_delinquent": max(total_count - delinquent_count, 0),
                "delinquent_rate": round(float(row["mean"]) * 100.0, 2),
            }
        )

    return chart_data


def build_insights_payload(
    dataframe: pd.DataFrame,
    imputation_report: Dict[str, Dict[str, Any]],
    model_metrics: Optional[Dict[str, Any]] = None,
    predicted_probabilities: Optional[np.ndarray] = None,
) -> Dict[str, Any]:
    correlations = (
        dataframe[FEATURE_COLUMNS + [TARGET_COLUMN]]
        .corr(numeric_only=True)[TARGET_COLUMN]
        .drop(TARGET_COLUMN)
        .to_dict()
    )

    behavioral_strength = float(
        np.mean([abs(float(correlations[column])) for column in BEHAVIORAL_FEATURES])
    )
    financial_strength = float(
        np.mean([abs(float(correlations[column])) for column in FINANCIAL_FEATURES])
    )

    interaction_mask = (
        (dataframe["debt_to_income_ratio"] >= 0.45)
        & (dataframe["missed_payments"] >= 2)
    )
    interaction_rate = float(
        dataframe.loc[interaction_mask, TARGET_COLUMN].mean() if interaction_mask.any() else 0.0
    )
    baseline_rate = float(dataframe[TARGET_COLUMN].mean())

    probabilities = (
        predicted_probabilities
        if predicted_probabilities is not None
        else _risk_proxy_probabilities(dataframe)
    )
    categories = _categorize_risk(np.asarray(probabilities, dtype=float))

    risk_distribution = {
        "low": int(np.sum(categories == "low")),
        "medium": int(np.sum(categories == "medium")),
        "high": int(np.sum(categories == "high")),
    }

    key_insights = [
        (
            "Behavioral features dominate risk prediction: missed_payments and repayment_history "
            f"show stronger average correlation ({behavioral_strength:.3f}) than financial metrics "
            f"({financial_strength:.3f})."
        ),
        (
            "High DTI + missed payments = high risk: customers with debt_to_income_ratio >= 45% "
            f"and 2+ missed payments show {interaction_rate * 100:.1f}% delinquency versus "
            f"{baseline_rate * 100:.1f}% baseline."
        ),
        (
            "Collections strategy should prioritize behavioral triggers (recent missed payments, "
            "weak repayment consistency) for early intervention campaigns."
        ),
    ]

    top_features = sorted(
        (
            {"feature": feature, "correlation": float(value), "abs_correlation": abs(float(value))}
            for feature, value in correlations.items()
        ),
        key=lambda item: item["abs_correlation"],
        reverse=True,
    )

    dashboard_metrics = {
        "total_customers": int(len(dataframe)),
        "high_risk_pct": round((risk_distribution["high"] / max(len(dataframe), 1)) * 100.0, 2),
        "avg_credit_score": round(float(dataframe["credit_score"].mean()), 2),
    }

    payload: Dict[str, Any] = {
        "dataset_summary": {
            "total_records": int(len(dataframe)),
            "delinquent_rate": round(float(dataframe[TARGET_COLUMN].mean()) * 100.0, 2),
            "features": FEATURE_COLUMNS,
        },
        "statistical_summary": _build_statistical_summary(dataframe),
        "imputation_report": imputation_report,
        "feature_correlations": {key: round(float(value), 4) for key, value in correlations.items()},
        "feature_importance": {
            "behavioral_strength": round(behavioral_strength, 4),
            "financial_strength": round(financial_strength, 4),
            "behavioral_dominant": behavioral_strength >= financial_strength,
            "top_features": top_features[:4],
        },
        "interaction_insights": {
            "high_dti_threshold": 0.45,
            "missed_payment_threshold": 2,
            "high_dti_and_missed_rate": round(interaction_rate * 100.0, 2),
            "baseline_delinquency_rate": round(baseline_rate * 100.0, 2),
        },
        "key_insights": key_insights,
        "dashboard_metrics": dashboard_metrics,
        "charts": {
            "risk_distribution": risk_distribution,
            "utilization_vs_delinquency": _build_utilization_vs_delinquency(dataframe),
        },
    }

    if model_metrics is not None:
        payload["model_performance"] = model_metrics

    return payload
