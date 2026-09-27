"""Randomised-experiment statistics for the Criteo-style uplift test.

Estimands, stated so nobody reads the wrong one:

  ITT  = P(convert | assigned treatment) - P(convert | assigned control).
         Identified by randomisation of `treatment` alone. This is the effect of the
         decision anyone can actually take: assigning a population to the campaign.
  CACE = ITT / compliance, the effect on compliers (users who would be exposed if
         assigned). Needs extra assumptions (listed in ASSUMPTIONS) and describes only a
         small, systematically different subgroup - it is not "the true effect".
  naive exposed-vs-control is NOT an estimate of either: exposure is post-assignment and
         selected by user behaviour.

Uncertainty: Wald (unpooled) 95% interval for the difference in proportions; delta-method
interval for the relative lift (log ratio) and for CACE (ratio estimator, including the
covariance between the treated conversion rate and the compliance rate, which come from
the same treated users). The pooled z-test p-value is reported as a footnote only.

Statistical significance is not practical importance: at millions of rows a trivially
small effect is "significant". The interval, the absolute size and the (hypothetical)
economics carry the decision.
"""
from __future__ import annotations

import math
import numbers
from dataclasses import dataclass

from statistics import NormalDist

Z = NormalDist()

# Generic assumptions. Measured diagnostics (e.g. covariate balance) are NOT stated here:
# they belong to a specific run and are attached by the caller with their provenance.
ASSUMPTIONS = [
    {"name": "Randomised assignment", "used_by": "ITT, CACE", "kind": "design",
     "status": "a design property; covariate balance across the assigned arms is the check (see diagnostics)"},
    {"name": "SUTVA / no interference between users", "used_by": "ITT, CACE", "kind": "assumed",
     "status": "assumed; not testable with anonymous impressions"},
    {"name": "One-sided non-compliance (no exposure in control)", "used_by": "CACE", "kind": "checked",
     "status": "counts_from_csv rejects any exposed control unit; for the historical run, control exposure "
               "was documented as 0"},
    {"name": "Exclusion restriction (assignment affects conversion only through exposure)",
     "used_by": "CACE", "kind": "assumed", "status": "assumed and untestable; violated if assignment changes anything besides ad exposure"},
    {"name": "CACE describes compliers only", "used_by": "CACE", "kind": "design",
     "status": "compliers can differ sharply from other users (see the exposure balance diagnostic), so CACE "
               "does not transfer to the whole population"},
]


@dataclass(frozen=True)
class ArmCounts:
    n_t: int            # assigned treatment
    y_t: int            # conversions among assigned treatment
    n_c: int            # assigned control
    y_c: int
    n_exposed: int      # exposed (treated arm only)
    y_exposed: int      # conversions among exposed

    def validate(self) -> list[str]:
        """Every cell of the 2x2 (treated: exposed / unexposed x converted / not; control:
        converted / not) must be a feasible non-negative integer count."""
        p = []
        vals = {k: getattr(self, k) for k in ("n_t", "y_t", "n_c", "y_c", "n_exposed", "y_exposed")}
        for k, v in vals.items():
            if isinstance(v, bool) or not isinstance(v, numbers.Integral):
                p.append(f"{k} must be an integer count, got {v!r}")
            elif v < 0:
                p.append(f"{k} must be >= 0, got {v}")
        if p:
            return p
        if self.n_t == 0 or self.n_c == 0:
            p.append("each arm needs at least one assigned unit")
        if self.y_t > self.n_t:
            p.append("treated conversions exceed treated units")
        if self.y_c > self.n_c:
            p.append("control conversions exceed control units")
        if self.n_exposed > self.n_t:
            p.append("exposed units exceed treated units")
        if self.y_exposed > self.n_exposed:
            p.append("exposed conversions exceed exposed units")
        if self.y_exposed > self.y_t:
            p.append("exposed conversions exceed all treated conversions")
        if self.y_t - self.y_exposed > self.n_t - self.n_exposed:
            p.append("unexposed treated conversions exceed unexposed treated units")
        return p


def z_for(alpha: float) -> float:
    return Z.inv_cdf(1 - alpha / 2)


