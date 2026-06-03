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
  const resultHeader = $("result-table-header");
  const thead = $("result-thead");
  const tbody = $("result-tbody");
  const emptyHint = $("empty-hint");

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

  const HISTORY_KEY = "nl2sql.history.v1";
  const GLOSSARY_KEY = "nl2sql.glossary.v1";  // 后接 .<source>
  const MAX_HISTORY_TURNS = 5;
  const MAX_GLOSSARY = 50;

  // 会话首轮路由选定的数据源;多轮追问复用它,避免串库。新会话/手动切换时重置。
  let conversationSource = null;
  // 下拉/标签显式选择的库(为空表示「自动识别」)
  let selectedSource = "";

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

  /* ---------------- 我的术语表(按库存 localStorage) ---------------- */

  // 当前术语表归属的库:手动选的优先,否则会话当前库
  function glossarySource() { return manualSource() || conversationSource; }

  function loadGlossary(source) {
    if (!source) return [];
    try { return JSON.parse(localStorage.getItem(GLOSSARY_KEY + "." + source)) || []; }
    catch { return []; }
  }
  function saveGlossary(source, arr) {
    if (!source) return;
    localStorage.setItem(GLOSSARY_KEY + "." + source, JSON.stringify(arr.slice(0, MAX_GLOSSARY)));
  }

  function renderGlossary() {
    const src = glossarySource();
    glossarySourceName.textContent = src || "当前数据源";
    const entries = loadGlossary(src);
    glossaryList.innerHTML = "";
    if (!src || entries.length === 0) {
      glossaryEmpty.hidden = false;
      glossaryEmpty.textContent = src
        ? "当前数据源还没有自定义术语,在上面输入框添加。"
        : "当前数据源还没有自定义术语。提问一次确定数据源后,或在上方手动选库,即可添加。";
    } else {
      glossaryEmpty.hidden = true;
      entries.forEach((text, i) => {
        const li = document.createElement("li");
        const span = document.createElement("span");
        span.textContent = text;
        const del = document.createElement("button");
        del.type = "button"; del.textContent = "×"; del.title = "删除";
        del.addEventListener("click", () => {
          const arr = loadGlossary(src); arr.splice(i, 1); saveGlossary(src, arr); renderGlossary();
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
    const arr = loadGlossary(src);
    if (arr.length >= MAX_GLOSSARY) { alert(`每个库最多 ${MAX_GLOSSARY} 条术语`); return; }
    arr.push(text); saveGlossary(src, arr);
    glossaryInput.value = "";
    renderGlossary();
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

  /* ---------------- routed source ---------------- */

  function showRoutedSource(data) {
    if (!data || !data.source) { hide(routedSource); return; }
    const label = data.source_label || data.source;
    routedText.textContent = data.auto_routed
      ? `数据源:${label} · 系统自动识别`
      : `数据源:${label}`;
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
          td.style.color = "rgba(255,255,255,0.25)";
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
    return `<span class="confidence ${cls}" title="${tipAttr}">AI 准确率 ${c}%</span>`;
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

  // 异步补准确率勋章:结果已先渲染,这里凭 judge_id 请求评估,先挂"评估中"占位,回来后替换为真实勋章。
  async function fetchConfidence(data) {
    if (!data.judge_id) return;
    const pending = document.createElement("span");
    pending.className = "confidence conf-pending";
    pending.title = "正在评估本次回答的可信度…";
    pending.textContent = "AI 准确率 评估中…";
    sqlMeta.appendChild(pending);
    try {
      const resp = await fetch("/api/judge", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ judge_id: data.judge_id }),
      });
      const jd = await resp.json();
      // 期间用户可能又发了新查询,sqlMeta 已被刷新,此时占位已脱离文档 -> 不再回填。
      if (!pending.isConnected) return;
      if (typeof jd.confidence === "number") {
        pending.outerHTML = confidenceBadge(jd.confidence, jd.confidence_detail);
      } else {
        pending.remove();
      }
    } catch (e) {
      pending.remove();
    }
  }

  /* ---------------- data fetching ---------------- */

  async function loadSchema(forceSource) {
    try {
      const src = forceSource || manualSource();
      const url = src ? `/api/schema?source=${encodeURIComponent(src)}` : "/api/schema";
      const resp = await fetch(url);
      if (!resp.ok) { schemaText.textContent = `(加载失败: HTTP ${resp.status})`; return; }
      const data = await resp.json();
      schemaText.textContent = data.ddl;
    } catch {
      schemaText.textContent = "(加载失败)";
    }
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
        sourceTags.querySelectorAll(".source-tag").forEach((t) => t.classList.remove("active"));
        tag.classList.add("active");
        selectedSource = tag.dataset.src || "";
        // 手动切换数据源 => 开启新会话:清历史、清会话已路由的库
        conversationSource = null;
        if (loadHistory().length > 0) clearHistory();
        hide(routedSource);
        hideAllStateCards();
        loadSchema();
        renderGlossary();   // 切到该库的术语表(选「自动识别」时 src 为空,显示提示)
      });
    });
  }

  async function loadSources() {
    try {
      const resp = await fetch("/api/sources");
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      renderSourceTags(data.sources || []);
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
    const userGlossary = loadGlossary(glossarySource());  // 当前库的自定义术语,自动带上

    startProgress(!source);   // 手动锁库时跳过"判断数据源"阶段

    try {
      const resp = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, history, source, current_source: currentSource,
                               user_glossary: userGlossary }),
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
        resultHeader.textContent = `查询结果 · ${rowCount} 行`;
        renderTable(data.columns, data.rows, data.column_sources);
        resultWrap.classList.add("visible");
        fetchConfidence(data);   // 结果已出,异步补准确率勋章(不阻塞结果显示)

        const isPlaceholder = data.columns.length === 1 && data.columns[0] === "error";
        if (data.sql && !isPlaceholder) {
          const next = loadHistory();
          next.push({ question, sql: data.sql, kind: "sql" });
          saveHistory(next.slice(-MAX_HISTORY_TURNS * 2));
          updateHistoryBadge();
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
  });

  sqlCopy.addEventListener("click", () => {
    const text = sqlCode.textContent || "";
    navigator.clipboard.writeText(text).then(() => {
      sqlCopy.textContent = "已复制 ✓";
      sqlCopy.classList.add("copied");
      setTimeout(() => { sqlCopy.textContent = "复制"; sqlCopy.classList.remove("copied"); }, 1500);
    }).catch(() => {});
  });

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
    renderGlossary();
  })();
})();
