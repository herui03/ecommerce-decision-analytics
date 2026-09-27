// node --test tests/js/engine.test.mjs  -- unit tests for dashboard/src/engine.js
import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const E = require('../../dashboard/src/engine.js');

test('money is formatted from integer cents without float drift', () => {
  assert.equal(E.fmtCents(1578620357), 'BRL 15,786,203.57');
  assert.equal(E.fmtCents(5), 'BRL 0.05');
  assert.equal(E.fmtCents(-1999), 'BRL -19.99');
  assert.throws(() => E.fmtCents(0.1 + 0.2));
  // 0.1 + 0.2 style drift cannot occur: sums stay integers
  const rows = [{ c: 10 }, { c: 20 }];
  assert.equal(E.sumField(rows, 'c').value, 30);
});

test('weighted rate differs from the mean of rates (the counterexample)', () => {
  const src = { months: ['a', 'b'], monthly: [
    { month: 'a', orders: 100, orders_with_items: 100, gmv_c: 100, goods_c: 90, freight_c: 10, payment_c: 100, canceled: 0, delivered: 100, late: 50, reviewed: 100, low_score: 0, low_score_status: 'observed', active_customers: 100 },
    { month: 'b', orders: 900, orders_with_items: 900, gmv_c: 900, goods_c: 810, freight_c: 90, payment_c: 900, canceled: 0, delivered: 900, late: 0, reviewed: 900, low_score: 0, low_score_status: 'observed', active_customers: 900 }] };
  const r = E.overview(src, { from: 'a', to: 'b' });
  assert.equal(r.late_rate.value, 5);            // 50 / 1000
  assert.equal(r.naive_late_mean.value, 25);     // (50% + 0%) / 2
  assert.equal(r.active_customers.status, 'unavailable');
  assert.equal(r.active_customers.alt, 1000);
});

test('an unidentified cell makes the aggregate unavailable instead of being dropped', () => {
  const rows = [{ v: 5, s: 'inferred' }, { v: null, s: 'unavailable' }];
  const r = E.sumField(rows, 'v', 's');
  assert.equal(r.status, 'unavailable');
  assert.equal(r.value, null);
  assert.equal(E.rate(r, { status: 'ok', value: 10 }).status, 'unavailable');
  const ok = E.sumField([{ v: 5, s: 'inferred' }, { v: 7, s: 'observed' }], 'v', 's');
  assert.deepEqual([ok.status, ok.value], ['inferred', 12]);
});

test('all-NULL money is NULL, not zero', () => {
  const r = E.sumField([{ g: null }, { g: null }], 'g');
  assert.equal(r.value, null);
  assert.equal(E.rate(r, { status: 'ok', value: 3 }).status, 'unavailable');
});

test('means combine only with valid-value counts', () => {
  const noComp = [{ m: 2 }, { m: 4 }];
  assert.equal(E.combinedMean(noComp, 's', 'n', 'm', 'x').status, 'unavailable');
  assert.equal(E.combinedMean([{ m: 2 }], 's', 'n', 'm', 'x').value, 2);
  const comp = [{ s: 10, n: 5, m: 2 }, { s: 40, n: 10, m: 4 }];
  assert.equal(E.combinedMean(comp, 's', 'n', 'm', 'x').value, 50 / 15);  // not (2 + 4) / 2
});

test('month range: reversed and unknown months are invalid', () => {
  const ms = ['2017-01', '2017-02', '2017-03'];
  assert.equal(E.monthRange(ms, '2017-03', '2017-01').ok, false);
  assert.equal(E.monthRange(ms, '2016-12', '2017-01').ok, false);
  assert.deepEqual(E.monthRange(ms, '2017-02', '2017-03').months, ['2017-02', '2017-03']);
});

test('top-k is tie-aware and independent of order inside a tied block', () => {
  // sorted desc; ties at 0.5 hold 2 positives out of 4
  const s = [0.9, 0.8, 0.5, 0.5, 0.5, 0.5, 0.1];
  const y = [1, 0, 1, 0, 1, 0, 0];
  const t = E.topK(s, y, 3);            // 2 above the cut + 1 slot in a block of 4 with 2 positives
  assert.equal(t.expected, 1 + 2 * 1 / 4);
  assert.deepEqual([t.min, t.max, t.tie_block], [1, 2, 4]);
  const y2 = [1, 0, 0, 1, 0, 1, 0];     // same block, positives in another order
  assert.equal(E.topK(s, y2, 3).expected, t.expected);
  const c = E.topK([0.3, 0.3, 0.3, 0.3], [1, 1, 0, 0], 2);   // constant score
  assert.equal(c.expected, 1);
  assert.equal(c.expected, c.random_expected);
});

test('axis scale and label spacing', () => {
  const sc = E.niceScale(0, 22.9, 4);
  assert.deepEqual(sc.ticks, [0, 5, 10, 15, 20, 25]);
  assert.deepEqual(E.niceScale(0, 117914400, 4).ticks, [0, 25e6, 50e6, 75e6, 100e6, 125e6]);
  assert.deepEqual([E.fmtCentsCompact(125e6), E.fmtCentsCompact(25e6), E.fmtCentsCompact(1e8)], ['1.25M', '250K', '1M']);
  const iv = E.niceScale(-0.01, 0.132, 5);
  assert.ok(iv.min <= -0.01 && iv.max >= 0.132 && iv.ticks.includes(0));
  assert.deepEqual(E.labelIndices(20, 3), [0, 3, 6, 9, 12, 15, 19]);
  assert.deepEqual(E.labelIndices(20, 2), [0, 2, 4, 6, 8, 10, 12, 14, 16, 19]);
});

test('break-even: invalid input is an error, arithmetic uses the ITT only', () => {
  assert.ok(E.breakeven(0.001, [0.0009, 0.0011], 0.03, { basis: 'assigned', cost: 'abc', value: '5' }).error);
  assert.ok(E.breakeven(0.001, [0.0009, 0.0011], 0.03, { basis: 'assigned', cost: '-1', value: '5' }).error);
  const r = E.breakeven(0.001, [0.0009, 0.0011], 0.03, { basis: 'assigned', cost: '2', value: '5' });
  assert.equal(r.incremental_per_1000, 1);
  assert.equal(r.net_per_1000, 1 * 5 - 2);
  assert.equal(r.breakeven_value, 2);
  const e = E.breakeven(0.001, [0.0009, 0.0011], 0.03, { basis: 'exposed', cost: '100', value: '5' });
  assert.equal(e.cost_per_1000_assigned, 3);      // 100 per 1,000 exposed x 3% exposure
});
