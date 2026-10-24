# AeroPlan 2.2 architecture

Plain HTML/CSS/JavaScript/SVG in web/ calls a loopback Python HTTP service. There is no frontend build step, CDN or external analytics client. Python uses NumPy and SciPy for the simulation and inference. SQLite stores immutable imported dataset versions and completed run results.

- launch.py holds an exclusive workspace lock and defaults to 127.0.0.1:8767 with workspace-v22. A fresh checkout creates its own workspace and imports the bundled synthetic data.
- app/runner.py dispatches versioned policy modes; app/optimization.py supplies the development-only joint model/buffer search with baseline fallback and Class A protection.
- app/intervals.py calculates horizon-specific empirical prediction bands; app/results.py can derive display-only bands for older immutable runs.
- app/ingest.py validates staged CSVs, hashes, mappings and identities before atomic import.
- app/store.py persists source metadata and immutable completed runs. Recovery occurs only when Application starts, not when a reader opens Store.
- app/study.py selects policies, invokes the pre-evaluation freeze callback, and executes paired simulations. It never reads the coursework Research folder.
- app/forecast.py provides causal forecast implementations used by both the current engine and scalar regression reference.
- app/results.py provides paged views, complete filtered exports, source snapshots and export checksums.
- app/server.py manages one cancellable background evaluation, token-checked writes, dataset selection, results and exports.
- tools/replay_export.py reproduces an exported run in a temporary Store.
- tests/ contains the portable regression and focused test suite. Frozen result exports in evidence/ can be replayed independently of a prior workspace.

App writes require an exact loopback Host, same-origin Origin when present, and a per-session token. Static paths are allowlisted. Inputs are size-limited; filenames become basenames; imports never execute their contents. UI strings are escaped and CSV formula-leading strings are protected. A completed result cannot be overwritten through Store.finish_run. Concurrent launches cannot share a workspace.

The running app has no purchasing, cloud, Canvas or coursework-submission client. Source data and local outputs are ordinary unencrypted user files. It is a single-user local tool, not a multiuser hosted service.

The v1 app/engine.py scalar simulator and reports.py/pdf.py remain as backward-compatible regression utilities. The current UI and API use study.py and results.py for all new evaluations. The screenshots in evidence/ document the recorded final study, while a fresh checkout starts with no completed runs.
