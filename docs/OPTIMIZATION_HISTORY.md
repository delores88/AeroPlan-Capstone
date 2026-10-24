# AeroPlan version comparison and portfolio research notes

Public-repository reading note: this log preserves the historical development sequence. Paths beginning with `verification/` and old author-side tools refer to the original audit workspace and are not prerequisites for running this repository. The published primary and sensitivity exports are in `evidence/improved-run.zip` and `evidence/stress-run.zip`; comparison CSVs, SQL, plots, and screenshots are also in `evidence/`. Use the root README for the independent setup and exact-source replay procedure.

## Purpose and evidence boundary

This record documents the transition from AeroPlan 2.0's reproduction of the Module 6 protocol through the AeroPlan 2.1 cost/service trial to the more conservative AeroPlan 2.2 selection. It is preparation material for the Module 7 paper and Module 8 non-video deliverables, not a replacement for either assignment.

The original experiment, paper, and saved runs remain unchanged. Its result was unfavorable for the joint hypothesis: selected policies increased holding cost by 9.9587% while improving portfolio immediate fill by 0.0773 percentage points. A later improvement must not be substituted into that original test or described as having been planned before its results were known.

All results are conditional simulations using a synthetic dataset. The currency is unspecified, so monetary quantities are source cost units. Holding cost excludes purchase, pipeline, shortage, expedite, disposal, and repair costs. No result is realized organizational savings or evidence of aerospace safety compliance.

## Matched comparison scope

- Six sites, 300 parts, and all 1,800 site-part series.
- 156 weekly observations: 78 training weeks, 52 validation weeks, and 26 evaluation weeks.
- Training and validation are the only observations available to the policy selector. The final 26 weeks have previously been examined and are therefore an exploratory evaluation for the redesign.
- The baseline remains an eight-week moving average with buffer multiplier 1.645.
- Initial usable stock, starting backlog, empty initial pipeline, receipt timing, demand sequence, unit costs, 24% annual carrying rate, and paired lead-time draws remain matched.
- Service is immediate units filled divided by demanded units. The 95% absolute target and the one-percentage-point baseline tolerance remain different checks.
- Locations are independent inventory points. There are no assumed transfers, pooled stock, substitution permissions, or fabricated order baskets.

## EDA findings that motivated the change

The first selection procedure minimized forecast MAE before searching inventory buffers. It did not compare inventory cost across all models. That objective mismatch is a design concern; the observed outcome is consistent with it but does not isolate a causal effect of the forecast-selection step.

EDA of original results found 928 series with increased cost. Gross increases were approximately 1.231 million cost units, partially offset by approximately 0.685 million in decreases. For 612 series, the baseline cost no more and provided at least as much immediate fill. Large buffers of at least 4 contributed approximately 530,000 cost units to the increase while attaining about 99.65% to 100% cohort fill. Class A fill fell from 97.7962% to 96.5720%, a 1.2242-percentage-point decline, while its holding cost increased about 4.50%.

There were 291 series whose across-replication mean fill was below 95%, 1,508 at or above 95%, and one with no evaluation demand. This count differs from the original mean of 1,503.7667 target-attaining series per replication. Counting series after averaging their fill rates is not the same as averaging per-replication target counts.

Average weekly demand declined from 4,039.44 in validation to 3,453.92 in evaluation, a 14.50% decrease. This distribution change limits interpretation of validation performance. The redesign does not use the observed decline as a test-period adjustment factor.

Detailed evidence: `verification/improvement/eda_summary.json`, `eda_series.csv`, `eda_groups.csv`, and `eda_top_cost_increases.csv`. The diagnostic script is `tools/analyze_policy.py`.

## Design changes

The cost-and-service mode evaluates model-and-buffer combinations together and includes the exact baseline as an explicit fallback. Candidate evaluation uses several fixed validation lead-time seeds with common draws. This is a finite candidate search under stated service safeguards, not a claim of a universally optimal inventory policy.

Candidate evidence and chosen policies are frozen before the evaluation period is simulated. Effective configuration, source identity, input hashes, and validation evidence are retained with the run. The original forecast-accuracy selection remains separately available, and old configurations continue to execute their original algorithm.

## Forecast uncertainty

