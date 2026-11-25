# Evaluation results

Generated 2026-11-25 23:04:08 +0900 by `python -m callfirst.train` (2000 patient-level bootstrap resamples, seed 20261204). Protocol: [docs/PROTOCOL.md](../docs/PROTOCOL.md).

## Data

101,766 encounters → 99,340 after exclusions (69,987 patients). SHA-256 `0689e7ec031237dc…`.

| Split | Encounters | Patients | 30-day readmission |
|---|---:|---:|---:|
| train | 59,391 | 41,991 | 11.2% |
| valid | 20,098 | 13,998 | 11.8% |
| test | 19,851 | 13,998 | 11.5% |

## Model selection (validation split only)

| Model | Setting | Validation AUROC |
|---|---|---:|
| Logistic regression | C=0.01 | 0.6678 |
| Logistic regression | C=0.1 | 0.6674 |
| Logistic regression | C=1.0 | 0.6673 |
| Gradient boosting | lr=0.05, leaves=15 | 0.6680 |
| Gradient boosting | lr=0.05, leaves=31 | 0.6629 |
| Gradient boosting | lr=0.1, leaves=15 | 0.6607 |
| Gradient boosting | lr=0.1, leaves=31 | 0.6524 |

Boosting − logistic = +0.0001 (rule: boosting only if ≥ +0.01). **Deployed: Logistic regression**, calibrated with isotonic regression on validation.

## Primary result: the coordinator can call 10% of discharges

| Ranking | Calls | Readmissions reached per 100 calls (95% CI) | Share of all readmissions reached (95% CI) | Nurse-hours per readmission reached* |
|---|---:|---:|---:|---:|
| Random order | 1,985 | 11.5 (10.9–12.1) | 10.0% (10.0–10.0) | 2.9 |
| Prior admissions only (post-hoc) | 1,985 | 24.2 (21.6–27.0) | 21.1% (19.3–22.9) | 1.4 |
| LACE index (baseline) | 1,985 | 17.2 (15.4–18.9) | 14.9% (13.6–16.3) | 1.9 |
| Logistic regression ✔ | 1,985 | 26.0 (23.4–28.7) | 22.6% (20.9–24.4) | 1.3 |
| Gradient boosting | 1,985 | 27.0 (24.3–29.8) | 23.4% (21.5–25.3) | 1.2 |

\* Assumes 20 minutes per call (stated assumption, not measured).

Paired difference against LACE (same bootstrap resamples):

| Ranking | Δ readmissions per 100 calls (95% CI) | Δ AUROC (95% CI) | Resamples where it beats LACE |
|---|---:|---:|---:|
| Logistic regression | +8.9 (6.7–11.1) | +0.091 (0.075–0.106) | 100.0% |
| Gradient boosting | +9.8 (7.4–12.3) | +0.098 (0.082–0.113) | 100.0% |
| Prior admissions only (post-hoc) | +7.1 (4.7–9.5) | +0.031 (0.014–0.049) | 100.0% |

Paired difference against prior admissions only (same bootstrap resamples):

| Ranking | Δ readmissions per 100 calls (95% CI) | Δ AUROC (95% CI) | Resamples where it beats prior admissions only |
|---|---:|---:|---:|
| Logistic regression | +1.8 (0.5–3.1) | +0.059 (0.051–0.068) | 99.5% |
| Gradient boosting | +2.7 (1.3–4.1) | +0.067 (0.056–0.077) | 100.0% |

## All capacities

| Ranking | Top 5%: per 100 calls | Top 10%: per 100 calls | Top 20%: per 100 calls | Top 30%: per 100 calls | AUROC (95% CI) | AUPRC |
|---|---:|---:|---:|---:|---:|---:|
| Random order | 11.5 | 11.5 | 11.5 | 11.5 | 0.500 (0.500–0.500) | 0.115 |
| Prior admissions only (post-hoc) | 29.4 | 24.2 | 19.9 | 17.8 | 0.611 (0.597–0.626) | 0.184 |
| LACE index (baseline) | 18.2 | 17.2 | 16.0 | 14.9 | 0.580 (0.566–0.593) | 0.144 |
| Logistic regression | 29.8 | 26.0 | 21.8 | 19.6 | 0.670 (0.657–0.684) | 0.215 |
| Gradient boosting | 32.5 | 27.0 | 22.2 | 19.7 | 0.677 (0.664–0.690) | 0.230 |

## Calibration of the deployed model (test split)

Brier score 0.0975 (predicting the training prevalence for everyone: 0.1018). Mean predicted risk 11.8%, observed 11.5%.

| Decile | Mean predicted | Observed | n |
|---:|---:|---:|---:|
| 1 | 4.1% | 4.0% | 1,986 |
| 2 | 5.2% | 5.0% | 1,985 |
| 3 | 6.7% | 6.7% | 1,985 |
| 4 | 8.7% | 9.1% | 1,985 |
| 5 | 9.4% | 8.7% | 1,985 |
| 6 | 11.3% | 11.0% | 1,985 |
| 7 | 12.8% | 12.1% | 1,985 |
| 8 | 15.5% | 14.4% | 1,985 |
| 9 | 18.2% | 18.5% | 1,985 |
| 10 | 26.4% | 25.5% | 1,985 |

## Subgroups (deployed model, one shared call list = top 10% of the test split)

| Attribute | Group | n | Readmissions | Rate | AUROC model | AUROC LACE | Share called | Share of group's readmissions reached |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| age | under 60 | 6,453 | 660 | 10.2% | 0.720 | 0.615 | 9.0% | 26.8% |
| age | 60-79 | 9,457 | 1,103 | 11.7% | 0.662 | 0.571 | 9.9% | 21.6% |
| age | 80+ | 3,941 | 520 | 13.2% | 0.595 | 0.536 | 11.9% | 19.8% |
| sex | female | 10,680 | 1,241 | 11.6% | 0.679 | 0.577 | 10.5% | 23.4% |
| sex | male | 9,171 | 1,042 | 11.4% | 0.659 | 0.582 | 9.4% | 21.9% |
| race | AfricanAmerican | 3,509 | 400 | 11.4% | 0.690 | 0.568 | 10.4% | 24.2% |
| race | Asian † | 95 | 13 | 13.7% | 0.742 | 0.559 | 7.4% | 15.4% |
| race | Caucasian | 15,128 | 1,776 | 11.7% | 0.663 | 0.580 | 10.2% | 22.6% |
| race | Hispanic † | 369 | 30 | 8.1% | 0.724 | 0.579 | 7.0% | 26.7% |
| race | Other † | 285 | 27 | 9.5% | 0.647 | 0.719 | 7.7% | 11.1% |
| race | unknown † | 465 | 37 | 8.0% | 0.720 | 0.594 | 4.3% | 16.2% |

† Fewer than 50 readmissions: shown, not interpreted.

Environment: Python 3.12.16, scikit-learn 1.9.1, numpy 2.5.5, pandas 3.1.1 on macOS-26.6.2-arm64-arm-64bit. Runtime 86.5 s.
