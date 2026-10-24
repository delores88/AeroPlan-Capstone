# Verification and reproduction

Run the commands from the repository root using the isolated Python environment created in README.md.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe tools/verify_package.py
```

On macOS or Linux, replace `.\.venv\Scripts\python.exe` with `.venv/bin/python`.

The test suite covers data ingestion, inventory accounting, statistical calculations, policy dispatch and guards, prediction intervals, and local-server behavior. Tests use temporary workspaces. The package check compares published source, data, and evidence files with SHA256SUMS.txt. A deliberate edit makes that check report a changed file.

The frozen primary run is `47b10bd460d3` in `evidence/improved-run.zip`. The anticipated longer-lead run is `793782ebd1c2` in `evidence/stress-run.zip`. Each export contains raw inputs, checksums, the recorded configuration, source.zip, policies, and numerical results. Follow the exact-source replay steps in the root README to recompute either run in a temporary workspace. A successful replay reports that its summary matches the export. Reading an archive or passing unit tests alone does not complete that replay.

The public checkout does not include a local database or a previously running web server. Start `launch.py` to create a new workspace, or replay a preserved export directly. Historical validation scripts that depended on external coursework folders are excluded from this checkout; archived source snapshots remain byte-for-byte intact for numerical reproduction.

## Interpretation

The final revision reduced modeled holding cost by 4.7726% against baseline while immediate fill declined 0.7980 percentage points to 96.0963%. Class A retained the exact baseline by design. Two sites lost more than one service point, and stockout weeks increased. These exploratory findings and the original unfavorable comparison are retained in OPTIMIZATION_HISTORY.md. Software verification does not establish performance in a real organization or a guaranteed service level.