Future rows expose `yhat`, `yhat_lower`, and `yhat_upper`. The UI draws a light area between the lower and upper bounds. These are nominal 95% empirical prediction intervals for future weekly demand, not confidence intervals for the mean.

Each horizon uses historical rolling-origin forecast errors whose outcomes were observable before the current origin. The method uses a finite-sample-adjusted absolute-error quantile, clips the lower bound at zero, and returns unavailable bounds when calibration is insufficient. Serial dependence, model selection, and distribution changes prevent a guaranteed 95% coverage claim. Future bands calibrated using the latest observed history do not establish historical test-period coverage. See `docs/FORECAST_INTERVALS.md` for exact details.

The general distinction between future observations and point estimates, and the need for chronological forecast evaluation, are supported by Hyndman and Athanasopoulos, *Forecasting: Principles and Practice* (3rd ed.), chapter 5: https://otexts.com/fpp3/toolbox.html. This does not make the book a source for our particular numerical results or establish that this interval algorithm has guaranteed coverage.

## Reuse in Module 7

Preserve the original hypothesis result, then introduce the redesign as an exploratory extension motivated by its limitations and EDA. Explain the objective, candidate space, validation safeguards, selection freeze, paired comparison, subgroup outcomes, sensitivity analysis, and remaining operational limitations. Report actual holding-cost and service changes with their units, denominators, and evaluation window.

The final paper still needs the required template, combined Module 5 and 6 content, a separate-page abstract, at least 5,250 words, hypotheses, literature, tool discussion, security/privacy/ethics, and interpretation of unsupported as well as supported hypotheses. The brief says 6 to 10 credible references while the highest sources rubric says at least 10; 10 well-integrated credible sources satisfies both numerical statements. Existing source validation does not remove the need to verify that every final citation supports its claim.

The saved SQL queries and SQLite comparison database supply an additional analytical tool alongside the Python simulation and plotting. Describe the actual SQL aggregation and checks, not merely SQLite's use as app storage. This supports the rubric's two-or-three-tool criterion without counting every Python package as an independent tool.

## Reuse in Module 8 non-video materials

Use the cost/service comparison figure, site and criticality figure, and verified app screenshots to explain the problem, first result, diagnosis, revised decision rule, and measured tradeoffs. Keep the narrative directed at management: what improved, what did not, why the evidence is bounded, and what data would be needed for deployment.

The non-video deliverables still require 8 to 10 slides with detailed speaker notes, additional visualizations, a reference slide with 6 to 10 credible sources available through the CSU Global Library, and the separate project code/screenshots/GitHub-link document with a title page. Do not claim library retrieval or a published GitHub project until verified. Publication has not been performed. Module 7 instructor feedback must be incorporated when available. The separate oral rubric mentions a self-evaluation form; its format remains unprovided and is outside these non-video preparation notes.

## Artifacts and preservation

`verification/improvement/pre-improvement-source.zip` preserves the source before this change. `original-integrity.json` records hashes for 24 original files and both original saved runs. `tools/preserve_original.py` checks them without modifying the originals. Each new run retains its own source, configuration, raw data, selected policies, and validation-selection evidence.

The measured comparison and verification receipt below complete this development pass.

## Local upgrade environment

The final updated app uses http://127.0.0.1:8767 and `workspace-v22`. The original workspace/process on port 8765 and the 2.1 trial on port 8766 were left intact because automatic approval review blocked stopping the original process. The new workspaces were created with SQLite's backup API and copies of immutable dataset/run artifacts. This separates new runs while retaining every completed run for comparison. No customer data, Canvas access, cloud computation, or publication was involved.

## Intermediate trial: 2.1 / joint-cost-service-v1

Run `fe8633e81a64` evaluated 66 candidates across five validation seeds, then 30 paired evaluation replications. It selected the lowest-cost candidate satisfying a 95% mean fill floor, no more than 0.5 percentage-point mean loss and one percentage-point worst-seed loss relative to baseline; class A had zero validation-loss tolerance. Every choice and its full candidate score evidence was frozen before evaluation. All 1,800 choices were independently reconstructed and verified.

