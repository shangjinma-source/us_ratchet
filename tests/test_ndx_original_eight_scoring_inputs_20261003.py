from copy import deepcopy
from pathlib import Path
import tempfile,types,unittest
from unittest.mock import patch
from scripts import ndx_original_eight_scoring_inputs_20261003 as m
from test_ndx_original_eight_scoring_inputs_research import fixture as purefixture

def fixture():
    a=purefixture();refs={k:dict(path='/synthetic/'+k,sha256='a'*64) for k in m.BOUND};rows=[];ar=[]
    for b in a['channel_bindings']:
        if b['coordinate']['ticker']=='TSM':continue
        i=len(rows);r=dict(index=i,coordinate=b['coordinate'],channel_reference=b['channel_reference']);rows.append(r);ar.append(dict(r,inspection=dict(status='PASS',ticker=r['coordinate']['ticker'],window_count=78)))
    for i in range(7,77):
        r=dict(index=i,coordinate=dict(ticker='X'+str(i)),channel_reference=dict(path='x'+str(i),sha256='b'*64));rows.append(r);ar.append(dict(r,inspection=dict(status='PASS',ticker='X'+str(i),window_count=78)))
    false=dict.fromkeys(('point_in_time_verified','fit_performed','execution_authorized','promotion_allowed'),False)
    docs=dict(control=deepcopy(a['original_control']['complete_original_manifest']),index=dict(schema='MULTIDECISION_SCORING_HISTORY_AGGREGATE_V1',security_count=77,rows=rows,source_hashes={}),tsm=dict(schema='TSM_CONTROL_SCORING_HISTORY_DOCUMENT_V1',original_control_preserved=deepcopy(a['original_control']),channel=deepcopy(a['channel_bindings'][4]['channel']),source_hashes={}))
    for role,schema,status,key in [('index','MULTIDECISION_SCORING_HISTORY_PUBLICATION_V1','PUBLISHED_CONDITIONAL_NUMBERS_PENDING_INDEPENDENT_READBACK','index_reference'),('tsm','TSM_CONTROL_SCORING_HISTORY_PUBLICATION_V1','PUBLISHED_CONTROL_NUMBERS_PENDING_INDEPENDENT_READBACK','channel_reference')]:docs[role+'_publication']=dict(schema=schema,status=status,source_hashes={},**{key:refs[role]})
    docs['index_audit']=dict(schema='MULTIDECISION_SCORING_HISTORY_INDEPENDENT_READBACK_V2',status='PASS',reader_sha256='a'*64,index_reference=refs['index'],publication_reference=refs['index_publication'],rows=ar,**false)
    docs['tsm_audit']=dict(schema='TSM_CONTROL_SCORING_HISTORY_INDEPENDENT_READBACK_V1',status='PASS',reader_sha256='a'*64,channel_reference=refs['tsm'],publication_reference=refs['tsm_publication'],arithmetic=dict(ticker='TSM',status='PASS',window_count=78),**false)
    return docs,refs

class Tests(unittest.TestCase):
    def test_original_eight_references_only_and_audit_mismatch(self):
        d,r=fixture();before=deepcopy(d);a=m.prepare_bindings(d,r);self.assertEqual(d,before)
        self.assertEqual([x['coordinate']['ticker'] for x in a['channel_bindings']],m.ORDER)
        self.assertEqual(sum(b['channel'] is None for b in a['channel_bindings']),7)
        for mutate in [lambda x:x['index_audit']['rows'][0]['inspection'].update(ticker='WRONG'),lambda x:x['tsm_audit'].update(status='FAILED'),lambda x:x['index_audit']['rows'][0].update(index=True),lambda x:x['control']['definition']['securities'][0].update(target_weight=.9)]:
            bad=deepcopy(d);mutate(bad)
            with self.assertRaises(ValueError):m.prepare_bindings(bad,r)
    def test_no_retry_after_pure_failure(self):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'out';calls=[]
            def fail(**kw):calls.append(kw);raise ValueError('pure failure')
            with patch.object(m,'OUTPUT',out),patch.object(m,'space'),patch.object(m,'load_inputs',return_value=({}, {}, {}, {},types.SimpleNamespace(prepare_original_eight_scoring_inputs=fail))):
                with self.assertRaisesRegex(ValueError,'pure failure'):m.run(execute=True)
                self.assertEqual({x.name for x in out.iterdir()},{'started.json','failure.json'})
                with self.assertRaisesRegex(ValueError,'Immutable'):m.run(execute=True)
                self.assertEqual(len(calls),1)
    def test_pending_before_io_and_source_drift(self):
        with patch.object(m,'CORE_SHA',None),patch.object(Path,'read_bytes',side_effect=AssertionError('IO')):
            with self.assertRaisesRegex(ValueError,'Pending'):m.load_inputs()
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'source';p.write_bytes(b'a')
            with self.assertRaises(ValueError):m.take(p,m.sha(b'b'),{})
            (p.parent/'failure.json').write_bytes(b'{}')
            with self.assertRaisesRegex(ValueError,'failure'):m.take(p,m.sha(b'a'),{})
