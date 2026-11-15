# Target-specific protein workbench

The app creates named local tasks and runs real Tamarind jobs. It never substitutes an unrelated demo for a task.

1. **New task:** enter a task name, a human/mouse UniProt accession or exact gene symbol, and 10–100 candidates. The task is saved locally before UniProt lookup. The selected region is the unique extracellular annotation, otherwise a single mature chain after a signal peptide, otherwise the full sequence. No custom residue range is supported.
2. **Tasks / ranking:** a real BoltzProt miniprotein design job (80 aa binders) is submitted when the user starts the task. Rank returned candidates by binding confidence, then structure confidence. Sequence and chain identity are checked. Configured gates are binding confidence ≥ 0.70 and structure confidence ≥ 0.68. Up to three passing candidates are displayed; when fewer pass, remaining slots contain explicitly labelled diagnostic predictions, not successful binders. Explanations describe score thresholds; they are not causal mechanisms.
3. **Experiment:** the user can start three independent Tamarind Boltz-2 complex predictions on the target and selected candidates. This consumes additional credits and may take several minutes. A restart resumes submitted jobs. Ambiguous submissions are not automatically repeated; retry of an HTTP 400 rejection requires explicit user action and verifies that the job does not already exist. The implementation has automated tests and API parameter validation; a complete live follow-up run has not yet been verified.
4. **Visualization:** ChimeraX renders predicted structures and illustrative animations. Candidate monomers are extracted bound conformations, not independently predicted unbound proteins. Complex animations are not molecular dynamics. User task and render data is stored under ignored `runs/`; copy those directories to transfer completed tasks, taking care with private data.

Priority sliders are recorded with the task but are **not** passed to Tamarind or used for ranking. Off-target selectivity, toxicity, immunogenicity, expression, yield, kinetics, biological effect and wet-lab success are not determined. Model scores are not measured affinity. Interface contacts are geometric proximity, not proof of hydrogen bonds.

## Setup

From the repository root run `sh scripts/start-local.sh` (Windows: `scripts/start-local.cmd`). Open http://127.0.0.1:8877. Put `TAMARIND_API_KEY=...` in `backend/.env` or your environment; do not commit credentials. Install ChimeraX under its license; macOS auto-detects `/Applications/ChimeraX.app`. Configure other installations with `CHIMERAX_EXECUTABLE`; Linux rendering needs working EGL/OpenGL. Precomputed assets may be viewed without a renderer when their matching task records are available. SAMSON publication is optional and requires an account and separately published matching documents.

The server binds to localhost and is not an authenticated multiuser production service. Stopping or restarting it does not cancel a cloud task; persisted jobs resume on restart. Task records and result artifacts remain on that machine and are not committed by Git.

## API and verification

- `POST /api/research/create` stores a named draft; `POST /api/research/start` begins or resumes work.
- `GET /api/research/tasks` lists named tasks; `GET /api/research/<id>` returns status.
- `POST /api/experiments/start` starts follow-up jobs; `GET /api/experiments/<id>` returns per-candidate status; `POST /api/experiments/retry` explicitly retries eligible rejected jobs.
- `/api/visualizations/...` serves verified structures and rendered media.

Run `cd backend && ../.venv/bin/python -m pytest -q`. Tests cover target identity, task persistence, screening, submission idempotency, retry safety, result chain matching and visualization. Validate real provider operations separately; do not infer a completed paid run from a passing mock test.
