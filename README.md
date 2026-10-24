# AeroPlan Capstone

AeroPlan is a local inventory-planning application that compares demand forecasts and replenishment policies for a synthetic aerospace supply chain. It provides inventory and forecast views, cohort comparisons, saved evaluations, and reproducible exports.

This repository contains the application, tests, the version-1 synthetic dataset, and archived portfolio evidence. It runs independently of the author's computer. The bundled-data workflow needs no credentials or cloud account. Internet access is needed to obtain the repository and install Python packages; normal analysis runs locally.

**Repository:** https://github.com/delores88/AeroPlan-Capstone

## 1. Get the code

```text
git clone https://github.com/delores88/AeroPlan-Capstone.git
cd AeroPlan-Capstone
```

Alternatively, select **Code > Download ZIP** on GitHub, extract the ZIP, and open a terminal in the extracted folder containing `launch.py` and `requirements.txt`. Do not run the application from inside the ZIP viewer.

## 2. Install and start

Use **Python 3.12** from https://www.python.org/downloads/. The recorded verification environment is Python 3.12.7, NumPy 1.26.4, and SciPy 1.13.1. `requirements.txt` pins the two package versions. These commands create an isolated environment without changing system Python packages.

### Windows PowerShell

Run from the repository folder:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe launch.py
```

After setup, double-clicking `START_APP.cmd` also starts the application using the compatible local environment.

### macOS or Linux

Run from the repository folder with Python 3.12 installed:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python launch.py
```

These commands use the virtual environment explicitly; activation is unnecessary. Windows was the recorded development and verification platform. The macOS/Linux commands use the application's portable Python entry point.

### What to expect

First launch creates `workspace-v22/`, verifies `data/aerospace-v1.zip`, imports its four CSV files, and opens http://127.0.0.1:8767. If the browser does not open, enter that address manually. Keep the terminal open; press **Ctrl+C** in it to stop the server.

**A fresh checkout has no completed analyses.** The dataset is automatically available, but an evaluation must run before results appear. The historical exports in `evidence/` are separate evidence files and are not automatically loaded as UI runs. New run IDs and timestamps differ from archived records.

If port 8767 is in use, stop the other instance or choose another port:

```powershell
.\.venv\Scripts\python.exe launch.py --port 8768
```

On macOS/Linux, use `.venv/bin/python` instead. `--no-browser` suppresses automatic browser opening. `--workspace path/to/new-folder` creates an independent workspace without copying existing analyses. One process may use a workspace at a time. The server binds to the local loopback address; runtime files and logs stay in the workspace.

## 3. Obtain and verify the data

The required archive is already included as **`data/aerospace-v1.zip`**. The source is Roberto Carlos Tientcheu's *Aerospace Supply Chain Performance & Forecasting*, version 1:

https://www.kaggle.com/datasets/robertocarlost/aerospace-supply-chain-performance-and-forecasting

The publisher identifies it as synthetic and MIT licensed. Preserve its attribution and the included license notices with redistributed copies.

| File | Records | Role in AeroPlan |
| --- | ---: | --- |
| `parts_master.csv` | 300 | Part cost, nominal lead time, family, criticality, supplier risk, repairability |
| `supply_chain_history.csv` | 280,800 | Weekly `consumption_qty` demand, site-part keys, inventory, backlog, blocked stock |
| `purchase_orders.csv` | 29,666 | Order/receipt dates and quantities for lead-time and receipt analysis |
| `quality_incidents.csv` | 368 | Quality context retained with the source data |

History spans **January 3, 2022 through December 23, 2024**: 156 weeks, six sites, 300 parts, and **1,800 site-part series**. Currency is unspecified, so monetary results retain source cost units. The publisher's `forecast_qty` fields are excluded from model predictors because their production timestamps are not established.

Expected SHA-256 of the original ZIP:

```text
844ba09645c33a09dbb2be28b9a8f560815ef38929ddcc818b33ecc3df2d8168
```

