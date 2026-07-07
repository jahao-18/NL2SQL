(function () {
  const $ = (id) => document.getElementById(id);
  const api = window.NL2SQLApi;
  const modal = window.NL2SQLModal;

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function statusLabel(status) {
    return {
      open: "待处理",
      in_progress: "处理中",
      accepted: "已采纳",
      rejected: "已驳回",
      closed: "已关闭",
    }[status || "open"] || "待处理";
  }

  function kindLabel(kind) {
    if (kind === "publish_request") return "发布申请";
    if (kind === "correct") return "正确确认";
    if (kind === "correct_example") return "用例沉淀";
    if (kind === "feedback_fix") return "错误反馈";
    return "错误反馈";
  }

  function kindClass(kind) {
    if (kind === "correct" || kind === "correct_example") return "is-correct";
    if (kind === "publish_request") return "is-publish";
    return "is-incorrect";
  }

  function reviewPayload(item) {
    return (item && item.payload && item.payload.feedback) || {};
  }

  function create(options) {
    const sourceFilter = $("governance-source-filter");
    const statusFilter = $("governance-status-filter");
    const statusTabs = $("governance-status-tabs");
    const kindFilter = $("governance-kind-filter");
    const refreshBtn = $("governance-refresh-btn");
    const reviewList = $("governance-review-list");
    const reviewDetail = $("governance-review-detail");
    const settingsSaveBtn = $("governance-settings-save-btn");
    const settingReviewRequired = $("setting-review-required");
    const settingAutoQueue = $("setting-auto-queue");
    const settingRequireNote = $("setting-require-note");
    const settingConfidenceThreshold = $("setting-confidence-threshold");
    const settingDefaultStatus = $("setting-default-status");
    const settingPageSize = $("setting-page-size");

    let reviewItemsCache = [];
    let selectedReviewItemId = "";
    let settingsCache = {};

    function getSettings() {
      return settingsCache || {};
    }

    function setSelectedReviewItemId(id) {
      selectedReviewItemId = id || "";
    }

    function renderSourceOptions() {
      if (!sourceFilter) return;
      const current = sourceFilter.value || "all";
      sourceFilter.innerHTML = '<option value="all">全部数据源</option>';
      (options.availableSources() || []).forEach((source) => {
        const opt = document.createElement("option");
        opt.value = source.name;
        opt.textContent = source.label || source.name;
        sourceFilter.appendChild(opt);
      });
      sourceFilter.value = Array.from(sourceFilter.options).some((opt) => opt.value === current) ? current : "all";
    }

    function syncStatusTabs() {
      if (!statusTabs || !statusFilter) return;
      const current = statusFilter.value || "open";
      statusTabs.querySelectorAll("[data-status]").forEach((btn) => {
        btn.classList.toggle("active", btn.dataset.status === current);
      });
    }

    async function loadReviewItems() {
      const limit = (settingsCache && settingsCache.page_size) || 100;
      try {
        const data = await api.reviewItems({
          source: sourceFilter && sourceFilter.value,
          status: statusFilter && statusFilter.value,
          kind: kindFilter && kindFilter.value,
          limit,
        });
        reviewItemsCache = data.items || [];
      } catch {
        reviewItemsCache = [];
      }
      return reviewItemsCache;
    }

    async function renderQueue() {
      if (!reviewList || !reviewDetail) return;
      renderSourceOptions();
      syncStatusTabs();
      const items = await loadReviewItems();
      reviewList.innerHTML = "";
      if (!items.length) {
        selectedReviewItemId = "";
        reviewList.innerHTML = '<div class="empty-note">当前筛选下没有待审项。用户反馈错误、确认正确或提交发布审核后，会进入这里。</div>';
        renderDetail(null);
        return;
      }
      if (!selectedReviewItemId || !items.some((item) => item.id === selectedReviewItemId)) {
        selectedReviewItemId = items[0].id;
      }
      items.forEach((item) => {
        const payload = reviewPayload(item);
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "review-row";
        btn.classList.toggle("active", item.id === selectedReviewItemId);
        btn.innerHTML = `
          <span class="review-row-main">
            <b>${escapeHtml(item.title || item.question || payload.question || "未记录问题")}</b>
            <small>${escapeHtml(item.source_label || item.source || "自动识别")} · ${escapeHtml(item.category || payload.category || "未分类")}</small>
          </span>
          <span class="review-row-meta">
            <em class="review-status">${escapeHtml(statusLabel(item.status))}</em>
            <small>${escapeHtml(kindLabel(item.kind))}</small>
          </span>
        `;
        btn.addEventListener("click", () => {
          selectedReviewItemId = item.id;
          renderQueue();
        });
        reviewList.appendChild(btn);
      });
      renderDetail(items.find((item) => item.id === selectedReviewItemId));
    }

    function renderDetail(item) {
      if (!reviewDetail) return;
      reviewDetail.innerHTML = "";
      if (!item) {
        reviewDetail.innerHTML = '<div class="empty-note">选择一条反馈后查看详情和处理动作。</div>';
        return;
      }
      const feedback = reviewPayload(item);
      const displayQuestion = item.title || item.question || feedback.question || "";
      const displaySql = item.sql || feedback.sql || "";
      const displayReason = item.reason || feedback.reason || "";
      const div = document.createElement("div");
      div.className = "review-detail-body";
      div.innerHTML = `
        <div class="review-detail-head">
          <span class="review-kind ${kindClass(item.kind)}">${escapeHtml(kindLabel(item.kind))}</span>
          <span class="review-status">${escapeHtml(statusLabel(item.status))}</span>
        </div>
        <label><span>问题</span><textarea readonly rows="3">${escapeHtml(displayQuestion)}</textarea></label>
        ${item.kind !== "publish_request" ? `<label><span>SQL</span><textarea readonly rows="7">${escapeHtml(displaySql)}</textarea></label>` : ""}
        <label><span>${item.kind === "publish_request" ? "发布说明" : "反馈说明"}</span><textarea readonly rows="3">${escapeHtml(displayReason)}</textarea></label>
        ${item.kind === "publish_request" ? `<div class="review-facts">
          <span>表画像: ${escapeHtml((item.explanation && item.explanation.table_count) || (item.payload && item.payload.table_count) || 0)}</span>
          <span>关系: ${escapeHtml((item.explanation && item.explanation.relation_count) || (item.payload && item.payload.relation_count) || 0)}</span>
          <span>指标: ${escapeHtml((item.explanation && item.explanation.metric_count) || (item.payload && item.payload.metric_count) || 0)}</span>
        </div>` : ""}
        <div class="review-facts">
          <span>数据源: ${escapeHtml(item.source_label || item.source || "-")}</span>
          <span>分类: ${escapeHtml(item.category || feedback.category || "-")}</span>
          <span>创建: ${escapeHtml((item.created_at || "").slice(0, 19))}</span>
        </div>
        <div class="review-actions grouped">
          <div class="review-action-group primary">
            ${item.kind === "publish_request" ? '<button type="button" data-action="publish">审核通过并发布</button>' : ""}
            ${item.kind !== "publish_request" ? '<button type="button" data-action="example">采纳为标准问法</button>' : ""}
            <button type="button" data-action="progress">标记处理中</button>
          </div>
          ${item.kind !== "publish_request" ? `<div class="review-action-group">
            <span>转为治理项</span>
            <button type="button" data-action="field">字段</button>
            <button type="button" data-action="relation">关系</button>
            <button type="button" data-action="metric">指标</button>
          </div>` : ""}
          <div class="review-action-group danger">
            <button type="button" data-action="reject">驳回</button>
            <button type="button" data-action="close">关闭</button>
          </div>
        </div>
        <div class="review-resolution">${escapeHtml(item.resolution || "")}</div>
      `;
      div.querySelector('[data-action="progress"]').addEventListener("click", () => updateStatus(item.id, "in_progress"));
      const publishBtn = div.querySelector('[data-action="publish"]');
      if (publishBtn) publishBtn.addEventListener("click", () => acceptAsPublish(item));
      const exampleBtn = div.querySelector('[data-action="example"]');
      if (exampleBtn) exampleBtn.addEventListener("click", () => acceptAsExample(item));
      const fieldBtn = div.querySelector('[data-action="field"]');
      if (fieldBtn) fieldBtn.addEventListener("click", () => acceptAsField(item));
      const relationBtn = div.querySelector('[data-action="relation"]');
      if (relationBtn) relationBtn.addEventListener("click", () => acceptAsRelation(item));
      const metricBtn = div.querySelector('[data-action="metric"]');
      if (metricBtn) metricBtn.addEventListener("click", () => acceptAsMetric(item));
      div.querySelector('[data-action="reject"]').addEventListener("click", () => reject(item));
      div.querySelector('[data-action="close"]').addEventListener("click", () => updateStatus(item.id, "closed"));
      reviewDetail.appendChild(div);
    }

    async function updateStatus(id, status) {
      try {
        await api.updateReviewItem(id, { status });
      } catch {
        alert("状态更新失败");
        return;
      }
      await refreshAfterChange();
    }

    async function accept(item, action, payload) {
      try {
        await api.acceptReviewItem(item.id, { action, payload: { source: item.source, ...payload } });
      } catch (e) {
        alert(e.message || "采纳失败");
        return;
      }
      if (item.source) await options.refreshSource(item.source);
      await refreshAfterChange();
    }

    async function refreshAfterChange() {
      await renderQueue();
      await options.loadFeedback();
      options.renderKbOverview();
      options.renderSchemaConsole();
    }

    function acceptAsExample(item) {
      const feedback = reviewPayload(item);
      const question = feedback.question || item.question || item.title || "";
      const sql = feedback.sql || item.sql || "";
      if (!question || !sql) {
        alert("缺少问题或 SQL，不能采纳为标准问法");
        return;
      }
      accept(item, "example", {
        question,
        sql,
        source_label: feedback.source_label || item.source_label || options.sourceLabel(item.source),
        tags: ["governance", feedback.category || item.category || item.kind || "feedback"],
        enabled: true,
        resolution: "采纳为标准问法",
      });
    }

    function acceptAsPublish(item) {
      const exp = item.explanation || item.payload || {};
      accept(item, "publish_profile", {
        label: exp.label || (item.question || "").replace("发布 Profile:", "").trim() || "发布版本",
        description: exp.description || item.reason || "",
        resolution: "审核通过并发布 Profile",
      });
    }

    async function acceptAsRelation(item) {
      const values = await modal.open({
        title: "转为表关系",
        fields: [
          { name: "relation", label: "关系表达式", placeholder: "orders.user_id = users.id", required: true },
          { name: "description", label: "关系说明", value: item.reason || "", type: "textarea" },
        ],
        submitText: "采纳",
      });
      if (!values) return;
      accept(item, "relation", { relation: values.relation, description: values.description, resolution: "采纳为表关系" });
    }

    async function acceptAsMetric(item) {
      const values = await modal.open({
        title: "转为指标口径",
        fields: [
          { name: "name", label: "指标名称", value: item.category || "", required: true },
          { name: "formula", label: "指标公式 / 计算口径", required: true },
          { name: "description", label: "指标说明", value: item.reason || "", type: "textarea" },
        ],
        submitText: "采纳",
      });
      if (!values) return;
      accept(item, "metric", { name: values.name, formula: values.formula, description: values.description, enabled: true, resolution: "采纳为指标口径" });
    }

    async function acceptAsField(item) {
      const values = await modal.open({
        title: "转为字段治理",
        fields: [
          { name: "table", label: "表名", required: true },
          { name: "column", label: "字段名", required: true },
          { name: "business_name", label: "字段中文名 / 别名" },
          { name: "description", label: "字段业务说明", value: item.reason || "", type: "textarea" },
        ],
        submitText: "采纳",
      });
      if (!values) return;
      accept(item, "field_profile", {
        table: values.table,
        column: values.column,
        business_name: values.business_name,
        description: values.description,
        notes: `来自反馈: ${item.question || item.title || ""}`.slice(0, 500),
        resolution: "采纳为字段治理",
      });
    }

    async function reject(item) {
      const values = await modal.open({
        title: "驳回待审项",
        fields: [{ name: "reason", label: "驳回原因", value: item.reason || "", type: "textarea", required: true }],
        submitText: "驳回",
      });
      if (!values) return;
      try {
        await api.rejectReviewItem(item.id, { reason: values.reason });
      } catch {
        alert("驳回失败");
        return;
      }
      await refreshAfterChange();
    }

    async function loadSettings() {
      try {
        const data = await api.governanceSettings();
        settingsCache = data.settings || {};
        if (statusFilter && settingsCache.default_status_filter && !statusFilter.dataset.initialized) {
          statusFilter.value = settingsCache.default_status_filter;
          statusFilter.dataset.initialized = "1";
          syncStatusTabs();
        }
      } catch {
        settingsCache = {
          review_required_for_publish: false,
          auto_queue_error_feedback: true,
          low_confidence_threshold: 70,
          require_publish_note: true,
          default_status_filter: "open",
          page_size: 50,
        };
      }
      return settingsCache;
    }

    async function saveSettings() {
      const payload = {
        review_required_for_publish: !!(settingReviewRequired && settingReviewRequired.checked),
        auto_queue_error_feedback: !!(settingAutoQueue && settingAutoQueue.checked),
        require_publish_note: !!(settingRequireNote && settingRequireNote.checked),
        low_confidence_threshold: Number((settingConfidenceThreshold && settingConfidenceThreshold.value) || 70),
        default_status_filter: (settingDefaultStatus && settingDefaultStatus.value) || "open",
        page_size: Number((settingPageSize && settingPageSize.value) || 50),
      };
      try {
        const data = await api.saveGovernanceSettings(payload);
        settingsCache = data.settings || payload;
      } catch {
        alert("设置保存失败");
        return;
      }
      if (statusFilter) statusFilter.value = settingsCache.default_status_filter || "open";
      syncStatusTabs();
      if (settingsSaveBtn) {
        const old = settingsSaveBtn.textContent;
        settingsSaveBtn.textContent = "已保存";
        setTimeout(() => { settingsSaveBtn.textContent = old; }, 1200);
      }
    }

    async function renderSettings() {
      await loadSettings();
      const s = settingsCache || {};
      if (settingReviewRequired) settingReviewRequired.checked = !!s.review_required_for_publish;
      if (settingAutoQueue) settingAutoQueue.checked = s.auto_queue_error_feedback !== false;
      if (settingRequireNote) settingRequireNote.checked = s.require_publish_note !== false;
      if (settingConfidenceThreshold) settingConfidenceThreshold.value = s.low_confidence_threshold == null ? 70 : s.low_confidence_threshold;
      if (settingDefaultStatus) settingDefaultStatus.value = s.default_status_filter || "open";
      if (settingPageSize) settingPageSize.value = s.page_size || 50;
    }

    [sourceFilter, kindFilter].forEach((el) => {
      if (el) el.addEventListener("change", () => {
        selectedReviewItemId = "";
        renderQueue();
      });
    });
    if (statusTabs && statusFilter) {
      statusTabs.addEventListener("click", (e) => {
        const btn = e.target.closest("[data-status]");
        if (!btn) return;
        statusFilter.value = btn.dataset.status || "open";
        selectedReviewItemId = "";
        syncStatusTabs();
        renderQueue();
      });
    }
    if (refreshBtn) refreshBtn.addEventListener("click", renderQueue);
    if (settingsSaveBtn) settingsSaveBtn.addEventListener("click", saveSettings);

    return {
      getSettings,
      setSelectedReviewItemId,
      renderSourceOptions,
      renderQueue,
      renderSettings,
      loadSettings,
    };
  }

  window.NL2SQLGovernanceView = { create };
})();
