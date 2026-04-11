const API_BASE_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

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

async function request(path, options = {}) {
  const isFormData = options.body instanceof FormData;
  const baseHeaders = isFormData ? {} : { "Content-Type": "application/json" };
  const roleHeader = { "X-User-Role": getUserRole() };

  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      ...baseHeaders,
      ...roleHeader,
      ...(options.headers || {}),
    },
    ...options,
  });

  const payload = await response.json().catch(() => ({}));

  if (!response.ok) {
    const detail = payload.detail || "Request failed.";
    throw new Error(detail);
  }

  return payload;
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

export function fetchPortfolio({ risk, status, search, limit = 300 } = {}) {
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
