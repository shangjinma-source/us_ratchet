from copy import deepcopy
from pathlib import Path
import tempfile,unittest,types
from unittest.mock import patch
from scripts import ndx_original_eight_tsm_scoring_history_20261003 as m
from test_ndx_original_eight_long_window_channels_20261003 import fixture as oldfixture
from scripts import ndx_original_eight_long_window_channels_20261003 as old


def fixture():
    olddocs,oldrefs,_,_=oldfixture();rows=old.prepare(olddocs,oldrefs)['rows'];r=deepcopy(olddocs['requirements'])
    meta=r['requirements']['stock_metadata_preserved']['TSM'];dates=[str(i) for i in range(1183)]
    meta.update(observation_rows=[dict(session=d) for d in dates],identity_evidence=[],risk_evidence=[])
    rows[4]['complete_benchmark_metadata']=deepcopy(meta);rows[4]['channel']={'bridge_row_preserved':deepcopy(rows[4]['conditional_event_policy_bridge'])}
    refs={k:dict(path='/synthetic/'+k,sha256='a'*64) for k in m.BOUND}
    false=dict.fromkeys(('fit_performed','point_in_time_verified','execution_authorized','promotion_allowed','legal_training_input_admitted'),False)
    h=dict(schema='BULK_HISTORY_REQUIREMENTS_DOCUMENT_V1',requirements=dict(reference_calendar=dict(ticker='AAPL',dates=dates)),source_hashes={},**false)
    saved=dict(schema='ORIGINAL_EIGHT_LONG_WINDOW_CONDITIONAL_CHANNELS_V1',rows=rows,original_control_preserved=deepcopy(r['requirements']['original_control_preserved']),source_hashes={},**false)
    docs=dict(history=h,requirements=r,original_channels=saved,control=deepcopy(r['requirements']['original_control_preserved']['complete_original_manifest']))
    for role,schema,parent,field,status in [('history','BULK_HISTORY_REQUIREMENTS_PUBLICATION_V1','history','requirements_reference','PUBLISHED_REQUIREMENTS_ONLY'),('requirements','BULK_LONG_WINDOW_BENCHMARK_REQUIREMENTS_PUBLICATION_V1','requirements','requirements_reference','PUBLISHED_REQUIREMENTS_ONLY'),('original','ORIGINAL_EIGHT_LONG_WINDOW_CHANNELS_PUBLICATION_V1','original_channels','channels_reference','PUBLISHED_CONDITIONAL_NUMBERS_PENDING_NEW_TSM_READBACK')]:
        docs[role+'_publication']=dict(schema=schema,status=status,source_hashes=deepcopy(docs[parent]['source_hashes']),**{field:refs[parent]})
    docs['history_audit']=dict(status='PASS',requirements_sha256='a'*64,publication_sha256='a'*64,reader_sha256='a'*64)
    docs['original_audit']=dict(schema='ORIGINAL_EIGHT_LONG_WINDOW_INDEPENDENT_READBACK_V1',status='PASS',channels_sha256='a'*64,publication_sha256='a'*64,reader_sha256='a'*64,raw_reference=meta['raw_reference'],receipt_reference=meta['receipt_reference'])
    return docs,refs


class WrapperTests(unittest.TestCase):
    def test_control_projection_and_parent_mismatch(self):
        docs,refs=fixture();before=deepcopy(docs);a=m.prepare(docs,refs)
        self.assertEqual(docs,before);self.assertEqual(a['original_control_contract']['role'],m.ROLE);self.assertEqual(len(a['reference_calendar']),1183)
        self.assertEqual(a['bridge_row'],docs['original_channels']['rows'][4]['conditional_event_policy_bridge'])
        for role,key,value in [('original_audit','status','FAILED'),('original_publication','status','FAILED')]:
            d=deepcopy(docs);d[role][key]=value
            with self.assertRaises(ValueError):m.prepare(d,refs)
        d=deepcopy(docs);d['control']['definition']['securities'][4]['target_weight']=.9
        with self.assertRaises(ValueError):m.prepare(d,refs)

    def test_failure_durable_and_no_retry(self):
        with tempfile.TemporaryDirectory() as td:
            output=Path(td)/'out';calls=[]
            def fail(**kwargs):calls.append(kwargs);raise ValueError('numeric failure')
            with patch.object(m,'OUTPUT',output),patch.object(m,'load_inputs',return_value=({}, {}, {}, {},types.SimpleNamespace(materialize_tsm_control_history=fail))),patch.object(m,'space'):
                with self.assertRaisesRegex(ValueError,'numeric failure'):m.run(execute=True)
                self.assertEqual({x.name for x in output.iterdir()},{'started.json','failure.json'})
                with self.assertRaisesRegex(ValueError,'Immutable'):m.run(execute=True)
                self.assertEqual(len(calls),1)

    def test_pending_and_source_failure(self):
        with patch.object(m,'CORE_SHA',None),patch.object(Path,'read_bytes',side_effect=AssertionError('IO')):
            with self.assertRaisesRegex(ValueError,'Pending'):m.load_inputs()
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'source';p.write_bytes(b'x');(p.parent/'failure.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'failure marker'):m.guard({str(p):m.sha(b'x')})

if __name__=='__main__':unittest.main()