Holding cost fell to 4,962,237.34 cost units, a 9.5093% reduction versus baseline and a 17.7048% reduction versus the original selected policies. Portfolio fill was 95.9653%, down 0.9289 percentage points versus baseline. Thus the original portfolio cost, one-percentage-point noninferiority, and 95% target checks all passed in this exploratory comparison.

However, criticality-A fill fell from 97.7962% to 95.0526%, a 2.7436-percentage-point decline. Its zero-loss validation safeguard did not generalize. Five of six sites lost more than 0.5 percentage points and four lost more than one point. Portfolio stockout site-part-weeks rose from 875.53 to 1,308.30, an increase of about 49.43%. This trial was not accepted as the final operational default. Portfolio success did not imply satisfactory subgroup service.

The trial remains in the saved run history. Its preserved standalone artifacts are `revision1-run.json`, `revision1-run.zip`, `revision1-http-verification.json`, `revision1-optimization-verification.json`, and the `revision1/` SQL/figure bundle under `verification/improvement/`.

## Conservative revision: 2.2 / joint-cost-service-v2

This second revision was designed after viewing the trial and is explicitly post hoc. It does not restore a fresh confirmatory holdout. The decision rule is applied to whole predefined groups and validation measurements, not to hand-picked test losers.

Class A retains the exact baseline model and buffer. Under the current separable simulator and matched inputs, this preserves its baseline inventory and service outcomes. That is a conservative policy restriction, not an assertion that the baseline is optimal or safe for every real aerospace use.

Other parts must show strictly lower mean validation holding cost, meet the absolute mean-fill target, and show no fill loss against baseline on any of the five validation lead paths. The same no-loss requirement is checked in each chronological validation half, with no mean holding-cost increase in either half. The split is fixed at index 104: the early half uses indices 78 through 103 after the existing series-specific warm-up; the late half uses 104 through 129. Inventory evolves continuously without resetting at the split. Undefined block service requires fallback.

The stopping rule was fixed before this revision's evaluation: run this revision once on the primary setting and once with 25% longer evaluation leads, then report both results without further retuning in this pass. All candidates, successful or unsuccessful, remain represented in the frozen score evidence. The preserved first trial prevents selective reporting of only a favorable final result.

## Final measured results

Primary run `47b10bd460d3` uses 30 paired lead paths, seeds 10001 through 10030. All figures below are means across those replications, except the fixed 89,802 units of evaluation demand. Costs are source cost units over the same 26 weeks, not dollars or annual savings.

| Measure | Baseline | Original 2.0 | Trial 2.1 | Revised 2.2 |
| --- | ---: | ---: | ---: | ---: |
| Holding cost | 5,483,697.15 | 6,029,804.48 | 4,962,237.34 | 5,221,980.47 |
| Immediate unit fill | 96.8942% | 96.9716% | 95.9653% | 96.0963% |
| Stockout site-part-weeks | 875.53 | 1,032.67 | 1,308.30 | 1,198.20 |
| Ending backlog, units | 482.27 | 364.97 | 507.67 | 523.67 |
| Class A immediate fill | 97.7962% | 96.5720% | 95.0526% | 97.7962% |

The final selection saves 261,716.67 cost units (4.7726%) versus baseline and 807,824.01 (13.3972%) versus the original selected policies. Overall service declines 0.7980 percentage points versus baseline and 0.8753 points versus the original selection. The portfolio cost test, one-percentage-point service-tolerance test, and separate 95% service target pass under the existing conditional simulation procedure. This does not establish general operational superiority.

The revised rule adopts 611 policies and retains the baseline for 1,189 series, including all 288 Class A series. Class A equality is a deliberate restriction. Thirty-five Class A series still average below 95%, exactly as under baseline. Zero validation service loss did not generalize to all other series. The 611 adopted series alone attain only 94.0932% fill compared with 96.9229% under baseline; retained series keep aggregate fill above 95%. Across the full population, 342 series average below 95%, versus 258 under baseline and 291 under the original selection. One zero-demand series has undefined fill. These are counts after averaging each series across replications, not average per-replication target counts.

