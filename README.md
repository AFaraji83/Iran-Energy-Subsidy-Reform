# Iran's 2010 Energy Subsidy Reform: Replication & Continuous-Dose Extension

Macroeconomics course project at Sharif University of Technology (2025–26 academic year). It replicates and extends:

> Zarepour, Z. & Wagner, N. (2023). *How manufacturing firms respond to energy subsidy reforms? An impact assessment of the Iranian Energy Subsidy Reform.* **Energy Economics**, 124, 106762. [doi:10.1016/j.eneco.2023.106762](https://doi.org/10.1016/j.eneco.2023.106762)

In December 2010, Iran raised domestic energy prices several-fold. The original paper uses a difference-in-differences (DiD) design on a 4-digit industry × province panel. It finds that the reform cut manufacturing output, value-added and operating surplus by about 3, 7 and 9%.

This project does two things:

1. **Replicates** the paper's fixed-effects estimates in Python, matching the published Stata results.
2. **Extends** the design. It replaces the binary energy-sensitive vs. less-sensitive comparison with a *continuous* measure of each unit's pre-reform energy exposure. It then asks how much of the headline result depends on the specification and on how standard errors are computed.

## Key findings

**Replication.** The binary DiD estimates are reproduced exactly:

| Outcome | Post × Treat | Effect | p (unit-clustered) |
|---|---|---|---|
| Output | −0.034 | −3.35% | 0.043 |
| Value-added | −0.076 | −7.30% | 0.010 |
| Operating surplus | −0.096 | −9.12% | 0.060 |

These are *relative* effects: energy-sensitive groups compared with less-sensitive ones. They are not the effect of the reform compared with no reform.

**Specification sensitivity.** The paper controls for inputs the reform itself changed, including energy use. It also has no year fixed effects, so the 2012 sanctions are absorbed only by an oil-export proxy and a linear trend. Adding year fixed effects turns the output coefficient positive and insignificant (+0.027, p = 0.28). Dropping the input controls as well makes it +0.18.

**Continuous dose.** Exposure is measured as each unit's pre-reform (2009–10) energy cost share of output. With unit, ISIC2 × year and province × year fixed effects, a one-SD higher exposure goes with a **less negative** relative output response after the reform (+0.051 log points). The effects on value-added (+0.012) and operating surplus (+0.050) are imprecise.

**Inference matters.** Treatment varies at the industry level, but the paper clusters standard errors at the unit level. The p-value for the output dose effect changes a lot with the method:

| Inference | p-value |
|---|---|
| Cluster by unit | 0.015 |
| Cluster by ISIC2 industry | 0.194 |
| Two-way (ISIC2 + province) | 0.222 |
| Wild cluster bootstrap-t (ISIC2, 999 reps) | 0.009 |

**Mechanisms.**

- **Direct vs. indirect exposure:** when both enter the same regression, indirect exposure through intermediate inputs matters at least as much as direct energy costs for value-added and operating surplus.
- **Adjustment margins:** of the margins examined, only raw-materials spending responds significantly (+0.108).

**Limitations.**

- The panel has only two pre-reform years, so the pre-trend check rests on a single contrast.
- The technology and investment-intensity measures are defined at the industry–province level, so they show differences in ability to adjust, not causal effects.

## Repository structure

```
.
├── energy_subsidy_reform.ipynb        # main notebook: stats engine, replication, extension, figures
├── data/
│   └── mydata.xlsx                    # 4-digit ISIC × province panel, 2009–2013 (5,636 obs, 1,336 units)
├── scripts/
│   └── replicate_paper.py             # command-line replication of the paper's tables
├── results/
│   ├── python_regression_results.xlsx # replication tables (Tables 5–8 and appendix)
│   └── extension_results.xlsx         # all extension tables
├── figures/                           # event study, dose-response, adjustment margins, inference, trends
├── report/
│   ├── report.pdf                     # final paper (Persian)
│   └── report.tex                     # LaTeX source (XeLaTeX + xepersian)
├── slides/
│   └── presentation.pdf               # final presentation (English)
└── docs/
    └── proposal.pdf                   # project proposal (Persian)
```

## How to run

```bash
pip install -r requirements.txt
jupyter notebook energy_subsidy_reform.ipynb
```

Run the notebook from the repository root, top to bottom; a full run takes about a minute. Before the extension runs, a **replication check** confirms that the custom estimator reproduces the paper's Table 5 Panel C. The wild bootstrap is seeded, so results are fully reproducible.

To reproduce only the paper's tables:

```bash
python scripts/replicate_paper.py          # writes results/python_regression_results.xlsx
```

The estimator works like Stata's `areg y x, absorb(id) vce(cluster id)`. It applies a within transformation, uses clustered sandwich standard errors and the same small-sample correction, so the standard errors match the published ones.

To rebuild the report, compile `report/report.tex` with XeLaTeX. You need the `xepersian` package and either the XB Niloofar or the Noto Naskh Arabic font.

## Data

`data/mydata.xlsx` is the industry × province panel used by Zarepour & Wagner (2023), built from Statistical Center of Iran (SCI) manufacturing census data. The article is open access under CC BY 4.0. Please cite the original paper if you use the data.

## Tools

Python · pandas · NumPy · statsmodels · SciPy · mpmath · matplotlib · Jupyter · LaTeX

## Team

- Alireza Faraji
- Pardis Rahimi Nasr
- Amyar Siosemardeh