def _approx_warnings(c: ArmCounts) -> list[str]:
    w = []
    cells = {"treated conversions": c.y_t, "treated non-conversions": c.n_t - c.y_t,
             "control conversions": c.y_c, "control non-conversions": c.n_c - c.y_c}
    zero = [k for k, v in cells.items() if v == 0]
    small = [k for k, v in cells.items() if 0 < v < 10]
    if zero:
        w.append("boundary: " + ", ".join(zero) + " = 0, so an arm rate is exactly 0 or 1 and the Wald "
                 "interval collapses; it is reported as unavailable rather than as a zero-width interval")
    if small:
        w.append("normal approximation unreliable: fewer than 10 in " + ", ".join(small))
    return w


def itt(c: ArmCounts, alpha: float = 0.05) -> dict:
    problems = c.validate()
    if problems:
        return {"status": "invalid", "problems": problems}
    p_t, p_c = c.y_t / c.n_t, c.y_c / c.n_c
    diff = p_t - p_c
    warnings = _approx_warnings(c)
    boundary = p_t in (0.0, 1.0) or p_c in (0.0, 1.0)
    se = math.sqrt(p_t * (1 - p_t) / c.n_t + p_c * (1 - p_c) / c.n_c)
    z = z_for(alpha)
    out = {"status": "ok", "p_t": p_t, "p_c": p_c, "diff": diff, "alpha": alpha, "warnings": warnings,
           "se": None if boundary else se,
           "ci": None if boundary else [diff - z * se, diff + z * se],
           "ci_status": "unavailable" if boundary else ("approximate" if warnings else "ok")}
    if c.y_t > 0 and c.y_c > 0:
        rr = p_t / p_c
        se_log = math.sqrt((1 - p_t) / c.y_t + (1 - p_c) / c.y_c)
        out["relative_lift"] = rr - 1
        out["relative_ci"] = [math.exp(math.log(rr) - z * se_log) - 1,
                              math.exp(math.log(rr) + z * se_log) - 1]
    else:
        out["relative_lift"] = None if c.y_c == 0 else rr_minus_one(p_t, p_c)
        out["relative_ci"] = None
    # pooled two-proportion z test - a footnote, not the finding
    pool = (c.y_t + c.y_c) / (c.n_t + c.n_c)
    se0 = math.sqrt(pool * (1 - pool) * (1 / c.n_t + 1 / c.n_c))
    if se0 > 0:
        zstat = diff / se0
        out["z"] = zstat
        out["p_value_two_sided"] = 2 * (1 - Z.cdf(abs(zstat)))
        out["log10_p_value"] = _log10_two_sided_p(abs(zstat))   # p underflows to 0 at |z| ~ 38
    else:
        out["z"] = out["p_value_two_sided"] = out["log10_p_value"] = None
        out["warnings"].append("no variation in the outcome: the z test is undefined")
    return out


def rr_minus_one(p_t: float, p_c: float):
    return None if p_c == 0 else p_t / p_c - 1


def _log10_two_sided_p(z: float) -> float:
    """log10 of 2*(1 - Phi(z)) using the asymptotic Mills-ratio series for large z."""
    if z < 8:
        return math.log10(2 * (1 - Z.cdf(z)))
    # 1 - Phi(z) ~ phi(z)/z * (1 - 1/z^2 + 3/z^4 - 15/z^6)
    ln_phi = -0.5 * z * z - 0.5 * math.log(2 * math.pi)
    series = 1 - 1 / z**2 + 3 / z**4 - 15 / z**6
    return (math.log(2) + ln_phi - math.log(z) + math.log(series)) / math.log(10)


