from copy import deepcopy
from decimal import localcontext,Inexact
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_dated_per_task_continuous_independent_readback_20261003 as m
from test_ndx_dated_per_task_continuous_20261003 import fixtures,core as synthetic_producer,numeric

def fixture(zero=False):
    tid,d,refs,control=fixtures()
    if zero:
        for sid,w in zip(d['inputs']['inputs']['candidate']['original_security_order'],[0.,1.]):
            d['inputs']['inputs']['candidate']['schedule'][0]['targets'][sid]['target_weight']=w;d['inputs']['inputs']['original_fit_result']['targets'][sid]['target_weight']=w
    result=synthetic_producer.assemble(tid,d,refs,control,numeric);result['source_hashes']={str(m.PRODUCER):m.PRODUCER_SHA}
    r=dict(diagnostic=dict(path='diagnostic.json',sha256='a'*64),publication=dict(path='result_publication.json',sha256='a'*64),inputs=refs['inputs'],input_publication=refs['publication'],input_readback=refs['readback'])
    pub=dict(schema='DATED_PER_TASK_CONTINUOUS_PUBLICATION_V1',status='PUBLISHED_CANDIDATE_DIAGNOSTIC_WITH_IMMUTABLE_CONTROL_REFERENCE',diagnostic_reference=r['diagnostic'],source_hashes=result['source_hashes'],**dict.fromkeys(m.FALSE,False))
    started=dict(schema='DATED_PER_TASK_CONTINUOUS_STARTED_V1',task_id=tid,planned_candidate_core_call_count=1,planned_control_core_call_count=0,input_references=refs,source_hashes=result['source_hashes'],immutable_control_reference=m.CONTROL,**dict.fromkeys(m.FALSE,False))
    ca=dict(schema='DATED_CONTINUOUS_INDEPENDENT_READBACK_V1',status='PASS',diagnostic_reference=m.CONTROL,publication_reference=m.CONTROL_PUB,**dict.fromkeys(('point_in_time_verified','promotion_allowed','account_executed','fit_performed'),False))
    docs=dict(diagnostic=result,publication=pub,started=started,inputs=d['inputs'],input_publication=d['publication'],input_readback=d['readback'],control_audit=ca,control_document=control)
    return tid,docs,r

class Tests(unittest.TestCase):
    def test_independent_full_candidate_split_zero_and_context(self):
        tid,d,r=fixture(True);before=deepcopy(d);m.validate_links(tid,d,r)
        with localcontext() as c:
            c.prec=2;c.traps[Inexact]=True;out=m.inspect_candidate(d['diagnostic']['candidate'],d['inputs']['inputs'],r['inputs'])
        self.assertEqual(out['point_count'],127);self.assertEqual(out['zero_weight_count'],1);self.assertEqual(out['split_event_count'],2);self.assertEqual(d,before)
    def test_double_split_rebalance_metadata_and_zero_drops_rejected(self):
        for mode in ('quantity','display','event','weight','dropzero'):
            tid,d,r=fixture(True);t=d['diagnostic']['candidate']
            if mode=='quantity':t['path'][-1]['security_rows'][1]['fractional_quantity']['numerator']='999'
            elif mode=='display':t['path'][3]['normalized_value_display']='1'
            elif mode=='event':t['split_events_preserved'].pop()
            elif mode=='weight':t['positions_preserved'][1]['target_weight']=.99
            else:t['path'][5]['security_rows'].pop(0)
            with self.subTest(mode=mode),self.assertRaises(ValueError):m.inspect_candidate(t,d['inputs']['inputs'],r['inputs'])
    def test_control_unchanged_and_authority_exact(self):
        for mode in ('control','receipt','call','flag'):
            tid,d,r=fixture()
            if mode=='control':d['inputs']['inputs']['incumbent']['minimum_cash_buffer_usd']=99
            elif mode=='receipt':d['diagnostic']['immutable_control_readback_reference']=dict(m.CONTROL_AUDIT,sha256='b'*64)
            elif mode=='call':d['diagnostic']['control_core_call_count']=False
            else:d['diagnostic']['integer_rejection_overridden']=True
            with self.subTest(mode=mode),self.assertRaises(ValueError):m.validate_links(tid,d,r)
    def test_oldtask_and_residual_namespace_early_rejected(self):
        with patch.object(m,'guard') as guard:
            with self.assertRaises(ValueError):m.readback(m.FIRST,{},execute=True)
            guard.assert_not_called()
        with tempfile.TemporaryDirectory() as tmp,patch.object(m,'BASE',Path(tmp)),patch.object(m,'guard') as guard:
            folder=Path(tmp)/('a'*64);folder.mkdir();(folder/'failure.json').write_text('{}')
            with self.assertRaises(ValueError):m.readback('a'*64,dict(path=str(folder/'publication.json'),sha256='b'*64),execute=True)
            guard.assert_not_called()

if __name__=='__main__':unittest.main()
