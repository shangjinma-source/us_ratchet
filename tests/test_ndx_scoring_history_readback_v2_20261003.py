from copy import deepcopy
from pathlib import Path
import tempfile,unittest
from unittest.mock import patch
from backtest import ndx_multidecision_scoring_history_inspection_v2_research as core
from scripts import ndx_multidecision_scoring_history_independent_readback_v2_20261003 as reader
from test_ndx_multidecision_scoring_history_inspection_research import saved_case
from test_ndx_multidecision_scoring_history_independent_readback_20261003 import physical


def compound(parent=None):
    return dict(parent=deepcopy(parent or core.REGISTRY_REFERENCE),event_index=23,original_raw_reference=dict(path=r'E:\Git\us_ratchet\data\cache\research\standard_split_official_evidence_20260912_v1\pcar_20230208_miax.response.bin',sha256='89760ae64baa1d658e2081e2ba5e5b96a3ff0faf89972425a5178ccede462765'),additional_execution_raw_reference=None)


def bind_event(a,ch,r):
    a['bridge_row']['event_policy_bridge']['events'][0]['specific_event_reference']=deepcopy(r)
    ch['bridge_row_preserved']=deepcopy(a['bridge_row']);ch['content_sha256']=core.digest({k:v for k,v in ch.items() if k!='content_sha256'})


class Tests(unittest.TestCase):
    def test_composite_actual_shapes_and_original_arithmetic(self):
        a,ch=saved_case()
        core.inspect_scoring_history_channel(saved_channel=ch,**a)
        for parent in (core.REGISTRY_REFERENCE,core.ADDITIONS_REFERENCE):
            for extra in (None,dict(path='executed.raw',sha256='a'*64)):
                r=compound(parent);r['additional_execution_raw_reference']=extra;bind_event(a,ch,r)
                result=core.inspect_scoring_history_channel(saved_channel=ch,**a)
                self.assertEqual(result['window_count'],78)

    def test_exact_keys_types_and_registered_parents(self):
        for mutate in (lambda r:r.update(event_index=True),lambda r:r.update(event_index=-1),lambda r:r.update(event_index=23.0),lambda r:r.update(extra='x'),lambda r:r.pop('additional_execution_raw_reference'),lambda r:r['original_raw_reference'].update(sha256='bad'),lambda r:r['parent'].update(path='foreign'),lambda r:r.update(additional_execution_raw_reference={}),lambda r:r['parent'].update(extra=True)):
            r=compound();mutate(r)
            with self.assertRaises(ValueError):core.event_reference(r)
        for value in (None,{},dict(path='raw',sha256='b'*64,unknown='x')):
            with self.assertRaises(ValueError):core.event_reference(value)

    def test_v2_physical_failure_binding_and_pending_gate(self):
        with patch.object(reader,'INDEX_SHA',None),patch.object(Path,'read_bytes') as read:
            with self.assertRaises(ValueError):reader.readback(execute=True)
            read.assert_not_called()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);pins,_,_,_,_=physical(root);old=root/'old';old.mkdir();prior={}
            def put(role,path,value):
                b=value if type(value) is bytes else reader.encoded(value);path.write_bytes(b);prior[role]=(str(path),reader.sha(b))
            put('reader',root/'oldreader.py',b'old reader never executed');put('inspector',root/'oldinspector.py',b'old inspector never executed')
            put('started',old/'started.json',dict(schema='MULTIDECISION_SCORING_HISTORY_READBACK_STARTED_V1',reader_sha256=prior['reader'][1],retry_allowed=False,index_reference=reader.ref(pins['PARENT']/'index.json',pins['INDEX_SHA']),publication_reference=reader.ref(pins['PARENT']/'publication.json',pins['PUBLICATION_SHA'])))
            put('failure',old/'failure.json',dict(completed_channel_count=6,remaining_channel_count=71,error='Reference',error_type='ValueError',retry_allowed=False,status='FAILED_DO_NOT_CONSUME'))
            with patch.multiple(reader,**pins),patch.object(reader,'PREVIOUS_ATTEMPT',prior):
                result=reader.load_inputs();self.assertEqual(len(result[2]),77);self.assertEqual(result[4].__file__,str(reader.INSPECTOR));self.assertIn(str(old/'failure.json'),result[1])
                (old/'failure.json').write_text('{}')
                with self.assertRaises(ValueError):reader.guard(result[1],result[0])

if __name__=='__main__':unittest.main()