def cace(c: ArmCounts, alpha: float = 0.05) -> dict:
    """Wald/IV estimator with a delta-method interval, plus the complier-decomposition
    cross-check (independent algebra, same assumptions)."""
    problems = c.validate()
    if problems:
        return {"status": "invalid", "problems": problems}
    if c.n_exposed == 0:
        return {"status": "unavailable", "problems": ["no exposed units: compliance is zero"]}
    p_t, p_c = c.y_t / c.n_t, c.y_c / c.n_c
    pi = c.n_exposed / c.n_t
    diff = p_t - p_c
    est = diff / pi
    var_pt = p_t * (1 - p_t) / c.n_t
    var_pc = p_c * (1 - p_c) / c.n_c
    var_pi = pi * (1 - pi) / c.n_t
    cov_pt_pi = (c.y_exposed / c.n_t - p_t * pi) / c.n_t
    # g(pt, pc, pi) = (pt - pc) / pi ; gradient (1/pi, -1/pi, -(pt-pc)/pi^2)
    var = (var_pt + var_pc) / pi**2 + diff**2 * var_pi / pi**4 - 2 * diff * cov_pt_pi / pi**3
    warnings = _approx_warnings(c)
    boundary = p_t in (0.0, 1.0) or p_c in (0.0, 1.0) or var <= 0
    se = math.sqrt(var) if not boundary else None
    z = z_for(alpha)
    p_exp = c.y_exposed / c.n_exposed
    n_never = c.n_t - c.n_exposed
    p_never = (c.y_t - c.y_exposed) / n_never if n_never else None
    complier_control = (p_c - (1 - pi) * p_never) / pi if p_never is not None else None
    decomposition = p_exp - complier_control if complier_control is not None else None
    return {
        "status": "ok", "compliance": pi, "cace": est, "se": se,
        "ci": None if boundary else [est - z * se, est + z * se],
        "ci_status": "unavailable" if boundary else ("approximate" if warnings else "ok"),
        "warnings": warnings,
        "exposed_rate": p_exp, "never_taker_rate": p_never,
        "implied_complier_control_rate": complier_control,
        "decomposition_cace": decomposition,
        "wald_vs_decomposition_gap": None if decomposition is None else abs(est - decomposition),
        "complier_relative_lift": None if not complier_control else p_exp / complier_control - 1,
    }


def naive_exposed_vs_control(c: ArmCounts) -> dict:
    p_exp = c.y_exposed / c.n_exposed if c.n_exposed else None
    p_c = c.y_c / c.n_c
    return {"exposed_rate": p_exp, "control_rate": p_c,
            "diff": None if p_exp is None else p_exp - p_c,
            "relative": None if p_exp is None or p_c == 0 else p_exp / p_c - 1,
            "label": "NOT an effect estimate: exposure is selected by user behaviour"}


def mde(c: ArmCounts, alpha: float = 0.05, power: float = 0.80) -> dict:
    """Minimum detectable absolute difference, normal approximation at the control rate.
    Unavailable when the control rate is 0 or 1 (no variance to plan with)."""
    p_c = c.y_c / c.n_c
    if p_c in (0.0, 1.0):
        return {"alpha": alpha, "power": power, "mde_abs": None, "mde_rel": None,
                "note": "control rate is at a boundary; the normal-approximation MDE is undefined"}
    se = math.sqrt(p_c * (1 - p_c) * (1 / c.n_t + 1 / c.n_c))
    m = (z_for(alpha) + Z.inv_cdf(power)) * se
    return {"alpha": alpha, "power": power, "mde_abs": m, "mde_rel": m / p_c}


def cohen_h_mde(c: ArmCounts, alpha: float = 0.05, power: float = 0.80) -> float | None:
    """Reproduces python/criteo/ab_analysis.py: solve Cohen's h for the design, then
    invert h back to an absolute difference above the control rate."""
    p_c = c.y_c / c.n_c
    if p_c in (0.0, 1.0):
        return None
    ratio = c.n_c / c.n_t
    h = (z_for(alpha) + Z.inv_cdf(power)) * math.sqrt(1 / c.n_t + 1 / (c.n_t * ratio))
    # h = 2*asin(sqrt(p2)) - 2*asin(sqrt(p1))  ->  p2 = sin(asin(sqrt(p1)) + h/2)^2
    p2 = math.sin(min(math.pi / 2, math.asin(math.sqrt(p_c)) + h / 2)) ** 2
    return p2 - p_c


def breakeven(itt_diff: float, itt_ci: list[float], cost_per_1000: float) -> dict:
    """HYPOTHETICAL economics. cost_per_1000 is a user-entered cost per 1,000 users
    assigned to the campaign; the dataset contains no cost or margin. Returns the value
    per incremental conversion needed to break even, for the point estimate and for
    the ends of the ITT interval (an interval end <= 0 means 'no finite break-even')."""
    def be(d):
        return None if d <= 0 else cost_per_1000 / (1000 * d)
    return {"incremental_per_1000": 1000 * itt_diff,
            "incremental_per_1000_ci": [1000 * itt_ci[0], 1000 * itt_ci[1]],
            "breakeven_value": be(itt_diff),
            "breakeven_value_range": [be(itt_ci[1]), be(itt_ci[0])],
            "label": "HYPOTHETICAL - cost and value are not in the dataset"}


