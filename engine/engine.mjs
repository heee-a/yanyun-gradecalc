/* 燕云毕业率本地引擎：加载 leoq7 管理器同款 runtime + WASM，
 * 通过 stdin/stdout 的行 JSON 协议对外提供「网站同款」毕业率计算。
 *
 * 请求:  {"id":1,"cmd":"meta"}
 *        {"id":2,"cmd":"calc","payload":{
 *           "className":"破竹鸢","bow":"precision","xinfa":["易水歌","沧海帖"],
 *           "setName":"易相套装","armory":"本系",
 *           "equippedItems":{"weapon1":{"mainStat":{"type":"最大外功攻击","value":199,"isPercent":false},
 *                             "subStats":[{"type":"劲","value":72.2,"isPercent":false}]}, ...}}}
 * 响应:  {"id":2,"ok":true,"result":{"graduationRate":99.7,"dps":...,"panel":{...}}}
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import vm from "node:vm";

const VENDOR = path.join(path.dirname(fileURLToPath(import.meta.url)), "vendor");

// ---- 浏览器环境 shim ----
globalThis.window = globalThis;

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

// ---- 加载站点脚本（与线上完全同一份代码） ----
for (const f of [
  "leoq7_generated-calc-metadata.js",
  "leoq7_generated-calc-strings.js",
  "leoq7_excel-runtime.js",
]) {
  const code = readFileSync(path.join(VENDOR, f), "utf-8");
  new vm.Script(code, { filename: f }).runInThisContext();
}

const runtime = globalThis.window.YYSLSExcelRuntime;
const META = globalThis.window.YYSLS_CALC_METADATA || {};

function metaInfo() {
  return {
    available: !!runtime.available,
    flowNames: META.flowNames || Object.keys(META.flowIds || {}),
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

function calc(payload) {
  const options = {
    equippedItems: payload.equippedItems || {},
    className: payload.className || payload.flowName || "",
    bow: payload.bow || "precision",
    xinfa: payload.xinfa || [],
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
  console.error("engine fatal:", e);
  process.exit(1);
});
