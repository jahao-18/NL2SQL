(function () {
  async function request(path, options) {
    const opts = options || {};
    const headers = new Headers(opts.headers || {});
    const token = localStorage.getItem("nl2sql.auth.token");
    if (token) headers.set("X-Demo-Token", token);
    const resp = await fetch(path, { ...opts, headers });
    let data = null;
    try {
      data = await resp.json();
    } catch {}
    if (!resp.ok) {
      const err = new Error((data && data.detail) || `HTTP ${resp.status}`);
      err.status = resp.status;
      err.data = data;
      throw err;
    }
    return data;
  }

  function qs(params) {
    const out = new URLSearchParams();
    Object.entries(params || {}).forEach(([key, value]) => {
      if (value == null || value === "" || value === "all") return;
      out.set(key, String(value));
    });
    const text = out.toString();
    return text ? `?${text}` : "";
  }

  function json(method, path, body) {
    return request(path, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
  }

  window.NL2SQLApi = {
    authOptions: () => request("/api/auth/options"),
    login: (payload) => json("POST", "/api/auth/login", payload),
    session: () => request("/api/auth/session"),
    changePassword: (payload) => json("POST", "/api/auth/password", payload),
    businessDomains: () => request("/api/business-domains"),
    sources: () => request("/api/sources"),
    teachingDashboard: (params) => request(`/api/teaching/dashboard${qs(params)}`),
    ask: (payload) => json("POST", "/api/ask", payload),
    judge: (judgeId) => json("POST", "/api/judge", { judge_id: judgeId }),
    debugRetrieval: (payload) => json("POST", "/api/debug/retrieval", payload),
    schema: (source) => request(source ? `/api/schema?source=${encodeURIComponent(source)}` : "/api/schema"),
    profile: (source) => request(`/api/profile?source=${encodeURIComponent(source)}`),
    saveProfile: (source, profile) => json("PUT", `/api/profile?source=${encodeURIComponent(source)}`, { profile }),
    publishProfile: (source, payload) => json("POST", `/api/profile/publish?source=${encodeURIComponent(source)}`, payload),
    rollbackProfile: (source, versionId) => json("POST", `/api/profile/rollback?source=${encodeURIComponent(source)}`, { version_id: versionId }),
    profileVersions: (source) => request(`/api/profile/versions?source=${encodeURIComponent(source)}`),
    updateProfileVersion: (source, versionId, payload) => json("PUT", `/api/profile/versions/${encodeURIComponent(versionId)}?source=${encodeURIComponent(source)}`, payload),
    deleteProfileVersion: (source, versionId) => request(`/api/profile/versions/${encodeURIComponent(versionId)}?source=${encodeURIComponent(source)}`, { method: "DELETE" }),
    feedback: (source) => request(`/api/feedback${source ? `?source=${encodeURIComponent(source)}` : ""}`),
    saveFeedback: (payload) => json("POST", "/api/feedback", payload),
    deleteFeedback: (id) => request(`/api/feedback/${encodeURIComponent(id)}`, { method: "DELETE" }),
    reviewItems: (params) => request(`/api/governance/review-items${qs(params)}`),
    updateReviewItem: (id, payload) => json("PATCH", `/api/governance/review-items/${encodeURIComponent(id)}`, payload),
    acceptReviewItem: (id, payload) => json("POST", `/api/governance/review-items/${encodeURIComponent(id)}/accept`, payload),
    rejectReviewItem: (id, payload) => json("POST", `/api/governance/review-items/${encodeURIComponent(id)}/reject`, payload),
    queueLowConfidence: (payload) => json("POST", "/api/governance/review-items/low-confidence", payload),
    governanceSettings: () => request("/api/governance/settings"),
    saveGovernanceSettings: (payload) => json("PUT", "/api/governance/settings", payload),
    quality: (source) => request(`/api/quality?source=${encodeURIComponent(source)}`),
    examples: (source) => request(`/api/examples?source=${encodeURIComponent(source)}`),
    saveExample: (source, item) => json("POST", `/api/examples?source=${encodeURIComponent(source)}`, item),
    deleteExample: (source, id) => request(`/api/examples/${encodeURIComponent(id)}?source=${encodeURIComponent(source)}`, { method: "DELETE" }),
    accessSources: () => request("/api/data-access/sources"),
    testAccessConnection: (payload) => json("POST", "/api/data-access/test", payload),
    registerSqliteSource: (payload) => json("POST", "/api/data-access/sources/sqlite", payload),
    importCsvSource: (payload) => json("POST", "/api/data-access/sources/csv", payload),
    scanAccessSource: (source) => json("POST", `/api/data-access/sources/${encodeURIComponent(source)}/scan`, {}),
    tableRows: (source, table, params) => request(`/api/data-access/sources/${encodeURIComponent(source)}/tables/${encodeURIComponent(table)}/rows${qs(params)}`),
    createTableRow: (source, table, values) => json("POST", `/api/data-access/sources/${encodeURIComponent(source)}/tables/${encodeURIComponent(table)}/rows`, { values }),
    updateTableRow: (source, table, pk, values) => json("PATCH", `/api/data-access/sources/${encodeURIComponent(source)}/tables/${encodeURIComponent(table)}/rows/${encodeURIComponent(pk)}`, { values }),
    deleteTableRow: (source, table, pk) => request(`/api/data-access/sources/${encodeURIComponent(source)}/tables/${encodeURIComponent(table)}/rows/${encodeURIComponent(pk)}`, { method: "DELETE" }),
    dataAudit: () => request("/api/data-access/audit"),
  };
})();