Verify the bundled file on Windows:

```powershell
Get-FileHash -Algorithm SHA256 .\data\aerospace-v1.zip
```

On macOS/Linux:

```bash
.venv/bin/python -c "from pathlib import Path; import hashlib; print(hashlib.sha256(Path('data/aerospace-v1.zip').read_bytes()).hexdigest())"
```

### Optional independent download

The public version-specific download endpoint is:

https://www.kaggle.com/api/v1/datasets/download/robertocarlost/aerospace-supply-chain-performance-and-forecasting?datasetVersionNumber=1

It was checked as a ZIP response without authentication when this repository was prepared. The bundled archive remains sufficient if the service later changes. Download a separate comparison copy on Windows:

```powershell
curl.exe --fail --location "https://www.kaggle.com/api/v1/datasets/download/robertocarlost/aerospace-supply-chain-performance-and-forecasting?datasetVersionNumber=1" --output data/downloaded-aerospace-v1.zip
Get-FileHash -Algorithm SHA256 .\data\downloaded-aerospace-v1.zip
```

On macOS/Linux:

```bash
curl --fail --location 'https://www.kaggle.com/api/v1/datasets/download/robertocarlost/aerospace-supply-chain-performance-and-forecasting?datasetVersionNumber=1' --output data/downloaded-aerospace-v1.zip
.venv/bin/python -c "from pathlib import Path; import hashlib; print(hashlib.sha256(Path('data/downloaded-aerospace-v1.zip').read_bytes()).hexdigest())"
```

Compare the hash with the value above. Do not replace the bundled file with another version or a recompressed archive: first launch checks the exact ZIP bytes. To evaluate other compatible CSV data, use **Data > Import data**, inspect the preview and mapping, then commit and activate the dataset. Portfolio results apply to the supplied version-1 data only.

## 4. Run the analyses in the interface

Select **New analysis**, enter a name, and use these settings:

| Setting | Revised primary analysis | Original comparison | Longer-lead sensitivity |
| --- | --- | --- | --- |
| Policy selection | Cost and service | Forecast accuracy | Cost and service |
| Service target (%) | 95 | 95 | 95 |
| Annual carrying rate (%) | 24 | 24 | 24 |
| Lead-time factor | 1 | 1 | 1.25 |
| Paired replications | 30 | 30 | 30 |
| Starting random seed | 10001 | 10001 | 10001 |

Select **Start analysis** and wait for completion. These evaluate all 1,800 series, not a 30-part sample. Progress appears in the interface. After completion:

1. Review separate carrying-cost, relative-service, and absolute-target results in **Overview**.
2. Inspect policies and baseline comparisons in **Inventory**.
3. Use **Forecasts** for history, rolling predictions, the 13-week forecast, and nominal 95% prediction bands.
4. Group **Cohorts** by criticality and site to reveal effects hidden by portfolio averages.
5. Use **Runs** to select and compare analyses. **Export run** downloads a complete evidence ZIP. Inventory and cohort CSV exports contain all matching rows, not just the visible page.

The protocol uses 78 training weeks, 52 validation weeks, and 26 evaluation weeks. The baseline is an eight-week moving average with buffer `z = 1.645`. Baseline and selected policies use matched lead-time draws in each evaluation replication. The revised mode compares 66 model-buffer combinations, retains exact baseline policies for Class A, and applies cost and service guards during validation. It does not establish global policy optimality.

## 5. Reproduce an archived result exactly

`evidence/improved-run.zip` and `evidence/stress-run.zip` contain the recorded configuration, raw inputs, frozen policy selections, replication results, code snapshot, and SHA-256 manifest. Execute the **archived code snapshot** against the archived inputs using the following procedure. It needs no live app, saved workspace, or parent project folder.

From the repository root, on Windows:

