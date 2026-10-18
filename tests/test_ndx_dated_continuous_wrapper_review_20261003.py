"""Independent diagnostic adapter checks on synthetic saved inputs only."""
from copy import deepcopy
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import tempfile
import unittest
import test_ndx_dated_continuous_weight_diagnostic_20261003 as owner

m=owner.m


class Review(unittest.TestCase):
    def test_exact_quotes_and_raw_weights_are_forwarded_not_engine_normalized(self):
        docs,refs=owner.fixture();inp=docs['inputs']['inputs'];t=inp['candidate'];sid=t['original_security_order'][0]
        n=Fraction(2,3);v=float(n)
        t['exact_quote_conversion_evidence'][sid][10]['close'].update(exact='2/3',value=v,float_hex=v.hex())
        inp['candidate_engine_normalization_evidence']['effective_weights']={sid:999}
        calls=[]
        core=SimpleNamespace(diagnose_continuous_weights=lambda **kw:calls.append(kw) or {'synthetic':True})
        result=m.assemble(docs,refs,core)
        self.assertEqual(len(calls),2)
        self.assertEqual(calls[0]['nominal_quotes'][sid][10]['nominal_close_exact'],dict(numerator='2',denominator='3'))
        self.assertEqual(calls[0]['positions'][0]['target_weight'],t['schedule'][0]['targets'][sid]['target_weight'])
        self.assertEqual(result['original_task_preserved'],inp['original_task'])
        self.assertTrue(all(result[k] is False for k in m.FLAGS))

    def test_zero_not_deleted_and_action_or_alias_tamper_rejected(self):
        docs,refs=owner.fixture();inp=docs['inputs']['inputs'];t=inp['candidate'];sid=t['original_security_order'][0]
        t['schedule'][0]['targets'][sid]['target_weight']=0
        inp['original_fit_result']['targets'][sid]['target_weight']=0
        a=m.project_track(inp,'candidate',refs['inputs'])
        self.assertEqual(len(a['positions']),len(t['original_security_order']))
        self.assertEqual(a['positions'][0]['target_weight'],0)
        for kind in ('alias','action','date'):
            docs,refs=owner.fixture();inp=docs['inputs']['inputs'];t=inp['candidate'];sid=t['original_security_order'][0]
            if kind=='alias':t['schedule'][0]['targets'][sid]['ticker']='MISMATCH'
            elif kind=='action':t['corporate_actions']=t['corporate_actions'][1:]
            else:t['exact_quote_conversion_evidence'][sid][-1]['session']='2026-09-22'
            with self.assertRaises(ValueError):m.project_track(inp,'candidate',refs['inputs'])

    def test_receipt_mismatch_before_compute_and_residue_before_load(self):
        docs,refs=owner.fixture();docs=deepcopy(docs)
        docs['readback']['inputs_reference']['sha256']='b'*64
        with patch.object(owner.core,'diagnose_continuous_weights') as compute:
            with self.assertRaises(ValueError):m.assemble(docs,refs,owner.core)
            compute.assert_not_called()
        with tempfile.TemporaryDirectory() as tmp,patch.object(m,'OUTPUT',Path(tmp)),patch.object(m,'load_inputs') as load:
            (Path(tmp)/'started.json').write_text('{}')
            with self.assertRaises(ValueError):m.run(execute=True)
            load.assert_not_called()
        with self.assertRaises(ValueError):m.guard({str(m.SOURCE):'0'*64})


if __name__=='__main__':unittest.main()
