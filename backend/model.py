from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

from data_processing import (
    FEATURE_COLUMNS,
    OPTIONAL_FEATURE_COLUMNS,
    TARGET_COLUMN,
    build_insights_payload,
    prepare_dataset,
)

ARTIFACT_PATH = Path(__file__).resolve().parent / "credit_risk_model.joblib"


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

        self.scaler = StandardScaler()
        self.model = LogisticRegression(max_iter=2600, C=1.0, class_weight="balanced", random_state=42)
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
            .to_dict()
        )

        alignment_score = 0.0
        for feature, expected_sign in expected_signs.items():
            value = float(correlations.get(feature, 0.0))
            if not np.isclose(value, 0.0):
                alignment_score += float(np.sign(value) * expected_sign)

        avg_abs_corr = float(np.mean([abs(float(value)) for value in correlations.values()]))
        return {
            "correlations": {feature: float(value) for feature, value in correlations.items()},
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

        index = (
            0.05
            + (0.24 * dti)
            + (0.22 * utilization)
            + (0.26 * missed_norm)
            + (0.18 * (1.0 - repayment))
            + (0.07 * (1.0 - credit_norm))
            + (0.05 * (1.0 - income_norm))
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

    def _calibrate_probability(self, model_probability: float, feature_values: Dict[str, float]) -> tuple[float, float]:
        business_index = self._business_risk_index(feature_values)
        stress_signals = self._stress_signal_count(feature_values)
        divergence = abs(float(model_probability) - float(business_index))

        if self.use_business_calibration:
            model_weight = 0.35
            business_weight = 0.65
        else:
            model_weight = 0.7
            business_weight = 0.3

        # In visibly stressed profiles, rely less on a potentially overconfident low model output.
        if stress_signals >= 3:
            model_weight = min(model_weight, 0.45)
            business_weight = max(business_weight, 0.55)

        # Handle large disagreement by leaning toward business risk calibration.
        if divergence >= 0.45 and business_index >= 0.65:
            model_weight = min(model_weight, 0.30)
            business_weight = max(business_weight, 0.70)

        weight_total = model_weight + business_weight
        calibrated_probability = (
            (model_weight / weight_total) * model_probability
            + (business_weight / weight_total) * business_index
        )

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
            override_reason = (
                "Rule override applied: missed_payments exceeded threshold (>5), forcing high risk."
            )
        elif dti >= 1.0 and missed >= 3.0 and repayment <= 0.72:
            adjusted_probability = max(adjusted_probability, 0.72)
            override_reason = (
                "Rule override applied: severe debt stress pattern detected (DTI >= 100%, "
                "missed_payments >= 3, repayment_history <= 72%)."
            )
        elif stress_signals >= 4 and business_risk_index >= 0.70:
            adjusted_probability = max(adjusted_probability, 0.70)
            override_reason = (
                "Rule override applied: multiple stress signals with elevated business risk index."
            )
        elif (
            stress_signals >= 3
            and business_risk_index >= 0.80
            and model_probability <= 0.12
            and (dti >= 0.75 or utilization >= 0.75)
        ):
            adjusted_probability = max(adjusted_probability, 0.68)
            override_reason = (
                "Rule override applied: strong model-business divergence under a stressed profile."
            )

        return adjusted_probability, override_reason is not None, override_reason

    def _base_feature_frame(self, dataframe: pd.DataFrame, fit_defaults: bool = False) -> pd.DataFrame:
        base = dataframe[self.feature_columns].copy()

        for column in self.optional_feature_columns:
            if column in dataframe.columns:
                base[column] = pd.to_numeric(dataframe[column], errors="coerce")
            else:
                base[column] = np.nan

        if fit_defaults:
            for column in self.optional_feature_columns:
                median_value = float(base[column].median(skipna=True))
                if np.isnan(median_value):
                    median_value = float(self.optional_feature_defaults.get(column, 0.0))
                self.optional_feature_defaults[column] = median_value

        for column in self.optional_feature_columns:
            fallback = float(self.optional_feature_defaults.get(column, 0.0))
            base[column] = base[column].fillna(fallback)

        return base

    def _augment_model_features(self, base_features: pd.DataFrame) -> pd.DataFrame:
        model_features = base_features.copy()

        model_features["utilization_dti_interaction"] = (
            model_features["credit_utilization"] * model_features["debt_to_income_ratio"]
        )
        model_features["payment_stress_index"] = (
            (model_features["missed_payments"] / 12.0) * (1.0 - model_features["repayment_history"])
        )
        model_features["credit_pressure"] = (
            (850.0 - model_features["credit_score"]) / 550.0
        ).clip(lower=0.0, upper=1.0)
        model_features["income_buffer"] = (
            (model_features["income"] - 18_000.0) / 232_000.0
        ).clip(lower=0.0, upper=1.0)
        model_features["credit_income_pressure"] = (
            model_features["credit_pressure"] * (1.0 - model_features["income_buffer"])
        )
        model_features["loan_to_income_ratio_raw"] = (
            model_features["loan_amount"] / np.maximum(model_features["income"], 1.0)
        ).clip(lower=0.0, upper=3.0)
        model_features["experience_credit_buffer"] = (
            (model_features["years_experience"] / 30.0).clip(lower=0.0, upper=1.0)
            * (model_features["credit_score"] / 850.0)
        )

        return model_features

    def _align_model_frame(self, model_features: pd.DataFrame) -> pd.DataFrame:
        aligned = model_features.copy()
        for column in self.model_input_columns:
            if column not in aligned.columns:
                aligned[column] = 0.0
        return aligned[self.model_input_columns]

    def _select_decision_threshold(self, y_true: pd.Series, probabilities: np.ndarray) -> tuple[float, float, float]:
        best_threshold = 0.5
        best_accuracy = -1.0
        best_f1 = -1.0

        for threshold in np.linspace(0.30, 0.70, 41):
            predictions = (probabilities >= threshold).astype(int)
            accuracy = float(accuracy_score(y_true, predictions))
            f1_value = float(f1_score(y_true, predictions, zero_division=0))

            if (accuracy, f1_value) > (best_accuracy, best_f1):
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

    def train(self, dataframe: pd.DataFrame) -> Dict[str, Any]:
        target = dataframe[TARGET_COLUMN].astype(int)

        diagnostics = self._target_direction_diagnostics(dataframe)
        self.use_business_calibration = (
            diagnostics["alignment_score"] < 1.0 or diagnostics["avg_abs_corr"] < 0.08
        )

        base_features = self._base_feature_frame(dataframe, fit_defaults=True)
        features = self._augment_model_features(base_features)
        self.model_input_columns = list(features.columns)

        x_train_valid, x_test, y_train_valid, y_test = train_test_split(
            features,
            target,
            test_size=0.2,
            random_state=42,
            stratify=target,
        )

        x_train, x_valid, y_train, y_valid = train_test_split(
            x_train_valid,
            y_train_valid,
            test_size=0.2,
            random_state=42,
            stratify=y_train_valid,
        )

        x_train_scaled = self.scaler.fit_transform(x_train)
        x_valid_scaled = self.scaler.transform(x_valid)

        candidate_metrics: Dict[str, Dict[str, Optional[float]]] = {}
        best_model_name: Optional[str] = None
        best_model: Any = None
        best_validation_probabilities: Optional[np.ndarray] = None
        best_threshold = 0.5
        best_sort_key: Optional[tuple[float, float, float]] = None

        for model_name, candidate_model in self._candidate_models().items():
            candidate_model.fit(x_train_scaled, y_train)

            validation_probabilities = candidate_model.predict_proba(x_valid_scaled)[:, 1]
            threshold, validation_accuracy, validation_f1 = self._select_decision_threshold(
                y_true=y_valid,
                probabilities=validation_probabilities,
            )
            validation_predictions = (validation_probabilities >= threshold).astype(int)

            candidate_roc_auc = (
                float(roc_auc_score(y_valid, validation_probabilities))
                if len(np.unique(y_valid)) > 1
                else None
            )

            candidate_metrics[model_name] = {
                "validation_accuracy": round(validation_accuracy, 4),
                "validation_precision": round(
                    float(precision_score(y_valid, validation_predictions, zero_division=0)),
                    4,
                ),
                "validation_recall": round(
                    float(recall_score(y_valid, validation_predictions, zero_division=0)),
                    4,
                ),
                "validation_f1_score": round(validation_f1, 4),
                "roc_auc": round(candidate_roc_auc, 4) if candidate_roc_auc is not None else None,
                "decision_threshold": round(threshold, 4),
            }

            sort_key = (
                validation_accuracy,
                validation_f1,
                candidate_roc_auc if candidate_roc_auc is not None else -1.0,
            )
            if best_sort_key is None or sort_key > best_sort_key:
                best_sort_key = sort_key
                best_model_name = model_name
                best_model = candidate_model
                best_validation_probabilities = validation_probabilities
                best_threshold = threshold

        if best_model is None or best_model_name is None or best_validation_probabilities is None:
            raise RuntimeError("Failed to train candidate models.")

        self.decision_threshold = float(best_threshold)
        self.selected_model_name = best_model_name
        self.model = best_model

        x_train_valid_scaled = self.scaler.fit_transform(x_train_valid)
        x_test_scaled = self.scaler.transform(x_test)
        self.model.fit(x_train_valid_scaled, y_train_valid)

        test_probabilities = self.model.predict_proba(x_test_scaled)[:, 1]
        test_predictions = (test_probabilities >= self.decision_threshold).astype(int)

        validation_roc_auc = (
            float(roc_auc_score(y_valid, best_validation_probabilities))
            if len(np.unique(y_valid)) > 1
            else None
        )
        test_roc_auc = (
            float(roc_auc_score(y_test, test_probabilities))
            if len(np.unique(y_test)) > 1
            else None
        )

        # Adapt low/medium/high bands to observed calibrated score distribution.
        full_base_features = self._base_feature_frame(dataframe, fit_defaults=False)
        full_model_features = self._align_model_frame(self._augment_model_features(full_base_features))
        full_scaled = self.scaler.transform(full_model_features)
        full_raw_probabilities = self.model.predict_proba(full_scaled)[:, 1]

        calibrated_full_probabilities = []
        for (_, row), raw_probability in zip(full_base_features.iterrows(), full_raw_probabilities):
            canonical_values = row[self.feature_columns].to_dict()
            calibrated_probability, business_risk_index = self._calibrate_probability(
                model_probability=float(raw_probability),
                feature_values=canonical_values,
            )
            calibrated_probability, _, _ = self._apply_high_risk_override(
                probability=calibrated_probability,
                model_probability=float(raw_probability),
                business_risk_index=float(business_risk_index),
                feature_values=canonical_values,
            )
            calibrated_full_probabilities.append(calibrated_probability)

        self._update_risk_band_thresholds(np.asarray(calibrated_full_probabilities, dtype=float))

        if hasattr(self.model, "coef_"):
            feature_signals = {
                feature: float(weight)
                for feature, weight in zip(self.model_input_columns, self.model.coef_[0])
            }
            self.feature_signal_type = "coefficient"
        elif hasattr(self.model, "feature_importances_"):
            feature_signals = {
                feature: float(weight)
                for feature, weight in zip(self.model_input_columns, self.model.feature_importances_)
            }
            self.feature_signal_type = "importance"
        else:
            feature_signals = {feature: 0.0 for feature in self.model_input_columns}
            self.feature_signal_type = "unknown"

        self.metrics = {
            "accuracy": round(float(accuracy_score(y_test, test_predictions)), 4),
            "precision": round(float(precision_score(y_test, test_predictions, zero_division=0)), 4),
            "recall": round(float(recall_score(y_test, test_predictions, zero_division=0)), 4),
            "f1_score": round(float(f1_score(y_test, test_predictions, zero_division=0)), 4),
            "roc_auc": round(float(test_roc_auc), 4) if test_roc_auc is not None else None,
            "validation_roc_auc": (
                round(float(validation_roc_auc), 4) if validation_roc_auc is not None else None
            ),
            "decision_threshold": round(float(self.decision_threshold), 4),
            "low_risk_threshold": round(float(self.low_threshold), 4),
            "high_risk_threshold": round(float(self.high_threshold), 4),
            "risk_band_quantiles": {
                "low": float(self.low_quantile),
                "high": float(self.high_quantile),
            },
            "train_size": int(len(x_train_valid)),
            "validation_size": int(len(x_valid)),
            "test_size": int(len(x_test)),
            "selected_model": self.selected_model_name,
            "model_candidates": candidate_metrics,
            "feature_coefficients": feature_signals,
            "feature_signal_type": self.feature_signal_type,
            "model_input_columns": self.model_input_columns,
            "directional_alignment_score": round(float(diagnostics["alignment_score"]), 4),
            "average_abs_feature_correlation": round(float(diagnostics["avg_abs_corr"]), 4),
            "calibration_mode": (
                "hybrid_business_adjusted" if self.use_business_calibration else "model_dominant_hybrid"
            ),
        }
        self.is_trained = True
        return self.metrics

    def score_dataframe(self, dataframe: pd.DataFrame) -> np.ndarray:
        if not self.is_trained:
            raise RuntimeError("Model must be trained before scoring dataframes.")

        base_features = self._base_feature_frame(dataframe, fit_defaults=False)
        model_features = self._augment_model_features(base_features)
        aligned_features = self._align_model_frame(model_features)
        scaled = self.scaler.transform(aligned_features)
        raw_probabilities = self.model.predict_proba(scaled)[:, 1]

        calibrated_probabilities = []
        for (_, row), raw_probability in zip(base_features.iterrows(), raw_probabilities):
            canonical_values = row[self.feature_columns].to_dict()
            probability, business_risk_index = self._calibrate_probability(
                float(raw_probability),
                canonical_values,
            )
            probability, _, _ = self._apply_high_risk_override(
                probability=probability,
                model_probability=float(raw_probability),
                business_risk_index=float(business_risk_index),
                feature_values=canonical_values,
            )
            calibrated_probabilities.append(probability)

        return np.asarray(calibrated_probabilities, dtype=float)

    def _risk_category(self, probability: float, missed_payments: float) -> tuple[str, bool, Optional[str]]:
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
            override_reason = (
                "Rule override applied: missed_payments exceeded threshold (>5), forcing high risk."
            )

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
        self,
        feature_values: Dict[str, float],
        limit: int = 5,
    ) -> list[Dict[str, Any]]:
        row = pd.DataFrame([feature_values])
        base_row = self._base_feature_frame(row, fit_defaults=False)
        model_row = self._align_model_frame(self._augment_model_features(base_row))

        if hasattr(self.model, "coef_"):
            scaled = self.scaler.transform(model_row)[0]
            coefficients = self.model.coef_[0]
            contributions = scaled * coefficients

            ranked = sorted(
                zip(self.model_input_columns, contributions),
                key=lambda item: abs(float(item[1])),
                reverse=True,
            )[:limit]

            return [
                {
                    "feature": self._format_driver_name(name),
                    "impact": round(float(value), 4),
                    "direction": "risk_up" if float(value) >= 0 else "risk_down",
                }
                for name, value in ranked
            ]

        if hasattr(self.model, "feature_importances_"):
            importances = [float(value) for value in self.model.feature_importances_]
            ranked = sorted(
                zip(self.model_input_columns, importances),
                key=lambda item: abs(float(item[1])),
                reverse=True,
            )[:limit]

            return [
                {
                    "feature": self._format_driver_name(name),
                    "impact": round(float(value), 4),
                    "direction": "risk_up",
                }
                for name, value in ranked
            ]

        return []

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
                    f"High risk with a {probability * 100:.1f}% delinquency probability. "
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
                f"Low risk profile with a {probability * 100:.1f}% delinquency probability. "
                "Consistent repayment behavior and controlled leverage are protective signals."
            )

        top_drivers = self._rank_drivers(feature_values)
        driver_text = ", ".join(top_drivers)
        reason_text = ", ".join(reasons[:2]) if reasons else "mixed financial behavior"

        return (
            f"{category.title()} risk with a {probability * 100:.1f}% delinquency probability, "
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

        row = pd.DataFrame([feature_values])
        base_row = self._base_feature_frame(row, fit_defaults=False)
        model_row = self._align_model_frame(self._augment_model_features(base_row))

        scaled = self.scaler.transform(model_row)
        raw_probability = float(self.model.predict_proba(scaled)[0, 1])

        canonical_values = base_row[self.feature_columns].iloc[0].to_dict()
        probability, business_risk_index = self._calibrate_probability(
            model_probability=raw_probability,
            feature_values=canonical_values,
        )

        probability, profile_override_applied, profile_override_reason = self._apply_high_risk_override(
            probability=probability,
            model_probability=raw_probability,
            business_risk_index=float(business_risk_index),
            feature_values=canonical_values,
        )

        category, override_applied, override_reason = self._risk_category(
            probability=probability,
            missed_payments=float(canonical_values["missed_payments"]),
        )
        if profile_override_applied:
            category = "high"
            override_applied = True
            override_reason = profile_override_reason
        elif override_applied:
            probability = max(probability, 0.75)

        explanation = self._build_explanation(
            feature_values=canonical_values,
            probability=probability,
            category=category,
            override_applied=override_applied,
            override_reason=override_reason,
        )
        top_drivers = self._top_driver_impacts(feature_values=canonical_values, limit=5)
        collections_strategy = self._recommend_collections_strategy(
            feature_values=canonical_values,
            category=category,
            probability=probability,
        )

        return {
            "risk_probability": round(probability, 4),
            "risk_score": round(probability * 100.0, 2),
            "model_probability": round(raw_probability, 4),
            "business_risk_index": round(float(business_risk_index), 4),
            "risk_category": category,
            "override_applied": override_applied,
            "override_reason": override_reason,
            "top_drivers": top_drivers,
            "collections_strategy": collections_strategy,
            "explanation": explanation,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def save(self, artifact_path: Path = ARTIFACT_PATH) -> None:
        payload = {
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
            "scaler": self.scaler,
            "model": self.model,
            "selected_model_name": self.selected_model_name,
            "feature_signal_type": self.feature_signal_type,
            "metrics": self.metrics,
            "is_trained": self.is_trained,
            "use_business_calibration": self.use_business_calibration,
        }
        joblib.dump(payload, artifact_path)

    def load(self, artifact_path: Path = ARTIFACT_PATH) -> None:
        payload = joblib.load(artifact_path)
        self.feature_columns = payload["feature_columns"]
        self.optional_feature_columns = payload.get("optional_feature_columns", OPTIONAL_FEATURE_COLUMNS)
        self.optional_feature_defaults = payload.get(
            "optional_feature_defaults",
            {
                "age": 40.0,
                "loan_amount": 20_000.0,
                "years_experience": 10.0,
            },
        )
        self.model_input_columns = payload.get("model_input_columns", list(self.feature_columns))
        self.decision_threshold = payload.get("decision_threshold", 0.5)
        self.low_threshold = payload["low_threshold"]
        self.high_threshold = payload["high_threshold"]
        self.low_quantile = float(payload.get("low_quantile", 0.30))
        self.high_quantile = float(payload.get("high_quantile", 0.75))
        self.override_threshold = payload["override_threshold"]
        self.scaler = payload["scaler"]
        self.model = payload["model"]
        self.selected_model_name = payload.get("selected_model_name", "logistic_regression")
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
    model_metrics = model.train(prepared.cleaned)

    predicted_probabilities = model.score_dataframe(prepared.cleaned)
    insights = build_insights_payload(
        dataframe=prepared.cleaned,
        imputation_report=prepared.imputation_report,
        model_metrics=model_metrics,
        predicted_probabilities=predicted_probabilities,
    )

    model.save()

    return {
        "model": model,
        "insights": insights,
        "dataset": prepared.cleaned,
    }