Every site reduces holding cost and exceeds 95% aggregate fill, but every site loses service against baseline. SITE01 loses 1.2347 percentage points and SITE05 loses 1.1288 points. These subgroup differences exceed the portfolio's numerical tolerance descriptively; they are not separately preregistered site hypothesis tests. Stockout site-part-weeks increase 36.85% versus baseline and 16.03% versus the original selection. The selected model's MAE is 1.49506 units, slightly worse than the original 1.49278 and slightly better than the MA(8) baseline 1.50208. Lower inventory cost must not be called a universal forecast-accuracy improvement.

## Anticipated longer-lead sensitivity

Run `793782ebd1c2` scales evaluation lead times by 1.25 and retains exactly the same policy rows, policy hash, and validation-evidence hash as the primary run. It changes both sampled receipts and the mean/standard deviation used in target-stock calculation. Consequently this tests anticipated longer leads with stock targets responding, not an unexpected disruption with fixed stock targets.

| Measure | Stress baseline | Revised 2.2 stress |
| --- | ---: | ---: |
| Holding cost | 6,478,304.83 | 6,150,966.17 |
| Immediate unit fill | 97.0565% | 96.2032% |
| Stockout site-part-weeks | 828.67 | 1,144.00 |
| Ending backlog, units | 431.47 | 500.77 |
| Class A immediate fill | 98.2254% | 98.2254% |

Stress savings are 327,338.66 cost units (5.0528%), with a service decline of 0.8533 percentage points. SITE01 and SITE05 again lose more than one point; 330 individual series average below 95%. All 30 observed paired replications save cost and lose less than one service point, but they reuse the same demand history. The service-difference Shapiro-Wilk p value is .03544, so the normality warning remains relevant to the paired t interpretation. These are descriptive and conditional findings, not distribution-free evidence or independent demand replications.

## Verification and reproducibility

- The full suite passed 98 tests; the original numerical comparison still passes 22 categories.
- The independent primary audit passed 23 groups and 1,907,751 assertions, reconstructing every selected policy from the frozen candidate scores, checking 23,400 future intervals, protected Class A endpoints, source identity, and paired inference.
- The sensitivity audit passed 25 groups and 1,909,931 assertions. Its baseline matches the retained original longer-lead results at portfolio, series, weekly, and all 30 replication levels. Selection evidence matches the primary run exactly.
- SQLite independently aggregated all four versions; a second audit checked all 576 reported aggregate cells. Queries and the 7,200-row analytical database are retained.
- Sixteen live HTTP workflow checks passed. The primary exported source and raw input were extracted and actually rerun; the replay matched the exported summary with exit status zero.
- Original artifacts and saved runs remain protected by the integrity receipt. The latest browser evidence and package check are listed in `VERIFICATION.md`.

Primary export: `verification/improvement/improved-run.zip`; stress export: `stress-run.zip`; original export and source snapshots remain in the same evidence folder. The primary export SHA-256 is `f87545bd061d44cdb78eaed8c83971d3e3bd4a7b0bd0c39df987ef4b7c81ae01`.

## Starting point for the next development pass

The useful gain is a joint model/buffer cost search with explicit baseline fallback, protected criticality, inspectable selection evidence, and visible forecast uncertainty. The unresolved problem is service resilience outside the observed validation demand sequence. Five lead seeds add supply variation but do not create five independent demand histories. Of 116 series losing more than five service points, 99 had perfect mean validation fill. Initial inventory and the transition into evaluation are plausible contributors requiring separate tests; they have not been established as causal explanations.

Next steps should be specified before any further evaluation: multiple rolling demand origins, burn-in and initial-stock sensitivity, rare-spike demand stresses, and explicit pipeline/stock adequacy at the validation boundary. Reserve genuinely new data for confirmation. Require site-level and adopted-policy service acceptance in addition to a portfolio average. For live replenishment, obtain an as-of inventory and open-order ledger, partial-receipt rules, supplier capacity, repair returns, and actual shortage/expedite costs. Until then, the app provides better constrained planning analysis, not executable procurement or proof of global optimality.

Figures for later use are `verification/improvement/version_cost_service.png` and `version_cohort_service.png`, with corresponding PDF exports. Detailed diagnostics are under `verification/improvement/optimized_v2_eda/`. The revised result is an exploratory extension to the original research, not a replacement for its unfavorable result.
