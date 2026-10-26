import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, train_test_split

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import data_processing as data
import model as modeling


def small_candidates(_self):
    return {
        "logistic_regression": LogisticRegression(max_iter=1000, random_state=42),
        "random_forest": RandomForestClassifier(
            n_estimators=20, min_samples_leaf=3, random_state=42
        ),
        "gradient_boosting": GradientBoostingClassifier(
            n_estimators=20, random_state=42
        ),
    }


class DataTests(unittest.TestCase):
    def test_default_uses_delinquency_labels(self):
        prepared = data.prepare_dataset()
        provenance = prepared.raw.attrs["provenance"]
        self.assertEqual(provenance["target_kind"], "observed_delinquency")
        self.assertEqual(provenance["target_source"], "Delinquent_Account")
        self.assertIn("loan_amount", prepared.raw)
        self.assertTrue(prepared.raw["income"].isna().any())

    def test_missing_configured_path_is_an_error(self):
        with self.assertRaises(FileNotFoundError):
            data.prepare_dataset("does-not-exist.csv")

    def test_proxy_target_is_identified(self):
        prepared = data.prepare_dataset(
            str(data.WORKSPACE_ROOT / "loan_risk_prediction_dataset.csv")
        )
        self.assertEqual(
            prepared.raw.attrs["provenance"]["target_kind"], "approval_proxy"
        )
        self.assertIn(
            "missed_payments", prepared.raw.attrs["provenance"]["derived_features"]
        )

    def test_bad_labels_are_not_fabricated(self):
        for labels in ([0] * 50, [np.nan] * 50, [2] + [0, 1] * 24 + [1]):
            frame = data.generate_synthetic_dataset(50)
            frame[data.TARGET_COLUMN] = labels
            with tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / "bad.csv"
                frame.to_csv(path, index=False)
                with self.assertRaises(ValueError):
                    data.prepare_dataset(str(path))

    def test_unknown_outcomes_are_dropped(self):
        frame = data.generate_synthetic_dataset(120).fillna(0)
        frame.loc[0, data.TARGET_COLUMN] = np.nan
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "data.csv"
            frame.to_csv(path, index=False)
            prepared = data.prepare_dataset(str(path))
            self.assertEqual(len(prepared.raw), 119)
            self.assertEqual(
                prepared.raw.attrs["provenance"]["dropped_unlabeled_rows"], 1
            )

    def test_ids_survive_row_reordering(self):
        source = data._read_tabular_dataset(data.DEFAULT_DATA_CANDIDATES[1])
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "accounts.csv"
            source.to_csv(path, index=False)
            before = data.load_financial_dataset(str(path))
            source.iloc[::-1].to_csv(path, index=False)
            after = data.load_financial_dataset(str(path))
            self.assertEqual(
                before["account_id"].tolist(), after["account_id"].tolist()[::-1]
            )
            self.assertTrue(before["account_id"].is_unique)

    def test_nonfinite_inputs_become_missing(self):
        frame = data.generate_synthetic_dataset(50)
        frame.loc[0, "income"] = np.inf
        self.assertTrue(pd.isna(data._sanitize_dataframe(frame).loc[0, "income"]))

    def test_ambiguous_column_names_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            data._standardize_schema(
                pd.DataFrame({"income": [50000], "Income": [100000]})
            )


class ModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frame = data.generate_synthetic_dataset(400)
        cls.frame.attrs["provenance"] = {"target_kind": "synthetic"}
        cls.model = modeling.CreditRiskModel()
        with patch.object(
            modeling.CreditRiskModel, "_candidate_models", small_candidates
        ):
            cls.model.train(cls.frame)

    def test_preprocessing_only_fits_training_rows(self):
        train_valid, test = train_test_split(
            self.frame, test_size=0.2, random_state=42, stratify=self.frame.delinquent
        )
        train, _ = train_test_split(
            train_valid, test_size=0.2, random_state=42, stratify=train_valid.delinquent
        )
        self.assertAlmostEqual(
            self.model.imputation_values["income"], train.income.median()
        )
        changed = self.frame.copy()
        changed.loc[test.index, "income"] = 999999
        other = modeling.CreditRiskModel()
        with patch.object(
            modeling.CreditRiskModel, "_candidate_models", small_candidates
        ):
            other.train(changed)
        self.assertEqual(self.model.imputation_values, other.imputation_values)
        for name in self.model.candidates:
            original_folds = self.model.candidates[name][
                "model"
            ].calibrated_classifiers_
            changed_folds = other.candidates[name]["model"].calibrated_classifiers_
            for original, modified in zip(original_folds, changed_folds):
                np.testing.assert_allclose(
                    original.estimator.named_steps["scaler"].mean_,
                    modified.estimator.named_steps["scaler"].mean_,
                )
            first_fold, _ = next(StratifiedKFold(3).split(train, train.delinquent))
            self.assertAlmostEqual(
                original_folds[0].estimator.named_steps["features"].medians_["income"],
                train.iloc[first_fold].income.median(),
            )
        self.assertEqual(
            self.model.metrics["model_candidates"], other.metrics["model_candidates"]
        )
        for name in self.model.candidates:
            self.assertEqual(
                self.model.candidates[name]["low_threshold"],
                other.candidates[name]["low_threshold"],
            )
            self.assertEqual(
                self.model.candidates[name]["high_threshold"],
                other.candidates[name]["high_threshold"],
            )

    def test_single_batch_and_override_agree(self):
        row = self.model._base_feature_frame(self.frame.iloc[[0]]).iloc[0].to_dict()
        row.update(missed_payments=7, debt_to_income_ratio=1.2, repayment_history=0.4)
        single = self.model.predict(row)
        batch = self.model.score_records(pd.DataFrame([row]))[0]
        for field in batch:
            self.assertEqual(single[field], batch[field])
        self.assertTrue(single["override_applied"])
        self.assertEqual(single["risk_category"], "high")
        self.assertGreaterEqual(single["risk_score"], 75)

    def test_missing_input_score_is_independent_of_other_rows(self):
        row = self.frame.iloc[[0]].copy()
        row["income"] = np.nan
        alone = self.model.score_records(row)[0]
        together = self.model.score_records(pd.concat([row, self.frame.iloc[1:50]]))[0]
        self.assertEqual(alone, together)

    def test_local_sensitivity_has_both_directions(self):
        row = self.model._base_feature_frame(self.frame.iloc[[0]]).iloc[0].to_dict()
        impacts = self.model._top_driver_impacts(row, limit=9)
        self.assertTrue(
            all(item["method"] == "median_replacement_sensitivity" for item in impacts)
        )
        self.assertTrue(any(item["impact"] != 0 for item in impacts))
        for item in impacts:
            self.assertEqual(
                item["direction"], "risk_up" if item["impact"] >= 0 else "risk_down"
            )

    def test_metrics_are_finite_and_separate_operational_scores(self):
        json.dumps(self.model.metrics, allow_nan=False)
        self.assertIn("operational_metrics", self.model.metrics)
        self.assertIn("baseline_metrics", self.model.metrics)
        self.assertIn("average_precision", self.model.metrics)
        self.assertEqual(
            sum(
                self.model.metrics[k]
                for k in ("train_size", "validation_size", "test_size")
            ),
            len(self.frame),
        )

    def test_saved_candidates_and_predictions_round_trip(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "model.joblib"
            self.model.save(path)
            loaded = modeling.CreditRiskModel()
            loaded.load(path)
            self.assertEqual(
                loaded.score_records(self.frame.iloc[:5]),
                self.model.score_records(self.frame.iloc[:5]),
            )
            challenger = next(
                name for name in loaded.candidates if name != loaded.selected_model_name
            )
            loaded.activate_candidate(challenger)
            self.assertEqual(loaded.selected_model_name, challenger)
            self.assertIs(loaded.model, loaded.candidates[challenger]["model"])

    def test_bad_training_labels_and_tiny_sets_fail(self):
        for frame in (
            self.frame.iloc[:10],
            self.frame.assign(delinquent=0),
            self.frame.assign(delinquent=np.nan),
        ):
            with self.assertRaises(ValueError):
                modeling.CreditRiskModel().train(frame)


if __name__ == "__main__":
    unittest.main()
