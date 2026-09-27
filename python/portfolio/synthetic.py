"""Deterministic SYNTHETIC sample data - NOT real Olist or Criteo data.

Why this exists
    The real inputs (Kaggle Olist CSVs, Criteo Uplift v2.1) are licensed third-party
    data that are not committed and need a download. A recruiter or reviewer must be
    able to run the whole pipeline from a clean clone with no credentials, so this
    module writes files with the SAME file names and columns as the real sources, filled
    with generated values, and the unchanged dbt project builds on them.

What it is not
    Nothing here is an estimate of the real business. IDs are prefixed "SYN-", customer
    states are fictional codes "XA".."XH", categories are "synthetic_cat_*". Any number
    computed from this sample demonstrates the MECHANICS (grain, denominators, windows,
    leakage controls, estimator behaviour) and must be labelled SYNTHETIC.

Edge cases planted on purpose (each one is exercised by a test)
    * orders with no items (unavailable / canceled) -> NULL basket, never zero-filled
    * one in-window and one pilot-period delivered order with NO payment row
    * split payments, a 50/50 two-instrument tie (primary-type tie-break), not_defined
      payments of 0.00 on item-less orders in the last window month
    * multi-item, multi-seller and multi-category orders (category grain != order grain)
    * repeat customers: one person (customer_unique_id) across several customer_ids
    * reviews: unreviewed orders, orders with two reviews, a review_id shared by 2 orders
    * delivery on the estimated calendar day at 23:59 (on time) and at 00:01 the next
      day (late); delivered-status orders with no delivery timestamp; cancelled orders
      that nevertheless carry a (late) delivery timestamp
    * products with NULL category and a category missing from the translation table
    * pilot months with a gap (2016-11 has zero orders) and a thin 2018-09/10 tail whose
      2018-10 orders are all canceled with no items (NULL GMV)
    * zip prefixes with no geolocation rows
    * leads: a win exactly on day 90 (positive), day 91 (negative), day 0 (positive) and
      day -2 (negative); NULL origin channel; pages with a single lead; pages whose
      traffic grows with their quality, so a full-dataset page count leaks the future
    * Criteo-shaped RCT: 85/15 assignment, exposure only in the treated arm and
      correlated with a covariate that also drives conversion (the exposure trap), with
      the true ITT and CACE known by construction.

Determinism
    One numpy Generator(PCG64) per table family, seeded from SEED; fixed formatting;
    rows written in a fixed order. Two runs produce byte-identical files (asserted in
    tests/test_synthetic.py via SHA-256).
"""
from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np

SEED = 20260926

STATES = ["XA", "XB", "XC", "XD", "XE", "XF", "XG", "XH"]
STATE_WEIGHT = np.array([0.34, 0.16, 0.13, 0.10, 0.09, 0.07, 0.06, 0.05])
# (typical delivery days, estimate days) - remote regions are slower and further off.
STATE_DELIVERY = {"XA": (8, 20), "XB": (11, 23), "XC": (12, 24), "XD": (14, 25),
                  "XE": (16, 27), "XF": (18, 28), "XG": (20, 30), "XH": (23, 33)}
# Freight multiplier by destination - drives a visible freight-share spread.
STATE_FREIGHT = {"XA": 0.8, "XB": 1.0, "XC": 1.05, "XD": 1.15, "XE": 1.3, "XF": 1.4,
                 "XG": 1.6, "XH": 1.8}

# (pt name, en name or None when untranslated, price median BRL, weight kg, popularity)
CATEGORIES = [
    ("sintetica_a", "synthetic_cat_a", 95.0, 1.2, 0.17),
    ("sintetica_b", "synthetic_cat_b", 140.0, 0.4, 0.13),
    ("sintetica_c", "synthetic_cat_c", 60.0, 0.3, 0.12),
    ("sintetica_d", "synthetic_cat_d", 230.0, 8.0, 0.10),
    ("sintetica_e", "synthetic_cat_e", 45.0, 0.2, 0.09),
    ("sintetica_f", "synthetic_cat_f", 310.0, 3.5, 0.08),
    ("sintetica_g", "synthetic_cat_g", 75.0, 2.0, 0.08),
    ("sintetica_h", "synthetic_cat_h", 180.0, 12.0, 0.07),
    ("sintetica_i", "synthetic_cat_i", 55.0, 0.6, 0.06),
    ("sintetica_j", "synthetic_cat_j", 120.0, 1.0, 0.05),
    ("sintetica_sem_traducao", None, 90.0, 1.5, 0.03),   # absent from the lookup
    (None, None, 70.0, 1.0, 0.02),                        # NULL category
]

