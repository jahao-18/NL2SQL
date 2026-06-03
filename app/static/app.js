const $ = (id) => document.getElementById(id);

const form = $("ask-form");
const questionEl = $("question");
const submitBtn = $("submit-btn");
const clearBtn = $("clear-btn");
const historyBadge = $("history-badge");
const errorBox = $("error-box");
const errorMsg = $("error-msg");
const clarifyBox = $("clarify-box");
const clarifyMsg = $("clarify-msg");
const sqlBox = $("sql-box");
const sqlText = $("sql-text");
const metaRow = $("meta-row");
const metaText = $("meta-text");
const resultBox = $("result-box");
const thead = $("result-thead");
const tbody = $("result-tbody");
const emptyHint = $("empty-hint");
const copyBtn = $("copy-btn");
const sourceSelect = $("source-select");
const themeToggle = $("theme-toggle");
const routedSource = $("routed-source");
const routedText = $("routed-text");

// 会话首轮路由选定的数据源;多轮追问复用它,避免串库。新会话/手动切换时重置。
let conversationSource = null;

const HISTORY_KEY = "nl2sql.history.v1";
const THEME_KEY = "nl2sql.theme.v1";
const MAX_HISTORY_TURNS = 5;

/* ---------------- theme ---------------- */

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
}

themeToggle.addEventListener("click", () => {
  const current = document.documentElement.getAttribute("data-theme") || "light";
  const next = current === "dark" ? "light" : "dark";
  applyTheme(next);
  localStorage.setItem(THEME_KEY, next);
});

/* ---------------- history ---------------- */

