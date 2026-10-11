#!/usr/bin/env python3
"""
Python translation of codes_final.do
====================================

Replicates the fixed-effects regressions in:
    Zarepour & Wagner (2023), Energy Economics 124, 106762

Stata command translated:
    areg y x1 x2 ..., absorb(id) vce(cluster id)

Implementation details
----------------------
1. Entity fixed effects are absorbed by within-group demeaning.
2. Standard errors are clustered by ``id``.
3. A Stata-like small-sample correction counts absorbed fixed effects in
   residual degrees of freedom. This makes the reported standard errors
   closely match Stata's ``areg, absorb(id) vce(cluster id)``.
4. Collinear regressors are removed from right to left, preserving the
   order used in the Stata code. This matters for the 2009-2011 models,
   where ``trend`` is collinear with other time-level regressors.

Example
-------
python scripts/replicate_paper.py \
    --data "data/mydata.xlsx" \
    --output "results/python_regression_results.xlsx"

Supported input formats: .dta, .xlsx, .xls, .csv, .parquet
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Sequence

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats


# -----------------------------------------------------------------------------
# Variable sets copied from the Stata do-file
# -----------------------------------------------------------------------------
VAR2 = [
    "srct",
    "lrinpraw",
    "lrinpndur",
    "lrinppack",
    "lrenerg",
    "lrinpwater",
    "lrinpmus",
    "lrcapform",
    "lrperwage",
    "lfirmno",
    "loilx1",
    "trend",
]

VAR2P = [
    "lenergp",
    "lrinpraw",
    "lrinpndur",
    "lrinppack",
    "lrenerg",
    "lrinpwater",
    "lrinpmus",
    "lrcapform",
    "lrperwage",
    "lfirmno",
    "loilx1",
    "trend",
]

VAR2RP = [
    "lrenergp",
    "lrinpraw",
    "lrinpndur",
    "lrinppack",
    "lrenerg",
    "lrinpwater",
    "lrinpmus",
    "lrcapform",
    "lrperwage",
    "lfirmno",
    "loilx1",
    "trend",
]

OUTCOMES = ["lrouttot", "lrmuvaluad", "lnmuopsur"]
OUTCOME_LABELS = {
    "lrouttot": "Output",
    "lrmuvaluad": "Value-added",
    "lnmuopsur": "Operating-surplus",
}


@dataclass
class AregResult:
    """Container for one absorbed fixed-effects regression."""

    table: str
    panel: str
    sample: str
    outcome: str
    main_variable: str | None
    nobs: int
    n_clusters: int
    n_absorbed_df: int
    regressors_requested: list[str]
    regressors_used: list[str]
    regressors_dropped: list[str]
    params: pd.Series
    covariance: pd.DataFrame
    std_errors: pd.Series
    t_values: pd.Series
    p_values: pd.Series
    ci_low: pd.Series
    ci_high: pd.Series
    within_r2: float
    df_resid_areg: int
    effect_pct: float | None
    effect_interpretation: str | None

    def coefficient_frame(self) -> pd.DataFrame:
        rows: list[dict[str, object]] = []
        for variable in self.params.index:
            rows.append(
                {
                    "table": self.table,
                    "panel": self.panel,
                    "sample": self.sample,
                    "outcome": self.outcome,
                    "outcome_label": OUTCOME_LABELS.get(self.outcome, self.outcome),
                    "main_variable": self.main_variable,
                    "variable": variable,
                    "coefficient": self.params[variable],
                    "std_error": self.std_errors[variable],
                    "t_stat": self.t_values[variable],
                    "p_value": self.p_values[variable],
                    "ci_95_low": self.ci_low[variable],
                    "ci_95_high": self.ci_high[variable],
                    "nobs": self.nobs,
                    "n_clusters": self.n_clusters,
                    "absorbed_df": self.n_absorbed_df,
                    "df_resid_areg": self.df_resid_areg,
                    "within_r2": self.within_r2,
                    "is_main_effect": variable == self.main_variable,
                    "effect_pct": self.effect_pct if variable == self.main_variable else np.nan,
                    "effect_interpretation": (
                        self.effect_interpretation if variable == self.main_variable else None
                    ),
                }
            )
        return pd.DataFrame(rows)

    def model_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "table": self.table,
                    "panel": self.panel,
                    "sample": self.sample,
                    "outcome": self.outcome,
                    "outcome_label": OUTCOME_LABELS.get(self.outcome, self.outcome),
                    "main_variable": self.main_variable,
                    "nobs": self.nobs,
                    "n_clusters": self.n_clusters,
                    "absorbed_df": self.n_absorbed_df,
                    "df_resid_areg": self.df_resid_areg,
                    "within_r2": self.within_r2,
                    "regressors_requested": " ".join(self.regressors_requested),
                    "regressors_used": " ".join(self.regressors_used),
                    "regressors_dropped": " ".join(self.regressors_dropped),
                    "effect_pct": self.effect_pct,
                    "effect_interpretation": self.effect_interpretation,
                }
            ]
        )


# -----------------------------------------------------------------------------
# Data loading and normalization
# -----------------------------------------------------------------------------
def load_data(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".dta":
        return pd.read_stata(path, convert_categoricals=False)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    raise ValueError(
        f"Unsupported data format: {suffix}. Use .dta, .xlsx, .xls, .csv, or .parquet."
    )


def normalize_data(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize columns that may differ between Stata and Excel exports."""
    data = df.copy()

    required_identifiers = {"id", "year"}
    missing_identifiers = sorted(required_identifiers.difference(data.columns))
    if missing_identifiers:
        raise KeyError(f"Missing required identifier columns: {missing_identifiers}")

    # Numeric entity and year identifiers.
    data["id"] = pd.to_numeric(data["id"], errors="coerce")
    data["year"] = pd.to_numeric(data["year"], errors="coerce")

    # The Excel file stores treatment status as labels, while the Stata code
    # compares it with 0 and 1. Create a robust numeric version.
    if "treat" in data.columns:
        if pd.api.types.is_numeric_dtype(data["treat"]):
            data["treat_num"] = pd.to_numeric(data["treat"], errors="coerce")
        else:
            labels = data["treat"].astype("string").str.strip().str.lower()
            mapping = {
                "control": 0,
                "less energy-sensitive": 0,
                "less energy sensitive": 0,
                "0": 0,
                "treatment": 1,
                "treated": 1,
                "energy-sensitive": 1,
                "energy sensitive": 1,
                "1": 1,
            }
            data["treat_num"] = labels.map(mapping)
            unmapped = sorted(labels[data["treat_num"].isna() & labels.notna()].unique())
            if unmapped:
                raise ValueError(f"Unrecognized values in 'treat': {unmapped}")
    elif "treat_num" not in data.columns:
        raise KeyError("The data must contain a 'treat' or 'treat_num' column.")

    # srct1 is the post-reform × treatment interaction in the supplied data.
    if "srct1" not in data.columns:
        if {"srct", "treat_num"}.issubset(data.columns):
            data["srct1"] = data["srct"] * data["treat_num"]
        else:
            raise KeyError("Cannot construct srct1; need columns 'srct' and 'treat'.")

    # The do-file uses srct2 in Table A.5, but the supplied Excel data does not
    # contain it. Within the balanced-panel restriction it is the same DID
    # interaction, so reconstruct it from srct × treatment.
    if "srct2" not in data.columns:
        if {"srct", "treat_num"}.issubset(data.columns):
            data["srct2"] = data["srct"] * data["treat_num"]
            warnings.warn(
                "Column 'srct2' was absent and has been reconstructed as "
                "srct * treat_num for Table A.5.",
                stacklevel=2,
            )
        else:
            raise KeyError("Cannot construct srct2; need columns 'srct' and 'treat'.")

    # Convert ISIC2 to numeric for robust comparisons. Stata's source variable
    # was apparently string, while the Excel version is numeric.
    if "isic2" in data.columns:
        data["isic2_num"] = pd.to_numeric(data["isic2"], errors="coerce")

    return data


