(function () {
  async function request(path, options) {
    const opts = options || {};
    const timeoutMs = Number(opts.timeoutMs || 0);
    const fetchOptions = { ...opts };
    delete fetchOptions.timeoutMs;
    const headers = new Headers(opts.headers || {});
    const token = localStorage.getItem("nl2sql.auth.token");
    if (token) headers.set("X-Demo-Token", token);
    const controller = timeoutMs > 0 ? new AbortController() : null;
    const timer = controller ? setTimeout(() => controller.abort(), timeoutMs) : null;
    let resp;
    try {
      resp = await fetch(path, { ...fetchOptions, headers, signal: controller ? controller.signal : fetchOptions.signal });
    } catch (error) {
      if (error && error.name === "AbortError") {
        const timeoutError = new Error("智能问数请求超时，请稍后重试。");
        timeoutError.status = 408;
        throw timeoutError;
      }
      throw error;
    } finally {
      if (timer) clearTimeout(timer);
    }
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

  function json(method, path, body, timeoutMs) {
    return request(path, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
      timeoutMs,
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
    switchRole: (roleBindingId) => json("POST", "/api/auth/switch-role", { role_binding_id: roleBindingId }),
    register: (payload) => json("POST", "/api/auth/register", payload),
    session: () => request("/api/auth/session"),
    myIdentityApplication: () => request("/api/auth/application"),
    identityApplications: (status) => request(`/api/auth/applications${qs({ status })}`),
    reviewIdentityApplication: (id, payload) => json("POST", `/api/auth/applications/${encodeURIComponent(id)}/review`, payload),
    batchReviewIdentityApplications: (payload) => json("POST", "/api/auth/applications/batch-review", payload),
    organizationUnits: () => request("/api/organization/units"),
    organizationStaff: (params) => request(`/api/organization/staff${qs(params)}`),
    organizationClassGroups: (collegeId) => request(`/api/organization/class-groups${qs({ college_id: collegeId })}`),
    organizationPositionSlots: (unitId) => request(`/api/organization/position-slots${qs({ organization_unit_id: unitId })}`),
    createPositionAssignment: (payload) => json("POST", "/api/organization/position-assignments", payload),
    updatePositionAssignment: (id, payload) => json("PATCH", `/api/organization/position-assignments/${encodeURIComponent(id)}`, payload),
    positionAssignmentImpact: (id) => request(`/api/organization/position-assignments/${encodeURIComponent(id)}/impact`),
    endPositionAssignment: (id, payload) => json("POST", `/api/organization/position-assignments/${encodeURIComponent(id)}/end`, payload),
    transferPositionAssignment: (id, payload) => json("POST", `/api/organization/position-assignments/${encodeURIComponent(id)}/transfer`, payload),
    organizationReviewQueues: () => request("/api/organization/review-queues"),
    securitySuspendAccount: (personIdentityId, payload) => json("POST", `/api/lifecycle/people/${encodeURIComponent(personIdentityId)}/security-suspend`, payload),
    securityRestoreAccount: (personIdentityId, payload) => json("POST", `/api/lifecycle/people/${encodeURIComponent(personIdentityId)}/security-restore`, payload),
    lifecycleStudents: (status) => request(`/api/lifecycle/students${qs({ status })}`),
    studentLifecycleAction: (personIdentityId, eventType, payload) => json("POST", `/api/lifecycle/students/${encodeURIComponent(personIdentityId)}/${encodeURIComponent(eventType)}`, payload),
    batchGraduateStudents: (payload) => json("POST", "/api/lifecycle/students/batch-graduation", payload),
    me: () => request("/api/auth/me"),
    changePassword: (payload) => json("POST", "/api/auth/password", payload),
    sources: () => request("/api/sources"),
    workbench: () => request("/api/workbench"),
    notifications: () => request("/api/notifications"),
    readNotification: (id) => json("POST", `/api/notifications/${encodeURIComponent(id)}/read`, {}),
    courseSpace: (id) => request(`/api/teaching/classes/${encodeURIComponent(id)}/space`),
    publishAnnouncement: (id, payload) => json("POST", `/api/teaching/classes/${encodeURIComponent(id)}/announcements`, payload),
    publishAnnouncementDraft: (id) => json("POST", `/api/teaching/announcements/${encodeURIComponent(id)}/publish`, {}),
    deleteAnnouncement: (id) => json("DELETE", `/api/teaching/announcements/${encodeURIComponent(id)}`, {}),
    addCourseResource: (id, payload) => json("POST", `/api/teaching/classes/${encodeURIComponent(id)}/resources`, payload),
    downloadCourseResource: (id, fileName) => download(`/api/teaching/resources/${encodeURIComponent(id)}/file`, fileName),
    courseSessions: (id) => request(`/api/teaching/classes/${encodeURIComponent(id)}/sessions`),
    createCourseSession: (id, payload) => json("POST", `/api/teaching/classes/${encodeURIComponent(id)}/sessions`, payload),
    sessionAttendance: (id) => request(`/api/teaching/sessions/${encodeURIComponent(id)}/attendance`),
    saveSessionAttendance: (id, payload) => json("PUT", `/api/teaching/sessions/${encodeURIComponent(id)}/attendance`, payload),
    courseQuestions: (id) => request(`/api/teaching/classes/${encodeURIComponent(id)}/questions`),
    createCourseQuestion: (id, payload) => json("POST", `/api/teaching/classes/${encodeURIComponent(id)}/questions`, payload),
    replyCourseQuestion: (id, payload) => json("POST", `/api/teaching/questions/${encodeURIComponent(id)}/replies`, payload),
    moderateCourseQuestion: (id, payload) => json("PATCH", `/api/teaching/questions/${encodeURIComponent(id)}`, payload),
    teachingTasks: (params) => request(`/api/teaching/operations/tasks${qs(params)}`),
    teachingOperationFilterOptions: () => request("/api/teaching/operations/filter-options"),
    teachingIssues: () => request("/api/teaching/operations/issues"),
    refreshTeachingIssues: () => json("POST", "/api/teaching/operations/issues/refresh", {}),
    updateTeachingIssue: (id, payload) => json("PATCH", `/api/teaching/operations/issues/${encodeURIComponent(id)}`, payload),
    gradeSubmissions: (params) => request(`/api/teaching/grade-submissions${qs(params)}`),
    submitCourseGrades: (id) => json("POST", `/api/teaching/classes/${encodeURIComponent(id)}/grade-submissions`, {}),
    reviewGradeSubmission: (id, payload) => json("POST", `/api/teaching/grade-submissions/${encodeURIComponent(id)}/review`, payload),
    teachingOperationsSummary: () => request("/api/teaching/operations/summary"),
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
    queryAssistant: (payload) => json("POST", "/api/assistant/query", payload, 50000),
    createAssistantAction: (payload) => json("POST", "/api/assistant/action-drafts", payload),
    assistantAction: (id) => request(`/api/assistant/action-drafts/${encodeURIComponent(id)}`),
    confirmAssistantAction: (id) => json("POST", `/api/assistant/action-drafts/${encodeURIComponent(id)}/confirm`, {}),
    assistantQuality: (days = 30) => request(`/api/assistant/quality-operations?days=${encodeURIComponent(days)}`),
    judge: (judgeId) => json("POST", "/api/judge", { judge_id: judgeId }),
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
    registerPostgresqlSource: (payload) => json("POST", "/api/data-access/sources/postgresql", payload),
    importCsvSource: (payload) => json("POST", "/api/data-access/sources/csv", payload),
    scanAccessSource: (source) => json("POST", `/api/data-access/sources/${encodeURIComponent(source)}/scan`, {}),
    tableRows: (source, table, params) => request(`/api/data-access/sources/${encodeURIComponent(source)}/tables/${encodeURIComponent(table)}/rows${qs(params)}`),
    createTableRow: (source, table, values) => json("POST", `/api/data-access/sources/${encodeURIComponent(source)}/tables/${encodeURIComponent(table)}/rows`, { values }),
    updateTableRow: (source, table, pk, values) => json("PATCH", `/api/data-access/sources/${encodeURIComponent(source)}/tables/${encodeURIComponent(table)}/rows/${encodeURIComponent(pk)}`, { values }),
    deleteTableRow: (source, table, pk) => request(`/api/data-access/sources/${encodeURIComponent(source)}/tables/${encodeURIComponent(table)}/rows/${encodeURIComponent(pk)}`, { method: "DELETE" }),
    dataAudit: () => request("/api/data-access/audit"),
  };
})();
