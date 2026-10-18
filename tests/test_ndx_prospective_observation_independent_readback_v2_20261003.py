"""New V2 reader tests; synthetic history and temporary files, no actual observation."""
import copy,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from scripts import ndx_prospective_observation_independent_readback_v2_20261003 as m
import test_ndx_prospective_observation_writer_v2_20261003 as f

def fixture(second=False,late=False):
    parent,capture,args,refs,sources,core=f.fixture(second)
    session=args['session'];start=session+'T21:01:00+00:00';end=session+'T21:01:01+00:00'
    payload=core.prepare_observation_payload(**args,writer_started_at_utc=start,writer_completed_at_utc=end)
    rt={'python':'synthetic'}
    payload.update(writer_adapter_schema=m.ADAPTER,writer_interval_role='PRE_PAYLOAD_VALIDATION_INTERVAL_NOT_PUBLICATION_COMPLETION',input_references=refs,source_hashes=sources,runtime=rt,**dict.fromkeys(m.WRITER_FALSE,False))
    pr={'path':'payload.json','sha256':m.sha(m.enc(payload))}
    receipt=dict(schema='PROSPECTIVE_OBSERVATION_DURABLE_RECEIPT_V1',writer_adapter_schema=m.ADAPTER,status='PERSISTED_RESEARCH_OBSERVATION_NOT_CANDIDATE_AUTHORITY',observation_id=payload['observation_id'],payload_reference=pr,publication_check_at_utc='2026-10-09T15:00:00+00:00'if late else session+'T21:01:02+00:00',publication_time_role='AFTER_PAYLOAD_FSYNC_AND_SOURCE_GUARD_BEFORE_RECEIPT_WRITE',timing_classification='LATE_OBSERVATION'if late else payload['timing_classification'],month_first_actual_observation=payload['month_first_actual_observation'],input_references=refs,source_hashes=sources,runtime=rt,**dict.fromkeys(m.WRITER_FALSE,False))
    started=dict(schema='PROSPECTIVE_OBSERVATION_WRITER_STARTED_V2',writer_adapter_schema=m.ADAPTER,writer_started_at_utc=start,input_references=refs,source_hashes=sources,runtime=rt,**dict.fromkeys(m.WRITER_FALSE,False))
    blobs={}
    for role in ('sources','baseline_sources'):
        for v in args['capture'][role].values():blobs[v['reference']['path']]=v['bytes']
    v=args['capture']['tzif'];blobs[v['reference']['path']]=v['bytes']
    return dict(payload=payload,receipt=receipt,started=started,docs=dict(parent=parent,capture=capture),refs=refs,payload_reference=pr,blobs=blobs,session=session)

class Tests(unittest.TestCase):
    def test_variable_prefix_and_late_does_not_replace_failed_first(self):
        for second in (False,True):
            a=fixture(second,True);before=copy.deepcopy(a);out=m.inspect(**a)
            self.assertEqual(out['parent_observed_count'],61+int(second));self.assertEqual(out['parent_gap_count'],5)
            self.assertFalse(out['month_first_actual_observation']);self.assertEqual(out['timing_classification'],'LATE_OBSERVATION');self.assertEqual(a,before)
            self.assertEqual(a['payload']['first_actual_observed_session_of_month'],'2026-10-02')
    def test_prefix_inventory_and_role_counters_are_not_optional(self):
        for mode in ('prefix','attempt','v1','snapshotbool','baseline','month'):
            a=fixture();h=a['docs']['parent']['document'];c=a['docs']['capture']
            if mode=='prefix':h['known_typed_rows'].pop(0)
            elif mode=='attempt':h['parent_attempt_inventory'][0]['status']='PAYLOAD_ONLY'
            elif mode=='v1':a['docs']['parent']['readback']['schema']='PROSPECTIVE_OBSERVATION_INDEPENDENT_READBACK_V1'
            elif mode=='snapshotbool':c['readback']['counts']['diagnostic_count']=False
            elif mode=='baseline':c['document']['plan']['source_evidence']['QQQ']['baseline_reference']=h['baseline_references']['SPY']
            else:h['first_actual_observed_session_by_month']['2026-10']='2026-10-05'
            with self.subTest(mode=mode),self.assertRaises(ValueError):m.inspect(**a)
    def test_original_rows_tzif_time_and_all_payload_permissions(self):
        for mode in ('row','base64','tzif','time','upgrade','zero','receiptlate','indexbool'):
            a=fixture(late=True);p=a['payload']
            if mode=='row':p['selected_original_rows']['QQQ']['Close']='11'
            elif mode=='base64':p['full_original_sources_preserved']['SPY']['sources']['original_csv_bytes_base64']=''
            elif mode=='tzif':p['tzif_bytes_base64']=''
            elif mode=='time':a['receipt']['publication_check_at_utc']='2026-10-05T20:00:00+00:00'
            elif mode=='upgrade':p['future_independent_oos']=True
            elif mode=='zero':p['future_independent_oos']=0
            elif mode=='receiptlate':a['receipt']['timing_classification']='WITHIN_CONSERVATIVE_OBSERVATION_WINDOW'
            else:p['source_row_locations']['QQQ']['original_data_row_index']=True
            with self.subTest(mode=mode),self.assertRaises(ValueError):m.inspect(**a)
        a=fixture();row=a['payload']['full_original_sources_preserved']['QQQ']['sources'];self.assertEqual(len(row['outside_required_scope_diagnostics']),1)
        with self.assertRaises(ValueError):m.parse_csv(b'Date,Open,High,Low,Close,Volume\n2026-10-05,1,12,8,10,100\n','2026-10-05')
    def test_pending_before_io_and_no_production_imports(self):
        with patch.object(Path,'read_bytes',side_effect=AssertionError('IO')),patch.object(Path,'exists',side_effect=AssertionError('IO')):
            with self.assertRaisesRegex(ValueError,'pending'):m.readback(execute=True)
        import ast
        tree=ast.parse(Path(m.__file__).read_text())
        self.assertFalse(any(isinstance(n,ast.Call)and isinstance(n.func,ast.Name)and n.func.id in ('exec','compile','eval','__import__')for n in ast.walk(tree)))
        with self.assertRaisesRegex(ValueError,'Live cache'):m.no_live({str(ROOT/'data/cache/QQQ.csv'):'a'*64})
    def test_output_drift_failure_is_retained_and_no_retry(self):
        a=fixture();sources=a['payload']['source_hashes']
        for fail in (False,True):
            with tempfile.TemporaryDirectory()as td,patch.object(m,'BASE',Path(td)),patch.object(m,'load_inputs',return_value=(a['docs'],a['refs'],a['blobs'],sources)):
                p=copy.deepcopy(a['payload']);pr={'path':str(m.BASE/'observation_payload.json'),'sha256':m.sha(m.enc(p))};r=copy.deepcopy(a['receipt']);r['payload_reference']=pr
                m.save(m.BASE/'observation_payload.json',p);m.save(m.BASE/'receipt.json',r);m.save(m.BASE/'started.json',a['started'])
                def guard(s):
                    if fail and(m.BASE/'independent_readback.json').exists():raise ValueError('source drift')
                with patch.object(m,'PAYLOAD_SHA',pr['sha256']),patch.object(m,'RECEIPT_SHA',m.sha(m.enc(r))),patch.object(m,'guard',side_effect=guard):
                    if fail:
                        with self.assertRaisesRegex(ValueError,'drift'):m.readback(execute=True)
                        self.assertTrue((m.BASE/'failure.json').exists());self.assertTrue((m.BASE/'observation_payload.json').exists())
                    else:self.assertEqual(m.decode(Path(m.readback(execute=True)['path']).read_bytes())['schema'],'PROSPECTIVE_OBSERVATION_INDEPENDENT_READBACK_V2')
                    with self.assertRaises(ValueError):m.readback(execute=True)
if __name__=='__main__':unittest.main()
