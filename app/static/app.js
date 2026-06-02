const $ = (id) => document.getElementById(id);

const form = $("ask-form");
const questionEl = $("question");
const submitBtn = $("submit-btn");
const clearBtn = $("clear-btn");
const historyBadge = $("history-badge");
const errorBox = $("error-box");
const errorMsg = $("error-msg");
const sqlBox = $("sql-box");
const sqlText = $("sql-text");
const metaText = $("meta-text");
const resultBox = $("result-box");
const thead = $("result-thead");
const tbody = $("result-tbody");
const emptyHint = $("empty-hint");
const copyBtn = $("copy-btn");

const HISTORY_KEY = "nl2sql.history.v1";
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

function updateHistoryBadge() {
  const n = loadHistory().length;
  historyBadge.textContent = n === 0 ? "未开始会话" : `已记 ${n} 轮(发送最近 ${Math.min(n, MAX_HISTORY_TURNS)} 轮上下文)`;
}

function show(el) { el.hidden = false; }
function hide(el) { el.hidden = true; }

function renderTable(columns, rows, sources) {
  thead.innerHTML = "";
  tbody.innerHTML = "";
  const hasSources = Array.isArray(sources) && sources.length === columns.length;
  for (let i = 0; i < columns.length; i++) {
    const th = document.createElement("th");
    const alias = columns[i];
    const src = hasSources ? (sources[i] || "") : "";
    if (src && src !== alias) {
      // 双行表头:主标题(别名) + 灰色小字(源表达式)
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
    const resp = await fetch("/api/schema");
    if (!resp.ok) return;
    const data = await resp.json();
    $("schema-text").textContent = data.ddl;
  } catch (e) {
    $("schema-text").textContent = "(加载失败)";
  }
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const question = questionEl.value.trim();
  if (!question) return;

  hide(errorBox);
  hide(sqlBox);
  hide(resultBox);
  submitBtn.disabled = true;
  submitBtn.setAttribute("aria-busy", "true");
  submitBtn.textContent = "查询中…";

  const history = loadHistory().slice(-MAX_HISTORY_TURNS);

  try {
    const resp = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, history }),
    });
    const data = await resp.json();

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

      // 仅追加成功且非"无法回答"占位的轮次
      const isPlaceholder = data.columns.length === 1 && data.columns[0] === "error";
      if (data.sql && !isPlaceholder) {
        const next = loadHistory();
        next.push({ question, sql: data.sql });
        saveHistory(next.slice(-MAX_HISTORY_TURNS * 2));  // 本地多存一点,发送时再截
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
  localStorage.removeItem(HISTORY_KEY);
  updateHistoryBadge();
});

copyBtn.addEventListener("click", async () => {
  await navigator.clipboard.writeText(sqlText.textContent);
  copyBtn.textContent = "已复制";
  setTimeout(() => (copyBtn.textContent = "复制"), 1200);
});

loadSchema();
updateHistoryBadge();
