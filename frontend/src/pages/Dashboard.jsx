import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { fetchAlerts, fetchInsights, fetchPortfolio } from "../api";
import RiskTrendChart from "../charts/RiskTrendChart";
import GlassCard from "../components/GlassCard";
import KpiCard from "../components/KpiCard";

function safePercent(value, total) {
  if (!total) {
    return 0;
  }
  return Math.max(0, Math.min(100, (value / total) * 100));
}

function buildTrendRows(records) {
  if (!records.length) {
    return Array.from({ length: 10 }, (_, index) => ({
      label: String(index + 1).padStart(2, "0"),
      low: 0,
      medium: 0,
      high: 0,
    }));
  }

  const sorted = [...records].sort((a, b) => a.risk_score - b.risk_score);
  const step = Math.max(1, Math.ceil(sorted.length / 10));
  const buckets = Array.from({ length: 10 }, (_, index) => ({
    label: String(index + 1).padStart(2, "0"),
    low: 0,
    medium: 0,
    high: 0,
  }));

  sorted.forEach((record, index) => {
    const bucketIndex = Math.min(9, Math.floor(index / step));
    buckets[bucketIndex][record.risk_category] += 1;
  });

  return buckets;
}

export default function Dashboard() {
  const [insights, setInsights] = useState(null);
  const [portfolio, setPortfolio] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let isMounted = true;

    async function loadData() {
      setLoading(true);
      setError("");
      try {
        const [insightsResponse, portfolioResponse, alertsResponse] = await Promise.all([
          fetchInsights(),
          fetchPortfolio({ limit: 400, summaryMode: "full" }),
          fetchAlerts(8),
        ]);

        if (isMounted) {
          setInsights(insightsResponse);
          setPortfolio(portfolioResponse);
          setAlerts(alertsResponse.alerts || []);
        }
      } catch (apiError) {
        if (isMounted) {
          setError(apiError.message || "Unable to load dashboard data.");
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    }

    loadData();

    return () => {
      isMounted = false;
    };
  }, []);

  const records = portfolio?.records || [];
  const summary = portfolio?.summary || {};
  const model = insights?.model_performance || {};
  const riskCounts = summary.risk_counts || {};
  const workflowCounts = summary.workflow_counts || {};
  const totalRecords = Number(summary.total_records || 0);
  const refreshedAt = insights?.generated_at || portfolio?.generated_at || null;

  const trendRows = useMemo(() => {
    const deciles = summary.risk_deciles;
    if (Array.isArray(deciles) && deciles.length) {
      return deciles.map((row, index) => ({
        label: String(row.label || String(index + 1).padStart(2, "0")),
        low: Number(row.low || 0),
        medium: Number(row.medium || 0),
        high: Number(row.high || 0),
      }));
    }

    return buildTrendRows(records);
  }, [summary, records]);
  const actionQueue = useMemo(
    () => records.filter((item) => item.risk_category === "high" && item.workflow_status !== "resolved").slice(0, 6),
    [records]
  );
  const unassignedHighRisk = useMemo(
    () =>
      records.filter(
        (item) =>
          item.risk_category === "high"
          && item.workflow_status !== "resolved"
          && !item.assigned_to
      ).length,
    [records]
  );
  const contactedWithoutFollowUp = useMemo(
    () => records.filter((item) => item.workflow_status === "contacted" && !item.follow_up_at).length,
    [records]
  );
  const snoozedOpenCases = useMemo(
    () => records.filter((item) => item.workflow_status === "snoozed").length,
    [records]
  );
  const ownerLoad = useMemo(() => {
    const ownerMap = new Map();

    records.forEach((item) => {
      if (item.risk_category !== "high" || item.workflow_status === "resolved") {
        return;
      }

      const owner = item.assigned_to || "Unassigned";
      ownerMap.set(owner, (ownerMap.get(owner) || 0) + 1);
    });

    return Array.from(ownerMap.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .map(([owner, count]) => ({ owner, count }));
  }, [records]);
  const peakHighBucket = useMemo(() => {
    if (!trendRows.length) {
      return { label: "--", high: 0, medium: 0, low: 0 };
    }

    return trendRows.reduce((peak, row) => (row.high > peak.high ? row : peak), trendRows[0]);
  }, [trendRows]);
  const highSeverityAlertCount = useMemo(
    () => alerts.filter((item) => item.severity === "high").length,
    [alerts]
  );
  const workflowRows = useMemo(
    () => [
      { label: "New", value: Number(workflowCounts.new || 0), tone: "neutral" },
      { label: "Assigned", value: Number(workflowCounts.assigned || 0), tone: "neutral" },
      { label: "In Progress", value: Number(workflowCounts.in_progress || 0), tone: "active" },
      { label: "Contacted", value: Number(workflowCounts.contacted || 0), tone: "active" },
      { label: "Promise To Pay", value: Number(workflowCounts.promise_to_pay || 0), tone: "active" },
      { label: "Snoozed", value: Number(workflowCounts.snoozed || 0), tone: "warning" },
      { label: "Resolved", value: Number(workflowCounts.resolved || 0), tone: "success" },
    ],
    [workflowCounts]
  );

  const riskRows = useMemo(
    () => [
      { label: "High Risk", value: Number(riskCounts.high || 0), tone: "high" },
      { label: "Medium Risk", value: Number(riskCounts.medium || 0), tone: "medium" },
      { label: "Low Risk", value: Number(riskCounts.low || 0), tone: "low" },
    ],
    [riskCounts]
  );

  if (loading) {
    return <div className="glass-card h-72 animate-pulse rounded-2xl" />;
  }

  if (error) {
    return (
      <GlassCard title="Dashboard Error" subtitle="Data service unavailable">
        <p>{error}</p>
      </GlassCard>
    );
  }

  return (
    <div className="dashboard-layout space-y-5 fade-up">
      <GlassCard strong className="dashboard-hero-card">
        <div className="dashboard-hero">
          <div>
            <p className="dashboard-eyebrow">Portfolio Operations Hub</p>
            <h2 className="dashboard-hero-title display-font">Collections Command Center</h2>
            <p className="dashboard-hero-copy">
              Track risk concentration, resolve queue bottlenecks, and prioritize borrower actions from one
              operational workspace.
            </p>
          </div>

          <div className="dashboard-hero-meta">
            <span className="metric-chip">Model: {model.selected_model || "n/a"}</span>
            <span className="metric-chip">Decision Threshold: {model.decision_threshold ?? "n/a"}</span>
            <span className="metric-chip">Accuracy: {model.accuracy ?? "n/a"}</span>
            <span className="metric-chip">Refreshed: {refreshedAt ? new Date(refreshedAt).toLocaleString() : "Live"}</span>
          </div>
        </div>
      </GlassCard>

      <div className="dashboard-kpi-grid stagger">
        <KpiCard
          title="Total Accounts"
          value={summary.total_records?.toLocaleString() || "0"}
          subtext="Borrowers currently monitored"
        />
        <KpiCard
          title="High Priority"
          value={summary.high_priority?.toLocaleString() || "0"}
          subtext="Accounts requiring immediate follow-up"
          accent="text-[#9a4c32]"
        />
        <KpiCard
          title="Average Risk Score"
          value={summary.average_risk_score ?? "0"}
          subtext="Portfolio-level risk baseline"
          accent="text-[#8a5a42]"
        />
        <KpiCard
          title="Due Follow-Ups"
          value={summary.due_followups?.toLocaleString() || "0"}
          subtext={`Open contacted: ${(summary.workflow_counts?.contacted ?? 0).toLocaleString()} | Alerts: ${(summary.alert_count ?? 0).toLocaleString()}`}
          accent="text-[#6f523f]"
        />
      </div>

      <div className="dashboard-main-grid">
        <div className="dashboard-rail dashboard-left-rail">
          <GlassCard
            className="dashboard-trend-card"
            title="Risk Pattern Trend"
            subtitle={`Distribution of low, medium, and high risk across portfolio deciles | model ${model.selected_model || "n/a"} (acc ${model.accuracy ?? "n/a"})`}
          >
            <RiskTrendChart rows={trendRows} />

            <div className="trend-summary-grid">
              <article className="trend-summary-card">
                <p className="trend-summary-label">Peak High-Risk Decile</p>
                <p className="trend-summary-value">{peakHighBucket.label}</p>
                <p className="trend-summary-meta">{peakHighBucket.high} high-risk accounts in this bucket</p>
              </article>

              <article className="trend-summary-card">
                <p className="trend-summary-label">Open High-Risk Queue</p>
                <p className="trend-summary-value">{Number(summary.high_priority || 0).toLocaleString()}</p>
                <p className="trend-summary-meta">Unresolved high-risk borrowers needing action</p>
              </article>

              <article className="trend-summary-card">
                <p className="trend-summary-label">High-Severity Alerts</p>
                <p className="trend-summary-value">{highSeverityAlertCount.toLocaleString()}</p>
                <p className="trend-summary-meta">Immediate operational exceptions currently active</p>
              </article>
            </div>

            <div className="trend-risk-strip">
              {riskRows.map((item) => {
                const pct = safePercent(item.value, totalRecords);
                return (
                  <div key={item.label} className="trend-risk-item">
                    <div className="trend-risk-head">
                      <span>{item.label}</span>
                      <span>{pct.toFixed(1)}%</span>
                    </div>
                    <div className="workflow-track">
                      <div className={`workflow-fill tone-${item.tone}`} style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                );
              })}
            </div>
          </GlassCard>

          <GlassCard
            title="Operational Focus Board"
            subtitle="Live workflow pressure points that need intervention before SLA breaches"
          >
            <div className="focus-kpi-grid">
              <article className="focus-kpi-card">
                <p className="focus-kpi-label">Unassigned High Risk</p>
                <p className="focus-kpi-value">{unassignedHighRisk.toLocaleString()}</p>
              </article>
              <article className="focus-kpi-card">
                <p className="focus-kpi-label">Contacted Without Follow-Up</p>
                <p className="focus-kpi-value">{contactedWithoutFollowUp.toLocaleString()}</p>
              </article>
              <article className="focus-kpi-card">
                <p className="focus-kpi-label">Snoozed Open Cases</p>
                <p className="focus-kpi-value">{snoozedOpenCases.toLocaleString()}</p>
              </article>
            </div>

            <div className="focus-owner-list">
              {ownerLoad.map((row) => {
                const pct = safePercent(row.count, Number(summary.high_priority || 0));
                return (
                  <div key={row.owner} className="focus-owner-item">
                    <div className="focus-owner-head">
                      <p>{row.owner}</p>
                      <p>{row.count.toLocaleString()}</p>
                    </div>
                    <div className="workflow-track">
                      <div className="workflow-fill tone-active" style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                );
              })}
              {!ownerLoad.length ? (
                <p className="rounded-xl border border-[#ead9cc] bg-[#fff9f4] px-3 py-3 text-sm text-[#7a665b]">
                  Owner workload data will appear once high-risk accounts are assigned.
                </p>
              ) : null}
            </div>
          </GlassCard>
        </div>

        <div className="dashboard-rail">
          <GlassCard title="Action Queue" subtitle="Top high-risk accounts prioritized for operations">
            <div className="dashboard-feed-scroll">
              {actionQueue.map((record) => (
                <div
                  key={record.account_id}
                  className="dashboard-feed-item"
                >
                  <div className="flex items-center justify-between gap-2">
                    <p className="font-semibold">{record.account_name}</p>
                    <span className="badge badge-high">High</span>
                  </div>
                  <p className="dashboard-feed-meta">
                    Score {record.risk_score} | Missed {record.missed_payments} | DTI {(record.debt_to_income_ratio * 100).toFixed(1)}%
                  </p>
                  <p className="dashboard-feed-meta">
                    Workflow: {String(record.workflow_status || "new").replaceAll("_", " ")} | Owner: {record.assigned_to || "Unassigned"}
                  </p>
                </div>
              ))}
              {!actionQueue.length ? (
                <p className="rounded-xl border border-[#ead9cc] bg-[#fff9f4] px-3 py-3 text-sm text-[#7a665b]">
                  No high-risk accounts found for the current snapshot.
                </p>
              ) : null}
            </div>
          </GlassCard>

          <GlassCard title="Alert Center" subtitle="Operational alerts requiring immediate review">
            <div className="dashboard-feed-scroll">
              {alerts.map((alert) => (
                <div
                  key={alert.alert_id}
                  className="dashboard-feed-item"
                >
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-semibold text-[#4d3b31]">{alert.title}</p>
                    <span className={`badge ${alert.severity === "high" ? "badge-high" : "badge-medium"}`}>
                      {alert.severity}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-[#745d50]">{alert.account_name} ({alert.account_id})</p>
                  <p className="mt-1 text-xs text-[#7f6558]">{alert.description}</p>
                </div>
              ))}
              {!alerts.length ? (
                <p className="rounded-xl border border-[#ead9cc] bg-[#fff9f4] px-3 py-3 text-sm text-[#7a665b]">
                  No active alerts at the moment.
                </p>
              ) : null}
            </div>
          </GlassCard>
        </div>
      </div>

      <div className="dashboard-bottom-grid">
        <GlassCard title="Workflow Snapshot" subtitle="Case movement by current operational state">
          <div className="workflow-snapshot-grid">
            {workflowRows.map((item) => {
              const pct = safePercent(item.value, totalRecords);

              return (
                <div key={item.label} className="workflow-snapshot-row">
                  <div className="workflow-snapshot-head">
                    <p>{item.label}</p>
                    <p>{item.value.toLocaleString()}</p>
                  </div>
                  <div className="workflow-track">
                    <div
                      className={`workflow-fill tone-${item.tone}`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </GlassCard>

        <GlassCard title="Portfolio Mix" subtitle="Current risk composition and direct action paths">
          <div className="workflow-snapshot-grid">
            {riskRows.map((item) => {
              const pct = safePercent(item.value, totalRecords);
              return (
                <div key={item.label} className="workflow-snapshot-row">
                  <div className="workflow-snapshot-head">
                    <p>{item.label}</p>
                    <p>{item.value.toLocaleString()}</p>
                  </div>
                  <div className="workflow-track">
                    <div
                      className={`workflow-fill tone-${item.tone}`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>

          <div className="dashboard-quick-grid">
            <Link to="/prediction" className="btn-primary rounded-xl px-4 py-3 text-center">
              Run New Assessment
            </Link>
            <Link to="/risk-queue" className="btn-secondary rounded-xl px-4 py-3 text-center">
              Open Risk Queue
            </Link>
            <Link to="/insights" className="btn-secondary rounded-xl px-4 py-3 text-center">
              Review Model Insights
            </Link>
          </div>
        </GlassCard>
      </div>
    </div>
  );
}