```powershell
.\.venv\Scripts\python.exe -m zipfile -e evidence/improved-run.zip .replay/primary/export
.\.venv\Scripts\python.exe -m zipfile -e .replay/primary/export/source.zip .replay/primary/source
.\.venv\Scripts\python.exe .replay/primary/source/tools/replay_export.py evidence/improved-run.zip --output .replay/primary/replay.json
```

On macOS/Linux:

```bash
.venv/bin/python -m zipfile -e evidence/improved-run.zip .replay/primary/export
.venv/bin/python -m zipfile -e .replay/primary/export/source.zip .replay/primary/source
.venv/bin/python .replay/primary/source/tools/replay_export.py evidence/improved-run.zip --output .replay/primary/replay.json
```

Success prints **`Replay matches exported summary:`** followed by the output path. The script verifies the export manifest, recomputes the analysis, and requires exact equality of the recorded summary. It does not claim byte-for-byte equality of the entire result or independent scientific validation. Use the recorded Python/package versions if numerical equality fails on a different runtime.

For the longer-lead result, repeat the three commands with `stress-run.zip` instead of `improved-run.zip` and `.replay/stress` instead of `.replay/primary`. Its lead-time factor is 1.25, scaling both evaluation lead draws and the moments used by stock targets while keeping validation selections fixed. This represents anticipated longer leads, not an unexpected disruption with unchanged targets.

## 6. Expected findings and limits

These are means across 30 paired simulations:

| Measure | Fixed baseline | Original selection | Revised selection |
| --- | ---: | ---: | ---: |
| Holding cost, source units | 5,483,697.15 | 6,029,804.48 | 5,221,980.47 |
| Immediate unit fill | 96.89% | 96.97% | 96.10% |
| Class A fill | 97.80% | 96.57% | 97.80% |
| Stockout series-weeks | 875.5 | 1,032.7 | 1,198.2 |

The original selection increased holding cost by **9.96%**, so its joint cost/service hypothesis is unsupported. The revision reduces cost by **4.77%** against baseline but lowers overall fill by **0.798 percentage points** and increases stockout series-weeks by **36.85%**. Two sites lose more than one service percentage point despite every site remaining above 95%. The 611 changed policies have approximately 94.09% fill. The revision reused an examined evaluation period and is **exploratory**.

The simulator assumes complete receipts and an empty initial order pipeline. It measures holding cost, not a complete total-cost objective with ordering, shortage, repair, and disposal costs. A 95% fill target differs from preserving fill within one percentage point of baseline. Prediction bands describe demand uncertainty without guaranteeing coverage or service. Synthetic data, these assumptions, and the reused period limit generalization. Target stock is not an approved purchase quantity; actual ordering requires reconciled inventory, open orders, receipt behavior, and planner review.

## 7. Check the package

On Windows:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe tools/verify_package.py
```

On macOS/Linux:

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tools/verify_package.py
```

Tests exercise application behavior using local fixtures. The package verifier checks files in `SHA256SUMS.txt`; editing a listed file intentionally changes that check. Neither replaces review of the scientific assumptions. The supported numerical reproduction command for the supplied evidence is `replay_export.py` above.

## Repository guide

- `app/`: ingestion, storage, forecasting, simulation, policy selection, results, and local server.
- `web/`: browser interface with no external JavaScript dependency.
- `data/`: pinned synthetic input archive and attribution.
- `evidence/`: archived runs, comparison CSVs, SQL, charts, and application screenshots.
- `tests/`: local application tests.
- `tools/replay_export.py`: exported-summary replay.
- `tools/verify_package.py`: release-manifest verification.
- `PORTFOLIO_README.md`: guide connecting the code and evidence to the research.

Application code is MIT licensed; see `LICENSE` and `THIRD_PARTY_NOTICES.txt`. Python, NumPy, and SciPy retain their respective licenses. Dataset citation:

Tientcheu, R. C. (2026). *Aerospace supply chain performance & forecasting* (Version 1) [Data set]. Kaggle. https://www.kaggle.com/datasets/robertocarlost/aerospace-supply-chain-performance-and-forecasting
