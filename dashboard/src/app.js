/*
 * Decision dashboard UI. All numbers come from Engine (engine.js) applied to the
 * embedded payload; nothing is fetched. Labels from data are inserted with textContent.
 */
(function () {
  'use strict';
  const DATA = JSON.parse(document.getElementById('dashboard-data').textContent);
  const E = window.Engine;
  const BADGE = Object.fromEntries(DATA.badges.map((b) => [b.id, b]));
  const VIEWS = ['overview', 'categories', 'states', 'payments', 'leads', 'experiment', 'definitions', 'memo'];
  const OLIST_VIEWS = ['overview', 'categories', 'states', 'payments'];
  const SRC_LABEL = { historical: 'Historical extracts', synthetic: 'Synthetic sample' };

  const S = {
    source: 'historical', view: 'overview', from: null, to: null,
    cat: { search: '', top: 15, sort: 'gmv' },
    st: { selected: null },
    pay: { selected: null },
    lead: { model: 'lr', kShare: 10 },
    exp: { basis: 'assigned', cost: '', value: '' },
    defs: { search: '' },
    tableMode: {},
  };

  // ------------------------------------------------------------------ DOM helpers
  function h(tag, attrs, ...kids) {
    const el = document.createElement(tag);
    setAttrs(el, attrs);
    append(el, kids);
    return el;
  }
  function sv(tag, attrs, ...kids) {
    const el = document.createElementNS('http://www.w3.org/2000/svg', tag);
    setAttrs(el, attrs);
    append(el, kids);
    return el;
  }
  function setAttrs(el, attrs) {
    if (!attrs) return;
    for (const [k, v] of Object.entries(attrs)) {
      if (v === null || v === undefined || v === false) continue;
      if (k === 'class') el.setAttribute('class', v);
      else if (k === 'text') el.textContent = v;
      else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? '' : String(v));
    }
  }
  function append(el, kids) {
    for (const kid of kids.flat(Infinity)) {
      if (kid === null || kid === undefined || kid === false) continue;
      el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
    }
  }
  function badge(id, title) {
    const b = BADGE[id];
    return h('span', { class: 'badge badge-' + id, title: title || b.meaning },
      h('span', { class: 'ic', 'aria-hidden': 'true', text: b.icon }), b.label);
  }
  function srcBadge() { return badge(S.source === 'historical' ? 'historical' : 'synthetic'); }
  const olist = () => DATA.olist[S.source];
  const pct = (v, dp) => {
    const d = dp === undefined ? 2 : dp;
    if (v !== null && v !== undefined && v > 0 && v < 0.5 * Math.pow(10, -d)) return '<' + E.fmtFixed(Math.pow(10, -d), d) + '%';
    return E.fmtPct(v, d);
  };
  const pp = (x, dp) => (x >= 0 ? '+' : '') + E.fmtFixed(100 * x, dp === undefined ? 4 : dp) + ' pp';
  const money = (c) => E.fmtCents(c);
  const int = (n) => E.fmtInt(n);
  let uid = 0;
  const nextId = (p) => p + '-' + (++uid);

  // ------------------------------------------------------------------ state <-> URL
  function readHash() {
    const p = new URLSearchParams(location.hash.slice(1));
    if (VIEWS.includes(p.get('view'))) S.view = p.get('view');
    if (['historical', 'synthetic'].includes(p.get('source'))) S.source = p.get('source');
  }
  function writeHash() {
    const p = new URLSearchParams({ view: S.view, source: S.source });
    history.replaceState(null, '', '#' + p.toString());
  }
  function announce(msg) { document.getElementById('live').textContent = msg; }

  // ---------------------------------------------------------------------- tiles
  function tile(label, metric, opts) {
    opts = opts || {};
    const badges = [srcBadge()];
    if (opts.recomputed !== false && S.source === 'historical') badges.push(badge('recomputed'));
    let valueEl;
    if (!metric || metric.status === 'unavailable') {
      badges.push(badge('unavailable'));
      valueEl = h('p', { class: 'value na', text: 'Unavailable' });
    } else {
      if (metric.status === 'inferred') badges.push(badge('inferred', opts.inferredTitle));
      const txt = opts.fmt(metric);
      valueEl = txt.indexOf('BRL ') === 0
        ? h('p', { class: 'value' }, h('span', { class: 'unit', text: 'BRL' }), txt.slice(4))
        : h('p', { class: 'value', text: txt });
    }
    const sub = metric && metric.status === 'unavailable' ? metric.reason : (opts.sub ? opts.sub(metric) : '');
    return h('div', { class: 'card tile', 'data-metric': opts.id || '' },
      h('p', { class: 'label' }, h('span', { text: label })),
      valueEl,
      h('p', { class: 'sub', text: sub }),
      h('div', { class: 'badges' }, badges));
  }

  // --------------------------------------------------------------------- charts

  /**
   * A chart card with a real table alternative. spec.draw(width) returns
   * {svg, n, point(i) -> {x, y, title, rows}, index(x, y) -> i, highlight(i)}.
   */
  function chartCard(spec) {
    const id = nextId('chart');
    const key = spec.key || id;
    const body = h('div', { class: 'chart-body', id: id + '-body' });
    const tip = h('div', { class: 'tooltip', role: 'presentation', hidden: true });
    const btn = h('button', { type: 'button', class: 'btn', 'aria-pressed': 'false', 'aria-controls': id + '-body',
      text: 'Show table' });
    const card = h('figure', { class: 'card chart', style: 'margin:0', 'data-chart': key },
      h('div', { class: 'chart-head' },
        h('div', null, h('h3', { id: id + '-title', text: spec.title }),
          spec.sub ? h('p', { class: 'chart-sub', text: spec.sub }) : null),
        btn),
      spec.legend ? h('div', { class: 'legend', 'aria-hidden': 'true' }, spec.legend.map((l) =>
        h('span', null, h('span', { class: 'key' + (l.box ? ' box' : ''), style: 'background:' + l.color }), l.label))) : null,
      body,
      spec.note ? h('figcaption', { class: 'chart-sub', text: spec.note }) : null);
    let lastWidth = 0;
    function drawChart() {
      const w = Math.max(280, Math.floor(body.clientWidth || 600));
      if (Math.abs(w - lastWidth) < 2 && body.querySelector('svg')) return;
      lastWidth = w;
      body.replaceChildren();
      const c = spec.draw(w);
      c.svg.setAttribute('role', 'img');
      c.svg.setAttribute('tabindex', '0');
      c.svg.setAttribute('aria-labelledby', id + '-title');
      c.svg.setAttribute('aria-describedby', id + '-desc');
      c.svg.prepend(sv('desc', { id: id + '-desc', text: (spec.desc || spec.title) +
        '. Use left and right arrow keys to read values, or press "Show table".' }));
      body.append(c.svg, tip);
      let active = -1;
      const show = (i) => {
        if (i < 0 || i >= c.n) { tip.hidden = true; c.highlight(-1); return; }
        active = i;
        const p = c.point(i);
        c.highlight(i);
        tip.replaceChildren(h('div', { class: 't-title', text: p.title }),
          p.rows.map((r) => h('div', { class: 't-row' },
            r.color ? h('span', { class: 't-key', style: 'background:' + r.color }) : null,
            h('strong', { text: r.value }), h('span', { class: 'muted', text: r.label }))));
        tip.hidden = false;
        const bw = body.clientWidth;
        const left = Math.min(Math.max(0, p.x + 12), Math.max(0, bw - 240));
        tip.style.left = left + 'px';
        tip.style.top = Math.max(0, p.y - 10) + 'px';
      };
      c.svg.addEventListener('pointermove', (e) => {
        const r = c.svg.getBoundingClientRect();
        show(c.index((e.clientX - r.left) * (w / r.width), (e.clientY - r.top) * (w / r.width)));
      });
      c.svg.addEventListener('pointerleave', () => show(-1));
      c.svg.addEventListener('focus', () => show(active >= 0 ? active : 0));
      c.svg.addEventListener('blur', () => show(-1));
      c.svg.addEventListener('keydown', (e) => {
        if (e.key === 'ArrowRight' || e.key === 'ArrowDown') { show(Math.min(c.n - 1, active + 1)); e.preventDefault(); }
        else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') { show(Math.max(0, active - 1)); e.preventDefault(); }
        else if (e.key === 'Home') { show(0); e.preventDefault(); }
        else if (e.key === 'End') { show(c.n - 1); e.preventDefault(); }
        else if (e.key === 'Escape') { show(-1); }
      });
    }
    function drawTable() {
      body.replaceChildren(dataTable(spec.table));
      lastWidth = 0;
    }
    function apply(sync) {
      const tableOn = !!S.tableMode[key];
      btn.setAttribute('aria-pressed', String(tableOn));
      btn.textContent = tableOn ? 'Show chart' : 'Show table';
      if (tableOn) drawTable();
      else if (sync) drawChart();                 // card is in the DOM: its width is known now
      else requestAnimationFrame(drawChart);      // first render: wait until the card is attached
    }
    btn.addEventListener('click', () => { S.tableMode[key] = !S.tableMode[key]; apply(true); });
    if (window.ResizeObserver) {
      new ResizeObserver(() => { if (!S.tableMode[key]) drawChart(); }).observe(body);
    }
    apply();
    return card;
  }

  function dataTable(t) {
    const table = h('table', null,
      t.caption ? h('caption', { text: t.caption }) : null,
      h('thead', null, h('tr', null, t.head.map((c) => h('th', { scope: 'col', class: c.num ? 'num' : null, text: c.label })))),
      h('tbody', null, t.rows.map((r) => h('tr', { class: r.total ? 'total' : null },
        r.cells.map((cell, j) => {
          const td = h(j === 0 ? 'th' : 'td', { class: t.head[j].num ? 'num' : null, scope: j === 0 ? 'row' : null });
          if (cell && typeof cell === 'object' && !cell.nodeType) {
            td.append(document.createTextNode(cell.text));
            (cell.badges || []).forEach((b) => td.append(badge(b)));
            if (cell.title) td.title = cell.title;
          } else if (cell && cell.nodeType) td.append(cell);
          else td.textContent = cell === null || cell === undefined ? '—' : String(cell);
          return td;
        })))));
    return h('div', { class: 'table-wrap', tabindex: '0', role: 'region', 'aria-label': t.caption || 'table' }, table);
  }

  const COLORS = () => {
    const cs = getComputedStyle(document.documentElement);
    return { s1: cs.getPropertyValue('--series-1').trim(), s2: cs.getPropertyValue('--series-2').trim(),
      s3: cs.getPropertyValue('--series-3').trim(), surface: cs.getPropertyValue('--surface').trim(),
      muted: cs.getPropertyValue('--muted').trim(), axis: cs.getPropertyValue('--axis').trim(),
      grid: cs.getPropertyValue('--grid').trim(), ink: cs.getPropertyValue('--ink').trim() };
  };

  function roundedTopRect(x, y, w, hgt, r) {
    r = Math.min(r, w / 2, hgt);
    if (hgt <= 0) return 'M' + x + ',' + y + 'h' + w;
    return 'M' + x + ',' + (y + hgt) + 'V' + (y + r) + 'Q' + x + ',' + y + ' ' + (x + r) + ',' + y +
      'H' + (x + w - r) + 'Q' + (x + w) + ',' + y + ' ' + (x + w) + ',' + (y + r) + 'V' + (y + hgt) + 'Z';
  }
  function roundedRightRect(x, y, w, hgt, r) {
    r = Math.min(r, hgt / 2, w);
    if (w <= 0) return 'M' + x + ',' + y + 'v' + hgt;
    return 'M' + x + ',' + y + 'H' + (x + w - r) + 'Q' + (x + w) + ',' + y + ' ' + (x + w) + ',' + (y + r) +
      'V' + (y + hgt - r) + 'Q' + (x + w) + ',' + (y + hgt) + ' ' + (x + w - r) + ',' + (y + hgt) + 'H' + x + 'Z';
  }

  /** Vertical columns over months (one series). values may be null (gap). */
  function drawColumns(items, fmtAxis, fmtVal, label) {
    return (w) => {
      const C = COLORS(), m = { l: 58, r: 10, t: 12, b: 34 }, hgt = 240;
      const iw = w - m.l - m.r, ih = hgt - m.t - m.b;
      const sc = E.niceScale(0, Math.max(...items.map((d) => d.value || 0), 1), 4), max = sc.max;
      const band = iw / items.length, bw = Math.min(24, band * 0.62);
      const svg = sv('svg', { viewBox: '0 0 ' + w + ' ' + hgt, width: w, height: hgt });
      const g = sv('g', { transform: 'translate(' + m.l + ',' + m.t + ')' });
      svg.append(g);
      sc.ticks.forEach((t) => {
        const y = ih - ih * t / max;
        g.append(sv('line', { class: t === 0 ? 'baseline' : 'gridline', x1: 0, x2: iw, y1: y, y2: y }));
        g.append(sv('text', { class: 'tick', x: -8, y: y + 4, 'text-anchor': 'end', text: fmtAxis(t) }));
      });
      const show = new Set(E.labelIndices(items.length, Math.max(1, Math.ceil(items.length * 56 / iw))));
      const bars = items.map((d, i) => {
        const x = band * i + (band - bw) / 2, v = d.value || 0, bh = ih * v / max;
        if (show.has(i)) {
          g.append(sv('text', { class: 'tick', x: x + bw / 2, y: ih + 16, 'text-anchor': 'middle', text: d.label }));
        }
        const p = sv('path', { d: roundedTopRect(x, ih - bh, bw, bh, 4), fill: C.s1 });
        g.append(p);
        return { p, x: m.l + x + bw / 2, y: m.t + ih - bh };
      });
      return {
        svg, n: items.length,
        point: (i) => ({ x: bars[i].x, y: bars[i].y, title: items[i].label,
          rows: [{ color: C.s1, value: fmtVal(items[i].value), label }] }),
        index: (x) => Math.max(0, Math.min(items.length - 1, Math.floor((x - m.l) / band))),
        highlight: (i) => bars.forEach((b, j) => b.p.setAttribute('class', j === i ? 'hl' : '')),
      };
    };
  }

  /** Multi-series line chart over months on ONE axis (same unit). */
  function drawLines(labels, series, fmtAxis, fmtVal) {
    return (w) => {
      const C = COLORS(), m = { l: 48, r: 14, t: 12, b: 34 }, hgt = 250;
      const iw = w - m.l - m.r, ih = hgt - m.t - m.b;
      const all = series.flatMap((s) => s.values.filter((v) => v !== null));
      const sc = E.niceScale(0, Math.max(...all, 1e-9), 4), max = sc.max;
      const x = (i) => labels.length === 1 ? iw / 2 : iw * i / (labels.length - 1);
      const y = (v) => ih - ih * v / max;
      const svg = sv('svg', { viewBox: '0 0 ' + w + ' ' + hgt, width: w, height: hgt });
      const g = sv('g', { transform: 'translate(' + m.l + ',' + m.t + ')' });
      svg.append(g);
      sc.ticks.forEach((t) => {
        g.append(sv('line', { class: t === 0 ? 'baseline' : 'gridline', x1: 0, x2: iw, y1: y(t), y2: y(t) }));
        g.append(sv('text', { class: 'tick', x: -8, y: y(t) + 4, 'text-anchor': 'end', text: fmtAxis(t) }));
      });
      E.labelIndices(labels.length, Math.max(1, Math.ceil(labels.length * 56 / iw))).forEach((i) => {
        g.append(sv('text', { class: 'tick', x: x(i), y: ih + 16, 'text-anchor': 'middle', text: labels[i] }));
      });
      const cross = sv('line', { x1: 0, x2: 0, y1: 0, y2: ih, stroke: C.axis, 'stroke-width': 1, visibility: 'hidden' });
      g.append(cross);
      series.forEach((s) => {
        let d = '', pen = false;
        s.values.forEach((v, i) => {
          if (v === null) { pen = false; return; }
          d += (pen ? 'L' : 'M') + x(i).toFixed(2) + ',' + y(v).toFixed(2);
          pen = true;
        });
        g.append(sv('path', { d, fill: 'none', stroke: s.color, 'stroke-width': 2, 'stroke-linejoin': 'round', 'stroke-linecap': 'round' }));
        s.values.forEach((v, i) => {
          if (v !== null && labels.length <= 24) g.append(sv('circle', { cx: x(i), cy: y(v), r: 4, fill: s.color, stroke: C.surface, 'stroke-width': 2 }));
        });
      });
      return {
        svg, n: labels.length,
        point: (i) => {
          const vals = series.map((s) => s.values[i]).filter((v) => v !== null);
          return { x: m.l + x(i), y: m.t + (vals.length ? y(Math.max(...vals)) : ih / 2), title: labels[i],
            rows: series.map((s) => ({ color: s.color, value: s.values[i] === null ? 'unavailable' : fmtVal(s.values[i]), label: s.name })) };
        },
        index: (px) => Math.max(0, Math.min(labels.length - 1, Math.round((px - m.l) / (iw / Math.max(1, labels.length - 1))))),
        highlight: (i) => {
          if (i < 0) { cross.setAttribute('visibility', 'hidden'); return; }
          cross.setAttribute('x1', x(i)); cross.setAttribute('x2', x(i)); cross.setAttribute('visibility', 'visible');
        },
      };
    };
  }

  /** Horizontal bars, one series, labels on the left, value at the bar tip when it fits. */
  function drawHBars(items, fmtVal, label, opts) {
    opts = opts || {};
    return (w) => {
      const C = COLORS();
      const rowH = 26, labelW = Math.min(Math.max(90, w * 0.34), 210);
      const m = { l: labelW, r: 70, t: 6, b: 22 };
      const iw = Math.max(40, w - m.l - m.r), hgt = m.t + m.b + rowH * items.length;
      const sc = E.niceScale(0, opts.max || Math.max(...items.map((d) => d.value || 0), 1e-9), 4), max = sc.max;
      const svg = sv('svg', { viewBox: '0 0 ' + w + ' ' + hgt, width: w, height: hgt });
      const g = sv('g', { transform: 'translate(' + m.l + ',' + m.t + ')' });
      svg.append(g);
      sc.ticks.forEach((t) => {
        const x = iw * t / max;
        g.append(sv('line', { class: t === 0 ? 'baseline' : 'gridline', x1: x, x2: x, y1: 0, y2: rowH * items.length }));
        g.append(sv('text', { class: 'tick', x, y: rowH * items.length + 14, 'text-anchor': 'middle', text: (opts.fmtAxis || fmtVal)(t) }));
      });
      const bars = items.map((d, i) => {
        const y0 = i * rowH + 5, bh = Math.min(16, rowH - 8);
        const maxChars = Math.floor((labelW - 10) / 6.6);
        const text = d.label.length > maxChars ? d.label.slice(0, maxChars - 1) + '…' : d.label;
        g.append(sv('text', { class: 'tick', x: -8, y: y0 + bh / 2 + 4, 'text-anchor': 'end', text }));
        if (d.value === null || d.value === undefined) {
          g.append(sv('text', { class: 'mark-label', x: 4, y: y0 + bh / 2 + 4, text: 'unavailable' }));
          return { p: null, x: m.l, y: m.t + y0 };
        }
        const bw = iw * d.value / max;
        const p = sv('path', { d: roundedRightRect(0, y0, bw, bh, 4), fill: d.color || C.s1 });
        g.append(p);
        g.append(sv('text', { class: 'mark-label', x: bw + 5, y: y0 + bh / 2 + 4, text: fmtVal(d.value) }));
        return { p, x: m.l + bw, y: m.t + y0 };
      });
      return {
        svg, n: items.length,
        point: (i) => ({ x: bars[i].x, y: bars[i].y, title: items[i].label,
          rows: [{ color: items[i].color || C.s1, value: items[i].value === null ? 'unavailable' : fmtVal(items[i].value), label }]
            .concat(items[i].extra || []) }),
        index: (x, y) => Math.max(0, Math.min(items.length - 1, Math.floor((y - m.t) / rowH))),
        highlight: (i) => bars.forEach((b, j) => b.p && b.p.setAttribute('class', j === i ? 'hl' : '')),
      };
    };
  }

  /** Point estimates with 95% intervals on one shared axis (same unit). */
  function drawIntervals(rows, fmtVal, refs) {
    return (w) => {
      const C = COLORS(), rowH = 44, m = { l: Math.min(190, w * 0.36), r: 24, t: 10, b: 30 };
      const iw = w - m.l - m.r, hgt = m.t + m.b + rowH * rows.length;
      const vals = rows.flatMap((r) => [r.lo, r.hi, r.est, r.truth]).concat((refs || []).map((r) => r.value), [0])
        .filter((v) => v !== null && v !== undefined);
      const sc = E.niceScale(Math.min(...vals), Math.max(...vals), 5);
      const lo = sc.min, hi = sc.max;
      const x = (v) => iw * (v - lo) / (hi - lo);
      const svg = sv('svg', { viewBox: '0 0 ' + w + ' ' + hgt, width: w, height: hgt });
      const g = sv('g', { transform: 'translate(' + m.l + ',' + m.t + ')' });
      svg.append(g);
      sc.ticks.forEach((v) => {
        g.append(sv('line', { class: v === 0 ? 'baseline' : 'gridline', x1: x(v), x2: x(v), y1: 0, y2: rowH * rows.length, 'stroke-width': v === 0 ? 1.5 : 1 }));
        g.append(sv('text', { class: 'tick', x: x(v), y: rowH * rows.length + 16, 'text-anchor': 'middle', text: fmtVal(v) }));
      });
      (refs || []).forEach((r) => {
        g.append(sv('line', { x1: x(r.value), x2: x(r.value), y1: 0, y2: rowH * rows.length, stroke: C.muted, 'stroke-width': 1 }));
        g.append(sv('text', { class: 'mark-label', x: x(r.value) + 4, y: 10, text: r.label }));
      });
      const marks = rows.map((r, i) => {
        const cy = i * rowH + rowH / 2;
        g.append(sv('text', { class: 'tick', x: -10, y: cy + 4, 'text-anchor': 'end', text: r.label }));
        g.append(sv('line', { x1: x(r.lo), x2: x(r.hi), y1: cy, y2: cy, stroke: C.s1, 'stroke-width': 2, 'stroke-linecap': 'round' }));
        [r.lo, r.hi].forEach((v) => g.append(sv('line', { x1: x(v), x2: x(v), y1: cy - 6, y2: cy + 6, stroke: C.s1, 'stroke-width': 2 })));
        const dot = sv('circle', { cx: x(r.est), cy, r: 5, fill: C.s1, stroke: C.surface, 'stroke-width': 2 });
        g.append(dot);
        if (r.truth !== undefined && r.truth !== null) {
          const tx = x(r.truth);
          g.append(sv('path', { d: 'M' + tx + ',' + (cy - 7) + 'l6,7l-6,7l-6,-7Z', fill: C.s2, stroke: C.surface, 'stroke-width': 1.5 }));
        }
        return { dot, x: m.l + x(r.est), y: m.t + cy };
      });
      return {
        svg, n: rows.length,
        point: (i) => ({ x: marks[i].x, y: marks[i].y, title: rows[i].label,
          rows: [{ color: C.s1, value: fmtVal(rows[i].est), label: 'estimate' },
            { value: fmtVal(rows[i].lo) + ' to ' + fmtVal(rows[i].hi), label: '95% interval' }]
            .concat(rows[i].truth !== undefined && rows[i].truth !== null ? [{ color: C.s2, value: fmtVal(rows[i].truth), label: 'true value (synthetic)' }] : []) }),
        index: (px, py) => Math.max(0, Math.min(rows.length - 1, Math.floor((py - m.t) / rowH))),
        highlight: (i) => marks.forEach((mk, j) => mk.dot.setAttribute('r', j === i ? 7 : 5)),
      };
    };
  }

  /** Cumulative gains: share of positives captured vs share of leads called. */
  function drawGains(curve) {
    return (w) => {
      const C = COLORS(), m = { l: 48, r: 16, t: 12, b: 40 }, hgt = 260;
      const iw = w - m.l - m.r, ih = hgt - m.t - m.b;
      const x = (v) => iw * v, y = (v) => ih - ih * v;
      const svg = sv('svg', { viewBox: '0 0 ' + w + ' ' + hgt, width: w, height: hgt });
      const g = sv('g', { transform: 'translate(' + m.l + ',' + m.t + ')' });
      svg.append(g);
      [0, .25, .5, .75, 1].forEach((t) => {
        g.append(sv('line', { class: t === 0 ? 'baseline' : 'gridline', x1: 0, x2: iw, y1: y(t), y2: y(t) }));
        g.append(sv('text', { class: 'tick', x: -8, y: y(t) + 4, 'text-anchor': 'end', text: Math.round(t * 100) + '%' }));
        g.append(sv('text', { class: 'tick', x: x(t), y: ih + 16, 'text-anchor': 'middle', text: Math.round(t * 100) + '%' }));
      });
      g.append(sv('text', { class: 'tick', x: iw / 2, y: ih + 32, 'text-anchor': 'middle', text: 'share of cohort called, highest scores first' }));
      g.append(sv('line', { x1: x(0), y1: y(0), x2: x(1), y2: y(1), stroke: C.muted, 'stroke-width': 1.5 }));
      let d = '';
      curve.forEach((p, i) => { d += (i ? 'L' : 'M') + x(p.share).toFixed(2) + ',' + y(p.captured).toFixed(2); });
      g.append(sv('path', { d, fill: 'none', stroke: C.s1, 'stroke-width': 2 }));
      const dots = curve.map((p) => {
        const c = sv('circle', { cx: x(p.share), cy: y(p.captured), r: 4, fill: C.s1, stroke: C.surface, 'stroke-width': 2 });
        g.append(c);
        return c;
      });
      return {
        svg, n: curve.length,
        point: (i) => ({ x: m.l + x(curve[i].share), y: m.t + y(curve[i].captured),
          title: 'Top ' + Math.round(curve[i].share * 100) + '% of leads',
          rows: [{ color: C.s1, value: pct(100 * curve[i].captured, 1), label: 'of positives captured (tie-aware)' },
            { color: C.muted, value: pct(100 * curve[i].share, 0), label: 'random ordering' }] }),
        index: (px) => Math.max(0, Math.min(curve.length - 1, Math.round((px - m.l) / (iw / (curve.length - 1))))),
        highlight: (i) => dots.forEach((c, j) => c.setAttribute('r', j === i ? 6 : 4)),
      };
    };
  }

  /** Lanes on a date axis for a lead-scoring design. */
  function drawTimeline(lanes, start, end) {
    const t0 = Date.parse(start), t1 = Date.parse(end);
    return (w) => {
      const C = COLORS(), rowH = 30, m = { l: Math.min(200, w * 0.38), r: 16, t: 8, b: 28 };
      const iw = w - m.l - m.r, hgt = m.t + m.b + rowH * lanes.length;
      const x = (d) => iw * (Date.parse(d) - t0) / (t1 - t0);
      const svg = sv('svg', { viewBox: '0 0 ' + w + ' ' + hgt, width: w, height: hgt });
      const g = sv('g', { transform: 'translate(' + m.l + ',' + m.t + ')' });
      svg.append(g);
      const months = [];
      for (let d = new Date(start); d <= new Date(end); d.setUTCMonth(d.getUTCMonth() + 1)) months.push(d.toISOString().slice(0, 7) + '-01');
      const step = Math.max(1, Math.ceil(months.length * 48 / iw));
      months.forEach((mo, i) => {
        g.append(sv('line', { class: 'gridline', x1: x(mo), x2: x(mo), y1: 0, y2: rowH * lanes.length }));
        if (i % step === 0) g.append(sv('text', { class: 'tick', x: x(mo), y: rowH * lanes.length + 16, 'text-anchor': 'middle', text: mo.slice(0, 7) }));
      });
      const bars = lanes.map((l, i) => {
        const y0 = i * rowH + 7;
        g.append(sv('text', { class: 'tick', x: -8, y: y0 + 12, 'text-anchor': 'end', text: l.label }));
        const x0 = x(l.from), x1 = Math.max(x0 + 3, x(l.to));
        const r = sv('rect', { x: x0, y: y0, width: x1 - x0, height: 16, rx: 4, fill: l.color || C.s1 });
        g.append(r);
        return { r, x: m.l + x1, y: m.t + y0 };
      });
      return {
        svg, n: lanes.length,
        point: (i) => ({ x: bars[i].x, y: bars[i].y, title: lanes[i].label,
          rows: [{ color: lanes[i].color || C.s1, value: lanes[i].from + ' → ' + lanes[i].to, label: '' }] }),
        index: (px, py) => Math.max(0, Math.min(lanes.length - 1, Math.floor((py - m.t) / rowH))),
        highlight: (i) => bars.forEach((b, j) => b.r.setAttribute('class', j === i ? 'hl' : '')),
      };
    };
  }

  // -------------------------------------------------------------------- filters
  function monthFilters() {
    const months = olist().months;
    if (!months.includes(S.from)) S.from = months[0];
    if (!months.includes(S.to)) S.to = months[months.length - 1];
    const sel = (id, label, val, on) => h('div', { class: 'field' },
      h('label', { for: id, text: label }),
      h('select', { id, onchange: (e) => { on(e.target.value); render(); } },
        months.map((m) => h('option', { value: m, selected: m === val, text: m }))));
    const preset = (label, a, b) => h('button', { type: 'button', class: 'btn',
      'aria-pressed': String(S.from === a && S.to === b), onclick: () => { S.from = a; S.to = b; render(); }, text: label });
    const last = months[months.length - 1];
    return [
      sel('f-from', 'From month', S.from, (v) => { S.from = v; }),
      sel('f-to', 'To month', S.to, (v) => { S.to = v; }),
      h('div', { class: 'field' }, h('span', { text: 'Presets' }), h('div', { class: 'presets' },
        preset('Full window', months[0], last),
        preset('2017', '2017-01', '2017-12'),
        preset('2018 (Jan–Aug)', '2018-01', last),
        preset('Last 3 months', months[months.length - 3], last))),
    ];
  }
  function scopeNote(extra) {
    return h('p', { class: 'scope' },
      h('strong', { text: 'Filter scope. ' }),
      'The month range applies to Overview, Categories, States and Payments (every extract has a month). ',
      extra || 'Category, state and payment filters apply only to their own view: no extract has a joint month × state × category grain, so combining them would invent numbers.');
  }
  function renderFilters() {
    const f = document.getElementById('filters');
    f.replaceChildren();
    const v = S.view;
    if (OLIST_VIEWS.includes(v)) {
      append(f, monthFilters());
      if (v === 'categories') {
        append(f, [
          h('div', { class: 'field' }, h('label', { for: 'f-search', text: 'Category contains' }),
            h('input', { id: 'f-search', type: 'search', value: S.cat.search, placeholder: 'e.g. furniture',
              oninput: (e) => { S.cat.search = e.target.value; renderPanel(); } })),
          h('div', { class: 'field' }, h('label', { for: 'f-top', text: 'Show' }),
            h('select', { id: 'f-top', onchange: (e) => { S.cat.top = Number(e.target.value); renderPanel(); } },
              [10, 15, 25, 100].map((n) => h('option', { value: n, selected: n === S.cat.top, text: n === 100 ? 'all' : 'top ' + n })))),
          h('div', { class: 'field' }, h('label', { for: 'f-sort', text: 'Sort by' }),
            h('select', { id: 'f-sort', onchange: (e) => { S.cat.sort = e.target.value; renderPanel(); } },
              [['gmv', 'GMV'], ['freight_share', 'Freight share'], ['lines', 'Order lines'], ['name', 'Name']]
                .map(([k, l]) => h('option', { value: k, selected: k === S.cat.sort, text: l })))),
        ]);
        f.append(scopeNote('Search, top-N and sort apply to this view only; shares keep all categories in the denominator.'));
      } else if (v === 'states') {
        const all = [...new Set(olist().state.map((r) => r.state))].sort();
        if (!S.st.selected || S.st.selected.some((s) => !all.includes(s))) S.st.selected = all.slice();
        f.append(checkGroup('States (this view only)', 'f-state', all, S.st.selected, (list) => { S.st.selected = list; renderPanel(); }));
        f.append(scopeNote());
      } else if (v === 'payments') {
        const all = [...new Set(olist().payment.map((r) => r.ptype))].sort();
        if (!S.pay.selected || S.pay.selected.some((s) => !all.includes(s))) S.pay.selected = all.slice();
        f.append(checkGroup('Primary instrument (this view only)', 'f-ptype', all, S.pay.selected, (list) => { S.pay.selected = list; renderPanel(); }));
        f.append(scopeNote('The instrument filter hides rows; each share still divides by all orders with a primary instrument.'));
      } else {
        f.append(scopeNote());
      }
    } else if (v === 'leads') {
      append(f, [
        h('div', { class: 'field' }, h('label', { for: 'f-model', text: 'Model' }),
          h('select', { id: 'f-model', onchange: (e) => { S.lead.model = e.target.value; renderPanel(); } },
            [['lr', 'Logistic regression'], ['gb', 'Gradient boosting']].map(([k, l]) => h('option', { value: k, selected: k === S.lead.model, text: l })))),
        h('div', { class: 'field' }, h('label', { for: 'f-k', text: 'Leads called: top ' + S.lead.kShare + '% of the held-out cohort' }),
          h('input', { id: 'f-k', type: 'range', min: 1, max: 100, step: 1, value: S.lead.kShare,
            'aria-valuetext': 'top ' + S.lead.kShare + ' percent',
            oninput: (e) => {
              S.lead.kShare = Number(e.target.value);
              e.target.setAttribute('aria-valuetext', 'top ' + S.lead.kShare + ' percent');
              document.querySelector('label[for="f-k"]').textContent = 'Leads called: top ' + S.lead.kShare + '% of the held-out cohort';
              renderPanel();
            } })),
        h('p', { class: 'scope' }, h('strong', { text: 'Filter scope. ' }),
          'Lead scoring uses a different dataset (B2B seller leads); the month filters of the marketplace views do not apply here.'),
      ]);
    } else if (v === 'experiment') {
      f.append(h('p', { class: 'scope' }, h('strong', { text: 'Filter scope. ' }),
        'The ad experiment is a separate study; no marketplace filter applies. Cost inputs live in the break-even section below and are hypothetical.'));
    } else if (v === 'definitions') {
      append(f, [h('div', { class: 'field' }, h('label', { for: 'f-defs', text: 'Find a metric' }),
        h('input', { id: 'f-defs', type: 'search', value: S.defs.search, placeholder: 'e.g. late, AOV, CACE',
          oninput: (e) => { S.defs.search = e.target.value; renderPanel(); } }))]);
    }
  }
  function checkGroup(legend, idp, all, selected, on) {
    const fs = h('fieldset', { class: 'field', style: 'border:0;padding:0;margin:0;min-width:0' },
      h('legend', { class: 'small muted', text: legend }));
    const box = h('div', { class: 'checks' });
    all.forEach((v, i) => box.append(h('label', null,
      h('input', { type: 'checkbox', id: idp + '-' + i, value: v, checked: selected.includes(v),
        onchange: () => on(all.filter((x, j) => document.getElementById(idp + '-' + j).checked)) }), v)));
    box.append(h('button', { type: 'button', class: 'btn', onclick: () => { on(all.slice()); renderFilters(); }, text: 'All' }),
      h('button', { type: 'button', class: 'btn', onclick: () => { on([]); renderFilters(); }, text: 'None' }));
    fs.append(box);
    return fs;
  }

  // -------------------------------------------------------------------- banner
  function renderBanner() {
    const b = document.getElementById('source-banner');
    b.className = 'banner ' + S.source;
    const m = DATA.sample_manifest;
    if (S.source === 'historical') {
      b.replaceChildren(
        h('p', null, badge('historical'), ' ', h('strong', { text: 'Prior full-data run (2026-07-16), not re-executed here.' }),
          ' The marketplace views load the four committed metric-layer extracts from that run; lead scoring and the experiment use its committed outputs and documented counts.'),
        h('p', null, badge('recomputed'), ' Every total, rate and ratio on the page is recomputed from those inputs with integer cents and integer counts. ',
          'The raw public dataset files were not available to this build, so no full-data pipeline stage was re-run.'));
    } else {
      b.replaceChildren(
        h('p', null, badge('synthetic'), ' ', h('strong', { text: 'Generated sample — not real data.' }),
          ' Produced by ', h('code', { text: 'make sample' }), ' (seed ' + m.seed + '): generator → dbt build (' +
          m.dbt.by_type.model + ' models, ' + m.dbt.by_type.test + ' tests, exit ' + m.dbt.exit_code + ') → extracts → models.'),
        h('p', null, 'Use it to see the pipeline and the metric rules working (including exact multi-month means). Regions "XA–XH" and "synthetic_cat_*" are invented labels.'));
    }
  }

  // ---------------------------------------------------------------- Overview
  function viewOverview(p) {
    const src = olist();
    const r = E.overview(src, { from: S.from, to: S.to });
    p.append(h('h2', { class: 'question', text: 'How did the marketplace perform in the selected months, and which operational signals deserve investigation?' }));
    if (r.error) { p.append(h('div', { class: 'error', role: 'alert', text: r.error })); announce(r.error); return; }
    const n = r.months.length;
    const range = n === 1 ? r.months[0] : r.months[0] + ' to ' + r.months[n - 1];
    p.append(h('p', { class: 'answer', 'data-testid': 'overview-answer',
      text: range + ' (' + n + ' month' + (n > 1 ? 's' : '') + '): ' + int(r.orders.value) + ' orders, GMV ' + money(r.gmv.value) +
        ', late-delivery rate ' + pct(r.late_rate.value) + ' of delivered orders.' }));
    announce('Overview updated: ' + range + ', ' + int(r.orders.value) + ' orders.');
    p.append(h('div', { class: 'grid tiles' },
      tile('Orders', r.orders, { id: 'orders', fmt: (m) => int(m.value), sub: () => 'orders purchased in the selection' }),
      tile('GMV (items + freight)', r.gmv, { id: 'gmv', fmt: (m) => money(m.value), sub: () => 'sum of integer cents; excludes item-less orders' }),
      tile('Average order value', r.aov, { id: 'aov', fmt: (m) => money(m.value), sub: (m) => money(m.num) + ' ÷ ' + int(m.den) + ' orders with items' }),
      tile('Late-delivery rate', r.late_rate, { id: 'late', fmt: (m) => pct(m.value), sub: (m) => int(m.num) + ' late ÷ ' + int(m.den) + ' delivered' }),
      tile('Cancellation rate', r.cancel_rate, { id: 'cancel', fmt: (m) => pct(m.value), sub: (m) => int(m.num) + ' cancelled ÷ ' + int(m.den) + ' orders' }),
      tile('Low-review rate (score ≤ 2)', r.low_rate, { id: 'low', fmt: (m) => pct(m.value), sub: (m) => int(m.num) + ' ÷ ' + int(m.den) + ' reviewed orders',
        inferredTitle: 'Monthly numerators inferred: the unique integer reproducing each exported rate' }),
      tile('Freight share of GMV', r.freight_share, { id: 'freight', fmt: (m) => pct(m.value), sub: (m) => money(m.num) + ' ÷ ' + money(m.den) + ' — price mix, not margin' }),
      tile('Active customers', r.active_customers, { id: 'active', fmt: (m) => int(m.value), sub: () => 'distinct people in the month' })));
    if (r.active_customers.status === 'unavailable') {
      p.lastChild.lastChild.querySelector('.sub').textContent =
        'Distinct people are not additive across months. The sum of monthly counts is ' + int(r.active_customers.alt) + ' customer-months, not people.';
    }
    if (n > 1) {
      const diff = r.naive_late_mean.value - r.late_rate.value;
      p.append(h('div', { class: 'callout warn', 'data-testid': 'weighted-callout' },
        h('h3', { text: 'Why the late rate is weighted, not averaged' }),
        h('p', { text: 'Weighted: ' + int(r.late.value) + ' late ÷ ' + int(r.delivered.value) + ' delivered = ' + pct(r.late_rate.value, 4) +
          '. The unweighted mean of the ' + r.naive_late_mean.months + ' monthly rates would be ' + pct(r.naive_late_mean.value, 4) +
          ' (' + (diff >= 0 ? '+' : '') + E.fmtFixed(diff, 4) + ' pp), because it gives every month the same weight regardless of volume. ' +
          'The dashboard always shows the weighted figure; the mean of rates is shown only here, as a counterexample.' })));
    }
    const C = COLORS();
    const labels = r.series.map((s) => s.month);
    p.append(h('div', { class: 'grid two' },
      chartCard({ key: 'ov-gmv', title: 'GMV by month', sub: 'BRL, items plus freight; axis starts at zero',
        draw: drawColumns(r.series.map((s) => ({ label: s.month, value: s.gmv_c })), (t) => E.fmtCentsCompact(t), money, 'GMV'),
        table: { caption: 'GMV, orders and AOV by month (' + SRC_LABEL[S.source] + ')',
          head: [{ label: 'Month' }, { label: 'Orders', num: true }, { label: 'GMV', num: true }, { label: 'AOV', num: true }],
          rows: r.series.map((s) => ({ cells: [s.month, int(s.orders), money(s.gmv_c), money(s.aov_c)] })) } }),
      chartCard({ key: 'ov-rates', title: 'Late deliveries and low reviews by month',
        sub: '% of delivered orders delivered late · % of reviewed orders scoring 1–2 (one shared % axis)',
        legend: [{ label: 'Late-delivery rate', color: C.s1 }, { label: 'Low-review rate', color: C.s2 }],
        draw: drawLines(labels, [
          { name: 'late-delivery rate', color: C.s1, values: r.series.map((s) => s.late_rate) },
          { name: 'low-review rate', color: C.s2, values: r.series.map((s) => s.low_rate) }], (t) => E.fmtFixed(t, t % 1 ? 1 : 0) + '%', (v) => pct(v)),
        note: 'The two lines move together in some months. That is a hypothesis to test, not a finding: the marketplace data has no randomised treatment, and volume, category mix or region could drive both.',
        table: { caption: 'Monthly late-delivery and low-review rates',
          head: [{ label: 'Month' }, { label: 'Late-delivery rate', num: true }, { label: 'Low-review rate', num: true }, { label: 'Cancellation rate', num: true }],
          rows: r.series.map((s) => ({ cells: [s.month, pct(s.late_rate), s.low_rate === null ? 'unavailable' : pct(s.low_rate), pct(s.cancel_rate)] })) } })));
    // means stored at original grain
    const meanRow = (label, m, dp) => ({ cells: [label, m.status === 'unavailable' ? { text: 'Unavailable', badges: ['unavailable'], title: m.reason } :
      { text: E.fmtFixed(m.value, dp), badges: m.basis && m.basis.indexOf('sum') === 0 ? [] : [] }, m.status === 'unavailable' ? m.reason : m.basis] });
    p.append(h('h3', { text: 'Averages stored at their original grain' }));
    p.append(h('p', { class: 'answer small', text: S.source === 'historical'
      ? 'The historical extract stores each month’s mean but not the count of valid values behind it, so a multi-month average cannot be derived exactly and is shown as unavailable. Select a single month to see its value.'
      : 'The synthetic extract carries each mean’s valid-value count and sum, so multi-month averages are exact: sum ÷ count.' }));
    p.append(dataTable({ caption: 'Selection-level averages (' + SRC_LABEL[S.source] + ')',
      head: [{ label: 'Average' }, { label: 'Selection value', num: true }, { label: 'Basis' }],
      rows: [meanRow('Delivery days (purchase → delivery)', r.delivery_days, 2), meanRow('Review score (1–5)', r.review_score, 3),
        meanRow('Items per order', r.items_per_order, 3), meanRow('Installments', r.installments, 3)] }));
    p.append(h('p', { class: 'small muted', text: S.source === 'historical'
      ? 'Analysis window 2017-01 to 2018-08. Per the prior run, 349 of 99,441 orders (0.35%) fall outside it: a 2016 pilot (with a month of zero orders) and a post-2018-08-28 export tail.'
      : 'Synthetic window 2017-01 to 2018-08; the generator also writes pilot and tail months, which the dbt window flag excludes exactly as for the real data.' }));
  }

  // ----------------------------------------------------------------- Categories
  function viewCategories(p) {
    const r = E.categories(olist(), { from: S.from, to: S.to }, S.cat);
    p.append(h('h2', { class: 'question', text: 'Where is item GMV concentrated, and how large is freight’s share of it?' }));
    if (r.error) { p.append(h('div', { class: 'error', role: 'alert', text: r.error })); announce(r.error); return; }
    if (r.empty) { p.append(h('div', { class: 'empty', text: 'No category rows in the selected months.' })); return; }
    if (r.no_match) {
      p.append(h('div', { class: 'empty', role: 'status', 'data-testid': 'category-empty',
        text: 'No category name contains “' + S.cat.search + '” in ' + r.months[0] + ' to ' + r.months[r.months.length - 1] + '. Clear the search to see all ' + r.all_count + ' categories.' }));
      announce('No matching categories.');
      return;
    }
    const top = r.shown[0];
    const fs = r.shown.map((c) => c.freight_share.value);
    const minC = r.shown[fs.indexOf(Math.min(...fs))], maxC = r.shown[fs.indexOf(Math.max(...fs))];
    p.append(h('p', { class: 'answer', 'data-testid': 'category-answer',
      text: 'Largest by GMV among those shown: ' + top.category + ', ' + money(top.gmv_c) + ' (' + pct(top.share_of_selected_gmv.value) +
        ' of selected GMV). Freight share among the ' + r.shown.length + ' shown ranges from ' + pct(minC.freight_share.value, 1) + ' (' + minC.category +
        ') to ' + pct(maxC.freight_share.value, 1) + ' (' + maxC.category + ').' }));
    announce('Categories updated: ' + r.shown.length + ' of ' + r.matched_count + ' shown.');
    p.append(h('div', { class: 'callout info' }, h('p', { text: 'Freight share = freight value ÷ item GMV. It describes what buyers pay for shipping relative to goods. It is not a margin, a cost to the marketplace or a potential saving: the data holds no costs.' })));
    const items = r.shown.map((c) => ({ label: c.category, value: c.gmv_c,
      extra: [{ value: pct(c.share_of_selected_gmv.value), label: 'of selected GMV' }] }));
    p.append(h('div', { class: 'grid two' },
      chartCard({ key: 'cat-gmv', title: 'GMV by category', sub: r.shown.length + ' of ' + r.matched_count + ' matching categories · BRL',
        draw: drawHBars(items, money, 'GMV', { fmtAxis: E.fmtCentsCompact }), table: catTable(r) }),
      chartCard({ key: 'cat-freight', title: 'Freight share of GMV', sub: 'same categories, same order · % of category GMV',
        draw: drawHBars(r.shown.map((c) => ({ label: c.category, value: c.freight_share.value })), (v) => pct(v, 1), 'freight share'),
        table: catTable(r) })));
    p.append(h('h3', { text: 'All shown categories' }), dataTable(catTable(r)));
    p.append(h('p', { class: 'small muted', text: int(r.missing_category_lines) + ' order lines in the selection have no product category (bucketed as "unknown"); ' +
      int(r.missing_translation_lines) + ' use a Portuguese category name missing from the translation table. Neither is dropped.' }));
  }
  function catTable(r) {
    const rows = r.shown.map((c) => ({ cells: [c.category, int(c.lines), int(c.orders), money(c.gmv_c), pct(c.share_of_selected_gmv.value),
      pct(c.freight_share.value), money(c.avg_line_c),
      c.customers.status === 'unavailable' ? { text: 'n/a', title: c.customers.reason } : int(c.customers.value)] }));
    rows.push({ total: true, cells: ['All categories in the months selected', int(r.total_lines.value),
      { text: int(r.category_order_pairs) + ' pairs', title: 'Category-order pairs: an order with lines in two categories counts twice. Not an order count.' },
      money(r.total_gmv.value), '100.00%', '', '', ''] });
    return { caption: 'Category performance, ' + r.months[0] + ' to ' + r.months[r.months.length - 1] + ' (' + SRC_LABEL[S.source] + ')',
      head: [{ label: 'Category' }, { label: 'Order lines', num: true }, { label: 'Orders containing it', num: true }, { label: 'GMV', num: true },
        { label: 'Share of selected GMV', num: true }, { label: 'Freight share', num: true }, { label: 'Avg line value', num: true },
        { label: 'Customers (single month only)', num: true }], rows };
  }

  // --------------------------------------------------------------------- States
  function viewStates(p) {
    const src = olist();
    const r = E.states(src, { from: S.from, to: S.to }, { states: S.st.selected });
    p.append(h('h2', { class: 'question', text: 'How do customer states compare on GMV, freight burden and delivery?' }));
    if (r.error) { p.append(h('div', { class: 'error', role: 'alert', text: r.error })); announce(r.error); return; }
    if (r.empty) {
      p.append(h('div', { class: 'empty', role: 'status', 'data-testid': 'state-empty', text: S.st.selected && S.st.selected.length === 0
        ? 'No state selected. Tick at least one state, or press "All".' : 'The selected states have no orders in these months.' }));
      announce('No state rows.');
      return;
    }
    const t = r.total;
    p.append(h('p', { class: 'answer', 'data-testid': 'state-answer',
      text: r.list.length + ' state(s) selected: ' + int(t.orders) + ' orders, GMV ' + money(t.gmv_c) + ', freight ' + pct(t.freight_share.value) +
        ' of GMV. Largest: ' + r.list[0].state + ' (' + money(r.list[0].gmv_c) + ').' }));
    announce('States updated: ' + r.list.length + ' selected.');
    const lateAvail = r.list.some((s) => s.late_rate.status !== 'unavailable');
    p.append(h('div', { class: 'grid two' },
      chartCard({ key: 'st-gmv', title: 'GMV by customer state', sub: 'BRL',
        draw: drawHBars(r.list.map((s) => ({ label: s.state, value: s.gmv_c })), money, 'GMV', { fmtAxis: E.fmtCentsCompact }), table: stateTable(r) }),
      chartCard({ key: 'st-freight', title: 'Freight share of GMV by state', sub: '% of the state’s GMV paid as freight',
        draw: drawHBars(r.list.map((s) => ({ label: s.state, value: s.freight_share.value })), (v) => pct(v, 1), 'freight share'), table: stateTable(r) })));
    if (lateAvail) {
      p.append(chartCard({ key: 'st-late', title: 'Late-delivery rate by state', sub: 'late ÷ delivered orders in the selection',
        draw: drawHBars(r.list.map((s) => ({ label: s.state, value: s.late_rate.value })), (v) => pct(v, 1), 'late-delivery rate'), table: stateTable(r) }));
    } else {
      p.append(h('div', { class: 'callout bad', 'data-testid': 'state-late-unavailable' }, h('h3', null, badge('unavailable'), ' Late-delivery rate by state'),
        h('p', { text: r.list[0].late_rate.reason }),
        h('p', { class: 'small', text: 'Select a single month to see each state’s exported rate for that month, or switch to the synthetic sample, whose extract carries the counts.' })));
    }
    p.append(h('h3', { text: 'Selected states' }), dataTable(stateTable(r)));
    if (S.source === 'historical') {
      p.append(h('p', { class: 'small muted', text: 'AOV uses orders with items, which the historical state extract does not store. It is inferred per state-month only where exactly one integer reproduces the exported AOV (all 533 cells were identified; see Definitions & sources).' }));
    }
  }
  function stateTable(r) {
    const cell = (m, f) => m.status === 'unavailable' ? { text: 'unavailable', title: m.reason } : { text: f(m.value), badges: m.status === 'inferred' ? ['inferred'] : [] };
    const rows = r.list.map((s) => ({ cells: [s.state, int(s.orders), money(s.gmv_c), cell(s.aov, money), pct(s.freight_share.value),
      cell(s.late_rate, (v) => pct(v)), cell(s.delivery_days, (v) => E.fmtFixed(v, 1)), s.cells + ' / ' + r.months.length] }));
    const t = r.total;
    rows.push({ total: true, cells: ['Selected states', int(t.orders), money(t.gmv_c), cell(t.aov, money), pct(t.freight_share.value),
      cell(t.late_rate, (v) => pct(v)), cell(t.delivery_days, (v) => E.fmtFixed(v, 1)), ''] });
    return { caption: 'State performance, ' + r.months[0] + ' to ' + r.months[r.months.length - 1] + ' (' + SRC_LABEL[S.source] + ')',
      head: [{ label: 'State' }, { label: 'Orders', num: true }, { label: 'GMV', num: true }, { label: 'AOV', num: true },
        { label: 'Freight share', num: true }, { label: 'Late-delivery rate', num: true }, { label: 'Avg delivery days', num: true },
        { label: 'Months with orders', num: true }], rows };
  }

  // ------------------------------------------------------------------- Payments
  function viewPayments(p) {
    const r = E.payments(olist(), { from: S.from, to: S.to }, { types: S.pay.selected });
    p.append(h('h2', { class: 'question', text: 'Which primary payment instrument do orders use, and how common are installments?' }));
    p.append(h('div', { class: 'callout info' }, h('p', { text: 'Primary instrument = the instrument carrying the most money on an order (one label per order). ' +
      '"Payments on these orders" is the whole payment total of those orders, including money paid with other instruments — it is not the amount paid with that instrument. ' +
      'Orders with no payment record have no primary instrument and are outside this view.' })));
    if (r.error) { p.append(h('div', { class: 'error', role: 'alert', text: r.error })); announce(r.error); return; }
    if (r.empty) {
      p.append(h('div', { class: 'empty', role: 'status', 'data-testid': 'payment-empty', text: S.pay.selected && S.pay.selected.length === 0
        ? 'No instrument selected. Tick at least one, or press "All".' : 'No payment rows in these months.' }));
      return;
    }
    const lead = r.list[0];
    p.append(h('p', { class: 'answer', 'data-testid': 'payment-answer',
      text: lead.ptype + ' is the primary instrument on ' + int(lead.orders) + ' orders (' + pct(lead.share_of_orders.value) + ' of ' +
        int(r.all_orders.value) + ' orders with a primary instrument); ' + pct(lead.installment_rate.value) + ' of them used more than one installment.' }));
    announce('Payments updated.');
    p.append(h('div', { class: 'grid two' },
      chartCard({ key: 'pay-share', title: 'Share of orders by primary instrument', sub: '% of all orders with a primary instrument in the months selected',
        draw: drawHBars(r.list.map((x) => ({ label: x.ptype, value: x.share_of_orders.value })), (v) => pct(v, 1), 'share of orders', { max: 100 }), table: payTable(r) }),
      chartCard({ key: 'pay-inst', title: 'Installment rate by primary instrument', sub: 'orders with more than one installment ÷ orders',
        draw: drawHBars(r.list.map((x) => ({ label: x.ptype, value: x.installment_rate.value })), (v) => pct(v, 1), 'installment rate', { max: 100 }), table: payTable(r) })));
    p.append(h('h3', { text: 'Primary instruments' }), dataTable(payTable(r)));
    const nullCells = r.list.reduce((a, x) => a + x.gmv_null_cells, 0);
    if (nullCells) p.append(h('p', { class: 'small muted', text: nullCells + ' group-month cell(s) in the selection have NULL GMV (orders with no items). They add nothing to GMV and make AOV for their group unavailable, because the number of orders with items in that cell is not identified.' }));
  }
  function payTable(r) {
    const cell = (m, f) => m.status === 'unavailable' ? { text: 'unavailable', title: m.reason } : { text: f(m.value), badges: m.status === 'inferred' ? ['inferred'] : [] };
    return { caption: 'Primary payment instruments, ' + r.months[0] + ' to ' + r.months[r.months.length - 1] + ' (' + SRC_LABEL[S.source] + ')',
      head: [{ label: 'Primary instrument' }, { label: 'Orders', num: true }, { label: 'Share of orders', num: true },
        { label: 'Payments on these orders', num: true }, { label: 'GMV', num: true }, { label: 'AOV', num: true },
        { label: 'Installment rate', num: true }, { label: 'Avg installments', num: true }],
      rows: r.list.map((x) => ({ cells: [x.ptype, int(x.orders), pct(x.share_of_orders.value), money(x.payments_c), money(x.gmv_c),
        cell(x.aov, money), pct(x.installment_rate.value), cell(x.installments, (v) => E.fmtFixed(v, 2))] })) };
  }

  // ---------------------------------------------------------------- Lead scoring
  function topKBlock(p, ranked, cohortLabel) {
    const d = ranked[S.lead.model];
    const n = d.scores.length;
    const k = Math.max(1, Math.floor(n * S.lead.kShare / 100));   // int(n x share), as the prior run
    const t = E.topK(d.scores, d.labels, k);
    const modelName = S.lead.model === 'lr' ? 'logistic regression' : 'gradient boosting';
    p.append(h('div', { class: 'grid tiles' },
      h('div', { class: 'card tile', 'data-metric': 'topk-hits' }, h('p', { class: 'label', text: 'Converted among the top ' + int(k) + ' (' + modelName + ')' }),
        h('p', { class: 'value', text: E.fmtFixed(t.expected, t.expected % 1 ? 2 : 0) }),
        h('p', { class: 'sub', text: t.tie_block > 1 ? 'tie-aware expectation; any tie-break gives ' + t.min + '–' + t.max + ' (tied block of ' + t.tie_block + ' at the cut-off)' : 'no tie at the cut-off' })),
      h('div', { class: 'card tile' }, h('p', { class: 'label', text: 'Expected if the same ' + int(k) + ' were picked at random' }),
        h('p', { class: 'value', text: E.fmtFixed(t.random_expected, 1) }), h('p', { class: 'sub', text: int(t.positives) + ' positives in ' + int(n) + ' leads = ' + pct(100 * t.prevalence) })),
      h('div', { class: 'card tile' }, h('p', { class: 'label', text: 'Hit rate in the top ' + int(k) }),
        h('p', { class: 'value', text: pct(100 * t.expected / t.k) }), h('p', { class: 'sub', text: 'vs ' + pct(100 * t.prevalence) + ' base rate · ' + E.fmtFixed(t.expected / t.random_expected, 2) + '× lift' }))));
    p.append(h('div', { class: 'callout warn', 'data-testid': 'topk-claim' }, h('p', { text: 'What this does and does not show: of the ' + int(k) + ' highest-scored leads in ' + cohortLabel + ', about ' +
      E.fmtFixed(t.expected, 1) + ' converted within 90 days, against ' + E.fmtFixed(t.random_expected, 1) + ' expected from a random pick. That is retrospective ranking quality. ' +
      'It is not incremental wins: these leads were worked regardless of score. Whether calling top-scored leads first creates extra conversions needs a randomised prioritisation test.' })));
    const curve = E.gains(d.scores, d.labels, 10);
    p.append(chartCard({ key: 'gains-' + S.source + '-' + S.lead.model, title: 'Cumulative gains, ' + modelName,
      sub: 'share of all 90-day conversions captured by calling the highest-scored leads first; grey line = random order',
      legend: [{ label: modelName, color: COLORS().s1 }, { label: 'random order', color: COLORS().muted }],
      draw: drawGains(curve),
      table: { caption: 'Cumulative gains by decile (tie-aware), ' + modelName, head: [{ label: 'Leads called' }, { label: 'Leads', num: true }, { label: 'Expected conversions', num: true }, { label: 'Share of conversions captured', num: true }],
        rows: curve.slice(1).map((c) => ({ cells: ['top ' + Math.round(c.share * 100) + '%', int(c.k), E.fmtFixed(c.expected, 2), pct(100 * c.captured, 1)] })) } }));
  }
  function viewLeads(p) {
    p.append(h('h2', { class: 'question', text: 'Can a lead score help sales prioritise — and what can honestly be claimed?' }));
    if (S.source === 'historical') {
      const L = DATA.leads.historical, rec = L.recomputed, a = L.audit;
      p.append(h('p', { class: 'answer', text: 'The prior run scored 2,655 held-out B2B seller leads (Apr–May 2018). Its ranking metrics reproduce exactly from the committed scores, but three problems limit what the numbers mean. Each is shown separately below.' }));
      p.append(h('div', { class: 'callout bad', 'data-testid': 'lead-maturity' }, h('h3', null, badge('retrospective'), ' 1. Labels were not available at the cut'),
        h('p', { text: 'Training used leads contacted ' + a.train_cohort[0] + ' to ' + a.train_cohort[1] + ' with 90-day labels; the test began at ' + a.cut + ' 00:00. ' +
          'Their 90-day outcome windows (contact day to contact + 90, inclusive) ended between ' + a.outcome_windows_end_between[0] + ' and ' + a.outcome_windows_end_between[1] +
          ', so the labels were usable only from ' + a.labels_usable_from_between[0] + ' to ' + a.labels_usable_from_between[1] + ' (00:00): none was complete at the cut. ' +
          'A model deployed at the cut could only have learned from leads contacted on or before ' + a.latest_contact_usable_at_cut + '. The Apr–May result is therefore a retrospective cohort backtest, not a prospective evaluation.' })));
      p.append(h('div', { class: 'callout warn' }, h('h3', { text: '2. A feature looked into the future' }),
        h('p', { text: 'page_lead_volume counted every lead on a landing page across the whole dataset, including leads that arrived later (and the test period). It never touched the label, but it was not computable when a lead arrived. The corrected pipeline uses a point-in-time count (strictly earlier leads only).' })));
      const lr = rec.models[0], gb = rec.models[1], cb = rec.constant_baseline;
      p.append(h('div', { class: 'callout warn', 'data-testid': 'lead-ties' }, h('h3', { text: '3. Top-decile hit counts depended on row order' }),
        h('p', { text: 'The top 265 were picked with argsort, which breaks ties by row order. Logistic regression has ' + lr.top_tie_block + ' leads tied at the cut-off, so any tie-break gives ' +
          lr.top_min_hits + '–' + lr.top_max_hits + ' hits (tie-aware expectation ' + E.fmtFixed(lr.top_expected_hits, 2) + '; reported ' + lr.historical_top_decile_hits + '). ' +
          'Gradient boosting: ' + gb.top_tie_block + ' tied, range ' + gb.top_min_hits + '–' + gb.top_max_hits + ', expectation ' + E.fmtFixed(gb.top_expected_hits, 2) + ' (reported ' + gb.historical_top_decile_hits + '). ' +
          'The constant base-rate baseline ties every lead: its reported ' + pct(100 * cb.historical_top_decile_rate) + ' was arbitrary; the correct expectation is the base rate, ' + pct(100 * cb.tie_aware_rate) + '.' })));
      const fmt4 = (v) => E.fmtFixed(v, 4);
      p.append(dataTable({ caption: 'Committed results vs recomputation from outputs/lead_scores_test.csv (2,655 leads, 280 positives)',
        head: [{ label: 'Model' }, { label: 'AUC', num: true }, { label: 'PR-AUC', num: true }, { label: 'Brier', num: true },
          { label: 'Reported top-265 hits', num: true }, { label: 'Tie-aware expected hits [range]', num: true }, { label: 'Status' }],
        rows: [
          { cells: ['logistic regression', fmt4(lr.auc), fmt4(lr.pr_auc), fmt4(lr.brier), int(lr.historical_top_decile_hits),
            E.fmtFixed(lr.top_expected_hits, 2) + ' [' + lr.top_min_hits + '–' + lr.top_max_hits + ']', { text: 'recomputed, matches', badges: ['recomputed', 'retrospective'] }] },
          { cells: ['gradient boosting', fmt4(gb.auc), fmt4(gb.pr_auc), fmt4(gb.brier), int(gb.historical_top_decile_hits),
            E.fmtFixed(gb.top_expected_hits, 2) + ' [' + gb.top_min_hits + '–' + gb.top_max_hits + ']', { text: 'recomputed, matches', badges: ['recomputed', 'retrospective'] }] },
          { cells: ['baseline: base rate (constant)', '0.5000', '—', fmt4(L.committed_results[0].brier), int(cb.historical_hits),
            E.fmtFixed(cb.tie_aware_expected_hits, 2) + ' [' + cb.min_hits + '–' + cb.max_hits + ']', { text: 'reported hit rate was a tie artefact', badges: ['retrospective'] }] },
          { cells: ['baseline: channel rate', fmt4(L.committed_results[1].auc), fmt4(L.committed_results[1].pr_auc), fmt4(L.committed_results[1].brier),
            int(Math.round(L.committed_results[1].top_decile_rate * 265)), { text: 'unavailable', title: rec.channel_baseline.note },
            { text: 'cannot be recomputed', badges: ['unavailable'] }] }] }));
      p.append(h('h3', { text: 'Explore the ranking (historical scores)' }));
      topKBlock(p, L.ranked, 'the Apr–May 2018 held-out cohort');
      const dd = DATA.leads.synthetic.declared_full_data_design;
      p.append(h('div', { class: 'callout info' }, h('h3', null, badge('unavailable'), ' Corrected full-data run: declared, not executed'),
        h('p', { text: 'The corrected design — train on contacts ' + dd.train_start + ' to ' + dd.train_end + ', as-of ' + dd.as_of + ' (' + dd.purge_gap_days +
          '-day purge gap), score ' + dd.score_start + ' to ' + dd.score_end + ', assuming wins are completely recorded through ' + dd.outcome_observed_through +
          ' — needs the raw Kaggle files, which this build could not download. It runs on the synthetic sample (switch the data source); on real data it remains unrerun.' })));
    } else {
      const L = DATA.leads.synthetic;
      const ok = L.designs.filter((d) => d.status === 'ok');
      const corrected = L.designs[0];
      const dz = corrected.design;
      p.append(h('p', { class: 'answer', text: 'On the synthetic funnel (' + int(L.leads) + ' leads) the corrected pipeline declares every window explicitly and refuses designs whose training labels are not mature at the as-of date.' }));
      const C = COLORS();
      p.append(chartCard({ key: 'lead-timeline', title: 'Corrected design: windows',
        sub: 'train only on labels complete before as-of; score a later cohort; evaluate once its outcomes are observable',
        draw: drawTimeline([
          { label: 'Train cohort', from: dz.train_start, to: dz.train_end, color: C.s1 },
          { label: 'Purge gap', from: dz.train_end, to: dz.as_of, color: C.axis },
          { label: 'Score cohort', from: dz.score_start, to: dz.score_end, color: C.s2 },
          { label: 'Outcomes observed', from: dz.score_start, to: dz.outcome_observed_through, color: C.s3 }], '2017-12-01', '2018-09-15'),
        table: { caption: 'Declared windows (synthetic run)', head: [{ label: 'Window' }, { label: 'From' }, { label: 'To' }],
          rows: [{ cells: ['Train cohort', dz.train_start, dz.train_end] }, { cells: ['As-of (deployment)', dz.as_of, '—'] },
            { cells: ['Score cohort', dz.score_start, dz.score_end] }, { cells: ['Outcomes assumed observed through', '—', dz.outcome_observed_through] }] } }));
      const byModel = (d, name) => d.results.find((m) => m.model === name) || {};
      const topTxt = (m) => m.top_k ? E.fmtFixed(m.top_expected_hits, 2) + (m.top_tie_block > 1 ? ' [' + m.top_min_hits + '–' + m.top_max_hits + ']' : '') : '—';
      const rowsT = L.designs.map((d) => {
        if (d.status !== 'ok') {
          return { cells: [d.design.name, { text: 'refused', badges: ['unavailable'] }, '—', '—', '—', '—', '—', '—', { text: d.problems.join(' ') }] };
        }
        const lr = byModel(d, 'logistic regression'), gb = byModel(d, 'gradient boosting'), ch = byModel(d, 'baseline: channel rate (train only)');
        return { cells: [d.design.name, { text: 'ran', badges: ['synthetic'] }, int(d.train_n) + ' / ' + int(d.train_positives),
          int(d.train_labels_immature_at_as_of), int(d.score_n) + ' / ' + int(d.score_positives),
          E.fmtFixed(lr.auc, 3), E.fmtFixed(gb.auc, 3) + ' / ' + E.fmtFixed(ch.auc, 3),
          topTxt(lr) + ' of ' + int(lr.top_k), 'random pick: ' + E.fmtFixed(lr.random_expected_hits, 1)] };
      });
      p.append(dataTable({ caption: 'Designs run on the synthetic funnel (top-10% = tie-aware expected hits for logistic regression)',
        head: [{ label: 'Design' }, { label: 'Status' }, { label: 'Train n / positives', num: true }, { label: 'Train labels incomplete at as-of', num: true },
          { label: 'Score n / positives', num: true }, { label: 'LR AUC', num: true }, { label: 'GB / channel-rate AUC', num: true },
          { label: 'LR top-10% hits', num: true }, { label: 'Notes' }], rows: rowsT }));
      p.append(h('p', { class: 'small muted', text: 'The legacy look-ahead feature does not move results in one direction on this synthetic draw; the defect is that the feature could not exist at scoring time, not a guaranteed inflation. ' +
        'The "historical calendar split" row reproduces the old design only to show that all of its training labels were immature at its cut (' + int(ok[ok.length - 1].train_labels_immature_at_as_of) + ' of ' + int(ok[ok.length - 1].train_n) + ').' }));
      p.append(h('h3', { text: 'Explore the ranking (corrected design, synthetic scores)' }));
      topKBlock(p, L.ranked, 'the synthetic May-2018 score cohort');
    }
  }

  // ------------------------------------------------------------------ Experiment
  function viewExperiment(p) {
    const X = DATA.experiment[S.source];
    p.append(h('h2', { class: 'question', text: 'Did the ad campaign lift conversions, and what would it need to be worth to pay back?' }));
    if (X.status !== 'ok' || !X.itt || X.itt.status !== 'ok' || !X.itt.ci) {
      p.append(h('div', { class: 'error', role: 'alert', text: 'The experiment counts cannot support an interval estimate: ' +
        ((X.problems || []).concat((X.itt && X.itt.warnings) || []).join(' ') || 'invalid input') }));
      return;
    }
    const it = X.itt, ca = X.cace, nv = X.naive, c = X.counts;
    p.append(h('p', { class: 'answer', 'data-testid': 'exp-answer',
      text: 'Assigning users to the campaign changed conversion by ' + pp(it.diff) + ' (95% CI ' + pp(it.ci[0]) + ' to ' + pp(it.ci[1]) + '), a relative lift of ' +
        pct(100 * it.relative_lift, 2) + '. That is about ' + E.fmtFixed(1000 * it.diff, 2) + ' extra conversions per 1,000 assigned users. Whether that pays depends on cost and margin, which the data does not contain.' }));
    p.append(h('p', { class: 'small' }, S.source === 'historical' ? [badge('historical'), ' ', badge('recomputed'),
      ' Counts from the prior full-data run (docs/data-verification.md); statistics recomputed here. Exposed conversions (' + int(c.y_exposed) + ') are ', badge('inferred'),
      ' as the only integer matching the documented 5.3784% rate. The raw file was not re-read.'] :
      [badge('synthetic'), ' Generated RCT with a known truth: true ITT ' + E.fmtFixed(X.truth.true_itt_pp, 4) + ' pp, true complier effect ' + E.fmtFixed(X.truth.true_cace_pp, 2) + ' pp.']));
    const tileRaw = (label, value, sub, badges, id) => h('div', { class: 'card tile', 'data-metric': id }, h('p', { class: 'label', text: label }),
      h('p', { class: 'value', text: value }), h('p', { class: 'sub', text: sub }), h('div', { class: 'badges' }, badges));
    const b0 = () => (S.source === 'historical' ? [badge('recomputed')] : [badge('synthetic')]);
    p.append(h('div', { class: 'grid tiles' },
      tileRaw('ITT effect (assigned vs control)', pp(it.diff), '95% CI ' + pp(it.ci[0]) + ' to ' + pp(it.ci[1]) + ' · ' + int(c.y_t) + '/' + int(c.n_t) + ' vs ' + int(c.y_c) + '/' + int(c.n_c), b0(), 'itt'),
      tileRaw('Relative lift (ITT ÷ control rate)', pct(100 * it.relative_lift, 2), '95% CI ' + pct(100 * it.relative_ci[0], 1) + ' to ' + pct(100 * it.relative_ci[1], 1), b0(), 'rel'),
      tileRaw('CACE: effect on compliers only', pp(ca.cace, 3), '95% CI ' + pp(ca.ci[0], 3) + ' to ' + pp(ca.ci[1], 3) + ' · compliance ' + pct(100 * ca.compliance, 4) + ' · needs the exclusion restriction', b0(), 'cace'),
      tileRaw('Exposed vs control (naive)', pct(100 * nv.relative, 1), 'NOT an effect: exposure is selected by user behaviour after assignment', b0(), 'naive'),
      tileRaw('Minimum detectable effect (80% power)', pp(X.cohen_h_mde80, 4), '95% power: ' + pp(X.cohen_h_mde95, 4) + ' · significance ≠ importance', b0(), 'mde')));
    const rows = [{ label: 'ITT (all assigned)', est: 100 * it.diff, lo: 100 * it.ci[0], hi: 100 * it.ci[1],
      truth: S.source === 'synthetic' ? X.truth.true_itt_pp : undefined }];
    p.append(chartCard({ key: 'exp-itt-' + S.source, title: 'ITT effect with 95% interval', sub: 'percentage points of conversion; the grey line marks the 80%-power minimum detectable effect' +
      (S.source === 'synthetic' ? '; diamond = true value built into the synthetic data' : ''),
      legend: S.source === 'synthetic' ? [{ label: 'estimate and 95% CI', color: COLORS().s1 }, { label: 'true value', color: COLORS().s2, box: true }] : null,
      draw: drawIntervals(rows, (v) => E.fmtFixed(v, 3) + ' pp', [{ value: 100 * X.cohen_h_mde80, label: 'MDE' }]),
      table: { caption: 'Estimates (' + (S.source === 'historical' ? 'historical counts, recomputed' : 'synthetic') + ')',
        head: [{ label: 'Estimate' }, { label: 'Point', num: true }, { label: '95% interval', num: true }, { label: 'Meaning' }],
        rows: [
          { cells: ['ITT, absolute', pp(it.diff), pp(it.ci[0]) + ' to ' + pp(it.ci[1]), 'effect of assigning a user to the campaign'] },
          { cells: ['ITT, relative', pct(100 * it.relative_lift, 2), pct(100 * it.relative_ci[0], 2) + ' to ' + pct(100 * it.relative_ci[1], 2), 'ITT ÷ control conversion rate'] },
          { cells: ['CACE', pp(ca.cace, 4), pp(ca.ci[0], 4) + ' to ' + pp(ca.ci[1], 4), 'compliers only; needs exclusion restriction'] },
          { cells: ['Wald vs decomposition gap', E.fmtFixed(100 * ca.wald_vs_decomposition_gap, 6) + ' pp', '—', 'two derivations of CACE agree'] },
          { cells: ['Naive exposed vs control', pct(100 * nv.relative, 2), '—', 'selection, not causation'] }] } }));
    const lp = it.log10_p_value;
    p.append(h('div', { class: 'callout info', 'data-testid': 'significance' }, h('h3', { text: 'Statistical significance is not practical importance' }),
      h('p', { text: 'z = ' + E.fmtFixed(it.z, 2) + ', two-sided p ≈ 10^' + E.fmtFixed(lp, 1) + '. That only says the effect is unlikely to be exactly zero. ' +
        'With ' + int(c.n_t + c.n_c) + ' users the design detects differences of ' + pp(X.cohen_h_mde80, 4) + ' with 80% power; the observed effect is ' +
        E.fmtFixed(it.diff / X.cohen_h_mde80, 1) + '× that. ' + (it.diff / X.cohen_h_mde80 >= 5
          ? 'The test is heavily powered, so even a commercially trivial effect would be "significant": the p-value adds almost nothing. '
          : 'The test is only modestly powered for an effect this size, so the interval is wide relative to the estimate. ') +
        'The interval, the absolute size and the economics carry the decision.' })));
    const asm = h('ul', { class: 'check-list' });
    const MARK = { design: '✓', checked: '✓', assumed: '?' };
    X.assumptions.forEach((a) => asm.append(h('li', { 'data-mark': MARK[a.kind] || '?' }, h('strong', { text: a.name }),
      ' (used by ' + a.used_by + '): ' + a.status + '.')));
    p.append(h('h3', { text: 'Assumptions behind each estimate' }), asm);
    const dg = X.diagnostics;
    if (dg) {
      p.append(h('p', { class: 'small', 'data-testid': 'balance' }, S.source === 'historical' ? badge('historical') : badge('synthetic'),
        ' Covariate balance on ' + dg.covariate + ' (standardised mean difference): across the randomised arms ' + E.fmtFixed(dg.smd_treatment, 4) +
        '; exposed vs unexposed within the treated arm ' + E.fmtFixed(dg.smd_exposure_within_treated, 4) + '. Values under about 0.1 are conventionally read as balanced. Source: ' + dg.provenance + '.'));
    }
    const warn = (it.warnings || []).concat(ca.warnings || []);
    if (warn.length) p.append(h('p', { class: 'na-note', text: 'Approximation warnings: ' + warn.join(' · ') }));
    // hypothetical economics
    const calc = h('div', { class: 'card', 'data-testid': 'breakeven' });
    p.append(h('h3', null, badge('hypothetical'), ' Break-even calculator'), calc);
    // Inputs are built ONCE; a change only redraws the output. (Re-creating a focused input
    // made the browser fire a second change on blur in the middle of the first redraw.)
    const basisId = nextId('basis');
    const out = h('div', { role: 'status', 'aria-live': 'polite', 'data-testid': 'breakeven-out' });
    const onInput = (field) => (e) => { S.exp[field] = e.target.value.trim(); drawOut(); };
    calc.append(h('p', { class: 'small', text: 'Type your own numbers. Neither dataset contains ad cost or conversion value; results below are only as good as your inputs.' }),
      h('div', { class: 'filters', style: 'margin:.4rem 0' },
        h('fieldset', { class: 'field', style: 'border:0;padding:0;margin:0' }, h('legend', { class: 'small muted', text: 'Cost is quoted per 1,000' }),
          h('div', { class: 'checks' }, ['assigned', 'exposed'].map((b) => h('label', null,
            h('input', { type: 'radio', name: basisId, value: b, checked: S.exp.basis === b, onchange: () => { S.exp.basis = b; drawOut(); } }),
            b === 'assigned' ? 'assigned users' : 'exposed users (impressions delivered)')))),
        h('div', { class: 'field' }, h('label', { for: 'be-cost', text: 'Cost per 1,000 (any currency)' }),
          h('input', { id: 'be-cost', type: 'text', inputmode: 'decimal', value: S.exp.cost, placeholder: 'e.g. 2.50',
            onchange: onInput('cost'), oninput: onInput('cost') })),
        h('div', { class: 'field' }, h('label', { for: 'be-value', text: 'Value per incremental conversion (same currency)' }),
          h('input', { id: 'be-value', type: 'text', inputmode: 'decimal', value: S.exp.value, placeholder: 'e.g. 5',
            onchange: onInput('value'), oninput: onInput('value') }))),
      out);
    function drawOut() {
      out.replaceChildren();
      if (S.exp.cost === '' && S.exp.value === '') {
        out.append(h('p', { class: 'empty', text: 'Enter a cost and a value to see the hypothetical net effect. Rule of thumb from the ITT alone: each 1 unit of cost per 1,000 assigned users needs a value of about ' +
          E.fmtFixed(1 / (1000 * it.diff), 3) + ' units per incremental conversion to break even (' + E.fmtFixed(1 / (1000 * it.ci[1]), 3) + ' to ' + E.fmtFixed(1 / (1000 * it.ci[0]), 3) + ' across the 95% interval).' }));
        return;
      }
      const res = E.breakeven(it.diff, it.ci, ca.compliance, { basis: S.exp.basis, cost: S.exp.cost, value: S.exp.value });
      if (res.error) { out.append(h('p', { class: 'error', role: 'alert', text: res.error })); return; }
      out.append(h('dl', { class: 'kv' },
        h('dt', { text: 'Cost per 1,000 assigned users' }), h('dd', { text: E.fmtFixed(res.cost_per_1000_assigned, 4) }),
        h('dt', { text: 'Incremental conversions per 1,000 assigned' }), h('dd', { text: E.fmtFixed(res.incremental_per_1000, 3) + ' (95% CI ' + E.fmtFixed(res.incremental_ci[0], 3) + ' to ' + E.fmtFixed(res.incremental_ci[1], 3) + ')' }),
        h('dt', { text: 'Hypothetical net value per 1,000 assigned' }), h('dd', { text: E.fmtFixed(res.net_per_1000, 3) + ' (range ' + E.fmtFixed(res.net_ci[0], 3) + ' to ' + E.fmtFixed(res.net_ci[1], 3) + ')' }),
        h('dt', { text: 'Break-even value per incremental conversion' }), h('dd', { text: res.breakeven_value === null ? 'none (no positive effect)' : E.fmtFixed(res.breakeven_value, 3) +
          ' (' + E.fmtFixed(res.breakeven_range[0], 3) + ' to ' + (res.breakeven_range[1] === null ? '∞' : E.fmtFixed(res.breakeven_range[1], 3)) + ')' })));
      out.append(h('p', { class: 'small muted', text: 'Uses the ITT (all assigned users), never CACE or the naive comparison. Ignores long-term effects, cannibalisation and cost of the control arm.' }));
    }
    drawOut();
  }

  // ---------------------------------------------------------------- Definitions
  function viewDefinitions(p) {
    p.append(h('h2', { class: 'question', text: 'What exactly does each number mean, where does it come from, and what was checked?' }));
    p.append(h('h3', { text: 'Provenance badges' }));
    const ul = h('ul', { class: 'check-list' });
    DATA.badges.forEach((b) => ul.append(h('li', { 'data-mark': '' }, badge(b.id), ' ' + b.meaning)));
    p.append(ul);
    const q = S.defs.search.trim().toLowerCase();
    const ms = DATA.metrics.filter((m) => !q || (m.name + ' ' + m.id + ' ' + m.definition + ' ' + m.views).toLowerCase().includes(q));
    p.append(h('h3', { text: 'Metric dictionary (' + ms.length + ' of ' + DATA.metrics.length + ')' }));
    if (!ms.length) p.append(h('p', { class: 'empty', role: 'status', text: 'No metric matches “' + S.defs.search + '”.' }));
    else p.append(dataTable({ caption: 'Definitions, numerators, denominators and how a selection is combined',
      head: [{ label: 'Metric' }, { label: 'Definition' }, { label: 'Numerator ÷ denominator' }, { label: 'Grain' }, { label: 'Combining a selection' }],
      rows: ms.map((m) => ({ cells: [m.name, m.definition, m.numerator + ' ÷ ' + m.denominator, m.grain, m.combine] })) }));
    p.append(h('h3', { text: 'Sources and licences' }));
    p.append(dataTable({ caption: 'Data sources (raw data is never committed)',
      head: [{ label: 'Source' }, { label: 'Licence' }, { label: 'Documented size' }, { label: 'What is in this repository' }, { label: 'Obligations' }],
      rows: DATA.sources.map((s) => ({ cells: [s.name + ' — ' + s.publisher, s.license, s.rows_documented, s.in_repo, s.obligations] })) }));
    const H = DATA.olist.historical;
    p.append(h('h3', { text: 'Inference audit (historical extracts)' }));
    const inf = Object.entries(H.inference.summary).map(([k, v]) => ({ cells: [k, int(v.inferred), int(v.unavailable)] }));
    p.append(dataTable({ caption: 'Denominators/numerators not stored in the historical extracts, recovered only when unique',
      head: [{ label: 'Extract.field' }, { label: 'Uniquely identified', num: true }, { label: 'Not identified (unavailable)', num: true }], rows: inf }));
    H.inference.not_identified.forEach((e) => p.append(h('p', { class: 'small' }, badge('unavailable'), ' ' + e.extract + ' ' + e.key + ': ' + e.reason)));
    p.append(h('h3', { text: 'Per-month reconciliation between extracts' }));
    ['historical', 'synthetic'].forEach((s) => {
      const R = DATA.olist[s].reconciliation;
      p.append(h('p', { class: 'small', text: SRC_LABEL[s] + ': ' + Object.entries(R.counts).map(([k, v]) => v + ' ' + k).join(', ') +
        '. "bounded" = a weaker check that passed (e.g. category order counts are not exclusive); "unsupported" = the extract cannot support the check.' }));
    });
    const det = h('details', null, h('summary', { text: 'Show the ' + H.reconciliation.non_exact.length + ' non-exact historical checks' }));
    det.append(dataTable({ caption: 'Historical checks that are bounded or unsupported', head: [{ label: 'Check' }, { label: 'Month' }, { label: 'Result' }, { label: 'Detail' }],
      rows: H.reconciliation.non_exact.map((c) => ({ cells: [c.check, c.month, c.result, c.detail] })) }));
    p.append(det);
    const inputs = h('details', null, h('summary', { text: 'Build inputs and their SHA-256 (' + Object.keys(DATA.inputs).length + ' files)' }));
    inputs.append(dataTable({ caption: 'Every committed file this page was built from', head: [{ label: 'File' }, { label: 'SHA-256' }],
      rows: Object.entries(DATA.inputs).map(([f, s]) => ({ cells: [f, h('code', { text: s })] })) }));
    p.append(inputs);
  }

  // ----------------------------------------------------------------------- Memo
  function viewMemo(p) {
    const H = DATA.olist.historical;
    const o = E.overview(H, { from: H.months[0], to: H.months[H.months.length - 1] });
    const worst = o.series.slice().sort((a, b) => b.late_rate - a.late_rate).slice(0, 3);
    const st = E.states(H, { from: H.months[0], to: H.months[H.months.length - 1] }, {});
    const fsorted = st.list.slice().sort((a, b) => b.freight_share.value - a.freight_share.value);
    const X = DATA.experiment.historical, lr = DATA.leads.historical.recomputed.models[0];
    const m = h('article', { class: 'memo', 'data-testid': 'memo' });
    m.append(h('p', { class: 'small' }, badge('historical'), ' ', badge('recomputed'), ' Numbers below are recomputed from the historical inputs, whatever data source is selected above.'));
    m.append(h('h2', { text: 'Decision memo' }));
    m.append(h('p', null, h('strong', { text: 'Bottom line. ' }),
      'Nothing here proves that any intervention would raise revenue. The data supports three investigations and one budgeting rule, each framed as a test to run rather than a gain already demonstrated.'));
    m.append(h('h3', { text: 'What the data shows' }));
    m.append(h('ul', null,
      h('li', { text: 'Marketplace, ' + o.months[0] + ' to ' + o.months[o.months.length - 1] + ': ' + int(o.orders.value) + ' orders, GMV ' + money(o.gmv.value) + ', AOV ' + money(o.aov.value) +
        ' (GMV ÷ ' + int(o.orders_with_items.value) + ' orders with items).' }),
      h('li', { text: 'Late deliveries: ' + pct(o.late_rate.value) + ' of delivered orders (' + int(o.late.value) + ' ÷ ' + int(o.delivered.value) + '), concentrated in ' +
        worst.map((w) => w.month + ' (' + pct(w.late_rate) + ')').join(', ') + '. Low reviews (score ≤ 2): ' + pct(o.low_rate.value) + ' of reviewed orders.' }),
      h('li', { text: 'Freight share of GMV varies by customer state from ' + pct(fsorted[fsorted.length - 1].freight_share.value, 1) + ' (' + fsorted[fsorted.length - 1].state + ', ' +
        int(fsorted[fsorted.length - 1].orders) + ' orders) to ' + pct(fsorted[0].freight_share.value, 1) + ' (' + fsorted[0].state + ', only ' + int(fsorted[0].orders) +
        ' orders, so treat the extreme with care). It is a price-mix measure, not margin.' }),
      h('li', { text: 'Ad experiment: assigning users to the campaign raised conversion by ' + pp(X.itt.diff) + ' (95% CI ' + pp(X.itt.ci[0]) + ' to ' + pp(X.itt.ci[1]) +
        '), about ' + E.fmtFixed(1000 * X.itt.diff, 2) + ' conversions per 1,000 assigned users. Only ' + pct(100 * X.cace.compliance, 2) + ' of treated users were exposed.' }),
      h('li', { text: 'Lead scoring: logistic regression ranks held-out leads with AUC ' + E.fmtFixed(lr.auc, 3) + ' — a retrospective result (labels immature at the cut, a look-ahead feature), not a deployable estimate.' })));
    m.append(h('h3', { text: 'Recommendations (investigations and experiments, not promised gains)' }));
    m.append(h('ol', null,
      h('li', null, h('strong', { text: 'Diagnose the late-delivery spikes. ' }), 'Break the worst months down by seller, carrier region and category (needs order-level data), then test one change — e.g. a padded delivery estimate or a carrier switch for the worst lanes — in a randomised rollout, measuring late rate and review score. The monthly co-movement of late deliveries and low reviews is a hypothesis until then.'),
      h('li', null, h('strong', { text: 'Price freight where it bites. ' }), 'States with the highest freight share are candidates for a freight-subsidy or threshold experiment. Without cost and margin data the dashboard cannot say whether a subsidy pays; the experiment must record both.'),
      h('li', null, h('strong', { text: 'Re-evaluate lead scoring prospectively. ' }), 'Retrain with mature labels only (as-of design, point-in-time features — implemented and demonstrated on synthetic data), then run a randomised prioritisation test (score order vs current order) before claiming any extra wins.'),
      h('li', null, h('strong', { text: 'Budget ads on the ITT, not on exposure. ' }), 'Use the ITT and its interval with real cost and margin (the break-even calculator shows the arithmetic). Do not budget on the naive exposed-vs-control lift or on CACE. Most assigned users were never exposed; before scaling, find out why (the data records exposure, not its cause).')));
    m.append(h('h3', { text: 'What we cannot claim' }));
    m.append(h('ul', null,
      h('li', { text: 'Any causal effect of delivery speed, freight or payment method on sales or reviews: the marketplace data has no randomised treatment.' }),
      h('li', { text: 'Any ROI: neither dataset holds costs or margins.' }),
      h('li', { text: 'That the reconstructed dbt intermediate layer reproduces the historical numbers: it was validated on synthetic data only.' }),
      h('li', { text: 'Why no 2017 lead converted within 90 days: the regime break is observed, its cause is unknown.' }),
      h('li', { text: 'Anything about the real marketplace or ad experiment from the synthetic sample.' })));
    p.append(m);
  }

  // ----------------------------------------------------------------- rendering
  // A render triggered while another is removing nodes (e.g. by a blur-time change event)
  // is deferred to a microtask instead of running nested.
  let busy = false;
  function guarded(fn) {
    return function () {
      if (busy) { queueMicrotask(() => guarded(fn)()); return; }
      busy = true;
      try { fn(); } finally { busy = false; }
    };
  }
  const VIEW_FN = { overview: viewOverview, categories: viewCategories, states: viewStates, payments: viewPayments,
    leads: viewLeads, experiment: viewExperiment, definitions: viewDefinitions, memo: viewMemo };
  function renderPanelNow() {
    VIEWS.forEach((v) => { document.getElementById('panel-' + v).hidden = v !== S.view; });
    const p = document.getElementById('panel-' + S.view);
    p.replaceChildren();
    VIEW_FN[S.view](p);
  }
  const renderPanel = guarded(renderPanelNow);
  function renderTabs() {
    document.querySelectorAll('[role="tab"]').forEach((t) => {
      const on = t.dataset.view === S.view;
      t.setAttribute('aria-selected', String(on));
      t.tabIndex = on ? 0 : -1;
    });
  }
  const render = guarded(function () {
    document.querySelectorAll('input[name="source"]').forEach((i) => { i.checked = i.value === S.source; });
    renderBanner();
    renderTabs();
    renderFilters();
    renderPanelNow();
    writeHash();
  });
  function selectView(v, focus) {
    S.view = v;
    render();
    if (focus) document.getElementById('tab-' + v).focus();
  }

  document.getElementById('tablist').addEventListener('click', (e) => {
    const t = e.target.closest('[role="tab"]');
    if (t) selectView(t.dataset.view, false);
  });
  document.getElementById('tablist').addEventListener('keydown', (e) => {
    const i = VIEWS.indexOf(S.view);
    let j = null;
    if (e.key === 'ArrowRight') j = (i + 1) % VIEWS.length;
    else if (e.key === 'ArrowLeft') j = (i - 1 + VIEWS.length) % VIEWS.length;
    else if (e.key === 'Home') j = 0;
    else if (e.key === 'End') j = VIEWS.length - 1;
    if (j !== null) { e.preventDefault(); selectView(VIEWS[j], true); }
  });
  document.querySelectorAll('input[name="source"]').forEach((i) => i.addEventListener('change', () => {
    S.source = i.value;
    render();
    announce('Data source: ' + SRC_LABEL[S.source]);
  }));
  const themeBtn = document.getElementById('theme-toggle');
  const THEMES = ['auto', 'light', 'dark'];
  let theme = 'auto';
  try { theme = localStorage.getItem('dash-theme') || 'auto'; } catch (e) { /* storage may be blocked */ }
  function applyTheme() {
    if (theme === 'auto') document.documentElement.removeAttribute('data-theme');
    else document.documentElement.setAttribute('data-theme', theme);
    themeBtn.textContent = 'Theme: ' + theme;
    themeBtn.setAttribute('aria-label', 'Colour theme: ' + (theme === 'auto' ? 'follow system' : theme) + '. Activate to change.');
  }
  themeBtn.addEventListener('click', () => {
    theme = THEMES[(THEMES.indexOf(theme) + 1) % THEMES.length];
    try { localStorage.setItem('dash-theme', theme); } catch (e) { /* ignore */ }
    applyTheme();
    renderPanel();
  });
  window.addEventListener('hashchange', () => { readHash(); render(); });
  applyTheme();
  readHash();
  render();
  window.__dashboard = { state: S, data: DATA, render };   // for automated browser checks
})();
