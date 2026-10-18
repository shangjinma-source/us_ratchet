from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import tempfile,unittest
from scripts import ndx_multidecision_scoring_budget_independent_readback_20261003 as m
from scripts import ndx_multidecision_scoring_budget_20261003 as producer
from test_ndx_multidecision_scoring_budget_wrapper_20261003 import fixture as parents_fixture


def fixture():
    d,r,c=parents_fixture()
    s={str(m.ROOT/'backtest/ndx_multidecision_rolling_fit_research.py'):'1'*64,str(m.ROOT/'backtest/ndx_multidecision_window_scoring_research.py'):'2'*64}
    s.update({f'/synthetic/new{i}':'3'*64 for i in range(23)})
    d['rolling_fitter_manifest']=dict(schema='MULTIDECISION_ROLLING_SCORING_NUMERICAL_SOURCES_V1',status='FROZEN_BEFORE_ACTUAL_PLAN_OR_SCORE_NOT_DISPATCH_AUTHORITY',policy_reference=r['policy'],source_hashes=s,required_worker_environment=dict(PYTHONHASHSEED='0',sys_flags_hash_randomization=0),**dict.fromkeys(('fit_performed','score_computed','execution_authorized','point_in_time_verified','promotion_allowed','outer_cutoff_refit_substitution_allowed'),False))
    args=producer.project_inputs(d,r,c)
    plan=dict(registration_preserved=args['registration'],registration_reference_preserved=args['registration_reference'],full_universe_preserved=args['universe'],decision_inputs_preserved=args['decisions'])
    return d,r,c,plan


class Tests(unittest.TestCase):
    def test_exact_source_projection_and_late_row_attacks(self):
        d,r,c,p=fixture();m.inspect_source_projection(p,d,r,iter(c))
        for edit in (lambda d,r,c,p:p['decision_inputs_preserved'][5]['qualifications'][76].update(conditional_member_scope_passed=False),lambda d,r,c,p:p['decision_inputs_preserved'][0]['mode_sources'][0].update(complete_thirteen_windows=True),lambda d,r,c,p:d['history_audit']['rows'][76]['channel_reference'].update(sha256='f'*64),lambda d,r,c,p:c.pop(),lambda d,r,c,p:p['decision_inputs_preserved'][0]['fitter_source_reference'].update(sha256='0'*64)):
            dd,rr,cc,pp=deepcopy((d,r,c,p));edit(dd,rr,cc,pp)
            with self.assertRaises(ValueError):m.inspect_source_projection(pp,dd,rr,iter(cc))

    def test_envelope_exact_closure_and_raw_plan(self):
        d,r,c,plan=fixture();plan['rows']=[dict(sampling=dict(complete=True)) for _ in range(6)]
        parents=deepcopy(r)
        r.update({k:dict(path='/synthetic/'+k,sha256='d'*64) for k in ('plan','raw','publication','started')})
        sources={'/fixed/producer':'a'*64,'/fixed/core':'b'*64}
        common=dict(input_references=parents,source_hashes=sources,**m.FLAGS)
        doc=dict(schema='MULTIDECISION_SCORING_BUDGET_DOCUMENT_V1',status='REGISTERED_BEFORE_CANDIDATE_SCORING_NOT_DISPATCH_AUTHORITY',plan=plan,raw_plan_reference=r['raw'],runtime={'python':'synthetic'},security_count=77,issuer_count=76,observed_security_count=101,preserved_sidecar_count=7,original_provenance_and_missing=d['history_index']['original_provenance_and_missing'],preserved_evidence_sidecars=d['history_index']['preserved_evidence_sidecars'],original_parent_source_hash_claims={k:d[k]['source_hashes'] for k in ('history_index','original8_inputs','target_index')},mdv_diagnostic_report_preserved=d['mdv_report'],rolling_fitter_manifest_preserved=d['rolling_fitter_manifest'],original25_baseline_source_hashes_preserved=d['fitter_container']['plan']['fitter_source_hashes'],conditional_membership_scope_only=True,numeric_source_readbacks_reused=True,**deepcopy(common))
        pub=dict(schema='MULTIDECISION_SCORING_BUDGET_PUBLICATION_V1',status=doc['status'],plan_reference=r['plan'],raw_plan_reference=r['raw'],**deepcopy(common))
        raw=dict(schema='MULTIDECISION_SCORING_BUDGET_RAW_RETURN_V1',status='RETURNED_PENDING_VALIDATION_NOT_REGISTERED',plan=deepcopy(plan),runtime=doc['runtime'],**deepcopy(common))
        start=dict(schema='MULTIDECISION_SCORING_BUDGET_STARTED_V1',retry_allowed=False,runtime=doc['runtime'],**deepcopy(common))
        m.inspect_documents(doc,pub,raw,start,r,sources,d)
        for target in ('empty_sources','extra_sources','raw_changed','incomplete','bool'):
            dd,pp,rr,ss=deepcopy((doc,pub,raw,start))
            if target=='empty_sources':ss['source_hashes']={}
            if target=='extra_sources':dd['source_hashes']['/unverified']='f'*64
            if target=='raw_changed':rr['plan']['new']='unexpected'
            if target=='incomplete':dd['plan']['rows'][0]['sampling']['complete']=False;rr['plan']=deepcopy(dd['plan'])
            if target=='bool':dd['score_computed']=0
            with self.assertRaises(ValueError):m.inspect_documents(dd,pp,rr,ss,r,sources,d)

    def test_pending_before_io_and_same_read_bytes(self):
        with patch.object(m,'PLAN_SHA',None),patch.object(Path,'read_bytes',side_effect=AssertionError('No IO')):
            with self.assertRaises(ValueError):m.readback(execute=True)
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'x';p.write_bytes(b'original');r=m.ref(p,m.sha(b'original'))
            with patch.object(Path,'read_bytes',side_effect=[b'original',b'wrong']) as read:
                self.assertEqual(m.read(r,{}),b'original');self.assertEqual(read.call_count,1)
            with self.assertRaises(ValueError):m.read(m.ref(p,'0'*64),{})

    def test_private_independent_core_and_parent_extra(self):
        core=m.private_inspector({});self.assertTrue(callable(core.inspect_scoring_budget))
        with tempfile.TemporaryDirectory() as directory,patch.object(m,'PARENT',Path(directory)):
            for name in ('started.json','raw_plan.json','plan.json','publication.json'):(m.PARENT/name).write_bytes(b'{}')
            m.guard({});(m.PARENT/'extra').write_bytes(b'x')
            with self.assertRaises(ValueError):m.guard({})


if __name__=='__main__':unittest.main()