function loadHistory() {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveHistory(history) {
  localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
}

function clearHistory() {
  localStorage.removeItem(HISTORY_KEY);
  updateHistoryBadge();
}

function updateHistoryBadge() {
  const n = loadHistory().length;
  historyBadge.textContent = n === 0
    ? "未开始会话"
    : `已记 ${n} 轮 · 发送最近 ${Math.min(n, MAX_HISTORY_TURNS)} 轮`;
}

function show(el) { el.hidden = false; }
function hide(el) { el.hidden = true; }

function hideAllStateCards() {
  hide(errorBox);
  hide(clarifyBox);
  hide(sqlBox);
  hide(resultBox);
}

// 下拉显式选择的库(为空表示「自动识别」)
function manualSource() {
  return sourceSelect.value || null;
}

// 本次提问最终发给后端的 source:手动选择优先;否则沿用会话已路由的库;都没有则为 null(由后端路由)
function effectiveSource() {
  return manualSource() || conversationSource;
}

function showRoutedSource(data) {
  if (!data || !data.source) {
    hide(routedSource);
    return;
  }
  const label = data.source_label || data.source;
  routedText.textContent = data.auto_routed
    ? `数据源:${label} · 系统自动识别`
    : `数据源:${label}`;
  show(routedSource);
}

/* ---------------- render ---------------- */

function renderTable(columns, rows, sources) {
  thead.innerHTML = "";
  tbody.innerHTML = "";
  const hasSources = Array.isArray(sources) && sources.length === columns.length;
  for (let i = 0; i < columns.length; i++) {
    const th = document.createElement("th");
    const alias = columns[i];
    const src = hasSources ? (sources[i] || "") : "";
    if (src && src !== alias) {
      const nameDiv = document.createElement("div");
      nameDiv.textContent = alias;
      const srcDiv = document.createElement("small");
      srcDiv.textContent = src;
      th.appendChild(nameDiv);
      th.appendChild(srcDiv);
    } else {
      th.textContent = alias;
    }
    thead.appendChild(th);
  }
  for (const row of rows) {
    const tr = document.createElement("tr");
    for (const cell of row) {
      const td = document.createElement("td");
      td.textContent = cell === null ? "NULL" : String(cell);
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }
  emptyHint.hidden = rows.length !== 0;
}

function renderMeta(data) {
  metaRow.innerHTML = "";
  const pill1 = document.createElement("span");
  pill1.className = "meta-pill";
  pill1.textContent = `${data.row_count} 行`;
  metaRow.appendChild(pill1);

  const pill2 = document.createElement("span");
  pill2.className = "meta-pill";
  pill2.textContent = `${data.elapsed_ms} ms`;
  metaRow.appendChild(pill2);

  if (data.truncated) {
    const pill3 = document.createElement("span");
    pill3.className = "meta-pill warn";
    pill3.textContent = "结果已截断";
    metaRow.appendChild(pill3);
  }
}

/* ---------------- data fetching ---------------- */

async function loadSchema(forceSource) {
  const target = $("schema-text");
  try {
    const src = forceSource || manualSource();
    const url = src ? `/api/schema?source=${encodeURIComponent(src)}` : "/api/schema";
    const resp = await fetch(url);
    if (!resp.ok) {
      target.textContent = `(加载失败: HTTP ${resp.status})`;
      return;
    }
    const data = await resp.json();
    target.textContent = data.ddl;
  } catch (e) {
    target.textContent = "(加载失败)";
  }
}

async function loadSources() {
  try {
    const resp = await fetch("/api/sources");
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    // 第一项始终是「自动识别」(value 为空 => 后端按问题路由)
    sourceSelect.innerHTML = `<option value="">🤖 自动识别</option>`;
    for (const s of data.sources) {
      const opt = document.createElement("option");
      opt.value = s.name;
      opt.textContent = `${s.label} · ${s.dialect}`;
      sourceSelect.appendChild(opt);
    }
    // 默认停在「自动识别」,体现数据源透明化
    sourceSelect.value = "";
  } catch (e) {
    sourceSelect.innerHTML = `<option value="">(数据源加载失败)</option>`;
  }
}

/* ---------------- events ---------------- */

sourceSelect.addEventListener("change", () => {
  // 手动切换数据源 => 开启新会话:清历史、清会话已路由的库
  conversationSource = null;
  if (loadHistory().length > 0) {
    clearHistory();
  }
  hide(routedSource);
  hideAllStateCards();
  loadSchema();
});

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const question = questionEl.value.trim();
  if (!question) return;

  hideAllStateCards();
  submitBtn.disabled = true;
  submitBtn.classList.add("is-loading");

  const history = loadHistory().slice(-MAX_HISTORY_TURNS);
  const source = effectiveSource();

  try {
    const resp = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, history, source }),
    });
    const data = await resp.json();

    // 透明展示本次实际使用的数据源,并锁定本会话后续追问到同一个库
    showRoutedSource(data);
    if (data.source) {
      conversationSource = data.source;
      loadSchema(data.source);
    }

    if (data.clarify) {
      clarifyMsg.textContent = data.clarify;
      show(clarifyBox);
      const next = loadHistory();
      next.push({ question, sql: `CLARIFY: ${data.clarify}`, kind: "clarify" });
      saveHistory(next.slice(-MAX_HISTORY_TURNS * 2));
      updateHistoryBadge();
      questionEl.value = "";
      questionEl.focus();
      return;
    }

    if (data.sql) {
      sqlText.textContent = data.sql;
      show(sqlBox);
    }

    if (data.error) {
      errorMsg.textContent = data.error;
      show(errorBox);
    } else {
      renderMeta(data);
      renderTable(data.columns, data.rows, data.column_sources);
      show(resultBox);

      const isPlaceholder = data.columns.length === 1 && data.columns[0] === "error";
      if (data.sql && !isPlaceholder) {
        const next = loadHistory();
        next.push({ question, sql: data.sql, kind: "sql" });
        saveHistory(next.slice(-MAX_HISTORY_TURNS * 2));
        updateHistoryBadge();
      }
    }
  } catch (err) {
    errorMsg.textContent = `请求失败: ${err.message}`;
    show(errorBox);
  } finally {
    submitBtn.disabled = false;
    submitBtn.classList.remove("is-loading");
  }
});

clearBtn.addEventListener("click", () => {
  if (loadHistory().length === 0 && !conversationSource) return;
  if (!confirm("清空当前会话?后续提问将重新自动识别数据源、且不带上下文。")) return;
  clearHistory();
  conversationSource = null;
  hide(routedSource);
  loadSchema();
});

copyBtn.addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(sqlText.textContent);
    const original = copyBtn.textContent;
    copyBtn.textContent = "已复制";
    setTimeout(() => (copyBtn.textContent = original), 1200);
  } catch (e) {
    // 静默失败
  }
});

// 跟随系统主题(未手动覆盖时)
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", (e) => {
  if (!localStorage.getItem(THEME_KEY)) {
    applyTheme(e.matches ? "dark" : "light");
  }
});

(async () => {
  await loadSources();
  await loadSchema();
  updateHistoryBadge();
})();
