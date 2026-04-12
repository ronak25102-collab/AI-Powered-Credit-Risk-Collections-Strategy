import { useEffect, useMemo, useState } from "react";
import { predictRisk } from "../api";
import GlassCard from "../components/GlassCard";

const initialFormState = {
  income: "6200",
  income_period: "monthly",
  loan_amount: "18000",
  age: "34",
  years_experience: "8",
  credit_score: "710",
  missed_payments: "1",
  repayment_history_pct: "90",
  credit_utilization_pct: "",
  debt_to_income_pct: "",
};

const categoryStyles = {
  low: {
    ring: "#ffc08f",
    badge: "border-orange-300/40 bg-orange-200/65 text-[#7f4f38]",
  },
  medium: {
    ring: "#ff9b6b",
    badge: "border-orange-300/50 bg-orange-300/60 text-[#73412a]",
  },
  high: {
    ring: "#ff6d5f",
    badge: "border-red-300/55 bg-red-200/65 text-[#713933]",
  },
};

const initialWhatIfState = {
  income_shift_pct: "0",
  loan_amount_delta: "0",
  missed_payments_delta: "0",
  repayment_shift_pct: "0",
};

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function toNumber(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function buildPredictionPayload(source) {
  const utilizationRatio =
    String(source.credit_utilization_pct || "").trim() === ""
      ? null
      : toNumber(source.credit_utilization_pct) / 100;

  const debtToIncomeRatio =
    String(source.debt_to_income_pct || "").trim() === ""
      ? null
      : toNumber(source.debt_to_income_pct) / 100;

  return {
    income: toNumber(source.income, 0),
    income_period: source.income_period,
    loan_amount: toNumber(source.loan_amount, 0),
    age: String(source.age || "").trim() === "" ? null : toNumber(source.age),
    years_experience:
      String(source.years_experience || "").trim() === "" ? null : toNumber(source.years_experience),
    credit_score: toNumber(source.credit_score, 300),
    missed_payments: toNumber(source.missed_payments, 0),
    repayment_history: toNumber(source.repayment_history_pct, 0) / 100,
    credit_utilization: utilizationRatio,
    debt_to_income_ratio: debtToIncomeRatio,
  };
}

export default function RiskPrediction() {
  const [formState, setFormState] = useState(initialFormState);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [whatIfState, setWhatIfState] = useState(initialWhatIfState);
  const [whatIfLoading, setWhatIfLoading] = useState(false);
  const [whatIfResult, setWhatIfResult] = useState(null);
  const [whatIfError, setWhatIfError] = useState("");
  const [savedProfiles, setSavedProfiles] = useState([]);
  const [selectedProfileId, setSelectedProfileId] = useState("");

  useEffect(() => {
    const raw = window.localStorage.getItem("risk_prediction_profiles_v1");
    if (!raw) {
      return;
    }

    try {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        setSavedProfiles(parsed);
      }
    } catch {
      setSavedProfiles([]);
    }
  }, []);

  function persistProfiles(nextProfiles) {
    setSavedProfiles(nextProfiles);
    window.localStorage.setItem("risk_prediction_profiles_v1", JSON.stringify(nextProfiles));
  }

  const score = result?.risk_score || 0;
  const category = result?.risk_category || "low";
  const currentStyle = categoryStyles[category] || categoryStyles.low;

  const gaugeStyle = useMemo(
    () => ({
      background: `conic-gradient(${currentStyle.ring} ${score}%, rgba(201,122,77,0.16) ${score}% 100%)`,
    }),
    [currentStyle.ring, score]
  );

  const simulationPreview = useMemo(() => {
    const payload = buildPredictionPayload(formState);

    const incomeShift = clamp(toNumber(whatIfState.income_shift_pct, 0), -70, 120) / 100;
    const loanDelta = toNumber(whatIfState.loan_amount_delta, 0);
    const missedDelta = Math.round(toNumber(whatIfState.missed_payments_delta, 0));
    const repaymentShift = clamp(toNumber(whatIfState.repayment_shift_pct, 0), -100, 100) / 100;

    const simulated = {
      ...payload,
      income: Math.max(1, payload.income * (1 + incomeShift)),
      loan_amount: Math.max(0, payload.loan_amount + loanDelta),
      missed_payments: clamp(Math.round(payload.missed_payments + missedDelta), 0, 60),
      repayment_history: clamp(payload.repayment_history + repaymentShift, 0, 1),
    };

    return simulated;
  }, [formState, whatIfState]);

  const scenarioDeltaText = useMemo(() => {
    if (!whatIfResult || !result) {
      return "";
    }

    const delta = whatIfResult.risk_score - result.risk_score;
    const direction = delta >= 0 ? "+" : "";
    return `${direction}${delta.toFixed(1)} pts vs baseline`;
  }, [result, whatIfResult]);

  const driverRows = result?.top_drivers || [];
  const maxDriverImpact = useMemo(() => {
    if (!driverRows.length) {
      return 1;
    }
    return Math.max(...driverRows.map((driver) => Math.abs(Number(driver.impact) || 0)), 1);
  }, [driverRows]);

  function handleChange(event) {
    const { name, value } = event.target;
    setFormState((previous) => ({ ...previous, [name]: value }));
    setWhatIfResult(null);
    setWhatIfError("");
  }

  function handleWhatIfChange(event) {
    const { name, value } = event.target;
    setWhatIfState((previous) => ({ ...previous, [name]: value }));
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setLoading(true);
    setError("");
    const payload = buildPredictionPayload(formState);

    try {
      const prediction = await predictRisk(payload);
      setResult(prediction);
      setWhatIfResult(null);
      setWhatIfError("");
    } catch (apiError) {
      setError(apiError.message || "Prediction request failed.");
    } finally {
      setLoading(false);
    }
  }

  function resetForm() {
    setFormState(initialFormState);
    setWhatIfState(initialWhatIfState);
    setWhatIfResult(null);
    setWhatIfError("");
    setResult(null);
    setError("");
  }

  function saveCurrentProfile() {
    const profileName = window.prompt("Profile name", `Profile ${savedProfiles.length + 1}`);
    if (!profileName) {
      return;
    }

    const nextProfiles = [
      {
        id: `profile-${Date.now()}`,
        name: profileName.trim(),
        formState,
        savedAt: new Date().toISOString(),
      },
      ...savedProfiles,
    ].slice(0, 10);

    persistProfiles(nextProfiles);
  }

  function loadSelectedProfile(profileId) {
    setSelectedProfileId(profileId);
    const profile = savedProfiles.find((item) => item.id === profileId);
    if (!profile) {
      return;
    }
    setFormState(profile.formState);
    setWhatIfState(initialWhatIfState);
    setWhatIfResult(null);
    setWhatIfError("");
    setResult(null);
    setError("");
  }

  function deleteSelectedProfile() {
    if (!selectedProfileId) {
      return;
    }
    const nextProfiles = savedProfiles.filter((item) => item.id !== selectedProfileId);
    persistProfiles(nextProfiles);
    setSelectedProfileId("");
  }

  async function runWhatIfSimulation() {
    setWhatIfLoading(true);
    setWhatIfError("");

    try {
      const prediction = await predictRisk(simulationPreview);
      setWhatIfResult(prediction);
    } catch (apiError) {
      setWhatIfError(apiError.message || "Scenario simulation failed.");
    } finally {
      setWhatIfLoading(false);
    }
  }

  return (
    <div className="grid gap-5 lg:grid-cols-[1.2fr,0.8fr] fade-up">
      <GlassCard
        strong
        title="Borrower Risk Estimator"
        subtitle="Unit-aware inputs with optional auto-calculation for utilization and DTI"
      >
        <form className="space-y-4" onSubmit={handleSubmit}>
          <div className="grid gap-4 sm:grid-cols-2 stagger">
            <label className="space-y-2 sm:col-span-2">
              <span className="input-label">Income</span>
              <div className="inline-field">
                <input
                  className="input-field"
                  name="income"
                  type="number"
                  min="1"
                  step="1"
                  value={formState.income}
                  onChange={handleChange}
                  required
                />
                <select
                  className="input-field w-[142px]"
                  name="income_period"
                  value={formState.income_period}
                  onChange={handleChange}
                >
                  <option value="monthly">Per Month</option>
                  <option value="annual">Per Year</option>
                </select>
              </div>
              <p className="input-help">Choose monthly or annual income so the model interprets the value correctly.</p>
            </label>

            <label className="space-y-2">
              <span className="input-label">Loan Amount</span>
              <input
                className="input-field"
                name="loan_amount"
                type="number"
                min="0"
                step="1"
                value={formState.loan_amount}
                onChange={handleChange}
                required
              />
              <p className="input-help">Requested or outstanding loan amount in the same currency as income.</p>
            </label>

            <label className="space-y-2">
              <span className="input-label">Credit Score</span>
              <input
                className="input-field"
                name="credit_score"
                type="number"
                min="300"
                max="850"
                value={formState.credit_score}
                onChange={handleChange}
                required
              />
              <p className="input-help">Standard credit score range: 300 to 850.</p>
            </label>

            <label className="space-y-2">
              <span className="input-label">Age (Optional)</span>
              <input
                className="input-field"
                name="age"
                type="number"
                min="18"
                max="100"
                value={formState.age}
                onChange={handleChange}
              />
              <p className="input-help">Included for model precision when available.</p>
            </label>

            <label className="space-y-2">
              <span className="input-label">Years of Experience (Optional)</span>
              <input
                className="input-field"
                name="years_experience"
                type="number"
                min="0"
                max="60"
                step="0.5"
                value={formState.years_experience}
                onChange={handleChange}
              />
              <p className="input-help">Professional experience in years.</p>
            </label>

            <label className="space-y-2">
              <span className="input-label">Missed Payments</span>
              <input
                className="input-field"
                name="missed_payments"
                type="number"
                min="0"
                max="60"
                value={formState.missed_payments}
                onChange={handleChange}
                required
              />
              <p className="input-help">Missed payment count in the recent repayment period.</p>
            </label>

            <label className="space-y-2">
              <span className="input-label">Repayment History (%)</span>
              <input
                className="input-field"
                name="repayment_history_pct"
                type="number"
                min="0"
                max="100"
                step="1"
                value={formState.repayment_history_pct}
                onChange={handleChange}
                required
              />
              <p className="input-help">On-time repayment percentage. Example: 90 means 90% on-time payments.</p>
            </label>

            <label className="space-y-2">
              <span className="input-label">Credit Utilization (%)</span>
              <input
                className="input-field"
                name="credit_utilization_pct"
                type="number"
                min="0"
                max="100"
                step="0.1"
                value={formState.credit_utilization_pct}
                onChange={handleChange}
                placeholder="Leave blank to auto-calculate"
              />
              <p className="input-help">If blank, the API estimates it from income and loan amount.</p>
            </label>

            <label className="space-y-2">
              <span className="input-label">Debt-to-Income (%)</span>
              <input
                className="input-field"
                name="debt_to_income_pct"
                type="number"
                min="0"
                max="150"
                step="0.1"
                value={formState.debt_to_income_pct}
                onChange={handleChange}
                placeholder="Leave blank to auto-calculate"
              />
              <p className="input-help">If blank, computed automatically as loan amount divided by annual income.</p>
            </label>
          </div>

          <div className="rounded-xl border border-orange-300/35 bg-orange-100/70 px-4 py-3 text-xs text-[var(--text-main)]">
            For clarity: percentages are entered as 0-100 values, and income can be monthly or yearly.
          </div>

          <div className="flex flex-wrap gap-3 pt-2">
            <button type="submit" className="btn-primary rounded-xl px-5 py-2.5" disabled={loading}>
              {loading ? "Scoring..." : "Predict Risk"}
            </button>
            <button type="button" className="btn-secondary rounded-xl px-5 py-2.5" onClick={resetForm}>
              Reset
            </button>
            <button type="button" className="btn-secondary rounded-xl px-5 py-2.5" onClick={saveCurrentProfile}>
              Save Profile
            </button>
          </div>

          {savedProfiles.length ? (
            <div className="grid gap-3 rounded-xl border border-[#ecd8ca] bg-[#fff7f1] p-3 sm:grid-cols-[1fr,auto,auto]">
              <select
                className="input-field"
                value={selectedProfileId}
                onChange={(event) => loadSelectedProfile(event.target.value)}
              >
                <option value="">Load saved profile</option>
                {savedProfiles.map((profile) => (
                  <option key={profile.id} value={profile.id}>
                    {profile.name} ({new Date(profile.savedAt).toLocaleDateString()})
                  </option>
                ))}
              </select>
              <button type="button" className="btn-secondary rounded-xl px-4 py-2" onClick={deleteSelectedProfile}>
                Delete
              </button>
              <p className="self-center text-xs text-[#7a665b]">Stored locally in your browser</p>
            </div>
          ) : null}

          {error ? (
            <p className="rounded-xl border border-red-300/45 bg-red-100/70 px-4 py-3 text-sm text-[#7a3830]">
              {error}
            </p>
          ) : null}
        </form>
      </GlassCard>

      <GlassCard title="Prediction Output" subtitle="Risk score and model explanation">
        <div className="flex flex-col items-center gap-4 text-center">
          <div className="rounded-full p-2" style={gaugeStyle}>
            <div className="flex h-36 w-36 items-center justify-center rounded-full border border-orange-200/60 bg-white/95">
              <div>
                <p className="display-font text-3xl font-semibold">{score.toFixed(1)}%</p>
                <p className="text-xs uppercase tracking-[0.2em] text-[var(--text-muted)]">Risk Score</p>
              </div>
            </div>
          </div>

          <span
            className={`rounded-full border px-4 py-1 text-xs font-semibold uppercase tracking-[0.18em] ${currentStyle.badge}`}
          >
            {category} risk
          </span>

          <div className="grid w-full gap-2 text-xs text-[var(--text-muted)] sm:grid-cols-2">
            <p className="rounded-lg border border-orange-300/35 bg-white/80 px-3 py-2">
              Model Probability: {result?.model_probability ?? "-"}
            </p>
            <p className="rounded-lg border border-orange-300/35 bg-white/80 px-3 py-2">
              Business Index: {result?.business_risk_index ?? "-"}
            </p>
          </div>

          <p className="text-sm text-[var(--text-main)]">
            {result?.explanation ||
              "Submit the borrower profile to receive a delinquency risk score and plain-language explanation."}
          </p>

          {result?.collections_strategy?.strategy ? (
            <div className="w-full rounded-xl border border-[#ecd8ca] bg-[#fff8f1] p-3 text-left">
              <h3 className="display-font text-base font-semibold">Strategy Recommendation</h3>
              <p className="mt-1 text-sm text-[#4f3a2f]">
                {result.collections_strategy.strategy} ({result.collections_strategy.priority} priority)
              </p>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-[#6a5448]">
                {(result.collections_strategy.next_steps || []).map((step) => (
                  <li key={step}>{step}</li>
                ))}
              </ul>
            </div>
          ) : null}

          {driverRows.length ? (
            <div className="w-full rounded-xl border border-[#ecd8ca] bg-[#fff8f2] p-3 text-left">
              <h3 className="display-font text-base font-semibold">Top Drivers</h3>
              <div className="mt-2 space-y-2">
                {driverRows.map((driver) => {
                  const impact = Number(driver.impact) || 0;
                  const width = `${Math.max(8, (Math.abs(impact) / maxDriverImpact) * 100)}%`;
                  const isRiskUp = driver.direction !== "risk_down";

                  return (
                    <div key={`${driver.feature}-${driver.impact}`}>
                      <div className="mb-1 flex items-center justify-between gap-2 text-xs">
                        <span className="text-[#4c3a31]">{driver.feature}</span>
                        <span className={isRiskUp ? "text-[#934735]" : "text-[#2f7a58]"}>
                          {impact >= 0 ? "+" : ""}{impact.toFixed(3)}
                        </span>
                      </div>
                      <div className="h-2 rounded-full bg-[#f3dfd2]">
                        <div
                          className="h-full rounded-full"
                          style={{
                            width,
                            background: isRiskUp ? "linear-gradient(90deg, #ffb392, #ff8c5f)" : "linear-gradient(90deg, #9fe2bc, #4dbd88)",
                          }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : null}

          {result?.override_applied ? (
            <p className="rounded-xl border border-orange-300/45 bg-orange-200/65 px-4 py-2 text-sm text-[#774530]">
              {result.override_reason}
            </p>
          ) : null}

          <div className="w-full rounded-xl border border-[#ecd6c9] bg-[#fff7f0] p-3 text-left">
            <h3 className="display-font text-base font-semibold">What-If Simulator</h3>
            <p className="mt-1 text-xs text-[var(--text-muted)]">
              Stress test small profile changes before final decisions.
            </p>

            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              <label className="space-y-1">
                <span className="input-label">Income Shift (%)</span>
                <input
                  className="input-field"
                  type="number"
                  min="-70"
                  max="120"
                  step="1"
                  name="income_shift_pct"
                  value={whatIfState.income_shift_pct}
                  onChange={handleWhatIfChange}
                />
              </label>

              <label className="space-y-1">
                <span className="input-label">Loan Delta (Amount)</span>
                <input
                  className="input-field"
                  type="number"
                  step="1"
                  name="loan_amount_delta"
                  value={whatIfState.loan_amount_delta}
                  onChange={handleWhatIfChange}
                />
              </label>

              <label className="space-y-1">
                <span className="input-label">Missed Payments Delta</span>
                <input
                  className="input-field"
                  type="number"
                  min="-15"
                  max="15"
                  step="1"
                  name="missed_payments_delta"
                  value={whatIfState.missed_payments_delta}
                  onChange={handleWhatIfChange}
                />
              </label>

              <label className="space-y-1">
                <span className="input-label">Repayment Shift (pp)</span>
                <input
                  className="input-field"
                  type="number"
                  min="-60"
                  max="60"
                  step="1"
                  name="repayment_shift_pct"
                  value={whatIfState.repayment_shift_pct}
                  onChange={handleWhatIfChange}
                />
              </label>
            </div>

            <div className="mt-3 rounded-lg border border-[#ecd9cc] bg-white px-3 py-2 text-xs text-[#6d5a50]">
              Scenario Preview: Income {simulationPreview.income.toFixed(0)}, Loan {simulationPreview.loan_amount.toFixed(0)}, Missed {simulationPreview.missed_payments}, Repayment {(simulationPreview.repayment_history * 100).toFixed(1)}%
            </div>

            <div className="mt-3 flex flex-wrap items-center gap-2">
              <button
                type="button"
                className="btn-secondary rounded-xl px-4 py-2"
                onClick={runWhatIfSimulation}
                disabled={whatIfLoading}
              >
                {whatIfLoading ? "Simulating..." : "Run Scenario"}
              </button>

              {whatIfResult ? (
                <span className="metric-chip">
                  Scenario Risk: {whatIfResult.risk_score.toFixed(1)}% {scenarioDeltaText ? `(${scenarioDeltaText})` : ""}
                </span>
              ) : null}
            </div>

            {whatIfResult?.explanation ? (
              <p className="mt-2 text-xs text-[#5f4b40]">{whatIfResult.explanation}</p>
            ) : null}

            {whatIfError ? (
              <p className="mt-2 rounded-lg border border-red-300/45 bg-red-100/75 px-3 py-2 text-xs text-[#7a3830]">
                {whatIfError}
              </p>
            ) : null}
          </div>
        </div>
      </GlassCard>
    </div>
  );
}