# -----------------------------------------------------------------------------
# Stata areg equivalent
# -----------------------------------------------------------------------------
def _ordered_full_rank_columns(X: pd.DataFrame, tolerance: float = 1e-10) -> tuple[list[str], list[str]]:
    """
    Keep columns in their original order and drop a column if it does not
    increase matrix rank. This emulates Stata's tendency to keep earlier
    variables and omit later collinear variables.
    """
    kept: list[str] = []
    dropped: list[str] = []
    current_rank = 0

    for column in X.columns:
        candidate = kept + [column]
        matrix = X[candidate].to_numpy(dtype=float)
        new_rank = np.linalg.matrix_rank(matrix, tol=tolerance)
        if new_rank > current_rank:
            kept.append(column)
            current_rank = new_rank
        else:
            dropped.append(column)

    return kept, dropped


def _main_effect_transform(variable: str | None, coefficient: float | None) -> tuple[float | None, str | None]:
    """Return the paper-style percentage interpretation for the key coefficient."""
    if variable is None or coefficient is None or not np.isfinite(coefficient):
        return None, None

    if variable in {"srct", "srct1", "srct2"}:
        effect = 100.0 * (math.exp(coefficient) - 1.0)
        return effect, "Exact percent change for a 0→1 change in the indicator"

    if variable in {"lenergp", "lrenergp"}:
        effect = 100.0 * (math.exp(coefficient * math.log(2.0)) - 1.0)
        return effect, "Exact percent change associated with doubling the energy price"

    return None, None


