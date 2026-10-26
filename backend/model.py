from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import joblib
import numpy as np
import pandas as pd
import sklearn
from data_processing import (
    FEATURE_COLUMNS,
    OPTIONAL_FEATURE_COLUMNS,
    TARGET_COLUMN,
    _build_statistical_summary,
    build_insights_payload,
    prepare_dataset,
)
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ARTIFACT_PATH = Path(__file__).resolve().parent / "credit_risk_model.joblib"


class CreditFeatureTransformer(TransformerMixin, BaseEstimator):
    """Fit imputation inside each calibration fold before engineering features."""

    def fit(self, X, y=None):
        frame = self._numeric(X)
        defaults = {"age": 40.0, "loan_amount": 20_000.0, "years_experience": 10.0}
        self.medians_ = {
            column: float(frame[column].median())
            if frame[column].notna().any()
            else defaults.get(column, 0.0)
            for column in frame.columns
        }
        return self

    @staticmethod
    def _numeric(X):
        return (
            X.reindex(columns=FEATURE_COLUMNS + OPTIONAL_FEATURE_COLUMNS)
            .apply(pd.to_numeric, errors="coerce")
            .replace([np.inf, -np.inf], np.nan)
        )

    def transform(self, X):
        return CreditRiskModel._augment_model_features(
            self._numeric(X).fillna(self.medians_)
        )


