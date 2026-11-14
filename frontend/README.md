# Protolab real-results frontend

```bash
cd backend
python3 -m protolab.web --port 8765
```

Open http://127.0.0.1:8765. This is a read-only viewer of saved real Boltz
results in `runs/1brs-live`. There is no synthetic demo endpoint or fallback.
Missing data stays unavailable. The historical 1BRS A/D complex is a reconstruction
smoke test, not a held-out test, candidate library or MD simulation.

Use the separately installed evaluation dependencies to refresh the existing
job and compute metrics (this command never submits another paid prediction):

```bash
venv/bin/python -m protolab.live_eval
```

The live report includes matched-residue complex Cα RMSD, binder Cα RMSD after
target alignment, and Cα contact precision/recall at 8 Å. No off-target,
developability, binding-affinity or wet-lab claims are inferred from these metrics.

Predicted samples and the experimental A/D pair can be inspected in the browser.
The reference pair is renamed A/B for display. Both use actual PDB coordinates;
the Cα viewer is not an all-atom visualization. Local PDB files stay in-browser.
API credentials and signed result URLs are never sent to the frontend.
