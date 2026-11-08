# Iran's 2010 Energy Subsidy Reform: Replication & Continuous-Dose Extension

Macroeconomics course project at Sharif University of Technology (2025–26 academic year). It replicates and extends:

> Zarepour, Z. & Wagner, N. (2023). *How manufacturing firms respond to energy subsidy reforms? An impact assessment of the Iranian Energy Subsidy Reform.* **Energy Economics**, 124, 106762. [doi:10.1016/j.eneco.2023.106762](https://doi.org/10.1016/j.eneco.2023.106762)

In December 2010, Iran raised domestic energy prices several-fold. The original paper uses a difference-in-differences (DiD) design on a 4-digit industry × province panel. It finds that the reform cut manufacturing output, value-added and operating surplus by about 3, 7 and 9%.

The project has two parts, listed below.

1. **Replicates** the paper's fixed-effects estimates in Python, matching the published Stata results.
2. **Extends** the design. It replaces the binary energy-sensitive vs. less-sensitive comparison with a *continuous* measure of each unit's pre-reform energy exposure. It then asks how much of the headline result depends on the specification and on how standard errors are computed.

## Key findings

**Replication.** Our Python code reproduces the published binary DiD estimates, shown below.

| Outcome | Post × Treat | Effect | p (unit-clustered) |
|---|---|---|---|
| Output | −0.034 | −3.35% | 0.043 |
| Value-added | −0.076 | −7.30% | 0.010 |
| Operating surplus | −0.096 | −9.12% | 0.060 |

These estimates compare energy-sensitive groups with less-sensitive ones, so they measure relative effects and not the effect of the reform compared with no reform.

**Specification sensitivity.** The paper controls for inputs the reform itself changed, including energy use, and handles common shocks such as the 2012 sanctions with an oil-export proxy and a linear trend. We keep this setup in the replication, because four year dummies on a five-year panel would absorb much of the post-reform change. The cost is that the baseline stays open to errors in how common shocks are modelled. Replacing the trend and the proxy with year fixed effects turns the output coefficient positive and insignificant (+0.027, p = 0.28). Dropping the input controls as well makes it +0.18.

**Continuous dose.** Exposure is measured as each unit's pre-reform (2009–10) energy cost share of output. With unit, ISIC2 × year and province × year fixed effects, a one-SD higher exposure is associated with 0.051 log points higher relative output after the reform. The effects on value-added (+0.012) and operating surplus (+0.050) are imprecise.

**Inference.** Treatment varies at the industry level, but the paper clusters standard errors at the unit level. The p-value for the output dose effect ranges from 0.009 to 0.222, depending on the method.

| Inference | p-value |
|---|---|
| Cluster by unit | 0.015 |
| Cluster by ISIC2 industry | 0.194 |
| Two-way (ISIC2 + province) | 0.222 |
| Wild cluster bootstrap-t (ISIC2, 999 reps) | 0.009 |

**Mechanisms.**

- When the direct and indirect doses enter the same regression, only direct exposure predicts output, while the indirect coefficient is larger for value-added and operating surplus.
- Losses are larger in low and medium-low technology groups, and smaller for high-investment-intensity units than in the full sample.
- Of the adjustment margins we examined, only raw-materials spending responds significantly (+0.108).

**Limitations.**

- The panel has only two pre-reform years, so the pre-trend check rests on a single contrast.
- The technology and investment-intensity measures are defined at the industry–province level, so they show differences in ability to adjust, not causal effects.

## Summary of the report

### Motivation

The reform covered the whole economy, so even the control units were treated, only less strongly. The report describes three channels for the shock. In the direct channel, firms pay more for fuel and electricity, and output and operating surplus fall if output prices cannot adjust at once. In the indirect channel, energy-intensive suppliers raise the prices of steel, cement, chemicals and other intermediate inputs. A firm with a small energy bill can therefore still face a large shock. In the demand channel, higher household energy costs and inflation reduce real purchasing power. We treat demand as background and do not identify it.

### Data and measures

A unit is a 4-digit ISIC industry in one province, included in a year only if at least two firms with ten or more workers operate there. Of the 1,336 units, 123 have no pre-reform data, and the dose sample has 1,213 units and 5,426 observations. The direct dose is a unit's average energy cost share of output before the reform. The indirect dose uses the spending shares of raw materials, packaging and non-durable tools instead, so it captures dependence on intermediate inputs rather than embodied energy. Both doses are winsorized at the 1st and 99th percentiles and standardized. Technology uses the OECD industry classes, and investment intensity is gross fixed capital formation over output, with 0.06 as the cutoff.

### What we did

The continuous dose model adds ISIC2 × year and province × year fixed effects to unit fixed effects. In one version, both doses enter together. The event study replaces the single post-reform term with dose × year terms and leaves out 2010. We also split the sample by technology and investment intensity and regressed six adjustment margins on the dose.

### What we found

Relative to 2010, the 2009 dose coefficients are 0.024 for output, 0.045 for value-added and 0.020 for operating surplus (p = 0.382, 0.124 and 0.644). No large pre-trend appears, but one contrast cannot prove parallel trends.

With both doses included, only direct exposure predicts output (0.0606, p = 0.024). For value-added and operating surplus the indirect coefficient is larger, and equal slopes are rejected for value-added (p = 0.0006). The doses are correlated at −0.522, which makes them hard to interpret separately.

Low and medium-low technology groups lose about 7.5, 13.2 and 14.9% in output, value-added and operating surplus, while losses in higher-technology groups are smaller and not significant. The low-technology group has only 59 control units against 905 treated, though. High-investment units lose 4.3, 9.8 and 10.6%, less than in the full-sample before–after model, but these estimates are imprecise. Capital formation does not respond to the dose (−0.0182, p = 0.695).

### What the report concludes

The report sees the binary and continuous results as answers to different questions. The positive output dose slope is not a benefit of exposure and may reflect adaptation, cost pass-through, product mix or an omitted confounder. Because energy, raw materials, labor costs and capital formation all react to the reform, the replication estimates a controlled direct effect rather than a total effect.

For policy, the report says reform design should consider both a firm's own energy use and its reliance on energy-intensive suppliers. It proposes gradual, pre-announced price increases and temporary finance for efficiency upgrades, mainly for low-technology and capital-constrained producers, but the project does not test them. Stronger claims would need longer pre-reform panels and firm-level data.

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

Run the notebook from the repository root, top to bottom; a full run takes about a minute. Before the extension runs, a **replication check** confirms that the custom estimator reproduces the paper's Table 5 Panel C. The wild bootstrap uses a fixed seed, so every run gives the same results.

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
