# Target-specific live workflow

The main page now uses real Tamarind BoltzProt jobs only. No RF demo scores, unrelated archive selector or seeded candidate generator is used.

1. Enter a supported UniProt accession or exact reviewed gene symbol and select human/mouse. Build design brief resolves the sequence from UniProt. A uniquely annotated extracellular region is used when present, otherwise a uniquely annotated mature chain following a signal peptide, or the full sequence; its exact bounds appear in the brief. Unsupported/ambiguous inputs are rejected.
2. Run real Tamarind screen submits 10 miniproteins (80 aa) with this target sequence using the account's credits. Merely loading the page or resolving a different target does not submit a new compute job.
3. The provider returns generated designs and predicted complex structures. Validate sequence identity, duplicates, binder/target chain mapping, and real numeric metrics. Rank by binding confidence, then structure confidence. These are model confidence scores, not measured affinity.
4. Gates: binding confidence >= 0.70 and structure confidence >= 0.68. Up to 3 passing candidates are shortlisted. If fewer than 3 pass, remaining display slots are filled by the highest-ranked QC-valid predictions, clearly labelled diagnostic only. Each card retains its gate outcome; the pass count is never inflated.
5. Render the exact target and shortlisted/diagnostic structures in ChimeraX. Individual proteins are extracted bound conformations, not independent unbound simulations. Assembly transitions are illustrative, not molecular dynamics.
6. Changing target inputs immediately clears the previous task's evidence. Only manifests with the matching research ID and target sequence hash are accepted. Refreshing the page with the same inputs reuses the existing task; it never automatically resubmits a paid job.

## Scope

Currently supported: canonical protein sequences of 10–2000 residues, human/mouse UniProt records, miniprotein binders. The original EGFR P00533 25–645 job was explicitly stopped by the user. The three active demos are human PD-L1 Q9NZQ7 19–238 (220 aa), PD-1 Q15116 25–170 (146 aa), and mature IL-2 P60568 21–153 (133 aa). Each designs 10 candidates and renders up to 3 candidate pairs; no historical substitute is shown. Target type, species, region, sequence hash and provider job are stored with every run.

Not implemented: site-specific antagonism design, mutant-sequence specification, glycans, off-target selectivity, toxicity/immunogenicity evaluation, expression/yield prediction, kinetics, independent replicate confirmation or wet-lab efficacy. The intended effect is recorded as a research objective, not passed as an unsupported constraint or inferred to be achieved. Unknown metrics have no fabricated scores or weights.

## Start

From repository root:

```sh
sh scripts/start-local.sh
```

Windows: `scripts/start-local.cmd` with Python 3 installed. Open http://127.0.0.1:8877. Set `TAMARIND_API_KEY` in the ignored `backend/.env` or environment for new jobs. Install official ChimeraX under its license; macOS auto-detects `/Applications/ChimeraX.app`. Other paths use `CHIMERAX_EXECUTABLE`. Linux rendering needs working EGL/OpenGL. There is no publicly exposed ChimeraX service.

SAMSON is optional: published documents for the exact objects may be linked following MOLECULAR_EVIDENCE.md. No account/document is currently configured. Real ChimeraX media plays without SAMSON.

## Persistence and API

`runs/research/<research-id>.json` is keyed by the verified target specification. `runs/tamarind/` holds provider inputs and an exclusive attempt marker; uncertain submissions are never silently repeated. A cross-process file lock prevents duplicate postprocessing. Worker progress is persistent. Server startup automatically resumes already requested nonterminal tasks, even without an open browser; ready, stopped and completed tasks are never auto-submitted. Completed render hashes are reused.

- GET `/api/research/demos`: three configured real demo records; buttons refresh status and open stored results directly without a new UniProt lookup or paid submission
- POST `/api/research/resolve`: target, species, modality, intent (read-only external lookup)
- POST `/api/research/start`: id (submits a real job or resumes local rendering)
- GET `/api/research/<id>`: real status, metrics, shortlist, provenance

States: ready, preparing, submitting, computing, screening, rendering, complete, stopped, failed, submission_uncertain, render_failed. Provider progress is not fabricated; Running can cover generation and complex prediction together.

## Sharing

The local URL is not publicly reachable. To share a runnable local package, export the exact completed visualization run with `scripts/export-viewer.py`. It includes the matching research record, structures and media, excluding API keys and raw API caches. Recipients install Python dependencies; stored demo buttons and movies need no external lookup, ChimeraX or Tamarind key. Resolving a new target requires internet access to UniProt. New computation requires their own key and renderer. Public hosting/authentication is separate deployment work.

Validation covers target/species matching, input-specific identity, duplicate exclusion, missing metrics, honest no-pass outcomes, no repeated completed submissions, media integrity and byte-range playback. Actual end-to-end success is only reported after the provider completes and the returned structures are verified/rendered.
