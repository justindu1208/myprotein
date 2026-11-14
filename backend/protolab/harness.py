"""Deterministic binder triage. No model-generated measurements or live jobs.

Evidence must be produced by a trusted server-side adapter, not by an LLM.
This module validates provenance shape and input scope; it cannot authenticate
an arbitrary caller's scientific claims. Thresholds are explicit project policy.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import math
import re
from typing import Callable

AA = re.compile(r"[ACDEFGHIKLMNPQRSTVWY]+\Z")
ERRORS = {"INPUT_PREPARATION_FAILED", "TOOL_TIMEOUT", "TOOL_ERROR", "RESULT_FILE_INVALID"}
# metric: (required evidence kind, accepted value type)
METRICS = {
    "interface_confidence": ("structure_prediction", "fraction"),
    "site_match": ("structure_analysis", "bool"),
    "replicates_consistent": ("replicate_analysis", "bool"),
    "selectivity_pass": ("off_target_assessment", "bool"),
    "developability_pass": ("developability_assessment", "bool"),
    "sampling_adequate": ("md_analysis", "bool"),
    "interface_retained": ("md_analysis", "bool"),
    "binder_stable": ("md_analysis", "bool"),
}


def fingerprint(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def valid_sequence(value: object) -> bool:
    return isinstance(value, str) and AA.fullmatch(value) is not None


@dataclass(frozen=True)
class Policy:
    version: str
    min_length: int
    max_length: int
    interface_min: float
    max_generated: int = 100
    max_predictions: int = 10
    max_recommendations: int = 5
    max_retries: int = 1
    require_md: bool = False
    require_selectivity: bool = True
    require_developability: bool = True
    forbidden_motifs: tuple[str, ...] = ()

    def __post_init__(self):
        if not self.version or type(self.interface_min) not in (int, float) or not math.isfinite(self.interface_min) or not 0 <= self.interface_min <= 1:
            raise ValueError("Explicit policy version and finite interface threshold required")
        ints = (self.min_length, self.max_length, self.max_generated,
                self.max_predictions, self.max_recommendations, self.max_retries)
        if any(type(x) is not int for x in ints):
            raise ValueError("Counts must be integers")
        if not 1 <= self.min_length <= self.max_length or not 1 <= self.max_recommendations <= self.max_predictions <= self.max_generated or self.max_retries < 0:
            raise ValueError("Invalid limits")
        if any(type(x) is not bool for x in (self.require_md, self.require_selectivity, self.require_developability)):
            raise ValueError("Policy flags must be boolean")
        if any(not valid_sequence(m) for m in self.forbidden_motifs):
            raise ValueError("Forbidden motifs must be canonical amino-acid strings")


@dataclass(frozen=True)
class Evidence:
    id: str
    candidate_id: str
    input_hash: str
    kind: str
    metric: str
    value: object
    tool: str
    tool_version: str
    run_id: str
    artifact_uri: str
    artifact_sha256: str
    unit: str = "dimensionless"
    status: str = "success"

    def validate(self):
        if any(not isinstance(x, str) or not x.strip() for x in (
            self.id, self.candidate_id, self.tool, self.tool_version,
            self.run_id, self.artifact_uri,
        )):
            raise ValueError("Evidence provenance is incomplete")
        if not re.fullmatch(r"[a-f0-9]{64}", self.input_hash) or not re.fullmatch(r"[a-f0-9]{64}", self.artifact_sha256):
            raise ValueError("Evidence needs SHA-256 input/artifact hashes")
        if self.status != "success" or self.metric not in METRICS:
            raise ValueError("Unsupported or unsuccessful evidence")
        kind, value_type = METRICS[self.metric]
        if self.kind != kind or self.unit != "dimensionless":
            raise ValueError("Wrong evidence kind or unit")
        if value_type == "bool" and type(self.value) is not bool:
            raise ValueError("Expected boolean metric")
        if value_type == "fraction" and (type(self.value) not in (int, float) or not math.isfinite(self.value) or not 0 <= self.value <= 1):
            raise ValueError("Expected finite metric in [0,1]")


@dataclass(frozen=True)
class Assessment:
    candidate_id: str | None
    stage: str
    state: str
    reasons: tuple[str, ...]
    decision: str
    evidence: tuple[Evidence, ...] = ()

    def to_dict(self):
        return asdict(self)


def result(cid, stage, state, reasons, decision, evidence=()):
    return Assessment(cid, stage, state, tuple(dict.fromkeys(reasons)), decision, tuple(evidence))


def readiness(request: dict, policy: Policy) -> Assessment:
    reasons = []
    target = request.get("target_sequence")
    if not target:
        reasons.append("TARGET_MISSING")
    elif not valid_sequence(target):
        reasons.append("INVALID_TARGET_SEQUENCE")
    if request.get("target_type", "protein") != "protein":
        reasons.append("UNSUPPORTED_TARGET_TYPE")
    # A user-confirmed exact construct resolves identity; a name alone does not.
    if request.get("target_confirmed") is not True:
        reasons.append("TARGET_AMBIGUOUS")
    region = request.get("target_region")
    if not region:
        reasons.append("TARGET_REGION_MISSING")
    elif not isinstance(region, list) or not valid_sequence(target) or any(type(i) is not int or not 1 <= i <= len(target) for i in region):
        reasons.append("CONFLICTING_CONSTRAINTS")
    if not isinstance(request.get("intended_use"), str) or not request["intended_use"].strip():
        reasons.append("INTENDED_USE_MISSING")
    # Explicit acceptance prevents the language model silently inventing constraints.
    if request.get("constraints_confirmed") is not True:
        reasons.append("CONSTRAINTS_MISSING")
    if request.get("unresolved_options"):
        reasons.append("NEEDS_USER_CONFIRMATION")
    return result(None, "READINESS", "NEED_INFO" if reasons else "PASS", reasons or ["INPUT_READY"], "ASK_USER" if reasons else "GENERATE_CANDIDATES")


def candidate_qc(candidate: dict, policy: Policy, seen: set[str]) -> Assessment:
    cid, sequence = candidate["id"], candidate.get("sequence")
    reasons = []
    if candidate.get("generation_complete") is not True:
        reasons.append("GENERATION_INCOMPLETE")
    if not valid_sequence(sequence):
        reasons.append("INVALID_SEQUENCE")
    else:
        if sequence in seen:
            reasons.append("DUPLICATE_CANDIDATE")
        seen.add(sequence)
        if not policy.min_length <= len(sequence) <= policy.max_length:
            reasons.append("WRONG_LENGTH")
        if any(motif in sequence for motif in policy.forbidden_motifs):
            reasons.append("FORBIDDEN_MOTIF")
    return result(cid, "CANDIDATE_QC", "FAIL" if reasons else "PASS", reasons or ["VALID_SEQUENCE"], "REJECT" if reasons else "RUN_PREDICTION")


def outcome(cid: str, evidence: tuple[Evidence, ...], policy: Policy,
            retries: int = 0, error: str | None = None) -> Assessment:
    if type(retries) is not int or retries < 0:
        raise ValueError("Invalid retry count")
    retry = "RERUN_PREDICTION" if retries < policy.max_retries else "HUMAN_REVIEW"
    if error:
        if error not in ERRORS:
            raise ValueError("Unknown tool error")
        action = retry if error in {"TOOL_TIMEOUT", "TOOL_ERROR"} else "HUMAN_REVIEW"
        return result(cid, "SIMULATION_OUTCOME", "ERROR", [error], action)
    by_metric = {}
    for e in evidence:
        e.validate()
        if e.candidate_id != cid:
            raise ValueError("Wrong candidate")
        by_metric.setdefault(e.metric, []).append(e.value)
    if any(len(set(values)) != 1 for values in by_metric.values()):
        return result(cid, "SIMULATION_OUTCOME", "UNCERTAIN", ["CONFLICTING_METRICS"], "HUMAN_REVIEW", evidence)
    values = {k: v[0] for k, v in by_metric.items()}
    reasons, negative, missing = [], [], []
    confidence = values.get("interface_confidence")
    if confidence is None:
        missing.append("STRUCTURE_INCONCLUSIVE")
    elif confidence < policy.interface_min:
        missing.append("STRUCTURE_LOW_CONFIDENCE")
    else:
        reasons.append("STRUCTURE_HIGH_CONFIDENCE")
    if "site_match" not in values:
        missing.append("BINDING_INCONCLUSIVE")
    elif values["site_match"] is False:
        negative.append("WRONG_BINDING_SITE")
    else:
        reasons.append("PREDICTED_SITE_MATCH")
    if "replicates_consistent" not in values:
        missing.append("INSUFFICIENT_SAMPLING")
    elif values["replicates_consistent"] is False:
        missing.append("INCONSISTENT_REPLICATES")
    else:
        reasons.append("CONSISTENT_REPLICATES")
    if policy.require_md:
        md_retry = "RERUN_SIMULATION" if retries < policy.max_retries else "HUMAN_REVIEW"
        checks = (("sampling_adequate", "SAMPLING_ADEQUATE", "INSUFFICIENT_SAMPLING"),
                  ("interface_retained", "STABLE_INTERFACE", "INTERFACE_LOST"),
                  ("binder_stable", "BINDER_STRUCTURE_STABLE", "BINDER_STRUCTURE_UNSTABLE"))
        for metric, positive, failure in checks:
            if metric not in values:
                missing.append("SIMULATION_INCONCLUSIVE")
            elif values[metric]:
                reasons.append(positive)
            elif metric == "sampling_adequate":
                missing.append(failure)
            else:
                negative.append(failure)
        if not any(m in missing for m in ("STRUCTURE_INCONCLUSIVE", "STRUCTURE_LOW_CONFIDENCE", "BINDING_INCONCLUSIVE", "INCONSISTENT_REPLICATES")):
            retry = md_retry
    if negative:
        return result(cid, "SIMULATION_OUTCOME", "FAIL", reasons + negative + missing, "REJECT", evidence)
    if missing:
        return result(cid, "SIMULATION_OUTCOME", "UNCERTAIN", reasons + missing, retry, evidence)
    return result(cid, "SIMULATION_OUTCOME", "PASS", reasons, "EVALUATE_DECISION", evidence)


def decide(qc: Assessment, evaluation: Assessment, policy: Policy) -> Assessment:
    if qc.candidate_id != evaluation.candidate_id:
        raise ValueError("Candidate mismatch")
    cid = qc.candidate_id
    if qc.state != "PASS" or evaluation.state == "FAIL":
        return result(cid, "DECISION", "FAIL", ["HARD_CONSTRAINT_VIOLATION"], "REJECT", evaluation.evidence)
    if evaluation.state != "PASS":
        return result(cid, "DECISION", "UNCERTAIN", ["INSUFFICIENT_EVIDENCE"], evaluation.decision, evaluation.evidence)
    reasons, missing, failures = ["MEETS_IMPLEMENTED_CONSTRAINTS"], [], []
    values = {e.metric: e.value for e in evaluation.evidence}
    for metric, required, positive, unknown, negative in (
        ("selectivity_pass", policy.require_selectivity, "SELECTIVITY_PASS", "NEEDS_OFF_TARGET_VALIDATION", "POSSIBLE_OFF_TARGET"),
        ("developability_pass", policy.require_developability, "DEVELOPABILITY_PASS", "DEVELOPABILITY_UNKNOWN", "DEVELOPABILITY_RISK"),
    ):
        if metric not in values:
            if required:
                missing.append(unknown)
            else:
                reasons.append(unknown)
        elif values[metric] is False:
            failures.append(negative)
        else:
            reasons.append(positive)
    if failures:
        return result(cid, "DECISION", "FAIL", reasons + failures + missing, "REJECT", evaluation.evidence)
    if missing:
        return result(cid, "DECISION", "UNCERTAIN", reasons + missing + ["INSUFFICIENT_EVIDENCE"], "REQUEST_EVIDENCE", evaluation.evidence)
    return result(cid, "DECISION", "PASS", reasons, "SHORTLIST_FOR_EXPERIMENT_REVIEW", evaluation.evidence)


class BinderHarness:
    """One bounded round; trusted adapters submit evidence, never LLM output.

    Input changes create a new scope. Calls cannot execute tools or authorize wet
    experiments. Recommendations are review candidates, not validated binders.
    """
    def __init__(self, policy: Policy):
        self.policy = policy

    def scope(self, request: dict, candidate: dict) -> str:
        return fingerprint({"request": request, "candidate": candidate, "policy": asdict(self.policy)})

    def run(self, request: dict, candidates: list[dict], evidence: list[Evidence] = (),
            retries: dict[str, int] | None = None, errors: dict[str, str] | None = None) -> dict:
        p = self.policy
        ready = readiness(request, p)
        report = {"schema_version": "1", "policy": asdict(p), "readiness": ready.to_dict(),
                  "candidates": [], "selected_for_prediction": [], "recommendations": [],
                  "limitations": ["Computational triage, not demonstrated binding or experimental success.",
                                  "QC selection uses input order, not a binding ranking."]}
        if ready.state != "PASS":
            return report
        if len(candidates) > p.max_generated:
            raise ValueError("Generation budget exceeded")
        ids = [c.get("id") for c in candidates]
        if any(not isinstance(cid, str) or not cid.strip() for cid in ids) or len(set(ids)) != len(ids):
            raise ValueError("Candidate IDs must be unique nonempty strings")
        index = {c["id"]: c for c in candidates}
        grouped = {cid: [] for cid in ids}
        evidence_ids = set()
        for e in evidence:
            e.validate()
            if e.id in evidence_ids or e.candidate_id not in index:
                raise ValueError("Duplicate evidence ID or unknown candidate")
            if e.input_hash != self.scope(request, index[e.candidate_id]):
                raise ValueError("Stale or mismatched evidence input hash")
            evidence_ids.add(e.id)
            grouped[e.candidate_id].append(e)
        retries, errors = retries or {}, errors or {}
        if (set(retries) | set(errors)) - set(ids):
            raise ValueError("Unknown candidate in execution state")
        if any(type(n) is not int or n < 0 for n in retries.values()) or any(e not in ERRORS for e in errors.values()):
            raise ValueError("Invalid execution state")
        seen, eligible = set(), []
        for candidate in candidates:
            cid = candidate["id"]
            qc = candidate_qc(candidate, p, seen)
            row = {"candidate_id": cid, "input_hash": self.scope(request, candidate), "qc": qc.to_dict()}
            if qc.state == "PASS" and len(report["selected_for_prediction"]) < p.max_predictions:
                report["selected_for_prediction"].append(cid)
                ev = outcome(cid, tuple(grouped[cid]), p, retries.get(cid, 0), errors.get(cid))
                decision = decide(qc, ev, p)
                row.update(outcome=ev.to_dict(), decision=decision.to_dict())
                if decision.state == "PASS":
                    score = next(e.value for e in ev.evidence if e.metric == "interface_confidence")
                    eligible.append((score, cid))
            elif qc.state == "PASS":
                row["decision"] = result(cid, "DECISION", "UNCERTAIN", ["PREDICTION_BUDGET_LIMIT"], "DEFER").to_dict()
            else:
                row["decision"] = result(cid, "DECISION", "FAIL", qc.reasons, "REJECT").to_dict()
            report["candidates"].append(row)
        report["recommendations"] = [cid for _, cid in sorted(eligible, key=lambda x: (-x[0], x[1]))[:p.max_recommendations]]
        report["ranking_basis"] = "interface_confidence among eligible candidates; not affinity"
        report["generation_complete"] = len(candidates) == p.max_generated and all(c.get("generation_complete") is True for c in candidates)
        return report


class BoundedExecutor:
    """Injected allowlist of adapters. Cache successful jobs; bound retry attempts.

    Own one executor per workflow and persist its state at the service boundary.
    Timeout enforcement is the adapter/worker's responsibility.
    """
    def __init__(self, adapters: dict[str, Callable], max_retries: int = 1):
        if type(max_retries) is not int or max_retries < 0:
            raise ValueError("Invalid retry budget")
        self.adapters = dict(adapters)
        self.max_retries = max_retries
        self.attempts, self.cache = {}, {}

    def execute(self, action: str, payload: dict) -> dict:
        if action not in self.adapters:
            raise ValueError("Action is not allowlisted")
        key = fingerprint({"action": action, "payload": payload})
        if key in self.cache:
            return json.loads(self.cache[key])
        if self.attempts.get(key, 0) >= self.max_retries + 1:
            return {"state": "UNCERTAIN", "reasons": ["RETRY_BUDGET_EXHAUSTED"], "decision": "HUMAN_REVIEW"}
        self.attempts[key] = self.attempts.get(key, 0) + 1
        try:
            output = self.adapters[action](json.loads(json.dumps(payload, allow_nan=False)))
            if not isinstance(output, dict) or output.get("status") != "success":
                raise ValueError("Adapter did not return success")
            encoded = json.dumps(output, allow_nan=False)
        except TimeoutError:
            return {"state": "ERROR", "reasons": ["TOOL_TIMEOUT"], "decision": "RETRY" if self.attempts[key] <= self.max_retries else "HUMAN_REVIEW"}
        except Exception:
            return {"state": "ERROR", "reasons": ["TOOL_ERROR"], "decision": "RETRY" if self.attempts[key] <= self.max_retries else "HUMAN_REVIEW"}
        self.cache[key] = encoded
        return json.loads(encoded)


def run_binder_round(record, policy: Policy, request: dict, candidates: list[dict],
                     evidence=(), retries=None, errors=None) -> dict:
    """Write only computed classifications to the shared record, never LLM text."""
    if record.protocol_id != 'binder-screening':
        raise ValueError('Expected binder-screening project record')
    report = BinderHarness(policy).run(request, candidates, evidence, retries, errors)
    record.write('readiness', {'assessment': report['readiness']})
    # Always replace downstream results, including after readiness becomes blocked.
    rows = report['candidates']
    record.write('candidate_qc', {'assessments': [r['qc'] for r in rows]})
    record.write('simulation_outcome', {'assessments': [r['outcome'] for r in rows if 'outcome' in r]})
    record.write('decision', {'assessments': [r['decision'] for r in rows],
                              'recommendations': report['recommendations'],
                              'policy': report['policy'], 'limitations': report['limitations']})
    return report