def areg(
    data: pd.DataFrame,
    outcome: str,
    regressors: Sequence[str],
    *,
    table: str,
    panel: str,
    sample: str,
    main_variable: str | None,
    mask: pd.Series | np.ndarray | None = None,
    absorb: str = "id",
    cluster: str = "id",
) -> AregResult:
    """
    Estimate a one-way absorbed fixed-effects model with clustered SEs.

    Equivalent target:
        areg outcome regressors, absorb(id) vce(cluster id)
    """
    requested = list(regressors)
    columns = [outcome, *requested, absorb, cluster]
    columns = list(dict.fromkeys(columns))

    missing = [column for column in columns if column not in data.columns]
    if missing:
        raise KeyError(
            f"{table} {panel}, {outcome}: missing columns {missing}"
        )

    if mask is None:
        work = data.loc[:, columns].copy()
    else:
        aligned_mask = pd.Series(mask, index=data.index).fillna(False).astype(bool)
        work = data.loc[aligned_mask, columns].copy()

    # Coerce model variables to numeric and apply Stata-like listwise deletion.
    for column in [outcome, *requested, absorb, cluster]:
        work[column] = pd.to_numeric(work[column], errors="coerce")
    work = work.dropna(subset=[outcome, *requested, absorb, cluster])

    if work.empty:
        raise ValueError(f"{table} {panel}, {outcome}: no observations after filtering.")

    model_variables = [outcome, *requested]
    values = work[model_variables].astype(float)

    # Within transformation: z_it - mean_i(z_it)
    group_means = values.groupby(work[absorb], sort=False).transform("mean")
    within = values - group_means
    y_within = within[outcome]
    X_within_all = within[requested]

    used, dropped = _ordered_full_rank_columns(X_within_all)
    if not used:
        raise ValueError(f"{table} {panel}, {outcome}: all regressors are collinear after absorption.")

    X_within = X_within_all[used]
    nobs = int(len(work))
    n_clusters = int(work[cluster].nunique())
    k = int(len(used))
    absorbed_df = int(work[absorb].nunique() - 1)
    df_resid_areg = int(nobs - k - absorbed_df)

    if n_clusters < 2:
        raise ValueError(f"{table} {panel}, {outcome}: at least two clusters are required.")
    if df_resid_areg <= 0:
        raise ValueError(
            f"{table} {panel}, {outcome}: non-positive residual degrees of freedom."
        )

    fitted = sm.OLS(y_within, X_within, hasconst=False).fit(
        cov_type="cluster",
        cov_kwds={
            "groups": work[cluster].to_numpy(),
            "use_correction": True,
            "df_correction": True,
        },
    )

    params = pd.Series(fitted.params, index=used, dtype=float)
    base_cov = pd.DataFrame(fitted.cov_params(), index=used, columns=used, dtype=float)

    # statsmodels' cluster correction uses N-k. Stata areg additionally counts
    # absorbed FE degrees of freedom. Multiply by the relative correction:
    #     (N-k) / (N-k-(G_absorb-1))
    stata_df_scale = (nobs - k) / df_resid_areg
    covariance = base_cov * stata_df_scale

    std_errors = pd.Series(np.sqrt(np.diag(covariance)), index=used)
    t_values = params / std_errors
    coefficient_df = n_clusters - 1
    p_values = pd.Series(
        2.0 * stats.t.sf(np.abs(t_values.to_numpy()), df=coefficient_df),
        index=used,
    )
    critical = stats.t.ppf(0.975, df=coefficient_df)
    ci_low = params - critical * std_errors
    ci_high = params + critical * std_errors

    residuals = y_within - X_within.to_numpy() @ params.to_numpy()
    ssr = float(np.dot(residuals, residuals))
    centered_tss = float(np.dot(y_within, y_within))
    within_r2 = np.nan if centered_tss <= 0 else 1.0 - ssr / centered_tss

    main_coefficient = params.get(main_variable, np.nan) if main_variable else np.nan
    effect_pct, effect_interpretation = _main_effect_transform(
        main_variable,
        None if pd.isna(main_coefficient) else float(main_coefficient),
    )

    return AregResult(
        table=table,
        panel=panel,
        sample=sample,
        outcome=outcome,
        main_variable=main_variable,
        nobs=nobs,
        n_clusters=n_clusters,
        n_absorbed_df=absorbed_df,
        regressors_requested=requested,
        regressors_used=used,
        regressors_dropped=dropped,
        params=params,
        covariance=covariance,
        std_errors=std_errors,
        t_values=t_values,
        p_values=p_values,
        ci_low=ci_low,
        ci_high=ci_high,
        within_r2=within_r2,
        df_resid_areg=df_resid_areg,
        effect_pct=effect_pct,
        effect_interpretation=effect_interpretation,
    )


