import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  batchScorePortfolio,
  fetchPortfolio,
  fetchPortfolioAccount,
  updatePortfolioWorkflow,
} from "../api";
import GlassCard from "../components/GlassCard";

const workflowStatusOptions = [
  { value: "new", label: "New" },
  { value: "assigned", label: "Assigned" },
  { value: "in_progress", label: "In Progress" },
  { value: "contacted", label: "Contacted" },
  { value: "promise_to_pay", label: "Promise To Pay" },
  { value: "snoozed", label: "Snoozed" },
  { value: "escalated", label: "Escalated" },
  { value: "resolved", label: "Resolved" },
];

function nextIsoDays(days) {
  const now = new Date();
  now.setDate(now.getDate() + days);
  return now.toISOString();
}

function formatDateTime(value) {
  if (!value) {
    return "-";
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.valueOf())) {
    return "-";
  }

  return parsed.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function exportCsv(records, filePrefix = "risk_queue", preferredHeaders = []) {
  if (!records.length) {
    return;
  }

  const headers = preferredHeaders.length ? preferredHeaders : Object.keys(records[0]);

  const rows = records.map((record) =>
    headers
      .map((header) => {
        const value = record[header] ?? "";
        return `"${String(value).replaceAll('"', '""')}"`;
      })
      .join(",")
  );

  const blob = new Blob([[headers.join(","), ...rows].join("\n")], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);

  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${filePrefix}_${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}

export default function RiskQueue() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [portfolio, setPortfolio] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [searchInput, setSearchInput] = useState(searchParams.get("search") || "");
  const [riskFilter, setRiskFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [operatorName, setOperatorName] = useState("Agent Prime");
  const [activeAccountId, setActiveAccountId] = useState(null);
  const [activeAccount, setActiveAccount] = useState(null);
  const [activeAccountLoading, setActiveAccountLoading] = useState(false);
  const [noteDraft, setNoteDraft] = useState("");
  const [actionLoadingByAccount, setActionLoadingByAccount] = useState({});
  const [batchFile, setBatchFile] = useState(null);
  const [batchResult, setBatchResult] = useState(null);
  const [batchLoading, setBatchLoading] = useState(false);
  const [batchError, setBatchError] = useState("");

  function mergeUpdatedRecord(updatedRecord) {
    setPortfolio((previous) => {
      if (!previous) {
        return previous;
      }

      const records = previous.records.map((record) => {
        if (record.account_id !== updatedRecord.account_id) {
          return record;
        }

        const timeline = Array.isArray(updatedRecord.timeline) ? updatedRecord.timeline : [];
        return {
          ...record,
          ...updatedRecord,
          timeline_count: timeline.length,
          latest_event: timeline.length ? timeline[timeline.length - 1] : null,
        };
      });

      return {
        ...previous,
        records,
      };
    });

    setActiveAccount((previous) => {
      if (!previous || previous.account_id !== updatedRecord.account_id) {
        return previous;
      }
      return updatedRecord;
    });
  }

  async function applyWorkflowUpdate(accountId, payload) {
    setError("");
    setActionLoadingByAccount((previous) => ({ ...previous, [accountId]: true }));

    try {
      const response = await updatePortfolioWorkflow(accountId, payload);
      if (response.record) {
        mergeUpdatedRecord(response.record);
      }
    } catch (apiError) {
      setError(apiError.message || "Unable to update workflow.");
    } finally {
      setActionLoadingByAccount((previous) => ({ ...previous, [accountId]: false }));
    }
  }

  async function handleBatchScoreSubmit(event) {
    event.preventDefault();
    if (!batchFile) {
      setBatchError("Select a CSV or Excel file to run batch scoring.");
      return;
    }

    setBatchLoading(true);
    setBatchError("");
    try {
      const response = await batchScorePortfolio(batchFile, 5000);
      setBatchResult(response);
    } catch (apiError) {
      setBatchError(apiError.message || "Batch scoring failed.");
    } finally {
      setBatchLoading(false);
    }
  }

  useEffect(() => {
    let isMounted = true;

    async function loadPortfolio() {
      setLoading(true);
      setError("");
      try {
        const response = await fetchPortfolio({ limit: 1000 });
        if (isMounted) {
          setPortfolio(response);
        }
      } catch (apiError) {
        if (isMounted) {
          setError(apiError.message || "Unable to load risk queue.");
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    }

    loadPortfolio();

    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    let isMounted = true;

    async function loadAccountTimeline() {
      if (!activeAccountId) {
        setActiveAccount(null);
        return;
      }

      setActiveAccountLoading(true);
      try {
        const response = await fetchPortfolioAccount(activeAccountId);
        if (isMounted) {
          setActiveAccount(response.record || null);
        }
      } catch (apiError) {
        if (isMounted) {
          setError(apiError.message || "Unable to load account timeline.");
        }
      } finally {
        if (isMounted) {
          setActiveAccountLoading(false);
        }
      }
    }

    loadAccountTimeline();

    return () => {
      isMounted = false;
    };
  }, [activeAccountId]);

  const baseRecords = portfolio?.records || [];

  const filteredRecords = useMemo(() => {
    const query = searchInput.trim().toLowerCase();

    return baseRecords.filter((record) => {
      const riskMatch = riskFilter === "all" || record.risk_category === riskFilter;
      if (!riskMatch) {
        return false;
      }

      const statusMatch = statusFilter === "all" || record.workflow_status === statusFilter;
      if (!statusMatch) {
        return false;
      }

      if (!query) {
        return true;
      }

      return (
        record.account_id.toLowerCase().includes(query)
        || record.account_name.toLowerCase().includes(query)
        || record.risk_category.toLowerCase().includes(query)
        || String(record.workflow_status || "").toLowerCase().includes(query)
        || String(record.assigned_to || "").toLowerCase().includes(query)
      );
    });
  }, [baseRecords, riskFilter, searchInput, statusFilter]);

  useEffect(() => {
    const query = searchInput.trim();
    if (!query) {
      setSearchParams((previous) => {
        const next = new URLSearchParams(previous);
        next.delete("search");
        return next;
      });
      return;
    }

    setSearchParams((previous) => {
      const next = new URLSearchParams(previous);
      next.set("search", query);
      return next;
    });
  }, [searchInput, setSearchParams]);

  const filteredCounts = useMemo(() => {
    return {
      low: filteredRecords.filter((record) => record.risk_category === "low").length,
      medium: filteredRecords.filter((record) => record.risk_category === "medium").length,
      high: filteredRecords.filter((record) => record.risk_category === "high").length,
      contacted: filteredRecords.filter((record) => record.workflow_status === "contacted").length,
      snoozed: filteredRecords.filter((record) => record.workflow_status === "snoozed").length,
      resolved: filteredRecords.filter((record) => record.workflow_status === "resolved").length,
    };
  }, [filteredRecords]);

  const timelineEvents = useMemo(() => {
    if (!activeAccount || !Array.isArray(activeAccount.timeline)) {
      return [];
    }
    return [...activeAccount.timeline].reverse();
  }, [activeAccount]);

  if (loading) {
    return <div className="glass-card h-72 animate-pulse rounded-2xl" />;
  }

  if (error) {
    return (
      <GlassCard title="Risk Queue Error" subtitle="Portfolio feed is unavailable">
        <p>{error}</p>
      </GlassCard>
    );
  }

  return (
    <div className="space-y-4 fade-up">
      <GlassCard
        strong
        title="Operational Risk Queue"
        subtitle="Filter, assign, and work cases with workflow actions and timeline tracking"
      >
        <div className="grid gap-3 lg:grid-cols-[1.2fr,0.8fr,0.9fr,0.9fr,auto,auto]">
          <input
            className="input-field"
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
            placeholder="Search by account id, borrower name, or risk category"
            aria-label="Search queue"
          />

          <select
            className="input-field"
            value={riskFilter}
            onChange={(event) => setRiskFilter(event.target.value)}
            aria-label="Filter risk category"
          >
            <option value="all">All Risk Levels</option>
            <option value="high">High Risk</option>
            <option value="medium">Medium Risk</option>
            <option value="low">Low Risk</option>
          </select>

          <select
            className="input-field"
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
            aria-label="Filter workflow status"
          >
            <option value="all">All Workflow Statuses</option>
            {workflowStatusOptions.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>

          <input
            className="input-field"
            value={operatorName}
            onChange={(event) => setOperatorName(event.target.value)}
            aria-label="Operator name"
            placeholder="Operator name for assignment"
          />

          <button
            type="button"
            className="btn-secondary rounded-xl px-4 py-2.5"
            onClick={() => {
              setSearchInput("");
              setRiskFilter("all");
              setStatusFilter("all");
            }}
          >
            Clear Filters
          </button>

          <button
            type="button"
            className="btn-primary rounded-xl px-4 py-2.5"
            onClick={() => exportCsv(
              filteredRecords,
              "risk_queue",
              [
                "account_id",
                "account_name",
                "risk_category",
                "risk_score",
                "risk_probability",
                "credit_score",
                "debt_to_income_ratio",
                "credit_utilization",
                "missed_payments",
                "repayment_history",
                "workflow_status",
                "assigned_to",
                "follow_up_at",
                "snoozed_until",
                "timeline_count",
                "recommended_action",
              ]
            )}
          >
            Export CSV
          </button>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          <span className="metric-chip">Visible Accounts: {filteredRecords.length}</span>
          <span className="metric-chip">High: {filteredCounts.high}</span>
          <span className="metric-chip">Medium: {filteredCounts.medium}</span>
          <span className="metric-chip">Low: {filteredCounts.low}</span>
          <span className="metric-chip">Contacted: {filteredCounts.contacted}</span>
          <span className="metric-chip">Snoozed: {filteredCounts.snoozed}</span>
          <span className="metric-chip">Resolved: {filteredCounts.resolved}</span>
        </div>
      </GlassCard>

      <GlassCard title="Batch Scoring Upload" subtitle="Score uploaded borrower files and export prioritized results">
        <form className="grid gap-3 lg:grid-cols-[1fr,auto,auto]" onSubmit={handleBatchScoreSubmit}>
          <input
            className="input-field"
            type="file"
            accept=".csv,.xlsx,.xls"
            onChange={(event) => {
              setBatchFile(event.target.files?.[0] || null);
              setBatchError("");
            }}
          />

          <button type="submit" className="btn-primary rounded-xl px-4 py-2.5" disabled={batchLoading}>
            {batchLoading ? "Scoring..." : "Run Batch Score"}
          </button>

          <button
            type="button"
            className="btn-secondary rounded-xl px-4 py-2.5"
            disabled={!batchResult?.records?.length}
            onClick={() => exportCsv(batchResult.records, "batch_scored_results")}
          >
            Export Scored CSV
          </button>
        </form>

        {batchError ? (
          <p className="mt-3 rounded-xl border border-red-300/45 bg-red-100/70 px-4 py-3 text-sm text-[#7a3830]">
            {batchError}
          </p>
        ) : null}

        {batchResult?.summary ? (
          <div className="mt-3 flex flex-wrap gap-2">
            <span className="metric-chip">Uploaded: {batchResult.summary.uploaded_rows}</span>
            <span className="metric-chip">Scored: {batchResult.summary.scored_rows}</span>
            <span className="metric-chip">High: {batchResult.summary.risk_counts?.high || 0}</span>
            <span className="metric-chip">Medium: {batchResult.summary.risk_counts?.medium || 0}</span>
            <span className="metric-chip">Low: {batchResult.summary.risk_counts?.low || 0}</span>
            <span className="metric-chip">Avg Score: {batchResult.summary.average_risk_score}</span>
          </div>
        ) : null}
      </GlassCard>

      <div className="table-shell">
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Account</th>
                <th>Risk</th>
                <th>Score</th>
                <th>Workflow</th>
                <th>Owner</th>
                <th>Follow-Up</th>
                <th>Metrics</th>
                <th>Recommended Action</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredRecords.map((record) => {
                const isActive = activeAccountId === record.account_id;
                const isBusy = Boolean(actionLoadingByAccount[record.account_id]);

                return (
                <tr
                  key={record.account_id}
                  className={isActive ? "table-row-active" : ""}
                  onClick={() => setActiveAccountId(record.account_id)}
                >
                  <td>
                    <p className="font-semibold">{record.account_name}</p>
                    <p className="text-xs text-[#7a665b]">{record.account_id}</p>
                  </td>
                  <td>
                    <span className={`badge badge-${record.risk_category}`}>{record.risk_category}</span>
                  </td>
                  <td>{record.risk_score}</td>
                  <td>
                    <select
                      className="workflow-select"
                      value={record.workflow_status}
                      onChange={(event) => {
                        event.stopPropagation();
                        applyWorkflowUpdate(record.account_id, { status: event.target.value });
                      }}
                      disabled={isBusy}
                    >
                      {workflowStatusOptions.map((option) => (
                        <option key={option.value} value={option.value}>{option.label}</option>
                      ))}
                    </select>
                  </td>
                  <td>{record.assigned_to || "Unassigned"}</td>
                  <td>
                    <div className="text-xs text-[#6f5a50]">
                      <p>Follow-up: {formatDateTime(record.follow_up_at)}</p>
                      <p>Snoozed: {formatDateTime(record.snoozed_until)}</p>
                    </div>
                  </td>
                  <td>
                    <p className="text-xs text-[#6f5a50]">
                      CS {record.credit_score} | DTI {(record.debt_to_income_ratio * 100).toFixed(1)}% | Util {(record.credit_utilization * 100).toFixed(1)}% | Missed {record.missed_payments}
                    </p>
                  </td>
                  <td>{record.recommended_action}</td>
                  <td>
                    <div className="queue-action-stack">
                      <button
                        type="button"
                        className="queue-action-btn"
                        disabled={isBusy || !operatorName.trim()}
                        onClick={(event) => {
                          event.stopPropagation();
                          applyWorkflowUpdate(record.account_id, {
                            owner: operatorName.trim(),
                            status: "assigned",
                          });
                        }}
                      >
                        Assign
                      </button>
                      <button
                        type="button"
                        className="queue-action-btn"
                        disabled={isBusy}
                        onClick={(event) => {
                          event.stopPropagation();
                          applyWorkflowUpdate(record.account_id, {
                            status: "contacted",
                            follow_up_at: nextIsoDays(3),
                          });
                        }}
                      >
                        Contacted
                      </button>
                      <button
                        type="button"
                        className="queue-action-btn"
                        disabled={isBusy}
                        onClick={(event) => {
                          event.stopPropagation();
                          applyWorkflowUpdate(record.account_id, {
                            snoozed_until: nextIsoDays(3),
                            note: "Case snoozed for 3 days.",
                          });
                        }}
                      >
                        Snooze 3d
                      </button>
                    </div>
                  </td>
                </tr>
                );
              })}
              {!filteredRecords.length ? (
                <tr>
                  <td colSpan={9} className="py-8 text-center text-sm text-[#7a665b]">
                    No records match the current filters.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>

      <GlassCard
        title={activeAccount ? `Borrower Timeline: ${activeAccount.account_name}` : "Borrower Timeline"}
        subtitle={activeAccount ? `${activeAccount.account_id} activity log` : "Select an account from the queue to view activity"}
      >
        {!activeAccountId ? (
          <p className="text-sm text-[#7a665b]">Select any account row to open timeline, add notes, and update case progression.</p>
        ) : null}

        {activeAccountLoading ? <div className="h-24 animate-pulse rounded-xl bg-[#fff6ef]" /> : null}

        {activeAccount && !activeAccountLoading ? (
          <div className="space-y-4">
            <div className="flex flex-wrap gap-2">
              <span className="metric-chip">Status: {activeAccount.workflow_status}</span>
              <span className="metric-chip">Owner: {activeAccount.assigned_to || "Unassigned"}</span>
              <span className="metric-chip">Follow-up: {formatDateTime(activeAccount.follow_up_at)}</span>
              <span className="metric-chip">Updated: {formatDateTime(activeAccount.last_updated_at)}</span>
            </div>

            <div className="queue-action-stack-row">
              <button
                type="button"
                className="btn-secondary rounded-xl px-3 py-2"
                onClick={() => applyWorkflowUpdate(activeAccount.account_id, { status: "in_progress" })}
              >
                Set In Progress
              </button>
              <button
                type="button"
                className="btn-secondary rounded-xl px-3 py-2"
                onClick={() => applyWorkflowUpdate(activeAccount.account_id, { status: "promise_to_pay" })}
              >
                Mark Promise To Pay
              </button>
              <button
                type="button"
                className="btn-secondary rounded-xl px-3 py-2"
                onClick={() => applyWorkflowUpdate(activeAccount.account_id, { status: "resolved" })}
              >
                Resolve Case
              </button>
            </div>

            <div className="timeline-shell">
              {timelineEvents.length ? timelineEvents.map((event) => (
                <article key={event.event_id} className="timeline-item">
                  <header className="timeline-item-header">
                    <span className="timeline-type">{String(event.event_type || "event").replaceAll("_", " ")}</span>
                    <span className="timeline-time">{formatDateTime(event.created_at)}</span>
                  </header>
                  <p className="timeline-description">{event.description}</p>
                  <p className="timeline-actor">By {event.actor || "system"}</p>
                </article>
              )) : (
                <p className="text-sm text-[#7a665b]">No timeline events yet for this account.</p>
              )}
            </div>

            <div className="space-y-2">
              <label className="input-label" htmlFor="timeline-note">Add Case Note</label>
              <textarea
                id="timeline-note"
                className="input-field min-h-24"
                value={noteDraft}
                onChange={(event) => setNoteDraft(event.target.value)}
                placeholder="Write a collections note, negotiation update, or repayment commitment."
              />
              <button
                type="button"
                className="btn-primary rounded-xl px-4 py-2"
                disabled={!noteDraft.trim()}
                onClick={async () => {
                  await applyWorkflowUpdate(activeAccount.account_id, { note: noteDraft.trim() });
                  setNoteDraft("");
                }}
              >
                Save Note
              </button>
            </div>
          </div>
        ) : null}
      </GlassCard>
    </div>
  );
}