def analyse(c: ArmCounts, alpha: float = 0.05, diagnostics: dict | None = None) -> dict:
    """One controlled result: invalid counts stop here instead of failing later."""
    problems = c.validate()
    if problems:
        return {"status": "invalid", "problems": problems, "counts": dict(c.__dict__)}
    return {"status": "ok", "counts": dict(c.__dict__), "itt": itt(c, alpha), "cace": cace(c, alpha),
            "naive": naive_exposed_vs_control(c), "mde80": mde(c, alpha, 0.80),
            "mde95": mde(c, alpha, 0.95), "cohen_h_mde80": cohen_h_mde(c, alpha, 0.80),
            "cohen_h_mde95": cohen_h_mde(c, alpha, 0.95),
            "assumptions": ASSUMPTIONS, "diagnostics": diagnostics}


def _binary_check(con, source: str, cols: tuple[str, ...]) -> None:
    for col in cols:
        bad = con.execute(f"SELECT count(*) FROM {source} WHERE {col} IS NULL "
                          f"OR CAST({col} AS VARCHAR) NOT IN ('0', '1')").fetchone()[0]
        if bad:
            raise ValueError(f"{bad} row(s) have a NULL or non-binary {col}; refusing to drop them silently")


def balance_from_csv(path, col: str = "f0") -> dict:
    """Standardised mean difference of one covariate across the randomised arms and, within
    the treated arm, across exposure. Measured on THIS file."""
    import duckdb
    from .paths import sql_literal
    con = duckdb.connect()
    # One engine thread: DuckDB parallelises float aggregates over row groups, and the
    # summation order (hence the last digits of avg / var_samp) otherwise varies per run.
    con.execute("SET threads TO 1")
    src = f"read_csv_auto({sql_literal(path)})"
    _binary_check(con, src, ("treatment", "exposure"))

    def smd(where_a: str, where_b: str) -> float | None:
        a = con.execute(f"SELECT avg({col}), var_samp({col}) FROM {src} WHERE {where_a}").fetchone()
        b = con.execute(f"SELECT avg({col}), var_samp({col}) FROM {src} WHERE {where_b}").fetchone()
        if None in a or None in b or (a[1] + b[1]) <= 0:
            return None
        return abs(a[0] - b[0]) / math.sqrt((a[1] + b[1]) / 2)
    out = {"covariate": col,
           "smd_treatment": smd("CAST(treatment AS INTEGER) = 1", "CAST(treatment AS INTEGER) = 0"),
           "smd_exposure_within_treated": smd("CAST(treatment AS INTEGER) = 1 AND CAST(exposure AS INTEGER) = 1",
                                              "CAST(treatment AS INTEGER) = 1 AND CAST(exposure AS INTEGER) = 0"),
           "provenance": "measured on the synthetic file in this build"}
    con.close()
    return out


def counts_from_csv(path) -> ArmCounts:
    import duckdb
    from .paths import sql_literal
    con = duckdb.connect()
    src = f"read_csv_auto({sql_literal(path)})"
    _binary_check(con, src, ("treatment", "conversion", "exposure"))
    r = con.execute(f"""
        WITH t AS (SELECT CAST(treatment AS INTEGER) AS tr, CAST(conversion AS INTEGER) AS cv,
                          CAST(exposure AS INTEGER) AS ex FROM {src})
        SELECT count(*) FILTER (WHERE tr=1),
               count(*) FILTER (WHERE tr=1 AND cv=1),
               count(*) FILTER (WHERE tr=0),
               count(*) FILTER (WHERE tr=0 AND cv=1),
               count(*) FILTER (WHERE tr=1 AND ex=1),
               count(*) FILTER (WHERE tr=1 AND ex=1 AND cv=1),
               count(*) FILTER (WHERE tr=0 AND ex=1)
        FROM t
    """).fetchone()
    con.close()
    if r[6]:
        raise ValueError(f"{r[6]} control units are exposed: one-sided non-compliance violated")
    return ArmCounts(*(int(v) for v in r[:6]))