def joint_wald_test(result: AregResult, variables: Sequence[str], test_name: str) -> dict[str, object]:
    """Stata-style joint test, e.g. ``test t1t t2t`` after clustered areg."""
    variables = list(variables)
    missing = [v for v in variables if v not in result.params.index]
    if missing:
        raise KeyError(f"Cannot run {test_name}; variables omitted or absent: {missing}")

    beta = result.params.loc[variables].to_numpy(dtype=float)
    cov = result.covariance.loc[variables, variables].to_numpy(dtype=float)
    q = len(variables)
    wald_chi2 = float(beta.T @ np.linalg.pinv(cov) @ beta)
    f_stat = wald_chi2 / q
    df_num = q
    df_denom = result.n_clusters - 1
    p_value = float(stats.f.sf(f_stat, df_num, df_denom))

    return {
        "table": result.table,
        "panel": result.panel,
        "sample": result.sample,
        "outcome": result.outcome,
        "test": test_name,
        "variables": " ".join(variables),
        "F": f_stat,
        "df_num": df_num,
        "df_denom": df_denom,
        "p_value": p_value,
    }


# -----------------------------------------------------------------------------
# Reproduction of each table in the do-file
# -----------------------------------------------------------------------------
def run_triplet(
    results: list[AregResult],
    data: pd.DataFrame,
    *,
    table: str,
    panel: str,
    sample: str,
    regressors: Sequence[str],
    main_variable: str | None,
    mask: pd.Series | np.ndarray | None = None,
) -> list[AregResult]:
    new_results: list[AregResult] = []
    for outcome in OUTCOMES:
        result = areg(
            data,
            outcome,
            regressors,
            table=table,
            panel=panel,
            sample=sample,
            main_variable=main_variable,
            mask=mask,
        )
        results.append(result)
        new_results.append(result)
    return new_results