class CreditRiskModel:
    def __init__(
        self,
        low_threshold: float = 0.33,
        high_threshold: float = 0.67,
        missed_payments_override_threshold: int = 5,
    ) -> None:
        self.feature_columns = FEATURE_COLUMNS
        self.optional_feature_columns = OPTIONAL_FEATURE_COLUMNS
        self.low_threshold = low_threshold
        self.high_threshold = high_threshold
        self.override_threshold = missed_payments_override_threshold

        self.model = LogisticRegression(
            max_iter=2600, C=1.0, class_weight="balanced", random_state=42
        )
        self.selected_model_name = "logistic_regression"
        self.feature_signal_type = "coefficient"
        self.model_input_columns = list(self.feature_columns)
        self.decision_threshold = 0.5
        self.low_quantile = 0.30
        self.high_quantile = 0.75
        self.optional_feature_defaults = {
            "age": 40.0,
            "loan_amount": 20_000.0,
            "years_experience": 10.0,
        }
        self.metrics: Dict[str, Any] = {}
        self.is_trained = False
        self.use_business_calibration = False
        self.imputation_values: Dict[str, float] = {}
        self.candidates: Dict[str, Dict[str, Any]] = {}
        self.data_provenance: Dict[str, Any] = {}
        self.dataset_fingerprint: Optional[str] = None

    def _target_direction_diagnostics(self, dataframe: pd.DataFrame) -> Dict[str, Any]:
        expected_signs = {
            "income": -1.0,
            "credit_score": -1.0,
            "credit_utilization": 1.0,
            "debt_to_income_ratio": 1.0,
            "missed_payments": 1.0,
            "repayment_history": -1.0,
        }

        correlations = (
            dataframe[self.feature_columns + [TARGET_COLUMN]]
            .corr(numeric_only=True)[TARGET_COLUMN]
            .drop(TARGET_COLUMN)
            .fillna(0.0)
            .to_dict()
        )

        alignment_score = 0.0
        for feature, expected_sign in expected_signs.items():
            value = float(correlations.get(feature, 0.0))
            if not np.isclose(value, 0.0):
                alignment_score += float(np.sign(value) * expected_sign)

        avg_abs_corr = float(
            np.mean([abs(float(value)) for value in correlations.values()])
        )
        return {
            "correlations": {
                feature: float(value) for feature, value in correlations.items()
            },
            "alignment_score": alignment_score,
            "avg_abs_corr": avg_abs_corr,
        }

    def _business_risk_index(self, feature_values: Dict[str, float]) -> float:
        income = float(np.clip(feature_values["income"], 18_000.0, 250_000.0))
        credit_score = float(np.clip(feature_values["credit_score"], 300.0, 850.0))
        utilization = float(np.clip(feature_values["credit_utilization"], 0.0, 1.0))
        dti = float(np.clip(feature_values["debt_to_income_ratio"], 0.0, 1.5))
        missed = float(np.clip(feature_values["missed_payments"], 0.0, 60.0))
        repayment = float(np.clip(feature_values["repayment_history"], 0.0, 1.0))

        income_norm = (income - 18_000.0) / (250_000.0 - 18_000.0)
        credit_norm = (credit_score - 300.0) / 550.0
        missed_norm = min(missed / 6.0, 1.0)
        dti_norm = dti / 1.5

        index = (
            0.03
            + (0.20 * dti_norm)
            + (0.18 * utilization)
            + (0.20 * missed_norm)
            + (0.17 * (1.0 - repayment))
            + (0.16 * (1.0 - credit_norm))
            + (0.09 * (1.0 - income_norm))
        )
        return float(np.clip(index, 0.01, 0.99))

    def _stress_signal_count(self, feature_values: Dict[str, float]) -> int:
        signals = 0
        if float(feature_values["debt_to_income_ratio"]) >= 0.8:
            signals += 1
        if float(feature_values["credit_utilization"]) >= 0.7:
            signals += 1
        if float(feature_values["missed_payments"]) >= 3.0:
            signals += 1
        if float(feature_values["repayment_history"]) <= 0.72:
            signals += 1
        if float(feature_values["credit_score"]) <= 640.0:
            signals += 1
        return signals

    def _calibrate_probability(
        self, model_probability: float, feature_values: Dict[str, float]
    ) -> tuple[float, float]:
        business_index = self._business_risk_index(feature_values)
        stress_signals = self._stress_signal_count(feature_values)
        divergence = abs(float(model_probability) - float(business_index))

        if self.use_business_calibration:
            model_weight = 0.30
            business_weight = 0.70
        else:
            model_weight = 0.60
            business_weight = 0.40

        if stress_signals >= 2:
            model_weight = min(model_weight, 0.52)
            business_weight = max(business_weight, 0.48)

        # In visibly stressed profiles, rely less on a potentially overconfident low model output.
        if stress_signals >= 3:
            model_weight = min(model_weight, 0.42)
            business_weight = max(business_weight, 0.58)

        # Moderate disagreement should already lean toward business calibration.
        if divergence >= 0.32 and business_index >= 0.55:
            model_weight = min(model_weight, 0.38)
            business_weight = max(business_weight, 0.62)

        # Symmetric divergence guard: prevent a single model-side spike from dominating all factors.
        if divergence >= 0.40 and model_probability >= business_index + 0.12:
            model_weight = min(model_weight, 0.34)
            business_weight = max(business_weight, 0.66)
        elif (
            divergence >= 0.40
            and business_index >= model_probability + 0.12
            and (stress_signals >= 2 or business_index >= 0.58)
        ):
            model_weight = min(model_weight, 0.34)
            business_weight = max(business_weight, 0.66)

        # Handle large disagreement by leaning toward business risk calibration.
        if divergence >= 0.45 and business_index >= 0.65:
            model_weight = min(model_weight, 0.26)
            business_weight = max(business_weight, 0.74)

        weight_total = model_weight + business_weight
        calibrated_probability = (model_weight / weight_total) * model_probability + (
            business_weight / weight_total
        ) * business_index

        return float(np.clip(calibrated_probability, 0.01, 0.99)), business_index

    def _apply_high_risk_override(
        self,
        probability: float,
        model_probability: float,
        business_risk_index: float,
        feature_values: Dict[str, float],
    ) -> tuple[float, bool, Optional[str]]:
        adjusted_probability = float(probability)
        override_reason: Optional[str] = None

        dti = float(feature_values["debt_to_income_ratio"])
        utilization = float(feature_values["credit_utilization"])
        missed = float(feature_values["missed_payments"])
        repayment = float(feature_values["repayment_history"])
        stress_signals = self._stress_signal_count(feature_values)

        if missed > self.override_threshold:
            adjusted_probability = max(adjusted_probability, 0.75)
            override_reason = "Rule override applied: missed_payments exceeded threshold (>5), forcing high risk."
        elif dti >= 1.0 and missed >= 3.0 and repayment <= 0.72:
            adjusted_probability = max(adjusted_probability, 0.72)
            override_reason = (
                "Rule override applied: severe debt stress pattern detected (DTI >= 100%, "
                "missed_payments >= 3, repayment_history <= 72%)."
            )
        elif stress_signals >= 4 and business_risk_index >= 0.70:
            adjusted_probability = max(adjusted_probability, 0.70)
            override_reason = "Rule override applied: multiple stress signals with elevated business risk index."
        elif (
            stress_signals >= 3
            and business_risk_index >= 0.80
            and model_probability <= 0.12
            and (dti >= 0.75 or utilization >= 0.75)
        ):
            adjusted_probability = max(adjusted_probability, 0.68)
            override_reason = "Rule override applied: strong model-business divergence under a stressed profile."

        return adjusted_probability, override_reason is not None, override_reason

    def _base_feature_frame(
        self, dataframe: pd.DataFrame, fit_defaults: bool = False
    ) -> pd.DataFrame:
        missing = set(self.feature_columns) - set(dataframe.columns)
        if missing:
            raise ValueError(f"Missing features: {', '.join(sorted(missing))}")
        columns = self.feature_columns + self.optional_feature_columns
        base = dataframe.reindex(columns=columns).apply(pd.to_numeric, errors="coerce")
        base = base.replace([np.inf, -np.inf], np.nan)
        if fit_defaults:
            self.imputation_values = {
                column: float(base[column].median())
                if base[column].notna().any()
                else float(self.optional_feature_defaults.get(column, 0.0))
                for column in columns
            }
            self.optional_feature_defaults.update(
                {c: self.imputation_values[c] for c in self.optional_feature_columns}
            )
        defaults = {**self.optional_feature_defaults, **self.imputation_values}
        return base.fillna(defaults)

    @staticmethod
    def _augment_model_features(base_features: pd.DataFrame) -> pd.DataFrame:
        model_features = base_features.copy()

        model_features["utilization_dti_interaction"] = (
            model_features["credit_utilization"]
            * model_features["debt_to_income_ratio"]
        )
        model_features["payment_stress_index"] = (
            model_features["missed_payments"] / 12.0
        ) * (1.0 - model_features["repayment_history"])
        model_features["credit_pressure"] = (
            (850.0 - model_features["credit_score"]) / 550.0
        ).clip(lower=0.0, upper=1.0)
        model_features["income_buffer"] = (
            (model_features["income"] - 18_000.0) / 232_000.0
        ).clip(lower=0.0, upper=1.0)
        model_features["credit_income_pressure"] = model_features["credit_pressure"] * (
            1.0 - model_features["income_buffer"]
        )
        model_features["loan_to_income_ratio_raw"] = (
            model_features["loan_amount"] / np.maximum(model_features["income"], 1.0)
        ).clip(lower=0.0, upper=3.0)
        model_features["experience_credit_buffer"] = (
            model_features["years_experience"] / 30.0
        ).clip(lower=0.0, upper=1.0) * (model_features["credit_score"] / 850.0)

        return model_features

    def _align_model_frame(self, model_features: pd.DataFrame) -> pd.DataFrame:
        aligned = model_features.copy()
        for column in self.model_input_columns:
            if column not in aligned.columns:
                aligned[column] = 0.0
        return aligned[self.model_input_columns]

    def _select_decision_threshold(
        self, y_true: pd.Series, probabilities: np.ndarray
    ) -> tuple[float, float, float]:
        best_threshold = 0.5
        best_accuracy = -1.0
        best_balanced = -1.0
        best_f1 = -1.0

        for threshold in np.linspace(0.05, 0.95, 91):
            predictions = (probabilities >= threshold).astype(int)
            accuracy = float(accuracy_score(y_true, predictions))
            f1_value = float(f1_score(y_true, predictions, zero_division=0))

            balanced = float(balanced_accuracy_score(y_true, predictions))
            if (f1_value, balanced) > (best_f1, best_balanced):
                best_balanced = balanced
                best_accuracy = accuracy
                best_f1 = f1_value
                best_threshold = float(threshold)

        return best_threshold, best_accuracy, best_f1

    def _update_risk_band_thresholds(self, probabilities: np.ndarray) -> None:
        if probabilities.size == 0:
            return

        low = float(np.quantile(probabilities, self.low_quantile))
        high = float(np.quantile(probabilities, self.high_quantile))

        low = float(np.clip(low, 0.15, 0.60))
        high = float(np.clip(high, max(low + 0.12, 0.35), 0.92))

        if high <= low:
            high = float(min(0.92, low + 0.2))

        self.low_threshold = low
        self.high_threshold = high

    def _candidate_models(self) -> Dict[str, Any]:
        return {
            "logistic_regression": LogisticRegression(
                max_iter=2600,
                C=1.0,
                class_weight="balanced",
                random_state=42,
            ),
            "random_forest": RandomForestClassifier(
                n_estimators=420,
                max_depth=None,
                min_samples_split=8,
                min_samples_leaf=3,
                class_weight="balanced_subsample",
                random_state=42,
                n_jobs=-1,
            ),
            "gradient_boosting": GradientBoostingClassifier(
                n_estimators=240,
                learning_rate=0.05,
                max_depth=3,
                random_state=42,
            ),
        }

    @staticmethod
    def _evaluate(
        target: pd.Series, probabilities: np.ndarray, threshold: float
    ) -> Dict[str, float]:
        predictions = probabilities >= threshold
        return {
            "accuracy": round(float(accuracy_score(target, predictions)), 4),
            "balanced_accuracy": round(
                float(balanced_accuracy_score(target, predictions)), 4
            ),
            "precision": round(
                float(precision_score(target, predictions, zero_division=0)), 4
            ),
            "recall": round(
                float(recall_score(target, predictions, zero_division=0)), 4
            ),
            "f1_score": round(float(f1_score(target, predictions, zero_division=0)), 4),
            "roc_auc": round(float(roc_auc_score(target, probabilities)), 4),
            "average_precision": round(
                float(average_precision_score(target, probabilities)), 4
            ),
            "brier_score": round(float(brier_score_loss(target, probabilities)), 4),
        }

    def train(self, dataframe: pd.DataFrame) -> Dict[str, Any]:
        if not dataframe[TARGET_COLUMN].isin([0, 1]).all():
            raise ValueError("Training labels must be known binary outcomes.")
        counts = dataframe[TARGET_COLUMN].value_counts()
        if len(dataframe) < 40 or len(counts) != 2 or counts.min() < 8:
            raise ValueError(
                "Training requires at least 40 labeled rows and 8 examples of each class."
            )
        self.data_provenance = dataframe.attrs.get("provenance", {})
        train_valid, test = train_test_split(
            dataframe, test_size=0.2, random_state=42, stratify=dataframe[TARGET_COLUMN]
        )
        train, valid = train_test_split(
            train_valid,
            test_size=0.2,
            random_state=42,
            stratify=train_valid[TARGET_COLUMN],
        )
        # All learned defaults, diagnostics, scaling and calibration see training rows only.
        train_base = self._base_feature_frame(train, fit_defaults=True)
        diagnostics = self._target_direction_diagnostics(
            train_base.assign(**{TARGET_COLUMN: train[TARGET_COLUMN]})
        )
        self.use_business_calibration = (
            diagnostics["alignment_score"] < 1.0 or diagnostics["avg_abs_corr"] < 0.08
        )
        train_features = self._augment_model_features(train_base)
        self.model_input_columns = list(train_features.columns)
        x_train, x_valid, x_test = (
            CreditFeatureTransformer._numeric(frame) for frame in (train, valid, test)
        )
        y_train, y_valid, y_test = (
            train[TARGET_COLUMN].astype(int),
            valid[TARGET_COLUMN].astype(int),
            test[TARGET_COLUMN].astype(int),
        )
        candidate_metrics = {}
        self.candidates = {}
        best_key = None
        selected = None
        for name, estimator in self._candidate_models().items():
            pipeline = Pipeline(
                [
                    ("features", CreditFeatureTransformer()),
                    ("scaler", StandardScaler()),
                    ("estimator", estimator),
                ]
            )
            calibrated = CalibratedClassifierCV(pipeline, method="sigmoid", cv=3)
            calibrated.fit(x_train, y_train)
            probabilities = calibrated.predict_proba(x_valid)[:, 1]
            threshold, _, _ = self._select_decision_threshold(y_valid, probabilities)
            validation = self._evaluate(y_valid, probabilities, threshold)
            candidate_metrics[name] = {
                **{f"validation_{key}": value for key, value in validation.items()},
                "roc_auc": validation["roc_auc"],
                "decision_threshold": threshold,
            }
            self.model = calibrated
            self.decision_threshold = threshold
            self.is_trained = True
            # Bands are frozen from validation scores, never from the test set or live uploads.
            self._update_risk_band_thresholds(self.score_dataframe(valid))
            operational_threshold, _, _ = self._select_decision_threshold(
                y_valid, self.score_dataframe(valid)
            )
            warnings = []
            if self.data_provenance.get("target_kind") != "observed_delinquency":
                warnings.append(
                    "Labels are proxy or synthetic outcomes, not observed delinquency."
                )
            if validation["average_precision"] < 1.5 * float(y_valid.mean()):
                warnings.append(
                    "Weak validation discrimination: average precision is below 1.5 times class prevalence."
                )
            test_probabilities = calibrated.predict_proba(x_test)[:, 1]
            metrics = {
                **self._evaluate(y_test, test_probabilities, threshold),
                "operational_metrics": {
                    **self._evaluate(
                        y_test, self.score_dataframe(test), operational_threshold
                    ),
                    "decision_threshold": operational_threshold,
                },
                "quality_warnings": warnings,
                "baseline_metrics": {
                    "accuracy": round(float(1 - y_test.mean()), 4),
                    "average_precision": round(float(y_test.mean()), 4),
                    "brier_score": round(
                        float(
                            brier_score_loss(
                                y_test, np.full(len(y_test), y_train.mean())
                            )
                        ),
                        4,
                    ),
                },
                "decision_threshold": threshold,
                "low_risk_threshold": self.low_threshold,
                "high_risk_threshold": self.high_threshold,
                "selected_model": name,
                "train_size": len(train),
                "validation_size": len(valid),
                "test_size": len(test),
                "evaluation_scope": "untouched_stratified_test_set",
                "selection_metric": "validation_average_precision_then_f1",
                "validation_roc_auc": validation["roc_auc"],
                "validation_average_precision": validation["average_precision"],
                "class_prevalence": round(float(y_test.mean()), 4),
                "calibration_mode": "sigmoid_cv3_then_business_policy",
                "score_semantics": "Business-adjusted risk score; model_probability is the calibrated model estimate.",
                "training_baseline": _build_statistical_summary(train_base),
                "feature_signal_type": "median_replacement_sensitivity",
                "directional_alignment_score": diagnostics["alignment_score"],
                "data_provenance": self.data_provenance,
            }
            self.candidates[name] = {
                "model": calibrated,
                "metrics": metrics,
                "low_threshold": self.low_threshold,
                "high_threshold": self.high_threshold,
                "decision_threshold": threshold,
            }
            key = (
                validation["average_precision"],
                validation["f1_score"],
                validation["roc_auc"],
            )
            if best_key is None or key > best_key:
                best_key, selected = key, name
        for bundle in self.candidates.values():
            bundle["metrics"]["model_candidates"] = candidate_metrics
        self.activate_candidate(selected)
        return self.metrics

    def activate_candidate(self, name: str) -> None:
        if name not in self.candidates:
            raise ValueError(f"No fitted artifact for candidate {name}.")
        bundle = self.candidates[name]
        self.model = bundle["model"]
        self.metrics = bundle["metrics"]
        self.selected_model_name = name
        self.decision_threshold = bundle["decision_threshold"]
        self.low_threshold, self.high_threshold = (
            bundle["low_threshold"],
            bundle["high_threshold"],
        )
        self.feature_signal_type = "median_replacement_sensitivity"

    def score_records(self, dataframe: pd.DataFrame) -> list[Dict[str, Any]]:
        if not self.is_trained:
            raise RuntimeError("Model must be trained before scoring.")
        if dataframe.empty:
            return []
        base = self._base_feature_frame(dataframe)
        raw = self.model.predict_proba(CreditFeatureTransformer._numeric(dataframe))[
            :, 1
        ]
        scores = []
        for row, probability in zip(
            base[self.feature_columns].to_dict(orient="records"), raw
        ):
            adjusted, business_index = self._calibrate_probability(
                float(probability), row
            )
            adjusted, override, reason = self._apply_high_risk_override(
                adjusted, float(probability), business_index, row
            )
            category, category_override, category_reason = self._risk_category(
                adjusted, row["missed_payments"]
            )
            if override:
                category = "high"
            scores.append(
                {
                    "risk_probability": round(adjusted, 4),
                    "risk_score": round(adjusted * 100, 2),
                    "model_probability": round(float(probability), 4),
                    "business_risk_index": round(business_index, 4),
                    "risk_category": category,
                    "override_applied": override or category_override,
                    "override_reason": reason or category_reason,
                }
            )
        return scores

    def score_dataframe(self, dataframe: pd.DataFrame) -> np.ndarray:
        return np.asarray(
            [row["risk_probability"] for row in self.score_records(dataframe)],
            dtype=float,
        )

    def _risk_category(
        self, probability: float, missed_payments: float
    ) -> tuple[str, bool, Optional[str]]:
        if probability < self.low_threshold:
            category = "low"
        elif probability <= self.high_threshold:
            category = "medium"
        else:
            category = "high"

        override_applied = False
        override_reason: Optional[str] = None
        if missed_payments > self.override_threshold:
            category = "high"
            override_applied = True
            override_reason = "Rule override applied: missed_payments exceeded threshold (>5), forcing high risk."

        return category, override_applied, override_reason

    def _format_driver_name(self, driver: str) -> str:
        labels = {
            "debt_to_income_ratio": "debt-to-income ratio",
            "credit_utilization": "credit utilization",
            "missed_payments": "missed payments",
            "repayment_history": "repayment history",
            "loan_amount": "loan amount",
            "years_experience": "years of experience",
            "utilization_dti_interaction": "utilization and DTI interaction",
            "payment_stress_index": "payment stress index",
            "credit_income_pressure": "credit-income pressure",
            "loan_to_income_ratio_raw": "loan-to-income ratio",
            "experience_credit_buffer": "experience-credit buffer",
        }
        return labels.get(driver, driver.replace("_", " "))

    def _top_driver_impacts(
        self, feature_values: Dict[str, float], limit: int = 5
    ) -> list[Dict[str, Any]]:
        # Local sensitivity, not SHAP: replace one original feature with its training median.
        base = (
            CreditFeatureTransformer._numeric(pd.DataFrame([feature_values]))
            .iloc[0]
            .to_dict()
        )
        rows = [base] + [
            {
                **base,
                column: self.imputation_values.get(
                    column, self.optional_feature_defaults.get(column, 0.0)
                ),
            }
            for column in self.feature_columns + self.optional_feature_columns
        ]
        probabilities = self.model.predict_proba(pd.DataFrame(rows))[:, 1]
        impacts = [
            {
                "feature": self._format_driver_name(column),
                "impact": round(float(probabilities[0] - probability), 4),
                "direction": "risk_up"
                if probabilities[0] >= probability
                else "risk_down",
                "method": "median_replacement_sensitivity",
            }
            for column, probability in zip(
                self.feature_columns + self.optional_feature_columns, probabilities[1:]
            )
        ]
        return sorted(impacts, key=lambda row: abs(row["impact"]), reverse=True)[:limit]

    def _rank_drivers(self, feature_values: Dict[str, float]) -> list[str]:
        ranked = self._top_driver_impacts(feature_values=feature_values, limit=3)
        if ranked:
            return [str(item["feature"]) for item in ranked]

        return [self._format_driver_name(name) for name in self.feature_columns[:3]]

    def _build_explanation(
        self,
        feature_values: Dict[str, float],
        probability: float,
        category: str,
        override_applied: bool,
        override_reason: Optional[str],
    ) -> str:
        if override_applied:
            if override_reason:
                return (
                    f"High risk with a {probability * 100:.1f}/100 business-adjusted risk score. "
                    f"{override_reason}"
                )
            return (
                "High risk due to high missed payments and DTI pressure. "
                "Rule-based override elevated this customer to high risk because missed_payments exceeds 5."
            )

        reasons = []
        if feature_values["missed_payments"] >= 3:
            reasons.append("frequent missed payments")
        if feature_values["debt_to_income_ratio"] >= 0.45:
            reasons.append("elevated debt-to-income ratio")
        if feature_values["credit_utilization"] >= 0.75:
            reasons.append("high credit utilization")
        if feature_values["repayment_history"] <= 0.7:
            reasons.append("weak repayment history")

        if not reasons and category == "low":
            return (
                f"Low risk profile with a {probability * 100:.1f}/100 business-adjusted risk score. "
                "Consistent repayment behavior and controlled leverage are protective signals."
            )

        top_drivers = self._rank_drivers(feature_values)
        driver_text = ", ".join(top_drivers)
        reason_text = ", ".join(reasons[:2]) if reasons else "mixed financial behavior"

        return (
            f"{category.title()} risk with a {probability * 100:.1f}/100 business-adjusted risk score, "
            f"driven by {reason_text}. Top model drivers: {driver_text}."
        )

    def _recommend_collections_strategy(
        self,
        feature_values: Dict[str, float],
        category: str,
        probability: float,
    ) -> Dict[str, Any]:
        missed = float(feature_values["missed_payments"])
        dti = float(feature_values["debt_to_income_ratio"])
        repayment = float(feature_values["repayment_history"])
        utilization = float(feature_values["credit_utilization"])

        if category == "high":
            if missed >= 5 or dti >= 1.0:
                return {
                    "strategy": "Restructure Outreach",
                    "priority": "immediate",
                    "next_steps": [
                        "Assign specialist collector",
                        "Offer hardship or restructuring options",
                        "Schedule follow-up within 24 hours",
                    ],
                }

            return {
                "strategy": "Intensive Contact Plan",
                "priority": "high",
                "next_steps": [
                    "Initiate multi-channel outreach",
                    "Set promise-to-pay checkpoint",
                    "Review account in 48 hours",
                ],
            }

        if category == "medium":
            if repayment < 0.75 or utilization > 0.7:
                return {
                    "strategy": "Preventive Stabilization",
                    "priority": "medium",
                    "next_steps": [
                        "Send proactive reminder",
                        "Offer payment calendar support",
                        "Monitor for 2 billing cycles",
                    ],
                }

            return {
                "strategy": "Watchlist Monitoring",
                "priority": "medium",
                "next_steps": [
                    "Maintain weekly monitoring",
                    "Trigger alert if risk increases by 10 points",
                    "Confirm contact details",
                ],
            }

        return {
            "strategy": "Routine Monitoring",
            "priority": "low",
            "next_steps": [
                "Keep standard reminders",
                "Reassess on major profile changes",
                "Promote digital self-service payments",
            ],
        }

    def predict(self, feature_values: Dict[str, float]) -> Dict[str, Any]:
        if not self.is_trained:
            raise RuntimeError("Model is not trained yet.")

        canonical_values = (
            self._base_feature_frame(pd.DataFrame([feature_values])).iloc[0].to_dict()
        )
        score = self.score_records(pd.DataFrame([feature_values]))[0]
        probability, category = score["risk_probability"], score["risk_category"]
        override_applied, override_reason = (
            score["override_applied"],
            score["override_reason"],
        )
        explanation = self._build_explanation(
            feature_values=canonical_values,
            probability=probability,
            category=category,
            override_applied=override_applied,
            override_reason=override_reason,
        )
        top_drivers = self._top_driver_impacts(feature_values=feature_values, limit=5)
        collections_strategy = self._recommend_collections_strategy(
            feature_values=canonical_values,
            category=category,
            probability=probability,
        )

        return {
            **score,
            "explanation_method": "median_replacement_sensitivity",
            "score_semantics": self.metrics.get("score_semantics"),
            "data_provenance": self.data_provenance,
            "top_drivers": top_drivers,
            "collections_strategy": collections_strategy,
            "explanation": explanation,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def save(self, artifact_path: Optional[Path] = None) -> None:
        payload = {
            "artifact_version": 3,
            "dataset_fingerprint": self.dataset_fingerprint,
            "imputation_values": self.imputation_values,
            "candidates": self.candidates,
            "data_provenance": self.data_provenance,
            "feature_columns": self.feature_columns,
            "optional_feature_columns": self.optional_feature_columns,
            "optional_feature_defaults": self.optional_feature_defaults,
            "model_input_columns": self.model_input_columns,
            "decision_threshold": self.decision_threshold,
            "low_threshold": self.low_threshold,
            "high_threshold": self.high_threshold,
            "low_quantile": self.low_quantile,
            "high_quantile": self.high_quantile,
            "override_threshold": self.override_threshold,
            "model": self.model,
            "selected_model_name": self.selected_model_name,
            "feature_signal_type": self.feature_signal_type,
            "metrics": self.metrics,
            "is_trained": self.is_trained,
            "use_business_calibration": self.use_business_calibration,
        }
        artifact_path = Path(artifact_path or ARTIFACT_PATH)
        handle, temporary = tempfile.mkstemp(dir=artifact_path.parent, suffix=".tmp")
        os.close(handle)
        try:
            joblib.dump(payload, temporary)
            os.replace(temporary, artifact_path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def load(self, artifact_path: Optional[Path] = None) -> None:
        payload = joblib.load(artifact_path or ARTIFACT_PATH)
        self.dataset_fingerprint = payload.get("dataset_fingerprint")
        self.imputation_values = payload.get("imputation_values", {})
        self.candidates = payload.get("candidates", {})
        self.data_provenance = payload.get("data_provenance", {})
        self.feature_columns = payload["feature_columns"]
        self.optional_feature_columns = payload.get(
            "optional_feature_columns", OPTIONAL_FEATURE_COLUMNS
        )
        self.optional_feature_defaults = payload.get(
            "optional_feature_defaults",
            {
                "age": 40.0,
                "loan_amount": 20_000.0,
                "years_experience": 10.0,
            },
        )
        self.model_input_columns = payload.get(
            "model_input_columns", list(self.feature_columns)
        )
        self.decision_threshold = payload.get("decision_threshold", 0.5)
        self.low_threshold = payload["low_threshold"]
        self.high_threshold = payload["high_threshold"]
        self.low_quantile = float(payload.get("low_quantile", 0.30))
        self.high_quantile = float(payload.get("high_quantile", 0.75))
        self.override_threshold = payload["override_threshold"]
        self.model = payload["model"]
        self.selected_model_name = payload.get(
            "selected_model_name", "logistic_regression"
        )
        self.feature_signal_type = payload.get("feature_signal_type", "coefficient")
        self.metrics = payload.get("metrics", {})
        self.is_trained = payload.get("is_trained", False)
        self.use_business_calibration = payload.get("use_business_calibration", False)


def initialize_model_system(data_path: Optional[str] = None) -> Dict[str, Any]:
    prepared = prepare_dataset(data_path=data_path)

    model = CreditRiskModel(
        low_threshold=0.33,
        high_threshold=0.67,
        missed_payments_override_threshold=5,
    )
    fingerprint = hashlib.sha256(
        pd.util.hash_pandas_object(prepared.raw, index=True).values.tobytes()
    )
    fingerprint.update(json.dumps(prepared.raw.attrs, sort_keys=True).encode())
    for path in (Path(__file__), Path(__file__).with_name("data_processing.py")):
        fingerprint.update(path.read_bytes())
    fingerprint.update(
        f"{sklearn.__version__}:{pd.__version__}:{np.__version__}".encode()
    )
    expected_fingerprint = fingerprint.hexdigest()
    cached = False
    if ARTIFACT_PATH.exists():
        try:
            model.load()
            cached = model.dataset_fingerprint == expected_fingerprint and bool(
                model.candidates
            )
        except Exception:
            logging.getLogger(__name__).warning(
                "Cached model could not be loaded; retraining.", exc_info=True
            )
    if not cached:
        model = CreditRiskModel()
        model_metrics = model.train(prepared.raw)
        model.dataset_fingerprint = expected_fingerprint
    else:
        model_metrics = model.metrics

    dataset = model._base_feature_frame(prepared.raw)
    dataset[TARGET_COLUMN] = prepared.raw[TARGET_COLUMN]
    dataset["account_id"] = prepared.raw["account_id"]
    dataset.attrs = prepared.raw.attrs
    for column, median in model.imputation_values.items():
        prepared.imputation_report[column] = {
            "missing_before": int(prepared.raw[column].isna().sum())
            if column in prepared.raw
            else len(prepared.raw),
            "imputed_with_median": median,
            "fit_scope": "training_split_only",
        }
    portfolio_scores = model.score_records(prepared.raw)
    predicted_probabilities = np.asarray(
        [score["risk_probability"] for score in portfolio_scores]
    )
    insights = build_insights_payload(
        dataframe=dataset,
        imputation_report=prepared.imputation_report,
        model_metrics=model_metrics,
        predicted_probabilities=predicted_probabilities,
        predicted_categories=[score["risk_category"] for score in portfolio_scores],
    )

    if not cached:
        model.save()

    return {
        "model": model,
        "insights": insights,
        "dataset": prepared.raw,
    }
