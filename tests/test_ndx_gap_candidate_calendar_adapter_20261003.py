import base64
from copy import deepcopy
from datetime import date,timedelta
import io,csv
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from scripts import ndx_gap_candidate_calendar_adapter_20261003 as m
from backtest import ndx_gap_candidate_calendar_research as core

def fixture():
    refs={k:dict(path=k,sha256='a'*64) for k in m.BOUND};flags={k:False for k in ('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed')}
    dates=[];d=date(2026,7,1)
    while len(dates)<65:
        if d.weekday()<5:dates.append(d.isoformat())
        d+=timedelta(days=1)
    rows=[dict(sequence=i+1,session=d,kind='SEALED_PARENT_OBSERVED_SESSION' if i<60 else 'MISSED_OBSERVATION',evidence_reference=dict(refs['frontier'],json_pointer=f'/known_accounted_rows/{i}'),seal_status='UNKNOWN' if i<60 else 'NOT_ATTEMPTED') for i,d in enumerate(dates)]
    old=[dict(session=r['session'],kind=r['kind']) for r in rows]
    front=dict(schema='OBSERVATION_GAP_FRONTIER_RESEARCH_V1',last_observed_session='2026-09-24',last_accounted_session='2026-10-01',input_references={k:refs[v] for k,v in [('ledger','ledger'),('publication','ledger_publication'),('parent_sessions','parent_sessions')]},known_accounted_rows=old,source_hashes={},**flags)
    p=dict(schema='SOURCE_BOUND_GAP_MONTHLY_POLICY_PROJECTION_V1',policy_id=m.POLICY,user_choice_reference=refs['user_choice'],frontier_reference=refs['frontier'],projection_inputs=dict(known_rows=rows,new_prospective_observations=[]),new_observation_count=0,saved_frontier_rows=old,projection=dict(rows=[dict(input_row=r) for r in rows]),source_hashes={},**flags)
    rawrows=[dict(Date=d,Open='1',High='1',Low='1',Close='1',Volume='1') for d in dates]
    stream=io.StringIO(newline='');w=csv.DictWriter(stream,fieldnames=m.FIELDS,lineterminator='\n');w.writeheader();w.writerows(rawrows);blob=stream.getvalue().encode()
    ev=dict(original_sha256=m.sha(blob),original_csv_bytes_base64=base64.b64encode(blob).decode(),original_row_count=65,original_rows=[dict(raw_csv_row=r,original_data_row_index=i,session=r['Date'],included_in_scoped_csv=True) for i,r in enumerate(rawrows)],included_original_row_indexes=list(range(65)),excluded_original_row_indexes=[],scoped_csv_utf8=blob.decode(),scoped_sha256=m.sha(blob))
    tz=(m.ROOT/'data/cache/research/forward_source_capture_scoped_20261002_v1/New_York.tzif').read_bytes();tzref=dict(path='tzif',sha256=m.sha(tz));hashes={t:m.sha(blob) for t in ('QQQ','SPY')}
    plan=dict(schema='FORWARD_SOURCE_CAPTURE_PLANNING_V1',accounted_prefix_dates=dates,capture_started_at_utc='2026-10-02T15:00:00+00:00',observed_at_utc='2026-10-02T15:00:01+00:00',fresh_observation=False,source_sha256=hashes,baseline_sha256=hashes,tzif_sha256=m.sha(tz),revisions=[],timeliness_candidate=None)
    scoped=dict(schema='FORWARD_SOURCE_CAPTURE_SCOPED_PLAN_V1',scope_start=dates[0],full_original_bytes_preserved=True,fresh_observation=False,capture_plan=plan,csv_scope_evidence={role:{t:deepcopy(ev) for t in ('QQQ','SPY')} for role in ('source','baseline')},original_source_sha256=hashes,original_baseline_sha256=hashes)
    capture=dict(schema='FORWARD_SOURCE_CAPTURE_SCOPED_PAYLOAD_V1',plan=scoped,input_references=dict(frontier=refs['frontier']),capture_started_at_utc=plan['capture_started_at_utc'],observed_at_utc=plan['observed_at_utc'],captured_artifacts=dict(tzif=tzref),source_hashes={},**flags)
    docs=dict(policy=p,frontier=front,capture=capture,ledger=dict(missed_observation_count=5,events=[{}]*5,**flags),ledger_publication=dict(status='PUBLISHED_MISSED_OBSERVATION_EVIDENCE_ONLY',artifacts=dict(ledger=refs['ledger']),**flags))
    for role,status,field in [('policy','PUBLISHED_USER_SELECTED_POLICY_COORDINATES_NO_SEAL','policy_reference'),('frontier','PUBLISHED_ACCOUNTED_FRONTIER_ONLY_NO_ELIGIBILITY','frontier_reference'),('capture','PUBLISHED_CURRENT_CACHE_CAPTURE_NOT_CALENDAR_APPEND','capture_reference')]:docs[role+'_publication']=dict(status=status,source_hashes={},**{field:refs[role]},**flags)
    artifacts={role+'_'+t:blob for role in ('source','baseline') for t in ('QQQ','SPY')};artifacts['tzif']=tz
    return docs,refs,artifacts

