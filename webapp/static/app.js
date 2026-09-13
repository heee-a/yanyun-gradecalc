/* 燕云装备毕业度计算器 · 前端逻辑
   方案数据全部保存在浏览器 localStorage，不与服务端共享。 */

"use strict";

const LS_KEY = "ygc_plans_v2";
const GRADES = [[90, "毕业"], [80, "准毕业"], [70, "可用"], [0, "过渡"]];

let META = { builds: {}, maxes: {}, known_stats: [] };
let PLANS = { plans: [], activeId: null };

// ---------------- 工具 ----------------
const $ = (sel) => document.querySelector(sel);
const uid = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function showBanner(msg) {
  const el = $("#banner");
  el.textContent = msg;
  el.classList.remove("hidden");
  setTimeout(() => el.classList.add("hidden"), 6000);
}

function loadPlans() {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (raw) PLANS = JSON.parse(raw);
  } catch (e) { console.warn("方案数据损坏，已重置", e); }
  if (!Array.isArray(PLANS.plans)) PLANS = { plans: [], activeId: null };
}
function savePlans() { localStorage.setItem(LS_KEY, JSON.stringify(PLANS)); }
function activePlan() { return PLANS.plans.find(p => p.id === PLANS.activeId) || null; }

// ---------------- 打分（与服务端同口径） ----------------
function weightFor(statName, weights) {
  if (statName in weights) return weights[statName];
  let best = 0;
  for (const [k, v] of Object.entries(weights)) {
    if (k && (statName.endsWith(k) || k.endsWith(statName))) best = Math.max(best, v);
  }
  return best;
}

function affixRoll(a, maxes) {
  const max = maxes[a.name];
  if (!max) return { roll: null, base: false };
  if (a.value > max * 1.3) return { roll: null, base: true };  // 疑似基础属性行
  return { roll: Math.min(100, a.value / max * 100), base: false };
}

function scorePiece(piece, buildWeights, maxes) {
  let num = 0, den = 0;
  const rows = [];
  for (const a of piece.affixes) {
    const w = weightFor(a.name, buildWeights);
    const { roll, base } = w > 0 ? affixRoll(a, maxes) : { roll: null, base: false };
    rows.push({ ...a, w, roll, relevant: w > 0, base });
    if (w > 0 && roll !== null && !base) { num += w * roll; den += w; }
  }
  const score = den > 0 ? num / den : null;
  return { score, rows, den };
}

function gradeOf(score) {
  return GRADES.find(([t]) => score >= t)[1];
}

// ---------------- 方案管理 ----------------
function newPlan(name) {
  const plan = { id: uid(), name: name || `方案${PLANS.plans.length + 1}`,
                 pieces: [], createdAt: Date.now() };
  PLANS.plans.push(plan);
  PLANS.activeId = plan.id;
  savePlans(); renderAll();
  return plan;
}

function deleteActivePlan() {
  const plan = activePlan();
  if (!plan) return;
  if (!confirm(`删除方案「${plan.name}」及其全部装备记录？`)) return;
  PLANS.plans = PLANS.plans.filter(p => p.id !== plan.id);
  PLANS.activeId = PLANS.plans[0]?.id || null;
  savePlans(); renderAll();
}

function renameActivePlan() {
  const plan = activePlan();
  if (!plan) return;
  const name = $("#planName").value.trim();
  if (!name) return;
  plan.name = name;
  savePlans(); renderAll();
}

function switchPlan(id) { PLANS.activeId = id; savePlans(); renderAll(); }

// ---------------- OCR 与装备卡片 ----------------
async function ocrFiles(files) {
  const plan = activePlan();
  if (!plan) { showBanner("请先新建一个方案"); return; }
  const status = $("#ocrStatus");
  for (let i = 0; i < files.length; i++) {
    status.textContent = `识别中 ${i + 1}/${files.length} …`;
    try {
      const compressed = await compressImage(files[i], 480);   // 本地缩略图
      const piece = { id: uid(), thumb: compressed, affixes: [], source: files[i].name };
      const form = new FormData();
      form.append("image", files[i]);
      const resp = await fetch("/api/ocr", { method: "POST", body: form });
      if (!resp.ok) throw new Error((await resp.json()).detail || resp.status);
      const recognized = await resp.json();
      Object.assign(piece, {
        name: recognized.name || recognized.source || "装备",
        slot: recognized.slot || "", tier: recognized.tier || "",
        setName: recognized.set_name || "", craft: recognized.craft_score ?? null,
        affixes: (recognized.affixes || []).map(a => ({
          name: a.name, value: a.value, unit: a.unit,
          converted: a.converted, raw: a.raw_name,
        })),
        rotated: recognized.rotated || 0,
      });
      plan.pieces.push(piece);
    } catch (e) {
      showBanner(`识别失败：${e.message}`);
    }
  }
  status.textContent = "";
  savePlans(); renderAll();
}

