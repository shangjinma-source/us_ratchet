from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from unittest.mock import patch
from scripts import run_continuous_guided_weak_no_add as runner
import test_continuous_guided_cost_stress as fixture


class WeakNoAddRunnerTests(unittest.TestCase):
    def test_prepare_rejects_changed_contract_hash(self):
        with TemporaryDirectory() as directory,patch.object(runner,'ROOT',Path(directory)):
            contract=Path(directory)/runner.CONTRACT;contract.parent.mkdir(parents=True)
            contract.write_text('{}')
            sealed={'source_hashes':{}}
            with patch.object(runner,'prepare_sealed_inputs',return_value=({}, {}, None, sealed)), \
                    patch.object(runner,'SEALED_RECEIPT_SHA',runner.canonical_hash(sealed)):
                with self.assertRaisesRegex(ValueError,'BINDING_HASH_MISMATCH:research_contracts'):
                    runner.prepare_run()
            self.assertFalse((Path(directory)/runner.OUTPUT).exists())

    def test_prepare_rejects_changed_comparator_approval_hash(self):
        with TemporaryDirectory() as directory,patch.object(runner,'ROOT',Path(directory)):
            contract=Path(directory)/runner.CONTRACT;contract.parent.mkdir(parents=True)
            contract.write_text(json.dumps(dict(scenarios=runner.SCENARIOS,initial_cash='20000',candidate=runner.ARM)))
            approval=Path(directory)/runner.APPROVAL;approval.parent.mkdir(parents=True)
            approval.write_text('{}')
            sealed={'source_hashes':{}}
            with patch.object(runner,'prepare_sealed_inputs',return_value=({}, {}, None, sealed)), \
                    patch.object(runner,'SEALED_RECEIPT_SHA',runner.canonical_hash(sealed)), \
                    patch.object(runner,'CONTRACT_SHA',runner.hashlib.sha256(contract.read_bytes()).hexdigest()):
                with self.assertRaisesRegex(ValueError,'BINDING_HASH_MISMATCH:outputs'):
                    runner.prepare_run()
            self.assertFalse((Path(directory)/runner.OUTPUT).exists())

    def setup_run(self,directory):
        root=Path(directory);(root/'source').write_text('fixed')
        pins={'source':runner.hashlib.sha256((root/'source').read_bytes()).hexdigest()}
        comparison={'arms':{scenario:{arm:dict(final_equity='20000',maximum_close_drawdown='1/5')
            for arm in ('continuous32','continuous32_half')} for scenario in runner.SCENARIOS}}
        return {'ohlc':{}},{'mutable':[]},None,dict(source_hashes=pins,comparison=comparison)

    def test_preflight_and_hash_gate_do_not_execute_or_write(self):
        with TemporaryDirectory() as directory,patch.object(runner,'ROOT',Path(directory)):
            prepared=self.setup_run(directory)
            with patch.object(runner,'prepare_run',return_value=prepared),patch.object(runner,'run_candidate') as execute:
                result=runner.run_once();self.assertEqual(result['status'],'PREFLIGHT_ONLY_NO_SEARCH')
                with self.assertRaises(ValueError):runner.run_once(execute=True,expected_receipt_sha256='wrong')
                execute.assert_not_called();self.assertFalse((Path(directory)/runner.OUTPUT).exists())

    def test_only_two_new_candidate_paths_no_comparator_replay(self):
        with TemporaryDirectory() as directory,patch.object(runner,'ROOT',Path(directory)):
            prepared=self.setup_run(directory);seen=[]
            def candidate(**kwargs):
                self.assertEqual(kwargs['assembled']['mutable'],[])
                kwargs['assembled']['mutable'].append('own');seen.append(kwargs['scenario'])
                return dict(status='COMPLETE')
            with patch.object(runner,'prepare_run',return_value=prepared),patch.object(runner,'run_candidate',side_effect=candidate), \
                    patch.object(runner,'summarize',return_value=dict(final_equity='20001',maximum_close_drawdown='1/10')):
                result=runner.run_once(execute=True,expected_receipt_sha256=runner.canonical_hash(prepared[3]))
                self.assertEqual(seen,list(runner.SCENARIOS));self.assertEqual(result['status'],'COMPLETE_PENDING_INDEPENDENT_REVIEW')
                saved=json.loads((Path(directory)/runner.OUTPUT/'comparison.json').read_text())
                self.assertTrue(saved['both_scenarios_joint_improvement'])
                with self.assertRaises(FileExistsError):runner.run_once(execute=True)
                with self.assertRaises(ValueError):runner.run_once(output_directory='other',execute=True)

    def test_failed_or_partial_output_never_retried(self):
        with TemporaryDirectory() as directory,patch.object(runner,'ROOT',Path(directory)):
            prepared=self.setup_run(directory)
            with patch.object(runner,'prepare_run',return_value=prepared),patch.object(runner,'run_candidate',side_effect=RuntimeError('stop')):
                with self.assertRaises(RuntimeError):runner.run_once(execute=True,expected_receipt_sha256=runner.canonical_hash(prepared[3]))
                saved=json.loads((Path(directory)/runner.OUTPUT/'terminal.json').read_text())
                self.assertFalse(saved['automatic_retry_allowed'])
                with self.assertRaises(FileExistsError):runner.run_once(execute=True)

    def test_synthetic_candidate_uses_named_binding_and_fixed_20000(self):
        a,b,resolver=fixture.CostStressTests().data();original=deepcopy(a)
        pins={'new-reviewed-contract':'b'*64,runner.CONTRACT:runner.CONTRACT_SHA}
        result=runner.run_candidate(scenario='fee1_slippage10',assembled=a,ohlc=b,resolver=resolver,pins=pins,progress=None,run_receipt_sha256='c'*64)
        self.assertEqual(result['status'],'COMPLETE')
        self.assertEqual(result['cost_stress_arm'],runner.ARM)
        self.assertEqual(result['cost_stress_binding']['initial_cash'],'20000')
        self.assertEqual(result['research_run_binding']['receipt_sha256'],'c'*64)
        self.assertEqual(result['research_run_binding']['contract_sha256'],runner.CONTRACT_SHA)
        self.assertEqual(result['selection_account_states'][0]['account_state']['cash'],'20000')
        self.assertEqual(result['selection_account_states'][0]['source_hashes']['new-reviewed-contract'],'b'*64)
        self.assertEqual(a,original)

    def test_source_change_after_candidate_stops_and_preserves_result(self):
        with TemporaryDirectory() as directory,patch.object(runner,'ROOT',Path(directory)):
            prepared=self.setup_run(directory)
            def changed(**kwargs):
                (Path(directory)/'source').write_text('changed')
                return dict(status='COMPLETE')
            with patch.object(runner,'prepare_run',return_value=prepared),patch.object(runner,'run_candidate',side_effect=changed) as calls:
                with self.assertRaisesRegex(ValueError,'SOURCE_DRIFT'):
                    runner.run_once(execute=True,expected_receipt_sha256=runner.canonical_hash(prepared[3]))
                self.assertEqual(calls.call_count,1)
                self.assertTrue((Path(directory)/runner.OUTPUT/('slippage5__'+runner.ARM)/'outcome.json').exists())


if __name__=='__main__':unittest.main()
