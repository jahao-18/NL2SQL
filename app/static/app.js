/* ============================================================
   CANVAS PARTICLE NETWORK BACKGROUND
   ============================================================ */
(function () {
  const canvas = document.getElementById("bg-canvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  let w, h;
  const particles = [];
  const PARTICLE_COUNT = 100;
  const CONNECT_DIST = 160;

  function resize() {
    w = canvas.width = window.innerWidth;
    h = canvas.height = window.innerHeight;
  }
  resize();
  window.addEventListener("resize", resize);

  class Particle {
    constructor() {
      this.reset();
      this.y = Math.random() * h;
    }
    reset() {
      this.x = Math.random() * w;
      this.y = Math.random() * h;
      this.vx = (Math.random() - 0.5) * 0.4;
      this.vy = (Math.random() - 0.5) * 0.4;
      this.size = Math.random() * 1.5 + 0.5;
      this.alpha = Math.random() * 0.5 + 0.15;
    }
    update() {
      this.x += this.vx;
      this.y += this.vy;
      if (this.x < -50 || this.x > w + 50 || this.y < -50 || this.y > h + 50) this.reset();
    }
    draw() {
      ctx.beginPath();
      ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(139,146,255,${this.alpha})`;
      ctx.fill();
    }
  }

  for (let i = 0; i < PARTICLE_COUNT; i++) particles.push(new Particle());

  let mouseX = -1000, mouseY = -1000;
  document.addEventListener("mousemove", (e) => { mouseX = e.clientX; mouseY = e.clientY; });

  function animate() {
    ctx.clearRect(0, 0, w, h);
    for (const p of particles) { p.update(); p.draw(); }
    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const dx = particles[i].x - particles[j].x;
        const dy = particles[i].y - particles[j].y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < CONNECT_DIST) {
          const alpha = (1 - dist / CONNECT_DIST) * 0.12;
          ctx.beginPath();
          ctx.moveTo(particles[i].x, particles[i].y);
          ctx.lineTo(particles[j].x, particles[j].y);
          ctx.strokeStyle = `rgba(139,146,255,${alpha})`;
          ctx.lineWidth = 0.5;
          ctx.stroke();
        }
      }
      const dmx = particles[i].x - mouseX;
      const dmy = particles[i].y - mouseY;
      const mdist = Math.sqrt(dmx * dmx + dmy * dmy);
      if (mdist < 200) {
        ctx.beginPath();
        ctx.moveTo(particles[i].x, particles[i].y);
        ctx.lineTo(mouseX, mouseY);
        const malpha = (1 - mdist / 200) * 0.2;
        ctx.strokeStyle = `rgba(167,139,250,${malpha})`;
        ctx.lineWidth = 0.8;
        ctx.stroke();
      }
    }
    requestAnimationFrame(animate);
  }
  animate();
})();

/* ============================================================
   NL2SQL QUERY ENGINE (real backend)
   ============================================================ */
(function () {
  const $ = (id) => document.getElementById(id);
  const api = window.NL2SQLApi;
  const openGovernanceModal = window.NL2SQLModal.open;

  const loginScreen = $("login-screen");
  const workspaceShell = $("workspace-shell");
  const loginForm = $("login-form");
  const loginUsername = $("login-username");
  const loginPassword = $("login-password");
  const loginError = $("login-error");
  const loginDomainList = $("login-domain-list");
  const logoutBtn = $("logout-btn");
  const currentUserName = $("current-user-name");
  const currentUserRole = $("current-user-role");

  const input = $("query-input");
  const submit = $("query-submit");
  const clearBtn = $("clear-btn");
  const historyBadge = $("history-badge");
  const sourceTags = $("source-tags");

  const routedSource = $("routed-source");
  const routedText = $("routed-text");

  const progressBox = $("progress-box");
  const processLog = $("process-log");

  const clarifyBox = $("clarify-box");
  const clarifyMsg = $("clarify-msg");
  const errorBox = $("error-box");
  const errorMsg = $("error-msg");

  const sqlBlock = $("sql-block");
  const sqlCode = $("sql-code");
  const sqlMeta = $("sql-meta");
  const sqlCopy = $("sql-copy");
  const sqlToggle = $("sql-toggle");

  const resultWrap = $("result-table-wrap");
  const resultTitle = $("result-table-title");
  const copyTableBtn = $("copy-table-btn");
  const downloadCsvBtn = $("download-csv-btn");
  const saveQueryBtn = $("save-query-btn");
  const confirmGoodBtn = $("confirm-good-btn");
  const reportBadBtn = $("report-bad-btn");
  const chartToggleBtn = $("chart-toggle-btn");
  const chartPanel = $("chart-panel");
  const chartCanvas = $("result-chart");
  const chartEmpty = $("chart-empty");
  const resultSummary = $("result-summary");
  const thead = $("result-thead");
  const tbody = $("result-tbody");
  const emptyHint = $("empty-hint");

  const suggestionList = $("suggestion-list");
  const suggestionRoleLabel = $("suggestion-role-label");
  const historyList = $("history-list");
  const historyEmpty = $("history-empty");
  const historyClearBtn = $("history-clear-btn");

  const schemaToggle = $("schema-toggle");
  const schemaToggleLabel = $("schema-toggle-label");
  const schemaBody = $("schema-body");
  const schemaText = $("schema-text");

  const glossaryToggle = $("glossary-toggle");
  const glossaryBody = $("glossary-body");
  const glossaryList = $("glossary-list");
  const glossaryInput = $("glossary-input");
  const glossaryAddBtn = $("glossary-add-btn");
  const glossaryEmpty = $("glossary-empty");
  const glossarySourceName = $("glossary-source-name");

  const pageTitle = $("page-title");
  const breadcrumb = $("breadcrumb");
  const navTargets = Array.from(document.querySelectorAll("[data-view-target]"));
  const workViews = Array.from(document.querySelectorAll(".work-view"));
  const kbTableBody = $("kb-table-body");
  const kbSearch = $("kb-search");
  const kbRefreshBtn = $("kb-refresh-btn");
  const kbStatGrid = $("kb-stat-grid");
  const kbCurrentTitle = $("kb-current-title");
  const kbCurrentDesc = $("kb-current-desc");
  const healthList = $("health-list");
  const activityList = $("activity-list");
  const savedExampleList = $("saved-example-list");
  const feedbackList = $("feedback-list");
  const schemaTree = $("schema-tree");
  const schemaTableSearch = $("schema-table-search");
  const schemaFieldSearch = $("schema-field-search");
  const schemaFieldCount = $("schema-field-count");
  const schemaExpandFields = $("schema-expand-fields");
  const schemaStatTables = $("schema-stat-tables");
  const schemaStatFields = $("schema-stat-fields");
  const schemaStatProfiled = $("schema-stat-profiled");
  const schemaEditorTitle = $("schema-editor-title");
  const schemaTableSummary = $("schema-table-summary");
  const fieldTableBody = $("field-table-body");
  const llmDraftBtn = $("llm-draft-btn");
  const schemaConfigTabs = Array.from(document.querySelectorAll("[data-schema-config-tab]"));
  const schemaConfigPanels = Array.from(document.querySelectorAll("[data-schema-config-panel]"));
  const profileVersionList = $("profile-version-list");
  const metricList = $("metric-list");
  const termList = $("term-list");
  const relationInput = $("relation-input");
  const relationAddBtn = $("relation-add-btn");
  const relationList = $("relation-list");
  const debugQuestion = $("debug-question");
  const debugRunBtn = $("debug-run-btn");
  const debugSteps = $("debug-steps");
  const dashboardRefreshBtn = $("dashboard-refresh-btn");
  const dashboardCardGrid = $("dashboard-card-grid");
  const dashboardStudentsBars = $("dashboard-students-bars");
  const dashboardScoreBars = $("dashboard-score-bars");
  const dashboardQualityBody = $("dashboard-quality-body");
  const dashboardLowScoreBody = $("dashboard-low-score-body");
  const dashboardFailRateBody = $("dashboard-fail-rate-body");
  const dashboardWorkloadBody = $("dashboard-workload-body");
  const dashboardAttendanceRiskBody = $("dashboard-attendance-risk-body");
  const dashboardWarningBody = $("dashboard-warning-body");
  const dashboardTermFilter = $("dashboard-term-filter");
  const dashboardCollegeFilter = $("dashboard-college-filter");
  const dashboardMajorFilter = $("dashboard-major-filter");
  const dashboardCourseTypeFilter = $("dashboard-course-type-filter");
  const dashboardFilterReset = $("dashboard-filter-reset");
  const assignmentRefreshBtn = $("assignment-refresh-btn");
  const assignmentStudentPanel = $("assignment-student-panel");
  const assignmentTeacherPanel = $("assignment-teacher-panel");
  const assignmentStudentList = $("assignment-student-list");
  const assignmentTeacherList = $("assignment-teacher-list");
  const assignmentCreateForm = $("assignment-create-form");
  const assignmentCreateTitle = $("assignment-create-title");
  const assignmentCreateDue = $("assignment-create-due");
  const assignmentCreateScore = $("assignment-create-score");
  const assignmentCreateInstructions = $("assignment-create-instructions");
  const assignmentCreateAllowLate = $("assignment-create-allow-late");
  const assignmentScopeTitle = $("assignment-scope-title");
  const assignmentScopeDesc = $("assignment-scope-desc");
  const assignmentMetricPending = $("assignment-metric-pending");
  const assignmentMetricDone = $("assignment-metric-done");
  const assignmentMetricTotal = $("assignment-metric-total");
  const assignmentCoursePicker = $("assignment-course-picker");
  const assignmentCoursePickerWrap = $("assignment-course-picker-wrap");
  const assignmentRoleContext = $("assignment-role-context");
  const assignmentPageHeading = $("assignment-page-heading");
  const assignmentPageLead = $("assignment-page-lead");
  const assignmentStudentFilters = $("assignment-student-filters");
  const assignmentTeacherTitle = $("assignment-teacher-title");
  const assignmentTeacherSubtitle = $("assignment-teacher-subtitle");
  const assignmentCreateToggle = $("assignment-create-toggle");
  const assignmentCreateClose = $("assignment-create-close");
  const assignmentDetailPane = $("assignment-detail-pane");
  const assignmentListCount = $("assignment-list-count");
  const analyticsCoursePicker = $("analytics-course-picker");
  const analyticsRefreshBtn = $("analytics-refresh-btn");
  const analyticsScopeCopy = $("analytics-scope-copy");
  const analyticsMeta = $("analytics-meta");
  const analyticsMetrics = $("analytics-metrics");
  const analyticsDetailTitle = $("analytics-detail-title");
  const analyticsDetailHead = $("analytics-detail-head");
  const analyticsDetailBody = $("analytics-detail-body");
  const analyticsQuestionTemplates = $("analytics-question-templates");
  const analyticsAskForm = $("analytics-ask-form");
  const analyticsQuestionInput = $("analytics-question-input");
  const analyticsAnswer = $("analytics-answer");
  const analyticsHistoryList = $("analytics-history-list");
  const supportRefreshBtn = $("support-refresh-btn");
  const supportRoleContext = $("support-role-context");
  const supportPageHeading = $("support-page-heading");
  const supportPageLead = $("support-page-lead");
  const supportMetricOpen = $("support-metric-open");
  const supportMetricTracking = $("support-metric-tracking");
  const supportMetricReview = $("support-metric-review");
  const supportMetricRequests = $("support-metric-requests");
  const supportCounselorPanel = $("support-counselor-panel");
  const supportStudentPanel = $("support-student-panel");
  const supportStatusFilter = $("support-status-filter");
  const supportCaseCount = $("support-case-count");
  const supportCaseList = $("support-case-list");
  const supportCaseDetail = $("support-case-detail");
  const supportCounselorRequests = $("support-counselor-requests");
  const supportStudentCases = $("support-student-cases");
  const supportStudentRequests = $("support-student-requests");
  const supportRequestForm = $("support-request-form");
  const supportRequestType = $("support-request-type");
  const supportRequestTime = $("support-request-time");
  const supportRequestMessage = $("support-request-message");
  const domainRefreshBtn = $("domain-refresh-btn");
  const domainCurrent = $("domain-current");
  const domainGrid = $("domain-grid");
  const domainRoleBody = $("domain-role-body");
  const roleRefreshBtn = $("role-refresh-btn");
  const roleCardGrid = $("role-card-grid");
  const roleUserBody = $("role-user-body");
  const passwordForm = $("password-form");
  const passwordAccount = $("password-account");
  const oldPassword = $("old-password");
  const newPassword = $("new-password");
  const confirmPassword = $("confirm-password");
  const passwordMessage = $("password-message");
  const feedbackModal = $("feedback-modal");
  const feedbackCategory = $("feedback-category");
  const feedbackReason = $("feedback-reason");
  const feedbackModalClose = $("feedback-modal-close");
  const feedbackModalCancel = $("feedback-modal-cancel");
  const feedbackModalSubmit = $("feedback-modal-submit");

  const HISTORY_KEY = "nl2sql.history.v1";
  const QUERY_LOG_KEY = "nl2sql.queryLog.v1";
  const SAVED_QUERY_KEY = "nl2sql.savedQueries.v1";
  const GLOSSARY_KEY = "nl2sql.glossary.v1";  // 后接 .<source>
  const METRIC_KEY = "nl2sql.metrics.v1";  // 后接 .<source>
  const FIELD_META_KEY = "nl2sql.fieldMeta.v1";  // 后接 .<source>
  const RELATION_KEY = "nl2sql.relations.v1";  // 后接 .<source>
  const FEEDBACK_KEY = "nl2sql.feedback.v1";
  const MAX_HISTORY_TURNS = 5;
  const MAX_GLOSSARY = 50;
  const MAX_QUERY_LOG = 20;
  const AUTH_TOKEN_KEY = "nl2sql.auth.token";
  const AUTH_USER_KEY = "nl2sql.auth.user";

  // 会话首轮路由选定的数据源;多轮追问复用它,避免串库。新会话/手动切换时重置。
  let conversationSource = null;
  // 下拉/标签显式选择的库(为空表示「自动识别」)
  let selectedSource = "";
  let currentResult = null;
  let availableSources = [];
  let schemaCache = {};
  let profileCache = {};
  let feedbackCache = [];
  let qualityCache = {};
  let standardExamplesCache = {};
  let profileVersionsCache = {};
  let governanceView = null;
  let schemaLoading = new Set();
  let selectedKb = "auto";
  let lastTrace = null;
  let activeSchemaTable = "";
  let schemaTableQuery = "";
  let schemaFieldQuery = "";
  const expandedSchemaFields = new Set();
  let dashboardCache = null;
  let dashboardCacheKey = "";
  let currentUser = null;
  let domainSettingsCache = null;
  let assignmentClasses = [];
  let assignmentStudentItems = [];
  let assignmentStudentFilter = "all";
  let selectedTeachingClassId = null;
  let selectedAssignmentId = null;
  let analyticsContexts = [];
  let selectedAnalyticsClassId = null;
  let supportCaseItems = [];
  let selectedSupportCaseId = null;

  /* ---------------- helpers ---------------- */

  function show(el) { if (el) el.hidden = false; }
  function hide(el) { if (el) el.hidden = true; }

  function hideAllStateCards() {
    hide(errorBox);
    hide(clarifyBox);
    if (typeof failProgress === "function") failProgress();
    sqlBlock.classList.remove("visible");
    resultWrap.classList.remove("visible");
  }

  function manualSource() { return selectedSource || null; }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function hasFeature(feature) {
    return !!currentUser && Array.isArray(currentUser.features) && currentUser.features.includes(feature);
  }

  function preferredHomeView() {
    if (hasFeature("student_support") && currentUser?.role === "counselor") return "support-workbench-view";
    if (hasFeature("assignments") && ["teacher", "student"].includes(currentUser?.role)) return "assignment-workflow-view";
    if (hasFeature("dashboard")) return "dashboard-view";
    return "assistant-view";
  }

  function applyUserUi() {
    if (!currentUser) return;
    if (currentUserName) currentUserName.textContent = currentUser.display_name || currentUser.username || "演示用户";
    if (currentUserRole) currentUserRole.textContent = `${currentUser.role_label || "角色"} · ${currentUser.domain_items?.length || 0} 个业务域`;
    const featureMap = {
      "dashboard-view": "dashboard",
      "assignment-workflow-view": "assignments",
      "course-analytics-view": "course_analytics",
      "support-workbench-view": "student_support",
      "assistant-view": "ask",
      "kb-list-view": "knowledge",
      "kb-overview-view": "knowledge",
      "schema-console-view": "schema",
      "data-access-view": "data_access",
      "debug-view": "schema",
      "governance-queue-view": "governance",
      "governance-settings-view": "governance",
      "domain-settings-view": "domain_settings",
      "role-management-view": "role_management",
    };
    document.querySelectorAll("[data-view-target]").forEach((btn) => {
      const feature = featureMap[btn.dataset.viewTarget];
      if (feature) btn.classList.toggle("hidden", !hasFeature(feature));
    });
  }

  function showLogin() {
    if (loginScreen) loginScreen.classList.remove("hidden");
    if (workspaceShell) workspaceShell.classList.add("app-locked");
  }

  function showWorkspace() {
    if (loginScreen) loginScreen.classList.add("hidden");
    if (workspaceShell) workspaceShell.classList.remove("app-locked");
  }

  function formatNumber(value, digits) {
    const num = Number(value || 0);
    if (digits != null) return num.toFixed(digits);
    return new Intl.NumberFormat("zh-CN").format(num);
  }

  function pctText(value) {
    return `${formatNumber(value, 2)}%`;
  }

  function renderDashboardCard(label, value, sub) {
    const div = document.createElement("div");
    div.className = "dashboard-card";
    div.innerHTML = `<span>${escapeHtml(label)}</span><b>${escapeHtml(value)}</b><small>${escapeHtml(sub || "")}</small>`;
    return div;
  }

  function renderDashboardBars(el, items, options) {
    if (!el) return;
    const rows = Array.isArray(items) ? items : [];
    el.innerHTML = "";
    if (!rows.length) {
      const empty = document.createElement("div");
      empty.className = "dashboard-empty";
      empty.textContent = (options && options.emptyText) || "暂无可展示数据";
      el.appendChild(empty);
      return;
    }
    const max = Math.max(1, ...rows.map((x) => Number(x.value || 0)));
    rows.forEach((item) => {
      const value = Number(item.value || 0);
      const row = document.createElement("div");
      row.className = "dashboard-bar-row";
      const width = value > 0 ? Math.max(6, value / max * 100) : 0;
      row.innerHTML = `
        <div class="dashboard-bar-meta">
          <span>${escapeHtml(item.label || "")}</span>
          <b>${escapeHtml(options && options.percent ? pctText(value) : formatNumber(value))}</b>
        </div>
        <div class="dashboard-bar-track" style="background:linear-gradient(90deg,#c74e3a 0%,#5a8a4c ${width}%,#eee8e1 ${width}%,#eee8e1 100%)"><i style="width:${width}%;background:linear-gradient(90deg,#c74e3a,#5a8a4c)"></i></div>
      `;
      el.appendChild(row);
    });
  }

  function renderDashboardTable(tbodyEl, rows, columns) {
    if (!tbodyEl) return;
    tbodyEl.innerHTML = "";
    (rows || []).forEach((row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = columns.map((col) => {
        const raw = typeof col.value === "function" ? col.value(row) : row[col.key];
        const value = col.percent ? pctText(raw) : (col.number ? formatNumber(raw, col.digits) : raw);
        return `<td class="${col.align === "right" ? "num" : ""}">${escapeHtml(value == null ? "" : value)}</td>`;
      }).join("");
      tbodyEl.appendChild(tr);
    });
  }

  function setSelectOptions(select, values, placeholder) {
    if (!select) return;
    const current = select.value;
    const uniq = Array.from(new Set((values || []).filter(Boolean)));
    const normalized = uniq.map((item) => (
      typeof item === "object"
        ? { value: String(item.value || ""), label: String(item.label || item.value || "") }
        : { value: String(item), label: String(item) }
    )).filter((item) => item.value);
    select.innerHTML = `<option value="">${escapeHtml(placeholder || "全部")}</option>` +
      normalized.map((item) => `<option value="${escapeHtml(item.value)}">${escapeHtml(item.label)}</option>`).join("");
    if (normalized.some((item) => item.value === current)) select.value = current;
  }

  function dashboardFilters() {
    return {
      term: dashboardTermFilter ? dashboardTermFilter.value : "",
      college: dashboardCollegeFilter ? dashboardCollegeFilter.value : "",
      major: dashboardMajorFilter ? dashboardMajorFilter.value : "",
      course_type: dashboardCourseTypeFilter ? dashboardCourseTypeFilter.value : "",
    };
  }

  function enrichDashboardQuestion(question) {
    const f = dashboardFilters();
    const parts = [];
    const courseTypeLabel = dashboardCourseTypeFilter && dashboardCourseTypeFilter.selectedOptions[0]
      ? dashboardCourseTypeFilter.selectedOptions[0].textContent
      : f.course_type;
    if (f.term === "2025-spring") parts.push("只看 2025 年春季学期");
    if (f.college) parts.push(`只看${f.college}`);
    if (f.major) parts.push(`只看${f.major}专业`);
    if (f.course_type) parts.push(`只看${courseTypeLabel}课程`);
    return parts.length ? `${question} ${parts.join("，")}。` : question;
  }

  function askDashboardQuestion(question) {
    if (!input) return;
    input.value = enrichDashboardQuestion(question);
    showView("assistant-view");
    input.focus();
  }

  function populateDashboardFilters(data) {
    if (!data) return;
    const opts = data.filter_options || {};
    setSelectOptions(dashboardTermFilter, opts.terms || [{ value: "2025-spring", label: "2025 春季学期" }], "全部学期");
    setSelectOptions(dashboardCollegeFilter, opts.colleges || [
      ...(data.students_by_college || []).map((x) => x.label),
      ...(data.college_quality || []).map((x) => x.college_name),
    ], "全部学院");
    const selectedCollege = dashboardCollegeFilter ? dashboardCollegeFilter.value : "";
    const majors = (opts.majors || (data.warning_by_major || []).map((x) => x.major_name))
      .filter((item) => !selectedCollege || typeof item !== "object" || item.college === selectedCollege);
    setSelectOptions(dashboardMajorFilter, majors, "全部专业");
    setSelectOptions(dashboardCourseTypeFilter, opts.course_types || [
      { value: "required", label: "必修" },
      { value: "elective", label: "选修" },
      { value: "general", label: "通识/实践" },
    ], "全部课程类型");
  }

  function renderDashboard(data) {
    if (!dashboardCardGrid || !data) return;
    populateDashboardFilters(data);
    const c = data.cards || {};
    dashboardCardGrid.innerHTML = "";
    [
      ["在读学生", "active_students", formatNumber(c.active_students), "默认 active 学籍"],
      ["本学期开课", "current_classes", formatNumber(c.current_classes), "2025 春季学期"],
      ["本学期选课", "current_enrollments", formatNumber(c.current_enrollments), "选课记录数"],
      ["平均成绩", "avg_score", formatNumber(c.avg_score, 2), "总评成绩"],
      ["及格率", "pass_rate", pctText(c.pass_rate), "final_score >= 60"],
      ["挂科率", "fail_rate", pctText(c.fail_rate), "final_score < 60"],
      ["作业提交率", "assignment_submit_rate", pctText(c.assignment_submit_rate), "非 missing 提交"],
      ["出勤率", "attendance_rate", pctText(c.attendance_rate), "present 考勤占比"],
      ["未解除预警", "open_warnings", formatNumber(c.open_warnings), "学业风险"],
      ["学习行为记录", "activity_records", formatNumber(c.activity_records), "平台活跃数据"],
    ].filter(([, key]) => Object.prototype.hasOwnProperty.call(c, key))
      .forEach(([label, , value, sub]) => dashboardCardGrid.appendChild(renderDashboardCard(label, value, sub)));

    const studentsByCollege = data.students_by_college || [];
    const collegeQuality = data.college_quality || [];
    const warningByMajor = data.warning_by_major || [];
    renderDashboardBars(dashboardStudentsBars, studentsByCollege, { emptyText: "当前筛选条件下暂无学院学生人数数据" });
    renderDashboardBars(dashboardScoreBars, data.score_distribution || [], { emptyText: "当前角色暂无成绩分布数据" });
    renderDashboardTable(dashboardQualityBody, collegeQuality, [
      { key: "college_name" },
      { key: "avg_score", number: true, digits: 2, align: "right" },
      { key: "fail_rate", percent: true, align: "right" },
    ]);
    renderDashboardTable(dashboardLowScoreBody, data.low_score_courses || [], [
      { key: "course_name" },
      { key: "avg_score", number: true, digits: 2, align: "right" },
      { key: "enrollment_count", number: true, align: "right" },
    ]);
    renderDashboardTable(dashboardFailRateBody, data.fail_rate_courses || [], [
      { key: "course_name" },
      { key: "fail_rate", percent: true, align: "right" },
      { key: "enrollment_count", number: true, align: "right" },
    ]);
    renderDashboardTable(dashboardWorkloadBody, data.teacher_workload || [], [
      { key: "teacher_name" },
      { key: "teaching_class_count", number: true, align: "right" },
      { key: "enrollment_count", number: true, align: "right" },
    ]);
    renderDashboardTable(dashboardAttendanceRiskBody, data.attendance_risk_courses || [], [
      { key: "course_name" },
      { key: "absent_rate", percent: true, align: "right" },
      { key: "attendance_count", number: true, align: "right" },
    ]);
    renderDashboardTable(dashboardWarningBody, warningByMajor, [
      { key: "major_name" },
      { key: "warning_count", number: true, align: "right" },
      { key: "avg_risk_score", number: true, digits: 1, align: "right" },
    ]);
  }

  async function loadDashboard(force) {
    const filters = dashboardFilters();
    const cacheKey = JSON.stringify(filters);
    if (!force && dashboardCache && dashboardCacheKey === cacheKey) {
      renderDashboard(dashboardCache);
      return dashboardCache;
    }
    if (dashboardCardGrid) {
      dashboardCardGrid.innerHTML = '<div class="dashboard-loading">正在加载教学数据总览...</div>';
    }
    try {
      dashboardCache = await api.teachingDashboard(filters);
      dashboardCacheKey = cacheKey;
      renderDashboard(dashboardCache);
    } catch (err) {
      if (dashboardCardGrid) {
        dashboardCardGrid.innerHTML = `<div class="dashboard-loading is-error">教学数据总览加载失败: ${escapeHtml(err.message || err)}</div>`;
      }
    }
    return dashboardCache;
  }

  function handleDashboardFilterChange(changed) {
    if (changed === "college" && dashboardMajorFilter) {
      dashboardMajorFilter.value = "";
    }
    loadDashboard(true);
  }

  function assignmentStatusLabel(status) {
    const map = {
      draft: "草稿",
      published: "已发布",
      closed: "已截止",
      submitted: "已提交",
      late_submitted: "迟交",
      returned: "已退回",
      resubmitted: "已重交",
      graded_unpublished: "已评分未发布",
      graded_published: "成绩已发布",
      missing: "未提交",
    };
    return map[status] || status || "未提交";
  }

  function assignmentStatusTone(status) {
    if (["graded_published", "submitted", "resubmitted"].includes(status)) return "good";
    if (["returned", "late_submitted"].includes(status)) return "warn";
    if (["missing", "not_submitted"].includes(status || "missing")) return "danger";
    return "muted";
  }

  function setAssignmentOverview(title, desc, pending, done) {
    if (assignmentScopeTitle) assignmentScopeTitle.textContent = title;
    if (assignmentScopeDesc) assignmentScopeDesc.textContent = desc;
    if (assignmentMetricPending) assignmentMetricPending.textContent = formatNumber(pending || 0);
    if (assignmentMetricDone) assignmentMetricDone.textContent = formatNumber(done || 0);
  }

  function renderAssignmentStudent(items) {
    if (!assignmentStudentList) return;
    assignmentStudentList.innerHTML = "";
    if (!items.length) {
      assignmentStudentList.innerHTML = '<div class="dashboard-empty">暂无作业待办</div>';
      return;
    }
    items.forEach((item) => {
      const card = document.createElement("div");
      card.className = "assignment-item";
      const status = item.submission_status || "missing";
      const scoreText = item.score == null ? "" : `<b>成绩 ${escapeHtml(item.score)}</b>`;
      const canSubmit = !["graded_published", "graded_unpublished"].includes(status);
      card.innerHTML = `
        <div class="assignment-item-head">
          <div>
            <strong>${escapeHtml(item.title)}</strong>
            <span>${escapeHtml(item.course_name)} · 截止 ${escapeHtml(item.due_time)}</span>
          </div>
          <em class="assignment-status is-${assignmentStatusTone(status)}">${escapeHtml(assignmentStatusLabel(status))}</em>
        </div>
        <div class="assignment-feedback">
          ${item.feedback ? `<span>${escapeHtml(item.feedback)}</span>` : "<span>暂无教师反馈</span>"}
          ${scoreText}
        </div>
        ${canSubmit ? `
          <form class="assignment-inline-form" data-submit-assignment="${escapeHtml(item.id)}">
            <input name="file_name" placeholder="附件名，例如 report.pdf" />
            <input name="content" placeholder="提交说明" />
            <button class="nav-btn" type="submit">${status === "returned" ? "重新提交" : "提交作业"}</button>
          </form>
        ` : ""}
      `;
      assignmentStudentList.appendChild(card);
    });
    assignmentStudentList.querySelectorAll("[data-submit-assignment]").forEach((form) => {
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const id = form.dataset.submitAssignment;
        const payload = {
          file_name: form.elements.file_name.value,
          content: form.elements.content.value,
        };
        await api.submitTeachingAssignment(id, payload);
        await loadAssignmentProduct(true);
      });
    });
  }

  function renderAssignmentTeacher(items) {
    if (!assignmentTeacherList) return;
    assignmentTeacherList.innerHTML = "";
    if (!items.length) {
      assignmentTeacherList.innerHTML = '<div class="dashboard-empty">暂无提交记录</div>';
      return;
    }
    const table = document.createElement("table");
    table.className = "assignment-manage-table";
    table.innerHTML = `
      <thead><tr><th>作业</th><th>学生</th><th>状态</th><th>批阅</th><th>操作</th></tr></thead>
      <tbody></tbody>
    `;
    const tbody = table.querySelector("tbody");
    items.forEach((item) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${escapeHtml(item.assignment_title)}</td>
        <td>${escapeHtml(item.student_name)}</td>
        <td><em class="assignment-status is-${assignmentStatusTone(item.status)}">${escapeHtml(assignmentStatusLabel(item.status))}</em></td>
        <td>
          <div class="assignment-row-controls">
            <input type="number" min="0" max="1000" step="1" value="${item.score == null ? "" : escapeHtml(item.score)}" placeholder="分数" data-score-for="${escapeHtml(item.id)}" />
            <input type="text" value="${escapeHtml(item.feedback || "")}" placeholder="评语或退回原因" data-feedback-for="${escapeHtml(item.id)}" />
          </div>
        </td>
        <td>
          <button type="button" data-return-submission="${escapeHtml(item.id)}">退回</button>
          <button type="button" data-grade-submission="${escapeHtml(item.id)}">评分</button>
          <button class="is-primary" type="button" data-publish-assignment="${escapeHtml(item.assignment_id)}">发布</button>
        </td>
      `;
      tbody.appendChild(tr);
    });
    assignmentTeacherList.appendChild(table);
    assignmentTeacherList.querySelectorAll("[data-return-submission]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const feedbackInput = assignmentTeacherList.querySelector(`[data-feedback-for="${CSS.escape(btn.dataset.returnSubmission)}"]`);
        const feedback = feedbackInput ? feedbackInput.value.trim() : "";
        if (!feedback) return;
        await api.returnTeachingSubmission(btn.dataset.returnSubmission, { feedback });
        await loadAssignmentProduct(true);
      });
    });
    assignmentTeacherList.querySelectorAll("[data-grade-submission]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const scoreInput = assignmentTeacherList.querySelector(`[data-score-for="${CSS.escape(btn.dataset.gradeSubmission)}"]`);
        const feedbackInput = assignmentTeacherList.querySelector(`[data-feedback-for="${CSS.escape(btn.dataset.gradeSubmission)}"]`);
        const score = scoreInput ? scoreInput.value : "";
        if (score === "") return;
        const feedback = feedbackInput ? feedbackInput.value : "";
        await api.gradeTeachingSubmission(btn.dataset.gradeSubmission, { score: Number(score), feedback });
        await loadAssignmentWorkflow(true);
      });
    });
    assignmentTeacherList.querySelectorAll("[data-publish-assignment]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        await api.publishTeachingGrades(btn.dataset.publishAssignment);
        await loadAssignmentWorkflow(true);
      });
    });
  }

  async function loadAssignmentWorkflow(force) {
    if (!currentUser || !hasFeature("assignments")) return;
    if (assignmentStudentPanel) assignmentStudentPanel.classList.toggle("hidden", currentUser.role !== "student");
    if (assignmentTeacherPanel) assignmentTeacherPanel.classList.toggle("hidden", currentUser.role !== "teacher");
    try {
      if (currentUser.role === "student") {
        const data = await api.myTeachingAssignments();
        const items = data.items || [];
        const pending = items.filter((item) => !["submitted", "resubmitted", "graded_published"].includes(item.submission_status || "missing")).length;
        const done = items.length - pending;
        setAssignmentOverview("我的课程任务", "仅统计本人选课和本人提交", pending, done);
        renderAssignmentStudent(items);
      } else if (currentUser.role === "teacher") {
        const data = await api.teachingClassSubmissions(900001);
        const items = data.items || [];
        const pending = items.filter((item) => ["submitted", "late_submitted", "resubmitted"].includes(item.status)).length;
        const done = items.filter((item) => item.status === "graded_published").length;
        setAssignmentOverview("数据库系统-1班", "任课教师仅处理本人开课班", pending, done);
        renderAssignmentTeacher(items);
      }
    } catch (err) {
      const target = currentUser.role === "student" ? assignmentStudentList : assignmentTeacherList;
      if (target) target.innerHTML = `<div class="dashboard-loading is-error">作业数据加载失败: ${escapeHtml(err.message || err)}</div>`;
    }
  }

  function assignmentDate(value) {
    if (!value) return "--";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value.replace("T", " ").slice(0, 16);
    return date.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });
  }

  function assignmentFileBase64(file) {
    if (!file) return Promise.resolve(null);
    if (file.size > 5 * 1024 * 1024) return Promise.reject(new Error("附件不能超过 5MB"));
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result).split(",", 2)[1] || "");
      reader.onerror = () => reject(new Error("附件读取失败"));
      reader.readAsDataURL(file);
    });
  }

  function assignmentFileSize(value) {
    const size = Number(value || 0);
    if (!size) return "";
    if (size < 1024 * 1024) return `${Math.max(1, Math.round(size / 1024))} KB`;
    return `${(size / 1024 / 1024).toFixed(1)} MB`;
  }

  function setAssignmentProductOverview(title, desc, pending, done, total) {
    if (assignmentScopeTitle) assignmentScopeTitle.textContent = title;
    if (assignmentScopeDesc) assignmentScopeDesc.textContent = desc;
    if (assignmentMetricPending) assignmentMetricPending.textContent = formatNumber(pending || 0);
    if (assignmentMetricDone) assignmentMetricDone.textContent = formatNumber(done || 0);
    if (assignmentMetricTotal) assignmentMetricTotal.textContent = formatNumber(total || 0);
  }

  function studentAssignmentGroup(item) {
    const status = item.submission_status || "missing";
    if (status === "graded_published") return "finished";
    if (["submitted", "resubmitted", "late_submitted", "graded_unpublished"].includes(status)) return "submitted";
    return "pending";
  }

  function renderAssignmentStudentProduct(items) {
    if (!assignmentStudentList) return;
    assignmentStudentItems = items;
    assignmentStudentList.innerHTML = "";
    const visible = assignmentStudentFilter === "all" ? items : items.filter((item) => studentAssignmentGroup(item) === assignmentStudentFilter);
    if (!visible.length) {
      assignmentStudentList.innerHTML = '<div class="assignment-empty"><b>当前分类没有任务</b><span>新的课程作业发布后会出现在这里</span></div>';
      return;
    }
    visible.forEach((item) => {
      const card = document.createElement("article");
      const status = item.submission_status || "missing";
      const group = studentAssignmentGroup(item);
      const canEdit = item.assignment_status === "published" && !["graded_published", "graded_unpublished"].includes(status);
      const hasSubmission = Boolean(item.submission_id);
      const formHidden = hasSubmission && status !== "returned";
      card.className = `assignment-item is-${group}`;
      card.innerHTML = `
        <div class="assignment-item-head">
          <div><span class="assignment-course-code">${escapeHtml(item.course_code || "COURSE")}</span><strong>${escapeHtml(item.title)}</strong><span>${escapeHtml(item.course_name)} · ${assignmentDate(item.due_time)} 截止</span></div>
          <em class="assignment-status is-${assignmentStatusTone(status)}">${escapeHtml(assignmentStatusLabel(status))}</em>
        </div>
        ${item.instructions ? `<p class="assignment-instructions">${escapeHtml(item.instructions)}</p>` : ""}
        ${hasSubmission ? `<div class="assignment-current-submission"><div><span class="assignment-current-label">当前提交 · 版本 ${item.latest_version_no || item.version_count || 1}</span><p>${escapeHtml(item.latest_content || "未填写提交说明")}</p></div>${item.latest_file_name ? `<button type="button" class="assignment-attachment-chip" data-download-submission="${item.submission_id}" data-version="${item.latest_version_no}" data-file-name="${escapeHtml(item.latest_file_name)}"><b>附件</b><span>${escapeHtml(item.latest_file_name)}</span><small>${assignmentFileSize(item.latest_file_size)}</small></button>` : '<span class="assignment-no-file">本版本无附件</span>'}</div>` : ""}
        <div class="assignment-feedback">${item.feedback ? `<span><b>教师反馈</b>${escapeHtml(item.feedback)}</span>` : "<span>尚无教师反馈</span>"}${item.score == null ? "" : `<b>成绩 ${escapeHtml(item.score)} / ${escapeHtml(item.max_score)}</b>`}</div>
        ${canEdit && hasSubmission && status !== "returned" ? `<button class="assignment-edit-submit" type="button" data-toggle-submit="${item.id}">修改提交</button>` : ""}
        ${canEdit ? `<form class="assignment-inline-form${formHidden ? " hidden" : ""}" data-submit-assignment="${item.id}"><label class="assignment-file-field"><input name="file" type="file" accept=".pdf,.doc,.docx,.zip,.png,.jpg,.jpeg,.txt" /><span>${item.latest_file_name ? "保留当前附件，或选择新附件" : "选择附件"}</span></label><textarea name="content" placeholder="填写提交说明">${escapeHtml(item.latest_content || "")}</textarea><button class="nav-btn" type="submit">${hasSubmission ? "保存新版本" : "提交作业"}</button></form>` : `<div class="assignment-submitted-note">${status === "graded_published" ? "成绩与评语已发布" : "教师已评分，当前提交不可再修改"}</div>`}
      `;
      assignmentStudentList.appendChild(card);
    });
    assignmentStudentList.querySelectorAll("[data-submit-assignment]").forEach((form) => {
      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const file = form.elements.file.files[0];
        const fileContent = await assignmentFileBase64(file);
        await api.submitTeachingAssignment(form.dataset.submitAssignment, { file_name: file ? file.name : null, file_content_base64: fileContent, retain_existing_file: true, content: form.elements.content.value });
        await loadAssignmentProduct(true);
      });
    });
    assignmentStudentList.querySelectorAll("[data-toggle-submit]").forEach((button) => button.addEventListener("click", () => {
      const form = assignmentStudentList.querySelector(`[data-submit-assignment="${button.dataset.toggleSubmit}"]`);
      form?.classList.toggle("hidden");
      button.textContent = form?.classList.contains("hidden") ? "修改提交" : "收起修改";
    }));
    assignmentStudentList.querySelectorAll(".assignment-file-field input").forEach((input) => input.addEventListener("change", () => {
      const label = input.closest(".assignment-file-field")?.querySelector("span");
      if (label) label.textContent = input.files[0] ? `已选择：${input.files[0].name} · ${assignmentFileSize(input.files[0].size)}` : "选择附件";
      input.closest(".assignment-file-field")?.classList.toggle("has-file", Boolean(input.files[0]));
    }));
    assignmentStudentList.querySelectorAll("[data-download-submission]").forEach((button) => button.addEventListener("click", () => api.downloadTeachingSubmissionFile(button.dataset.downloadSubmission, button.dataset.version, button.dataset.fileName)));
  }

  function renderAssignmentTeacherProduct(items) {
    if (!assignmentTeacherList) return;
    assignmentTeacherList.innerHTML = "";
    if (assignmentListCount) assignmentListCount.textContent = `${items.length} 项`;
    if (!items.length) {
      assignmentTeacherList.innerHTML = '<div class="assignment-empty compact"><b>还没有作业</b><span>点击“新建作业”创建第一项课程任务</span></div>';
      return;
    }
    items.forEach((item) => {
      const button = document.createElement("button");
      const missing = Math.max(0, Number(item.student_count) - Number(item.submitted_count));
      button.type = "button";
      button.className = `assignment-master-item${Number(selectedAssignmentId) === Number(item.id) ? " active" : ""}`;
      button.dataset.assignmentId = item.id;
      button.innerHTML = `<span class="assignment-master-top"><b>${escapeHtml(item.title)}</b><em class="assignment-status is-${assignmentStatusTone(item.status)}">${assignmentStatusLabel(item.status)}</em></span><span class="assignment-master-time">${assignmentDate(item.due_time)} 截止</span><span class="assignment-master-progress"><i style="width:${item.student_count ? Math.round(item.submitted_count / item.student_count * 100) : 0}%"></i></span><span class="assignment-master-meta"><span>${item.submitted_count}/${item.student_count} 已交</span><span>${item.pending_grade_count} 待批</span><span>${missing} 未交</span></span>`;
      assignmentTeacherList.appendChild(button);
    });
    assignmentTeacherList.querySelectorAll("[data-assignment-id]").forEach((button) => button.addEventListener("click", () => loadTeacherAssignmentDetail(button.dataset.assignmentId)));
  }

  async function loadTeacherAssignmentList(selectFirst) {
    const data = await api.teachingClassAssignments(selectedTeachingClassId);
    const items = data.items || [];
    const pending = items.reduce((sum, item) => sum + Number(item.pending_grade_count || 0), 0);
    const done = items.reduce((sum, item) => sum + Number(item.published_count || 0), 0);
    const course = assignmentClasses.find((item) => Number(item.id) === Number(selectedTeachingClassId));
    setAssignmentProductOverview(course ? course.course_name : "我的开课班", "任课教师仅能处理本人开课班", pending, done, items.length);
    renderAssignmentTeacherProduct(items);
    if (selectFirst && items.length) await loadTeacherAssignmentDetail(items[0].id, items);
    return items;
  }

  async function loadTeacherAssignmentDetail(assignmentId, knownItems) {
    selectedAssignmentId = Number(assignmentId);
    if (!assignmentDetailPane) return;
    assignmentDetailPane.innerHTML = '<div class="dashboard-loading">正在加载学生名单...</div>';
    const [detailData, rosterData] = await Promise.all([api.teachingAssignment(assignmentId), api.teachingAssignmentRoster(assignmentId)]);
    const detail = detailData.item;
    const items = rosterData.items || [];
    const submitted = items.filter((item) => item.submission_id).length;
    const pending = items.filter((item) => ["submitted", "late_submitted", "resubmitted"].includes(item.status)).length;
    const unpublished = items.filter((item) => item.status === "graded_unpublished").length;
    assignmentDetailPane.innerHTML = `
      <div class="assignment-detail-head"><div><span>${escapeHtml(detail.course_name)}</span><h3>${escapeHtml(detail.title)}</h3><p>${escapeHtml(detail.instructions || "未填写作业说明")}</p></div><div class="assignment-detail-actions">${detail.status === "draft" ? `<button class="nav-btn secondary" type="button" data-edit-draft="${detail.id}">编辑草稿</button><button class="nav-btn" type="button" data-publish-draft="${detail.id}">发布作业</button>` : ""}${unpublished ? `<button class="nav-btn" type="button" data-publish-grades="${detail.id}">发布 ${unpublished} 份成绩</button>` : ""}</div></div>
      <div class="assignment-detail-metrics"><span><b>${submitted}/${items.length}</b>已提交</span><span><b>${pending}</b>待批阅</span><span><b>${items.length - submitted}</b>未提交</span><span><b>${unpublished}</b>待发布成绩</span></div>
      <div class="assignment-roster-wrap"><table class="assignment-manage-table"><thead><tr><th>学生</th><th>提交情况</th><th>状态</th><th>评分与反馈</th><th>操作</th></tr></thead><tbody>${items.map((item) => {
        const canReview = item.submission_id && ["submitted", "late_submitted", "resubmitted"].includes(item.status);
        return `<tr class="${canReview ? "is-awaiting-review" : ""}"><td><b>${escapeHtml(item.student_name)}</b><small>${escapeHtml(item.student_no)}</small></td><td>${item.submit_time ? `<b>${assignmentDate(item.submit_time)}</b><small>版本 ${item.version_no || 1} · 共 ${item.version_count || 1} 个版本</small>${item.content ? `<p class="assignment-roster-content">${escapeHtml(item.content)}</p>` : ""}${item.file_name ? `<button class="assignment-teacher-attachment" type="button" data-download-submission="${item.submission_id}" data-version="${item.file_version_no}" data-file-name="${escapeHtml(item.file_name)}"><b>附件</b><span>${escapeHtml(item.file_name)}</span><small>${assignmentFileSize(item.file_size)}</small></button>` : ""}` : '<span class="assignment-missing-text">尚未提交</span>'}</td><td><em class="assignment-status is-${assignmentStatusTone(item.status)}">${assignmentStatusLabel(item.status)}</em></td><td>${canReview ? `<div class="assignment-row-controls"><input type="number" min="0" max="${escapeHtml(detail.max_score)}" value="${item.score == null ? "" : escapeHtml(item.score)}" placeholder="分数" data-score-for="${item.submission_id}" /><input value="${escapeHtml(item.feedback || "")}" placeholder="评语或退回原因" data-feedback-for="${item.submission_id}" /></div>` : escapeHtml(item.feedback || (item.score == null ? "--" : `${item.score} 分`))}</td><td>${canReview ? `<button type="button" data-return-submission="${item.submission_id}">退回</button><button class="is-primary" type="button" data-grade-submission="${item.submission_id}">评分</button>` : "--"}</td></tr>`;
      }).join("")}</tbody></table></div>`;
    renderAssignmentTeacherProduct(knownItems || await loadTeacherAssignmentList(false));
    assignmentDetailPane.querySelectorAll("[data-return-submission]").forEach((button) => button.addEventListener("click", async () => {
      const feedback = assignmentDetailPane.querySelector(`[data-feedback-for="${button.dataset.returnSubmission}"]`)?.value.trim() || "";
      if (!feedback) return;
      await api.returnTeachingSubmission(button.dataset.returnSubmission, { feedback });
      await loadTeacherAssignmentDetail(selectedAssignmentId);
    }));
    assignmentDetailPane.querySelectorAll("[data-grade-submission]").forEach((button) => button.addEventListener("click", async () => {
      const score = assignmentDetailPane.querySelector(`[data-score-for="${button.dataset.gradeSubmission}"]`)?.value;
      const feedback = assignmentDetailPane.querySelector(`[data-feedback-for="${button.dataset.gradeSubmission}"]`)?.value || "";
      if (score === "" || score == null) return;
      await api.gradeTeachingSubmission(button.dataset.gradeSubmission, { score: Number(score), feedback });
      await loadTeacherAssignmentDetail(selectedAssignmentId);
    }));
    assignmentDetailPane.querySelectorAll("[data-download-submission]").forEach((button) => button.addEventListener("click", () => api.downloadTeachingSubmissionFile(button.dataset.downloadSubmission, button.dataset.version, button.dataset.fileName)));
    assignmentDetailPane.querySelector("[data-publish-grades]")?.addEventListener("click", async (event) => {
      await api.publishTeachingGrades(event.currentTarget.dataset.publishGrades);
      await loadTeacherAssignmentDetail(selectedAssignmentId);
    });
    assignmentDetailPane.querySelector("[data-publish-draft]")?.addEventListener("click", async (event) => {
      await api.publishTeachingAssignment(event.currentTarget.dataset.publishDraft);
      await loadTeacherAssignmentDetail(selectedAssignmentId);
    });
    assignmentDetailPane.querySelector("[data-edit-draft]")?.addEventListener("click", () => {
      assignmentCreateForm.dataset.editingId = detail.id;
      assignmentCreateTitle.value = detail.title;
      const localDue = new Date(detail.due_time);
      localDue.setMinutes(localDue.getMinutes() - localDue.getTimezoneOffset());
      assignmentCreateDue.value = localDue.toISOString().slice(0, 16);
      assignmentCreateScore.value = detail.max_score;
      assignmentCreateInstructions.value = detail.instructions || "";
      assignmentCreateAllowLate.checked = Boolean(detail.allow_late);
      assignmentCreateForm.classList.remove("hidden");
      assignmentCreateForm.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
  }

  async function loadAssignmentProduct(force) {
    if (!currentUser || !hasFeature("assignments")) return;
    assignmentStudentPanel?.classList.toggle("hidden", currentUser.role !== "student");
    assignmentTeacherPanel?.classList.toggle("hidden", currentUser.role !== "teacher");
    assignmentCoursePickerWrap?.classList.toggle("hidden", currentUser.role !== "teacher");
    try {
      if (currentUser.role === "student") {
        if (assignmentRoleContext) assignmentRoleContext.textContent = "学生学习空间";
        if (assignmentPageHeading) assignmentPageHeading.textContent = "我的课程作业";
        if (assignmentPageLead) assignmentPageLead.textContent = "按截止时间安排任务，提交后查看批阅进度和成绩反馈。";
        const data = await api.myTeachingAssignments();
        const items = data.items || [];
        setAssignmentProductOverview("本学期课程", "仅统计本人选课和本人提交", items.filter((item) => studentAssignmentGroup(item) === "pending").length, items.filter((item) => studentAssignmentGroup(item) === "finished").length, items.length);
        renderAssignmentStudentProduct(items);
      } else if (currentUser.role === "teacher") {
        if (assignmentRoleContext) assignmentRoleContext.textContent = "教师教学空间";
        if (assignmentPageHeading) assignmentPageHeading.textContent = "作业与批阅";
        if (assignmentPageLead) assignmentPageLead.textContent = "围绕开课班发布任务、跟踪提交并完成成绩反馈。";
        const classData = await api.myTeachingClasses();
        assignmentClasses = classData.items || [];
        if (!assignmentClasses.length) throw new Error("当前账号没有可管理的开课班");
        if (!selectedTeachingClassId || !assignmentClasses.some((item) => Number(item.id) === Number(selectedTeachingClassId))) selectedTeachingClassId = assignmentClasses[0].id;
        if (assignmentCoursePicker) {
          assignmentCoursePicker.innerHTML = assignmentClasses.map((item) => `<option value="${item.id}">${escapeHtml(item.course_name)} · ${item.year} ${item.semester === "spring" ? "春" : "秋"}</option>`).join("");
          assignmentCoursePicker.value = selectedTeachingClassId;
        }
        const course = assignmentClasses.find((item) => Number(item.id) === Number(selectedTeachingClassId));
        if (assignmentTeacherTitle) assignmentTeacherTitle.textContent = course?.course_name || "课程作业";
        if (assignmentTeacherSubtitle) assignmentTeacherSubtitle.textContent = course ? `${course.student_count} 名学生 · ${course.classroom} · ${course.course_code}` : "";
        await loadTeacherAssignmentList(true);
      }
    } catch (err) {
      const target = currentUser.role === "student" ? assignmentStudentList : assignmentDetailPane;
      if (target) target.innerHTML = `<div class="dashboard-loading is-error">作业数据加载失败: ${escapeHtml(err.message || err)}</div>`;
    }
  }

  function supportStatusLabel(status) {
    const labels = { open: "待确认", contacted: "已联系", tracking: "跟进中", improved: "已改善", closed: "已关闭", submitted: "待受理", accepted: "已受理", completed: "已完成", declined: "未受理" };
    return labels[status] || status || "--";
  }

  function supportStatusTone(status) {
    if (["improved", "completed"].includes(status)) return "good";
    if (["open", "submitted"].includes(status)) return "warn";
    if (["tracking", "accepted"].includes(status)) return "info";
    return "muted";
  }

  function supportEvidenceSummary(evidence) {
    if (!evidence) return "暂无事实依据";
    if (typeof evidence === "string") return evidence;
    return [evidence.course, evidence.fact, evidence.summary].filter(Boolean).join(" · ") || "已记录事实依据";
  }

  function supportEvidenceEvents(evidence) {
    if (!evidence || typeof evidence === "string" || !Array.isArray(evidence.events)) return "";
    return evidence.events.map((event) => {
      if (typeof event === "string") return `<li>${escapeHtml(event)}</li>`;
      const text = event.assignment ? `${event.assignment} · 截止 ${assignmentDate(event.due_time)}` : `第 ${event.session} 次课 · ${escapeHtml(event.date || "")}`;
      return `<li>${escapeHtml(text)}</li>`;
    }).join("");
  }

  function supportNextStatuses(status) {
    const transitions = { open: ["contacted", "closed"], contacted: ["tracking", "closed"], tracking: ["improved", "closed"], improved: ["closed"], closed: [] };
    return transitions[status] || [];
  }

  function renderSupportCaseList(items) {
    if (!supportCaseList) return;
    supportCaseList.innerHTML = "";
    if (supportCaseCount) supportCaseCount.textContent = `${items.length} 项`;
    if (!items.length) {
      supportCaseList.innerHTML = '<div class="support-empty compact"><b>当前没有事项</b><span>规则检查不会生成正式警告，只创建待确认事项</span></div>';
      return;
    }
    items.forEach((item) => {
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.supportCase = item.id;
      button.className = `support-case-item${Number(selectedSupportCaseId) === Number(item.id) ? " active" : ""}`;
      button.innerHTML = `
        <span class="support-case-top"><b>${escapeHtml(item.student_name)}</b><em class="support-status is-${supportStatusTone(item.status)}">${supportStatusLabel(item.status)}</em></span>
        <strong>${escapeHtml(item.title)}</strong>
        <span>${escapeHtml(item.class_name)} · ${escapeHtml(supportEvidenceSummary(item.evidence))}</span>
        <small>${item.review_at ? `复查 ${assignmentDate(item.review_at)}` : `创建 ${assignmentDate(item.created_at)}`}${item.visible_to_student ? " · 已共享" : " · 内部待办"}</small>`;
      supportCaseList.appendChild(button);
    });
    supportCaseList.querySelectorAll("[data-support-case]").forEach((button) => button.addEventListener("click", () => loadSupportCaseDetail(button.dataset.supportCase)));
  }

  async function loadSupportCaseDetail(caseId) {
    selectedSupportCaseId = Number(caseId);
    if (!supportCaseDetail) return;
    supportCaseDetail.innerHTML = '<div class="dashboard-loading">正在加载事项详情...</div>';
    const data = await api.supportCase(caseId);
    const item = data.item;
    const events = supportEvidenceEvents(item.evidence);
    const nextStatuses = supportNextStatuses(item.status);
    supportCaseDetail.innerHTML = `
      <div class="support-detail-head">
        <div><span>${escapeHtml(item.student_name)} · ${escapeHtml(item.code)}</span><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(supportEvidenceSummary(item.evidence))}</p></div>
        <em class="support-status is-${supportStatusTone(item.status)}">${supportStatusLabel(item.status)}</em>
      </div>
      <div class="support-fact-grid">
        <section><span>事实依据</span><b>${escapeHtml(item.evidence?.fact || item.evidence?.summary || supportEvidenceSummary(item.evidence))}</b>${events ? `<ul>${events}</ul>` : ""}</section>
        <section><span>建议动作</span><b>${escapeHtml(item.suggested_action || "先确认事实，再与学生制定后续计划。")}</b><small>${item.visible_to_student ? "该建议已对学生可见" : "当前仅辅导员可见"}</small></section>
      </div>
      <section class="support-timeline"><div class="support-detail-title"><b>处理记录</b><span>${(item.logs || []).length} 条</span></div>${(item.logs || []).length ? item.logs.map((log) => `<div class="support-log"><i></i><div><b>${supportStatusLabel(log.action)} · ${escapeHtml(log.actor_user)}</b><p>${escapeHtml(log.note)}</p>${log.student_feedback ? `<p><span>学生反馈：</span>${escapeHtml(log.student_feedback)}</p>` : ""}<small>${assignmentDate(log.created_at)}${log.contact_method ? ` · ${escapeHtml(log.contact_method)}` : ""}${log.follow_up_at ? ` · 复查 ${assignmentDate(log.follow_up_at)}` : ""}</small></div></div>`).join("") : '<div class="support-empty compact"><span>尚无联系记录</span></div>'}</section>
      ${nextStatuses.length ? `<form class="support-action-form" id="support-action-form"><div class="support-detail-title"><b>记录本次处理</b><span>状态变化将写入审计日志</span></div><div class="support-action-grid"><label><span>下一状态</span><select name="target_status">${nextStatuses.map((status) => `<option value="${status}">${supportStatusLabel(status)}</option>`).join("")}</select></label><label><span>联系方式</span><select name="contact_method"><option value="">非首次联系</option><option value="phone">电话</option><option value="message">即时消息</option><option value="meeting">面谈</option></select></label><label><span>复查时间</span><input name="follow_up_at" type="datetime-local" /></label><label class="wide"><span>处理记录</span><textarea name="note" placeholder="记录已核实的情况、处理动作或关闭原因"></textarea></label><label class="wide"><span>学生反馈</span><textarea name="student_feedback" placeholder="记录学生反馈；学生端不会直接看到这段内部记录"></textarea></label></div><div class="support-action-message" role="status"></div><div class="support-action-foot"><label><input name="visible_to_student" type="checkbox" />同步更新学生端支持建议</label><button class="nav-btn" type="submit">保存处理记录</button></div></form>` : `<div class="support-closed-note">事项已关闭，历史记录将继续保留。</div>`}`;
    renderSupportCaseList(supportCaseItems);
    const form = $("support-action-form");
    if (form) form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const message = form.querySelector(".support-action-message");
      try {
        await api.transitionSupportCase(item.id, {
          target_status: form.elements.target_status.value,
          note: form.elements.note.value,
          contact_method: form.elements.contact_method.value || null,
          student_feedback: form.elements.student_feedback.value || null,
          follow_up_at: form.elements.follow_up_at.value || null,
          visible_to_student: form.elements.visible_to_student.checked,
        });
        await loadSupportWorkbench(true, item.id);
      } catch (err) {
        if (message) message.textContent = err.message || "保存失败";
      }
    });
  }

  function renderCounselorSupportRequests(items) {
    if (!supportCounselorRequests) return;
    if (!items.length) {
      supportCounselorRequests.innerHTML = '<div class="support-empty compact"><span>暂无学生沟通请求</span></div>';
      return;
    }
    supportCounselorRequests.innerHTML = `<div class="support-request-table">${items.map((item) => `<div class="support-request-row"><div><b>${escapeHtml(item.student_name)} · ${item.request_type === "appointment" ? "预约沟通" : "问题咨询"}</b><p>${escapeHtml(item.message)}</p><small>${item.preferred_time ? `希望时间 ${assignmentDate(item.preferred_time)}` : "未指定时间"}</small></div><em class="support-status is-${supportStatusTone(item.status)}">${supportStatusLabel(item.status)}</em>${item.status === "submitted" ? `<div class="support-request-reply"><input placeholder="填写给学生的回复" data-request-response="${item.id}" /><button type="button" data-accept-request="${item.id}">受理</button></div>` : `<span class="support-response">${escapeHtml(item.counselor_response || "暂无回复")}</span>`}</div>`).join("")}</div>`;
    supportCounselorRequests.querySelectorAll("[data-accept-request]").forEach((button) => button.addEventListener("click", async () => {
      const response = supportCounselorRequests.querySelector(`[data-request-response="${button.dataset.acceptRequest}"]`)?.value.trim() || "";
      if (!response) return;
      await api.updateSupportRequest(button.dataset.acceptRequest, { status: "accepted", response });
      await loadSupportWorkbench(true);
    }));
  }

  function renderStudentSupportCases(items) {
    if (!supportStudentCases) return;
    if (!items.length) {
      supportStudentCases.innerHTML = '<div class="support-empty"><b>暂无需要处理的支持事项</b><span>你仍可以主动发起预约或咨询</span></div>';
      return;
    }
    supportStudentCases.innerHTML = items.map((item) => `<article class="support-student-card"><div><span>${escapeHtml(item.counselor_name || "辅导员")}</span><em class="support-status is-${supportStatusTone(item.status)}">${supportStatusLabel(item.status)}</em></div><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(supportEvidenceSummary(item.evidence))}</p><section><b>建议行动</b><span>${escapeHtml(item.suggested_action || "请按约定完成后续学习任务。")}</span></section>${item.review_at ? `<small>计划复查：${assignmentDate(item.review_at)}</small>` : ""}</article>`).join("");
  }

  function renderStudentSupportRequests(items) {
    if (!supportStudentRequests) return;
    if (!items.length) {
      supportStudentRequests.innerHTML = '<div class="support-empty compact"><span>还没有沟通记录</span></div>';
      return;
    }
    supportStudentRequests.innerHTML = `<div class="support-request-table">${items.map((item) => `<div class="support-request-row"><div><b>${item.request_type === "appointment" ? "预约沟通" : "问题咨询"}</b><p>${escapeHtml(item.message)}</p><small>${assignmentDate(item.created_at)}${item.preferred_time ? ` · 希望时间 ${assignmentDate(item.preferred_time)}` : ""}</small></div><em class="support-status is-${supportStatusTone(item.status)}">${supportStatusLabel(item.status)}</em><span class="support-response">${escapeHtml(item.counselor_response || "等待辅导员回复")}</span></div>`).join("")}</div>`;
  }

  async function loadSupportWorkbench(force, keepCaseId) {
    if (!currentUser || !hasFeature("student_support")) return;
    supportCounselorPanel?.classList.toggle("hidden", currentUser.role !== "counselor");
    supportStudentPanel?.classList.toggle("hidden", currentUser.role !== "student");
    supportRefreshBtn?.classList.toggle("hidden", currentUser.role !== "counselor");
    try {
      if (currentUser.role === "counselor") {
        if (supportRoleContext) supportRoleContext.textContent = "辅导员工作空间";
        if (supportPageHeading) supportPageHeading.textContent = "学习支持待办";
        if (supportPageLead) supportPageLead.textContent = "以事实为依据开展确认、联系、跟进和复查，不自动生成正式学业警告。";
        const [caseData, requestData] = await Promise.all([api.supportCases(supportStatusFilter?.value || "all"), api.supportRequests()]);
        supportCaseItems = caseData.items || [];
        const requests = requestData.items || [];
        if (supportMetricOpen) supportMetricOpen.textContent = supportCaseItems.filter((item) => item.status === "open").length;
        if (supportMetricTracking) supportMetricTracking.textContent = supportCaseItems.filter((item) => ["contacted", "tracking"].includes(item.status)).length;
        if (supportMetricReview) supportMetricReview.textContent = supportCaseItems.filter((item) => item.review_at && item.status !== "closed").length;
        if (supportMetricRequests) supportMetricRequests.textContent = requests.filter((item) => item.status === "submitted").length;
        selectedSupportCaseId = keepCaseId || (supportCaseItems.some((item) => Number(item.id) === Number(selectedSupportCaseId)) ? selectedSupportCaseId : supportCaseItems[0]?.id);
        renderSupportCaseList(supportCaseItems);
        renderCounselorSupportRequests(requests);
        if (selectedSupportCaseId) await loadSupportCaseDetail(selectedSupportCaseId);
        else if (supportCaseDetail) supportCaseDetail.innerHTML = '<div class="support-empty"><b>当前没有事项</b><span>可以检查最新教学事实</span></div>';
      } else if (currentUser.role === "student") {
        if (supportRoleContext) supportRoleContext.textContent = "学生个人空间";
        if (supportPageHeading) supportPageHeading.textContent = "我的学习支持";
        if (supportPageLead) supportPageLead.textContent = "查看已共享的支持建议，也可以主动预约辅导员沟通。";
        const [caseData, requestData] = await Promise.all([api.supportCases("all"), api.supportRequests()]);
        const cases = caseData.items || [];
        const requests = requestData.items || [];
        if (supportMetricOpen) supportMetricOpen.textContent = cases.filter((item) => ["contacted", "tracking"].includes(item.status)).length;
        if (supportMetricTracking) supportMetricTracking.textContent = cases.filter((item) => item.status === "tracking").length;
        if (supportMetricReview) supportMetricReview.textContent = cases.filter((item) => item.review_at).length;
        if (supportMetricRequests) supportMetricRequests.textContent = requests.filter((item) => ["submitted", "accepted"].includes(item.status)).length;
        renderStudentSupportCases(cases);
        renderStudentSupportRequests(requests);
      }
    } catch (err) {
      const target = currentUser.role === "counselor" ? supportCaseDetail : supportStudentCases;
      if (target) target.innerHTML = `<div class="dashboard-loading is-error">学习支持数据加载失败: ${escapeHtml(err.message || err)}</div>`;
    }
  }

  function renderDomainSettings(data) {
    if (!domainCurrent || !domainGrid || !domainRoleBody || !data) return;
    const user = data.current_user || currentUser || {};
    const userDomains = user.domain_items || [];
    domainCurrent.innerHTML = `
      <b>${escapeHtml(user.display_name || "当前用户")} · ${escapeHtml(user.role_label || "")}</b>
      <span>当前可访问业务域：${escapeHtml(userDomains.map((d) => d.label).join("、") || "无")}；可访问表：${escapeHtml((user.allowed_tables || []).join(", ") || "无")}</span>
    `;
    domainGrid.innerHTML = "";
    (data.domains || []).forEach((domain) => {
      const active = (user.domains || []).includes(domain.name);
      const card = document.createElement("div");
      card.className = "domain-card";
      card.innerHTML = `
        <b>${active ? "已授权 · " : ""}${escapeHtml(domain.label)}</b>
        <span>${escapeHtml(domain.description || "")}</span>
        <span>表：${escapeHtml((domain.tables || []).join(", "))}</span>
      `;
      domainGrid.appendChild(card);
    });
    domainRoleBody.innerHTML = "";
    (data.roles || []).forEach((role) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${escapeHtml(role.label)}</td>
        <td>${escapeHtml((role.domain_items || []).map((d) => d.label).join("、"))}</td>
        <td>${escapeHtml((role.tables || []).join(", "))}</td>
      `;
      domainRoleBody.appendChild(tr);
    });
  }

  function renderRoleManagement(data) {
    if (!roleUserBody || !data) return;
    if (roleCardGrid) roleCardGrid.innerHTML = "";
    if (passwordAccount && currentUser) {
      passwordAccount.value = `${currentUser.username} · ${currentUser.display_name || ""} · ${currentUser.role_label || ""}`;
    }
    roleUserBody.innerHTML = "";
    (data.users || []).forEach((user) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${escapeHtml(user.username)}</td>
        <td>${escapeHtml(user.display_name)}</td>
        <td>${escapeHtml(user.role_label)}</td>
        <td>${escapeHtml(user.description || "")}</td>
      `;
      roleUserBody.appendChild(tr);
    });
  }

  async function loadDomainSettings(force) {
    if (!force && domainSettingsCache) {
      renderDomainSettings(domainSettingsCache);
      return domainSettingsCache;
    }
    try {
      domainSettingsCache = await api.businessDomains();
      renderDomainSettings(domainSettingsCache);
      renderRoleManagement(domainSettingsCache);
    } catch {
      if (domainCurrent) domainCurrent.innerHTML = "<b>权限加载失败</b><span>请重新登录后再试。</span>";
    }
    return domainSettingsCache;
  }

  function analyticsStatusLabel(status) {
    return ({ missing: "未提交", returned: "需修改", submitted: "已提交", late_submitted: "迟交", graded: "成绩已发布", graded_unpublished: "已批阅待发布" })[status] || status || "-";
  }

  function analyticsMetric(label, value, definition) {
    return `<article><span>${escapeHtml(label)}</span><b>${escapeHtml(value)}</b><small>${escapeHtml(definition)}</small></article>`;
  }

  function renderCourseAnalytics(data) {
    const teacher = data.role === "teacher";
    const metrics = data.metrics || {};
    if (analyticsScopeCopy) analyticsScopeCopy.textContent = teacher
      ? `仅汇总本人授课班“${data.scope.course_name || "当前课程"}”的作业级数据，不展示学生身份。`
      : `仅展示本人在“${data.scope.course_name || "当前课程"}”的任务和已发布成绩。`;
    if (analyticsMeta) analyticsMeta.innerHTML = `<span>统计范围：当前开课班</span><span>更新时间：${escapeHtml(assignmentDate(data.refreshed_at))}</span><span>数据源：${escapeHtml(data.definitions.source)}</span>`;
    const pending = teacher ? metrics.pending_grade_count : metrics.pending_task_count;
    if (analyticsMetrics) analyticsMetrics.innerHTML = [
      analyticsMetric("作业完成率", `${formatNumber(metrics.completion_rate, 2)}%`, data.definitions.completion_rate),
      analyticsMetric("迟交率", `${formatNumber(metrics.late_rate, 2)}%`, data.definitions.late_rate),
      analyticsMetric(teacher ? "待批阅" : "待完成", formatNumber(pending), data.definitions.pending),
      analyticsMetric(teacher ? "得分分布" : "已发布平均分", teacher ? (() => { const d = data.score_summary.distribution || {}; return `90+ ${d["90_plus"] || 0} · 80-89 ${d["80_89"] || 0} · <60 ${d["lt_60"] || 0}`; })() : (data.score_summary.average == null ? "暂无" : formatNumber(data.score_summary.average, 2)), data.definitions.score),
    ].join("");
    if (analyticsDetailTitle) analyticsDetailTitle.textContent = teacher ? "各作业执行情况" : "我的课程任务";
    if (analyticsDetailHead) analyticsDetailHead.innerHTML = teacher
      ? "<tr><th>作业</th><th>截止时间</th><th>已交 / 应交</th><th>未交</th><th>迟交率</th><th>待批阅</th><th>平均分</th></tr>"
      : "<tr><th>作业</th><th>截止时间</th><th>状态</th><th>是否迟交</th><th>已发布成绩</th></tr>";
    const items = data.items || [];
    if (analyticsDetailBody) analyticsDetailBody.innerHTML = items.length ? items.map((item) => teacher
      ? `<tr><td><b>${escapeHtml(item.assignment_title)}</b></td><td>${escapeHtml(assignmentDate(item.due_time))}</td><td>${item.submitted_count} / ${item.enrolled_count}</td><td>${item.missing_count}</td><td>${formatNumber(item.late_rate, 2)}%</td><td>${item.pending_grade_count}</td><td>${item.average_score == null ? "-" : formatNumber(item.average_score, 2)}</td></tr>`
      : `<tr><td><b>${escapeHtml(item.assignment_title)}</b></td><td>${escapeHtml(assignmentDate(item.due_time))}</td><td><span class="analytics-state is-${escapeHtml(item.task_status)}">${escapeHtml(analyticsStatusLabel(item.task_status))}</span></td><td>${item.late ? "是" : "否"}</td><td>${item.published_score == null ? "未发布" : `${formatNumber(item.published_score, 2)} / ${formatNumber(item.max_score)}`}</td></tr>`
    ).join("") : '<tr><td colspan="7" class="analytics-empty">当前课程暂无已发布作业</td></tr>';
    const templates = teacher ? ["本班各作业未交情况", "哪些作业迟交率高", "还有多少提交待批阅"] : ["我的课程还剩哪些任务", "查看我的已发布作业成绩"];
    if (analyticsQuestionTemplates) analyticsQuestionTemplates.innerHTML = templates.map((item) => `<button type="button" data-analytics-question="${escapeHtml(item)}">${escapeHtml(item)}</button>`).join("");
  }

  function renderAnalyticsAnswer(result) {
    if (!analyticsAnswer) return;
    if (result.error || result.clarify) {
      analyticsAnswer.innerHTML = `<div class="analytics-error"><b>本次查询未完成</b><p>${escapeHtml(result.error || result.clarify)}</p></div>`;
      return;
    }
    const columns = result.columns || [];
    const rows = result.rows || [];
    const table = rows.length ? `<div class="analytics-answer-table"><table><thead><tr>${columns.map((col) => `<th>${escapeHtml(col)}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${row.map((cell) => `<td>${escapeHtml(cell == null ? "-" : cell)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>` : '<p class="analytics-empty">没有符合当前课程范围的数据。</p>';
    const feedback = result.query_log_id ? `<div class="analytics-answer-feedback"><span>结果是否有帮助？</span><button type="button" data-analytics-feedback="helpful" data-log-id="${result.query_log_id}">有帮助</button><button type="button" data-analytics-feedback="not_helpful" data-log-id="${result.query_log_id}">需改进</button></div>` : "";
    analyticsAnswer.innerHTML = `<div class="analytics-answer-meta"><span>${result.query_mode === "context_template" ? "课程问题模板" : "受限 NL2SQL"}</span><span>${result.row_count || 0} 行</span></div>${table}<details><summary>查看执行 SQL</summary><code>${escapeHtml(result.sql || "")}</code></details>${feedback}`;
  }

  async function loadAnalyticsHistory() {
    if (!selectedAnalyticsClassId || !analyticsHistoryList) return;
    const data = await api.courseAnalyticsHistory(selectedAnalyticsClassId);
    const items = data.items || [];
    analyticsHistoryList.innerHTML = items.length ? items.map((item) => `<button type="button" data-analytics-question="${escapeHtml(item.question)}"><span>${escapeHtml(item.question)}</span><small>${item.user_feedback === "helpful" ? "有帮助 · " : item.user_feedback === "not_helpful" ? "需改进 · " : ""}${item.status === "success" ? `${item.row_count} 行` : "未完成"} · ${escapeHtml(assignmentDate(item.created_at))}</small></button>`).join("") : "<p>暂无查询记录</p>";
  }

  async function loadCourseAnalytics(force) {
    if (!hasFeature("course_analytics")) return;
    try {
      if (force || !analyticsContexts.length) {
        const contextData = await api.courseAnalyticsContexts();
        analyticsContexts = contextData.items || [];
      }
      if (!analyticsContexts.length) throw new Error("当前账号没有可分析的课程");
      if (!selectedAnalyticsClassId || !analyticsContexts.some((item) => Number(item.id) === Number(selectedAnalyticsClassId))) selectedAnalyticsClassId = Number(analyticsContexts[0].id);
      if (analyticsCoursePicker) {
        analyticsCoursePicker.innerHTML = analyticsContexts.map((item) => `<option value="${item.id}">${escapeHtml(item.course_name)} · ${item.year} ${item.semester === "spring" ? "春" : "秋"}</option>`).join("");
        analyticsCoursePicker.value = selectedAnalyticsClassId;
      }
      const data = await api.courseAnalyticsSummary(selectedAnalyticsClassId);
      renderCourseAnalytics(data);
      await loadAnalyticsHistory();
    } catch (err) {
      if (analyticsAnswer) analyticsAnswer.innerHTML = `<div class="analytics-error"><b>课程分析加载失败</b><p>${escapeHtml(err.message || "请稍后重试")}</p></div>`;
    }
  }

  async function executeAnalyticsQuestion(question) {
    if (!selectedAnalyticsClassId || !question) return;
    if (analyticsAnswer) analyticsAnswer.innerHTML = "<p>正在按当前课程范围查询...</p>";
    try {
      const result = await api.askCourseAnalytics({ teaching_class_id: selectedAnalyticsClassId, question });
      renderAnalyticsAnswer(result);
      await loadAnalyticsHistory();
    } catch (err) {
      renderAnalyticsAnswer({ error: err.message || "查询失败" });
    }
  }

  function showView(id) {
    const trigger = document.querySelector(`[data-view-target="${id}"]`);
    if (trigger && trigger.classList.contains("hidden")) {
      id = preferredHomeView();
    }
    workViews.forEach((view) => view.classList.toggle("active", view.id === id));
    navTargets.forEach((btn) => {
      if (!btn.classList.contains("side-nav-item")) return;
      btn.classList.toggle("active", btn.dataset.viewTarget === id);
    });
    const view = workViews.find((v) => v.id === id);
    if (view) {
      pageTitle.textContent = view.dataset.pageTitle || "问数工作台";
      breadcrumb.textContent = view.dataset.breadcrumb || "智能问数";
    }
    if (id === "kb-list-view") renderKbList();
    if (id === "dashboard-view") loadDashboard();
    if (id === "kb-overview-view") {
      loadFeedback(currentKbSource()).then(() => renderKbOverview());
      renderKbOverview();
    }
    if (id === "schema-console-view") renderSchemaConsole();
    if (id === "data-access-view") window.dispatchEvent(new CustomEvent("nl2sql:data-access:show"));
    if (id === "debug-view") renderDebugSteps();
    if (id === "domain-settings-view") loadDomainSettings();
    if (id === "role-management-view") loadDomainSettings();
    if (id === "assignment-workflow-view") loadAssignmentProduct();
    if (id === "course-analytics-view") loadCourseAnalytics();
    if (id === "support-workbench-view") loadSupportWorkbench();
    if (id === "governance-queue-view" && governanceView) governanceView.renderQueue();
    if (id === "governance-settings-view" && governanceView) governanceView.renderSettings();
  }

  function sourceByName(name) {
    return availableSources.find((s) => s.name === name);
  }

  function sourceLabel(name) {
    if (!name) return "自动识别";
    const s = sourceByName(name);
    return s ? s.label : name;
  }

  function activeSourceName() {
    return selectedKb === "auto" ? "" : selectedKb;
  }

  function setManualSource(src) {
    selectedSource = src || "";
    selectedKb = selectedSource || "auto";
    sourceTags.querySelectorAll(".source-tag").forEach((t) => {
      t.classList.toggle("active", (t.dataset.src || "") === selectedSource);
    });
    conversationSource = null;
    if (loadHistory().length > 0) clearHistory();
    hide(routedSource);
    hideAllStateCards();
    loadSchema(selectedSource || undefined);
    renderSuggestions();
    renderGlossary();
    renderKbOverview();
    renderSchemaConsole();
  }

  function schemaKey(src) {
    return src || "__auto__";
  }

  function currentKbSource() {
    if (selectedKb !== "auto") return selectedKb;
    return conversationSource || selectedSource || (availableSources[0] && availableSources[0].name) || "";
  }

  function schemaSummary(src) {
    const data = schemaCache[schemaKey(src)] || {};
    const tables = data.tables || {};
    const tableNames = Object.keys(tables);
    const fieldCount = tableNames.reduce((sum, name) => sum + ((tables[name] || []).length), 0);
    return { data, tables, tableNames, fieldCount };
  }

  function schemaColumnMeta(src, table, field) {
    const data = schemaCache[schemaKey(src)] || {};
    const columns = (data.columns && data.columns[table]) || [];
    return columns.find((item) => item.column_name === field) || {};
  }

  function profileKey(src) {
    return src || "__auto__";
  }

  function emptyProfile() {
    return { tables: {}, columns: {}, relations: [], metrics: {} };
  }

  function currentProfile(source) {
    return profileCache[profileKey(source)] || emptyProfile();
  }

  function profileColumn(source, table, field) {
    const p = currentProfile(source);
    return (((p.columns || {})[table] || {})[field]) || {};
  }

  function ensureProfileColumn(profile, table, field) {
    profile.columns = profile.columns || {};
    profile.columns[table] = profile.columns[table] || {};
    profile.columns[table][field] = profile.columns[table][field] || {};
    return profile.columns[table][field];
  }

  function ensureProfileTable(profile, table) {
    profile.tables = profile.tables || {};
    profile.tables[table] = profile.tables[table] || {};
    return profile.tables[table];
  }

  function fieldRoleLabel(meta, fallbackName) {
    if (meta.is_primary_key) return "主键";
    if (meta.is_foreign_key) return "关联键";
    if (meta.is_metric) return "指标";
    if (meta.is_dimension) return "维度";
    return inferFieldRole(fallbackName);
  }

  function compactList(values, emptyText) {
    const arr = Array.isArray(values) ? values.filter((v) => v != null && String(v).trim() !== "") : [];
    return arr.length ? arr.slice(0, 6).join(" / ") : (emptyText || "");
  }

  function inferFieldRole(name) {
    const n = String(name || "").toLowerCase();
    if (/(date|time|created|updated|year|month|day)/.test(n)) return "时间";
    if (/(amount|price|count|num|total|score|salary|height|weight|rate|avg|sum)/.test(n)) return "指标";
    if (/(id|key|code)/.test(n)) return "主键/关联";
    return "维度";
  }

  function makeKbRows() {
    const queryLog = loadQueryLog();
    const saved = readJsonList(SAVED_QUERY_KEY);
    const rows = availableSources.map((s) => {
      const summary = schemaSummary(s.name);
      const logs = queryLog.filter((item) => item.source === s.name);
      const loading = schemaLoading.has(schemaKey(s.name));
      return {
        id: s.name,
        name: s.name,
        label: s.label || s.name,
        dialect: s.dialect || "SQL",
        desc: summary.tableNames.length
          ? `${summary.tableNames.length} 张表 / ${summary.fieldCount} 个字段`
          : (loading ? "Schema 加载中" : "Schema 待加载"),
        status: "已接入",
        recall: summary.tableNames.length ? `${Math.min(96, 78 + summary.tableNames.length * 3)}%` : (loading ? "加载中" : "待加载"),
        owner: "Data Team",
        queries: logs.length,
        saved: saved.filter((item) => item.source === s.name).length,
      };
    });
    return [{
      id: "auto",
      name: "",
      label: "自动识别",
      dialect: "Router",
      desc: "按问题语义自动选择知识库",
      status: availableSources.length ? "运行中" : "待连接",
      recall: availableSources.length ? "90%" : "待连接",
      owner: "System",
      queries: queryLog.length,
      saved: saved.length,
    }, ...rows];
  }

  function renderKbList() {
    if (!kbTableBody) return;
    const keyword = (kbSearch && kbSearch.value || "").trim().toLowerCase();
    const rows = makeKbRows().filter((row) => {
      if (!keyword) return true;
      return [row.label, row.id, row.dialect, row.status, row.owner].some((v) => String(v || "").toLowerCase().includes(keyword));
    });
    kbTableBody.innerHTML = "";
    rows.forEach((row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>
          <div class="kb-name-cell">
            <span class="kb-icon">${escapeHtml(row.id === "auto" ? "A" : row.label.slice(0, 1).toUpperCase())}</span>
            <span><b>${escapeHtml(row.label)}</b><small>${escapeHtml(row.id || "auto")} · ${escapeHtml(row.dialect)}</small></span>
          </div>
        </td>
        <td><span class="status-badge">${row.status}</span></td>
        <td>${escapeHtml(row.desc)}</td>
        <td><span class="quality-pill">${escapeHtml(row.recall)}</span></td>
        <td>${row.queries} / ${row.saved}</td>
        <td class="row-actions"></td>
      `;
      const actions = tr.querySelector(".row-actions");
      const openBtn = document.createElement("button");
      openBtn.type = "button";
      openBtn.textContent = "打开";
      openBtn.addEventListener("click", () => {
        selectedKb = row.id || "auto";
        selectedSource = row.name || "";
        loadSchema(selectedSource || undefined);
        showView("kb-overview-view");
      });
      const askBtn = document.createElement("button");
      askBtn.type = "button";
      askBtn.textContent = "问数";
      askBtn.addEventListener("click", () => {
        setManualSource(row.name || "");
        showView("assistant-view");
        input.focus();
      });
      actions.appendChild(openBtn);
      actions.appendChild(askBtn);
      kbTableBody.appendChild(tr);
    });
  }

  function renderStatPill(label, value, sub) {
    const div = document.createElement("div");
    div.className = "stat-pill";
    div.innerHTML = `<span>${label}</span><b>${value}</b><small>${sub || ""}</small>`;
    return div;
  }

  function renderKbOverview() {
    if (!kbStatGrid || !healthList || !activityList) return;
    const src = currentKbSource();
    const summary = schemaSummary(src);
    const label = selectedKb === "auto" ? "自动识别知识库" : sourceLabel(src);
    if (kbCurrentTitle) kbCurrentTitle.textContent = label;
    if (kbCurrentDesc) {
      kbCurrentDesc.textContent = selectedKb === "auto"
        ? "系统会根据问题语义在已连接的数据源中自动路由，并保留每次查询的过程证据。"
        : `${src || "当前"} 数据源的 Schema、术语、样例问法和查询行为概览。`;
    }
    const logs = loadQueryLog().filter((item) => !src || item.source === src);
    const saved = readJsonList(SAVED_QUERY_KEY).filter((item) => !src || item.source === src);
    const feedback = feedbackCache.filter((item) => !src || item.source === src);
    const profile = currentProfile(src);
    const governedFields = Object.values(profile.columns || {}).reduce((sum, cols) => {
      return sum + Object.values(cols || {}).filter((x) => x && (x.business_name || x.description || x.semantic_type)).length;
    }, 0);
    const relationCount = (profile.relations || []).length;
    kbStatGrid.innerHTML = "";
    kbStatGrid.appendChild(renderStatPill("数据表", summary.tableNames.length, "已读取 Schema"));
    kbStatGrid.appendChild(renderStatPill("字段", summary.fieldCount, "可被问数召回"));
    kbStatGrid.appendChild(renderStatPill("查询", logs.length, "最近本地记录"));
    kbStatGrid.appendChild(renderStatPill("收藏", saved.length, "沉淀为样例"));
    if (feedback.length) kbStatGrid.appendChild(renderStatPill("反馈", feedback.length, "待治理线索"));

    const quality = qualityCache[profileKey(src)] || {};
    const qp = quality.parts || {};
    const healthItems = quality.score ? [
      ["总质量", quality.score],
      ["表粒度", qp.table_grain || 0],
      ["字段语义", qp.field_semantics || 0],
      ["关系治理", qp.relations || 0],
      ["指标口径", qp.metrics || 0],
      ["安全标记", qp.safety || 0],
    ] : [
      ["Schema 完整度", summary.tableNames.length ? 88 : 45],
      ["字段治理", summary.fieldCount ? Math.min(96, Math.round(governedFields / summary.fieldCount * 100)) : 0],
      ["关系治理", relationCount ? Math.min(96, 60 + relationCount * 6) : 35],
      ["术语覆盖", Math.min(96, 52 + (loadGlossary(src).length + loadMetrics(src).length) * 8)],
      ["召回稳定性", logs.length ? 86 : 70],
      ["结果可信度", lastTrace && (!src || lastTrace.source === src) ? 82 : 74],
    ];
    healthList.innerHTML = "";
    healthItems.forEach(([name, value]) => {
      const row = document.createElement("div");
      row.className = "health-row";
      row.innerHTML = `<div><b>${name}</b><span>${value >= 80 ? "健康" : "需补充"}</span></div><div class="health-track"><i style="width:${value}%"></i></div><em>${value}%</em>`;
      healthList.appendChild(row);
    });
    (quality.gaps || []).slice(0, 4).forEach((gap) => {
      const row = document.createElement("div");
      row.className = "health-row";
      row.innerHTML = `<div><b>治理建议</b><span>${escapeHtml(gap)}</span></div><em>todo</em>`;
      healthList.appendChild(row);
    });

    activityList.innerHTML = "";
    const activity = logs.slice(0, 6);
    if (!activity.length) {
      activityList.innerHTML = '<div class="empty-note">还没有查询活动。完成一次问数后，这里会显示问题、数据源、耗时和行数。</div>';
      renderSavedExamples(src);
      renderFeedbackList(src);
      return;
    }
    activity.forEach((item) => {
      const row = document.createElement("button");
      row.type = "button";
      row.className = "activity-row";
      row.innerHTML = `<span>${escapeHtml(item.question || "")}</span><small>${escapeHtml(item.source_label || item.source || "自动识别")} · ${escapeHtml(item.row_count || 0)} 行 · ${escapeHtml(item.elapsed_ms || 0)} ms</small>`;
      row.addEventListener("click", () => {
        input.value = item.question || "";
        setManualSource(item.source || "");
        showView("assistant-view");
      });
      activityList.appendChild(row);
    });

    renderSavedExamples(src);
    renderFeedbackList(src);
  }

  function renderFeedbackList(source) {
    if (!feedbackList) return;
    const items = feedbackCache.filter((item) => !source || item.source === source).slice(0, 12);
    feedbackList.innerHTML = "";
    if (!items.length) {
      feedbackList.innerHTML = '<div class="empty-note">暂无反馈。用户点击「结果正确」或「反馈错误」后会出现在这里。</div>';
      return;
    }
    items.forEach((item) => {
      const row = document.createElement("div");
      row.className = `feedback-row ${item.kind === "correct" ? "is-correct" : "is-incorrect"}`;
      row.innerHTML = `
        <div><b>${item.kind === "correct" ? "正确" : "错误"}</b><span>${escapeHtml(item.question || "")}</span></div>
        <small>${escapeHtml(item.category || "未分类")} · ${escapeHtml(item.reason || "无说明")} · ${escapeHtml(item.source_label || item.source || "自动识别")}</small>
      `;
      feedbackList.appendChild(row);
    });
  }

  function savedExamplesForSource(source) {
    const remote = standardExamplesCache[profileKey(source)];
    if (remote && remote.length) return remote;
    return readJsonList(SAVED_QUERY_KEY).filter((item) => !source || item.source === source);
  }

  function renderSavedExamples(source) {
    if (!savedExampleList) return;
    const examples = savedExamplesForSource(source);
    savedExampleList.innerHTML = "";
    if (!examples.length) {
      savedExampleList.innerHTML = '<div class="empty-note">还没有收藏样例。在问数结果中点击「保存查询」后，这里会展示可复用的 few-shot。</div>';
      return;
    }
    examples.slice(0, 12).forEach((item) => {
      const card = document.createElement("div");
      card.className = "saved-example-card";
      card.innerHTML = `
        <div class="saved-example-head">
          <span>${escapeHtml(item.source_label || item.source || "自动识别")}</span>
          <label><input type="checkbox" class="saved-example-fewshot" ${item.use_few_shot === false ? "" : "checked"} /> 用于 few-shot</label>
        </div>
        <textarea class="saved-example-question-input" rows="2">${escapeHtml(item.question || "")}</textarea>
        <textarea class="saved-example-sql-input" rows="5">${escapeHtml(item.sql || "")}</textarea>
        <div class="saved-example-actions">
          <button class="saved-example-use" type="button">带入提问</button>
          <button class="saved-example-save" type="button">保存修改</button>
          <button class="saved-example-delete" type="button">删除</button>
        </div>
      `;
      const questionInput = card.querySelector(".saved-example-question-input");
      const sqlInput = card.querySelector(".saved-example-sql-input");
      const fewshotInput = card.querySelector(".saved-example-fewshot");
      async function persistExample() {
        const src = item.source || source;
        if (src) {
          await saveStandardExample(src, {
            id: item.id,
            question: questionInput.value.trim(),
            sql: sqlInput.value.trim(),
            source_label: item.source_label || sourceLabel(src),
            enabled: fewshotInput.checked,
            tags: item.tags || [],
          });
        }
        const next = readJsonList(SAVED_QUERY_KEY).map((x) => x.id === item.id ? {
          ...x,
          question: questionInput.value.trim(),
          sql: sqlInput.value.trim(),
          use_few_shot: fewshotInput.checked,
        } : x);
        writeJsonList(SAVED_QUERY_KEY, next);
      }
      card.querySelector(".saved-example-use").addEventListener("click", () => {
        input.value = questionInput.value.trim() || item.question || "";
        setManualSource(item.source || "");
        showView("assistant-view");
        input.focus();
      });
      card.querySelector(".saved-example-save").addEventListener("click", () => {
        persistExample().then(() => renderSavedExamples(source));
      });
      fewshotInput.addEventListener("change", () => {
        persistExample().then(() => renderKbOverview());
      });
      card.querySelector(".saved-example-delete").addEventListener("click", async () => {
        if (item.source || source) await deleteStandardExample(item.source || source, item.id);
        const next = readJsonList(SAVED_QUERY_KEY).filter((x) => x.id !== item.id);
        writeJsonList(SAVED_QUERY_KEY, next);
        renderKbList();
        renderKbOverview();
      });
      savedExampleList.appendChild(card);
    });
  }

  function renderSchemaConsole() {
    if (!schemaTree || !fieldTableBody || !schemaEditorTitle) return;
    const src = currentKbSource();
    const summary = schemaSummary(src);
    const tables = summary.tables;
    const names = summary.tableNames;
    const profile = currentProfile(src);
    const totalFields = names.reduce((sum, name) => sum + (tables[name] || []).length, 0);
    const profiledFields = Object.values(profile.columns || {}).reduce((sum, columns) => {
      return sum + Object.values(columns || {}).filter((item) => item && (item.business_name || item.description || item.semantic_type)).length;
    }, 0);
    if (schemaStatTables) schemaStatTables.textContent = names.length;
    if (schemaStatFields) schemaStatFields.textContent = totalFields;
    if (schemaStatProfiled) schemaStatProfiled.textContent = profiledFields;
    if (!names.includes(activeSchemaTable)) activeSchemaTable = names[0] || "";
    schemaTree.innerHTML = "";
    if (!names.length) {
      schemaTree.innerHTML = '<div class="empty-note">暂无 Schema。请先选择知识库或刷新数据源。</div>';
    } else {
      const visibleNames = names.filter((name) => name.toLowerCase().includes(schemaTableQuery));
      visibleNames.forEach((name) => {
        const tableFields = tables[name] || [];
        const profiledInTable = tableFields.filter((field) => {
          const profMeta = profileColumn(src, name, field);
          return profMeta && (profMeta.business_name || profMeta.description || profMeta.semantic_type);
        }).length;
        const tableProfile = (profile.tables || {})[name] || {};
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "schema-tree-btn";
        btn.classList.toggle("active", name === activeSchemaTable);
        btn.innerHTML = `
          <b>${escapeHtml(tableProfile.business_name || name)}</b>
          <small>${escapeHtml(name)}</small>
          <span>${profiledInTable}/${tableFields.length}</span>
        `;
        btn.addEventListener("click", () => {
          activeSchemaTable = name;
          schemaFieldQuery = "";
          if (schemaFieldSearch) schemaFieldSearch.value = "";
          expandedSchemaFields.clear();
          renderSchemaConsole();
        });
        schemaTree.appendChild(btn);
      });
      if (!visibleNames.length) schemaTree.innerHTML = '<div class="empty-note">没有匹配的数据表</div>';
    }

    schemaEditorTitle.textContent = activeSchemaTable ? `${activeSchemaTable} 字段配置` : "字段配置";
    if (schemaTableSummary) {
      if (!activeSchemaTable) {
        schemaTableSummary.innerHTML = "";
      } else {
        const tableProfile = (profile.tables || {})[activeSchemaTable] || {};
        const fieldCount = (tables[activeSchemaTable] || []).length;
        const tableProfiled = (tables[activeSchemaTable] || []).filter((field) => {
          const profMeta = profileColumn(src, activeSchemaTable, field);
          return profMeta && (profMeta.business_name || profMeta.description || profMeta.semantic_type);
        }).length;
        schemaTableSummary.innerHTML = `
          <span><b>${tableProfiled}/${fieldCount}</b> 已画像字段</span>
          <span>${escapeHtml(tableProfile.business_name || "未设置业务名")}</span>
          <span>${escapeHtml(tableProfile.grain || "未设置粒度")}</span>
          <span>${escapeHtml(tableProfile.default_time_column || "未设置时间字段")}</span>
        `;
      }
    }
    fieldTableBody.innerHTML = "";
    if (activeSchemaTable) {
      const tableProfile = (profile.tables || {})[activeSchemaTable] || {};
      const tableCard = document.createElement("div");
      tableCard.className = "field-card table-profile-card is-expanded";
      tableCard.innerHTML = `
        <div class="field-card-head">
          <div class="field-identity">
            <b>${escapeHtml(activeSchemaTable)}</b>
            <span>表画像 / 粒度 / 默认口径</span>
          </div>
          <div class="field-badges"><em>P0</em><em>发布到后端</em></div>
          <button class="field-meta-save" type="button">保存表画像</button>
        </div>
        <div class="field-card-grid">
          <label>
            <span>业务名</span>
            <input class="table-profile-input" data-profile-field="business_name" value="${escapeHtml(tableProfile.business_name || "")}" placeholder="例如: 学生 / 课程 / 成绩" />
          </label>
          <label class="wide">
            <span>表说明</span>
            <input class="table-profile-input" data-profile-field="description" value="${escapeHtml(tableProfile.description || "")}" placeholder="这张表记录什么业务对象" />
          </label>
          <label class="wide">
            <span>表粒度</span>
            <input class="table-profile-input" data-profile-field="grain" value="${escapeHtml(tableProfile.grain || "")}" placeholder="例如: 一行代表一名学生或一条选课记录" />
          </label>
          <label>
            <span>默认时间字段</span>
            <input class="table-profile-input" data-profile-field="default_time_column" value="${escapeHtml(tableProfile.default_time_column || "")}" placeholder="created_at" />
          </label>
          <label class="wide">
            <span>默认过滤</span>
            <input class="table-profile-input" data-profile-field="default_filters" value="${escapeHtml((tableProfile.default_filters || []).join("; "))}" placeholder="status = 'paid'; is_deleted = 0" />
          </label>
        </div>
      `;
      tableCard.querySelector(".field-meta-save").addEventListener("click", async () => {
        const next = JSON.parse(JSON.stringify(currentProfile(src)));
        const target = ensureProfileTable(next, activeSchemaTable);
        tableCard.querySelectorAll(".table-profile-input").forEach((el) => {
          const key = el.dataset.profileField;
          if (key === "default_filters") {
            target[key] = el.value.split(";").map((x) => x.trim()).filter(Boolean);
          } else {
            target[key] = el.value.trim();
          }
        });
        await saveProfile(src, next);
        renderSchemaConsole();
      });
      fieldTableBody.appendChild(tableCard);
    }
    const fieldMeta = loadFieldMeta(src);
    const allFields = tables[activeSchemaTable] || [];
    const visibleFields = allFields.filter((field) => {
      const serverMeta = schemaColumnMeta(src, activeSchemaTable, field);
      const profMeta = profileColumn(src, activeSchemaTable, field);
      const localMeta = fieldMeta[fieldMetaId(activeSchemaTable, field)] || {};
      const haystack = [field, profMeta.business_name, profMeta.description, serverMeta.business_name, serverMeta.description, localMeta.alias, localMeta.desc]
        .filter(Boolean).join(" ").toLowerCase();
      return !schemaFieldQuery || haystack.includes(schemaFieldQuery);
    });
    if (schemaFieldCount) schemaFieldCount.textContent = `${visibleFields.length} / ${allFields.length} 个字段`;
    if (schemaExpandFields) {
      const allExpanded = visibleFields.length > 0 && visibleFields.every((field) => expandedSchemaFields.has(`${activeSchemaTable}.${field}`));
      schemaExpandFields.textContent = allExpanded ? "收起全部" : "展开全部";
    }
    visibleFields.forEach((field) => {
      const card = document.createElement("div");
      const fieldKey = `${activeSchemaTable}.${field}`;
      const isExpanded = expandedSchemaFields.has(fieldKey);
      card.className = `field-card schema-field-card${isExpanded ? " is-expanded" : ""}`;
      const serverMeta = schemaColumnMeta(src, activeSchemaTable, field);
      const role = fieldRoleLabel(serverMeta, field);
      const id = fieldMetaId(activeSchemaTable, field);
      const meta = fieldMeta[id] || {};
      const profMeta = profileColumn(src, activeSchemaTable, field);
      const enumText = meta.enums || compactList(profMeta.enum_values, "") || compactList(serverMeta.enum_values, "");
      const descText = meta.desc || profMeta.description || serverMeta.description || "";
      const unitText = meta.unit || profMeta.unit || serverMeta.unit || "";
      const defaultFilterText = meta.default_filter || profMeta.default_filter || serverMeta.default_filter || "";
      const aliasText = meta.alias || profMeta.business_name || serverMeta.business_name || "";
      const semanticText = profMeta.semantic_type || serverMeta.semantic_type || "";
      const aggText = profMeta.default_aggregation || serverMeta.default_aggregation || "";
      const nullableText = serverMeta.nullable === false ? "NOT NULL" : "可空";
      const defaultText = serverMeta.default_value ? `默认 ${serverMeta.default_value}` : "";
      const keyBadge = serverMeta.is_primary_key ? "主键" : (serverMeta.is_foreign_key ? "外键" : "");
      const previewText = aliasText || descText || "尚未补充业务说明";
      card.innerHTML = `
        <div class="field-card-head">
          <div class="field-identity">
            <b>${escapeHtml(field)}</b>
            <span>${escapeHtml(nullableText)}${defaultText ? " · " + escapeHtml(defaultText) : ""}</span>
            <small>${escapeHtml(previewText)}</small>
          </div>
          <div class="field-badges">
            <code>${escapeHtml(serverMeta.data_type || "unknown")}</code>
            ${keyBadge ? `<em>${escapeHtml(keyBadge)}</em>` : ""}
            <em>${escapeHtml(role)}</em>
            <em>${role === "指标" ? "可聚合" : "可筛选"}</em>
          </div>
          <button class="field-expand-toggle" type="button" aria-expanded="${isExpanded}">${isExpanded ? "收起" : "编辑"}</button>
          <button class="field-meta-save" type="button">保存</button>
        </div>
        <div class="field-card-grid">
          <label>
            <span>中文名 / 别名</span>
            <input class="field-meta-input" data-meta-field="business_name" value="${escapeHtml(aliasText)}" placeholder="例如: 总评成绩 / 学院名称" />
          </label>
          <label class="wide">
            <span>业务描述</span>
            <input class="field-meta-input" data-meta-field="description" value="${escapeHtml(descText)}" placeholder="字段含义、统计口径或使用边界" />
          </label>
          <label class="wide">
            <span>枚举 / 取值</span>
            <input class="field-meta-input" data-meta-field="enums" value="${escapeHtml(enumText)}" placeholder="如 paid=已支付, cancelled=已取消" />
          </label>
          <label>
            <span>示例值</span>
            <output>${escapeHtml(compactList(serverMeta.example_values, "-"))}</output>
          </label>
          <label>
            <span>单位</span>
            <input class="field-meta-input compact" data-meta-field="unit" value="${escapeHtml(unitText)}" placeholder="元 / 个 / %" />
          </label>
          <label>
            <span>默认过滤</span>
            <input class="field-meta-input" data-meta-field="default_filter" value="${escapeHtml(defaultFilterText)}" placeholder="如 is_deleted = 0" />
          </label>
          <label>
            <span>语义类型</span>
            <input class="field-meta-input compact" data-meta-field="semantic_type" value="${escapeHtml(semanticText)}" placeholder="metric / dimension / time / identifier" />
          </label>
          <label>
            <span>默认聚合</span>
            <input class="field-meta-input compact" data-meta-field="default_aggregation" value="${escapeHtml(aggText)}" placeholder="sum / avg / count" />
          </label>
          <label>
            <span>敏感 / 禁用</span>
            <input class="field-meta-input compact" data-meta-field="flags" value="${escapeHtml([profMeta.sensitive ? "sensitive" : "", profMeta.deprecated ? "deprecated" : "", profMeta.enabled === false ? "disabled" : ""].filter(Boolean).join(", "))}" placeholder="sensitive, deprecated, disabled" />
          </label>
        </div>
      `;
      card.querySelector(".field-expand-toggle").addEventListener("click", () => {
        const expanded = card.classList.toggle("is-expanded");
        const toggle = card.querySelector(".field-expand-toggle");
        toggle.textContent = expanded ? "收起" : "编辑";
        toggle.setAttribute("aria-expanded", String(expanded));
        if (expanded) expandedSchemaFields.add(fieldKey);
        else expandedSchemaFields.delete(fieldKey);
      });
      card.querySelector(".field-meta-save").addEventListener("click", async () => {
        const next = JSON.parse(JSON.stringify(currentProfile(src)));
        const target = ensureProfileColumn(next, activeSchemaTable, field);
        card.querySelectorAll(".field-meta-input").forEach((el) => {
          const key = el.dataset.metaField;
          const value = el.value.trim();
          if (key === "enums") target.enum_values = value ? value.split(/[;/]/).map((x) => x.trim()).filter(Boolean) : [];
          else if (key === "flags") {
            const flags = value.toLowerCase();
            target.sensitive = flags.includes("sensitive");
            target.deprecated = flags.includes("deprecated");
            target.enabled = !flags.includes("disabled");
          } else {
            target[key] = value;
          }
        });
        await saveProfile(src, next);
        renderSchemaConsole();
      });
      fieldTableBody.appendChild(card);
    });
    if (!visibleFields.length && activeSchemaTable) {
      const empty = document.createElement("div");
      empty.className = "empty-note schema-fields-empty";
      empty.textContent = schemaFieldQuery ? "没有匹配的字段，请尝试其他关键词。" : "当前表暂无字段。";
      fieldTableBody.appendChild(empty);
    }

    if (metricList) {
      const metrics = currentProfile(src).metrics || {};
      metricList.innerHTML = "";
      const add = document.createElement("button");
      add.className = "nav-btn secondary metric-add-btn";
      add.type = "button";
      add.textContent = "新增指标";
      add.addEventListener("click", async () => {
        const name = prompt("指标名称", "新指标");
        if (!name) return;
        const formula = prompt("指标公式", "挂科人数 / 选课人数");
        if (!formula) return;
        const next = JSON.parse(JSON.stringify(currentProfile(src)));
        next.metrics = next.metrics || {};
        next.metrics[name.trim()] = { formula: formula.trim(), enabled: true };
        await saveProfile(src, next);
        renderSchemaConsole();
      });
      metricList.appendChild(add);
      Object.entries(metrics).forEach(([name, metric]) => {
        const card = document.createElement("div");
        card.className = "metric-card";
        card.innerHTML = `
          <div class="metric-card-head">
            <input class="metric-name" value="${escapeHtml(name)}" />
            <label><input class="metric-enabled" type="checkbox" ${metric.enabled === false ? "" : "checked"} /> 启用</label>
          </div>
          <input class="metric-formula" value="${escapeHtml(metric.formula || "")}" placeholder="公式 / 计算口径" />
          <input class="metric-filters" value="${escapeHtml((metric.default_filters || []).join("; "))}" placeholder="默认过滤, 用 ; 分隔" />
          <input class="metric-time" value="${escapeHtml(metric.default_time_column || "")}" placeholder="默认时间字段" />
          <textarea class="metric-desc" rows="2" placeholder="说明">${escapeHtml(metric.description || "")}</textarea>
          <div class="saved-example-actions">
            <button type="button" class="metric-save">保存</button>
            <button type="button" class="metric-delete">删除</button>
            <button type="button" class="metric-test">测试命中</button>
          </div>
        `;
        card.querySelector(".metric-save").addEventListener("click", async () => {
          const next = JSON.parse(JSON.stringify(currentProfile(src)));
          next.metrics = next.metrics || {};
          delete next.metrics[name];
          const newName = card.querySelector(".metric-name").value.trim();
          if (!newName) return;
          next.metrics[newName] = {
            formula: card.querySelector(".metric-formula").value.trim(),
            default_filters: card.querySelector(".metric-filters").value.split(";").map((x) => x.trim()).filter(Boolean),
            default_time_column: card.querySelector(".metric-time").value.trim(),
            description: card.querySelector(".metric-desc").value.trim(),
            enabled: card.querySelector(".metric-enabled").checked,
          };
          await saveProfile(src, next);
          renderSchemaConsole();
        });
        card.querySelector(".metric-delete").addEventListener("click", async () => {
          const next = JSON.parse(JSON.stringify(currentProfile(src)));
          next.metrics = next.metrics || {};
          delete next.metrics[name];
          await saveProfile(src, next);
          renderSchemaConsole();
        });
        card.querySelector(".metric-test").addEventListener("click", () => {
          const q = prompt("输入一个问题,检查是否包含该指标名", `今年${name}是多少?`);
          if (q != null) alert(q.includes(card.querySelector(".metric-name").value.trim()) ? "会命中该指标" : "未直接命中,建议添加别名或标准问法");
        });
        metricList.appendChild(card);
      });
      if (Object.keys(metrics).length === 0) {
        const empty = document.createElement("div");
        empty.className = "empty-note";
        empty.textContent = "暂无结构化指标。点击新增指标沉淀 GMV、客单价、复购用户数等口径。";
        metricList.appendChild(empty);
      }
    }
    if (termList) {
      const terms = [...loadGlossary(src), "最近一年 = 当前日期向前 12 个月", "TOP N = 按指标倒序取前 N 条"].slice(0, 10);
      termList.innerHTML = "";
      terms.forEach((text) => {
        const li = document.createElement("li");
        li.className = "tag-chip";
        li.textContent = text;
        termList.appendChild(li);
      });
    }
    renderRelations(src);
    renderProfileVersions(src);
  }

  function renderProfileVersions(source) {
    if (!profileVersionList) return;
    const versions = profileVersionsCache[profileKey(source)] || [];
    profileVersionList.innerHTML = "";
    if (!versions.length) {
      profileVersionList.innerHTML = '<div class="empty-note">暂无发布快照。字段保存只会更新草稿，点击发布后才会生成版本。</div>';
      return;
    }
    versions.slice(0, 6).forEach((v) => {
      const row = document.createElement("div");
      row.className = "relation-row version-row";
      const title = v.label || (v.kind === "publish" ? "发布版本" : "自动快照");
      const desc = v.description || v.id;
      row.innerHTML = `
        <span>
          <b>${escapeHtml(title)}</b>
          <small>${escapeHtml(desc)}</small>
          <small>${escapeHtml(v.id)} · ${escapeHtml(v.size || 0)} bytes</small>
        </span>
        <div class="version-actions">
          <button type="button" data-action="rollback">回滚</button>
          <button type="button" data-action="rename">重命名</button>
          <button type="button" data-action="delete">删除</button>
        </div>
      `;
      row.querySelector('[data-action="rollback"]').addEventListener("click", async () => {
        if (!confirm(`回滚到 ${v.id}? 当前 profile 会先自动保存为新快照。`)) return;
        let data;
        try {
          data = await api.rollbackProfile(source, v.id);
        } catch {
          alert("回滚失败");
          return;
        }
        profileCache[profileKey(source)] = data.profile || emptyProfile();
        await loadProfileVersions(source);
        await loadSchema(source);
        renderSchemaConsole();
      });
      row.querySelector('[data-action="rename"]').addEventListener("click", async () => {
        const label = prompt("版本名称", v.label || title);
        if (label == null) return;
        const description = prompt("版本描述", v.description || "");
        if (description == null) return;
        try {
          await api.updateProfileVersion(source, v.id, { label: label.trim(), description: description.trim() });
        } catch {
          alert("更新版本信息失败");
          return;
        }
        await loadProfileVersions(source);
        renderProfileVersions(source);
      });
      row.querySelector('[data-action="delete"]').addEventListener("click", async () => {
        if (!confirm(`删除版本 ${v.label || v.id}? 删除后不能回滚到该快照。`)) return;
        try {
          await api.deleteProfileVersion(source, v.id);
        } catch {
          alert("删除版本失败");
          return;
        }
        await loadProfileVersions(source);
        renderProfileVersions(source);
      });
      profileVersionList.appendChild(row);
    });
  }

  function renderRelations(source) {
    if (!relationList) return;
    const list = loadRelations(source);
    relationList.innerHTML = "";
    if (!list.length) {
      relationList.innerHTML = '<div class="empty-note">暂无表关系。添加后会注入问数上下文。</div>';
      return;
    }
    list.forEach((text, index) => {
      const row = document.createElement("div");
      row.className = "relation-row";
      row.innerHTML = `<span>${escapeHtml(text)}</span><button type="button">删除</button>`;
      row.querySelector("button").addEventListener("click", () => {
        const next = JSON.parse(JSON.stringify(currentProfile(source)));
        next.relations = next.relations || [];
        next.relations.splice(index, 1);
        saveProfile(source, next).then(() => renderRelations(source));
      });
      relationList.appendChild(row);
    });
  }

  function addRelationEntry() {
    const src = currentKbSource();
    const text = (relationInput && relationInput.value || "").trim();
    if (!src || !text) return;
    const m = text.match(/^\s*([A-Za-z_][\w]*\.[A-Za-z_][\w]*)\s*=\s*([A-Za-z_][\w]*\.[A-Za-z_][\w]*)(?:\s*[;·]\s*(.*))?$/);
    if (!m) {
      alert("关系格式示例: enrollment.student_id = student.id");
      return;
    }
    const next = JSON.parse(JSON.stringify(currentProfile(src)));
    next.relations = next.relations || [];
    const exists = next.relations.some((r) => r.left === m[1] && r.right === m[2]);
    if (!exists) next.relations.unshift({ left: m[1], right: m[2], type: "manual", description: m[3] || "" });
    relationInput.value = "";
    saveProfile(src, next).then(() => renderRelations(src));
  }

  function renderDebugSteps() {
    if (!debugSteps) return;
    debugSteps.innerHTML = "";
    if (!lastTrace) {
      debugSteps.innerHTML = '<div class="empty-note">执行一次问数后，这里会展示路由、召回、SQL、安全校验和可信度评估链路。</div>';
      return;
    }
    const steps = [
      ["数据源路由", lastTrace.source_label || lastTrace.source || "自动识别", lastTrace.route_reason || (lastTrace.auto_routed ? "系统自动选择最相关的数据源。" : "使用当前锁定的数据源。")],
      ["Schema 召回", (lastTrace.trace && lastTrace.trace.retrieval_used) ? `命中表: ${(lastTrace.trace.tables || []).join(", ")}` : `${lastTrace.columns || 0} 个结果字段`, (lastTrace.trace && lastTrace.trace.retrievers_used || []).join(" / ") || "结合问题、术语表和表结构选择候选字段。"],
      ["SQL 生成", lastTrace.sql ? lastTrace.sql.slice(0, 160) : "无 SQL", "生成只读查询并保留可复制 SQL。"],
      ["执行结果", `${lastTrace.row_count || 0} 行 · ${lastTrace.elapsed_ms || 0} ms`, "结果表、CSV 下载和图表预览共用同一份返回数据。"],
      ["可信度评估", lastTrace.judge_id ? "后台异步评估" : "未触发", "评估结果会补充到 SQL 元信息区域。"],
    ];
    steps.forEach(([title, value, desc], i) => {
      const div = document.createElement("div");
      div.className = "debug-step";
      div.innerHTML = `<span class="debug-step-no">${i + 1}</span><div><b>${escapeHtml(title)}</b><strong>${escapeHtml(value)}</strong><p>${escapeHtml(desc)}</p></div>`;
      debugSteps.appendChild(div);
    });
  }

  function renderDebugPayload(data, question) {
    lastTrace = {
      question,
      source: data.source,
      source_label: data.source_label,
      auto_routed: data.auto_routed,
      route_reason: data.route_reason,
      sql: "",
      columns: data.column_count,
      row_count: 0,
      elapsed_ms: 0,
      judge_id: null,
      trace: {
        retrieval_used: data.retrieval_used,
        tables: data.retrieval_tables || [],
        retrievers_used: data.retrievers_used || [],
        context_preview: data.context_preview || "",
      },
    };
    debugSteps.innerHTML = "";
    const rows = [
      ["路由结果", `${data.source_label || data.source || "-"} · ${data.auto_routed ? "自动" : "手动"}`, data.route_reason || ""],
      ["Schema 规模", `${data.table_count || 0} 张表 / ${data.column_count || 0} 个字段`, data.retrieval_used ? "已触发 schema linking" : "未触发检索,使用整库 DDL"],
      ["召回表", (data.retrieval_tables || []).join(", ") || "-", (data.retrievers_used || []).join(" / ") || "-"],
      ["上下文预览", (data.context_preview || "").slice(0, 500), "这是将喂给生成器的 schema 证据预览。"],
    ];
    rows.forEach(([title, value, desc], i) => {
      const div = document.createElement("div");
      div.className = "debug-step";
      div.innerHTML = `<span class="debug-step-no">${i + 1}</span><div><b>${escapeHtml(title)}</b><strong>${escapeHtml(value)}</strong><p>${escapeHtml(desc)}</p></div>`;
      debugSteps.appendChild(div);
    });
  }

  async function runRetrievalDebug() {
    const question = (debugQuestion && debugQuestion.value || input.value || "").trim();
    if (!question) return;
    debugSteps.innerHTML = '<div class="empty-note">正在分析路由和召回...</div>';
    try {
      const data = await api.debugRetrieval({ question, source: manualSource(), current_source: conversationSource, history: loadHistory().slice(-MAX_HISTORY_TURNS) });
      renderDebugPayload(data, question);
    } catch (e) {
      debugSteps.innerHTML = `<div class="empty-note">调试失败: ${escapeHtml(e.message)}</div>`;
    }
  }

  /* ---------------- 我的术语表(按库存 localStorage) ---------------- */

  // 当前术语表归属的库:手动选的优先,否则会话当前库
  function glossarySource() { return manualSource() || conversationSource; }

  function loadGlossary(source) {
    if (!source) return [];
    try { return JSON.parse(localStorage.getItem(GLOSSARY_KEY + "." + source)) || []; }
    catch { return []; }
  }
  function loadMetrics(source) {
    if (!source) return [];
    try { return JSON.parse(localStorage.getItem(METRIC_KEY + "." + source)) || []; }
    catch { return []; }
  }
  function saveGlossary(source, arr) {
    if (!source) return;
    localStorage.setItem(GLOSSARY_KEY + "." + source, JSON.stringify(arr.slice(0, MAX_GLOSSARY)));
  }
  function saveMetrics(source, arr) {
    if (!source) return;
    localStorage.setItem(METRIC_KEY + "." + source, JSON.stringify(arr.slice(0, MAX_GLOSSARY)));
  }

  function isMetricEntry(text) {
    const parts = String(text || "").split(/=|＝/);
    if (parts.length < 2) return false;
    const expr = parts.slice(1).join("=");
    return /[+\-*/()]/.test(expr) || /\b(SUM|AVG|COUNT|MAX|MIN|ROUND|CASE|WHEN)\b/i.test(expr);
  }

  function customContext(source) {
    return [
      ...loadGlossary(source).map((item) => `业务术语: ${item}`),
      ...loadMetrics(source).map((item) => `计算指标: ${item}`),
      ...relationContext(source),
      ...fieldMetaContext(source),
    ].slice(0, 50);
  }

  function renderGlossary() {
    const src = glossarySource();
    glossarySourceName.textContent = src || "当前数据源";
    const terms = loadGlossary(src);
    const metrics = loadMetrics(src);
    const entries = [
      ...metrics.map((text, i) => ({ text, type: "metric", index: i })),
      ...terms.map((text, i) => ({ text, type: "term", index: i })),
    ];
    glossaryList.innerHTML = "";
    if (!src || entries.length === 0) {
      glossaryEmpty.hidden = false;
      glossaryEmpty.textContent = src
        ? "当前数据源还没有自定义术语或计算指标,在上面输入框添加。"
        : "当前数据源还没有自定义术语或计算指标。提问一次确定数据源后,或在上方手动选库,即可添加。";
    } else {
      glossaryEmpty.hidden = true;
      entries.forEach((entry) => {
        const li = document.createElement("li");
        const span = document.createElement("span");
        span.textContent = `${entry.type === "metric" ? "计算指标" : "业务术语"} · ${entry.text}`;
        const del = document.createElement("button");
        del.type = "button"; del.textContent = "×"; del.title = "删除";
        del.addEventListener("click", () => {
          if (entry.type === "metric") {
            const arr = loadMetrics(src); arr.splice(entry.index, 1); saveMetrics(src, arr);
          } else {
            const arr = loadGlossary(src); arr.splice(entry.index, 1); saveGlossary(src, arr);
          }
          renderGlossary();
          renderSchemaConsole();
          renderKbOverview();
        });
        li.appendChild(span); li.appendChild(del);
        glossaryList.appendChild(li);
      });
    }
    // 没有确定的库时禁用添加(无处归属)
    const disabled = !src;
    glossaryInput.disabled = disabled;
    glossaryAddBtn.disabled = disabled;
  }

  function addGlossaryEntry() {
    const src = glossarySource();
    const text = glossaryInput.value.trim();
    if (!src || !text) return;
    const metric = isMetricEntry(text);
    const arr = metric ? loadMetrics(src) : loadGlossary(src);
    if (arr.length >= MAX_GLOSSARY) { alert(`每个库最多 ${MAX_GLOSSARY} 条${metric ? "计算指标" : "术语"}`); return; }
    arr.push(text);
    if (metric) saveMetrics(src, arr);
    else saveGlossary(src, arr);
    glossaryInput.value = "";
    renderGlossary();
    renderSchemaConsole();
    renderKbOverview();
  }

  /* ---------------- history ---------------- */

  function loadHistory() {
    try {
      const raw = localStorage.getItem(HISTORY_KEY);
      if (!raw) return [];
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed : [];
    } catch { return []; }
  }
  function saveHistory(history) { localStorage.setItem(HISTORY_KEY, JSON.stringify(history)); }
  function clearHistory() { localStorage.removeItem(HISTORY_KEY); updateHistoryBadge(); }

  function updateHistoryBadge() {
    const n = loadHistory().length;
    historyBadge.textContent = n === 0
      ? "未开始会话"
      : `已记 ${n} 轮 · 发送最近 ${Math.min(n, MAX_HISTORY_TURNS)} 轮`;
  }

  function readJsonList(key) {
    try {
      const parsed = JSON.parse(localStorage.getItem(key) || "[]");
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }

  function writeJsonList(key, list) {
    localStorage.setItem(key, JSON.stringify(list));
  }

  function fieldMetaKey(source) {
    return FIELD_META_KEY + "." + (source || "__auto__");
  }

  function loadFieldMeta(source) {
    try {
      const parsed = JSON.parse(localStorage.getItem(fieldMetaKey(source)) || "{}");
      return parsed && typeof parsed === "object" ? parsed : {};
    } catch {
      return {};
    }
  }

  function saveFieldMeta(source, meta) {
    localStorage.setItem(fieldMetaKey(source), JSON.stringify(meta || {}));
  }

  function fieldMetaId(table, field) {
    return `${table || ""}.${field || ""}`;
  }

  function fieldMetaContext(source) {
    const meta = loadFieldMeta(source);
    return Object.entries(meta)
      .filter(([, item]) => item && (item.alias || item.desc || item.enums || item.unit || item.default_filter))
      .map(([key, item]) => {
        const parts = [`字段治理: ${key}`];
        if (item.alias) parts.push(`别名=${item.alias}`);
        if (item.desc) parts.push(`描述=${item.desc}`);
        if (item.enums) parts.push(`取值=${item.enums}`);
        if (item.unit) parts.push(`单位=${item.unit}`);
        if (item.default_filter) parts.push(`默认过滤=${item.default_filter}`);
        return parts.join("；");
      });
  }

  function relationKey(source) {
    return RELATION_KEY + "." + (source || "__auto__");
  }

  function loadRelations(source) {
    const rels = currentProfile(source).relations || [];
    return rels.map((r) => `${r.left} = ${r.right}${r.description ? " · " + r.description : ""}`);
  }

  function saveRelations(source, list) {
    localStorage.setItem(relationKey(source), JSON.stringify((list || []).slice(0, 50)));
  }

  function relationContext(source) {
    return loadRelations(source).map((item) => `表关系: ${item}`);
  }

  function loadQueryLog() {
    return readJsonList(QUERY_LOG_KEY);
  }

  function saveQueryLogItem(item) {
    const next = [item, ...loadQueryLog().filter((x) => x.id !== item.id)];
    writeJsonList(QUERY_LOG_KEY, next.slice(0, MAX_QUERY_LOG));
    renderQueryLog();
  }

  function renderQueryLog() {
    if (!historyList || !historyEmpty) return;
    const items = loadQueryLog();
    historyList.innerHTML = "";
    historyEmpty.hidden = items.length !== 0;
    items.forEach((item) => {
      const row = document.createElement("button");
      row.type = "button";
      row.className = "history-item";
      const question = document.createElement("span");
      question.className = "history-question";
      question.textContent = item.question || "";
      const meta = document.createElement("span");
      meta.className = "history-meta";
      meta.textContent = `${item.source_label || item.source || "自动识别"} · ${item.row_count || 0} 行 · ${item.elapsed_ms || 0} ms`;
      row.appendChild(question);
      row.appendChild(meta);
      row.addEventListener("click", () => {
        input.value = item.question || "";
        input.focus();
      });
      historyList.appendChild(row);
    });
  }
  const SUGGESTIONS = {
    admin: [
      "各学院在读学生人数、平均分和挂科率分别是多少？",
      "哪些课程的作业提交率最低？",
      "按课程统计缺勤率最高的前 10 门课。",
      "各课程的学习活跃度和平均分有什么关系？",
      "哪些专业的未解除学业预警人数最多？",
      "各学院获得奖助金额总额是多少？",
    ],
    academic_office: [
      "2025 年春季学期选课人数最多的 10 门课程是什么？",
      "哪些课程平均分低于 70 且作业提交率低？",
      "按学院统计本学期出勤率和缺勤率。",
      "哪些专业的学业预警人数最多？",
      "各学院课程开设数量、选课人次和平均容量是多少？",
      "按课程类型统计平均成绩、挂科率和优秀率。",
    ],
    college_manager: [
      "本学院课程平均成绩排名前 10 的课程有哪些？",
      "本学院哪些课程缺勤率和挂科率都比较高？",
      "本学院各课程的作业迟交率是多少？",
      "本学院学习活跃度最高的课程有哪些？",
      "本学院教学评价平均分最高的课程有哪些？",
      "本学院未解除学业预警学生主要集中在哪些专业？",
    ],
    teacher: [
      "我负责课程的平均成绩和挂科率是多少？",
      "我负责课程的作业提交率和迟交率是多少？",
      "我负责课程的出勤率、迟到率和缺勤率是多少？",
      "我负责课程的学习活跃度趋势如何？",
      "我负责课程的教学评价平均分是多少？",
      "我负责课程中平均分低于 70 的课程有哪些？",
    ],
    student: [
      "我本学期选择了哪些课程？",
      "我各门课程的成绩是多少？",
      "我的作业还有哪些未提交或迟交？",
      "我的课程出勤情况怎么样？",
      "我的学习平台活跃度最高的是哪些课程？",
      "我是否有未解除的学业预警？",
    ],
    teaching: [
      "各学院学生人数是多少？",
      "2025 年春季学期挂科率最高的 5 门课程是什么？",
      "哪些课程的作业提交率最低？",
      "按课程统计缺勤率最高的前 10 门课。",
      "各课程的学习活跃度和平均分有什么关系？",
      "哪些专业的未解除学业预警人数最多？",
    ],
    auto: [
      "各学院学生人数是多少？",
      "本学期开设了多少门课程？",
      "2025 年春季学期选课人数最多的 10 门课程是什么？",
      "哪些课程的作业提交率最低？",
      "按课程统计缺勤率最高的前 10 门课。",
      "哪些专业的未解除学业预警人数最多？",
    ],
  };


  function suggestionSource() {
    return manualSource() || conversationSource || "auto";
  }

  function renderSuggestions() {
    if (!suggestionList) return;
    const src = suggestionSource();
    const role = currentUser && currentUser.role;
    const list = SUGGESTIONS[role] || SUGGESTIONS[src] || SUGGESTIONS.auto;
    if (suggestionRoleLabel) {
      suggestionRoleLabel.textContent = currentUser ? `· ${currentUser.role_label}` : "";
    }
    const groups = [
      ["成绩质量", ["成绩", "平均分", "挂科", "及格", "分布", "低于"]],
      ["教学运行", ["开设", "教学班", "选课", "课程类型", "授课", "人次"]],
      ["学习过程", ["作业", "考勤", "出勤", "缺勤", "迟交", "活跃度"]],
      ["风险反馈", ["预警", "评价", "风险", "奖助"]],
      ["常用", []],
    ].map(([title, words]) => ({ title, words, items: [] }));
    list.forEach((text) => {
      const group = groups.find((g) => g.words.some((w) => text.includes(w))) || groups[groups.length - 1];
      group.items.push(text);
    });
    suggestionList.innerHTML = "";
    groups.filter((g) => g.items.length).forEach((group) => {
      const section = document.createElement("div");
      section.className = "suggestion-group";
      section.innerHTML = `<div class="suggestion-group-title">${escapeHtml(group.title)}</div>`;
      const body = document.createElement("div");
      body.className = "suggestion-group-body";
      group.items.forEach((text) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "suggestion-chip";
        btn.textContent = text;
        btn.addEventListener("click", () => {
          input.value = text;
          input.focus();
        });
        body.appendChild(btn);
      });
      section.appendChild(body);
      suggestionList.appendChild(section);
    });
  }

  /* ---------------- routed source ---------------- */

  function showRoutedSource(data) {
    if (!data || !data.source) { hide(routedSource); return; }
    const label = data.source_label || data.source;
    routedText.textContent = data.auto_routed
      ? `已自动识别并使用「${label}」${data.route_reason ? " · " + data.route_reason : ""}`
      : `当前使用「${label}」${data.route_reason ? " · " + data.route_reason : ""}`;
    show(routedSource);
  }

  /* ---------------- SQL highlight ---------------- */

  function highlightSQL(sql) {
    return sql
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/('.*?')/g, '<span class="sql-str">$1</span>')
      .replace(/\b(SELECT|FROM|WHERE|JOIN|LEFT|RIGHT|INNER|OUTER|CROSS|ON|AND|OR|NOT|IN|LIKE|BETWEEN|IS|NULL|AS|GROUP\s+BY|ORDER\s+BY|HAVING|LIMIT|OFFSET|UNION|ALL|DISTINCT|CASE|WHEN|THEN|ELSE|END|WITH|OVER|PARTITION\s+BY|ASC|DESC|USING)\b/gi, '<span class="sql-kw">$1</span>')
      .replace(/\b(\d+\.?\d*)\b/g, '<span class="sql-num">$1</span>')
      .replace(/\b(COUNT|SUM|AVG|MAX|MIN|ROW_NUMBER|RANK|DENSE_RANK|SUBSTR|SUBSTRING|COALESCE|ROUND|CAST|DATE|STRFTIME|LOWER|UPPER|LENGTH)\s*\(/gi, '<span class="sql-fn">$1</span>(');
  }

  /* ---------------- render ---------------- */

  function isNumeric(v) {
    if (v === null || v === "" || typeof v === "boolean") return false;
    return !isNaN(parseFloat(v)) && isFinite(v);
  }

  function renderTable(columns, rows, sources) {
    thead.innerHTML = "";
    tbody.innerHTML = "";
    const hasSources = Array.isArray(sources) && sources.length === columns.length;

    const trHead = document.createElement("tr");
    for (let i = 0; i < columns.length; i++) {
      const th = document.createElement("th");
      const alias = columns[i];
      const src = hasSources ? (sources[i] || "") : "";
      th.textContent = alias;
      if (src && src !== alias) {
        const small = document.createElement("small");
        small.textContent = src;
        th.appendChild(small);
      }
      trHead.appendChild(th);
    }
    thead.appendChild(trHead);

    rows.forEach((row, i) => {
      const tr = document.createElement("tr");
      tr.style.animation = `fadeInUp .3s ${Math.min(i, 12) * 40}ms ease both`;
      for (const cell of row) {
        const td = document.createElement("td");
        if (cell === null) {
          td.textContent = "NULL";
          td.style.color = "#95a1b2";
        } else {
          td.textContent = String(cell);
          if (isNumeric(cell)) td.className = "num";
        }
        tr.appendChild(td);
      }
      tbody.appendChild(tr);
    });

    emptyHint.hidden = rows.length !== 0;
  }

  function confidenceBadge(c, d) {
    const cls = c >= 80 ? "conf-high" : c >= 50 ? "conf-mid" : "conf-low";
    let tip = "AI 对本次回答可信度的估算,仅供参考";
    if (d) tip = `数据完整度 ${d.retrieval}% · 结果匹配度 ${d.correctness}%${d.reason ? " — " + d.reason : ""}(AI 估算,仅供参考)`;
    const tipAttr = tip.replace(/"/g, "&quot;");
    return `<span class="confidence ${cls}" title="${tipAttr}">结果可信度 ${c}%</span>`;
  }

  function renderMeta(data) {
    const parts = [];
    if (typeof data.row_count === "number") parts.push(`${data.row_count} 行`);
    if (typeof data.elapsed_ms === "number") parts.push(`${data.elapsed_ms} ms`);
    let html = parts.map((s) => `<span>${s}</span>`).join("");
    if (data.truncated) html += '<span class="warn">结果已截断</span>';
    // confidence 多在结果渲染后由 fetchConfidence 异步补上;若响应已直接带分(兼容),这里也渲染。
    if (typeof data.confidence === "number") html += confidenceBadge(data.confidence, data.confidence_detail);
    sqlMeta.innerHTML = html;
  }

  function renderResultSummary(data) {
    if (!resultSummary) return;
    const columns = data.columns || [];
    const rows = data.rows || [];
    if (!columns.length) {
      resultSummary.innerHTML = "";
      return;
    }
    const rowCount = typeof data.row_count === "number" ? data.row_count : rows.length;
    const bits = [`共返回 ${rowCount} 行、${columns.length} 列`];
    if (data.truncated) bits.push("结果已按安全上限截断");
    const exp = data.explanation || {};
    if (exp.summary) bits.push(exp.summary);
    (exp.default_filters || []).slice(0, 3).forEach((x) => bits.push(`口径: ${x}`));
    (exp.metrics || []).slice(0, 2).forEach((x) => bits.push(`指标: ${x}`));
    (exp.relations || []).slice(0, 2).forEach((x) => bits.push(`关系: ${x}`));
    const first = rows[0] || [];
    const numericIndex = columns.findIndex((_, idx) => rows.some((r) => isNumeric(r[idx])));
    if (numericIndex >= 0) {
      const values = rows.map((r) => Number(r[numericIndex])).filter((v) => Number.isFinite(v));
      if (values.length) {
        const max = Math.max(...values);
        const min = Math.min(...values);
        bits.push(`${columns[numericIndex]} 范围 ${min} - ${max}`);
      }
    }
    if (first.length) {
      const preview = columns.slice(0, 3).map((c, i) => `${c}: ${first[i] == null ? "NULL" : first[i]}`).join("；");
      bits.push(`首行 ${preview}`);
    }
    resultSummary.innerHTML = bits.map((x) => `<span>${escapeHtml(x)}</span>`).join("");
  }

  async function fetchConfidence(data) {
    if (!data.judge_id) return;
    const pending = document.createElement("span");
    pending.className = "confidence conf-pending";
    pending.title = "正在评估本次回答的可信度";
    pending.textContent = "结果可信度评估中";
    sqlMeta.appendChild(pending);
    try {
      for (let attempt = 0; attempt < 45; attempt++) {
        const jd = await api.judge(data.judge_id);
        if (!pending.isConnected) return;
        if (typeof jd.confidence === "number") {
          pending.outerHTML = confidenceBadge(jd.confidence, jd.confidence_detail);
          appendProcessLog(`可信度评估完成: ${jd.confidence}%。`, "done");
          queueLowConfidenceIfNeeded(data, jd.confidence, jd.confidence_detail);
          return;
        }
        if (jd.status === "failed") {
          pending.className = "confidence conf-pending";
          pending.title = "裁判模型调用失败或输出无法解析,不影响本次查询结果";
          pending.textContent = "可信度评估失败";
          appendProcessLog("可信度评估失败,不影响当前查询结果。", "failed");
          return;
        }
        if (jd.status === "missing") {
          pending.className = "confidence conf-pending";
          pending.title = "评估任务已过期或服务重启后丢失,不影响本次查询结果";
          pending.textContent = "可信度评估过期";
          appendProcessLog("可信度评估任务已过期,查询结果仍可使用。", "failed");
          return;
        }
        await new Promise((resolve) => setTimeout(resolve, 1000));
      }
      pending.className = "confidence conf-pending";
      pending.title = "裁判模型仍未返回,可能是模型响应慢或网络较慢;不影响本次查询结果";
      pending.textContent = "可信度评估仍在后台运行";
      appendProcessLog("可信度评估仍在后台运行,你可以先查看当前查询结果。", "active");
    } catch (e) {
      if (!pending.isConnected) return;
      pending.className = "confidence conf-pending";
      pending.title = "可信度评估请求失败,不影响本次查询结果";
      pending.textContent = "可信度评估失败";
      appendProcessLog("可信度评估请求失败,不影响当前查询结果。", "failed");
    }
  }

  async function queueLowConfidenceIfNeeded(data, confidence, detail) {
    const settings = governanceView ? governanceView.getSettings() : {};
    const threshold = Number((settings && settings.low_confidence_threshold) || 70);
    if (confidence >= threshold || !data || !data.source) return;
    try {
      await api.queueLowConfidence({
        confidence,
        confidence_detail: detail || {},
        question: currentResult && currentResult.question || "",
        sql: data.sql || "",
        source: data.source || "",
        source_label: data.source_label || "",
        reason: detail && detail.reason || "",
      });
    } catch {}
  }

  function tableToText(data, sep) {
    if (!data || !Array.isArray(data.columns)) return "";
    const esc = (value) => {
      let text = value == null ? "" : String(value);
      if (/^[=+\-@]/.test(text)) text = "'" + text;
      if (sep === "," && /[",\n]/.test(text)) return `"${text.replace(/"/g, '""')}"`;
      return text;
    };
    const lines = [data.columns.map(esc).join(sep)];
    (data.rows || []).forEach((row) => lines.push(row.map(esc).join(sep)));
    return lines.join("\n");
  }

  function downloadCsv() {
    if (!currentResult) return;
    const blob = new Blob(["\ufeff" + tableToText(currentResult, ",")], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `nl2sql-result-${Date.now()}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  function copyTable() {
    if (!currentResult) return;
    navigator.clipboard.writeText(tableToText(currentResult, "\t")).catch(() => {});
  }

  function saveCurrentQuery() {
    if (!currentResult) return null;
    const saved = readJsonList(SAVED_QUERY_KEY);
    const item = {
      id: currentResult.id || String(Date.now()),
      question: currentResult.question,
      sql: currentResult.sql,
      source: currentResult.source,
      source_label: currentResult.source_label,
      use_few_shot: true,
      saved_at: new Date().toISOString(),
    };
    writeJsonList(SAVED_QUERY_KEY, [item, ...saved.filter((x) => x.id !== item.id)].slice(0, 50));
    renderKbList();
    renderKbOverview();
    if (saveQueryBtn) {
      const old = saveQueryBtn.textContent;
      saveQueryBtn.textContent = "已保存";
      setTimeout(() => { saveQueryBtn.textContent = old; }, 1200);
    }
    return item;
  }

  async function saveFeedback(kind, reason, category) {
    if (!currentResult) return;
    const item = {
      id: String(Date.now()),
      kind,
      reason: reason || "",
      category: category || "",
      question: currentResult.question,
      sql: currentResult.sql,
      source: currentResult.source,
      source_label: currentResult.source_label,
      explanation: currentResult.explanation || {},
      created_at: new Date().toISOString(),
    };
    writeJsonList(FEEDBACK_KEY, [item, ...readJsonList(FEEDBACK_KEY)].slice(0, 100));
    try {
      const saved = await api.saveFeedback(item);
      feedbackCache = [saved.item, ...feedbackCache.filter((x) => x.id !== saved.item.id)];
      currentResult.feedback = saved.item;
      currentResult.feedbackKind = kind;
    } catch {}
    renderKbOverview();
    updateFeedbackButtons();
  }

  async function clearCurrentFeedback() {
    if (!currentResult || !currentResult.feedback) return;
    const id = currentResult.feedback.id;
    currentResult.feedback = null;
    currentResult.feedbackKind = "";
    feedbackCache = feedbackCache.filter((x) => x.id !== id);
    try { await api.deleteFeedback(id); } catch {}
    renderKbOverview();
    updateFeedbackButtons();
  }

  function updateFeedbackButtons() {
    const kind = currentResult && currentResult.feedbackKind;
    if (confirmGoodBtn) {
      confirmGoodBtn.classList.toggle("active", kind === "correct");
      confirmGoodBtn.textContent = kind === "correct" ? "取消点赞" : "结果正确";
      confirmGoodBtn.title = kind === "correct" ? "已提交用例沉淀审核，再次点击可取消" : "提交到治理队列，审核通过后沉淀为标准样例";
    }
    if (reportBadBtn) {
      reportBadBtn.classList.toggle("active", kind === "incorrect");
      reportBadBtn.textContent = kind === "incorrect" ? "取消点踩" : "反馈错误";
    }
  }

  async function confirmCurrentResult() {
    if (!currentResult) return;
    if (currentResult.feedbackKind === "correct") {
      await clearCurrentFeedback();
      return;
    }
    if (currentResult.feedbackKind === "incorrect") {
      await clearCurrentFeedback();
    }
    await saveFeedback("correct", "用户确认结果正确，建议沉淀为标准问法样例", "confirmed_example");
  }

  async function reportCurrentResult() {
    if (!currentResult) return;
    if (currentResult.feedbackKind === "incorrect") {
      await clearCurrentFeedback();
      return;
    }
    openFeedbackModal();
  }

  function openFeedbackModal() {
    if (!feedbackModal) return;
    if (feedbackReason) feedbackReason.value = "";
    feedbackModal.hidden = false;
    if (feedbackReason) feedbackReason.focus();
  }

  function closeFeedbackModal() {
    if (feedbackModal) feedbackModal.hidden = true;
  }

  async function submitFeedbackModal() {
    if (!currentResult) return;
    const reason = (feedbackReason && feedbackReason.value || "").trim();
    const category = (feedbackCategory && feedbackCategory.value || "其他").trim();
    if (!reason) {
      if (feedbackReason) feedbackReason.focus();
      return;
    }
    if (currentResult.feedbackKind === "correct") {
      await clearCurrentFeedback();
    }
    await saveFeedback("incorrect", reason, category);
    closeFeedbackModal();
  }

  function textTokens(text) {
    const s = String(text || "").toLowerCase();
    const words = s.match(/[a-z0-9_]+|[\u4e00-\u9fa5]/g) || [];
    const grams = [];
    for (let i = 0; i < s.length - 1; i++) {
      const g = s.slice(i, i + 2).trim();
      if (/[\u4e00-\u9fa5]{2}/.test(g)) grams.push(g);
    }
    return new Set([...words, ...grams]);
  }

  function similarityScore(a, b) {
    const ta = textTokens(a);
    const tb = textTokens(b);
    if (!ta.size || !tb.size) return 0;
    let hit = 0;
    ta.forEach((x) => { if (tb.has(x)) hit += 1; });
    return hit / Math.sqrt(ta.size * tb.size);
  }

  function savedFewShotsForRequest(question) {
    const src = manualSource() || conversationSource || currentKbSource();
    const remote = standardExamplesCache[profileKey(src)] || [];
    const base = remote.length ? remote.map((x) => ({ ...x, use_few_shot: x.enabled !== false })) : readJsonList(SAVED_QUERY_KEY);
    return base
      .filter((item) => item.question && item.sql && item.use_few_shot !== false)
      .map((item) => ({ ...item, _score: similarityScore(question, item.question) }))
      .sort((a, b) => b._score - a._score)
      .filter((item, i) => item._score > 0 || i < 3)
      .slice(0, 8)
      .map((item) => ({
        question: item.question,
        sql: item.sql,
        source: item.source || null,
        source_label: item.source_label || null,
      }));
  }

  function drawChart() {
    if (!chartCanvas || !chartEmpty || !currentResult) return;
    const columns = currentResult.columns || [];
    const rows = (currentResult.rows || []).slice(0, 12);
    const numericIndex = columns.findIndex((_, idx) => rows.some((r) => isNumeric(r[idx])));
    const labelIndex = columns.findIndex((_, idx) => idx !== numericIndex && rows.some((r) => r[idx] != null && !isNumeric(r[idx])));
    const ctx = chartCanvas.getContext("2d");
    ctx.clearRect(0, 0, chartCanvas.width, chartCanvas.height);
    if (numericIndex < 0 || labelIndex < 0 || rows.length === 0) {
      chartCanvas.hidden = true;
      chartEmpty.hidden = false;
      return;
    }
    chartCanvas.hidden = false;
    chartEmpty.hidden = true;
    const width = chartCanvas.width = chartCanvas.clientWidth || chartCanvas.parentElement.clientWidth;
    const height = chartCanvas.height = 220;
    const values = rows.map((r) => Number(r[numericIndex]) || 0);
    const max = Math.max(...values.map((v) => Math.abs(v)), 1);
    const pad = 34;
    const gap = 8;
    const barW = Math.max(12, (width - pad * 2 - gap * (rows.length - 1)) / rows.length);
    ctx.font = "12px JetBrains Mono, monospace";
    ctx.fillStyle = "#4a4540";
    ctx.fillText(`${columns[numericIndex]} by ${columns[labelIndex]}`, pad, 18);
    rows.forEach((row, i) => {
      const value = Number(row[numericIndex]) || 0;
      const h = Math.max(2, Math.abs(value) / max * 140);
      const x = pad + i * (barW + gap);
      const y = height - 44 - h;
      const grad = ctx.createLinearGradient(0, y, 0, height - 44);
      grad.addColorStop(0, "#d97a66");
      grad.addColorStop(1, "#c74e3a");
      ctx.fillStyle = grad;
      ctx.fillRect(x, y, barW, h);
      ctx.fillStyle = "#141210";
      ctx.fillText(String(value).slice(0, 8), x, y - 6);
      ctx.fillStyle = "#a09890";
      ctx.fillText(String(row[labelIndex]).slice(0, 8), x, height - 20);
    });
  }

  function toggleChart() {
    if (!chartPanel) return;
    chartPanel.hidden = !chartPanel.hidden;
    if (!chartPanel.hidden) drawChart();
    if (chartToggleBtn) chartToggleBtn.textContent = chartPanel.hidden ? "图表视图" : "收起图表";
  }

  function setSqlExpanded(expanded) {
    if (!sqlBlock) return;
    sqlBlock.classList.toggle("is-collapsed", !expanded);
    if (sqlToggle) sqlToggle.textContent = expanded ? "收起 SQL" : "展开 SQL";
  }

  /* ---------------- data fetching ---------------- */

  async function loadProfile(source) {
    if (!source) return emptyProfile();
    const key = profileKey(source);
    if (profileCache[key]) return profileCache[key];
    try {
      const data = await api.profile(source);
      profileCache[key] = data.profile || emptyProfile();
    } catch {
      profileCache[key] = emptyProfile();
    }
    return profileCache[key];
  }

  async function saveProfile(source, profile) {
    if (!source) return;
    const data = await api.saveProfile(source, profile);
    profileCache[profileKey(source)] = data.profile || profile;
    schemaCache = {};
    await loadQuality(source);
    await loadProfileVersions(source);
    await loadSchema(source);
  }

  async function loadFeedback(source) {
    try {
      const data = await api.feedback(source);
      feedbackCache = data.items || [];
    } catch {
      feedbackCache = readJsonList(FEEDBACK_KEY);
    }
    return feedbackCache;
  }

  async function loadQuality(source) {
    if (!source) return {};
    try {
      const data = await api.quality(source);
      qualityCache[profileKey(source)] = data.report || {};
    } catch {
      qualityCache[profileKey(source)] = {};
    }
    return qualityCache[profileKey(source)];
  }

  async function loadStandardExamples(source) {
    if (!source) return [];
    try {
      const data = await api.examples(source);
      standardExamplesCache[profileKey(source)] = data.items || [];
    } catch {
      standardExamplesCache[profileKey(source)] = savedExamplesForSource(source);
    }
    return standardExamplesCache[profileKey(source)];
  }

  async function saveStandardExample(source, item) {
    if (!source) return null;
    const data = await api.saveExample(source, item);
    await loadStandardExamples(source);
    return data.item;
  }

  async function deleteStandardExample(source, id) {
    if (!source || !id) return;
    await api.deleteExample(source, id);
    await loadStandardExamples(source);
  }

  async function loadProfileVersions(source) {
    if (!source) return [];
    try {
      const data = await api.profileVersions(source);
      profileVersionsCache[profileKey(source)] = data.items || [];
    } catch {
      profileVersionsCache[profileKey(source)] = [];
    }
    return profileVersionsCache[profileKey(source)];
  }

  async function refreshSourceGovernanceDependencies(source) {
    profileCache[profileKey(source)] = null;
    await Promise.allSettled([
      loadProfile(source),
      loadStandardExamples(source),
      loadQuality(source),
      loadProfileVersions(source),
      loadSchema(source),
    ]);
  }

  async function publishCurrentProfile() {
    const src = currentKbSource();
    if (!src) return;
    const settings = governanceView ? governanceView.getSettings() : {};
    const values = await openGovernanceModal({
      title: "发布 Profile",
      kicker: sourceLabel(src),
      fields: [
        { name: "label", label: "发布版本名称", value: "发布版本", required: true },
        { name: "description", label: "发布说明", type: "textarea", required: settings && settings.require_publish_note !== false },
      ],
      submitText: settings && settings.review_required_for_publish ? "提交审核" : "发布",
    });
    if (!values) return;
    let data;
    try {
      data = await api.publishProfile(src, { label: values.label, description: values.description });
    } catch (e) {
      const msg = e.message || "发布失败";
      alert(msg);
      return;
    }
    if (data.review_required) {
      await loadFeedback();
      if (governanceView) governanceView.setSelectedReviewItemId(data.item && data.item.id || "");
      showView("governance-queue-view");
      if (llmDraftBtn) {
        const old = llmDraftBtn.textContent;
        llmDraftBtn.textContent = "已提交审核";
        setTimeout(() => { llmDraftBtn.textContent = old; }, 1400);
      }
      return;
    }
    await loadProfileVersions(src);
    renderProfileVersions(src);
    if (llmDraftBtn) {
      const old = llmDraftBtn.textContent;
      llmDraftBtn.textContent = "已发布";
      setTimeout(() => { llmDraftBtn.textContent = old; }, 1400);
    }
  }

  async function loadSchema(forceSource) {
    const src = forceSource || manualSource();
    const key = schemaKey(src);
    schemaLoading.add(key);
    renderKbList();
    try {
      const data = await api.schema(src);
      const shouldUpdateSchemaText = schemaKey(activeSourceName()) === key || (!activeSourceName() && key === "__auto__");
      schemaCache[key] = data;
      if (src) {
        await loadProfile(src);
        await Promise.allSettled([loadQuality(src), loadStandardExamples(src), loadProfileVersions(src)]);
      }
      if (shouldUpdateSchemaText) {
        schemaText.textContent = data.ddl;
      }
      renderKbList();
      renderKbOverview();
      renderSchemaConsole();
    } catch {
      const shouldUpdateSchemaText = schemaKey(activeSourceName()) === key || (!activeSourceName() && key === "__auto__");
      if (shouldUpdateSchemaText) schemaText.textContent = "(加载失败)";
    } finally {
      schemaLoading.delete(key);
      renderKbList();
    }
  }

  async function loadAllSchemas() {
    if (!availableSources.length) return;
    const tasks = availableSources
      .filter((s) => s && s.name && !schemaCache[schemaKey(s.name)] && !schemaLoading.has(schemaKey(s.name)))
      .map((s) => loadSchema(s.name));
    if (tasks.length) await Promise.allSettled(tasks);
  }

  function renderSourceTags(sources) {
    // 第一项始终是「自动识别」(value 为空 => 后端按问题路由)
    sourceTags.innerHTML = "";
    const autoTag = document.createElement("span");
    autoTag.className = `source-tag${selectedSource ? "" : " active"}`;
    autoTag.dataset.src = "";
    autoTag.textContent = "🤖 自动识别";
    sourceTags.appendChild(autoTag);

    for (const s of sources) {
      const tag = document.createElement("span");
      tag.className = `source-tag${selectedSource === s.name ? " active" : ""}`;
      tag.dataset.src = s.name;
      tag.textContent = `${s.label} · ${s.dialect}`;
      sourceTags.appendChild(tag);
    }

    sourceTags.querySelectorAll(".source-tag").forEach((tag) => {
      tag.addEventListener("click", () => {
        if (tag.classList.contains("active")) return;
        setManualSource(tag.dataset.src || "");
        return;
        sourceTags.querySelectorAll(".source-tag").forEach((t) => t.classList.remove("active"));
        tag.classList.add("active");
        selectedSource = tag.dataset.src || "";
        // 手动切换数据源 => 开启新会话:清历史、清会话已路由的库
        conversationSource = null;
        if (loadHistory().length > 0) clearHistory();
        hide(routedSource);
        hideAllStateCards();
        loadSchema();
        renderSuggestions();
        renderGlossary();   // 切到该库的术语表(选「自动识别」时 src 为空,显示提示)
      });
    });
  }

  async function loadAuthOptions() {
    try {
      const data = await api.authOptions();
      if (loginDomainList) {
        loginDomainList.innerHTML = "";
        (data.users || []).forEach((user) => {
          const card = document.createElement("div");
          card.className = "login-domain-card";
          card.innerHTML = `
            <b>${escapeHtml(user.display_name)} · ${escapeHtml(user.role_label)}</b>
            <span>${escapeHtml(user.description || "")}</span>
            <code>${escapeHtml(user.username)} / 123456</code>
          `;
          loginDomainList.appendChild(card);
        });
      }
    } catch {
      if (loginError) loginError.textContent = "登录选项加载失败，请确认后端服务已启动。";
    }
  }

  function setAuthSession(payload) {
    currentUser = payload.user;
    localStorage.setItem(AUTH_TOKEN_KEY, payload.token);
    localStorage.setItem(AUTH_USER_KEY, JSON.stringify(payload.user || {}));
    dashboardCache = null;
    domainSettingsCache = null;
    schemaCache = {};
    profileCache = {};
    qualityCache = {};
    standardExamplesCache = {};
    profileVersionsCache = {};
    conversationSource = null;
    selectedSource = "teaching";
    selectedKb = "teaching";
    applyUserUi();
    showWorkspace();
  }

  async function restoreAuthSession() {
    const token = localStorage.getItem(AUTH_TOKEN_KEY);
    if (!token) return false;
    try {
      const payload = await api.session();
      setAuthSession(payload);
      return true;
    } catch {
      localStorage.removeItem(AUTH_TOKEN_KEY);
      localStorage.removeItem(AUTH_USER_KEY);
      return false;
    }
  }

  async function bootWorkspace() {
    applyUserUi();
    await loadSources();
    await loadDashboard(true);
    await loadDomainSettings(true);
    showView(preferredHomeView());
  }

  async function loadSources() {
    try {
      const data = await api.sources();
      availableSources = data.sources || [];
      if (!selectedSource && availableSources.some((s) => s.name === "teaching")) {
        selectedSource = "teaching";
        selectedKb = "teaching";
      }
      renderSourceTags(availableSources);
      if (governanceView) governanceView.renderSourceOptions();
      renderSuggestions();
      if (governanceView) await governanceView.loadSettings();
      await loadFeedback();
      renderKbList();
      renderKbOverview();
      renderSchemaConsole();
      loadAllSchemas();
    } catch {
      sourceTags.innerHTML = '<span class="source-tag active">（数据源加载失败）</span>';
    }
  }

  /* ---------------- process log ---------------- */
  // 后端当前不是流式返回,这里按真实流水线阶段追加过程日志,让用户知道系统还在推进。
  let progressTimers = [];
  let progressHeartbeat = null;
  const PROGRESS_AUTO = [
    "接收问题,准备识别可用数据源和当前角色权限。",
    "根据问题和会话上下文判断要查询的教学数据域。",
    "读取当前账号的数据范围,过滤不可访问的表和敏感字段。",
    "检索相关表、字段、指标口径和业务术语。",
    "组织数据库结构上下文,准备生成查询语句。",
    "正在调用模型生成 SQL,同时进行安全约束检查。",
    "如果 SQL 校验未通过,系统会自动尝试修复一次。",
    "正在只读执行查询,并限制最大返回行数。",
  ];
  const PROGRESS_MANUAL = [
    "接收问题,使用当前手动选择的数据源。",
    "读取当前账号的数据范围,过滤不可访问的表和敏感字段。",
    "检索相关表、字段、指标口径和业务术语。",
    "组织数据库结构上下文,准备生成查询语句。",
    "正在调用模型生成 SQL,同时进行安全约束检查。",
    "如果 SQL 校验未通过,系统会自动尝试修复一次。",
    "正在只读执行查询,并限制最大返回行数。",
  ];

  function clearProgressTimers() {
    progressTimers.forEach((t) => clearTimeout(t));
    progressTimers = [];
    if (progressHeartbeat) {
      clearInterval(progressHeartbeat);
      progressHeartbeat = null;
    }
  }

  function appendProcessLog(text, kind) {
    if (!processLog) return;
    const row = document.createElement("div");
    row.className = `process-line ${kind || ""}`.trim();
    const time = new Date().toLocaleTimeString("zh-CN", { hour12: false });
    row.innerHTML = `<span>${escapeHtml(time)}</span><b>${escapeHtml(text)}</b>`;
    processLog.appendChild(row);
    processLog.scrollTop = processLog.scrollHeight;
  }

  function startProgress(isAuto) {
    clearProgressTimers();
    const stages = isAuto ? PROGRESS_AUTO : PROGRESS_MANUAL;
    if (processLog) processLog.innerHTML = "";
    progressBox.classList.remove("done", "failed");
    show(progressBox);
    appendProcessLog("已提交查询,系统开始处理。", "active");
    let delay = 260;
    stages.forEach((text, i) => {
      progressTimers.push(setTimeout(() => {
        appendProcessLog(text, "active");
      }, delay));
      delay += 850 + i * 260;
    });
    progressTimers.push(setTimeout(() => {
      const waitingMessages = [
        "查询仍在处理中，系统正在等待模型或数据库返回。",
        "正在检查返回行数和字段权限，避免展示越权或过量数据。",
        "正在保持请求连接，请不要重复点击查询按钮。",
        "复杂问题可能正在进行 SQL 校验、修复或二次执行。",
        "正在整理结果元数据，完成后会立即渲染表格。",
      ];
      let waitingIndex = 0;
      appendProcessLog("执行时间略长，已切换为持续状态同步。", "active");
      progressHeartbeat = setInterval(() => {
        appendProcessLog(waitingMessages[waitingIndex % waitingMessages.length], "active");
        waitingIndex += 1;
      }, 2800);
    }, delay + 900));
  }

  function finishProgress() {
    clearProgressTimers();
    progressBox.classList.remove("failed");
    progressBox.classList.add("done");
    appendProcessLog("查询执行完成,正在渲染结果。", "done");
  }

  function failProgress() {
    clearProgressTimers();
    if (progressBox && !progressBox.hidden) {
      progressBox.classList.remove("done");
      progressBox.classList.add("failed");
      appendProcessLog("流程已停止,请查看错误提示。", "failed");
    }
  }

  /* ---------------- query ---------------- */

  async function executeQuery() {
    const question = input.value.trim();
    if (!question) return;

    hideAllStateCards();
    submit.disabled = true;
    const submitLabel = submit.innerHTML;
    submit.innerHTML = '查询中<span class="arrow">…</span>';

    const history = loadHistory().slice(-MAX_HISTORY_TURNS);
    // source = 手动选定的库(硬锁);current_source = 本会话当前库(给后端路由当提示,
    // 让追问留在原库、换话题能切库)。自动模式下 source 为空,后端每轮按问题+历史重新路由。
    const source = manualSource();
    const currentSource = conversationSource;
    const userGlossary = customContext(glossarySource());  // 当前库的自定义术语和计算指标,自动带上
    const fewShots = savedFewShotsForRequest(question);

    startProgress(!source);   // 手动锁库时跳过"判断数据源"阶段

    try {
      const data = await api.ask({ question, history, source, current_source: currentSource,
                                  user_glossary: userGlossary, few_shots: fewShots });
      finishProgress();   // 网络往返结束,进度补满收起(后续分支只管渲染)

      // 透明展示本次实际使用的数据源
      showRoutedSource(data);
      if (data.source_label || data.source) {
        appendProcessLog(`已确定数据源: ${data.source_label || data.source}${data.auto_routed ? "（自动路由）" : "（手动选择）"}。`, "done");
      }
      if (data.source) {
        // 自动路由切换了数据源 => 换库即换话题,清掉旧库的历史,避免把上一个库的问答
        // 当上下文喂给新库(跨库上下文污染)。同库追问不受影响。
        if (conversationSource && data.source !== conversationSource) {
          clearHistory();
          updateHistoryBadge();
        }
        conversationSource = data.source;
        loadSchema(data.source);
        renderSuggestions();
        renderGlossary();   // 数据源确定/切换后,刷新术语表面板到对应库
      }

      if (data.clarify) {
        appendProcessLog("模型判断还需要补充信息,已暂停执行并等待澄清。", "failed");
        // 澄清时彻底清掉上一轮的 SQL/结果内容,避免和澄清卡片并存(连隐藏的 DOM 残留也清)
        sqlBlock.classList.remove("visible");
        resultWrap.classList.remove("visible");
        sqlCode.textContent = "";
        tbody.innerHTML = "";
        sqlMeta.innerHTML = "";
        clarifyMsg.textContent = data.clarify;
        show(clarifyBox);
        const next = loadHistory();
        next.push({ question, sql: `CLARIFY: ${data.clarify}`, kind: "clarify" });
        saveHistory(next.slice(-MAX_HISTORY_TURNS * 2));
        updateHistoryBadge();
        input.value = "";
        input.focus();
        return;
      }

      if (data.sql) {
        appendProcessLog("SQL 已生成并通过安全校验,准备展示执行语句。", "done");
        sqlCode.innerHTML = highlightSQL(data.sql);
        sqlBlock.classList.add("visible");
        setSqlExpanded(false);
      }

      if (data.error) {
        appendProcessLog(`执行返回错误: ${data.error}`, "failed");
        errorMsg.textContent = data.error;
        show(errorBox);
      } else {
        renderMeta(data);
        const rowCount = typeof data.row_count === "number" ? data.row_count : (data.rows || []).length;
        appendProcessLog(`查询完成,返回 ${rowCount} 行,耗时 ${data.elapsed_ms || 0} ms。`, "done");
        if (data.judge_id) appendProcessLog("可信度评估已提交后台,结果出来后会自动补充。", "active");
        if (resultTitle) resultTitle.textContent = `查询结果 · ${rowCount} 行`;
        currentResult = { ...data, question, id: String(Date.now()), feedback: null, feedbackKind: "" };
        updateFeedbackButtons();
        lastTrace = {
          question,
          source: data.source,
          source_label: data.source_label,
          auto_routed: data.auto_routed,
          route_reason: data.route_reason,
          sql: data.sql,
          columns: (data.columns || []).length,
          row_count: rowCount,
          elapsed_ms: data.elapsed_ms,
          judge_id: data.judge_id,
          explanation: data.explanation || {},
          trace: data.trace || {},
        };
        if (chartPanel) chartPanel.hidden = true;
        if (chartToggleBtn) chartToggleBtn.textContent = "图表视图";
        renderResultSummary(data);
        renderTable(data.columns, data.rows, data.column_sources);
        resultWrap.classList.add("visible");
        renderKbOverview();
        renderDebugSteps();
        fetchConfidence(data);   // 结果已出,异步补准确率勋章(不阻塞结果显示)

        const isPlaceholder = data.columns.length === 1 && data.columns[0] === "error";
        if (data.sql && !isPlaceholder) {
          const next = loadHistory();
          next.push({ question, sql: data.sql, kind: "sql" });
          saveHistory(next.slice(-MAX_HISTORY_TURNS * 2));
          updateHistoryBadge();
          saveQueryLogItem({
            id: currentResult.id,
            question,
            sql: data.sql,
            source: data.source,
            source_label: data.source_label,
            row_count: rowCount,
            elapsed_ms: data.elapsed_ms,
            created_at: new Date().toISOString(),
          });
          renderKbList();
          renderKbOverview();
        }
      }
    } catch (err) {
      failProgress();
      appendProcessLog(`请求失败: ${err.message}`, "failed");
      errorMsg.textContent = `请求失败: ${err.message}`;
      show(errorBox);
    } finally {
      submit.disabled = false;
      submit.innerHTML = submitLabel;
    }
  }

  governanceView = window.NL2SQLGovernanceView.create({
    availableSources: () => availableSources,
    sourceLabel,
    loadFeedback,
    renderKbOverview,
    renderSchemaConsole,
    refreshSource: refreshSourceGovernanceDependencies,
  });

  /* ---------------- events ---------------- */

  navTargets.forEach((btn) => {
    btn.addEventListener("click", () => showView(btn.dataset.viewTarget));
  });
  document.querySelectorAll(".dashboard-ask-btn").forEach((btn) => {
    btn.addEventListener("click", () => askDashboardQuestion(btn.dataset.question || ""));
  });
  if (dashboardTermFilter) dashboardTermFilter.addEventListener("change", () => handleDashboardFilterChange("term"));
  if (dashboardCollegeFilter) dashboardCollegeFilter.addEventListener("change", () => handleDashboardFilterChange("college"));
  if (dashboardMajorFilter) dashboardMajorFilter.addEventListener("change", () => handleDashboardFilterChange("major"));
  if (dashboardCourseTypeFilter) dashboardCourseTypeFilter.addEventListener("change", () => handleDashboardFilterChange("course_type"));
  if (dashboardFilterReset) {
    dashboardFilterReset.addEventListener("click", () => {
      [dashboardTermFilter, dashboardCollegeFilter, dashboardMajorFilter, dashboardCourseTypeFilter].forEach((el) => {
        if (el) el.value = "";
      });
      loadDashboard(true);
    });
  }
  if (sqlToggle) {
    sqlToggle.addEventListener("click", () => setSqlExpanded(sqlBlock && sqlBlock.classList.contains("is-collapsed")));
  }
  [feedbackModalClose, feedbackModalCancel].forEach((btn) => {
    if (btn) btn.addEventListener("click", closeFeedbackModal);
  });
  if (feedbackModalSubmit) feedbackModalSubmit.addEventListener("click", submitFeedbackModal);
  if (feedbackModal) {
    feedbackModal.addEventListener("click", (event) => {
      if (event.target === feedbackModal) closeFeedbackModal();
    });
  }
  if (kbSearch) kbSearch.addEventListener("input", renderKbList);
  if (schemaTableSearch) {
    schemaTableSearch.addEventListener("input", () => {
      schemaTableQuery = schemaTableSearch.value.trim().toLowerCase();
      renderSchemaConsole();
    });
  }
  if (schemaFieldSearch) {
    schemaFieldSearch.addEventListener("input", () => {
      schemaFieldQuery = schemaFieldSearch.value.trim().toLowerCase();
      renderSchemaConsole();
    });
  }
  if (schemaExpandFields) {
    schemaExpandFields.addEventListener("click", () => {
      const src = currentKbSource();
      const summary = schemaSummary(src);
      const fieldMeta = loadFieldMeta(src);
      const visible = (summary.tables[activeSchemaTable] || []).filter((field) => {
        const serverMeta = schemaColumnMeta(src, activeSchemaTable, field);
        const profMeta = profileColumn(src, activeSchemaTable, field);
        const localMeta = fieldMeta[fieldMetaId(activeSchemaTable, field)] || {};
        const text = [field, profMeta.business_name, profMeta.description, serverMeta.business_name, serverMeta.description, localMeta.alias, localMeta.desc]
          .filter(Boolean).join(" ").toLowerCase();
        return !schemaFieldQuery || text.includes(schemaFieldQuery);
      });
      const shouldExpand = visible.some((field) => !expandedSchemaFields.has(`${activeSchemaTable}.${field}`));
      visible.forEach((field) => {
        const key = `${activeSchemaTable}.${field}`;
        if (shouldExpand) expandedSchemaFields.add(key);
        else expandedSchemaFields.delete(key);
      });
      renderSchemaConsole();
    });
  }
  schemaConfigTabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const target = tab.dataset.schemaConfigTab;
      schemaConfigTabs.forEach((item) => item.classList.toggle("active", item === tab));
      schemaConfigPanels.forEach((panel) => {
        panel.classList.toggle("active", panel.dataset.schemaConfigPanel === target);
      });
    });
  });
  if (kbRefreshBtn) {
    kbRefreshBtn.addEventListener("click", async () => {
      await loadSources();
      await loadSchema(activeSourceName() || undefined);
    });
  }
  if (debugRunBtn) {
    debugRunBtn.addEventListener("click", () => {
      const text = (debugQuestion && debugQuestion.value || "").trim();
      if (text) input.value = text;
      runRetrievalDebug();
    });
  }
  if (relationAddBtn) relationAddBtn.addEventListener("click", addRelationEntry);
  if (relationInput) {
    relationInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") { e.preventDefault(); addRelationEntry(); }
    });
  }
  if (llmDraftBtn) {
    llmDraftBtn.textContent = "发布 Profile";
    llmDraftBtn.addEventListener("click", publishCurrentProfile);
  }

  submit.addEventListener("click", executeQuery);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); executeQuery(); }
  });

  clearBtn.addEventListener("click", () => {
    if (loadHistory().length === 0 && !conversationSource) return;
    if (!confirm("清空当前会话?后续提问将重新自动识别数据源、且不带上下文。")) return;
    clearHistory();
    conversationSource = null;
    hide(routedSource);
    hideAllStateCards();
    loadSchema();
    renderSuggestions();
  });

  sqlCopy.addEventListener("click", () => {
    const text = sqlCode.textContent || "";
    navigator.clipboard.writeText(text).then(() => {
      sqlCopy.textContent = "已复制 ✓";
      sqlCopy.classList.add("copied");
      setTimeout(() => { sqlCopy.textContent = "复制"; sqlCopy.classList.remove("copied"); }, 1500);
    }).catch(() => {});
  });

  if (copyTableBtn) copyTableBtn.addEventListener("click", copyTable);
  if (downloadCsvBtn) downloadCsvBtn.addEventListener("click", downloadCsv);
  if (saveQueryBtn) saveQueryBtn.addEventListener("click", saveCurrentQuery);
  if (confirmGoodBtn) confirmGoodBtn.addEventListener("click", confirmCurrentResult);
  if (reportBadBtn) reportBadBtn.addEventListener("click", reportCurrentResult);
  if (chartToggleBtn) chartToggleBtn.addEventListener("click", toggleChart);
  if (historyClearBtn) {
    historyClearBtn.addEventListener("click", () => {
      localStorage.removeItem(QUERY_LOG_KEY);
      renderQueryLog();
    });
  }

  schemaToggle.addEventListener("click", () => {
    schemaBody.classList.toggle("visible");
    schemaToggle.classList.toggle("open");
  });

  glossaryToggle.addEventListener("click", () => {
    glossaryBody.classList.toggle("visible");
    glossaryToggle.classList.toggle("open");
  });
  glossaryAddBtn.addEventListener("click", addGlossaryEntry);
  glossaryInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); addGlossaryEntry(); }
  });
  if (dashboardRefreshBtn) dashboardRefreshBtn.addEventListener("click", () => loadDashboard(true));
  if (assignmentRefreshBtn) assignmentRefreshBtn.addEventListener("click", () => loadAssignmentProduct(true));
  if (analyticsRefreshBtn) analyticsRefreshBtn.addEventListener("click", () => loadCourseAnalytics(true));
  if (analyticsCoursePicker) analyticsCoursePicker.addEventListener("change", () => {
    selectedAnalyticsClassId = Number(analyticsCoursePicker.value);
    loadCourseAnalytics();
  });
  [analyticsQuestionTemplates, analyticsHistoryList].forEach((container) => {
    if (!container) return;
    container.addEventListener("click", (event) => {
      const button = event.target.closest("[data-analytics-question]");
      if (!button) return;
      const question = button.dataset.analyticsQuestion || "";
      if (analyticsQuestionInput) analyticsQuestionInput.value = question;
      executeAnalyticsQuestion(question);
    });
  });
  if (analyticsAskForm) analyticsAskForm.addEventListener("submit", (event) => {
    event.preventDefault();
    executeAnalyticsQuestion(analyticsQuestionInput?.value.trim() || "");
  });
  if (analyticsAnswer) analyticsAnswer.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-analytics-feedback]");
    if (!button) return;
    await api.feedbackCourseAnalytics(button.dataset.logId, button.dataset.analyticsFeedback);
    button.parentElement.innerHTML = "<span>反馈已记录</span>";
    await loadAnalyticsHistory();
  });
  if (assignmentCoursePicker) assignmentCoursePicker.addEventListener("change", async () => {
    selectedTeachingClassId = Number(assignmentCoursePicker.value);
    selectedAssignmentId = null;
    await loadAssignmentProduct(true);
  });
  if (assignmentCreateToggle) assignmentCreateToggle.addEventListener("click", () => {
    if (!assignmentCreateForm) return;
    delete assignmentCreateForm.dataset.editingId;
    assignmentCreateForm.reset();
    if (assignmentCreateAllowLate) assignmentCreateAllowLate.checked = true;
    assignmentCreateForm.classList.remove("hidden");
  });
  if (assignmentCreateClose) assignmentCreateClose.addEventListener("click", () => {
    if (!assignmentCreateForm) return;
    delete assignmentCreateForm.dataset.editingId;
    assignmentCreateForm.classList.add("hidden");
  });
  if (assignmentStudentFilters) assignmentStudentFilters.addEventListener("click", (event) => {
    const button = event.target.closest("[data-assignment-filter]");
    if (!button) return;
    assignmentStudentFilter = button.dataset.assignmentFilter;
    assignmentStudentFilters.querySelectorAll("button").forEach((item) => item.classList.toggle("active", item === button));
    renderAssignmentStudentProduct(assignmentStudentItems);
  });
  if (assignmentCreateForm) {
    assignmentCreateForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const title = assignmentCreateTitle ? assignmentCreateTitle.value.trim() : "";
      const due = assignmentCreateDue ? assignmentCreateDue.value.trim() : "";
      if (!title || !due) return;
      const status = e.submitter?.dataset.createStatus || "draft";
      const payload = {
        title,
        due_time: due,
        max_score: assignmentCreateScore ? Number(assignmentCreateScore.value || 100) : 100,
        instructions: assignmentCreateInstructions ? assignmentCreateInstructions.value : "",
        allow_late: assignmentCreateAllowLate ? assignmentCreateAllowLate.checked : true,
        status,
      };
      if (assignmentCreateForm.dataset.editingId) {
        payload.status = "draft";
        await api.updateTeachingAssignment(assignmentCreateForm.dataset.editingId, payload);
        delete assignmentCreateForm.dataset.editingId;
      } else {
        await api.createTeachingAssignment(selectedTeachingClassId, payload);
      }
      assignmentCreateForm.reset();
      if (assignmentCreateAllowLate) assignmentCreateAllowLate.checked = true;
      assignmentCreateForm.classList.add("hidden");
      await loadAssignmentProduct(true);
    });
  }
  if (supportRefreshBtn) supportRefreshBtn.addEventListener("click", async () => {
    await api.refreshSupportCases();
    await loadSupportWorkbench(true);
  });
  if (supportStatusFilter) supportStatusFilter.addEventListener("change", () => {
    selectedSupportCaseId = null;
    loadSupportWorkbench(true);
  });
  if (supportRequestForm) supportRequestForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const message = supportRequestMessage?.value.trim() || "";
    if (!message) return;
    await api.createSupportRequest({
      request_type: supportRequestType?.value || "appointment",
      message,
      preferred_time: supportRequestTime?.value || null,
    });
    supportRequestForm.reset();
    await loadSupportWorkbench(true);
  });
  if (domainRefreshBtn) domainRefreshBtn.addEventListener("click", () => loadDomainSettings(true));
  if (roleRefreshBtn) roleRefreshBtn.addEventListener("click", () => loadDomainSettings(true));
  if (passwordForm) {
    passwordForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (passwordMessage) passwordMessage.textContent = "";
      const oldValue = oldPassword ? oldPassword.value : "";
      const newValue = newPassword ? newPassword.value : "";
      const confirmValue = confirmPassword ? confirmPassword.value : "";
      if (!oldValue || !newValue || !confirmValue) {
        if (passwordMessage) passwordMessage.textContent = "请完整填写原密码和新密码。";
        return;
      }
      if (newValue !== confirmValue) {
        if (passwordMessage) passwordMessage.textContent = "两次输入的新密码不一致。";
        return;
      }
      try {
        await api.changePassword({ old_password: oldValue, new_password: newValue });
        if (passwordMessage) passwordMessage.textContent = "密码已修改，请使用新密码重新登录。";
        setTimeout(() => {
          localStorage.removeItem(AUTH_TOKEN_KEY);
          localStorage.removeItem(AUTH_USER_KEY);
          currentUser = null;
          showLogin();
          if (loginUsername && passwordAccount) loginUsername.value = (passwordAccount.value.split("·")[0] || "").trim();
          if (loginPassword) loginPassword.value = "";
        }, 700);
      } catch (err) {
        if (passwordMessage) passwordMessage.textContent = err.message || "密码修改失败";
      }
    });
  }
  if (loginForm) {
    loginForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (loginError) loginError.textContent = "";
      try {
        const payload = await api.login({
          username: (loginUsername && loginUsername.value || "").trim(),
          password: loginPassword.value || "",
        });
        setAuthSession(payload);
        await bootWorkspace();
      } catch (err) {
        if (loginError) loginError.textContent = err.message || "登录失败";
      }
    });
  }
  if (logoutBtn) {
    logoutBtn.addEventListener("click", () => {
      localStorage.removeItem(AUTH_TOKEN_KEY);
      localStorage.removeItem(AUTH_USER_KEY);
      clearHistory();
      currentUser = null;
      conversationSource = null;
      dashboardCache = null;
      domainSettingsCache = null;
      showLogin();
    });
  }

  /* ---------------- init ---------------- */

  (async () => {
    showLogin();
    await loadAuthOptions();
    const restored = await restoreAuthSession();
    if (restored) {
      await bootWorkspace();
      await loadSchema();
    }
    updateHistoryBadge();
    renderQueryLog();
    renderSuggestions();
    renderGlossary();
    renderKbList();
    renderKbOverview();
    renderSchemaConsole();
    renderDebugSteps();
    if (restored) showView(hasFeature("dashboard") ? "dashboard-view" : "assistant-view");
  })();
})();
