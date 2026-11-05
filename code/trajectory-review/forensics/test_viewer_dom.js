'use strict';
// Minimal DOM smoke: real gzip decoding + navigation. Not a visual browser test.
const fs = require('fs'), vm = require('vm'), path = require('path');
const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(__dirname, 'viewer.js'), 'utf8');
const cases = ['5ee06990-e26b-4ad8-b519-556169844669', '93e70998-9446-4798-ba79-8798273b8325', '56a53f1e-e143-4281-a6bd-e681846c9dc0', '8a510b0c-f49c-4568-b961-e88324d4a384', '6590f80c-3ae9-4f7e-b901-7f889ea9907c', '63815a3d-a441-4841-be12-d71bc9b8beb6', '2f9a4c6b-4795-4aa4-a49f-ad401cc35b27'];
async function run(id) {
  const nodes = new Map(), all = [], errors = [];
  class Element {
    constructor(tag) { this.tagName = tag; this.children = []; this.className = ''; this.dataset = {}; this.value = ''; this.textContent = ''; this.classList = {add: s => {this.className += ' ' + s;}, toggle: (s, yes) => {const a = new Set(this.className.split(/\s+/)); if (yes) a.add(s); else a.delete(s); this.className = [...a].join(' ');}}; all.push(this); }
    set id(v) { this._id = v; nodes.set(v, this); } get id() { return this._id; }
    append(...children) { this.children.push(...children); }
    replaceChildren(...children) { this.children = [...children]; }
    setAttribute(k, v) { this[k] = String(v); }
    scrollIntoView() {} click() {this.onclick?.();}
    getBoundingClientRect() {return {left: 0, width: 1000};}
  }
  const doc = {getElementById(id) {if (!nodes.has(id)) {const e = new Element('div'); e.id = id;} return nodes.get(id);}, createElement: t => new Element(t), createElementNS: (ns, t) => new Element(t), querySelectorAll: sel => sel === '.call-row' ? all.filter(n => n.className.split(/\s+/).includes('call-row')) : []};
  const html = fs.readFileSync(path.join(root, 'report', 'episodes', id + '.html'), 'utf8');
  const packed = html.match(/<script id="packed-data"[^>]*>([^<]+)<\/script>/)[1];
  doc.getElementById('packed-data').textContent = packed; doc.getElementById('mode').value = 'all';
  const location = {hash: ''};
  const context = vm.createContext({document: doc, location, history: {replaceState(a,b,h){location.hash=h;}}, window: {addEventListener(){}}, console: {error(...args){errors.push(args.map(String).join(' '));}}, Blob, Response, DecompressionStream, Uint8Array, atob, setTimeout, clearTimeout, URL});
  await vm.runInContext(source.replace(/boot\(\);\s*$/, 'globalThis.auditBoot = boot();'), context);
  await context.auditBoot;
  if (errors.length) throw new Error(id + ': ' + errors.join('\n'));
  if (!doc.getElementById('load-status').textContent.startsWith('载入 ')) throw new Error('boot did not finish');
  const counts = vm.runInContext('[D.calls.length, D.tools.length]', context);
  if (counts[0]) {
    doc.getElementById('last').click();
    if (!location.hash.includes('#call-' + counts[0])) throw new Error('last-call navigation failed');
    if (counts[1]) {
      vm.runInContext('gotoTool(1)', context);
      if (location.hash !== '#tool-1') throw new Error('tool navigation failed');
    }
    doc.getElementById('mode').value = 'error'; doc.getElementById('mode').onchange();
    if (!doc.getElementById('matched').textContent.includes('/')) throw new Error('filter failed');
  }
  return {id, calls: counts[0], tools: counts[1], boot: true, navigation: true, errors};
}
(async () => {
  const results = [];
  for (const id of cases) {results.push(await run(id)); if (global.gc) global.gc(); console.log(JSON.stringify(results.at(-1)));}
  const result = {test_type: 'minimal_dom_smoke_not_visual_browser', cases: results, no_network_or_model_requests: true};
  fs.writeFileSync(path.join(root, 'report', 'VIEWER_DOM_SMOKE.json'), JSON.stringify(result, null, 2) + '\n');
})().catch(e => {console.error(e); process.exitCode = 1;});
