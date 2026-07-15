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

  async function download(path, fileName) {
    const headers = new Headers();
    const token = localStorage.getItem("nl2sql.auth.token");
    if (token) headers.set("X-Demo-Token", token);
    const resp = await fetch(path, { headers });
    if (!resp.ok) throw new Error(`附件下载失败: HTTP ${resp.status}`);
    const url = URL.createObjectURL(await resp.blob());
    const link = document.createElement("a");
    link.href = url;
    link.download = fileName || "attachment";
    link.click();
    URL.revokeObjectURL(url);
  }

  window.NL2SQLApi = {
    authOptions: () => request("/api/auth/options"),
    login: (payload) => json("POST", "/api/auth/login", payload),
    session: () => request("/api/auth/session"),
    changePassword: (payload) => json("POST", "/api/auth/password", payload),
    businessDomains: () => request("/api/business-domains"),
    sources: () => request("/api/sources"),
    teachingDashboard: (params) => request(`/api/teaching/dashboard${qs(params)}`),
    teachingClass: (id) => request(`/api/teaching/classes/${encodeURIComponent(id)}`),
    myTeachingClasses: () => request("/api/teaching/classes"),
    courseAnalyticsContexts: () => request("/api/teaching/analytics/contexts"),
    courseAnalyticsSummary: (id) => request(`/api/teaching/analytics/summary?teaching_class_id=${encodeURIComponent(id)}`),
    askCourseAnalytics: (payload) => json("POST", "/api/teaching/analytics/ask", payload),
    courseAnalyticsHistory: (id) => request(`/api/teaching/analytics/history?teaching_class_id=${encodeURIComponent(id)}`),
    feedbackCourseAnalytics: (id, feedback) => json("PATCH", `/api/teaching/analytics/history/${encodeURIComponent(id)}/feedback`, { feedback }),
    teachingClassAssignments: (id) => request(`/api/teaching/classes/${encodeURIComponent(id)}/assignments`),
    teachingClassSubmissions: (id) => request(`/api/teaching/classes/${encodeURIComponent(id)}/submissions`),
    createTeachingAssignment: (id, payload) => json("POST", `/api/teaching/classes/${encodeURIComponent(id)}/assignments`, payload),
    myTeachingAssignments: () => request("/api/teaching/assignments/my"),
    teachingAssignment: (id) => request(`/api/teaching/assignments/${encodeURIComponent(id)}`),
    updateTeachingAssignment: (id, payload) => json("PUT", `/api/teaching/assignments/${encodeURIComponent(id)}`, payload),
    submitTeachingAssignment: (id, payload) => json("POST", `/api/teaching/assignments/${encodeURIComponent(id)}/submit`, payload),
    teachingAssignmentRoster: (id) => request(`/api/teaching/assignments/${encodeURIComponent(id)}/roster`),
    downloadTeachingSubmissionFile: (submissionId, versionNo, fileName) => download(`/api/teaching/submissions/${encodeURIComponent(submissionId)}/versions/${encodeURIComponent(versionNo)}/file`, fileName),
    publishTeachingAssignment: (id) => json("POST", `/api/teaching/assignments/${encodeURIComponent(id)}/publish`, {}),
    publishTeachingGrades: (id) => json("POST", `/api/teaching/assignments/${encodeURIComponent(id)}/publish-grades`, {}),
    returnTeachingSubmission: (id, payload) => json("POST", `/api/teaching/submissions/${encodeURIComponent(id)}/return`, payload),
    gradeTeachingSubmission: (id, payload) => json("POST", `/api/teaching/submissions/${encodeURIComponent(id)}/grade`, payload),
    supportCases: (status) => request(`/api/teaching/support/cases${status && status !== "all" ? `?status=${encodeURIComponent(status)}` : ""}`),
    supportCase: (id) => request(`/api/teaching/support/cases/${encodeURIComponent(id)}`),
    refreshSupportCases: () => json("POST", "/api/teaching/support/cases/refresh", {}),
    transitionSupportCase: (id, payload) => json("POST", `/api/teaching/support/cases/${encodeURIComponent(id)}/transition`, payload),
    supportRequests: () => request("/api/teaching/support/requests"),
    createSupportRequest: (payload) => json("POST", "/api/teaching/support/requests", payload),
    updateSupportRequest: (id, payload) => json("PATCH", `/api/teaching/support/requests/${encodeURIComponent(id)}`, payload),
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
