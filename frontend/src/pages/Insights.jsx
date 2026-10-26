import { useEffect, useState } from "react";
import {
  fetchInsights,
  fetchModelMonitoring,
  fetchModelVersions,
  promoteModelVersion,
} from "../api";
import FeatureCorrelationChart from "../charts/FeatureCorrelationChart";
import GlassCard from "../components/GlassCard";
import SkeletonLoader from "../components/SkeletonLoader";
import { useToast } from "../components/ToastProvider";

export default function Insights() {
  const { addToast } = useToast();
  const [insights, setInsights] = useState(null);
  const [monitoring, setMonitoring] = useState(null);
  const [modelVersions, setModelVersions] = useState(null);
  const [promotionLoading, setPromotionLoading] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");

  useEffect(() => {
    let isMounted = true;

    async function loadInsights() {
      setLoading(true);
      setError("");
      try {
        const [insightsResponse, monitoringResponse, versionResponse] = await Promise.all([
          fetchInsights(),
          fetchModelMonitoring(),
          fetchModelVersions(),
        ]);
        if (isMounted) {
          setInsights(insightsResponse);
          setMonitoring(monitoringResponse);
          setModelVersions(versionResponse);
        }
      } catch (apiError) {
        if (isMounted) {
          setError(apiError.message || "Could not load insights.");
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    }

    loadInsights();

    return () => {
      isMounted = false;
    };
  }, []);

  if (loading) {
    return <SkeletonLoader />;
  }

  if (error) {
    return (
      <GlassCard title="Insights Error" subtitle="Analytics payload unavailable">
        <p className="text-[var(--text-main)]">{error}</p>
      </GlassCard>
    );
  }

  const featureImportance = insights?.feature_importance || {};
  const topFeatures = featureImportance.top_features || [];
  const modelCandidates = insights?.model_performance?.model_candidates || {};
  const candidateRows = Object.entries(modelCandidates);
  const monitoringCurrent = monitoring?.current || {};
  const monitoringHistory = monitoring?.history || [];
  const driftRows = monitoringCurrent?.drift_rows || [];
  const champion = modelVersions?.champion;
  const challengers = modelVersions?.challengers || [];

  async function handlePromote(modelName) {
    setPromotionLoading(modelName);
    setActionError("");
    try {
      const response = await promoteModelVersion({
        challenger_model: modelName,
        rationale: "Promoted from Insights workflow panel.",
      });
      const [refreshedInsights, refreshedMonitoring] = await Promise.all([fetchInsights(), fetchModelMonitoring()]);
      setInsights(refreshedInsights);
      setMonitoring(refreshedMonitoring);
      setModelVersions({
        champion: response.champion,
        challengers: (response.registry || []).filter((item) => item.status === "challenger"),
        registry: response.registry,
      });
      addToast(`${modelName} promoted to champion`, "success");
    } catch (apiError) {
      setActionError(apiError.message || "Model promotion failed.");
      addToast(apiError.message || "Promotion failed", "error");
    } finally {
      setPromotionLoading("");
    }
  }

  return (
    <div className="space-y-5 fade-up">
      <GlassCard
        strong
        title="Analytics and Model Insights"
        subtitle="Transparent feature behavior and candidate-model performance diagnostics"
      >
        <p className="text-sm text-[var(--text-main)]">
          The analysis combines behavior-driven risk signals with holdout validation diagnostics so teams can understand
          both why the model predicts risk and how reliable the chosen model is.
        </p>
      </GlassCard>

      <GlassCard title="Validation and Data Quality" subtitle="Held-out results and data provenance">
        <div className="space-y-2 text-sm text-[var(--text-main)]">
          <p>Source: {insights?.data_provenance?.source || "Unknown"} | Target: {insights?.data_provenance?.target_kind || "Unknown"}</p>
          <p>Derived inputs: {(insights?.data_provenance?.derived_features || []).join(", ") || "None"}</p>
          <p>Test rows: {insights?.model_performance?.test_size} | Average precision: {insights?.model_performance?.average_precision} | Baseline: {insights?.model_performance?.baseline_metrics?.average_precision}</p>
          <p>Recall: {insights?.model_performance?.recall} | Precision: {insights?.model_performance?.precision} | Brier score: {insights?.model_performance?.brier_score}</p>
          <p>Business-rule score F1: {insights?.model_performance?.operational_metrics?.f1_score} | Model F1: {insights?.model_performance?.f1_score}</p>
          <p>The business-adjusted score is a prioritization score. Predictive metrics measure the calibrated model separately.</p>
          {(insights?.model_performance?.quality_warnings || []).map((warning) => (
            <p key={warning} role="status" className="rounded-xl border border-orange-300/45 bg-orange-100/70 px-4 py-3">{warning}</p>
          ))}
        </div>
      </GlassCard>

      <div className="grid gap-4 md:grid-cols-2 stagger">
        <GlassCard title="Model Monitoring" subtitle="Drift, override rate, and live risk behavior">
          <div className="grid gap-2 text-sm">
            <p className="rounded-xl border border-orange-300/35 bg-white/85 px-4 py-3 text-[var(--text-main)]">
              Selected Model: <span className="font-semibold">{monitoringCurrent.selected_model || "n/a"}</span>
            </p>
            <p className="rounded-xl border border-orange-300/35 bg-white/85 px-4 py-3 text-[var(--text-main)]">
              Override Rate: <span className="font-semibold">{((monitoringCurrent.override_rate || 0) * 100).toFixed(2)}%</span>
            </p>
            <p className="rounded-xl border border-orange-300/35 bg-white/85 px-4 py-3 text-[var(--text-main)]">
              Avg Drift Z-Score: <span className="font-semibold">{monitoringCurrent.average_drift_z ?? 0}</span>
            </p>
            <p className="rounded-xl border border-orange-300/35 bg-orange-100/70 px-4 py-3 text-[var(--text-main)]">
              Calibration Mode: <span className="font-semibold">{monitoringCurrent.calibration_mode || "n/a"}</span>
            </p>
          </div>
        </GlassCard>

        <GlassCard title="Behavioral vs Financial Signal Strength">
          <div className="space-y-3 text-sm">
            <p className="rounded-xl border border-orange-300/35 bg-orange-100/70 px-4 py-3 text-[var(--text-main)]">
              Behavioral strength: <span className="font-semibold">{featureImportance.behavioral_strength}</span>
            </p>
            <p className="rounded-xl border border-orange-300/30 bg-white/80 px-4 py-3 text-[var(--text-main)]">
              Financial strength: <span className="font-semibold">{featureImportance.financial_strength}</span>
            </p>
            <p className="rounded-xl border border-orange-300/35 bg-orange-200/60 px-4 py-3 text-[#844e35]">
              {featureImportance.behavioral_dominant
                ? "Behavioral patterns dominate this portfolio risk signal."
                : "Financial and behavioral signals are currently close in influence."}
            </p>
          </div>
        </GlassCard>

        <GlassCard title="Interaction Insight: DTI + Missed Payments">
          <p className="rounded-xl border border-orange-300/45 bg-orange-200/55 px-4 py-3 text-sm text-[#7f4c35]">
            Compare the observed target rate for elevated DTI with missed payments against the portfolio baseline.
          </p>
          <div className="mt-3 space-y-2 text-sm text-[var(--text-main)]">
            <p>
              High-interaction delinquency rate: {insights?.interaction_insights?.high_dti_and_missed_rate}%
            </p>
            <p>Baseline delinquency rate: {insights?.interaction_insights?.baseline_delinquency_rate}%</p>
          </div>
        </GlassCard>
      </div>

      <GlassCard title="Feature Correlation Map" subtitle="Correlation with delinquency target (0/1)">
        <FeatureCorrelationChart correlations={insights?.feature_correlations || {}} />
      </GlassCard>

      <div className="grid gap-4 lg:grid-cols-2 stagger">
        <GlassCard title="Model Candidate Comparison" subtitle="Validation metrics before final model selection">
          <div className="space-y-3 text-sm">
            {candidateRows.map(([modelName, stats]) => (
              <div key={modelName} className="rounded-xl border border-orange-300/35 bg-white/80 px-4 py-3">
                <p className="display-font text-base text-[var(--text-main)]">{modelName.replaceAll("_", " ")}</p>
                <p className="mt-1 text-[var(--text-muted)]">
                  Validation Accuracy: {stats.validation_accuracy} | Validation F1: {stats.validation_f1_score}
                </p>
                <p className="text-[var(--text-muted)]">Average precision: {stats.validation_average_precision} | ROC AUC: {stats.roc_auc} | Threshold: {stats.decision_threshold}</p>
              </div>
            ))}
          </div>
        </GlassCard>

        <GlassCard title="Top Feature Signals" subtitle="Highest absolute correlations to target">
          <div className="space-y-3">
            {topFeatures.map((item) => (
              <div key={item.feature} className="rounded-xl border border-orange-300/35 bg-white/80 px-4 py-3 text-sm">
                <p className="font-semibold text-[var(--text-main)]">{item.feature.replaceAll("_", " ")}</p>
                <p className="text-[var(--text-muted)]">Correlation: {item.correlation.toFixed(4)}</p>
              </div>
            ))}
          </div>
        </GlassCard>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <GlassCard title="Champion-Challenger" subtitle="Model version governance and promotion workflow">
          <div className="space-y-3 text-sm">
            <div className="rounded-xl border border-orange-300/35 bg-orange-100/70 px-4 py-3">
              <p className="font-semibold text-[var(--text-main)]">Champion: {champion?.model_name || "n/a"}</p>
              <p className="text-[var(--text-muted)]">
                Accuracy {champion?.accuracy ?? "n/a"} | ROC AUC {champion?.roc_auc ?? "n/a"}
              </p>
            </div>

            {challengers.map((challenger) => (
              <div key={challenger.version_id} className="rounded-xl border border-orange-300/35 bg-white/85 px-4 py-3">
                <p className="font-semibold text-[var(--text-main)]">{challenger.model_name}</p>
                <p className="text-[var(--text-muted)]">
                  Validation Accuracy {challenger.accuracy ?? "n/a"} | ROC AUC {challenger.roc_auc ?? "n/a"}
                </p>
                <button
                  type="button"
                  className="btn-secondary mt-2 rounded-xl px-3 py-1.5 text-xs"
                  disabled={promotionLoading === challenger.model_name}
                  onClick={() => handlePromote(challenger.model_name)}
                >
                  {promotionLoading === challenger.model_name ? "Promoting..." : "Promote to Champion"}
                </button>
              </div>
            ))}

            {!challengers.length ? (
              <p className="rounded-xl border border-orange-300/35 bg-white/80 px-4 py-3 text-[var(--text-muted)]">
                No challengers available for promotion.
              </p>
            ) : null}

            {actionError ? (
              <p className="rounded-xl border border-red-300/45 bg-red-100/70 px-4 py-3 text-[#7a3830]">
                {actionError}
              </p>
            ) : null}
          </div>
        </GlassCard>

        <GlassCard title="Drift Watch" subtitle="Feature-level shift against training baseline">
          <div className="space-y-2 text-sm">
            {driftRows.map((row) => (
              <div key={row.feature} className="rounded-xl border border-orange-300/35 bg-white/85 px-4 py-3">
                <p className="font-semibold text-[var(--text-main)]">{row.feature.replaceAll("_", " ")}</p>
                <p className="text-[var(--text-muted)]">
                  Baseline {row.baseline_mean} | Current {row.current_mean} | z-score {row.z_score}
                </p>
              </div>
            ))}
            {!driftRows.length ? (
              <p className="rounded-xl border border-orange-300/35 bg-white/80 px-4 py-3 text-[var(--text-muted)]">
                Drift diagnostics are unavailable.
              </p>
            ) : null}
          </div>
        </GlassCard>

        <GlassCard title="Monitoring History" subtitle="Recent monitoring snapshots">
          <div className="space-y-2 text-sm">
            {monitoringHistory.slice().reverse().map((snapshot, index) => (
              <div key={`${snapshot.timestamp}-${index}`} className="rounded-xl border border-orange-300/35 bg-white/85 px-4 py-3">
                <p className="font-semibold text-[var(--text-main)]">{new Date(snapshot.timestamp).toLocaleString()}</p>
                <p className="text-[var(--text-muted)]">
                  Avg Risk {snapshot.average_risk_score} | High-Risk Share {((snapshot.high_risk_share || 0) * 100).toFixed(2)}% | Override {((snapshot.override_rate || 0) * 100).toFixed(2)}%
                </p>
              </div>
            ))}
            {!monitoringHistory.length ? (
              <p className="rounded-xl border border-orange-300/35 bg-white/80 px-4 py-3 text-[var(--text-muted)]">
                Monitoring history has no snapshots yet.
              </p>
            ) : null}
          </div>
        </GlassCard>
      </div>

      <GlassCard title="Key Business Findings" subtitle="Executive-summary interpretation">
        <ul className="space-y-3 text-sm text-[var(--text-main)]">
          {(insights?.key_insights || []).map((insight, index) => (
            <li key={index} className="rounded-xl border border-orange-300/35 bg-white/80 px-4 py-3">
              {insight}
            </li>
          ))}
        </ul>
      </GlassCard>
    </div>
  );
}