class Tests(unittest.TestCase):
    def test_no_capture_promotion_and_prefix_preserved(self):
        docs,refs,artifacts=fixture();before=deepcopy(docs);args=m.project_inputs(docs,refs,artifacts);result=core.prepare_candidate_calendar_evidence(**args)
        self.assertEqual(result['status'],'BLOCKED');self.assertIsNone(result['selected_row']);self.assertEqual(len(result['complete_typed_rows']),65);self.assertEqual(docs,before)
        docs['capture']['plan']['capture_plan']['timeliness_candidate']={'session':'2026-10-02'}
        self.assertEqual(m.project_inputs(docs,refs,artifacts)['new_observation_evidence'],[])
    def test_scope_receipt_and_old_seal_mutations_rejected(self):
        for mutate in ('hash','receipt','seal','bool'):
            docs,refs,artifacts=fixture()
            if mutate=='hash':docs['capture']['plan']['csv_scope_evidence']['source']['QQQ']['scoped_sha256']='b'*64
            elif mutate=='receipt':docs['policy_publication']['policy_reference']=dict(path='wrong',sha256='a'*64)
            elif mutate=='seal':docs['policy']['projection_inputs']['known_rows'][0]['seal_status']='NOT_ATTEMPTED'
            else:docs['capture_publication']['promotion_allowed']=0
            with self.assertRaises(ValueError):m.project_inputs(docs,refs,artifacts)
    def test_started_failure_and_no_retry(self):
        docs,refs,artifacts=fixture()
        with tempfile.TemporaryDirectory() as tmp,patch.object(m,'OUTPUT',Path(tmp)/'attempt'),patch.object(m,'load_inputs',return_value=(docs,refs,{},artifacts,SimpleNamespace(prepare_candidate_calendar_evidence=lambda **kw:(_ for _ in ()).throw(ValueError('synthetic'))))),patch.object(m,'guard'):
            with self.assertRaises(ValueError):m.run(execute=True)
            self.assertEqual({p.name for p in m.OUTPUT.iterdir()},{'started.json','failure.json'})
            with self.assertRaises(ValueError):m.run(execute=True)
    def test_complete_publish_only_blocked(self):
        docs,refs,artifacts=fixture()
        with tempfile.TemporaryDirectory() as tmp,patch.object(m,'OUTPUT',Path(tmp)/'attempt'),patch.object(m,'load_inputs',return_value=(docs,refs,{},artifacts,core)),patch.object(m,'guard'):
            ref=m.run(execute=True);doc=m.loads(Path(ref['path']).read_bytes());self.assertFalse(doc['production_lineage_ready']);self.assertEqual(doc['evidence']['status'],'BLOCKED')

if __name__=='__main__':unittest.main()
