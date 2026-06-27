#!/usr/bin/env node
/*
 * Re-extract the share-export CSS/JS assets from the installed @github/copilot
 * bundle, so the recap HTML report matches Copilot CLI's `/share html`.
 *
 * Why a Node script (not raw byte copy): the bundle stores these as JS template
 * literals, so every backslash is doubled on disk (`\\u2600`, regex `\\b`,
 * `\\n`, …). Copying raw bytes keeps them doubled and breaks the theme toggle,
 * the syntax highlighter regexes and code line-splitting. Evaluating each as a
 * template literal collapses the escaping to exactly the string the bundle
 * itself writes into the page.
 *
 * Usage:  node extract_assets.js [path/to/@github/copilot/app.js]
 * Writes: ../assets/share-export.css , ../assets/share-export.js
 */
const fs = require("fs");
const path = require("path");

function findBundle() {
  if (process.argv[2]) return process.argv[2];
  const roots = [];
  try {
    roots.push(require("child_process").execSync("npm root -g").toString().trim());
  } catch {}
  for (const r of roots) {
    const p = path.join(r, "@github", "copilot", "app.js");
    if (fs.existsSync(p)) return p;
  }
  throw new Error("could not locate @github/copilot/app.js — pass it as arg");
}

// Evaluate a raw template-literal body (already escaped as on disk) to the
// runtime string. `subs` supplies any ${ident()} interpolations as ''.
function evalLiteral(raw, subs = {}) {
  const names = Object.keys(subs);
  const fn = new Function(...names, "return `" + raw + "`;");
  return fn(...names.map((n) => subs[n]));
}

function bodyAfter(src, marker) {
  // body between the first backtick after `marker` and the next backtick
  const i = src.indexOf(marker);
  const b = src.indexOf("`", i);
  const e = src.indexOf("`", b + 1);
  return src.slice(b + 1, e);
}

const app = fs.readFileSync(findBundle(), "utf-8");

// CSS pieces: lFs (Primer light) + cFs (Primer dark) + mFs custom tail.
const lFs = evalLiteral(bodyAfter(app, "lFs=`"));
const cFs = evalLiteral(bodyAfter(app, "cFs=`"));
let mfsRaw = bodyAfter(app, "mFs(){return")
  .replace(/\$\{uFs\(\)\}/g, "")
  .replace(/\$\{dFs\(\)\}/g, "");
const mfsTail = evalLiteral(mfsRaw);
const css = lFs + "\n" + cFs + "\n" + mfsTail;

// JS: pFs() — contains a literal (escaped) backtick, so bound it by the next
// function (hFs), not the next backtick.
const p = app.indexOf("function pFs(){return");
const jb = app.indexOf("`", p);
const hf = app.indexOf("function hFs", jb);
const je = app.lastIndexOf("`", hf);
const js = evalLiteral(app.slice(jb + 1, je));

const outDir = path.join(__dirname, "..", "assets");
fs.mkdirSync(outDir, { recursive: true });
fs.writeFileSync(path.join(outDir, "share-export.css"), css);
fs.writeFileSync(path.join(outDir, "share-export.js"), js);
console.log(`css ${css.length} bytes, js ${js.length} bytes`);
