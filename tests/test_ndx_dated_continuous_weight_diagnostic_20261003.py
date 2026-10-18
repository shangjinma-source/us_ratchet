from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_dated_continuous_weight_diagnostic_20261003 as m
from backtest import ndx_dated_continuous_weight_diagnostic_research as core
from test_ndx_dated_account_input_readback_data_review_20261003 import fixture as input_fixture

def fixture():
    d,_=input_fixture();d['source_hashes']={};refs={k:dict(path=k+'.json',sha256='a'*64) for k in m.BOUND}
    p=dict(schema='DATED_ACCOUNT_INPUT_PUBLICATION_V1',status='PUBLISHED_CONDITIONAL_INPUT_NOT_EXECUTED',inputs_reference=refs['inputs'],source_hashes={},point_in_time_verified=False,promotion_allowed=False,account_executed=False)
    a=dict(schema=m.READBACK_SCHEMA,status='PASS',inputs_reference=refs['inputs'],publication_reference=refs['publication'],point_in_time_verified=False,promotion_allowed=False,account_executed=False)
    return dict(inputs=d,publication=p,readback=a),refs

class Tests(unittest.TestCase):
    def test_two_tracks_original_weights_and_exact_fraction_quotes(self):
        docs,refs=fixture();before=deepcopy(docs);r=m.assemble(docs,refs,core)
        self.assertEqual(set(r['tracks']),{'candidate','incumbent'});self.assertEqual(len(r['tracks']['candidate']['path']),127)
        self.assertEqual([p['target_weight'] for p in r['tracks']['incumbent']['positions_preserved']],[.12500000000000003]*8)
        self.assertEqual(len(r['tracks']['candidate']['split_events_preserved']),2);self.assertEqual(docs,before)
    def test_receipt_flags_weight_and_split_tampering(self):
        for what in ('receipt','flag','weight','float','split'):
            docs,refs=fixture();inp=docs['inputs']['inputs'];track=inp['candidate'];sid=track['original_security_order'][0]
            if what=='receipt':docs['readback']['publication_reference']['sha256']='b'*64;refs=deepcopy(refs);refs['publication']['sha256']='a'*64
            elif what=='flag':docs['readback']['promotion_allowed']=0
            elif what=='weight':track['schedule'][0]['targets'][sid]['target_weight']=.51
            elif what=='float':track['exact_quote_conversion_evidence'][sid][1]['open']['value']=101.
            else:track['corporate_actions']=[]
            with self.subTest(what=what),self.assertRaises(ValueError):m.assemble(docs,refs,core)
    def test_pending_no_read_and_failure_immutable(self):
        with patch.object(m,'BOUND',dict.fromkeys(m.BOUND)),patch.object(Path,'read_bytes') as read:
            with self.assertRaises(ValueError):m.load_inputs()
            read.assert_not_called()
        docs,refs=fixture()
        with tempfile.TemporaryDirectory() as tmp,patch.object(m,'OUTPUT',Path(tmp)/'out'),patch.object(m,'load_inputs',return_value=(docs,refs,{},core)),patch.object(m,'guard'),patch.object(m,'assemble',side_effect=ValueError('synthetic')):
            with self.assertRaises(ValueError):m.run(execute=True)
            self.assertEqual({p.name for p in m.OUTPUT.iterdir()},{'started.json','failure.json'})
            with self.assertRaises(ValueError):m.run(execute=True)
    def test_publication_then_source_drift_retains_failure(self):
        docs,refs=fixture();calls=[]
        def guard(s):
            calls.append(1)
            if len(calls)==3:raise ValueError('after publication source drift')
        with tempfile.TemporaryDirectory() as tmp,patch.object(m,'OUTPUT',Path(tmp)/'out'),patch.object(m,'load_inputs',return_value=(docs,refs,{},core)),patch.object(m,'guard',side_effect=guard):
            with self.assertRaises(ValueError):m.run(execute=True)
            self.assertTrue((m.OUTPUT/'publication.json').exists());self.assertTrue((m.OUTPUT/'failure.json').exists())

if __name__=='__main__':unittest.main()