def reproduce_all(data: pd.DataFrame) -> tuple[list[AregResult], list[dict[str, object]]]:
    results: list[AregResult] = []
    wald_tests: list[dict[str, object]] = []

    # ------------------------------------------------------------------
    # Table 5: Impact of the energy subsidy reform
    # ------------------------------------------------------------------
    run_triplet(
        results,
        data,
        table="Table 5",
        panel="Panel A",
        sample="Overall impact, 2009-2013",
        regressors=VAR2,
        main_variable="srct",
    )
    run_triplet(
        results,
        data,
        table="Table 5",
        panel="Panel B",
        sample="Immediate impact, 2009-2011",
        regressors=VAR2,
        main_variable="srct",
        mask=data["year"] < 2012,
    )
    table5_c = [
        "srct1",
        "lrinpraw",
        "lrinpndur",
        "lrinppack",
        "lrenerg",
        "lrinpwater",
        "lrinpmus",
        "lrcapform",
        "lrperwage",
        "lfirmno",
        "loilx1",
        "trend",
    ]
    run_triplet(
        results,
        data,
        table="Table 5",
        panel="Panel C",
        sample="Difference-in-differences",
        regressors=table5_c,
        main_variable="srct1",
    )

    # ------------------------------------------------------------------
    # Table 6: Energy price and manufacturing performance
    # ------------------------------------------------------------------
    run_triplet(
        results,
        data,
        table="Table 6",
        panel="Panel A",
        sample="Overall",
        regressors=VAR2P,
        main_variable="lenergp",
    )
    run_triplet(
        results,
        data,
        table="Table 6",
        panel="Panel B - Control",
        sample="Less energy-sensitive industries",
        regressors=VAR2P,
        main_variable="lenergp",
        mask=data["treat_num"] == 0,
    )
    run_triplet(
        results,
        data,
        table="Table 6",
        panel="Panel B - Treatment",
        sample="Energy-sensitive industries",
        regressors=VAR2P,
        main_variable="lenergp",
        mask=data["treat_num"] == 1,
    )

    # ------------------------------------------------------------------
    # Table 7: Heterogeneity analysis
    # ------------------------------------------------------------------
    for category, label in [
        (1, "Low energy intensity"),
        (2, "Moderate energy intensity"),
        (3, "High energy intensity"),
    ]:
        run_triplet(
            results,
            data,
            table="Table 7",
            panel=f"Panel A - Category {category}",
            sample=label,
            regressors=VAR2,
            main_variable="srct",
            mask=data["energcat"] == category,
        )

    run_triplet(
        results,
        data,
        table="Table 7",
        panel="Panel B - Low/medium-low tech",
        sample="Technology intensity <= 2",
        regressors=VAR2,
        main_variable="srct",
        mask=data["tech"] <= 2,
    )
    run_triplet(
        results,
        data,
        table="Table 7",
        panel="Panel B - Medium-high/high tech",
        sample="Technology intensity > 2",
        regressors=VAR2,
        main_variable="srct",
        mask=data["tech"] > 2,
    )

    # ------------------------------------------------------------------
    # Table 8: Mitigating and reinforcing firm characteristics
    # ------------------------------------------------------------------
    run_triplet(
        results,
        data,
        table="Table 8",
        panel="Panel A",
        sample="Large firms: xlargrio >= 0.5",
        regressors=VAR2,
        main_variable="srct",
        mask=data["xlargrio"] >= 0.5,
    )
    run_triplet(
        results,
        data,
        table="Table 8",
        panel="Panel B",
        sample="Large fixed capital: rfcaprio > 0.06",
        regressors=VAR2,
        main_variable="srct",
        mask=data["rfcaprio"] > 0.06,
    )
    run_triplet(
        results,
        data,
        table="Table 8",
        panel="Panel C",
        sample="Food and beverage industry: ISIC2 = 15",
        regressors=VAR2,
        main_variable="srct",
        mask=data["isic2_num"] == 15,
    )
    run_triplet(
        results,
        data,
        table="Table 8",
        panel="Panel D",
        sample="Provinces with low GDP: lesgdp = 1",
        regressors=VAR2,
        main_variable="srct",
        mask=data["lesgdp"] == 1,
    )

    # ------------------------------------------------------------------
    # Appendix Table A.3: Real energy price
    # ------------------------------------------------------------------
    run_triplet(
        results,
        data,
        table="Table A.3",
        panel="Panel A",
        sample="Overall",
        regressors=VAR2RP,
        main_variable="lrenergp",
    )
    run_triplet(
        results,
        data,
        table="Table A.3",
        panel="Panel B - Control",
        sample="Less energy-sensitive industries",
        regressors=VAR2RP,
        main_variable="lrenergp",
        mask=data["treat_num"] == 0,
    )
    run_triplet(
        results,
        data,
        table="Table A.3",
        panel="Panel B - Treatment",
        sample="Energy-sensitive industries",
        regressors=VAR2RP,
        main_variable="lrenergp",
        mask=data["treat_num"] == 1,
    )

    # ------------------------------------------------------------------
    # Appendix Table A.4: Parallel-trend test
    # ------------------------------------------------------------------
    event_study_regressors = [
        "t1t",
        "t2t",
        "t4t",
        "t5t",
        "lrinpraw",
        "lrinpndur",
        "lrinppack",
        "lrenerg",
        "lrinpwater",
        "lrinpmus",
        "lrcapform",
        "lrperwage",
        "lfirmno",
        "loilx1",
        "trend",
    ]
    event_results = run_triplet(
        results,
        data,
        table="Table A.4",
        panel="Parallel trend",
        sample="Full sample",
        regressors=event_study_regressors,
        main_variable=None,
    )
    for result in event_results:
        wald_tests.append(joint_wald_test(result, ["t1t", "t2t"], "t1t = t2t = 0"))

    # ------------------------------------------------------------------
    # Appendix Table A.5: Balanced panel
    # ------------------------------------------------------------------
    balanced = data["presnt"] == 1
    run_triplet(
        results,
        data,
        table="Table A.5",
        panel="Panel A",
        sample="Balanced panel, overall impact",
        regressors=VAR2,
        main_variable="srct",
        mask=balanced,
    )
    run_triplet(
        results,
        data,
        table="Table A.5",
        panel="Panel B",
        sample="Balanced panel, immediate impact 2009-2011",
        regressors=VAR2,
        main_variable="srct",
        mask=balanced & (data["year"] < 2012),
    )
    table_a5_c = [
        "srct2",
        "lrinpraw",
        "lrinpndur",
        "lrinppack",
        "lrenerg",
        "lrinpwater",
        "lrinpmus",
        "lrcapform",
        "lrperwage",
        "lfirmno",
        "loilx1",
        "trend",
    ]
    run_triplet(
        results,
        data,
        table="Table A.5",
        panel="Panel C",
        sample="Balanced panel, difference-in-differences",
        regressors=table_a5_c,
        main_variable="srct2",
        mask=balanced,
    )

    # ------------------------------------------------------------------
    # Appendix Table A.6: Excluding ISIC 23
    # ------------------------------------------------------------------
    excluding_isic23 = data["isic2_num"] != 23
    run_triplet(
        results,
        data,
        table="Table A.6",
        panel="Panel A",
        sample="Excluding coke and petroleum products (ISIC 23)",
        regressors=VAR2,
        main_variable="srct",
        mask=excluding_isic23,
    )
    run_triplet(
        results,
        data,
        table="Table A.6",
        panel="Panel B",
        sample="Immediate impact, excluding ISIC 23",
        regressors=VAR2,
        main_variable="srct",
        mask=excluding_isic23 & (data["year"] < 2012),
    )
    run_triplet(
        results,
        data,
        table="Table A.6",
        panel="Panel C",
        sample="DID, excluding ISIC 23",
        regressors=table5_c,
        main_variable="srct1",
        mask=excluding_isic23,
    )

    return results, wald_tests


