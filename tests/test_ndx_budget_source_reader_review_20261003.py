from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_multidecision_scoring_budget_independent_readback_20261003 as reader
from test_ndx_multidecision_scoring_budget_independent_readback_20261003 import fixture


class Review(unittest.TestCase):
    def test_qualification_references_and_final_security_are_not_optional(self):
        docs, refs, channels, plan = fixture()
        reader.inspect_source_projection(plan, docs, refs, iter(channels))
        attacks = [
            lambda d,r,c,p: p['decision_inputs_preserved'][5]['qualifications'][76]['history_reference'].update(json_pointer='/decisions/0'),
            lambda d,r,c,p: p['decision_inputs_preserved'][0]['incumbent_fee_reference'].update(json_pointer='/scoring_inputs/original_weights'),
            lambda d,r,c,p: d['history_audit']['rows'][0].update(index=False),
            lambda d,r,c,p: d['mdv_report'].update(independently_checked_security_periods=462.0),
            lambda d,r,c,p: c.append(deepcopy(c[-1])),
        ]
        for attack in attacks:
            # Separate copies prevent fixture aliases from changing the expected parent.
            d,r,c,p = deepcopy(docs),deepcopy(refs),deepcopy(channels),deepcopy(plan)
            attack(d,r,c,p)
            with self.assertRaises(ValueError):
                reader.inspect_source_projection(p,d,r,iter(c))

    def test_new_fitter_cannot_be_old_baseline_or_authorize_current_worker(self):
        docs, refs, _, _ = fixture()
        attacks = [
            lambda d: d['rolling_fitter_manifest'].update(source_hashes=deepcopy(d['fitter_container']['plan']['fitter_source_hashes'])),
            lambda d: d['rolling_fitter_manifest']['required_worker_environment'].update(sys_flags_hash_randomization=False),
            lambda d: d['rolling_fitter_manifest'].update(execution_authorized=0),
            lambda d: d['target_audit'].update(reader_sha256='e'*64),
        ]
        for attack in attacks:
            changed=deepcopy(docs);attack(changed)
            with self.assertRaises(ValueError):reader.inspect_parent_links(changed,refs)

    def test_guard_detects_late_failure_and_private_code_has_no_producer_import(self):
        with tempfile.TemporaryDirectory() as temporary:
            base=Path(temporary);parent=base/'parent';parent.mkdir()
            for name in ('started.json','raw_plan.json','plan.json','publication.json'):
                (parent/name).write_bytes(b'{}')
            source=base/'source';source.mkdir();file=source/'input';file.write_bytes(b'original')
            sources={str(file):reader.sha(b'original')}
            with patch.object(reader,'PARENT',parent):
                reader.guard(sources)
                (source/'failure.json').write_bytes(b'{}')
                with self.assertRaises(ValueError):reader.guard(sources)
            with patch.object(reader,'PLAN_SHA',None),patch.object(Path,'read_bytes',side_effect=AssertionError('pending cannot read')):
                with self.assertRaises(ValueError):reader.readback(execute=True)
        sources={};core=reader.private_inspector(sources)
        self.assertTrue(callable(core.inspect_scoring_budget))
        self.assertEqual(set(sources),{str(reader.INSPECTOR),str(reader.ROOT/'backtest/ndx_issuer_combination_index_research.py')})


if __name__=='__main__':unittest.main()
