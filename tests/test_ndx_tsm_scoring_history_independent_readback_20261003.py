from copy import deepcopy
from pathlib import Path
import tempfile,unittest
from unittest.mock import patch
from scripts import ndx_tsm_scoring_history_independent_readback_20261003 as m
from test_ndx_original_eight_tsm_scoring_history_20261003 import fixture as parentfixture

def fixture():
    docs,refs=parentfixture();base={'fixed':'a'*64}
    document=dict(schema='TSM_CONTROL_SCORING_HISTORY_DOCUMENT_V1',status='PUBLISHED_CONTROL_NUMBERS_PENDING_INDEPENDENT_READBACK',role=m.ROLE,raw_decode_count=1,other_seven_channels_recomputed=False,new_independent_numeric_readback_completed=False,score_computed=False,input_references=refs,source_hashes=base,original_control_preserved=deepcopy(docs['requirements']['requirements']['original_control_preserved']),complete_tsm_metadata=deepcopy(docs['requirements']['requirements']['stock_metadata_preserved']['TSM']),**dict.fromkeys(m.FLAGS,False))
    pub=dict(schema='TSM_CONTROL_SCORING_HISTORY_PUBLICATION_V1',status=document['status'],input_references=refs,source_hashes=base,**dict.fromkeys(m.FLAGS,False))
    start=dict(schema='TSM_CONTROL_SCORING_HISTORY_STARTED_V1',input_references=refs,source_hashes=base,planned_raw_decode_count=1,retry_allowed=False)
    return document,pub,start,docs,refs,base

class Tests(unittest.TestCase):
    def test_metadata_exact_and_false_sources(self):
        a=fixture();r=m.inspect_evidence(*a);self.assertEqual(r['bridge_row']['ticker'],'TSM')
        for field,value in [('raw_decode_count',True),('other_seven_channels_recomputed',True),('source_hashes',{})]:
            b=deepcopy(a);b[0][field]=value
            with self.assertRaises(ValueError):m.inspect_evidence(*b)
        b=deepcopy(a);b[3]['original_audit']['status']='FAILED'
        with self.assertRaises(ValueError):m.inspect_evidence(*b)
    def test_own_started_drift_leaves_failure_and_no_retry(self):
        with tempfile.TemporaryDirectory() as td:
            parent=Path(td)/'parent';parent.mkdir();out=Path(td)/'audit'
            for name in ('started.json','channel.json','publication.json'):(parent/name).write_bytes(b'{}')
            _,_,_,docs,_,_=fixture();meta=docs['requirements']['requirements']['stock_metadata_preserved']['TSM']
            meta['original_receipt']={}
            role_paths={str(m.ROOT/rel):role for role,(rel,h) in m.BOUND.items()}
            def take(path,h,sources):
                name=str(path)
                if path==m.INSPECTOR:return b'def inspect_tsm_control_history(**kwargs): return {"status":"PASS"}'
                if path==parent/'channel.json':return m.encoded({'channel':{}})
                if path==parent/'publication.json':return m.encoded({'channel_reference':{'path':str(parent/'channel.json'),'sha256':'a'*64}})
                if name==meta['receipt_reference']['path']:return b'{}'
                return m.encoded(docs[role_paths[name]]) if name in role_paths and role_paths[name] in docs else b'{}'
            real_save=m.save
            def save(path,value):
                ref=real_save(path,value)
                if path.name=='independent_readback.json':(out/'started.json').write_bytes(b'changed')
                return ref
            with patch.object(m,'PARENT',parent),patch.object(m,'OUTPUT',out),patch.object(m,'CHANNEL_SHA','a'*64),patch.object(m,'PUBLICATION_SHA','b'*64),patch.object(m,'PRODUCER_SHA','c'*64),patch.object(m,'take',side_effect=take),patch.object(m,'guard'),patch.object(m,'inspect_evidence',return_value={}),patch.object(m,'save',side_effect=save):
                with self.assertRaisesRegex(ValueError,'Final audit output'):m.readback(execute=True)
                self.assertTrue((out/'failure.json').exists())
                with self.assertRaisesRegex(ValueError,'Immutable'):m.readback(execute=True)

    def test_pending_before_io(self):
        with patch.object(m,'CHANNEL_SHA',None),patch.object(Path,'read_bytes',side_effect=AssertionError('IO')):
            with self.assertRaisesRegex(ValueError,'Future'):m.readback(execute=True)
    def test_take_same_bytes_and_failure_namespace(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'raw';p.write_bytes(b'good');sources={}
            self.assertEqual(m.take(p,m.sha(b'good'),sources),b'good')
            p.write_bytes(b'bad')
            with self.assertRaises(ValueError):m.take(p,m.sha(b'good'),{})
            (p.parent/'failure.json').write_bytes(b'{}')
            with self.assertRaisesRegex(ValueError,'failure'):m.take(p,m.sha(b'bad'),{})

