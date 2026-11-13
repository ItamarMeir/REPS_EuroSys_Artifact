// Headless smoke test for an interactive page: runs the inline script against a stub DOM + stub Plotly.
// usage: node check_page.js <page.html>   -> prints plots drawn, ids written, and any exception.
const fs = require("fs"), vm = require("vm");
const html = fs.readFileSync(process.argv[2], "utf8");
const scripts = [...html.matchAll(/<script(?![^>]*src)[^>]*>([\s\S]*?)<\/script>/g)].map(m => m[1]);
const ids = new Set([...html.matchAll(/id=["']([^"']+)["']/g)].map(m => m[1]));
const els = {}, plots = [], titles = [];
function el(id) {
  return els[id] || (els[id] = { id, innerHTML: "", value: "", options: [], style: {}, set onchange(f) { this._oc = f; }, get onchange() { return this._oc; },
    add(o) { this.options.push(o); if (this.value === "") this.value = o.value; }, appendChild() {}, addEventListener() {}, classList: { add() {}, remove() {} } });
}
const Plotly = { newPlot: (id, tr, lay) => { plots.push(id); titles.push((lay && lay.title && (lay.title.text || lay.title)) || ""); return Promise.resolve(); }, react: (id, tr, lay) => Plotly.newPlot(id, tr, lay), Plots: { resize() {} } };
const document = { getElementById: el, querySelectorAll: () => [], createElement: () => el("_tmp" + Math.random()), body: el("body"), addEventListener() {} };
const ctx = { document, Plotly, window: {}, console, Option: function (t, v) { this.text = t; this.value = v === undefined ? t : String(v); }, setTimeout, location: { hash: "" } };
ctx.window = ctx; vm.createContext(ctx);
let err = null;
for (const s of scripts) { try { vm.runInContext(s, ctx); } catch (e) { err = e; console.log("EXCEPTION", e.stack.split("\n").slice(0, 4).join("\n")); } }
const written = Object.values(els).filter(e => e.innerHTML && e.innerHTML.length > 20).map(e => e.id);
const missing = [...ids].filter(i => !plots.includes(i) && !written.includes(i) && !/^(upF|upB|tsF|verdict)/.test(i));
console.log("plots drawn:", plots.length, "| html-filled:", written.length, "| ids never filled:", missing.length, missing.slice(0, 12).join(","));
console.log("sample titles:", titles.slice(0, 3));
if (process.argv[3]) { const re = new RegExp(process.argv[3]); const bad = titles.filter(t => !re.test(t)); console.log("titles not matching", process.argv[3] + ":", bad.length, bad.slice(0, 5)); }
process.exit(err ? 1 : 0);
