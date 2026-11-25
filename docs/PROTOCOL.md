# Evaluation protocol

Written and committed **before** the held-out test split was scored. Numbers below are set in
[`callfirst/config.py`](../callfirst/config.py); changing them changes the results.

## Question

A hospital discharges more patients than its care coordinators can phone. If a coordinator can call
only *k%* of today's discharges, does ranking patients with CallFirst reach more patients who will be
readmitted within 30 days than (a) calling at random or (b) ranking with the LACE index, a published
bedside score (van Walraven et al., CMAJ 2010)?

## Data

UCI "Diabetes 130-US Hospitals for Years 1999-2008" (Clore, Cios, DeShazo & Strack, 2014;
DOI 10.24432/C5230J; CC BY 4.0). 101,766 inpatient encounters of adults with diabetes at 130 US
hospitals. The file is verified by SHA-256 in `scripts/download_data.py`.

- Label: `readmitted == "<30"` (readmitted within 30 days of discharge).
- Excluded: encounters ending in death or hospice (`discharge_disposition_id` 11, 13, 14, 19, 20, 21),
  as in Strack et al. 2014, and 3 encounters with unknown sex.
- Not used as model inputs: `race` (kept only to audit errors by group), `payer_code` (insurance,
  a socioeconomic proxy), `weight` (97% missing), encounter and patient IDs.

## Split

Patients (`patient_nbr`) are split 60 / 20 / 20 into train / validation / test with seed
`20261204`. All encounters of a patient stay in one split, so the model is never tested on a patient
it has seen. The test split is used once, after the model and its calibration are frozen.

## Models

1. **Random**: every patient equally likely to be called (expected hit rate = prevalence).
2. **LACE** (baseline): Length of stay, Acuity (emergency admission), Comorbidity (Charlson index from
   the 3 recorded diagnoses, every patient scored as having diabetes), ED visits (prior-year count,
   the dataset has no 6-month count). It needs no training. It is an approximation; see limitations.
3. **Logistic regression** (L2; C chosen on validation from 0.01, 0.1, 1).
4. **Gradient boosting** (scikit-learn HistGradientBoosting; 4 settings chosen on validation).

Rule fixed in advance: deploy logistic regression unless gradient boosting improves **validation**
AUROC by at least 0.01. The deployed model's probabilities are calibrated with isotonic regression
fitted on the validation split.

## Metrics (test split)

- **Primary:** readmissions reached per 100 calls when the coordinator can call the top 10% of
  discharges (positive predictive value at 10% capacity), compared with LACE and random.
- Share of all 30-day readmissions reached at 5 / 10 / 20 / 30% capacity (sensitivity).
- Nurse time per readmission reached, assuming a fixed time per call (a stated assumption, not a
  measurement; see Changes).
- AUROC, AUPRC, Brier score, calibration (10 equal-size bins; observed vs predicted).
- 95% confidence intervals: 2,000 bootstrap resamples of **patients** (all of a patient's encounters
  move together). Model-vs-LACE differences are bootstrapped as paired differences.
- Subgroups (age band, sex, race as recorded): AUROC, share of readmissions reached at 10% capacity,
  and the share of each group that would be called. Groups with fewer than 50 readmissions are
  reported but not interpreted.

Ties in the LACE score at the capacity cut-off are broken by expected value (a tied group contributes
its average readmission rate), so results do not depend on row order.

## What would make the result not useful

- If the CI of the model-minus-LACE difference at 10% capacity includes 0, CallFirst is not shown to
  beat a score a nurse can compute by hand.
- The data is US, 1999-2008, diabetic inpatients only. No claim is made for other populations,
  countries (including Korea), or current practice without local re-validation.

## Changes after the first test run

- 2026-11-25: added a **prior admissions only** ranking (number of hospital admissions in the past
  year) as an extra, post-hoc baseline, because it is the strongest single input and a rule a nurse
  could apply without software. It is labelled post-hoc in the results. Nothing about the deployed
  model, its calibration, or the other baselines was changed.
- 2026-11-25: the assumed time per call was raised from 10 to 20 minutes after reading AHRQ RED
  Tool 5, which puts a post-discharge call at about 20 to 60 minutes. This only rescales the
  nurse-time column; rankings and all other metrics are unchanged. At 60 minutes per call every
  nurse-time figure triples.
