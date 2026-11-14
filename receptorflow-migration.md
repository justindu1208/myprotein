# ReceptorFlow frontend migration

The shared ReceptorFlow concept has been migrated into Protolab's existing buildless frontend. The implementation deliberately keeps the stdlib Python server and live API surface unchanged.

## What was migrated

- Receptor, species, modality, and natural-language intended-use input.
- An agent-resolved design brief with explicit mechanism limitations.
- Five screening priorities that always rebalance to 100%.
- Independent hard constraints for structure confidence, aggregation, and immunogenicity risk.
- A six-stage rapid-screen visualisation with concise agent activity summaries.
- Thirty deterministic simulated candidates with evidence gates, uncertainty penalties, non-dominated screening, and weighted ranking.
- Balanced, affinity, selectivity, and lowest-risk winner categories.
- Top 10 evidence table, affinity-versus-safety map, JSON/CSV export, search, and Top 3 comparison.
- Candidate detail drawer with radar chart, evidence copy, provenance, and an interactive illustrative receptor/binder view.
- Responsive layouts for desktop, tablet, and mobile navigation.

## Trust and evidence design

- All candidate values are labelled as simulated `DemoProvider` data.
- Computational risk is never presented as clinical safety.
- The molecule canvas is explicitly labelled as illustrative geometry.
- Functional antagonism is presented as unverified until ligand-competition and receptor-activation assays are performed.
- The UI displays scientific action summaries rather than private chain-of-thought.

## Verification

- HTML parsed successfully with 50 unique element IDs.
- Browser flow completed from brief creation through rapid screen and candidate inspection.
- Weight rebalance verified: changing affinity from 40% to 60% preserved a 100% total and changed the balanced winner from RF-028 to RF-004.
- Top 3 comparison opened with three candidates.
- Candidate drawer rendered both canvases at device-pixel resolution.
- Desktop and 390 px responsive layouts were inspected.
- Browser console contained no warnings or errors during the verified flow.
- `git diff --check` passed.
- Python modules compile successfully.
- 29 backend unit tests passed under `unittest`; three pytest-authored modules could not import because `pytest` is not installed in the current interpreter.

## Cloud deployment

- Production URL: https://receptorflow-protolab.looseraccoon4.chatgpt.site
- Site project: `appgprj_6af8a870286c8191be30e18d05404a15`
- Published source commit: `f5d67ec77073526dafac20d6b5a2fced5eb9a70e`
- Access: owner-private
- Cloud source checkout: `sites/receptorflow-cloud/`
