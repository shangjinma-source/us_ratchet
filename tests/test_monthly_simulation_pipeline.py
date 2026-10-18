import unittest
from unittest.mock import patch

from scripts.run_monthly_simulation_pipeline import run


class PipelineSequencingTests(unittest.TestCase):
    arguments = dict(coordinator_config='coordinator', coordinator_sha256='c',
                     bootstrap_config='bootstrap', bootstrap_sha256='b',
                     policy_path='policy', policy_sha256='p', output_directory='new-evidence')

    def test_waiting_account_or_session_never_starts_capture(self):
        for status in ('WAITING_ACCOUNT', 'WAITING_SESSION_CLOSE'):
            with self.subTest(status=status), patch('scripts.run_monthly_simulation_pipeline.coordinate',
                    return_value={'status':'PREFLIGHT_ONLY'}) as coordinator, \
                    patch('scripts.run_monthly_simulation_pipeline.collect', return_value={'status':status}):
                self.assertEqual(run(**self.arguments, execute=True)['status'], status)
                self.assertEqual(coordinator.call_count, 1)
                self.assertNotIn('execute', coordinator.call_args.kwargs)

    def test_unresolved_collected_evidence_never_reaches_publication(self):
        with patch('scripts.run_monthly_simulation_pipeline.coordinate',
                   side_effect=[{'status':'PREFLIGHT_ONLY'}, {'status':'WAITING_REVIEW'}]) as coordinator, \
                patch('scripts.run_monthly_simulation_pipeline.collect',
                   side_effect=[{'status':'PREFLIGHT_ONLY'}, {'status':'WAITING_REVIEW', 'reason':'KNOWN_SOURCE_UNRESOLVED'}]):
            result = run(**self.arguments, execute=True)
            self.assertEqual(result['phase'], 'EVIDENCE_COLLECTION')
            self.assertEqual(coordinator.call_count, 2)
            self.assertTrue(all('auto_review_inputs' not in call.kwargs for call in coordinator.call_args_list))

    def test_collector_actual_pins_are_forwarded_after_training(self):
        calls = []
        def coordinator(**arguments):
            calls.append(('coordinate', arguments))
            return {'status': 'MONTHLY_RUNTIME_PUBLISHED' if 'auto_review_inputs' in arguments else
                    'WAITING_REVIEW' if arguments.get('execute') else 'PREFLIGHT_ONLY'}
        def collector(**arguments):
            calls.append(('collect', arguments))
            return {'status':'EVIDENCE_READY', 'inputs_path':'actual/input.json', 'inputs_sha256':'actual-sha'} if arguments.get('execute') else {'status':'PREFLIGHT_ONLY'}
        with patch('scripts.run_monthly_simulation_pipeline.coordinate', side_effect=coordinator), \
                patch('scripts.run_monthly_simulation_pipeline.collect', side_effect=collector):
            self.assertEqual(run(**self.arguments, execute=True)['status'], 'MONTHLY_RUNTIME_PUBLISHED')
        self.assertEqual([name for name, _ in calls], ['coordinate','collect','coordinate','collect','coordinate'])
        self.assertEqual(calls[-1][1]['auto_review_inputs'], 'actual/input.json')
        self.assertEqual(calls[-1][1]['auto_review_inputs_sha256'], 'actual-sha')

    def test_default_never_executes_even_if_ready(self):
        with patch('scripts.run_monthly_simulation_pipeline.coordinate', return_value={'status':'PREFLIGHT_ONLY'}) as coordinator, \
                patch('scripts.run_monthly_simulation_pipeline.collect', return_value={'status':'PREFLIGHT_ONLY'}) as collector:
            result = run(**self.arguments)
            self.assertEqual(result['status'], 'PREFLIGHT_ONLY')
            self.assertNotIn('execute', coordinator.call_args.kwargs)
            self.assertNotIn('execute', collector.call_args.kwargs)


if __name__ == '__main__':
    unittest.main()
