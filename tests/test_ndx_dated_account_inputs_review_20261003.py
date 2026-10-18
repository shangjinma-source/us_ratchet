"""Independent source-bound input projection checks; no actual task consumption."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import test_ndx_dated_account_inputs_20261003 as owner

m=owner.core


class Review(unittest.TestCase):
    def test_effective_weights_match_saved_sorted_schedule_without_rewriting(self):
        a,docs=owner.documents()
        sids=list(a['task']['numerical_identity']['selected'])
        a['fit_result']['targets'][sids[0]]['target_weight']=.5000000000000001
        a['fit_result']['targets'][sids[1]]['target_weight']=.5000000000000001
        before=deepcopy(a)
        out=m.project(owner.pure,a['task'],dict(owner.REF,json_pointer='/task'),a['fit_result'],owner.REF,docs)
        e=out['inputs']['candidate_engine_normalization_evidence']
        self.assertEqual(e['effective_weights'],dict.fromkeys(sids,.5))
        self.assertEqual(a,before)
        saved=out['inputs']['candidate']['schedule'][0]['targets']
        self.assertEqual([saved[s]['target_weight'] for s in sids],[.5000000000000001]*2)
        self.assertEqual(out['inputs']['original_incumbent_definition'],a['incumbent_securities'])
        self.assertTrue(all(out[k] is False for k in m.FLAGS))

    def test_zero_keeps_slot_and_blocks_dispatch_without_normalization(self):
        a,docs=owner.documents();sids=list(a['task']['numerical_identity']['selected'])
        a['fit_result']['targets'][sids[0]]['target_weight']=0
        a['fit_result']['targets'][sids[1]]['target_weight']=1
        out=m.project(owner.pure,a['task'],owner.REF,a['fit_result'],owner.REF,docs)['inputs']
        self.assertEqual(set(out['candidate']['schedule'][0]['targets']),set(sids))
        self.assertEqual(out['candidate']['engine_input_compatibility']['status'],'BLOCKED_NONPOSITIVE_TARGET')
        self.assertIsNone(out['candidate_engine_normalization_evidence']['effective_weights'])
        self.assertTrue(out['candidate_engine_normalization_evidence']['blocked_nonpositive'])

    def test_event_parent_and_date_cannot_be_rebound(self):
        for kind in ('parent','date','ratio','flag'):
            a,docs=owner.documents();row=docs['channels']['rows'][0]
            source=row['channel']['bridge_row_preserved']['event_policy_bridge']['events'][0]['specific_event_reference']
            if kind=='parent':source['parent']=dict(source['parent'],sha256='b'*64)
            elif kind=='date':docs['registry']['events'][2]['first_adjusted_trading_date']='2026-04-01'
            elif kind=='ratio':docs['registry']['events'][2]['new_shares']=True
            else:docs['registry']['events'][2]['specific_simple_share_split_event_supported']=1
            with self.assertRaises(ValueError):m.project(owner.pure,a['task'],owner.REF,a['fit_result'],owner.REF,docs)

    def test_residue_and_forged_common_block_before_consumption(self):
        tid='a'*64
        with tempfile.TemporaryDirectory() as tmp,patch.object(m,'OUTPUT',Path(tmp)),patch.object(m,'load_common') as load:
            (Path(tmp)/tid).mkdir();(Path(tmp)/tid/'failure.json').write_text('{}')
            with self.assertRaises(ValueError):m.run(tid,owner.REF,execute=True)
            load.assert_not_called()
        with patch.object(m,'consume') as consume:
            with self.assertRaises(ValueError):m.run(tid,owner.REF,execute=True,common={'ordered_task_ids':[tid]})
            consume.assert_not_called()
        with self.assertRaises(ValueError):m.guard({str(m.SOURCE):'0'*64})


if __name__=='__main__':unittest.main()
