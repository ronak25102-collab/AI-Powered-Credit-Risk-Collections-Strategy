const API_BASE_URL = import.meta.env?.VITE_API_URL || "http://127.0.0.1:8000";
const REQUEST_TIMEOUT_MS = 15000;

const ROLE_STORAGE_KEY = "app_user_role";

export function getUserRole() {
  if (typeof window === "undefined") {
    return "manager";
  }
  return window.localStorage.getItem(ROLE_STORAGE_KEY) || "manager";
}

export function setUserRole(role) {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(ROLE_STORAGE_KEY, role);
}

export function getApiToken() {
  return typeof window === "undefined" ? "" : window.sessionStorage.getItem("credit_risk_api_token") || "";
}

export function setApiToken(token) {
  window.sessionStorage.setItem("credit_risk_api_token", token.trim());
}

async function request(path, options = {}) {
  const isFormData = options.body instanceof FormData;
  const token = getApiToken();
  const controller = new AbortController();
  const timeoutHandle = globalThis.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers: {
        ...(isFormData ? {} : { "Content-Type": "application/json" }),
        "X-User-Role": getUserRole(),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(options.headers || {}),
      },
      signal: controller.signal,
    });
    const payload = await response.json();
    if (!response.ok) {
      const detail = Array.isArray(payload.detail)
        ? payload.detail.map((item) => `${(item.loc || []).slice(1).join(".")}: ${item.msg}`).join("; ")
        : payload.detail || "Request failed.";
      throw new Error(detail);
    }
    return payload;
  } catch (error) {
    if (error?.name === "AbortError") throw new Error("Request timed out. Please try again.");
    throw error;
  } finally {
    globalThis.clearTimeout(timeoutHandle);
  }
}

export function fetchInsights() {
  return request("/insights");
}

export function fetchAlerts(limit = 80) {
  const params = new URLSearchParams();
  params.set("limit", String(limit));
  return request(`/alerts?${params.toString()}`);
}

export function fetchModelMonitoring() {
  return request("/model-monitoring");
}

export function fetchModelVersions() {
  return request("/model-versions");
}

export function promoteModelVersion(payload) {
  return request("/model-versions/promote", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function fetchPortfolio({ risk, status, search, limit = 300, offset = 0, summaryMode = "full" } = {}) {
  const params = new URLSearchParams();
  if (risk) {
    params.set("risk", risk);
  }
  if (status) {
    params.set("status", status);
  }
  if (search) {
    params.set("search", search);
  }
  if (limit) {
    params.set("limit", String(limit));
  }
  if (offset !== undefined && offset !== null) {
    params.set("offset", String(offset));
  }
  if (summaryMode) {
    params.set("summary_mode", String(summaryMode));
  }

  const query = params.toString();
  return request(`/portfolio${query ? `?${query}` : ""}`);
}

export function fetchPortfolioAccount(accountId) {
  return request(`/portfolio/${encodeURIComponent(accountId)}`);
}

export function updatePortfolioWorkflow(accountId, payload) {
  return request(`/portfolio/${encodeURIComponent(accountId)}/workflow`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function automatePortfolioWorkflow(payload) {
  return request("/portfolio/workflow/auto", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function batchScorePortfolio(file, limit = 2000) {
  const formData = new FormData();
  formData.append("file", file);

  const params = new URLSearchParams();
  params.set("limit", String(limit));

  return request(`/portfolio/batch-score?${params.toString()}`, {
    method: "POST",
    body: formData,
  });
}

export function predictRisk(input) {
  return request("/predict", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export { API_BASE_URL };