# -----------------------------------------------------------------------------
# Output helpers
# -----------------------------------------------------------------------------
def significance_stars(p_value: float) -> str:
    if pd.isna(p_value):
        return ""
    if p_value < 0.01:
        return "***"
    if p_value < 0.05:
        return "**"
    if p_value < 0.10:
        return "*"
    return ""


def build_main_effects(results: Iterable[AregResult]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for result in results:
        if result.main_variable is None or result.main_variable not in result.params.index:
            continue
        variable = result.main_variable
        p_value = float(result.p_values[variable])
        rows.append(
            {
                "table": result.table,
                "panel": result.panel,
                "sample": result.sample,
                "outcome": result.outcome,
                "outcome_label": OUTCOME_LABELS.get(result.outcome, result.outcome),
                "main_variable": variable,
                "coefficient": float(result.params[variable]),
                "std_error": float(result.std_errors[variable]),
                "stars": significance_stars(p_value),
                "formatted": (
                    f"{result.params[variable]:.3f}{significance_stars(p_value)} "
                    f"({result.std_errors[variable]:.3f})"
                ),
                "p_value": p_value,
                "effect_pct": result.effect_pct,
                "effect_interpretation": result.effect_interpretation,
                "nobs": result.nobs,
                "n_clusters": result.n_clusters,
                "within_r2": result.within_r2,
                "dropped_regressors": " ".join(result.regressors_dropped),
            }
        )
    return pd.DataFrame(rows)


def save_results(
    results: Sequence[AregResult],
    wald_tests: Sequence[dict[str, object]],
    output_path: Path,
    metadata: dict[str, object],
) -> None:
    coefficient_frames = [result.coefficient_frame() for result in results]
    model_frames = [result.model_frame() for result in results]
    coefficients = pd.concat(coefficient_frames, ignore_index=True)
    models = pd.concat(model_frames, ignore_index=True)
    main_effects = build_main_effects(results)
    wald = pd.DataFrame(wald_tests)
    metadata_frame = pd.DataFrame(
        [{"key": key, "value": json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value}
         for key, value in metadata.items()]
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.suffix.lower() == ".xlsx":
        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            main_effects.to_excel(writer, sheet_name="main_effects", index=False)
            coefficients.to_excel(writer, sheet_name="all_coefficients", index=False)
            models.to_excel(writer, sheet_name="model_info", index=False)
            wald.to_excel(writer, sheet_name="wald_tests", index=False)
            metadata_frame.to_excel(writer, sheet_name="metadata", index=False)

            # One compact sheet per paper table.
            for table_name, table_df in main_effects.groupby("table", sort=False):
                safe_name = table_name.replace("Table ", "T").replace(".", "_")[:31]
                table_df.to_excel(writer, sheet_name=safe_name, index=False)
    else:
        output_path.mkdir(parents=True, exist_ok=True)
        main_effects.to_csv(output_path / "main_effects.csv", index=False)
        coefficients.to_csv(output_path / "all_coefficients.csv", index=False)
        models.to_csv(output_path / "model_info.csv", index=False)
        wald.to_csv(output_path / "wald_tests.csv", index=False)
        metadata_frame.to_csv(output_path / "metadata.csv", index=False)


def print_key_results(results: Sequence[AregResult]) -> None:
    main = build_main_effects(results)
    key = main[main["table"] == "Table 5"].copy()
    if key.empty:
        return

    print("\nTable 5 — key coefficients")
    print("-" * 82)
    for _, row in key.iterrows():
        effect_text = ""
        if pd.notna(row["effect_pct"]):
            effect_text = f" | impact={row['effect_pct']:.1f}%"
        print(
            f"{row['panel']:<10} {row['outcome_label']:<20} "
            f"{row['formatted']:<20} N={int(row['nobs']):<5}{effect_text}"
        )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reproduce the Stata areg models in codes_final.do using Python."
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=Path("data/mydata.xlsx"),
        help="Input data file (.dta, .xlsx, .xls, .csv, or .parquet).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/python_regression_results.xlsx"),
        help="Output .xlsx file or output directory for CSV files.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)

    if not args.data.exists():
        print(f"ERROR: data file not found: {args.data}", file=sys.stderr)
        return 2

    print(f"Loading data: {args.data}")
    raw = load_data(args.data)
    data = normalize_data(raw)
    print(f"Rows: {len(data):,} | unique id groups: {data['id'].nunique():,}")

    results, wald_tests = reproduce_all(data)

    metadata = {
        "source_data": str(args.data.resolve()),
        "n_rows_source": int(len(data)),
        "n_unique_ids_source": int(data["id"].nunique()),
        "number_of_models": int(len(results)),
        "number_of_wald_tests": int(len(wald_tests)),
        "estimator": "Within-transformed OLS with id fixed effects and id-clustered SE",
        "small_sample_correction": "Stata areg-style, including absorbed FE degrees of freedom",
        "srct2_note": "Reconstructed as srct * treat_num when absent",
    }
    save_results(results, wald_tests, args.output, metadata)
    print_key_results(results)
    print(f"\nSaved results to: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