function compressImage(file, maxDim) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const url = URL.createObjectURL(file);
    img.onload = () => {
      const scale = Math.min(1, maxDim / Math.max(img.width, img.height));
      const canvas = document.createElement("canvas");
      canvas.width = Math.round(img.width * scale);
      canvas.height = Math.round(img.height * scale);
      canvas.getContext("2d").drawImage(img, 0, 0, canvas.width, canvas.height);
      URL.revokeObjectURL(url);
      resolve(canvas.toDataURL("image/jpeg", 0.65));
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("图片读取失败")); };
    img.src = url;
  });
}

function addAffixRow(piece) {
  piece.affixes.push({ name: META.known_stats[0] || "会心率", value: 0, unit: "percent" });
  savePlans(); renderPieces();
}

function removeAffix(piece, idx) {
  piece.affixes.splice(idx, 1);
  savePlans(); renderPieces();
}

function updateAffix(piece, idx, field, value) {
  const a = piece.affixes[idx];
  if (field === "name") {
    a.name = value;
    a.unit = (META.maxes[value] ?? 0) > 15 || value.includes("率") || value.includes("增伤")
      ? "percent" : a.unit;
    if (value.endsWith("攻击") || ["劲", "势", "敏", "体魄", "外功穿透", "鸣金穿透"]
        .includes(value)) a.unit = "flat";
  } else if (field === "value") {
    a.value = parseFloat(value) || 0;
  }
  savePlans(); renderPieces();
}

// ---------------- 渲染 ----------------
function renderAll() { renderPlanChips(); renderPieces(); }

function renderPlanChips() {
  const box = $("#planChips");
  box.innerHTML = "";
  for (const p of PLANS.plans) {
    const chip = document.createElement("span");
    chip.className = "chip" + (p.id === PLANS.activeId ? " active" : "");
    chip.textContent = `${p.name}（${p.pieces.length}件）`;
    chip.onclick = () => switchPlan(p.id);
    box.appendChild(chip);
  }
  const plan = activePlan();
  $("#planActions").style.display = plan ? "flex" : "none";
  if (plan) $("#planName").value = plan.name;
}

