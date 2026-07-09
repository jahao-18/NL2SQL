(function () {
  const api = window.NL2SQLApi;
  const $ = (id) => document.getElementById(id);
  const state = { sources: [], selectedSource: "", selectedTable: "", rows: null };

  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  function msg(text, kind) {
    const box = $("access-message");
    if (!box) return;
    box.textContent = text || "";
    box.className = `access-message ${kind || ""}`.trim();
  }

  function currentSource() {
    return state.sources.find((s) => s.name === state.selectedSource) || state.sources[0];
  }

  function renderSources() {
    const list = $("access-source-list");
    const sourceSelect = $("access-source-select");
    const tableSelect = $("access-table-select");
    if (!list || !sourceSelect || !tableSelect) return;

    list.innerHTML = state.sources.map((s) => `
      <button class="access-source-card ${s.name === state.selectedSource ? "active" : ""}" data-source="${esc(s.name)}" type="button">
        <b>${esc(s.label || s.name)}</b>
        <span>${esc(s.name)} · ${esc(s.dialect)} · ${s.table_count || 0} 表</span>
        <small>${s.writable ? "可维护" : "只读"} · ${esc(s.status || "published")}</small>
      </button>
    `).join("");
    list.querySelectorAll("[data-source]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.selectedSource = btn.dataset.source;
        const s = currentSource();
        state.selectedTable = (s && s.tables && s.tables[0]) || "";
        renderSources();
      });
    });

    sourceSelect.innerHTML = state.sources.map((s) => `<option value="${esc(s.name)}">${esc(s.label || s.name)}</option>`).join("");
    sourceSelect.value = state.selectedSource || (state.sources[0] && state.sources[0].name) || "";
    const selected = currentSource();
    const tables = (selected && selected.tables) || [];
    tableSelect.innerHTML = tables.map((t) => `<option value="${esc(t)}">${esc(t)}</option>`).join("");
    tableSelect.value = state.selectedTable || tables[0] || "";
    renderObjectTabs();
  }

  function renderObjectTabs() {
    const tabs = $("access-object-tabs");
    if (!tabs) return;
    const selected = currentSource();
    const tables = (selected && selected.tables) || [];
    tabs.querySelectorAll("[data-object-table]").forEach((btn) => {
      const available = tables.includes(btn.dataset.objectTable);
      btn.disabled = !available;
      btn.classList.toggle("active", btn.dataset.objectTable === state.selectedTable);
    });
  }

  async function selectObjectTable(table) {
    const selected = currentSource();
    const tables = (selected && selected.tables) || [];
    if (!tables.includes(table)) {
      msg("当前数据源没有对应的业务表", "err");
      return;
    }
    state.selectedTable = table;
    renderSources();
    await loadTable();
  }

  function renderTable(data) {
    const head = $("access-table-head");
    const body = $("access-table-body");
    if (!head || !body) return;
    const columns = data && data.columns || [];
    const rows = data && data.rows || [];
    head.innerHTML = `<tr>${columns.map((c) => `<th>${esc(c)}</th>`).join("")}<th>操作</th></tr>`;
    body.innerHTML = rows.map((row) => `
      <tr data-pk="${esc(row[columns[0]])}">
        ${columns.map((c) => `<td><input data-col="${esc(c)}" value="${esc(row[c])}" ${c === columns[0] ? "disabled" : ""}></td>`).join("")}
        <td class="access-row-actions">
          <button type="button" data-action="save">保存</button>
          <button type="button" data-action="delete">删除</button>
        </td>
      </tr>
    `).join("");
    body.querySelectorAll("[data-action='save']").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const tr = btn.closest("tr");
        const values = {};
        tr.querySelectorAll("input[data-col]").forEach((input) => {
          if (!input.disabled) values[input.dataset.col] = input.value;
        });
        await api.updateTableRow(state.selectedSource, state.selectedTable, tr.dataset.pk, values);
        msg("保存成功", "ok");
        await loadTable();
        await loadAudit();
      });
    });
    body.querySelectorAll("[data-action='delete']").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const tr = btn.closest("tr");
        if (!confirm("确认删除这条记录？")) return;
        await api.deleteTableRow(state.selectedSource, state.selectedTable, tr.dataset.pk);
        msg("删除成功", "ok");
        await loadTable();
        await loadAudit();
      });
    });
  }

  async function loadSources() {
    const data = await api.accessSources();
    state.sources = data.items || [];
    if (!state.selectedSource && state.sources[0]) state.selectedSource = state.sources[0].name;
    const s = currentSource();
    if (!state.selectedTable && s && s.tables && s.tables[0]) state.selectedTable = s.tables[0];
    renderSources();
  }

  async function loadTable() {
    state.selectedSource = $("access-source-select").value;
    state.selectedTable = $("access-table-select").value;
    if (!state.selectedSource || !state.selectedTable) return;
    const data = await api.tableRows(state.selectedSource, state.selectedTable, { limit: 50 });
    state.rows = data;
    renderTable(data);
  }

  async function loadAudit() {
    const box = $("access-audit-list");
    if (!box) return;
    const data = await api.dataAudit();
    const items = data.items || [];
    box.innerHTML = items.length ? items.map((item) => `
      <div class="access-audit-item">
        <b>${esc(item.action)} · ${esc(item.source)}.${esc(item.table)}</b>
        <span>${esc(item.actor)} · ${esc(item.created_at)} · pk=${esc(item.pk)}</span>
      </div>
    `).join("") : '<div class="access-empty">暂无审计记录</div>';
  }

  async function addRow() {
    if (!state.rows || !state.rows.columns || !state.rows.columns.length) return;
    const values = {};
    for (const col of state.rows.columns.slice(1)) {
      const value = prompt(`请输入 ${col} 的值，留空则写入空字符串`);
      if (value === null) return;
      values[col] = value;
    }
    await api.createTableRow(state.selectedSource, state.selectedTable, values);
    msg("新增成功", "ok");
    await loadTable();
    await loadAudit();
  }

  async function init() {
    if (!$("data-access-view") || !api) return;
    $("access-refresh-btn").addEventListener("click", async () => {
      await loadSources();
      await loadAudit();
    });
    $("access-load-table-btn").addEventListener("click", loadTable);
    $("access-add-row-btn").addEventListener("click", addRow);
    $("access-source-select").addEventListener("change", () => {
      state.selectedSource = $("access-source-select").value;
      state.selectedTable = "";
      renderSources();
    });
    $("access-table-select").addEventListener("change", () => {
      state.selectedTable = $("access-table-select").value;
    });

    document.querySelectorAll(".access-tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        document.querySelectorAll(".access-tab").forEach((t) => t.classList.remove("active"));
        tab.classList.add("active");
        $("sqlite-source-form").hidden = tab.dataset.accessTab !== "sqlite";
        $("csv-source-form").hidden = tab.dataset.accessTab !== "csv";
      });
    });
    const objectTabs = $("access-object-tabs");
    if (objectTabs) {
      objectTabs.querySelectorAll("[data-object-table]").forEach((btn) => {
        btn.addEventListener("click", () => selectObjectTable(btn.dataset.objectTable));
      });
    }

    $("sqlite-source-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        await api.registerSqliteSource({
          name: $("sqlite-source-name").value,
          label: $("sqlite-source-label").value,
          db_path: $("sqlite-source-path").value,
          writable: $("sqlite-source-writable").checked,
        });
        msg("SQLite 数据源接入成功", "ok");
        await loadSources();
      } catch (err) {
        msg(err.message, "err");
      }
    });

    $("csv-source-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const file = $("csv-file-input").files[0];
      if (!file) { msg("请选择 CSV 文件", "err"); return; }
      try {
        const csvText = await file.text();
        await api.importCsvSource({
          name: $("csv-source-name").value,
          label: $("csv-source-label").value,
          table_name: $("csv-table-name").value || "imported_data",
          csv_text: csvText,
          writable: $("csv-source-writable").checked,
        });
        msg("CSV 已导入为新数据源", "ok");
        await loadSources();
      } catch (err) {
        msg(err.message, "err");
      }
    });

    try {
      await loadSources();
      await loadAudit();
    } catch (err) {
      msg(err.message, "err");
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
