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

  const input = $("query-input");
  const submit = $("query-submit");
  const clearBtn = $("clear-btn");
  const historyBadge = $("history-badge");
  const sourceTags = $("source-tags");

  const routedSource = $("routed-source");
  const routedText = $("routed-text");

  const progressBox = $("progress-box");
  const progressFill = $("progress-fill");
  const progressStageText = $("progress-stage-text");

  const clarifyBox = $("clarify-box");
  const clarifyMsg = $("clarify-msg");
  const errorBox = $("error-box");
  const errorMsg = $("error-msg");

  const sqlBlock = $("sql-block");
  const sqlCode = $("sql-code");
  const sqlMeta = $("sql-meta");
  const sqlCopy = $("sql-copy");

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
  const schemaEditorTitle = $("schema-editor-title");
  const fieldTableBody = $("field-table-body");
  const metricList = $("metric-list");
  const termList = $("term-list");
  const relationInput = $("relation-input");
  const relationAddBtn = $("relation-add-btn");
  const relationList = $("relation-list");
  const debugQuestion = $("debug-question");
  const debugRunBtn = $("debug-run-btn");
  const debugSteps = $("debug-steps");

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

  // 会话首轮路由选定的数据源;多轮追问复用它,避免串库。新会话/手动切换时重置。
  let conversationSource = null;
  // 下拉/标签显式选择的库(为空表示「自动识别」)
  let selectedSource = "";
  let currentResult = null;
  let availableSources = [];
  let schemaCache = {};
  let profileCache = {};
  let feedbackCache = [];
  let schemaLoading = new Set();
  let selectedKb = "auto";
  let lastTrace = null;
  let activeSchemaTable = "";

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

  function showView(id) {
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
    if (id === "kb-overview-view") {
      loadFeedback(currentKbSource()).then(() => renderKbOverview());
      renderKbOverview();
    }
    if (id === "schema-console-view") renderSchemaConsole();
    if (id === "debug-view") renderDebugSteps();
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

    const healthItems = [
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
      function persistExample() {
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
        persistExample();
        renderSavedExamples(source);
      });
      fewshotInput.addEventListener("change", () => {
        persistExample();
        renderKbOverview();
      });
      card.querySelector(".saved-example-delete").addEventListener("click", () => {
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
    if (!names.includes(activeSchemaTable)) activeSchemaTable = names[0] || "";
    schemaTree.innerHTML = "";
    if (!names.length) {
      schemaTree.innerHTML = '<div class="empty-note">暂无 Schema。请先选择知识库或刷新数据源。</div>';
    } else {
      names.forEach((name) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "schema-tree-btn";
        btn.classList.toggle("active", name === activeSchemaTable);
        btn.innerHTML = `<b>${escapeHtml(name)}</b><span>${(tables[name] || []).length} fields</span>`;
        btn.addEventListener("click", () => {
          activeSchemaTable = name;
          renderSchemaConsole();
        });
        schemaTree.appendChild(btn);
      });
    }

    schemaEditorTitle.textContent = activeSchemaTable ? `${activeSchemaTable} 字段配置` : "字段配置";
    fieldTableBody.innerHTML = "";
    const profile = currentProfile(src);
    if (activeSchemaTable) {
      const tableProfile = (profile.tables || {})[activeSchemaTable] || {};
      const tableCard = document.createElement("div");
      tableCard.className = "field-card";
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
            <input class="table-profile-input" data-profile-field="business_name" value="${escapeHtml(tableProfile.business_name || "")}" placeholder="例如: 订单" />
          </label>
          <label class="wide">
            <span>表说明</span>
            <input class="table-profile-input" data-profile-field="description" value="${escapeHtml(tableProfile.description || "")}" placeholder="这张表记录什么业务对象" />
          </label>
          <label class="wide">
            <span>表粒度</span>
            <input class="table-profile-input" data-profile-field="grain" value="${escapeHtml(tableProfile.grain || "")}" placeholder="例如: 一行代表一笔订单" />
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
    (tables[activeSchemaTable] || []).forEach((field) => {
      const card = document.createElement("div");
      card.className = "field-card";
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
      card.innerHTML = `
        <div class="field-card-head">
          <div class="field-identity">
            <b>${escapeHtml(field)}</b>
            <span>${escapeHtml(nullableText)}${defaultText ? " · " + escapeHtml(defaultText) : ""}</span>
          </div>
          <div class="field-badges">
            <code>${escapeHtml(serverMeta.data_type || "unknown")}</code>
            ${keyBadge ? `<em>${escapeHtml(keyBadge)}</em>` : ""}
            <em>${escapeHtml(role)}</em>
            <em>${role === "指标" ? "可聚合" : "可筛选"}</em>
          </div>
          <button class="field-meta-save" type="button">保存</button>
        </div>
        <div class="field-card-grid">
          <label>
            <span>中文名 / 别名</span>
            <input class="field-meta-input" data-meta-field="business_name" value="${escapeHtml(aliasText)}" placeholder="例如: 订单金额" />
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
    if (!fieldTableBody.children.length) {
      fieldTableBody.innerHTML = '<div class="empty-note">暂无字段</div>';
    }

    if (metricList) {
      const metricSeeds = ["销售额 = 金额字段求和", "订单量 = 订单主键计数", "平均值 = 数值字段 AVG", "占比 = 分组值 / 总量"];
      const metrics = [...loadMetrics(src), ...metricSeeds].slice(0, 10);
      metricList.innerHTML = "";
      metrics.forEach((text) => {
        const li = document.createElement("li");
        li.className = "tag-chip";
        li.textContent = text;
        metricList.appendChild(li);
      });
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
      alert("关系格式示例: orders.user_id = users.id");
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
      const resp = await fetch("/api/debug/retrieval", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, source: manualSource(), current_source: conversationSource, history: loadHistory().slice(-MAX_HISTORY_TURNS) }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
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
    demo_sqlite: [
      "2025 年订单总金额是多少？",
      "销量前 5 的商品有哪些？",
      "按城市拆分 2025 年订单金额",
      "平均评分最高的 5 个商品，至少 10 条评价",
    ],
    financial: [
      "交易后才出对账单的账户有多少个？",
      "按地区统计客户数量",
      "平均工资大于 8000 的地区有哪些？",
    ],
    superhero: [
      "拥有 Super Strength 且身高超过 200cm 的超级英雄有多少个？",
      "列出蓝眼睛且金色头发的超级英雄名字",
      "Marvel Comics 旗下英雄按身高排名",
    ],
    european_football_2: [
      "2016 赛季进球总数最多的联赛是哪一个？",
      "苏格兰超级联赛 2010 赛季客场胜场最多的球队是哪支？",
    ],
    formula_1: [
      "第 592 场比赛中完赛车手里年龄最大的是谁？",
      "按车队统计完赛次数",
    ],
    auto: [
      "2025 年销售额最高的 5 个商品是什么？",
      "按地区统计用户数量",
      "最近一年每个月的订单金额趋势",
      "数量最多的是哪一个？",
    ],
  };

  function suggestionSource() {
    return manualSource() || conversationSource || "auto";
  }

  function renderSuggestions() {
    if (!suggestionList) return;
    const src = suggestionSource();
    const list = SUGGESTIONS[src] || SUGGESTIONS.auto;
    suggestionList.innerHTML = "";
    list.forEach((text) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "suggestion-chip";
      btn.textContent = text;
      btn.addEventListener("click", () => {
        input.value = text;
        input.focus();
      });
      suggestionList.appendChild(btn);
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
        const resp = await fetch("/api/judge", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ judge_id: data.judge_id }),
        });
        const jd = await resp.json();
        if (!pending.isConnected) return;
        if (typeof jd.confidence === "number") {
          pending.outerHTML = confidenceBadge(jd.confidence, jd.confidence_detail);
          return;
        }
        if (jd.status === "failed") {
          pending.className = "confidence conf-pending";
          pending.title = "裁判模型调用失败或输出无法解析,不影响本次查询结果";
          pending.textContent = "可信度评估失败";
          return;
        }
        if (jd.status === "missing") {
          pending.className = "confidence conf-pending";
          pending.title = "评估任务已过期或服务重启后丢失,不影响本次查询结果";
          pending.textContent = "可信度评估过期";
          return;
        }
        await new Promise((resolve) => setTimeout(resolve, 1500));
      }
      pending.className = "confidence conf-pending";
      pending.title = "裁判模型仍未返回,可能是模型响应慢或网络较慢;不影响本次查询结果";
      pending.textContent = "可信度评估仍在后台运行";
    } catch (e) {
      if (!pending.isConnected) return;
      pending.className = "confidence conf-pending";
      pending.title = "可信度评估请求失败,不影响本次查询结果";
      pending.textContent = "可信度评估失败";
    }
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
      const resp = await fetch("/api/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(item),
      });
      if (resp.ok) {
        const saved = await resp.json();
        feedbackCache = [saved.item, ...feedbackCache.filter((x) => x.id !== saved.item.id)];
      }
    } catch {}
    renderKbOverview();
  }

  function confirmCurrentResult() {
    if (!currentResult) return;
    const item = saveCurrentQuery();
    saveFeedback("correct", "用户确认结果正确", "confirmed");
    if (confirmGoodBtn) {
      const old = confirmGoodBtn.textContent;
      confirmGoodBtn.textContent = item ? "已沉淀为样例" : "已确认";
      setTimeout(() => { confirmGoodBtn.textContent = old; }, 1500);
    }
  }

  function reportCurrentResult() {
    if (!currentResult) return;
    const reason = prompt("请简要说明哪里不对: 口径不对 / 字段选错 / 过滤条件错 / 数据源错 / 其他", "");
    if (reason == null) return;
    const category = prompt("错误类型(可选): 选错库 / 字段理解错 / JOIN错 / 过滤条件错 / 指标口径错 / 结果看不懂", "") || "";
    saveFeedback("incorrect", reason.trim(), category.trim());
    if (reportBadBtn) {
      const old = reportBadBtn.textContent;
      reportBadBtn.textContent = "已记录";
      setTimeout(() => { reportBadBtn.textContent = old; }, 1500);
    }
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
    return readJsonList(SAVED_QUERY_KEY)
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

  /* ---------------- data fetching ---------------- */

  async function loadProfile(source) {
    if (!source) return emptyProfile();
    const key = profileKey(source);
    if (profileCache[key]) return profileCache[key];
    try {
      const resp = await fetch(`/api/profile?source=${encodeURIComponent(source)}`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      profileCache[key] = data.profile || emptyProfile();
    } catch {
      profileCache[key] = emptyProfile();
    }
    return profileCache[key];
  }

  async function saveProfile(source, profile) {
    if (!source) return;
    const resp = await fetch(`/api/profile?source=${encodeURIComponent(source)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile }),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    profileCache[profileKey(source)] = data.profile || profile;
    schemaCache = {};
    await loadSchema(source);
  }

  async function loadFeedback(source) {
    try {
      const qs = source ? `?source=${encodeURIComponent(source)}` : "";
      const resp = await fetch(`/api/feedback${qs}`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      feedbackCache = data.items || [];
    } catch {
      feedbackCache = readJsonList(FEEDBACK_KEY);
    }
    return feedbackCache;
  }

  async function loadSchema(forceSource) {
    const src = forceSource || manualSource();
    const key = schemaKey(src);
    schemaLoading.add(key);
    renderKbList();
    try {
      const url = src ? `/api/schema?source=${encodeURIComponent(src)}` : "/api/schema";
      const resp = await fetch(url);
      const shouldUpdateSchemaText = schemaKey(activeSourceName()) === key || (!activeSourceName() && key === "__auto__");
      if (!resp.ok) {
        if (shouldUpdateSchemaText) schemaText.textContent = `(加载失败: HTTP ${resp.status})`;
        return;
      }
      const data = await resp.json();
      schemaCache[key] = data;
      if (src) await loadProfile(src);
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
    autoTag.className = "source-tag active";
    autoTag.dataset.src = "";
    autoTag.textContent = "🤖 自动识别";
    sourceTags.appendChild(autoTag);

    for (const s of sources) {
      const tag = document.createElement("span");
      tag.className = "source-tag";
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

  async function loadSources() {
    try {
      const resp = await fetch("/api/sources");
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      availableSources = data.sources || [];
      renderSourceTags(availableSources);
      renderSuggestions();
      await loadFeedback();
      renderKbList();
      renderKbOverview();
      renderSchemaConsole();
      loadAllSchemas();
    } catch {
      sourceTags.innerHTML = '<span class="source-tag active">（数据源加载失败）</span>';
    }
  }

  /* ---------------- progress ---------------- */
  // 后端是一次性返回(不逐阶段推送),这里按真实流水线阶段做"乐观"进度:
  // 分阶段推进、填到约 88%,响应一到补满 100% 收起。自动模式多一个"判断数据源"阶段。
  let progressTimers = [];
  const PROGRESS_AUTO = [
    { text: "正在判断数据源…", pct: 18 },
    { text: "检索相关表与字段…", pct: 44 },
    { text: "生成 SQL…", pct: 72 },
    { text: "执行查询…", pct: 88 },
  ];
  const PROGRESS_MANUAL = [
    { text: "检索相关表与字段…", pct: 32 },
    { text: "生成 SQL…", pct: 70 },
    { text: "执行查询…", pct: 88 },
  ];

  function clearProgressTimers() {
    progressTimers.forEach((t) => clearTimeout(t));
    progressTimers = [];
  }

  function startProgress(isAuto) {
    clearProgressTimers();
    const stages = isAuto ? PROGRESS_AUTO : PROGRESS_MANUAL;
    progressBox.classList.remove("done");
    progressFill.style.transition = "none";
    progressFill.style.width = "0%";
    show(progressBox);
    void progressFill.offsetWidth;          // 强制重排,让 0% 先落地再开始过渡
    progressFill.style.transition = "";
    let delay = 120;
    stages.forEach((st, i) => {
      progressTimers.push(setTimeout(() => {
        progressStageText.textContent = st.text;
        progressFill.style.width = st.pct + "%";
      }, delay));
      delay += 550 + i * 450;               // 越往后阶段越慢(生成 SQL 最耗时)
    });
  }

  function finishProgress() {
    clearProgressTimers();
    progressStageText.textContent = "完成";
    progressBox.classList.add("done");
    progressFill.style.width = "100%";
    progressTimers.push(setTimeout(() => {
      hide(progressBox);
      progressFill.style.width = "0%";
      progressBox.classList.remove("done");
    }, 480));
  }

  function failProgress() {
    clearProgressTimers();
    hide(progressBox);
    progressFill.style.width = "0%";
    progressBox.classList.remove("done");
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
      const resp = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, history, source, current_source: currentSource,
                               user_glossary: userGlossary, few_shots: fewShots }),
      });
      const data = await resp.json();
      finishProgress();   // 网络往返结束,进度补满收起(后续分支只管渲染)

      // 透明展示本次实际使用的数据源
      showRoutedSource(data);
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
        sqlCode.innerHTML = highlightSQL(data.sql);
        sqlBlock.classList.add("visible");
      }

      if (data.error) {
        errorMsg.textContent = data.error;
        show(errorBox);
      } else {
        renderMeta(data);
        const rowCount = typeof data.row_count === "number" ? data.row_count : (data.rows || []).length;
        if (resultTitle) resultTitle.textContent = `查询结果 · ${rowCount} 行`;
        currentResult = { ...data, question, id: String(Date.now()) };
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
      errorMsg.textContent = `请求失败: ${err.message}`;
      show(errorBox);
    } finally {
      submit.disabled = false;
      submit.innerHTML = submitLabel;
    }
  }

  /* ---------------- events ---------------- */

  navTargets.forEach((btn) => {
    btn.addEventListener("click", () => showView(btn.dataset.viewTarget));
  });
  if (kbSearch) kbSearch.addEventListener("input", renderKbList);
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

  /* ---------------- init ---------------- */

  (async () => {
    await loadSources();
    await loadSchema();
    updateHistoryBadge();
    renderQueryLog();
    renderSuggestions();
    renderGlossary();
    renderKbList();
    renderKbOverview();
    renderSchemaConsole();
    renderDebugSteps();
    showView("assistant-view");
  })();
})();
