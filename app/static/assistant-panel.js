(function () {
  "use strict";

  const DEFAULT_QUESTIONS = [
    "我当前有哪些待办？",
    "当前范围内有哪些需要关注的数据？",
    "本学期课程运行情况怎么样？",
  ];

  const WARNING_TITLES = {
    EMPTY_RESULT: "当前范围暂无结果",
    LOW_CONFIDENCE: "结果需要复核",
    RETRIEVAL_DEGRADED: "检索已降级",
    SMALL_SAMPLE: "样本量较小",
    TRUNCATED: "结果已截断",
    CONTEXT_IGNORED: "部分上下文未采用",
  };

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = String(text);
    return node;
  }

  function button(text, className) {
    const node = el("button", className, text);
    node.type = "button";
    return node;
  }

  function isObject(value) {
    return value && typeof value === "object" && !Array.isArray(value);
  }

  function displayValue(value) {
    if (value == null || value === "") return "—";
    if (Array.isArray(value)) return value.map(displayValue).join("、");
    if (isObject(value)) {
      return Object.entries(value)
        .filter((entry) => entry[1] != null && entry[1] !== "")
        .map((entry) => `${entry[0]}：${displayValue(entry[1])}`)
        .join("；");
    }
    return String(value);
  }

  function stateFrom(result) {
    if (result.status === "clarify" || result.clarify) return "clarify";
    if (result.status === "failed") return "error";
    if (result.status === "rejected") return "unauthorized";
    const codes = new Set((result.warnings || []).map((item) => item.code));
    if (codes.has("EMPTY_RESULT")) return "empty";
    if (codes.has("RETRIEVAL_DEGRADED") || result.status === "degraded") return "degraded";
    if (codes.has("LOW_CONFIDENCE")) return "low-confidence";
    return "success";
  }

  function csvCell(value) {
    const text = value == null ? "" : String(value);
    return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  }

  function downloadCsv(result) {
    const data = result && result.data;
    if (!data || !Array.isArray(data.columns) || !Array.isArray(data.rows)) return false;
    const lines = [data.columns.map(csvCell).join(",")];
    data.rows.forEach((row) => lines.push((row || []).map(csvCell).join(",")));
    const blob = new Blob(["\ufeff", lines.join("\r\n")], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `assistant-result-${Date.now()}.csv`;
    link.click();
    URL.revokeObjectURL(url);
    return true;
  }

  class AssistantPanel {
    constructor(options) {
      this.root = options.root;
      this.api = options.api;
      this.contextProvider = options.contextProvider || (() => ({ page: "assistant" }));
      this.questions = options.recommendations || DEFAULT_QUESTIONS;
      this.sessionId = null;
      this.currentResult = null;
      this.busy = false;
      this.renderShell();
      this.renderInitial();
      window.addEventListener("nl2sql:identity-changed", () => this.reset());
    }

    renderShell() {
      this.root.classList.add("v3-assistant-panel");
      this.root.setAttribute("aria-label", "教学数据智能助手");

      const hero = el("header", "v3ap-hero");
      const mark = el("div", "v3ap-mark", "AI");
      const copy = el("div", "v3ap-hero-copy");
      copy.append(el("span", "v3ap-eyebrow", "UNIFIED TEACHING ASSISTANT"));
      copy.append(el("h2", "", "教学数据智能助手"));
      copy.append(el("p", "", "基于当前工作身份与页面范围回答，并在执行任何业务动作前等待你确认。"));
      const reset = button("新会话", "v3ap-reset");
      reset.addEventListener("click", () => this.reset());
      hero.append(mark, copy, reset);

      this.thread = el("section", "v3ap-thread");
      this.thread.setAttribute("aria-live", "polite");
      this.thread.setAttribute("aria-busy", "false");

      const composer = el("form", "v3ap-composer");
      composer.setAttribute("aria-label", "向智能助手提问");
      this.input = el("textarea", "v3ap-input");
      this.input.rows = 2;
      this.input.maxLength = 500;
      this.input.placeholder = "询问课程、作业、考勤、成绩、支持事项或教学运行数据…";
      this.submit = button("发送", "v3ap-submit");
      this.submit.type = "submit";
      const hint = el("div", "v3ap-composer-hint");
      hint.append(el("span", "", "仅使用服务端确认的权限范围"), el("kbd", "", "Ctrl + Enter"));
      composer.append(this.input, this.submit, hint);
      composer.addEventListener("submit", (event) => {
        event.preventDefault();
        this.ask(this.input.value);
      });
      this.input.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
          event.preventDefault();
          composer.requestSubmit();
        }
      });

      this.root.replaceChildren(hero, this.thread, composer);
    }

    renderInitial() {
      this.thread.replaceChildren();
      const card = el("article", "v3ap-welcome");
      card.append(el("span", "v3ap-state-label", "READY"));
      card.append(el("h3", "", "从一个具体问题开始"));
      card.append(el("p", "", "助手会展示数据范围、证据、质量提示和待确认动作；不会在浏览器中扩大或推断权限。"));
      const list = el("div", "v3ap-recommendations");
      this.questions.forEach((question) => {
        const item = button(question, "v3ap-question-chip");
        item.addEventListener("click", () => this.ask(question));
        list.append(item);
      });
      card.append(list);
      this.thread.append(card);
    }

    reset() {
      this.sessionId = null;
      this.currentResult = null;
      this.busy = false;
      this.input.value = "";
      this.setBusy(false);
      this.renderInitial();
    }

    setContext(context) {
      const next = { ...(context || {}) };
      if (!next.page) next.page = "assistant";
      const previous = JSON.stringify(this.contextProvider());
      const current = JSON.stringify(next);
      this.contextProvider = () => ({ ...next });
      if (previous !== current) this.reset();
    }

    prefill(question) {
      this.input.value = String(question || "").slice(0, this.input.maxLength || 500);
      this.input.focus();
    }

    setBusy(value) {
      this.busy = value;
      this.submit.disabled = value;
      this.input.disabled = value;
      this.submit.textContent = value ? "处理中…" : "发送";
      this.thread.setAttribute("aria-busy", value ? "true" : "false");
    }

    appendQuestion(question) {
      const row = el("article", "v3ap-message v3ap-message-user");
      row.append(el("span", "v3ap-avatar", "我"), el("p", "", question));
      this.thread.append(row);
    }

    appendLoading() {
      const row = el("article", "v3ap-loading");
      row.dataset.loading = "true";
      row.append(el("span", "v3ap-spinner"));
      const copy = el("div");
      copy.append(el("b", "", "正在核对范围并组织回答"), el("p", "", "服务端正在验证当前身份、页面上下文和可用数据。"));
      row.append(copy);
      this.thread.append(row);
    }

    removeLoading() {
      this.thread.querySelector('[data-loading="true"]')?.remove();
    }

    async ask(rawQuestion) {
      const question = String(rawQuestion || "").trim();
      if (!question || this.busy) return;
      if (typeof this.api.queryAssistant !== "function") {
        this.renderTransportError(
          new Error("前端资源版本不一致，请刷新页面后重试。"),
          false,
        );
        return;
      }
      this.appendQuestion(question);
      this.input.value = "";
      this.appendLoading();
      this.setBusy(true);
      this.scrollToEnd();
      try {
        const payload = {
          question,
          context: this.contextProvider(),
          options: { include_sql: true, include_trace: false, max_rows: 100 },
        };
        if (this.sessionId) payload.session_id = this.sessionId;
        const result = await this.api.queryAssistant(payload);
        this.sessionId = result.session_id;
        this.currentResult = result;
        this.removeLoading();
        this.renderAnswer(result);
      } catch (error) {
        this.removeLoading();
        const unauthorized = error && (error.status === 401 || error.status === 403);
        this.renderTransportError(error, unauthorized);
      } finally {
        this.setBusy(false);
        this.input.focus();
        this.scrollToEnd();
      }
    }

    renderTransportError(error, unauthorized) {
      const card = el("article", `v3ap-answer is-${unauthorized ? "unauthorized" : "error"}`);
      card.append(el("span", "v3ap-state-label", unauthorized ? "ACCESS DENIED" : "SERVICE ERROR"));
      card.append(el("h3", "", unauthorized ? "当前工作身份无权完成此请求" : "服务暂时不可用"));
      card.append(el("p", "v3ap-answer-text", error?.message || "请稍后重试。"));
      this.thread.append(card);
    }

    renderAnswer(result) {
      const state = stateFrom(result);
      const card = el("article", `v3ap-answer is-${state}`);
      card.dataset.state = state;
      const heading = this.stateHeading(state);
      card.append(el("span", "v3ap-state-label", heading.label));
      card.append(el("h3", "", heading.title));
      const answer = result.answer || result.clarify || result.error?.message || heading.fallback;
      if (answer) card.append(el("p", "v3ap-answer-text", answer));

      this.renderWarnings(card, result.warnings || []);
      this.renderScope(card, result);
      this.renderMetricDefinitions(card, result.metric_definitions || []);
      this.renderData(card, result.data);
      this.renderEvidence(card, result.evidence || []);
      this.renderSql(card, result.sql);
      this.renderTrace(card, result.trace_summary);
      this.renderSuggestedQuestions(card, result.suggested_questions || []);
      this.renderActions(card, result.suggested_actions || []);
      this.thread.append(card);
    }

    stateHeading(state) {
      const items = {
        clarify: { label: "NEEDS CLARIFICATION", title: "还需要一点信息", fallback: "请补充范围或口径后继续提问。" },
        success: { label: "ANSWER READY", title: "回答已生成", fallback: "查询已完成。" },
        empty: { label: "NO RESULT", title: "当前范围没有匹配数据", fallback: "可以调整时间或筛选条件后重试。" },
        "low-confidence": { label: "REVIEW ADVISED", title: "回答已生成，建议复核", fallback: "当前可信度较低。" },
        degraded: { label: "DEGRADED", title: "回答已生成，但部分检索降级", fallback: "请结合证据与提示复核。" },
        unauthorized: { label: "ACCESS DENIED", title: "当前工作身份无权完成此请求", fallback: "请检查当前页面和工作身份。" },
        error: { label: "SERVICE ERROR", title: "本次回答未完成", fallback: "请稍后重试。" },
      };
      return items[state] || items.success;
    }

    renderWarnings(card, warnings) {
      if (!warnings.length) return;
      const box = el("section", "v3ap-warnings");
      warnings.forEach((warning) => {
        const item = el("div", `v3ap-warning is-${warning.severity || "warning"}`);
        item.append(el("b", "", WARNING_TITLES[warning.code] || "质量提示"));
        item.append(el("span", "", warning.message || warning.code || "请复核当前结果。"));
        box.append(item);
      });
      card.append(box);
    }

    renderScope(card, result) {
      const scope = result.scope || {};
      const timeRange = result.time_range;
      if (!Object.keys(scope).length && !timeRange) return;
      const section = this.section("回答范围", "服务端最终采用的身份与数据范围");
      const chips = el("div", "v3ap-scope-chips");
      Object.entries(scope).forEach(([key, value]) => {
        if (value == null || value === "" || isObject(value)) return;
        chips.append(el("span", "v3ap-scope-chip", `${key} · ${displayValue(value)}`));
      });
      if (timeRange) chips.append(el("span", "v3ap-scope-chip", `时间 · ${displayValue(timeRange)}`));
      section.append(chips);
      card.append(section);
    }

    renderMetricDefinitions(card, definitions) {
      if (!definitions.length) return;
      const section = this.section("指标口径", "认证指标名称与计算说明");
      const list = el("div", "v3ap-definition-list");
      definitions.forEach((definition) => {
        const item = el("article", "v3ap-definition");
        item.append(el("b", "", definition.name || definition.code || "指标"));
        item.append(el("p", "", definition.formula || definition.description || definition.definition || ""));
        list.append(item);
      });
      section.append(list);
      card.append(section);
    }

    renderData(card, data) {
      if (!data || !Array.isArray(data.columns) || !Array.isArray(data.rows) || !data.columns.length) return;
      const section = this.section("结果数据", `${data.row_count ?? data.rows.length} 行${data.truncated ? " · 已截断" : ""}`);
      const scroll = el("div", "v3ap-table-scroll");
      const table = el("table", "v3ap-table");
      const head = el("thead");
      const headRow = el("tr");
      data.columns.forEach((column) => headRow.append(el("th", "", column)));
      head.append(headRow);
      const body = el("tbody");
      data.rows.forEach((row) => {
        const tr = el("tr");
        (row || []).forEach((value) => tr.append(el("td", "", displayValue(value))));
        body.append(tr);
      });
      table.append(head, body);
      scroll.append(table);
      section.append(scroll);
      card.append(section);
    }

    renderEvidence(card, evidence) {
      if (!evidence.length) return;
      const section = this.section("证据与来源", "结果从哪里来、何时更新");
      const list = el("div", "v3ap-evidence-list");
      evidence.forEach((source) => {
        const item = el("article", "v3ap-evidence");
        item.append(el("b", "", source.label || source.kind || "数据来源"));
        const details = [source.source, source.updated_at, source.time_semantics].filter(Boolean).join(" · ");
        if (details) item.append(el("span", "", details));
        list.append(item);
      });
      section.append(list);
      card.append(section);
    }

    renderSql(card, sql) {
      if (!sql) return;
      const details = el("details", "v3ap-sql");
      details.append(el("summary", "", "查看生成 SQL"));
      details.append(el("pre", "", sql));
      card.append(details);
    }

    renderTrace(card, trace) {
      if (!trace || !Object.keys(trace).length) return;
      const details = el("details", "v3ap-trace");
      details.append(el("summary", "", "查看执行摘要"));
      const grid = el("dl", "v3ap-trace-grid");
      Object.entries(trace).forEach(([key, value]) => {
        if (isObject(value) || Array.isArray(value)) return;
        grid.append(el("dt", "", key), el("dd", "", displayValue(value)));
      });
      details.append(grid);
      card.append(details);
    }

    renderSuggestedQuestions(card, questions) {
      if (!questions.length) return;
      const section = this.section("继续追问", "沿用当前会话与服务端范围");
      const list = el("div", "v3ap-followups");
      questions.forEach((question) => {
        const item = button(question, "v3ap-question-chip");
        item.addEventListener("click", () => this.ask(question));
        list.append(item);
      });
      section.append(list);
      card.append(section);
    }

    renderActions(card, actions) {
      if (!actions.length) return;
      const section = this.section("待确认动作", "预览服务端校验后的动作；确认时会再次鉴权");
      const list = el("div", "v3ap-action-list");
      actions.forEach((action) => list.append(this.actionCard(action)));
      section.append(list);
      card.append(section);
    }

    actionCard(action) {
      const item = el("article", "v3ap-action");
      const head = el("div", "v3ap-action-head");
      const copy = el("div");
      copy.append(el("span", "", action.type || "action"));
      copy.append(el("b", "", action.label || action.preview?.label || "确认动作"));
      const confirm = button("确认执行", "v3ap-action-confirm");
      head.append(copy, confirm);
      item.append(head);
      const preview = el("dl", "v3ap-action-preview");
      Object.entries(action.preview || {}).forEach(([key, value]) => {
        if (key === "mutates_data" || value == null || value === "") return;
        preview.append(el("dt", "", key), el("dd", "", displayValue(value)));
      });
      if (preview.children.length) item.append(preview);
      item.append(el("p", "v3ap-action-note", action.requires_confirmation ? "此动作尚未执行。确认后服务端会重新检查当前身份和数据范围。" : "服务端未要求额外确认。"));
      confirm.addEventListener("click", () => this.confirmAction(action, item, confirm));
      return item;
    }

    async confirmAction(action, card, confirm) {
      if (!action.draft_id || confirm.disabled) return;
      confirm.disabled = true;
      confirm.textContent = "确认中…";
      try {
        const response = await this.api.confirmAssistantAction(action.draft_id);
        const draft = response.item;
        card.classList.add("is-confirmed");
        confirm.textContent = "已确认";
        card.querySelector(".v3ap-action-note").textContent = this.actionResultMessage(draft.result);
        this.applyConfirmedAction(draft.result);
      } catch (error) {
        card.classList.add("is-failed");
        confirm.textContent = error?.status === 410 ? "已过期" : "确认失败";
        card.querySelector(".v3ap-action-note").textContent = error?.message || "动作未执行，请重新生成。";
      }
    }

    actionResultMessage(result) {
      if (!result) return "动作已经确认。";
      if (result.kind === "navigation") return "已确认安全导航，正在打开目标页面。";
      if (result.kind === "client_export") return "已确认导出当前结果。";
      if (result.kind === "business_draft") return "课程公告草稿已保存，正在打开课程空间；请在“待发布草稿”中明确发布。";
      if (result.kind === "governance_feedback") return "治理反馈已提交。";
      return "动作已经确认。";
    }

    applyConfirmedAction(result) {
      if (!result) return;
      if (result.kind === "navigation") {
        window.dispatchEvent(new CustomEvent("nl2sql:assistant:navigate", { detail: result }));
      } else if (result.kind === "business_draft" && result.target_view) {
        window.dispatchEvent(new CustomEvent("nl2sql:assistant:navigate", { detail: { kind: "navigation", target_view: result.target_view, context: { teaching_class_id: result.teaching_class_id } } }));
      } else if (result.kind === "client_export") {
        downloadCsv(this.currentResult);
      }
    }

    section(title, subtitle) {
      const section = el("section", "v3ap-section");
      const head = el("header", "v3ap-section-head");
      head.append(el("b", "", title), el("span", "", subtitle));
      section.append(head);
      return section;
    }

    scrollToEnd() {
      this.thread.scrollTop = this.thread.scrollHeight;
    }
  }

  function create(options) {
    if (!options || !options.root || !options.api) throw new Error("助手组件缺少挂载节点或 API 客户端");
    return new AssistantPanel(options);
  }

  window.NL2SQLAssistantPanel = { create, stateFrom };

  const autoRoot = document.querySelector("[data-assistant-panel]");
  if (autoRoot && window.NL2SQLApi) {
    window.NL2SQLAssistantPanelInstance = create({
      root: autoRoot,
      api: window.NL2SQLApi,
      contextProvider: () => ({ page: autoRoot.dataset.page || "assistant" }),
    });
  }
})();
