import unittest
from dataclasses import replace
from hashlib import sha256
import json
from protolab.harness import Policy
from protolab.pipeline import DemoBackend, FixedPipeline


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.policy = Policy('test', 3, 20, .7)
        self.request = dict(target_sequence='ACDEFGHIK', target_confirmed=True,
                            target_region=[2], intended_use='test', constraints_confirmed=True)

    def test_demo_end_to_end_and_provenance(self):
        report = FixedPipeline(self.policy, DemoBackend()).run(self.request)
        self.assertEqual(report['pipeline_status'], 'COMPLETE')
        self.assertEqual(len(report['candidates']), 100)
        self.assertEqual(len(report['selected_for_prediction']), 10)
        self.assertEqual(len(report['demo_recommendations']), 5)
        self.assertEqual(report['recommendations'], [])
        for row in report['candidates'][:10]:
            for e in row['outcome']['evidence']:
                raw = report['artifacts'][e['artifact_uri'].split('/')[-1]]
                self.assertEqual(e['artifact_sha256'], sha256(json.dumps(raw, sort_keys=True, allow_nan=False).encode()).hexdigest())
        self.assertEqual(report['candidates'][5]['decision']['decision'], 'REJECT')
        self.assertEqual(report['candidates'][6]['decision']['state'], 'UNCERTAIN')

    def test_live_fails_closed(self):
        report = FixedPipeline(self.policy).run(self.request)
        self.assertEqual(report['pipeline_status'], 'BLOCKED')
        self.assertEqual(report['recommendations'], [])

    def test_readiness_prevents_tool_calls(self):
        class Forbidden(DemoBackend):
            def generate(self, request, count):
                raise AssertionError('Must not run')
        report = FixedPipeline(self.policy, Forbidden()).run({})
        self.assertEqual(report['pipeline_status'], 'NEED_INFO')
        self.assertEqual(len(report['events']), 1)

    def test_invalid_generation_never_predicts(self):
        class Duplicate(DemoBackend):
            def generate(self, request, count):
                return [dict(id='x', sequence='ACDE', generation_complete=True)] * 2
            def predict(self, *args):
                raise AssertionError('Must not run')
        report = FixedPipeline(self.policy, Duplicate()).run(self.request)
        self.assertEqual(report['pipeline_status'], 'ERROR')
        self.assertFalse(any(e['stage'] == 'PREDICTION' for e in report['events']))

    def test_timeout_isolated_and_no_retry(self):
        class Timeout(DemoBackend):
            calls = 0
            def predict(self, request, candidate):
                self.calls += 1
                if candidate['id'] == 'DEMO-001':
                    raise TimeoutError()
                return super().predict(request, candidate)
        backend = Timeout()
        report = FixedPipeline(self.policy, backend).run(self.request)
        self.assertEqual(backend.calls, 10)
        self.assertEqual(report['pipeline_status'], 'COMPLETE_WITH_ERRORS')
        self.assertEqual(report['candidates'][0]['outcome']['reasons'], ('TOOL_TIMEOUT',))
        self.assertNotIn('DEMO-001', report['demo_recommendations'])

    def test_bad_metrics_fail_closed(self):
        class Bad(DemoBackend):
            def predict(self, request, candidate):
                data = super().predict(request, candidate)
                data['metrics']['invented_affinity'] = .99
                return data
        report = FixedPipeline(self.policy, Bad()).run(self.request)
        self.assertEqual(report['demo_recommendations'], [])
        self.assertEqual(report['artifacts'], {})
        self.assertEqual(report['pipeline_status'], 'COMPLETE_WITH_ERRORS')

    def test_demo_does_not_supply_md(self):
        report = FixedPipeline(replace(self.policy, require_md=True), DemoBackend()).run(self.request)
        self.assertEqual(report['demo_recommendations'], [])


if __name__ == '__main__':
    unittest.main()
