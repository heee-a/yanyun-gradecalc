/* 燕云毕业率本地引擎：加载 leoq7 管理器同款 runtime + WASM + 站点 UI 脚本，
 * 通过 stdin/stdout 的行 JSON 协议对外提供「网站同款」毕业率计算。
 *
 * 请求:  {"id":1,"cmd":"meta"}
 *        {"id":2,"cmd":"calc","payload":{
 *           "className":"破竹鸢","bow":"precision",
 *           "xinfa":["扶摇直上","擒天势","断石之构","易水歌"],
 *           "setName":"玉斗","armory":"本系",
 *           "equippedItems":{"head":{"mainStat":{"type":"气血最大值","value":9723,"isPercent":false},
 *                             "subStats":[{"type":"会意率","value":6.6,"isPercent":true}]}, ...}}}
 * 响应:  {"id":2,"ok":true,"result":{"graduationRate":99.7,"dps":...,"panel":{...},"xinfa":[...]}}
 *
 * meta 额外返回站点真数据（均取自站点自己的函数与常量）：
 *   xinfa[flow] = {default:[4 槽默认], choices:[每槽候选，空数组=锁定槽]}
 *   setNames    = ClassConfig.DEFAULT_SETS（套装列表）
 *   setData     = CommonData.SET_DATA（各套装主词条加成）
 *   xinfaList / genericXinfa = CommonData 里的全部/通用心法
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import vm from "node:vm";

const VENDOR = path.join(path.dirname(fileURLToPath(import.meta.url)), "vendor");

// ---- 浏览器环境 shim（足够让站点 UI 脚本完整初始化） ----
globalThis.window = globalThis;

const universal = new Proxy(function () {}, {
  get: (_t, k) => {
    if (k === Symbol.toPrimitive) return () => "";
    if (k === "then") return undefined; // 防止被当 thenable
    if (k === "length") return 0;
    return universal;
  },
  set: () => true,
  apply: () => universal,
  construct: () => universal,
});

globalThis.document = new Proxy({}, {
  get: (_t, k) => {
    if (k === "querySelectorAll") return () => [];
    if (k === "addEventListener" || k === "removeEventListener") return () => {};
    return universal;
  },
  set: () => true,
});
Object.defineProperty(globalThis, "navigator", { value: universal, configurable: true });
globalThis.location = universal;
const mkStore = () => new Proxy({}, {
  get: (_t, k) => (k === "getItem" ? () => null : universal),
  set: () => true,
});
globalThis.localStorage = mkStore();
globalThis.sessionStorage = mkStore();
globalThis.addEventListener = () => {};
globalThis.removeEventListener = () => {};
globalThis.matchMedia = () => universal;
globalThis.requestAnimationFrame = () => 0;
globalThis.cancelAnimationFrame = () => {};
globalThis.getComputedStyle = () => universal;
globalThis.Option = class Option {
  constructor(text, value) { this.text = text; this.value = value ?? text; }
};

const assetCache = new Map();
globalThis.fetch = async (url) => {
  const s = String(url);
  if (s.startsWith("assets/")) {
    const rel = s.replace(/^assets\//, "").split("?")[0];
    const file = path.join(VENDOR, rel);
    let data = assetCache.get(file);
    if (!data) {
      data = readFileSync(file);
      assetCache.set(file, data);
    }
    return new Response(data, {
      headers: { "content-type": rel.endsWith(".wasm") ? "application/wasm" : "text/plain" },
    });
  }
  throw new Error("engine fetch 仅支持本地 assets/：" + s);
};
process.on("unhandledRejection", () => {}); // 站点脚本的定时器回调可能触发网络失败，忽略

// 站点脚本的 console.log 会污染 stdout 的 JSON 协议，全部改道 stderr；
// send() 直接写 process.stdout，不受影响。
console.log = console.info = console.debug = console.warn =
  (...a) => process.stderr.write("[site] " + a.join(" ") + "\n");

// 站点脚本的 let/const 词法全局不挂 window，需在脚本上下文里求值读取
const g = (expr) => vm.runInThisContext(expr, { filename: "engine-eval.mjs" });

// ---- 加载站点脚本（与线上完全同一份代码） ----
for (const f of [
  "leoq7_generated-calc-metadata.js",
  "leoq7_generated-calc-strings.js",
  "leoq7_excel-runtime.js",
  "leoq7_app.min.js", // 提供 ClassConfig/CommonData/心法槽位规则（XINFA_LOCKED 等）/套装列表
]) {
  const code = readFileSync(path.join(VENDOR, f), "utf-8");
  try {
    new vm.Script(code, { filename: f }).runInThisContext();
  } catch (e) {
    console.error(`[engine] ${f} 加载失败: ${e.message}`);
  }
}

const runtime = g("window.YYSLSExcelRuntime");
const META = g("window.YYSLS_CALC_METADATA || {}");

function metaInfo() {
  let xinfa = {}, setNames = [], setData = {}, xinfaList = [], genericXinfa = [];
  try {
    const flows = JSON.stringify(META.flowNames || []);
    g(`(function(){
  window.__flowDefaults = {};
  for (const f of ${flows}) {
    loadDefaultXinfa(f);
    window.__flowDefaults[f] = AppState.currentXinfaLoadout.slice();
  }
})()`);
    for (const flow of META.flowNames || []) {
      xinfa[flow] = {
        default: g(`window.__flowDefaults[${JSON.stringify(flow)}] || []`),
        choices: [0, 1, 2, 3].map(
          (s) => g(`getXinfaChoicesForSlot(${JSON.stringify(flow)}, ${s})`) || []),
      };
    }
    setNames = g(`Array.isArray(ClassConfig.DEFAULT_SETS) ? ClassConfig.DEFAULT_SETS.slice()
                 : Object.keys(CommonData.SET_DATA || {})`);
    setData = g("CommonData.SET_DATA || {}");
    xinfaList = g("CommonData.XINFA_LIST || []");
    genericXinfa = g("CommonData.GENERIC_XINFA || []");
  } catch (e) {
    console.error(`[engine] 站点心法/套装数据提取失败: ${e.message}`);
  }
  return {
    available: !!runtime.available,
    flowNames: META.flowNames || Object.keys(META.flowIds || {}),
    xinfa,
    setNames,
    setData,
    xinfaList,
    genericXinfa,
    classXinfaInputs: META.classXinfaInputs || {},
    classRotationStats: META.classRotationStats || {},
    setField: "g5",
    bows: [
      { key: "precision", label: "精准" },
      { key: "crit", label: "会心" },
      { key: "intent", label: "会意" },
    ],
    slots: {
      weapon1: "武器1", weapon2: "武器2", head: "冠胄", chest: "胸甲",
      ring: "环", pendant: "佩", legs: "胫甲", hands: "腕甲",
    },
  };
}

function normalizeLoadout(className, xinfa) {
  try {
    return g(`normalizeXinfaLoadout(${JSON.stringify(className)}, ${JSON.stringify(xinfa || [])})`);
  } catch {
    return xinfa || [];
  }
}

function calc(payload) {
  const className = payload.className || payload.flowName || "";
  const options = {
    equippedItems: payload.equippedItems || {},
    className,
    bow: payload.bow || "precision",
    // 与站点一致：先按流派规则归一化心法槽位（锁定槽回正、缺失补默认）
    xinfa: normalizeLoadout(className, payload.xinfa),
    setName: payload.setName || "",
    armory: payload.armory || "本系",
    loanDingyin: !!payload.loanDingyin,
  };
  const r = runtime.calculate(options);
  if (!r) throw new Error("引擎计算失败（runtime 不可用或输入无效）");
  return {
    graduationRate: r.graduationRate,
    rdpsGraduationRate: r.rdpsGraduationRate,
    dps: r.dps,
    totalDamage: r.totalDamage,
    panel: r.panel || null,
    xinfa: options.xinfa,
    meta: {
      version: r.meta && (r.meta.version || r.meta.updateTime) ? {
        version: r.meta.version, updateTime: r.meta.updateTime, author: r.meta.author,
      } : null,
    },
  };
}

let buf = "";

async function main() {
  await runtime.ready;
  if (!runtime.available) {
    console.error("引擎初始化失败：WASM runtime 不可用");
    process.exit(1);
  }

  process.stdin.setEncoding("utf-8");
  process.stdin.on("data", (chunk) => {
    buf += chunk;
    let idx;
    while ((idx = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, idx).trim();
      buf = buf.slice(idx + 1);
      if (!line) continue;
      let msg = null;
      try {
        msg = JSON.parse(line);
      } catch {
        continue;
      }
      const { id, cmd, payload } = msg;
      try {
        if (cmd === "meta") {
          send({ id, ok: true, result: metaInfo() });
        } else if (cmd === "ping") {
          send({ id, ok: true, result: { pong: true, available: !!runtime.available } });
        } else if (cmd === "calc") {
          send({ id, ok: true, result: calc(payload) });
        } else {
          send({ id, ok: false, error: `未知命令 ${cmd}` });
        }
      } catch (e) {
        send({ id, ok: false, error: String(e && e.message ? e.message : e) });
      }
    }
  });
  process.stdin.on("end", () => process.exit(0));
  send({ id: 0, cmd: "ready", ok: true, result: metaInfo() });
}

function send(obj) {
  process.stdout.write(JSON.stringify(obj) + "\n");
}

main().catch((e) => {
  console.error("引擎 fatal:", e);
  process.exit(1);
});
