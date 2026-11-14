"""Fixed sequence: readiness -> generate -> QC -> predict -> classify -> shortlist.

No LLM planner, no ReAct loop. DemoBackend is software-test data, not biology.
A real backend must implement generate(request, count) and predict(request,
candidate), with explicit per-request timeouts and scientific analysis.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

from .harness import BinderHarness, Evidence, METRICS, Policy


class NotConfigured(RuntimeError):
    pass


class UnconfiguredBackend:
    mode = 'live'

    def generate(self, request, count):
        raise NotConfigured('No binder-generation adapter configured')

    def predict(self, request, candidate):
        raise NotConfigured('No prediction adapter configured')


class DemoBackend:
    """Deterministic synthetic fixtures: deliberately NOT binder design."""
    mode = 'demo'

    def generate(self, request, count):
        alphabet = 'ACDEFGHIKLMNPQRSTVWY'
        if count > 400:
            raise ValueError('Demo fixture supports at most 400 candidates')
        return [dict(id=f'DEMO-{i + 1:03d}',
                     sequence='ACDEFGHIKL' + alphabet[i // 20] + alphabet[i % 20],
                     generation_complete=True) for i in range(count)]

    def predict(self, request, candidate):
        n = int(candidate['id'].split('-')[1])
        # Cases exercise positive, wrong-site, inconsistent, off-target,
        # developability-risk and missing-evidence paths.
        metrics = {
            'interface_confidence': round(.95 - n * .01, 2),
            'site_match': n != 6,
            'replicates_consistent': n != 7,
            'selectivity_pass': n != 8,
            'developability_pass': n != 9,
        }
        if n == 10:
            del metrics['interface_confidence']
        return {'tool': 'SYNTHETIC_FIXTURE_NOT_BOLTZ', 'tool_version': '1',
                'run_id': candidate['id'] + '-fixture', 'metrics': metrics,
                'notice': 'Fabricated software test values. No structure prediction or simulation ran.'}


class FixedPipeline:
    def __init__(self, policy: Policy, backend=None):
        self.policy = policy
        self.backend = backend or UnconfiguredBackend()
        self.harness = BinderHarness(policy)

    def run(self, request: dict) -> dict:
        events, artifacts = [], {}
        def event(stage, state, **detail):
            events.append(dict(stage=stage, state=state, **detail))
        def finish(report, status):
            report.update(mode=self.backend.mode, pipeline_status=status,
                          events=events, artifacts=artifacts)
            if self.backend.mode == 'demo':
                report['demo_recommendations'] = report['recommendations']
                report['recommendations'] = []
                report['notice'] = 'SYNTHETIC DEMO ONLY: no real generated binders, structures, affinity or MD results. Candidate assessments are test fixtures.'
            return report
        report = self.harness.run(request, [])
        event('READINESS', report['readiness']['state'])
        if report['readiness']['state'] != 'PASS':
            return finish(report, 'NEED_INFO')
        event('GENERATION', 'RUNNING', requested=self.policy.max_generated)
        try:
            candidates = self.backend.generate(request, self.policy.max_generated)
            # Validate identity and QC before any prediction job is launched.
            report = self.harness.run(request, candidates)
        except NotConfigured as exc:
            event('GENERATION', 'BLOCKED', reason='TOOL_NOT_CONFIGURED', message=str(exc))
            return finish(report, 'BLOCKED')
        except Exception as exc:
            event('GENERATION', 'ERROR', reason='TOOL_TIMEOUT' if isinstance(exc, TimeoutError) else 'TOOL_ERROR')
            return finish(report, 'ERROR')
        event('GENERATION', 'COMPLETE', received=len(candidates))
        selected = report['selected_for_prediction']
        event('CANDIDATE_QC', 'COMPLETE', selected=selected,
              rejected=sum(r['qc']['state'] == 'FAIL' for r in report['candidates']))
        by_id = {c['id']: c for c in candidates}
        evidence, errors = [], {}
        for cid in selected:
            candidate = by_id[cid]
            event('PREDICTION', 'RUNNING', candidate_id=cid)
            try:
                raw = self.backend.predict(request, candidate)
            except NotConfigured:
                errors[cid] = 'INPUT_PREPARATION_FAILED'
                event('PREDICTION', 'BLOCKED', candidate_id=cid, reason='TOOL_NOT_CONFIGURED')
                continue
            except Exception as exc:
                errors[cid] = 'TOOL_TIMEOUT' if isinstance(exc, TimeoutError) else 'TOOL_ERROR'
                event('PREDICTION', 'ERROR', candidate_id=cid, reason=errors[cid])
                continue
            try:
                serialized = json.dumps(raw, sort_keys=True, allow_nan=False)
                digest = sha256(serialized.encode()).hexdigest()
                artifact_id = 'result-' + digest
                if not isinstance(raw['metrics'], dict):
                    raise ValueError('Invalid metrics')
                batch = []
                for metric, value in raw['metrics'].items():
                    # Analysis metric kind is registered here, not chosen by an LLM.
                    # Production adapters must actually perform the named analysis.
                    e = Evidence(cid + ':' + metric, cid, self.harness.scope(request, candidate),
                                 METRICS[metric][0], metric, value, raw['tool'],
                                 raw['tool_version'], raw['run_id'],
                                 'report://artifacts/' + artifact_id, digest)
                    e.validate()
                    batch.append(e)
                artifacts[artifact_id] = raw
                evidence.extend(batch)
                event('PREDICTION', 'COMPLETE', candidate_id=cid)
            except (KeyError, TypeError, ValueError):
                errors[cid] = 'RESULT_FILE_INVALID'
                event('PREDICTION', 'ERROR', candidate_id=cid, reason='RESULT_FILE_INVALID')
        # One attempt per candidate: this fixed pipeline never silently resubmits jobs.
        report = self.harness.run(request, candidates, evidence, errors=errors)
        event('SIMULATION_OUTCOME', 'COMPLETE', errors=len(errors))
        event('DECISION', 'COMPLETE', shortlisted=len(report['recommendations']))
        return finish(report, 'COMPLETE_WITH_ERRORS' if errors else 'COMPLETE')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--demo', action='store_true', help='Use explicitly synthetic fixtures; no API calls')
    parser.add_argument('--input', type=Path, help='JSON containing request and policy; required outside demo')
    parser.add_argument('--output', type=Path, help='Save report to a NEW file (never overwrite)')
    args = parser.parse_args()
    if not args.demo and args.input is None:
        parser.error('Use --demo or supply --input; no live adapter is configured')
    try:
        if args.input:
            data = json.loads(args.input.read_text())
        else:
            data = {'policy': dict(version='synthetic-demo-v1', min_length=3, max_length=20, interface_min=.7),
                    'request': dict(target_sequence='ACDEFGHIK', target_confirmed=True,
                                    target_region=[2, 3], intended_use='software demo only', constraints_confirmed=True)}
        report = FixedPipeline(Policy(**data['policy']), DemoBackend() if args.demo else None).run(data['request'])
        rendered = json.dumps(report, indent=2, allow_nan=False)
        if args.output:
            with args.output.open('x') as f:
                f.write(rendered + '\n')
        # Compact, readable terminal output; full evidence retained in optional report.
        print(report.get('notice', 'Live mode: tool configuration required.'))
        for e in report['events']:
            if e['stage'] != 'PREDICTION' or e['state'] != 'RUNNING':
                print(f"{e['stage']:20} {e['state']:12} " + json.dumps({k: v for k, v in e.items() if k not in ('stage', 'state')}))
        print('Demo shortlist:' if args.demo else 'Shortlist:', report.get('demo_recommendations', report['recommendations']))
        if args.output:
            print('Full report:', args.output.resolve())
    except (ValueError, TypeError, KeyError, OSError) as exc:
        parser.exit(2, f'Pipeline input/output error: {exc}\n')
    if report['pipeline_status'] in {'BLOCKED', 'ERROR', 'COMPLETE_WITH_ERRORS'}:
        parser.exit(1)


if __name__ == '__main__':
    main()
