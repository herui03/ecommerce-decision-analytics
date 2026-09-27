/*
 * Decision-dashboard calculation engine. Pure functions, no DOM.
 *
 * Rules this file enforces (see docs/metric-dictionary.md):
 *  - Money arrives as INTEGER CENTS and is summed as integers. Division happens only
 *    when a value is formatted for display.
 *  - Every rate is sum(numerator) / sum(denominator) over the selection - never a mean
 *    of per-row rates. The naive mean of monthly rates is computed only to show the
 *    difference, and is labelled as such.
 *  - A mean stored at its original grain (delivery days, review score, installments,
 *    items per order) is combined only when the extract carries its valid-value count
 *    and sum. Otherwise it is available for a single row only, and UNAVAILABLE for a
 *    multi-row selection.
 *  - Distinct counts (customers, products, sellers, category orders across categories)
 *    are never summed into a total.
 *  - A value inferred by the build (bounded unique-integer inference) carries status
 *    "inferred"; if any cell in a selection is unidentified the aggregate is
 *    "unavailable" - the cell is never silently dropped.
 *
 * Loaded as a plain <script> in the dashboard (global `Engine`) and by Node tests
 * (module.exports).
 */
var Engine = (function () {
  'use strict';

  // ------------------------------------------------------------------ formatting
  function group(intStr) {
    return intStr.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  }
  function fmtInt(n) {
    if (n === null || n === undefined || !isFinite(n)) return '—';
    var s = n < 0 ? '-' : '';
    return s + group(String(Math.abs(Math.round(n))));
  }
  /** Integer cents -> "BRL 1,234.56" using integer arithmetic only. */
  function fmtCents(c, withCode) {
    if (c === null || c === undefined) return '—';
    if (!Number.isSafeInteger(c)) throw new Error('cents must be a safe integer: ' + c);
    var neg = c < 0, a = Math.abs(c);
    var whole = Math.floor(a / 100), frac = a % 100;
    var s = (neg ? '-' : '') + group(String(whole)) + '.' + (frac < 10 ? '0' : '') + frac;
    return withCode === false ? s : 'BRL ' + s;
  }
  /** Compact axis label from cents: BRL 1.2M / 350K. Presentation only. */
  function fmtCentsCompact(c) {
    var v = c / 100;
    var a = Math.abs(v);
    var trim = function (x) { return x.toFixed(2).replace(/\.?0+$/, ''); };
    if (a >= 1e6) return trim(v / 1e6) + 'M';
    if (a >= 1e3) return trim(v / 1e3) + 'K';
    return trim(v);
  }
  function fmtFixed(x, dp) {
    if (x === null || x === undefined || !isFinite(x)) return '—';
    var s = Math.abs(x).toFixed(dp);
    var parts = s.split('.');
    var out = group(parts[0]) + (parts.length > 1 ? '.' + parts[1] : '');
    return (x < 0 && Number(s) !== 0 ? '-' : '') + out;
  }
  function fmtPct(x, dp) {             // x is already a percentage
    return x === null || x === undefined ? '—' : fmtFixed(x, dp === undefined ? 2 : dp) + '%';
  }
  /** Average money value from integer cents / integer count, rounded half-up to cents. */
  function centsPer(cents, n) {
    if (cents === null || n === null || n === 0) return null;
    return Math.round(cents / n);
  }

  // --------------------------------------------------------------- metric results
  function ok(value, extra) { return Object.assign({ status: 'ok', value: value }, extra || {}); }
  function unavailable(reason, extra) {
    return Object.assign({ status: 'unavailable', value: null, reason: reason }, extra || {});
  }
  function rate(num, den, extra) {
    if (num.status === 'unavailable') return unavailable(num.reason, extra);
    if (den.status === 'unavailable') return unavailable(den.reason, extra);
    if (num.value === null || den.value === null) return unavailable('no recorded value in this selection', extra);
    if (den.value === 0) return unavailable('denominator is zero for this selection', extra);
    var r = ok(100 * num.value / den.value, Object.assign({ num: num.value, den: den.value }, extra || {}));
    if (num.status === 'inferred' || den.status === 'inferred') r.status = 'inferred';
    return r;
  }
  /** Sum an integer field. statusField (optional) marks per-row observed/inferred/unavailable. */
  function sumField(rows, f, statusField) {
    var total = 0, inferred = false, missing = 0, nullCount = 0;
    for (var i = 0; i < rows.length; i++) {
      var r = rows[i];
      var st = statusField ? r[statusField] : 'observed';
      if (st === 'unavailable') { missing++; continue; }
      if (st === 'inferred') inferred = true;
      var v = r[f];
      if (v === null || v === undefined) { nullCount++; continue; }
      total += v;
    }
    if (!Number.isSafeInteger(total)) throw new Error('sum exceeds safe integer range: ' + f);
    if (missing) return unavailable(missing + ' cell(s) in this selection have no identified ' + f +
      ' (see Definitions & sources > inference audit)', { missing: missing });
    // every row NULL: no value was recorded (e.g. GMV of item-less orders) - not zero
    var allNull = rows.length > 0 && nullCount === rows.length;
    return { status: inferred ? 'inferred' : 'ok', value: allNull ? null : total, nulls: nullCount };
  }

  // ------------------------------------------------------------------ axis scale
  /** Clean axis: step from {1, 2, 2.5, 5} x 10^k, ~targetTicks intervals covering [lo, hi]. */
  function niceScale(lo, hi, targetTicks) {
    targetTicks = targetTicks || 4;
    if (!(hi > lo)) { hi = lo + 1; }
    var raw = (hi - lo) / targetTicks;
    var k0 = Math.floor(Math.log10(raw));
    var best = null;
    for (var k = k0 - 1; k <= k0 + 1; k++) {
      [1, 2, 2.5, 5].forEach(function (m) {
        var step = m * Math.pow(10, k);
        var min = Math.floor(lo / step + 1e-9) * step, max = Math.ceil(hi / step - 1e-9) * step;
        var n = Math.round((max - min) / step);
        if (n < targetTicks - 1 || n > targetTicks + 1) return;
        var waste = (max - hi) + (lo - min);
        if (!best || waste < best.waste - 1e-12 * (hi - lo) || (Math.abs(waste - best.waste) <= 1e-12 * (hi - lo) && n < best.n)) {
          best = { min: min, max: max, step: step, n: n, waste: waste };
        }
      });
    }
    var ticks = [];
    for (var i = 0; i <= best.n; i++) ticks.push(Math.round((best.min + i * best.step) / best.step) * best.step);
    return { min: best.min, max: best.max, step: best.step, ticks: ticks };
  }
  /** Which category-axis labels to draw so they never collide: every `step`-th, always the
   *  last, dropping the stepped label just before the last if it would sit too close. */
  function labelIndices(n, step) {
    var out = [];
    for (var i = 0; i < n; i += step) out.push(i);
    if (out[out.length - 1] !== n - 1) {
      if (n - 1 - out[out.length - 1] < step * 0.75) out.pop();
      out.push(n - 1);
    }
    return out;
  }

  // --------------------------------------------------------------------- months
  function monthRange(allMonths, from, to) {
    var a = allMonths.indexOf(from), b = allMonths.indexOf(to);
    if (a < 0 || b < 0) return { ok: false, error: 'Unknown month in the selection.' };
    if (a > b) return { ok: false, error: 'The start month (' + from + ') is after the end month (' + to + '). Choose a start on or before the end.' };
    return { ok: true, months: allMonths.slice(a, b + 1) };
  }
  function inMonths(rows, months) {
    var set = {};
    months.forEach(function (m) { set[m] = true; });
    return rows.filter(function (r) { return set[r.month]; });
  }

  // ------------------------------------------------------ original-grain means
  /** Combine a mean across rows. Exact when components exist; single-row value otherwise. */
  function combinedMean(rows, sumF, nF, meanF, what) {
    if (rows.length === 0) return unavailable('no rows in the selection');
    var hasComp = rows.every(function (r) { return r[nF] !== undefined; });
    if (hasComp) {
      var s = 0, n = 0;
      rows.forEach(function (r) { if (r[nF]) { s += r[sumF] || 0; n += r[nF]; } });
      return n === 0 ? unavailable('no valid values in the selection') :
        ok(s / n, { num: s, den: n, basis: 'sum ÷ valid-value count' });
    }
    if (rows.length === 1) {
      var v = rows[0][meanF];
      return v === null || v === undefined ? unavailable('no value in this cell') :
        ok(v, { basis: 'single-cell value as exported (original grain)' });
    }
    return unavailable(what + ' cannot be combined across ' + rows.length +
      ' cells: this extract stores only the per-cell mean, not its valid-value count. ' +
      'A mean of means, or a mean weighted by a count it was not divided by, would be unproven.');
  }
  function singleCellOnly(rows, f, what) {
    if (rows.length === 1) return ok(rows[0][f], { basis: 'single cell' });
    var s = 0;
    rows.forEach(function (r) { s += r[f] || 0; });
    return unavailable(what + ' are distinct within each cell and cannot be added across cells.',
      { alt: s });
  }

  // ------------------------------------------------------------------ overview
  function overview(src, sel) {
    var mr = monthRange(src.months, sel.from, sel.to);
    if (!mr.ok) return { error: mr.error };
    var rows = inMonths(src.monthly, mr.months);
    if (rows.length === 0) return { empty: true, months: mr.months };
    var S = function (f, st) { return sumField(rows, f, st); };
    var orders = S('orders'), owi = S('orders_with_items'), gmv = S('gmv_c');
    var out = {
      months: mr.months, rows: rows,
      orders: orders, orders_with_items: owi, gmv: gmv, goods: S('goods_c'),
      freight: S('freight_c'), payments: S('payment_c'),
      canceled: S('canceled'), delivered: S('delivered'), late: S('late'),
      reviewed: S('reviewed'), low: S('low_score', 'low_score_status'),
    };
    out.aov = owi.value ? ok(centsPer(gmv.value, owi.value), { num: gmv.value, den: owi.value }) :
      unavailable('no orders with items in the selection');
    out.cancel_rate = rate(out.canceled, orders);
    out.late_rate = rate(out.late, out.delivered);
    out.low_rate = rate(out.low, out.reviewed);
    out.freight_share = rate(out.freight, gmv);
    // naive counterexample: unweighted mean of monthly late rates
    var monthly = rows.filter(function (r) { return r.delivered > 0; })
      .map(function (r) { return 100 * r.late / r.delivered; });
    out.naive_late_mean = monthly.length ? ok(monthly.reduce(function (a, b) { return a + b; }, 0) / monthly.length,
      { months: monthly.length }) : unavailable('no delivered orders');
    out.delivery_days = combinedMean(rows, 'delivery_days_sum', 'delivery_days_n', 'avg_delivery_days', 'Average delivery days');
    out.review_score = combinedMean(rows, 'review_score_sum', 'review_score_n', 'avg_review_score', 'Average review score');
    out.items_per_order = combinedMean(rows, 'items_sold', 'items_n', 'avg_items_per_order', 'Items per order');
    out.installments = combinedMean(rows, 'installments_sum', 'installments_n', 'avg_installments', 'Average installments');
    out.active_customers = singleCellOnly(rows, 'active_customers', 'Active customers');
    out.series = rows.map(function (r) {
      return {
        month: r.month, orders: r.orders, gmv_c: r.gmv_c,
        late_rate: r.delivered ? 100 * r.late / r.delivered : null,
        low_rate: r.low_score_status === 'unavailable' || !r.reviewed ? null : 100 * r.low_score / r.reviewed,
        low_status: r.low_score_status, cancel_rate: 100 * r.canceled / r.orders,
        aov_c: r.orders_with_items ? centsPer(r.gmv_c, r.orders_with_items) : null,
        avg_delivery_days: r.avg_delivery_days, avg_review_score: r.avg_review_score,
        active_customers: r.active_customers,
      };
    });
    return out;
  }

  // ---------------------------------------------------------------- categories
  function categories(src, sel, opts) {
    var mr = monthRange(src.months, sel.from, sel.to);
    if (!mr.ok) return { error: mr.error };
    var rows = inMonths(src.category, mr.months);
    var groups = {};
    rows.forEach(function (r) { (groups[r.category] = groups[r.category] || []).push(r); });
    var total = sumField(rows, 'gmv_c');
    var all = Object.keys(groups).sort().map(function (k) {
      var g = groups[k];
      var lines = sumField(g, 'lines'), gmv = sumField(g, 'gmv_c'), fr = sumField(g, 'freight_c');
      return {
        category: k, cells: g.length, lines: lines.value, gmv_c: gmv.value, goods_c: sumField(g, 'goods_c').value,
        freight_c: fr.value,
        // an order sits in exactly one month, so for ONE category distinct orders add across months
        orders: sumField(g, 'orders').value,
        freight_share: rate(fr, gmv),
        avg_line_c: centsPer(gmv.value, lines.value),
        share_of_selected_gmv: rate(gmv, total),
        customers: singleCellOnly(g, 'customers', 'Customers'),
        sellers: singleCellOnly(g, 'sellers', 'Active sellers'),
        missing_category_lines: sumField(g, 'lines_missing_category').value,
        missing_translation_lines: sumField(g, 'lines_missing_translation').value,
      };
    });
    var q = (opts && opts.search ? opts.search : '').trim().toLowerCase();
    var matched = q ? all.filter(function (c) { return c.category.toLowerCase().indexOf(q) >= 0; }) : all;
    var key = (opts && opts.sort) || 'gmv';
    var sorter = {
      gmv: function (a, b) { return b.gmv_c - a.gmv_c || cmp(a.category, b.category); },
      freight_share: function (a, b) { return (b.freight_share.value || 0) - (a.freight_share.value || 0) || cmp(a.category, b.category); },
      lines: function (a, b) { return b.lines - a.lines || cmp(a.category, b.category); },
      name: function (a, b) { return cmp(a.category, b.category); },
    }[key];
    matched.sort(sorter);
    var n = opts && opts.top ? opts.top : matched.length;
    return {
      months: mr.months, total_gmv: total, total_lines: sumField(rows, 'lines'),
      category_order_pairs: sumField(rows, 'orders').value,
      all_count: all.length, matched_count: matched.length, shown: matched.slice(0, n),
      missing_category_lines: sumField(rows, 'lines_missing_category').value,
      missing_translation_lines: sumField(rows, 'lines_missing_translation').value,
      empty: rows.length === 0, no_match: rows.length > 0 && matched.length === 0,
    };
  }
  function cmp(a, b) { return a < b ? -1 : a > b ? 1 : 0; }

  // --------------------------------------------------------------------- states
  function states(src, sel, opts) {
    var mr = monthRange(src.months, sel.from, sel.to);
    if (!mr.ok) return { error: mr.error };
    var rows = inMonths(src.state, mr.months);
    var chosen = opts && opts.states ? opts.states : null;
    if (chosen) rows = rows.filter(function (r) { return chosen.indexOf(r.state) >= 0; });
    var groups = {};
    rows.forEach(function (r) { (groups[r.state] = groups[r.state] || []).push(r); });
    var hasLate = src.components && src.components.state;
    function block(g) {
      var gmv = sumField(g, 'gmv_c'), owi = sumField(g, 'orders_with_items', 'owi_status');
      var fr = sumField(g, 'freight_c');
      var aov;
      if (owi.status === 'unavailable') aov = unavailable(owi.reason);
      else if (!owi.value) aov = unavailable('no orders with items');
      else aov = Object.assign(ok(centsPer(gmv.value, owi.value), { num: gmv.value, den: owi.value }),
        owi.status === 'inferred' ? { status: 'inferred' } : {});
      var late;
      if (hasLate) late = rate(sumField(g, 'late_orders'), sumField(g, 'delivered_orders'));
      else if (g.length === 1) late = g[0].late_rate_pct === null ? unavailable('no delivered orders') :
        ok(g[0].late_rate_pct, { basis: 'single-cell value as exported' });
      else late = unavailable('Late-delivery rate cannot be combined across ' + g.length +
        ' state-months: this extract has no delivered/late counts at state grain, and averaging the ' +
        'per-cell percentages would weight a 10-order month like a 5,000-order month.');
      return {
        cells: g.length, orders: sumField(g, 'orders').value, gmv_c: gmv.value, freight_c: fr.value,
        orders_with_items: owi, aov: aov, freight_share: rate(fr, gmv), late_rate: late,
        delivery_days: combinedMean(g, 'delivery_days_sum', 'delivery_days_n', 'avg_delivery_days', 'Average delivery days'),
        customers: singleCellOnly(g, 'customers', 'Customers'),
      };
    }
    var list = Object.keys(groups).sort().map(function (k) {
      return Object.assign({ state: k }, block(groups[k]));
    });
    list.sort(function (a, b) { return (b.gmv_c || 0) - (a.gmv_c || 0) || cmp(a.state, b.state); });
    return { months: mr.months, list: list, total: rows.length ? block(rows) : null, empty: rows.length === 0 };
  }

  // ------------------------------------------------------------------- payments
  function payments(src, sel, opts) {
    var mr = monthRange(src.months, sel.from, sel.to);
    if (!mr.ok) return { error: mr.error };
    var inRange = inMonths(src.payment, mr.months);
    var allOrders = sumField(inRange, 'orders');     // denominator: orders WITH a primary type
    var chosen = opts && opts.types ? opts.types : null;
    var rows = chosen ? inRange.filter(function (r) { return chosen.indexOf(r.ptype) >= 0; }) : inRange;
    var groups = {};
    rows.forEach(function (r) { (groups[r.ptype] = groups[r.ptype] || []).push(r); });
    var list = Object.keys(groups).sort().map(function (k) {
      var g = groups[k];
      var orders = sumField(g, 'orders'), gmv = sumField(g, 'gmv_c');
      var owi = sumField(g, 'orders_with_items', 'owi_status');
      var aov;
      if (owi.status === 'unavailable') aov = unavailable(owi.reason);
      else if (!owi.value) aov = unavailable('no orders with items (GMV is NULL)');
      else aov = Object.assign(ok(centsPer(gmv.value, owi.value), { num: gmv.value, den: owi.value }),
        owi.status === 'inferred' ? { status: 'inferred' } : {});
      return {
        ptype: k, cells: g.length, orders: orders.value, share_of_orders: rate(orders, allOrders),
        payments_c: sumField(g, 'payment_c').value, gmv_c: gmv.value, gmv_null_cells: gmv.nulls,
        orders_with_items: owi, aov: aov,
        installment_rate: rate(sumField(g, 'installment_orders'), orders),
        installments: combinedMean(g, 'installments_sum', 'installments_n', 'avg_installments', 'Average installments'),
      };
    });
    list.sort(function (a, b) { return b.orders - a.orders || cmp(a.ptype, b.ptype); });
    return { months: mr.months, list: list, all_orders: allOrders, empty: rows.length === 0 };
  }

  // -------------------------------------------------------------- lead ranking
  /**
   * scores must be sorted DESC with ties already ordered by lead id (done at build).
   * Returns deterministic hits (first k rows), the tie-aware expected hits (average over
   * every ordering of the tied block at the cut-off) and the min/max any tie-break allows.
   */
  function topK(scores, labels, k) {
    var n = scores.length;
    if (!n) return null;
    k = Math.max(1, Math.min(Math.floor(k), n));
    var cut = scores[k - 1];
    var above = 0, posAbove = 0, block = 0, posBlock = 0, det = 0;
    for (var i = 0; i < n; i++) {
      if (i < k) det += labels[i];
      if (scores[i] > cut) { above++; posAbove += labels[i]; }
      else if (scores[i] === cut) { block++; posBlock += labels[i]; }
    }
    var slots = k - above;
    var positives = 0;
    for (var j = 0; j < n; j++) positives += labels[j];
    return {
      k: k, n: n, positives: positives, prevalence: positives / n,
      deterministic: det, expected: posAbove + posBlock * slots / block,
      min: posAbove + Math.max(0, slots - (block - posBlock)), max: posAbove + Math.min(posBlock, slots),
      tie_block: block, random_expected: k * positives / n,
    };
  }
  /** Cumulative gains at each decile boundary, tie-aware. */
  function gains(scores, labels, steps) {
    var out = [{ share: 0, captured: 0 }];
    var n = scores.length, positives = 0;
    for (var i = 0; i < n; i++) positives += labels[i];
    for (var s = 1; s <= steps; s++) {
      var t = topK(scores, labels, Math.max(1, Math.floor(n * s / steps)));
      out.push({ share: s / steps, captured: positives ? t.expected / positives : 0, k: t.k, expected: t.expected });
    }
    return out;
  }

  // --------------------------------------------------------------- economics
  /** HYPOTHETICAL break-even. cost is per 1,000 users on the chosen basis; value per
   *  incremental conversion. ITT difference and CI are proportions (not pp). */
  function breakeven(ittDiff, ittCi, compliance, input) {
    var cost = Number(input.cost), value = Number(input.value);
    var errors = [];
    if (input.cost === '' || !isFinite(cost) || cost < 0) errors.push('Cost must be a number ≥ 0.');
    if (input.value === '' || !isFinite(value) || value < 0) errors.push('Value per conversion must be a number ≥ 0.');
    if (errors.length) return { error: errors.join(' ') };
    // cost basis: per 1,000 ASSIGNED users, or per 1,000 EXPOSED users (paid impressions)
    var costPerAssigned = input.basis === 'exposed' ? cost * compliance : cost;
    var inc = 1000 * ittDiff, lo = 1000 * ittCi[0], hi = 1000 * ittCi[1];
    function be(d) { return d > 0 ? costPerAssigned / d : null; }
    return {
      cost_per_1000_assigned: costPerAssigned,
      incremental_per_1000: inc, incremental_ci: [lo, hi],
      net_per_1000: inc * value - costPerAssigned,
      net_ci: [lo * value - costPerAssigned, hi * value - costPerAssigned],
      breakeven_value: be(inc), breakeven_range: [be(hi), be(lo)],
    };
  }

  return {
    fmtInt: fmtInt, fmtCents: fmtCents, fmtCentsCompact: fmtCentsCompact, fmtFixed: fmtFixed,
    fmtPct: fmtPct, centsPer: centsPer, sumField: sumField, rate: rate, monthRange: monthRange,
    combinedMean: combinedMean, overview: overview, categories: categories, states: states,
    payments: payments, topK: topK, gains: gains, breakeven: breakeven, niceScale: niceScale,
    labelIndices: labelIndices,
  };
})();
if (typeof module !== 'undefined' && module.exports) module.exports = Engine;
