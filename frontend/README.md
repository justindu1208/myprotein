# ReceptorFlow frontend

ReceptorFlow is the interactive decision-workbench demo for Protolab. It turns a receptor and intended biological effect into a structured design brief, runs a deterministic rapid-screen simulation, and lets the user re-rank candidates by changing scientific priorities.

## Run locally

```bash
cd backend
python3 -m protolab.web --port 8877
```

Open http://127.0.0.1:8877.

No npm install or build step is required. The existing Python server continues to serve the frontend and retain its live API routes.

## Demo path

1. Review or edit the target, modality, and intended effect.
2. Build the design brief and confirm its evidence boundary.
3. Adjust screening priorities and hard constraints.
4. Run the simulated rapid screen.
5. Inspect the winners, Top 10 table, decision frontier, or Top 3 comparison.
6. Open a candidate to inspect its metric profile and interactive illustrative structure.

## Evidence boundary

All candidate values in this flow are deterministic simulated data from `DemoProvider`. The interface labels them as simulated and never presents computational risk as clinical safety. The 3D view is illustrative geometry, not a physical structure prediction.

The backend's existing real Boltz routes remain available, but this migration does not silently mix them into the simulated decision report.
