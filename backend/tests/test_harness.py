import unittest
from pathlib import Path
from dataclasses import replace
from protolab.harness import BinderHarness, BoundedExecutor, Evidence, Policy, run_binder_round
from protolab import ProjectRecord, load_protocol, build_instructions


class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.policy = Policy('test-only', 3, 20, 0.7)
        self.h = BinderHarness(self.policy)
        self.request = dict(target_sequence='ACDEFGHIK', target_confirmed=True,
                            target_region=[2, 3], intended_use='research', constraints_confirmed=True)
        self.candidate = dict(id='B1', sequence='ACDE', generation_complete=True)

    def evidence(self, metric, value, kind, candidate=None):
        c = candidate or self.candidate
        return Evidence(metric + c['id'], c['id'], self.h.scope(self.request, c), kind,
                        metric, value, 'test-adapter', '1', 'test-run',
                        'fixture://result', 'a' * 64)

    def complete(self):
        return [self.evidence(*x) for x in [
            ('interface_confidence', .8, 'structure_prediction'),
            ('site_match', True, 'structure_analysis'),
            ('replicates_consistent', True, 'replicate_analysis'),
            ('selectivity_pass', True, 'off_target_assessment'),
            ('developability_pass', True, 'developability_assessment')]]

    def run_report(self, evidence=(), **kwargs):
        return self.h.run(self.request, [self.candidate], evidence, **kwargs)

    def test_missing_target_blocks_generation(self):
        report = self.h.run({}, [])
        self.assertEqual(report['readiness']['state'], 'NEED_INFO')
        self.assertIn('TARGET_MISSING', report['readiness']['reasons'])
        self.assertEqual(report['candidates'], [])

    def test_bad_sequence_and_region(self):
        self.request.update(target_sequence='ACX', target_region=[99])
        reasons = self.run_report()['readiness']['reasons']
        self.assertIn('INVALID_TARGET_SEQUENCE', reasons)
        self.assertIn('CONFLICTING_CONSTRAINTS', reasons)

    def test_missing_evidence_never_passes(self):
        report = self.run_report()
        self.assertEqual(report['recommendations'], [])
        self.assertEqual(report['candidates'][0]['decision']['state'], 'UNCERTAIN')

    def test_complete_prediction_is_review_only(self):
        report = self.run_report(self.complete())
        self.assertEqual(report['recommendations'], ['B1'])
        row = report['candidates'][0]
        self.assertEqual(row['decision']['decision'], 'SHORTLIST_FOR_EXPERIMENT_REVIEW')
        self.assertNotIn('STABLE_INTERFACE', row['outcome']['reasons'])
        self.assertFalse(report['generation_complete'])

    def test_no_offtarget_evidence_is_unknown(self):
        es = [e for e in self.complete() if e.metric != 'selectivity_pass']
        report = self.run_report(es)
        self.assertEqual(report['recommendations'], [])
        self.assertIn('NEEDS_OFF_TARGET_VALIDATION', report['candidates'][0]['decision']['reasons'])

    def test_wrong_site_overrides_good_confidence(self):
        es = [replace(e, value=False) if e.metric == 'site_match' else e for e in self.complete()]
        row = self.run_report(es)['candidates'][0]
        self.assertEqual(row['outcome']['state'], 'FAIL')
        self.assertEqual(row['decision']['decision'], 'REJECT')

    def test_stale_input_rejected(self):
        es = self.complete()
        self.request['target_region'] = [4]
        with self.assertRaisesRegex(ValueError, 'Stale'):
            self.run_report(es)

    def test_md_cannot_be_claimed_by_boltz(self):
        e = self.evidence('interface_retained', True, 'structure_prediction')
        with self.assertRaisesRegex(ValueError, 'kind'):
            self.run_report([e])

    def test_md_requirement_cannot_be_skipped(self):
        self.h = BinderHarness(replace(self.policy, require_md=True))
        report = self.run_report(self.complete())
        self.assertEqual(report['recommendations'], [])
        self.assertIn('SIMULATION_INCONCLUSIVE', report['candidates'][0]['outcome']['reasons'])

    def test_complete_md_and_failed_md(self):
        self.h = BinderHarness(replace(self.policy, require_md=True))
        es = self.complete() + [self.evidence(m, True, 'md_analysis') for m in
                               ('sampling_adequate', 'interface_retained', 'binder_stable')]
        self.assertEqual(self.run_report(es)['recommendations'], ['B1'])
        es[-1] = replace(es[-1], value=False)
        self.assertEqual(self.run_report(es)['recommendations'], [])

    def test_conflicting_results_require_review(self):
        es = self.complete()
        es.append(replace(es[1], id='conflict', value=False))
        row = self.run_report(es)['candidates'][0]
        self.assertEqual(row['outcome']['reasons'], ('CONFLICTING_METRICS',))
        self.assertEqual(row['decision']['decision'], 'HUMAN_REVIEW')

    def test_retries_bounded(self):
        row = self.run_report(retries={'B1': 1})['candidates'][0]
        self.assertEqual(row['decision']['decision'], 'HUMAN_REVIEW')

    def test_timeout_is_not_biological_failure(self):
        row = self.run_report(errors={'B1': 'TOOL_TIMEOUT'})['candidates'][0]
        self.assertEqual(row['outcome']['state'], 'ERROR')
        self.assertNotEqual(row['decision']['decision'], 'REJECT')

    def test_invalid_evidence_values(self):
        for v in (float('nan'), float('inf'), -1, 88, True, '0.8'):
            with self.subTest(v=v), self.assertRaises(ValueError):
                self.run_report([self.evidence('interface_confidence', v, 'structure_prediction')])

    def test_provenance_required(self):
        with self.assertRaises(ValueError):
            self.run_report([replace(self.complete()[0], artifact_uri='')])

    def test_unknown_candidate_and_duplicate_evidence(self):
        es = self.complete()
        for invalid in ([replace(es[0], candidate_id='B2')], es + [es[0]]):
            with self.assertRaises(ValueError):
                self.run_report(invalid)

    def test_duplicate_sequences_rejected(self):
        c2 = dict(self.candidate, id='B2')
        report = self.h.run(self.request, [self.candidate, c2])
        self.assertIn('DUPLICATE_CANDIDATE', report['candidates'][1]['qc']['reasons'])

    def test_budget_and_ids(self):
        with self.assertRaises(ValueError):
            self.h.run(self.request, [self.candidate] * 101)
        with self.assertRaises(ValueError):
            self.h.run(self.request, [self.candidate] * 2)

    def test_selection_cap(self):
        self.h = BinderHarness(replace(self.policy, max_predictions=1, max_recommendations=1))
        report = self.h.run(self.request, [self.candidate, dict(id='B2', sequence='ACDF', generation_complete=True)])
        self.assertEqual(report['selected_for_prediction'], ['B1'])
        self.assertEqual(report['candidates'][1]['decision']['decision'], 'DEFER')

    def test_policy_validation(self):
        for changes in ({'interface_min': float('nan')}, {'max_retries': -1}, {'min_length': 0}, {'forbidden_motifs': ('',)}):
            with self.assertRaises(ValueError):
                replace(self.policy, **changes)

    def test_executor_allowlist_cache_and_budget(self):
        calls = []
        def adapter(payload):
            calls.append(payload)
            return {'status': 'success', 'value': 1}
        executor = BoundedExecutor({'RUN_PREDICTION': adapter})
        executor.execute('RUN_PREDICTION', {'input_hash': 'x'})
        result = executor.execute('RUN_PREDICTION', {'input_hash': 'x'})
        result['value'] = 999
        self.assertEqual(executor.execute('RUN_PREDICTION', {'input_hash': 'x'})['value'], 1)
        self.assertEqual(len(calls), 1)
        with self.assertRaises(ValueError):
            executor.execute('ADVANCE_TO_WET_LAB', {})
        def timeout(payload):
            raise TimeoutError()
        executor = BoundedExecutor({'RUN_PREDICTION': timeout}, max_retries=1)
        self.assertEqual(executor.execute('RUN_PREDICTION', {})['decision'], 'RETRY')
        self.assertEqual(executor.execute('RUN_PREDICTION', {})['decision'], 'HUMAN_REVIEW')
        self.assertEqual(executor.execute('RUN_PREDICTION', {})['reasons'], ['RETRY_BUDGET_EXHAUSTED'])

    def test_record_integration_clears_old_recommendations(self):
        protocol = load_protocol(Path(__file__).parents[2] / 'protocols/binder-screening.json')
        record = ProjectRecord.from_protocol(protocol)
        with self.assertRaises(ValueError):
            build_instructions(protocol.step('decision'), record)
        run_binder_round(record, self.policy, self.request, [self.candidate], self.complete())
        self.assertEqual(record.read('decision').fields['recommendations'], ['B1'])
        self.assertIn('SHORTLIST_FOR_EXPERIMENT_REVIEW', build_instructions(protocol.step('decision'), record))
        run_binder_round(record, self.policy, {}, [])
        self.assertEqual(record.read('decision').fields['recommendations'], [])
        record.write('readiness', {'assessment': 'changed'})
        with self.assertRaises(ValueError):
            build_instructions(protocol.step('decision'), record)


if __name__ == '__main__':
    unittest.main()
