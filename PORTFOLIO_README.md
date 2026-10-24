# Portfolio evidence guide

**AeroPlan: Inventory Forecasting and Replenishment**  
Benjamin Van Dorn  
Colorado State University Global  
MIS581-1: Capstone - Business Intelligence and Data Analytics  
Dr. Goodwin

Repository: https://github.com/delores88/AeroPlan-Capstone

## Start here

The main [README](README.md) provides Windows and macOS/Linux setup, the publisher download URL, archive checksum, UI settings, and exact replay commands. The application and archived replays run independently of the author's computer. The public synthetic archive is bundled, so no account credentials, cloud service, or separate course folder are needed.

First launch imports the 300-part, six-site dataset into a new `workspace-v22/`. It does **not** preload historical analyses. Select **New analysis** to compute results. The normal configuration evaluates all 1,800 site-part series across 156 weeks; the chronological periods contain 78, 52, and 26 weeks.

## Research continuity

The original design selected a forecast by validation error and then searched for a service-constrained buffer. The comparison policy uses an eight-week moving average and fixed buffer of 1.645. Thirty paired lead-time replications support conditional comparisons of holding cost and immediate fill.

The original joint hypothesis requires lower expected holding cost and service noninferiority within one percentage point of baseline. A separate absolute target requires 95% fill. The original selection raises holding cost by 9.96%, despite an overall fill increase of 0.077 percentage points. That joint hypothesis remains unsupported.

The later exploratory revision selects models and buffers jointly using validation cost and service safeguards. It preserves the exact baseline for Class A. Against the matched baseline, the revised primary run reduces holding cost by 4.77% but lowers fill from 96.89% to 96.10%; stockout series-weeks increase by 36.85%. Class A remains at 97.80% fill. Two sites lose more than one percentage point, and the 611 changed policies have approximately 94.09% fill. These adverse outcomes are retained rather than concealed by the portfolio average.

The longer-lead sensitivity uses a factor of 1.25 and yields approximately 5.05% lower cost and 96.20% fill against its matched stressed baseline. Policies remain fixed while lead draws and the moments used to calculate stock targets increase. This is an anticipated-lead scenario, not a shock with unchanged targets.

## Inspect and reproduce the evidence

| Artifact | Purpose |
| --- | --- |
| `evidence/improved-run.zip` | Revised primary run `47b10bd460d3`, with inputs, code, policies, replications, cohorts, and checksums |
| `evidence/stress-run.zip` | Longer-lead run `793782ebd1c2`, its matched baseline, and replay inputs |
| `evidence/comparison_portfolio.csv` | Baseline, original, intermediate trial, and revised portfolio results |
| `evidence/comparison_criticality.csv` | Criticality-level comparison, including protected Class A |
| `evidence/comparison_site.csv` | Site-level service and cost outcomes |
| `evidence/comparison_queries.sql` | SQL used for a separate aggregation review; the CSVs above provide its exported results |
| `evidence/final-overview.png` | Actual application overview for the revised run |
| `evidence/final-forecast.png` | Actual forecast view, historical through December 23, 2024, with nominal prediction bands |

For an exact summary replay, follow README section 5: extract the evidence ZIP, extract its nested `source.zip`, and execute that archived source's `tools/replay_export.py` against the outer ZIP. Success confirms checksum validation and numerical summary equality. It does not claim every output byte or scientific assumption was independently validated. The evidence is separate from the fresh application's run history.

## Interpretation limits

All data are synthetic, and cost currency is unspecified. The revision reused an examined evaluation period, making its results exploratory. The simulator begins with an empty order pipeline, assumes complete receipts, and measures holding cost rather than complete total cost. Nominal 95% forecast intervals do not guarantee coverage or inventory service. Operational adoption requires new observations, validated partial receipts and open orders, site-level acceptance rules, and planner approval.

The code and evidence make the analysis inspectable and reproducible. They do not establish realized savings, production readiness, or safety-critical procurement suitability.