function renderPieces() {
  const plan = activePlan();
  const box = $("#pieces");
  box.innerHTML = "";
  if (!plan) {
    $("#summaryCard").style.display = "none";
    box.innerHTML = `<section class="card muted">还没有方案——点击「＋ 新方案」开始，
      然后拍照或从相册添加装备。</section>`;
    return;
  }
  const weights = META.builds[$("#buildSelect").value] || {};
  const maxes = META.maxes;

  const scored = plan.pieces.map(p => ({ p, r: scorePiece(p, weights, maxes) }));
  const valid = scored.filter(s => s.r.score !== null);
  const planScore = valid.length
    ? Math.round(valid.reduce((s, v) => s + v.r.score, 0) / valid.length * 10) / 10
    : null;

  $("#summaryCard").style.display = plan.pieces.length ? "" : "none";
  if (planScore !== null) {
    $("#planScore").textContent = planScore.toFixed(1);
    $("#planGrade").textContent = gradeOf(planScore);
    $("#pieceCount").textContent = `${valid.length} 件计入 / 共 ${plan.pieces.length} 件`;
    const chipBox = $("#pieceScores");
    chipBox.innerHTML = "";
    for (const { p, r } of scored) {
      if (r.score === null) continue;
      const chip = document.createElement("span");
      chip.className = "chip";
      chip.textContent = `${p.name || "装备"} ${r.score.toFixed(0)}`;
      chipBox.appendChild(chip);
    }
  }

  for (const { p, r } of scored) {
    const card = document.createElement("div");
    card.className = "piece";
    const head = document.createElement("div");
    head.className = "head";
    head.innerHTML = `
      ${p.thumb ? `<img class="thumb" src="${p.thumb}" alt="">` : ""}
      <div class="meta">
        <div class="title"><span>${esc(p.name || "装备")}</span>
          ${p.tier ? `<span class="muted small">${esc(p.tier)}</span>` : ""}
          ${p.setName ? `<span class="muted small">${esc(p.setName)}</span>` : ""}
          <span class="score">${r.score !== null ? r.score.toFixed(1) : "--"}</span>
        </div>
        <div class="muted small">${p.craft != null ? `造诣 ${p.craft} · ` : ""}${p.pieces ? "" : esc(p.source || "")}</div>
      </div>`;
    const del = document.createElement("button");
    del.className = "btn danger small"; del.textContent = "删除";
    del.onclick = () => {
      plan.pieces = plan.pieces.filter(x => x.id !== p.id);
      savePlans(); renderPieces();
    };
    head.querySelector(".meta").appendChild(del);
    card.appendChild(head);

    for (let i = 0; i < r.rows.length; i++) {
      const a = r.rows[i];
      const row = document.createElement("div");
      row.className = "affix";
      const sel = document.createElement("select");
      const opts = new Set(META.known_stats);
      if (!META.known_stats.includes(a.name)) opts.add(a.name);
      for (const s of opts) {
        const o = document.createElement("option");
        o.value = s; o.textContent = s + (s === a.name && !META.known_stats.includes(s) ? "（未收录）" : "");
        if (s === a.name) o.selected = true;
        sel.appendChild(o);
      }
      sel.onchange = () => updateAffix(plan, planAffixIndex(plan, p, i), "name", sel.value);
      const input = document.createElement("input");
      input.type = "number"; input.step = "any"; input.value = a.value;
      input.onchange = () => updateAffix(plan, planAffixIndex(plan, p, i), "value", input.value);
      const rollText = document.createElement("span");
      rollText.className = "roll";
      rollText.textContent = a.roll !== null ? `${a.roll.toFixed(0)}%` : "?";
      const delBtn = document.createElement("span");
      delBtn.className = "del"; delBtn.textContent = "✕";
      delBtn.onclick = () => removeAffix(plan, i);
      row.append(sel, input, rollText, delBtn);
      card.appendChild(row);
    }

    const addBtn = document.createElement("button");
    addBtn.className = "btn ghost small";
    addBtn.textContent = "＋ 手动补一条词条";
    addBtn.onclick = () => addAffixRow(plan.pieces.find(x => x.id === p.id));
    card.appendChild(addBtn);
    box.appendChild(card);
  }
}

function planAffixIndex(plan, piece, affixIdx) {
  const target = plan.pieces.find(x => x.id === piece.id);
  return target.affixes.indexOf(target.affixes[affixIdx]);
}

// ---------------- 备份 ----------------
function exportPlans() {
  const blob = new Blob([JSON.stringify(PLANS, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `毕业度方案备份_${new Date().toISOString().slice(0, 10)}.json`;
  a.click();
  URL.revokeObjectURL(a.href);
}

function importPlans(file) {
  const reader = new FileReader();
  reader.onload = () => {
    try {
      const data = JSON.parse(reader.result);
      if (!Array.isArray(data.plans)) throw new Error("格式不对");
      const names = new Set(PLANS.plans.map(p => p.name));
      for (const p of data.plans) {
        if (names.has(p.name)) p.name += "（导入）";
        p.id = uid();
        PLANS.plans.push(p);
      }
      savePlans(); renderAll();
    } catch (e) { showBanner("导入失败：" + e.message); }
  };
  reader.readAsText(file);
}

// ---------------- 初始化 ----------------
async function loadMeta() {
  const resp = await fetch("/api/meta");
  META = await resp.json();
  const sel = $("#buildSelect");
  sel.innerHTML = "";
  for (const name of Object.keys(META.builds)) {
    const o = document.createElement("option");
    o.value = name; o.textContent = name;
    sel.appendChild(o);
  }
}

async function init() {
  loadPlans();
  try {
    await loadMeta();
  } catch (e) {
    showBanner("无法加载流派数据（服务端未启动或 builds 目录缺失）");
    return;
  }
  $("#buildSelect").onchange = renderPieces;
  $("#btnRefreshMeta").onclick = async () => { await loadMeta(); renderPieces(); };
  $("#btnNewPlan").onclick = () => newPlan();
  $("#btnRename").onclick = renameActivePlan;
  $("#btnDeletePlan").onclick = deleteActivePlan;
  $("#fileCamera").onchange = (e) => { ocrFiles([...e.target.files]); e.target.value = ""; };
  $("#fileAlbum").onchange = (e) => { ocrFiles([...e.target.files]); e.target.value = ""; };
  $("#btnExport").onclick = exportPlans;
  $("#fileImport").onchange = (e) => { if (e.target.files[0]) importPlans(e.target.files[0]); e.target.value = ""; };
  if (!PLANS.plans.length) newPlan("我的方案");
  renderAll();
}

init();
