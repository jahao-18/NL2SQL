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
const metaText = $("meta-text");
const resultBox = $("result-box");
const thead = $("result-thead");
const tbody = $("result-tbody");
const emptyHint = $("empty-hint");
const copyBtn = $("copy-btn");
const sourceSelect = $("source-select");

const HISTORY_KEY = "nl2sql.history.v1";
const SOURCE_KEY = "nl2sql.source.v1";
const MAX_HISTORY_TURNS = 5;

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
  historyBadge.textContent = n === 0 ? "未开始会话" : `已记 ${n} 轮(发送最近 ${Math.min(n, MAX_HISTORY_TURNS)} 轮上下文)`;
}

function show(el) { el.hidden = false; }
function hide(el) { el.hidden = true; }

function currentSource() {
  return sourceSelect.value || null;
}

function renderTable(columns, rows, sources) {
  thead.innerHTML = "";
  tbody.innerHTML = "";
  const hasSources = Array.isArray(sources) && sources.length === columns.length;
  for (let i = 0; i < columns.length; i++) {
    const th = document.createElement("th");
    const alias = columns[i];
    const src = hasSources ? (sources[i] || "") : "";
    if (src && src !== alias) {
      th.innerHTML = "";
      const nameDiv = document.createElement("div");
      nameDiv.textContent = alias;
      const srcDiv = document.createElement("small");
      srcDiv.textContent = src;
      srcDiv.style.color = "var(--pico-muted-color)";
      srcDiv.style.fontWeight = "normal";
      srcDiv.style.display = "block";
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

async function loadSchema() {
  try {
    const src = currentSource();
    const url = src ? `/api/schema?source=${encodeURIComponent(src)}` : "/api/schema";
    const resp = await fetch(url);
    if (!resp.ok) {
      $("schema-text").textContent = `(加载失败: HTTP ${resp.status})`;
      return;
    }
    const data = await resp.json();
    $("schema-text").textContent = data.ddl;
  } catch (e) {
    $("schema-text").textContent = "(加载失败)";
  }
}

async function loadSources() {
  try {
    const resp = await fetch("/api/sources");
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    sourceSelect.innerHTML = "";
    for (const s of data.sources) {
      const opt = document.createElement("option");
      opt.value = s.name;
      opt.textContent = `${s.label} · ${s.dialect}`;
      sourceSelect.appendChild(opt);
    }
    const remembered = localStorage.getItem(SOURCE_KEY);
    const fallback = data.default || (data.sources[0] && data.sources[0].name);
    const valid = data.sources.some(s => s.name === remembered);
    sourceSelect.value = valid ? remembered : fallback;
  } catch (e) {
    sourceSelect.innerHTML = `<option value="">(数据源加载失败)</option>`;
  }
}

sourceSelect.addEventListener("change", () => {
  const src = currentSource();
  if (src) localStorage.setItem(SOURCE_KEY, src);
  // 跨库历史无意义,切换时清空 history 并提示
  if (loadHistory().length > 0) {
    clearHistory();
  }
  hide(errorBox);
  hide(clarifyBox);
  hide(sqlBox);
  hide(resultBox);
  loadSchema();
});

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const question = questionEl.value.trim();
  if (!question) return;

  hide(errorBox);
  hide(clarifyBox);
  hide(sqlBox);
  hide(resultBox);
  submitBtn.disabled = true;
  submitBtn.setAttribute("aria-busy", "true");
  submitBtn.textContent = "查询中…";

  const history = loadHistory().slice(-MAX_HISTORY_TURNS);
  const source = currentSource();

  try {
    const resp = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, history, source }),
    });
    const data = await resp.json();

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
      let meta = `返回 ${data.row_count} 行 · 耗时 ${data.elapsed_ms} ms`;
      if (data.truncated) {
        meta += ` · ⚠️ 结果已截断`;
      }
      metaText.textContent = meta;
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
    submitBtn.removeAttribute("aria-busy");
    submitBtn.textContent = "查询";
  }
});

clearBtn.addEventListener("click", () => {
  if (loadHistory().length === 0) return;
  if (!confirm("清空当前会话历史?后续提问将不再带上下文。")) return;
  clearHistory();
});

copyBtn.addEventListener("click", async () => {
  await navigator.clipboard.writeText(sqlText.textContent);
  copyBtn.textContent = "已复制";
  setTimeout(() => (copyBtn.textContent = "复制"), 1200);
});

(async () => {
  await loadSources();
  await loadSchema();
  updateHistoryBadge();
})();
