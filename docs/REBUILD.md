# Rebuild implementation notes

These notes describe the original 2.0 rebuild. The subsequent 2.1 trial and 2.2 cost/service revision, including all measured improvements and service losses, are recorded in [OPTIMIZATION_HISTORY.md](OPTIMIZATION_HISTORY.md). Version 2.2 is the current local default; the original research mode remains reproducible.

## Scope

AeroPlan 2.0 adapts the original research protocol into a runnable local application. The public package supplies synthetic data and frozen numerical evidence independently of the coursework documents.

## Implementation principles

The application uses explicit feasibility rules, matched comparison populations, immutable effective configurations, prior-only inputs for policy selection, and complete row exports. All thresholds are declared in the AeroPlan study configuration.

The original research objective remains unchanged. An unfavorable result cannot silently promote a different policy or become a positive savings claim.

## Data adaptation

The actual four CSVs are bundled and imported. supplier_id_primary maps to the part's preferred supplier, while purchase-order supplier IDs retain their actual source values. The archive and each CSV are hashed. All 1,800 complete site-part series are evaluated. No lexicographic 60-series default remains.

Cohorts cover site, part family, criticality, supplier risk, repairability and training demand frequency. Demand-weighted fill is calculated from total filled units divided by total demand, not the mean of series fill rates. Class A outcomes remain visible even when the portfolio service test passes. Cohort filtering is descriptive and does not rerun portfolio hypothesis tests.

The dataset does not contain customer, order-line basket or maintenance work-order identifiers. Genuine market-basket analysis is therefore not implemented. Site-week coincidence is not labeled a purchase basket. Part family is not a substitution relationship.

## Numerical contract

The simulation serves existing backorders before current demand, places orders after demand, and makes orders placed in week t available at week t + sampled lead weeks + 1. It starts from the common training cutoff, subtracts blocked stock from on-hand, and assumes an empty starting pipeline. Only current demand filled immediately counts toward unit fill. Zero-demand service is undefined.

Holding cost uses ending usable on-hand times unit cost times the annual carrying rate divided by 52. Purchasing, pipeline, shortage, expedite, disposal and repair costs are not modeled. They must not be described as included total operating cost.

Training receipts determine empirical lead times, with site-part, part-pool and nominal fallback. A recorded receipt date does not prove complete quantity delivery. Full receipt remains the explicit simulation assumption for parity. The observed short-quantity POs require a separate versioned model with residual-order assumptions before any partial-receipt simulation can be supported.

Policy identity and buffer choice are fixed before test evaluation. Rolling forecasts can consume previously observed test demand without reselecting models. Thirty replications share each site-part/order-week lead draw between baseline and selected policies. They quantify conditional lead uncertainty, not uncertainty across independent real organizations.

## Operational boundary

Forecasts and stock targets are planning outputs. They are not procurement instructions: the source has no reliable current open-pipeline event ledger, live supplier commitments, repair returns or safety approvals. The UI does not fabricate an executable purchase quantity.

The application is loopback-only and does not place orders or submit coursework. Normal operation is offline after installing the pinned dependencies in a dedicated virtual environment.

## Next extensions

1. Versioned receipt-event and residual-quantity model, separately validated.
2. Real stock/pipeline adapter with as-of consistency before actionable replenishment quantities.
3. Optional operational policy selection that can retain a matched baseline when a candidate fails explicit cost and service gates. It must be evaluated on fresh data, not retroactively substituted into the paper's protocol.
4. Basket analysis only after authentic basket/work-order keys and timestamps become available.

A new objective or data extension must create a new protocol version and leave existing run records intact.