# In-window monthly order volume (2017-01 .. 2018-08) plus pilot/tail months.
MONTH_VOLUME = {
    "2016-09": 3, "2016-10": 40, "2016-12": 1,              # pilot; 2016-11 absent
    "2017-01": 110, "2017-02": 230, "2017-03": 340, "2017-04": 310, "2017-05": 460,
    "2017-06": 410, "2017-07": 500, "2017-08": 540, "2017-09": 530, "2017-10": 580,
    "2017-11": 940, "2017-12": 700, "2018-01": 900, "2018-02": 840, "2018-03": 900,
    "2018-04": 870, "2018-05": 860, "2018-06": 770, "2018-07": 790, "2018-08": 810,
    "2018-09": 6, "2018-10": 3,                               # export tail
}
SLOW_MONTHS = {"2017-11": 1.45, "2018-02": 1.35, "2018-03": 1.55}   # delivery strain

ORIGINS = ["organic_search", "paid_search", "social", "direct_traffic", "email",
           "referral", "display", "other", "unknown", "other_publicities"]
ORIGIN_EFFECT = {"organic_search": 0.1, "paid_search": 0.2, "social": -0.6,
                 "direct_traffic": 0.05, "email": -1.0, "referral": -0.3, "display": -0.7,
                 "other": -1.1, "unknown": 0.4, "other_publicities": -0.8, None: 0.7}


def _money(cents: int) -> str:
    """Integer cents -> 'R.CC' string. Money is generated as integers, never floats."""
    sign = "-" if cents < 0 else ""
    cents = abs(int(cents))
    return f"{sign}{cents // 100}.{cents % 100:02d}"


def _ts(dt: datetime | None) -> str:
    return "" if dt is None else dt.strftime("%Y-%m-%d %H:%M:%S")


