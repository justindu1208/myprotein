# Binder harness: evidence before explanation

The binder workflow is a deterministic backend alongside the original research
protocol. Run it with `python -m protolab.binder_cli input.json`. The legacy
`run_step` is a language-model explanation interface, not the binder controller.

## Current implementation

1. Readiness checks exact canonical target sequence, confirmed construct identity,
   explicit target residues (1-based positions in that sequence), intended use,
   accepted constraints and unresolved options.
2. Candidate QC checks completion, canonical sequence, duplicate sequence, length
   and forbidden literal motifs. It cannot infer binding before prediction.
3. Outcome checks typed prediction/analysis evidence, provenance and scope. A
   project policy can additionally require MD evidence.
4. Decision checks implemented constraints and required selectivity/developability
   assessments, then shortlists candidates for experimental review.

Every assessment returns `candidate_id`, `stage`, `state`, `reasons`, `evidence`
and `decision`. Reasons may coexist. A wrong site overrides high confidence;
a timeout is a technical error rather than biological rejection. Missing evidence
is uncertain, never zero and never pass. The final action is
`SHORTLIST_FOR_EXPERIMENT_REVIEW`, not automatic wet-lab execution.

100 generated / 10 prediction jobs / 5 recommendations are configurable upper
limits, not success quotas. QC currently takes valid candidates in input order;
it does NOT claim a learned top-10 ranking or diversity optimization. Eligible
final candidates are sorted by interface confidence, NOT protein-protein affinity.
Fewer candidates, including zero, are valid results.

## Prediction versus simulation

| Evidence | Allowed interpretation | Not established |
| --- | --- | --- |
| Boltz complex structure + confidence | Predicted geometry and model confidence | Binding affinity or time stability |
| Independent predictions + explicit comparison | Agreement of samples | Molecular motion or dissociation |
| MD trajectory + trusted analysis | Behavior over the sampled conditions/time | Guaranteed long-term stability or experimental binding |
| Off-target assessment | The assessed panel/protocol's outcome | Universal specificity |
| Developability assessment | The assessed properties/protocol's outcome | Guaranteed expression or clinical safety |

Tamarind is a provider; record the actual underlying method and version. The
adapter must preserve raw files and compute metrics. Do not feed an LLM-generated
`STABLE_INTERFACE` label back as a measurement. MD `sampling_adequate` must be
judged against a documented project-specific protocol, not a universal duration.
This first version intentionally does not emit all proposed reasons: affinity,
immunogenicity, dissociation and solubility labels need appropriate adapters.
`MEETS_IMPLEMENTED_CONSTRAINTS` is intentionally narrower than all user wishes.

## Trust boundary

`Evidence` is trusted adapter input, never public chat input. Each item requires:
metric/value/unit, method kind, tool/version, run ID, artifact URI and SHA-256,
candidate ID and input hash. Obtain the input hash using
`BinderHarness.scope(request, candidate)`; it covers request, candidate and full
policy. Changed inputs or policy invalidate previous evidence. Unknown metric,
wrong type/unit, nonfinite value, wrong kind, duplicate evidence ID, unknown
candidate and stale hash fail closed. Conflicting measurements require review.

The harness validates metadata, not artifact existence or scientific truth.
A production adapter must actually read and hash raw artifacts, verify chain
mapping and units, and compute each metric before creating Evidence. Forging a
valid JSON envelope is not prevented by a hash alone. `site_match`, replicate
agreement and risk assessments must cite their analysis artifact, including
thresholds and scope. Do not expose the CLI input format as an unauthenticated API.

A versioned Policy explicitly supplies the interface threshold: no universal
biological cutoff is hard-coded. Demo thresholds are illustrative, not validated.
Require human acceptance of the normalized request; unsupported natural-language
constraints must remain unresolved rather than silently dropped. Canonical
sequences only are supported in this initial implementation.

## Execution and integration

`BinderHarness.run` consumes candidate lists and evidence and produces a JSON
report. It does not generate sequences or launch simulations. `BoundedExecutor`
provides injected action allowlisting, in-memory job deduplication and bounded
attempts. Adapters must set timeouts; there is no background worker, cancellation
or durable retry store yet. Persist attempts/cache at the service boundary before
using multiple processes or restarts. Classifier retry counts are provided by
that trusted execution state, not by chat.

Generation, Boltz/Tamarind adapters, trajectory analysis and UI are still to be
connected. The existing Boltz stub now returns `not_configured`, with no fake
structure. No API keys or paid jobs are required for offline tests.

The protocol template `binder-screening.json` supplies the four explanation views.
Use `run_binder_round` to put authoritative assessments into their project-record
entries. Calling a step agent only explains those records; it must never replace
their classifications. This is a bounded workflow scaffold, not a complete
production ReAct agent.

## Offline checks

```bash
cd backend
python -m unittest discover -s tests -p test_harness.py -v
python -m protolab.binder_cli ../examples/binder-input.json
# With test dependencies installed:
python -m pytest
```

The example intentionally has no evidence and therefore recommends nobody.
MD mode can be tested offline with synthetic fixtures in the test suite, but
these fixtures are not scientific results.

## Hard-coded pipeline (no ReAct)

```bash
cd /Users/justindu/Documents/Codex/2026-11-14/new-chat-2/protolab/backend
python3 -m protolab.pipeline --demo
# Optional complete report, including embedded source artifacts (new file only):
python3 -m protolab.pipeline --demo --output /tmp/protolab-demo-report.json
```

`FixedPipeline` executes readiness, generation, QC, sequential predictions,
outcome classification and shortlist in that fixed order. It has no LLM planner,
no automatic retry loop, and launches at most the configured prediction limit.
Failures are isolated to the affected candidate. The event list is an execution
record returned at completion, not a live event stream.

`DemoBackend` supplies deterministic synthetic sequences and fabricated test
metrics, not designed binders or actual Boltz output. Demo results are separated
under `demo_recommendations`; real `recommendations` stays empty. Embedded
artifact JSON is hashed and referenced by evidence. No MD is fabricated.

Without `--demo`, `--input` is required and unconfigured adapters fail closed.
Supply a backend implementing `generate(request, count)` and
`predict(request, candidate)` to use real tools. Prediction output needs `tool`,
`tool_version`, `run_id` and a `metrics` mapping. This backend is a trusted
integration boundary: it must perform the real analyses required for each metric,
including separate off-target/developability checks. The pipeline merely
packages those supplied measurements; it cannot authenticate their biology.
No frontend changes were made.
