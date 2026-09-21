(function () {
  "use strict";

  const FIELD_META = window.FIELD_META;
  const COL_TIPS = window.COL_TIPS;
  const FREE_COLS = window.FREE_COLS; // [id, label, defaultVisible]
  const FIXED_COLS = [["code", "代碼"], ["name", "名稱"]];

  const COL_VIS_KEY = "wr_col_visible_v1";

  const state = {
    watchlist: [],
    conditions: [],
    activeConds: new Set(),
    curCode: null,
    allRows: [],
    displayRows: [],
    colVisible: loadColVisible(),
    condDraft: null,
    condTabIdx: 0,
    sortCol: null,
    sortRev: true,
  };

  function loadColVisible() {
    try {
      const saved = JSON.parse(localStorage.getItem(COL_VIS_KEY) || "null");
      if (saved) return saved;
    } catch (e) {}
    const v = {};
    FREE_COLS.forEach(([id, , def]) => (v[id] = def));
    return v;
  }
  function saveColVisible() {
    try {
      localStorage.setItem(COL_VIS_KEY, JSON.stringify(state.colVisible));
    } catch (e) {}
  }

  async function api(path, opts) {
    const res = await fetch(path, Object.assign({ headers: { "Content-Type": "application/json" } }, opts));
    if (res.status === 401) {
      window.location.href = "/login";
      throw new Error("unauthorized");
    }
    return res.json();
  }

  function setStatus(text, color) {
    const el = document.getElementById("statusline");
    el.textContent = text;
    el.style.color = color || "";
  }

  // ── 時鐘 ──────────────────────────────────────────
  function tickClock() {
    const d = new Date();
    const pad = (n) => String(n).padStart(2, "0");
    document.getElementById("clock").textContent =
      `${d.getFullYear()}/${pad(d.getMonth() + 1)}/${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  }

  // ── 自選股 ────────────────────────────────────────
  async function loadWatchlist() {
    state.watchlist = await api("/api/watchlist");
    renderWatchlist();
  }

  function renderWatchlist() {
    const ul = document.getElementById("watchList");
    ul.innerHTML = "";
    state.watchlist.forEach((s) => {
      const li = document.createElement("li");
      if (s.code === state.curCode) li.classList.add("active");
      const chg = s.chg || 0;
      const color = chg > 0 ? "var(--red)" : chg < 0 ? "var(--green)" : "var(--fg2)";
      const span = document.createElement("span");
      span.style.color = color;
      span.textContent = `${s.code} ${s.name}`;
      span.style.cursor = "pointer";
      span.addEventListener("click", () => selectStock(s.code));
      const del = document.createElement("span");
      del.className = "del";
      del.textContent = "✕";
      del.title = "刪除";
      del.addEventListener("click", (e) => {
        e.stopPropagation();
        delStock(s.code);
      });
      li.appendChild(span);
      li.appendChild(del);
      ul.appendChild(li);
    });
  }

  async function addStock(code) {
    code = code.trim();
    if (!code) return;
    state.watchlist = await api("/api/watchlist", { method: "POST", body: JSON.stringify({ code }) });
    renderWatchlist();
    selectStock(code);
  }

  async function delStock(code) {
    state.watchlist = await api("/api/watchlist/" + encodeURIComponent(code), { method: "DELETE" });
    if (state.curCode === code) {
      state.curCode = null;
      state.allRows = [];
      renderTableHead();
      renderTableBody([]);
    }
    renderWatchlist();
  }

  // ── 查詢 ──────────────────────────────────────────
  function selectStock(code) {
    state.curCode = code;
    renderWatchlist();
    query();
  }

  async function query() {
    if (!state.curCode) return;
    setStatus("查詢中…", "var(--yellow)");
    const wtype = document.getElementById("wtype").value;
    const data = await api(`/api/quote?code=${encodeURIComponent(state.curCode)}&type=${encodeURIComponent(wtype)}`);
    state.conditions = data.conditions || state.conditions;
    renderCondButtons();

    if (!data.rows || !data.rows.length) {
      state.allRows = [];
      applyFilter();
      setStatus(wtype === "全部" ? "查無資料" : `查無資料（目前只查「${wtype}」，可切換「別」為全部再試）`, "var(--red)");
      return;
    }

    state.allRows = data.rows;
    if (data.stock) updateInfobar(data.stock);
    applyFilter();
    setStatus(`共 ${data.rows.length} 筆  ｜  ${new Date().toLocaleTimeString("zh-TW", { hour12: false })}`, "var(--green)");

    if (data.stock) checkFutures(state.curCode, data.stock.price);
  }

  function updateInfobar(stock) {
    const chg = stock.chg || 0;
    const color = chg > 0 ? "var(--red)" : chg < 0 ? "var(--green)" : "var(--fg2)";
    const sign = chg > 0 ? "+" : "";
    document.getElementById("stockName").textContent = `${stock.name}（${stock.code}）`;
    document.getElementById("stockPrice").textContent = stock.price;
    const chgEl = document.getElementById("stockChg");
    chgEl.textContent = `${sign}${chg.toFixed(2)}%`;
    chgEl.style.color = color;
    document.getElementById("stockVol").textContent = "成交量 " + Math.round(stock.vol || 0).toLocaleString();
    document.getElementById("stockSf").textContent = "";
  }

  async function checkFutures(code, price) {
    try {
      const data = await api(`/api/futures?code=${encodeURIComponent(code)}&price=${price || 0}`);
      const el = document.getElementById("stockSf");
      if (code !== state.curCode) return;
      if (data.has_sf) {
        const m = (data.margins || []).map(([lbl, amt]) => `${lbl} $${Math.round(amt).toLocaleString()}`).join("，");
        el.textContent = `✓ 有股期（${code}F）${m ? "  " + m : ""}`;
        el.style.color = "var(--red)";
      } else {
        el.textContent = "✗ 無股期";
        el.style.color = "var(--fg3)";
      }
    } catch (e) {}
  }

  // ── 快速篩選按鈕 ───────────────────────────────────
  function renderCondButtons() {
    const wrap = document.getElementById("condBtns");
    wrap.innerHTML = "";
    state.conditions.forEach((cond, i) => {
      if (!cond.rules || !cond.rules.length) return;
      const btn = document.createElement("button");
      btn.className = "cond-btn" + (state.activeConds.has(i) ? " active" : "");
      btn.textContent = cond.name;
      if (state.activeConds.has(i)) {
        btn.style.background = cond.color;
      }
      btn.addEventListener("click", () => {
        if (state.activeConds.has(i)) state.activeConds.delete(i);
        else state.activeConds.add(i);
        renderCondButtons();
        applyFilter();
      });
      wrap.appendChild(btn);
    });
  }

  document.getElementById("showAllBtn").addEventListener("click", () => {
    state.activeConds.clear();
    renderCondButtons();
    applyFilter();
  });

  // ── 篩選 + 排序 + 顯示 ─────────────────────────────
  function applyFilter() {
    let result;
    if (!state.activeConds.size) {
      result = state.allRows.slice();
    } else {
      result = state.allRows.filter((r) => {
        const conds = r._conds || [];
        for (const i of state.activeConds) {
          if (!conds[i]) return false;
        }
        return true;
      });
    }
    result.sort((a, b) => {
      const pa = (a._conds || []).filter(Boolean).length;
      const pb = (b._conds || []).filter(Boolean).length;
      if (pa !== pb) return pb - pa;
      return (a.sl_ratio || 99) - (b.sl_ratio || 99);
    });
    state.displayRows = result;
    state.sortCol = null;
    renderTableHead();
    renderTableBody(result);

    const counts = state.conditions.map((c, i) => `${c.name}:${state.allRows.filter((r) => (r._conds || [])[i]).length}`);
    const both = state.allRows.filter((r) => (r._conds || []).slice(0, 2).every(Boolean)).length;
    document.getElementById("statusline").textContent =
      `顯示 ${result.length} 筆 / 共 ${state.allRows.length} 筆  ｜  ${counts.join("  ｜  ")}  ｜  全過:${both}`;
  }

  // ── 欄位定義 ───────────────────────────────────────
  function getColDefs() {
    const defs = [];
    state.conditions.forEach((cond, i) => {
      if (cond.rules && cond.rules.length) defs.push([`cond_${i}`, cond.name]);
    });
    FIXED_COLS.forEach((c) => defs.push(c));
    FREE_COLS.forEach(([id, label]) => {
      if (state.colVisible[id]) defs.push([id, label]);
    });
    return defs;
  }

  function renderTableHead() {
    const tr = document.getElementById("theadRow");
    tr.innerHTML = "";
    getColDefs().forEach(([id, label]) => {
      const th = document.createElement("th");
      th.textContent = label;
      if (COL_TIPS[id]) th.title = COL_TIPS[id];
      th.addEventListener("click", () => sortByCol(id));
      tr.appendChild(th);
    });
  }

  function fmtCell(id, r) {
    const sign = (v) => (v > 0 ? "+" : "");
    switch (id) {
      case "code": return r.code;
      case "name": return r.name;
      case "sl_ratio": return (r.sl_ratio || 0).toFixed(4);
      case "eff_lev": return (r.eff_lev || 0).toFixed(1) + "x";
      case "spread_pct": return (r.spread_pct || 0).toFixed(2) + "%";
      case "moneyness": return sign(r.moneyness) + (r.moneyness || 0).toFixed(2) + "%";
      case "days": return String(parseInt(r.days || 0, 10));
      case "out_rate": return (r.out_rate || 0).toFixed(1) + "%";
      case "war_price": return (r.war_price || 0).toFixed(2);
      case "bid": return (r.bid || 0).toFixed(2);
      case "ask": return (r.ask || 0).toFixed(2);
      case "delta": return (r.delta || 0).toFixed(4);
      case "premium": return (r.premium || 0).toFixed(2) + "%";
      case "bid_ask_iv": return (r.bid_ask_iv || 0).toFixed(2);
      case "iv_buy": return (r.iv_buy || 0).toFixed(2) + "%";
      case "iv_sell": return (r.iv_sell || 0).toFixed(2) + "%";
      case "iv_avg": return r.iv_avg ? r.iv_avg.toFixed(1) + "%" : "-";
      case "iv_dev": return r.iv_avg ? sign(r.iv_dev) + r.iv_dev.toFixed(1) + "%" : "-";
      case "iv_stable": return r.iv_stable || "-";
      case "theta": return (r.theta || 0).toFixed(4);
      case "war_chg": return r.war_chg ? sign(r.war_chg) + r.war_chg.toFixed(2) + "%" : "-";
      case "qty": return Math.round(r.qty || 0).toLocaleString();
      case "out_qty": return Math.round(r.out_qty || 0).toLocaleString();
      case "strike": return (r.strike || 0).toFixed(0);
      case "ratio": return (r.ratio || 0).toFixed(4);
      case "expire": return r.expire || "-";
      case "fair": return r.fair ? r.fair.toFixed(2) : "-";
      case "fair_diff": return r.fair ? sign(r.fair_diff) + r.fair_diff.toFixed(2) + "%" : "-";
      default:
        if (id.startsWith("cond_")) {
          const i = parseInt(id.slice(5), 10);
          return (r._conds || [])[i] ? "✓" : "";
        }
        return "";
    }
  }

  function darkenHex(hex, div) {
    try {
      const r = parseInt(hex.slice(1, 3), 16), g = parseInt(hex.slice(3, 5), 16), b = parseInt(hex.slice(5, 7), 16);
      const f = (x) => Math.floor(x / div).toString(16).padStart(2, "0");
      return `#${f(r)}${f(g)}${f(b)}`;
    } catch (e) {
      return "#161b22";
    }
  }

  function renderTableBody(rows) {
    const tbody = document.getElementById("tbody");
    tbody.innerHTML = "";
    const colDefs = getColDefs();
    rows.forEach((r, i) => {
      const passed = (r._conds || []).map((ok, j) => (ok ? j : -1)).filter((j) => j >= 0);
      const tr = document.createElement("tr");
      if (passed.length >= 2) {
        tr.className = "row-multi";
      } else if (passed.length === 1) {
        const cond = state.conditions[passed[0]];
        const color = (cond && cond.color) || "#888888";
        tr.style.background = darkenHex(color, 5);
        tr.style.color = color;
      } else {
        tr.className = i % 2 ? "row-b" : "row-a";
      }
      colDefs.forEach(([id]) => {
        const td = document.createElement("td");
        td.textContent = fmtCell(id, r);
        if (id === "code") {
          td.className = "code";
          td.addEventListener("click", () => {
            window.open(`https://www.warrantwin.com.tw/eyuanta/Warrant/InfoAnalyzer.aspx?WID=${r.code}`, "_blank");
          });
        }
        if (id === "name") td.className = "name";
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
  }

  function sortByCol(id) {
    state.sortRev = state.sortCol === id ? !state.sortRev : true;
    state.sortCol = id;
    const rows = state.displayRows.slice();
    rows.sort((a, b) => {
      const va = fmtCell(id, a).replace(/[%x,+]/g, "");
      const vb = fmtCell(id, b).replace(/[%x,+]/g, "");
      const fa = parseFloat(va), fb = parseFloat(vb);
      let cmp;
      if (!isNaN(fa) && !isNaN(fb)) cmp = fa - fb;
      else cmp = va.localeCompare(vb, "zh-Hant");
      return state.sortRev ? -cmp : cmp;
    });
    state.displayRows = rows;
    renderTableBody(rows);
  }

  // ── 篩選條件設定 Modal ─────────────────────────────
  function openCondModal() {
    state.condDraft = JSON.parse(JSON.stringify(state.conditions.length ? state.conditions : window.DEF_CONDITIONS));
    while (state.condDraft.length < 5) state.condDraft.push(JSON.parse(JSON.stringify(window.DEF_CONDITIONS[state.condDraft.length])));
    state.condTabIdx = 0;
    renderCondTabs();
    renderCondTabBody();
    document.getElementById("condModal").classList.remove("hidden");
  }

  function renderCondTabs() {
    const wrap = document.getElementById("condTabs");
    wrap.innerHTML = "";
    state.condDraft.forEach((cond, i) => {
      const tab = document.createElement("div");
      tab.className = "tab" + (i === state.condTabIdx ? " active" : "");
      tab.textContent = cond.name || `條件${i + 1}`;
      tab.addEventListener("click", () => {
        state.condTabIdx = i;
        renderCondTabs();
        renderCondTabBody();
      });
      wrap.appendChild(tab);
    });
  }

  function renderCondTabBody() {
    const body = document.getElementById("condTabBody");
    body.innerHTML = "";
    const idx = state.condTabIdx;
    const cond = state.condDraft[idx];

    const head = document.createElement("div");
    head.className = "cond-head";
    head.innerHTML = `
      <span>名稱</span>
      <input type="text" id="condName" value="${escapeHtml(cond.name)}">
      <span>顏色</span>
      <input type="color" id="condColor" value="${cond.color}">
    `;
    body.appendChild(head);
    head.querySelector("#condName").addEventListener("input", (e) => (cond.name = e.target.value));
    head.querySelector("#condColor").addEventListener("input", (e) => (cond.color = e.target.value));

    const hintEl = document.createElement("div");
    hintEl.style.cssText = "color:var(--fg3);font-size:11px;margin-bottom:8px;";
    hintEl.textContent = "規則最多8條，全部同時通過（AND）才算通過此條件";
    body.appendChild(hintEl);

    const rulesWrap = document.createElement("div");
    body.appendChild(rulesWrap);

    function renderRules() {
      rulesWrap.innerHTML = "";
      cond.rules.forEach((rule, ri) => {
        rulesWrap.appendChild(buildRuleRow(cond, rule, ri, renderRules));
      });
    }
    renderRules();

    const addBtn = document.createElement("button");
    addBtn.className = "btn btn-ghost";
    addBtn.textContent = "＋ 新增規則";
    addBtn.addEventListener("click", () => {
      if (cond.rules.length >= 8) return;
      cond.rules.push({ field: Object.keys(FIELD_META)[0], op: ">=", value: 0 });
      renderRules();
    });
    body.appendChild(addBtn);
  }

  function buildRuleRow(cond, rule, ri, rerender) {
    const isBetween = rule.op === "between";
    const lo = isBetween ? rule.value[0] : rule.value;
    const hi = isBetween ? rule.value[1] : rule.value;

    const row = document.createElement("div");
    row.className = "rule-row";

    const fieldSel = document.createElement("select");
    Object.keys(FIELD_META).forEach((k) => {
      const opt = document.createElement("option");
      opt.value = k;
      opt.textContent = `${FIELD_META[k][0]}（${k}）`;
      if (k === rule.field) opt.selected = true;
      fieldSel.appendChild(opt);
    });
    fieldSel.addEventListener("change", () => (rule.field = fieldSel.value));

    const opSel = document.createElement("select");
    ["<", "<=", ">", ">=", "between"].forEach((op) => {
      const opt = document.createElement("option");
      opt.value = op;
      opt.textContent = op;
      if (op === rule.op) opt.selected = true;
      opSel.appendChild(opt);
    });

    const valLabel = document.createElement("span");
    valLabel.textContent = "值:";
    valLabel.style.color = "var(--fg2)";
    valLabel.style.fontSize = "12px";

    const loInput = document.createElement("input");
    loInput.type = "number";
    loInput.step = "any";
    loInput.style.width = "70px";
    loInput.value = lo;

    const tilde = document.createElement("span");
    tilde.textContent = "~";
    tilde.style.color = "var(--fg2)";

    const hiInput = document.createElement("input");
    hiInput.type = "number";
    hiInput.step = "any";
    hiInput.style.width = "70px";
    hiInput.value = hi;

    function syncValue() {
      const loV = parseFloat(loInput.value) || 0;
      const hiV = parseFloat(hiInput.value) || 0;
      rule.op = opSel.value;
      rule.value = rule.op === "between" ? [loV, hiV] : loV;
    }
    loInput.addEventListener("input", syncValue);
    hiInput.addEventListener("input", syncValue);
    opSel.addEventListener("change", () => {
      syncValue();
      tilde.style.display = opSel.value === "between" ? "" : "none";
      hiInput.style.display = opSel.value === "between" ? "" : "none";
    });
    tilde.style.display = isBetween ? "" : "none";
    hiInput.style.display = isBetween ? "" : "none";

    const rmBtn = document.createElement("button");
    rmBtn.className = "rm";
    rmBtn.textContent = "✕";
    rmBtn.addEventListener("click", () => {
      cond.rules.splice(ri, 1);
      rerender();
    });

    row.appendChild(fieldSel);
    row.appendChild(opSel);
    row.appendChild(valLabel);
    row.appendChild(loInput);
    row.appendChild(tilde);
    row.appendChild(hiInput);
    row.appendChild(rmBtn);
    return row;
  }

  function escapeHtml(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  document.getElementById("condSettingsBtn").addEventListener("click", openCondModal);
  document.getElementById("condSaveBtn").addEventListener("click", async () => {
    state.conditions = await api("/api/conditions", { method: "POST", body: JSON.stringify(state.condDraft) });
    state.activeConds.clear();
    renderCondButtons();
    if (state.allRows.length) applyFilter();
    else { renderTableHead(); }
    closeModal("condModal");
  });

  // ── 欄位設定 Modal ─────────────────────────────────
  function openColModal() {
    const list = document.getElementById("colList");
    list.innerHTML = "";
    FREE_COLS.forEach(([id, label]) => {
      const row = document.createElement("label");
      row.className = "col-item";
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = !!state.colVisible[id];
      cb.addEventListener("change", () => (state.colVisible[id] = cb.checked));
      row.appendChild(cb);
      const span = document.createElement("span");
      span.textContent = label;
      row.appendChild(span);
      list.appendChild(row);
    });
    document.getElementById("colModal").classList.remove("hidden");
  }
  document.getElementById("colBtn").addEventListener("click", openColModal);
  document.getElementById("colSaveBtn").addEventListener("click", () => {
    saveColVisible();
    renderTableHead();
    renderTableBody(state.displayRows);
    closeModal("colModal");
  });

  function closeModal(id) {
    document.getElementById(id).classList.add("hidden");
  }
  document.querySelectorAll("[data-close]").forEach((el) => {
    el.addEventListener("click", () => closeModal(el.dataset.close));
  });
  document.querySelectorAll(".modal").forEach((m) => {
    m.addEventListener("click", (e) => {
      if (e.target === m) m.classList.add("hidden");
    });
  });

  // ── 綁定 & 初始化 ──────────────────────────────────
  document.getElementById("addForm").addEventListener("submit", (e) => {
    e.preventDefault();
    const input = document.getElementById("codeInput");
    addStock(input.value);
    input.value = "";
  });
  document.getElementById("wtype").addEventListener("change", () => {
    if (state.curCode) query();
  });

  async function init() {
    tickClock();
    setInterval(tickClock, 1000);
    state.conditions = await api("/api/conditions");
    renderCondButtons();
    renderTableHead();
    await loadWatchlist();
    if (state.watchlist.length) selectStock(state.watchlist[0].code);
  }
  init();
})();
