import io
import json
import os
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main
import model as modeling
from test_pipeline import small_candidates


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.artifacts = tempfile.TemporaryDirectory()
        cls.artifact_path = Path(cls.artifacts.name) / "model.joblib"
        with (
            patch.object(modeling, "ARTIFACT_PATH", cls.artifact_path),
            patch.object(
                modeling.CreditRiskModel, "_candidate_models", small_candidates
            ),
        ):
            cls.initial = modeling.initialize_model_system()

    @classmethod
    def tearDownClass(cls):
        cls.artifacts.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        main.state.model = deepcopy(self.initial["model"])
        main.state.dataset = self.initial["dataset"].copy()
        main.state.insights = deepcopy(self.initial["insights"])
        main.state.portfolio_records = main._build_portfolio_records(
            main.state.model, main.state.dataset
        )
        main.state.portfolio_index = {
            r["account_id"]: r for r in main.state.portfolio_records
        }
        main.state.model_registry = main._initialize_model_registry(
            main.state.model.metrics
        )
        main.state.monitoring_snapshots = []
        main.state.startup_error = None
        self.account = main.state.portfolio_records[0]["account_id"]
        self.env = patch.dict(
            os.environ, {"CREDIT_RISK_DEMO_MODE": "1", "CREDIT_RISK_ROLE_KEYS": "{}"}
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        self.path_patch = patch.object(
            main, "WORKFLOW_STATE_PATH", Path(self.temp.name) / "workflow.json"
        )
        self.path_patch.start()
        self.addCleanup(self.path_patch.stop)
        self.client = TestClient(main.app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)

    def test_read_endpoints_and_account_lookup(self):
        for route in (
            "/health",
            "/insights",
            "/portfolio?limit=2",
            "/portfolio/" + self.account.lower(),
            "/alerts",
            "/model-monitoring",
            "/model-versions",
        ):
            self.assertEqual(self.client.get(route).status_code, 200, route)

    def test_null_status_rejected_before_mutation(self):
        before = deepcopy(main.state.portfolio_index[self.account])
        response = self.client.patch(
            f"/portfolio/{self.account}/workflow", json={"status": None}
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(main.state.portfolio_index[self.account], before)

    def test_failed_persistence_rolls_back(self):
        url = f"/portfolio/{self.account}/workflow"
        self.assertEqual(
            self.client.patch(url, json={"note": "saved"}).status_code, 200
        )
        before = deepcopy(main.state.portfolio_index[self.account])
        disk = main.WORKFLOW_STATE_PATH.read_bytes()
        with patch.object(main.os, "replace", side_effect=OSError("disk unavailable")):
            response = self.client.patch(
                url, json={"status": "resolved", "note": "must roll back"}
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(main.state.portfolio_index[self.account], before)
        self.assertEqual(main.WORKFLOW_STATE_PATH.read_bytes(), disk)

    def test_concurrent_notes_are_preserved(self):
        url = f"/portfolio/{self.account}/workflow"
        with ThreadPoolExecutor(max_workers=4) as pool:
            statuses = list(
                pool.map(
                    lambda n: (
                        self.client.patch(url, json={"note": f"note {n}"}).status_code
                    ),
                    range(8),
                )
            )
        self.assertEqual(statuses, [200] * 8)
        timeline = main.state.portfolio_index[self.account]["timeline"]
        self.assertEqual(len(timeline), 8)
        self.assertEqual(len({entry["event_id"] for entry in timeline}), 8)
        self.assertEqual(
            len(
                json.loads(main.WORKFLOW_STATE_PATH.read_text())["accounts"][
                    self.account
                ]["timeline"]
            ),
            8,
        )

    def test_promotion_switches_artifact_rescores_and_preserves_workflow(self):
        self.client.patch(
            f"/portfolio/{self.account}/workflow",
            json={"owner": "Test Agent", "note": "retain"},
        )
        name = next(
            n
            for n in main.state.model.candidates
            if n != main.state.model.selected_model_name
        )
        with patch.object(modeling, "ARTIFACT_PATH", self.artifact_path):
            response = self.client.post(
                "/model-versions/promote", json={"challenger_model": name}
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(main.state.model.selected_model_name, name)
        self.assertIs(
            main.state.model.model, main.state.model.candidates[name]["model"]
        )
        self.assertEqual(
            main.state.portfolio_index[self.account]["assigned_to"], "Test Agent"
        )
        self.assertEqual(
            main.state.insights["model_performance"]["selected_model"], name
        )
        with (
            patch.object(modeling, "ARTIFACT_PATH", self.artifact_path),
            patch.object(
                modeling.CreditRiskModel,
                "train",
                side_effect=AssertionError("cache should be reused"),
            ),
        ):
            loaded = modeling.initialize_model_system()
        self.assertEqual(loaded["model"].selected_model_name, name)

    def test_income_drift_is_measured(self):
        for row in main.state.portfolio_records:
            row["annual_income"] *= 3
        income = next(
            r
            for r in self.client.get("/model-monitoring").json()["current"][
                "drift_rows"
            ]
            if r["feature"] == "income"
        )
        self.assertGreater(income["z_score"], 1)
        self.assertTrue(income["drift_flag"])
        self.assertEqual(income["observed_count"], len(main.state.portfolio_records))

    def test_insights_and_portfolio_use_identical_risk_categories(self):
        expected = {
            risk: sum(
                row["risk_category"] == risk for row in main.state.portfolio_records
            )
            for risk in ("low", "medium", "high")
        }
        self.assertEqual(main.state.insights["charts"]["risk_distribution"], expected)

    def test_monthly_and_annual_income_agree(self):
        sample = dict(
            income=5000,
            income_period="monthly",
            credit_score=700,
            missed_payments=1,
            repayment_history=0.9,
            loan_amount=15000,
        )
        monthly = self.client.post("/predict", json=sample)
        annual = self.client.post(
            "/predict", json={**sample, "income": 60000, "income_period": "annual"}
        )
        self.assertEqual(monthly.status_code, 200)
        self.assertEqual(monthly.json()["risk_score"], annual.json()["risk_score"])
        self.assertEqual(
            self.client.post("/predict", json={**sample, "income": 100000}).status_code,
            422,
        )

    def test_stale_model_cache_is_invalidated(self):
        path = Path(self.temp.name) / "stale.joblib"
        stale = deepcopy(self.initial["model"])
        stale.dataset_fingerprint = "stale"
        stale.save(path)
        original_train = modeling.CreditRiskModel.train
        with (
            patch.object(modeling, "ARTIFACT_PATH", path),
            patch.object(
                modeling.CreditRiskModel, "_candidate_models", small_candidates
            ),
            patch.object(
                modeling.CreditRiskModel,
                "train",
                autospec=True,
                side_effect=original_train,
            ) as train,
        ):
            initialized = modeling.initialize_model_system()
        self.assertEqual(train.call_count, 1)
        self.assertNotEqual(initialized["model"].dataset_fingerprint, "stale")

    def test_batch_and_single_override_agree(self):
        sample = dict(
            income=74000,
            credit_score=600,
            credit_utilization=0.8,
            debt_to_income_ratio=1.2,
            missed_payments=7,
            repayment_history=0.4,
            age=34,
            loan_amount=80000,
            years_experience=8,
        )
        single = self.client.post("/predict", json=sample)
        csv = pd.DataFrame([sample]).to_csv(index=False)
        batch = self.client.post(
            "/portfolio/batch-score", files={"file": ("borrowers.csv", csv, "text/csv")}
        )
        self.assertEqual(single.status_code, 200)
        self.assertEqual(batch.status_code, 200)
        record = batch.json()["records"][0]
        for field in (
            "risk_score",
            "risk_category",
            "model_probability",
            "override_applied",
            "override_reason",
        ):
            self.assertEqual(record[field], single.json()[field])

    def test_renamed_excel_upload(self):
        stream = io.BytesIO()
        main.state.dataset.iloc[:2].to_excel(stream, index=False)
        response = self.client.post(
            "/portfolio/batch-score",
            files={"file": ("renamed.csv", stream.getvalue(), "text/csv")},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["summary"]["scored_rows"], 2)

    def test_empty_and_oversize_uploads(self):
        for contents, expected in (
            (b"", 400),
            (b"x" * (main.MAX_UPLOAD_BYTES + 1), 413),
        ):
            response = self.client.post(
                "/portfolio/batch-score",
                files={"file": ("data.csv", contents, "text/csv")},
            )
            self.assertEqual(response.status_code, expected)
        with patch.object(main, "MAX_UPLOAD_ROWS", 1):
            csv = main.state.dataset.iloc[:2].to_csv(index=False)
            self.assertEqual(
                self.client.post(
                    "/portfolio/batch-score", files={"file": ("data.csv", csv)}
                ).status_code,
                413,
            )

    def test_authentication_fails_closed(self):
        os.environ["CREDIT_RISK_DEMO_MODE"] = "0"
        self.assertEqual(self.client.get("/portfolio").status_code, 503)
        self.assertEqual(self.client.get("/health").status_code, 200)

    def test_bearer_role_cannot_be_spoofed(self):
        os.environ["CREDIT_RISK_ROLE_KEYS"] = json.dumps(
            {"analyst": "analyst-secret-123456", "manager": "manager-secret-123456"}
        )
        self.assertEqual(
            self.client.get(
                "/portfolio", headers={"X-User-Role": "manager"}
            ).status_code,
            401,
        )
        headers = {
            "Authorization": "Bearer analyst-secret-123456",
            "X-User-Role": "manager",
        }
        self.assertEqual(
            self.client.get("/auth/roles", headers=headers).json()["current_role"],
            "analyst",
        )
        self.assertEqual(
            self.client.patch(
                f"/portfolio/{self.account}/workflow",
                headers=headers,
                json={"note": "forbidden"},
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(
                "/portfolio", headers={"Authorization": "Bearer manager-secret-123456"}
            ).status_code,
            200,
        )

    def test_invalid_auth_config_fails_closed(self):
        for config in (
            "not-json",
            "[]",
            '{"manager":"short"}',
            '{"manager":"same-secret-12345", "analyst":"same-secret-12345"}',
        ):
            os.environ["CREDIT_RISK_ROLE_KEYS"] = config
            self.assertEqual(self.client.get("/portfolio").status_code, 503)


if __name__ == "__main__":
    unittest.main()
