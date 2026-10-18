from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_historical_cross_k_accounts_delta_independent_audit_20260923 as m


class DeltaReaderTests(unittest.TestCase):
    def envelope(self):
        payload={'schema':'fixture','value':1}
        return dict(schema='HISTORICAL_CROSS_K_DELTA_RAW_ACCOUNT_V2',producer_reference=deepcopy(m.PRODUCER),
            seed_account_audit_reference=deepcopy(m.SEED),global_task_ordinal_zero_based=121,
            reused_payload_schema_is_not_producer_identity=True,payload_sha256=m.independent.digest(payload),payload=payload)

    def test_exact_envelope_and_resigned_producer_seed_ordinal_attacks(self):
        document=self.envelope()
        self.assertEqual(m.unwrap(document,'RAW_ACCOUNT',121),document['payload'])
        for key,value in [('producer_reference',{'path':'other','sha256':'x'}),
                          ('seed_account_audit_reference',m.INDEX),('global_task_ordinal_zero_based',120),
                          ('global_task_ordinal_zero_based',True),('reused_payload_schema_is_not_producer_identity',False),
                          ('schema','HISTORICAL_CROSS_K_RAW_CANDIDATE_ACCOUNT_V1'),('payload_sha256','0'*64)]:
            with self.subTest(key=key):
                changed=deepcopy(document);changed[key]=value
                with self.assertRaises(ValueError):m.unwrap(changed,'RAW_ACCOUNT',121)

    def entry(self):
        return dict(task_id='new_task',global_task_ordinal_zero_based=121,
                    started_reference={'path':str(m.OUTPUT/'new_task/started.json'),'sha256':'s'},
                    raw_reference={'path':str(m.OUTPUT/'new_task/raw.json'),'sha256':'r'},
                    result_reference={'path':str(m.OUTPUT/'new_task/result.json'),'sha256':'v'})

    def test_new_ordinal_path_and_payload_reference_bounds(self):
        entry=self.entry();row={'task_id':'new_task'}
        self.assertEqual(len(m.entry_sources(entry,121,row,m.OUTPUT)),3)
        changed=deepcopy(entry);changed['started_reference']['path']=str(m.OUTPUT/'old_task/started.json')
        with self.assertRaises(ValueError):m.entry_sources(changed,121,row,m.OUTPUT)
        with self.assertRaises(ValueError):m.entry_sources(entry,120,row,m.OUTPUT)
        changed=deepcopy(entry);changed['raw_reference']=None
        self.assertEqual(len(m.entry_sources(changed,121,row,m.OUTPUT)),2)

    def valid_index(self):
        entry=self.entry();auth={'authority.py':'a'};seed={'index_reference':{'path':'seed_index','sha256':'seed'}}
        sources=dict(auth);sources.update(m.entry_sources(entry,121,{'task_id':'new_task'},m.OUTPUT))
        index=dict(schema='HISTORICAL_CROSS_K_FINALIZED_DELTA_INDEX_V2',producer_reference=m.PRODUCER,
            seed_account_audit_reference=m.SEED,seed_index_reference=seed['index_reference'],fit_prefix_audit_reference=m.FIT,
            plan_reference=m.independent.PLAN,folder=str(m.OUTPUT),seed_account_count=121,newly_completed_account_count=1,
            combined_account_count=122,new_execution_count=1,new_skipped_risk_count=0,real_execution_performed=True,
            audited_fit_task_count=5001,pending_account_count=4879,entries=[entry],old_accounts_copied=False,
            old_account_numerical_audit_repeated=False,old_fit_numerical_audit_repeated=False,independent_delta_audit_completed=False,
            finalized_after_full_source_verification=True,historical_expected_source_hashes=sources,archive_resolution={},
            fit_performed=False,control_executed=False,promotion_allowed=False,point_in_time_verified=False,formal_dual_benchmark_admission=False)
        queue=[{'task_id':str(i)} for i in range(121)]+[{'task_id':'new_task'}]
        return index,auth,seed,queue,[{'status':'ACCOUNT_EXECUTED_AND_INDEPENDENTLY_AUDITED'}]

    def test_exact_closure_and_unreviewed_delta_not_seed(self):
        arguments=self.valid_index();m.expected_index(*arguments)
        for key,value in [('combined_account_count',123),('independent_delta_audit_completed',True),
                          ('seed_account_audit_reference',m.INDEX),('new_execution_count',0),('real_execution_performed',False)]:
            changed=list(deepcopy(arguments));changed[0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):m.expected_index(*changed)
        for mode in ('omit','extra'):
            changed=list(deepcopy(arguments))
            if mode=='omit':changed[0]['historical_expected_source_hashes'].pop('authority.py')
            else:changed[0]['historical_expected_source_hashes']['unexplained.py']='x'
            with self.assertRaises(ValueError):m.expected_index(*changed)

    def test_hard_first_index_rejects_other_delta_before_io(self):
        with patch.object(m.independent,'read',side_effect=AssertionError('must not read')):
            with self.assertRaises(ValueError):m.build('other.json','0'*64)

    def test_single_build_publish_no_old_verification(self):
        with tempfile.TemporaryDirectory() as folder:
            value={'historical_expected_source_hashes':{},'archive_resolution':{},'fixture':True}
            with patch.object(m,'build',return_value=value) as build,patch.object(m.independent.archive,'load_contract',return_value={}),\
                 patch.object(m.independent.archive,'verify_expected_sources',return_value={}),\
                 patch.object(m.independent.prefix,'verify',side_effect=AssertionError('old fit verification')),\
                 patch.object(m.independent.shared,'verify',side_effect=AssertionError('old account verification')):
                result=m.build_and_publish(Path(folder)/'audit.json',m.INDEX['path'],m.INDEX['sha256'])
                self.assertEqual(build.call_count,1)
                self.assertEqual(m.independent.read(result,{}),value)


if __name__=='__main__':unittest.main()
