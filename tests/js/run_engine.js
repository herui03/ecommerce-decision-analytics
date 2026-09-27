// Harness: node tests/js/run_engine.js <dashboard-data.json>  < queries.json  > results.json
// Runs the SAME engine.js the dashboard inlines against the SAME payload it embeds.
'use strict';
const fs = require('fs');
const path = require('path');
const Engine = require(path.join(__dirname, '..', '..', 'dashboard', 'src', 'engine.js'));
const data = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const queries = JSON.parse(fs.readFileSync(0, 'utf8'));
const out = queries.map((q) => {
  const src = data.olist[q.source];
  const sel = { from: q.from, to: q.to };
  if (q.kind === 'overview') return Engine.overview(src, sel);
  if (q.kind === 'categories') return Engine.categories(src, sel, q.opts || {});
  if (q.kind === 'states') return Engine.states(src, sel, q.opts || {});
  if (q.kind === 'payments') return Engine.payments(src, sel, q.opts || {});
  if (q.kind === 'topk') { const r = data.leads[q.source].ranked[q.model]; return Engine.topK(r.scores, r.labels, q.k); }
  throw new Error('unknown query ' + q.kind);
});
process.stdout.write(JSON.stringify(out));