def _write(path: Path, header: list[str], rows: list[list]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(header)
        for r in rows:
            w.writerow(["" if v is None else v for v in r])


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _month_start(label: str) -> datetime:
    y, m = map(int, label.split("-"))
    return datetime(y, m, 1)


def _next_month(dt: datetime) -> datetime:
    return datetime(dt.year + (dt.month == 12), dt.month % 12 + 1, 1)


# --------------------------------------------------------------------------- Olist
@dataclass
class OlistSample:
    files: dict[str, int]          # file name -> data rows


def generate_olist(raw_dir: Path, seed: int = SEED) -> OlistSample:
    rng = np.random.default_rng(np.random.PCG64(seed))
    raw_dir.mkdir(parents=True, exist_ok=True)

    # ---- geography: 20 zips per state, a few never geocoded -------------------------
    zips: dict[str, list[int]] = {}
    geo_rows = []
    not_geocoded = set()
    for si, st in enumerate(STATES):
        zips[st] = [91000 + si * 100 + k for k in range(20)]
        base_lat, base_lng = -10.0 - 2.2 * si, -40.0 - 1.7 * si
        for k, z in enumerate(zips[st]):
            if k == 19 and si < 3:            # 3 zips with no geolocation at all
                not_geocoded.add(z)
                continue
            n_pts = 1 + int(rng.integers(0, 6))
            for p in range(n_pts):
                city = f"syn_city_{st.lower()}_{k // 5:02d}"
                if p == n_pts - 1 and n_pts >= 4:   # a minority label -> modal city wins
                    city = f"syn_city_{st.lower()}_alt"
                geo_rows.append([z, f"{base_lat + rng.normal(0, 0.3):.6f}",
                                 f"{base_lng + rng.normal(0, 0.3):.6f}", city, st.lower()])
    _write(raw_dir / "olist_geolocation_dataset.csv",
           ["geolocation_zip_code_prefix", "geolocation_lat", "geolocation_lng",
            "geolocation_city", "geolocation_state"], geo_rows)

    # ---- categories and products -----------------------------------------------------
    _write(raw_dir / "product_category_name_translation.csv",
           ["product_category_name", "product_category_name_english"],
           [[pt, en] for pt, en, *_ in CATEGORIES if pt is not None and en is not None])
    products = []           # (product_id, category index)
    prod_rows = []
    pop = np.array([c[4] for c in CATEGORIES])
    pop = pop / pop.sum()
    for p in range(400):
        ci = int(rng.choice(len(CATEGORIES), p=pop))
        pt, en, price, kg, _ = CATEGORIES[ci]
        pid = f"SYN-PRD-{p:04d}"
        products.append((pid, ci))
        w = max(50, int(kg * 1000 * rng.lognormal(0, 0.3)))
        prod_rows.append([pid, pt, int(rng.integers(20, 60)), int(rng.integers(100, 2000)),
                          int(rng.integers(1, 6)), w, int(rng.integers(10, 80)),
                          int(rng.integers(2, 60)), int(rng.integers(10, 60))])
    _write(raw_dir / "olist_products_dataset.csv",
           ["product_id", "product_category_name", "product_name_lenght",
            "product_description_lenght", "product_photos_qty", "product_weight_g",
            "product_length_cm", "product_height_cm", "product_width_cm"], prod_rows)
    prod_by_cat: dict[int, list[str]] = {}
    for pid, ci in products:
        prod_by_cat.setdefault(ci, []).append(pid)
    cat_ids = sorted(prod_by_cat)
    cat_pop = np.array([CATEGORIES[c][4] for c in cat_ids])
    cat_pop = cat_pop / cat_pop.sum()

    # ---- sellers --------------------------------------------------------------------------
    sellers = [f"SYN-SEL-{s:03d}" for s in range(60)]
    seller_rows = []
    for s, sid in enumerate(sellers):
        st = STATES[s % 3]                       # sellers concentrated in 3 regions
        seller_rows.append([sid, zips[st][s % 20], f"syn_city_{st.lower()}_{(s % 20) // 5:02d}", st])
    _write(raw_dir / "olist_sellers_dataset.csv",
           ["seller_id", "seller_zip_code_prefix", "seller_city", "seller_state"], seller_rows)

    # ---- orders and children ---------------------------------------------------------------
    orders, items, payments, reviews, customers = [], [], [], [], []
    persons: list[tuple[str, str, int]] = []          # (unique id, state, zip)
    order_seq = review_seq = 0
    shared_review_id = None
    tie_planted = False
    boundary_planted = 0

    for label, n in MONTH_VOLUME.items():
        m0 = _month_start(label)
        span = (_next_month(m0) - m0).total_seconds()
        offsets = np.sort(rng.random(n) * span)
        for j in range(n):
            order_seq += 1
            oid = f"SYN-ORD-{order_seq:06d}"
            cid = f"SYN-CUS-{order_seq:06d}"         # one customer_id per ORDER (as Olist)
            purchased = m0 + timedelta(seconds=int(offsets[j]))
            # person: ~5% of orders come from an existing person
            if persons and rng.random() < 0.05:
                uid, st, z = persons[int(rng.integers(0, len(persons)))]
                if rng.random() < 0.2:               # moved house between orders
                    z = zips[st][int(rng.integers(0, 20))]
            else:
                st = STATES[int(rng.choice(len(STATES), p=STATE_WEIGHT))]
                z = zips[st][int(rng.integers(0, 20))]
                uid = f"SYN-PER-{len(persons) + 1:06d}"
                persons.append((uid, st, z))
            customers.append([cid, uid, z, f"syn_city_{st.lower()}_{(z % 100) // 5:02d}", st])

            # status
            u = rng.random()
            skip_payment = (label == "2016-10" and j == 5) or (label == "2017-06" and j == 17)
            if skip_payment:
                status = "delivered"                       # delivered but no payment record
            elif label == "2018-10":
                status = "canceled"
            elif u < 0.955:
                status = "delivered"
            elif u < 0.967:
                status = "shipped"
            elif u < 0.976:
                status = "canceled"
            elif u < 0.985:
                status = "unavailable"
            elif u < 0.990:
                status = "invoiced"
            elif u < 0.995:
                status = "processing"
            elif u < 0.998:
                status = "approved"
            else:
                status = "created"
            no_items = (status == "unavailable") or (status == "canceled" and rng.random() < 0.7) \
                or (status == "created" and rng.random() < 0.5) or label == "2018-10"

            # items
            basket_cents = 0
            if not no_items:
                k = 1 if rng.random() < 0.86 else (2 if rng.random() < 0.75 else int(rng.integers(3, 6)))
                ci = cat_ids[int(rng.choice(len(cat_ids), p=cat_pop))]
                for seq in range(1, k + 1):
                    if seq > 1 and rng.random() < 0.35:        # second category in basket
                        ci = cat_ids[int(rng.choice(len(cat_ids), p=cat_pop))]
                    pid = prod_by_cat[ci][int(rng.integers(0, len(prod_by_cat[ci])))]
                    price_med, kg = CATEGORIES[ci][2], CATEGORIES[ci][3]
                    price = int(round(price_med * rng.lognormal(0, 0.45) * 100))
                    freight = int(round((900 + 380 * kg ** 0.8) * STATE_FREIGHT[st]
                                        * rng.lognormal(0, 0.2)))
                    seller = sellers[int(rng.integers(0, len(sellers)))]
                    items.append([oid, seq, pid, seller, _ts(purchased + timedelta(days=6)),
                                  _money(price), _money(freight)])
                    basket_cents += price + freight

            # payments
            pay_total = basket_cents if basket_cents else int(round(rng.lognormal(4.6, 0.5) * 100))
            if skip_payment:
                pass                                       # no payment row at all
            elif label == "2018-08" and no_items and status == "canceled":
                payments.append([oid, 1, "not_defined", 1, _money(0)])
            elif not tie_planted and label == "2017-05" and not no_items and basket_cents % 2 == 0:
                half = basket_cents // 2                   # exact 50/50 split -> tie-break
                payments.append([oid, 1, "voucher", 1, _money(half)])
                payments.append([oid, 2, "credit_card", 1, _money(basket_cents - half)])
                tie_planted = True
            else:
                v = rng.random()
                if v < 0.72:
                    inst = int(rng.choice([1, 1, 2, 3, 4, 5, 6, 8, 10]))
                    if rng.random() < 0.06 and pay_total > 2000:       # split with a voucher
                        vouch = int(pay_total * rng.uniform(0.1, 0.4))
                        payments.append([oid, 1, "credit_card", inst, _money(pay_total - vouch)])
                        payments.append([oid, 2, "voucher", 1, _money(vouch)])
                    else:
                        extra = int(pay_total * 0.02) if (inst > 6 and rng.random() < 0.3) else 0
                        payments.append([oid, 1, "credit_card", inst, _money(pay_total + extra)])
                elif v < 0.92:
                    payments.append([oid, 1, "boleto", 1, _money(pay_total)])
                elif v < 0.97:
                    payments.append([oid, 1, "voucher", 1, _money(pay_total)])
                else:
                    payments.append([oid, 1, "debit_card", 1, _money(pay_total)])

            # delivery
            typ, est = STATE_DELIVERY[st]
            estimated = datetime.combine((purchased + timedelta(days=est)).date(), datetime.min.time())
            approved = purchased + timedelta(minutes=int(rng.integers(5, 2000)))
            carrier = delivered = None
            if status in ("delivered", "shipped") or (status == "canceled" and rng.random() < 0.05):
                carrier = approved + timedelta(days=float(rng.uniform(0.5, 4)))
            if status == "delivered":
                days = typ * SLOW_MONTHS.get(label, 1.0) * rng.lognormal(0, 0.35)
                delivered = purchased + timedelta(days=float(days))
                if boundary_planted < 2 and label == "2018-04":
                    # on the estimated calendar day at 23:59 -> ON TIME;
                    # at 00:01 the following day -> LATE by exactly one calendar day
                    delivered = estimated + (timedelta(hours=23, minutes=59) if boundary_planted == 0
                                             else timedelta(days=1, minutes=1))
                    boundary_planted += 1
                elif rng.random() < 0.0015:
                    delivered = None                       # delivered status, no timestamp
            elif status == "canceled" and not no_items and rng.random() < 0.3:
                # cancelled AFTER a (late) delivery timestamp - present in the real data; a late
                # flag that forgot the delivered-status condition would count these
                delivered = estimated + timedelta(days=int(rng.integers(1, 5)), hours=3)
            orders.append([oid, cid, status, _ts(purchased), _ts(approved), _ts(carrier),
                           _ts(delivered), _ts(estimated)])

            # reviews
            if rng.random() < 0.985:
                late = delivered is not None and delivered.date() > estimated.date()
                p_low = 0.45 if late else (0.25 if status != "delivered" else 0.08)
                n_rev = 2 if rng.random() < 0.006 else 1
                for r in range(n_rev):
                    review_seq += 1
                    rid = f"SYN-REV-{review_seq:06d}"
                    if shared_review_id is None and label == "2017-08":
                        shared_review_id = rid
                    elif shared_review_id and label == "2017-09" and r == 0 and review_seq % 97 == 0:
                        rid = shared_review_id             # same review_id on a 2nd order
                    score = int(rng.choice([1, 2])) if rng.random() < p_low else int(rng.choice([3, 4, 5, 5, 5]))
                    created = (delivered or estimated) + timedelta(days=1 + r)
                    answered = created + timedelta(hours=int(rng.integers(2, 72)))
                    reviews.append([rid, oid, score, "", "", _ts(created), _ts(answered)])

    _write(raw_dir / "olist_customers_dataset.csv",
           ["customer_id", "customer_unique_id", "customer_zip_code_prefix", "customer_city",
            "customer_state"], customers)
    _write(raw_dir / "olist_orders_dataset.csv",
           ["order_id", "customer_id", "order_status", "order_purchase_timestamp",
            "order_approved_at", "order_delivered_carrier_date", "order_delivered_customer_date",
            "order_estimated_delivery_date"], orders)
    _write(raw_dir / "olist_order_items_dataset.csv",
           ["order_id", "order_item_id", "product_id", "seller_id", "shipping_limit_date",
            "price", "freight_value"], items)
    _write(raw_dir / "olist_order_payments_dataset.csv",
           ["order_id", "payment_sequential", "payment_type", "payment_installments",
            "payment_value"], payments)
    _write(raw_dir / "olist_order_reviews_dataset.csv",
           ["review_id", "order_id", "review_score", "review_comment_title",
            "review_comment_message", "review_creation_date", "review_answer_timestamp"], reviews)

    leads, deals = _generate_leads(np.random.default_rng(np.random.PCG64(seed + 1)), sellers)
    _write(raw_dir / "olist_marketing_qualified_leads_dataset.csv",
           ["mql_id", "first_contact_date", "landing_page_id", "origin"], leads)
    _write(raw_dir / "olist_closed_deals_dataset.csv",
           ["mql_id", "seller_id", "sdr_id", "sr_id", "won_date", "business_segment",
            "lead_type", "lead_behaviour_profile", "has_company", "has_gtin", "average_stock",
            "business_type", "declared_product_catalog_size", "declared_monthly_revenue"], deals)

    counts = {}
    for f in sorted(raw_dir.glob("*.csv")):
        with open(f, encoding="utf-8") as fh:
            counts[f.name] = sum(1 for _ in fh) - 1
    return OlistSample(files=counts)


def _generate_leads(rng: np.random.Generator, sellers: list[str]):
    """B2B seller-acquisition leads, 2017-07-01 .. 2018-05-31.

    Page quality drives BOTH conversion and later traffic growth, so a page's
    full-dataset lead count reveals its future popularity - exactly the look-ahead that
    the legacy page_lead_volume feature carries and page_lead_volume_prior does not.
    Leads before 2017-11 get no 90-day wins (the observed regime break is reproduced
    as a pattern; the synthetic data says nothing about its real-world cause).
    """
    n_pages = 90
    quality = rng.normal(0, 0.8, n_pages)
    offsets = np.sort(rng.integers(0, 300, n_pages))
    offsets[:10] = 0                     # ten pages live from day one
    launch = [date(2017, 7, 1) + timedelta(days=int(d)) for d in offsets]
    leads, deals = [], []
    start, end = date(2017, 7, 1), date(2018, 5, 31)
    seq = 0
    special = iter([90, 91, 0, -2])      # boundary wins planted in 2018-02
    d = start
    while d <= end:
        base = 6.0 if d < date(2018, 1, 1) else 26.0
        n_today = int(rng.poisson(base))
        live = [p for p in range(n_pages) if launch[p] <= d]
        age = np.array([(d - launch[p]).days for p in live], dtype=float)
        # traffic weight grows with quality x age: good pages become popular LATER
        w = np.exp(0.9 * quality[live] * np.minimum(age, 240) / 240)
        w = w / w.sum()
        for _ in range(n_today):
            seq += 1
            mid = f"SYN-MQL-{seq:05d}"
            p = live[int(rng.choice(len(live), p=w))]
            origin = None if rng.random() < 0.012 else ORIGINS[int(rng.integers(0, len(ORIGINS)))]
            leads.append([mid, d.isoformat(), f"SYN-LP-{p:03d}", origin])
            # conversion
            logit = -2.45 + ORIGIN_EFFECT[origin] + 0.55 * quality[p]
            p_win = 1 / (1 + np.exp(-logit))
            won_days = None
            forced = None
            if d.year == 2018 and d.month == 2 and d.day >= 10:
                forced = next(special, None)
            if forced is not None:
                won_days = forced
            elif d < date(2017, 11, 1):
                if rng.random() < 0.05:
                    won_days = int(rng.integers(150, 330))        # late wins only
            elif d < date(2018, 1, 1):
                if rng.random() < p_win * 0.25:
                    won_days = int(rng.integers(5, 200))
            elif rng.random() < p_win:
                won_days = int(min(89, rng.geometric(1 / 16)))     # within the horizon
            elif rng.random() < 0.02:
                won_days = int(rng.integers(92, 180))              # won, but after 90 days
            if won_days is not None:
                won = datetime.combine(d + timedelta(days=won_days), datetime.min.time()) \
                    + timedelta(hours=int(rng.integers(8, 19)), minutes=int(rng.integers(0, 60)))
                deals.append([mid, f"SYN-SLR-{len(deals) + 1:04d}", f"SYN-SDR-{int(rng.integers(0, 12)):02d}",
                              f"SYN-SR-{int(rng.integers(0, 10)):02d}", _ts(won),
                              f"segment_{int(rng.integers(0, 8))}", "online_medium", "cat", "", "",
                              "", "reseller", int(rng.integers(0, 500)), int(rng.integers(0, 200000))])
        d += timedelta(days=1)
    return leads, deals


# --------------------------------------------------------------------------- Criteo
CRITEO_N = 240_000
CRITEO_TREAT_SHARE = 0.85
CRITEO_COMPLIER_EFFECT = 0.040      # +4.0 pp conversion for compliers when exposed


def generate_criteo(path: Path, seed: int = SEED, n: int = CRITEO_N) -> dict:
    """Criteo-shaped RCT with known truth. f0..f11 are anonymous covariates - they are
    deliberately NOT given product/geography meaning, exactly as in the real dataset.

    Potential exposure D(1) ~ Bernoulli(q_i) with q_i rising steeply in f0 (active
    browsers see ads); D(0) = 0 (one-sided non-compliance). Baseline conversion p0_i also
    rises in f0, so exposed users convert more even without any ad effect. Treated
    conversion probability is p0_i + effect * D_i(1).

    Returns the truth: the sample-average ITT E[p1 - p0] and the complier effect.
    """
    rng = np.random.default_rng(np.random.PCG64(seed + 2))
    f = rng.normal(0, 1, (n, 12))
    treat = (rng.random(n) < CRITEO_TREAT_SHARE).astype(int)
    q = 1 / (1 + np.exp(-(-3.4 + 1.3 * f[:, 0])))            # P(D(1) = 1)
    d1 = (rng.random(n) < q).astype(int)
    p0 = 1 / (1 + np.exp(-(-5.6 + 0.9 * f[:, 0] + 0.2 * f[:, 3])))
    p1 = np.clip(p0 + CRITEO_COMPLIER_EFFECT * d1, 0, 1)
    exposure = treat * d1
    conv = (rng.random(n) < np.where(treat == 1, p1, p0)).astype(int)
    visit = np.maximum(conv, (rng.random(n) < 0.035 + 0.25 * exposure).astype(int))
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow([f"f{k}" for k in range(12)] + ["treatment", "conversion", "visit", "exposure"])
        for i in range(n):
            w.writerow([f"{v:.4f}" for v in f[i]] + [treat[i], conv[i], visit[i], exposure[i]])
    truth = {
        "rows": n,
        "treatment_share_target": CRITEO_TREAT_SHARE,
        # Sample-average treatment effect of ASSIGNMENT given each row's realised
        # compliance type: E[p1 - p0] = effect * mean(D(1)). This is the estimand the
        # ITT difference in means targets for this finite population.
        "true_itt_pp": float(100 * CRITEO_COMPLIER_EFFECT * d1.mean()),
        "true_cace_pp": float(100 * CRITEO_COMPLIER_EFFECT),
        "complier_share": float(d1.mean()),
    }
    return truth


def generate_all(work_dir: Path, seed: int = SEED) -> dict:
    raw = work_dir / "raw"
    olist = generate_olist(raw, seed)
    criteo_path = work_dir / "criteo" / "criteo-uplift-synthetic.csv"
    truth = generate_criteo(criteo_path, seed)
    manifest = {
        "label": "SYNTHETIC - generated, not real data",
        "seed": seed,
        "generator": "python/portfolio/synthetic.py",
        "files": {name: {"rows": rows, "sha256": sha256(raw / name)}
                  for name, rows in olist.files.items()},
        "criteo": {"file": criteo_path.name, "sha256": sha256(criteo_path), **truth},
    }
    (work_dir / "synthetic_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest
