from copy import deepcopy
from datetime import date,timedelta
from unittest.mock import patch
from pathlib import Path
import unittest
from scripts import ndx_prospective_observation_independent_readback_20261003 as r
from scripts import ndx_prospective_observation_writer_20261003 as writer
from backtest import ndx_prospective_observation_receipt_research as core
from test_ndx_prospective_observation_receipt_research import fixture as small,csv_item,ref

def fixture():
    a=small();days=[];d=date(2026,10,1)
    while len(days)<65:
        if d.weekday()<5:days.append(d.isoformat())
        d-=timedelta(days=1)
    days.reverse();a['known_typed_rows']=[dict(sequence=i+1,session=d,kind='SEALED_PARENT_OBSERVED_SESSION' if i<60 else 'MISSED_OBSERVATION',seal_status='UNKNOWN' if i<60 else 'NOT_ATTEMPTED',evidence_reference=dict(ref('old'),json_pointer='/rows/'+str(i))) for i,d in enumerate(days)]
    for t in ('QQQ','SPY'):
        a['capture']['sources'][t]=csv_item(t,['2015-03-30']+days+[a['session']]);a['capture']['baseline_sources'][t]=csv_item('base'+t,['2015-03-30']+days)
        for role in ('sources','baseline_sources'):
            item=a['capture'][role][t];item['bytes']=item['bytes'].replace(b'2015-03-30,10,11,9,10',b'2015-03-30,8,11,9,10');item['reference']['sha256']=r.sha(item['bytes'])
    p=core.prepare_observation_payload(**a);refs={k:ref(k) for k in r.BOUND};refs['parent']=a['parent_reference'];refs['parent_readback']=a['parent_readback_reference'];refs['capture']=a['capture']['reference']
    p.update(writer_interval_role='PRE_PAYLOAD_VALIDATION_INTERVAL_NOT_PUBLICATION_COMPLETION',input_references=refs,source_hashes={},runtime={'python':'synthetic'})
    started=dict(schema='PROSPECTIVE_OBSERVATION_WRITER_STARTED_V1',writer_started_at_utc=a['writer_started_at_utc'],input_references=refs,source_hashes={},runtime=p['runtime'],**writer.FLAGS)
    pr=ref('payload');receipt=dict(schema='PROSPECTIVE_OBSERVATION_DURABLE_RECEIPT_V1',status='PERSISTED_RESEARCH_OBSERVATION_NOT_CANDIDATE_AUTHORITY',payload_reference=pr,observation_id=p['observation_id'],publication_check_at_utc='2026-10-02T20:00:04+00:00',publication_time_role='AFTER_PAYLOAD_FSYNC_AND_SOURCE_GUARD_BEFORE_RECEIPT_WRITE',timing_classification=p['timing_classification'],month_first_actual_observation=p['month_first_actual_observation'],source_hashes={},runtime=p['runtime'],**writer.FLAGS)
    parent=dict(schema='SOURCE_BOUND_GAP_MONTHLY_POLICY_PROJECTION_V1',policy_id='FIRST_ACTUAL_OBSERVED_SESSION_GAPS_DO_NOT_CONSUME_MONTH',projection_inputs=dict(known_rows=a['known_typed_rows'],new_prospective_observations=[]),new_observation_count=0,frontier_reference=ref('frontier'))
    c=a['capture'];capture=dict(input_references=dict(frontier=parent['frontier_reference'],**{'baseline_'+t:c['baseline_sources'][t]['reference'] for t in ('QQQ','SPY')}),captured_artifacts={**{t:c['sources'][t]['reference'] for t in ('QQQ','SPY')},'tzif':c['tzif']['reference']},capture_started_at_utc=c['started_at_utc'],observed_at_utc=c['completed_at_utc'],plan={'capture_plan':dict(accounted_prefix_dates=days,new_source_dates=[a['session']],revisions=[])})
    blobs={item['reference']['path']:item['bytes'] for role in ('sources','baseline_sources') for item in c[role].values()};blobs[c['tzif']['reference']['path']]=c['tzif']['bytes']
    return [p,receipt,started,dict(parent=parent,capture=capture),refs,pr,blobs,a['session']]

class Tests(unittest.TestCase):
    def test_full_prefix_outside_bad_row_and_late_consumes_month(self):
        a=fixture();before=deepcopy(a);v=r.inspect(*a);self.assertEqual(a,before);self.assertTrue(v['month_first_actual_observation'])
        a[1].update(publication_check_at_utc='2026-10-05T13:30:00+00:00',timing_classification='LATE_OBSERVATION')
        self.assertEqual(r.inspect(*a)['timing_classification'],'LATE_OBSERVATION');self.assertTrue(r.inspect(*a)['month_first_actual_observation'])
        self.assertEqual(len(a[0]['full_original_sources_preserved']['QQQ']['sources']['outside_required_scope_diagnostics']),1)
    def test_prefix_capture_clock_and_authority_attacks(self):
        for kind in ('prefix','oldcapture','clock','flag','diagnostic','tz'):
            a=fixture()
            if kind=='prefix':a[3]['parent']['projection_inputs']['known_rows'].pop()
            elif kind=='oldcapture':a[3]['capture']['plan']['capture_plan']['new_source_dates']=[]
            elif kind=='clock':a[1]['publication_check_at_utc']='2026-10-02T20:00:02+00:00'
            elif kind=='flag':a[1]['candidate_seal_allowed']=0
            elif kind=='diagnostic':a[0]['full_original_sources_preserved']['SPY']['sources']['outside_required_scope_diagnostics']=[]
            else:a[0]['tzif_bytes_base64']=''
            with self.subTest(kind=kind),self.assertRaises(ValueError):r.inspect(*a)
    def test_required_bad_ohlc_and_nonfinite_always_reject(self):
        blob=b'Date,Open,High,Low,Close,Volume\n2026-10-02,8,11,9,10,100\n'
        with self.assertRaises(ValueError):r.parse_csv(blob,'2026-07-01')
        with self.assertRaises(ValueError):r.parse_csv(blob.replace(b',8,',b',NaN,'),'2027-01-01')
    def test_pending_refuses_before_reads(self):
        with patch.object(Path,'read_bytes') as read:
            with self.assertRaises(ValueError):r.readback(ref('receipt'),ref('payload'),execute=True)
            read.assert_not_called()

if __name__=='__main__':unittest.main()
