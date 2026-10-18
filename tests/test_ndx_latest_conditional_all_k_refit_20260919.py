import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import pandas as pd
from scripts import ndx_latest_conditional_all_k_refit_20260919 as m
from backtest import ndx_latest_conditional_panel_research as core

PARAMETERS=dict(fit_days=126,shrinkage_intensity=.35,turnover_anchor_strength=.25,max_single_weight=.45,min_single_weight=.05,top_weight_cap=.8,minimum_effective_n_ratio=.7,risk_chain_top1_cap=.55)
def panel(n=9):
    rows=[dict(security_id='security:'+str(i).zfill(10)+':'+str(i).zfill(9),issuer_id='issuer:'+str(i).zfill(10),ticker='T'+str(i),risk_chain='chain'+str(i)) for i in range(n)]
    value=dict(schema='LATEST_CONDITIONAL_TYPED_PANEL_V1',scope=core.SCOPE,cutoff='2026-09-17',universe=pd.DataFrame(rows),returns=pd.DataFrame({r['ticker']:[0.]*126 for r in rows},index=pd.bdate_range(end='2026-09-17',periods=126)),**dict.fromkeys(core.FALSE,False))
    for name,length in (('nominal_close',127),('raw_volume',63),('dollar_volume',63)):
        value[name]=pd.DataFrame({r['ticker']:[100.]*length for r in rows},index=pd.bdate_range(end='2026-09-17',periods=length))
    value['panel_content_sha256']=core.panel_digest(value);return value

class AllKTests(unittest.TestCase):
    def test_independent_panel_audit_is_required_and_exact(self):
        p=panel(4);reference=dict(path='bound-panel',sha256='a'*64)
        audit=dict(schema='LATEST_CONDITIONAL_PANEL_INDEPENDENT_READBACK_V1',panel_reference=reference,
            details=dict(observed_rows=101,numeric_channels=96,conditional_securities=4,returns_cells=504,nominal_close_cells=508,volume_cells=252,dollar_volume_cells=252,
                all_four_numeric_frames_reconstructed=True,universe_and_all_101_gap_rows_reconstructed=True,rangeindex_and_panel_checksum_verified=True,distinct_dates_and_original_facts_verified=True),
            **dict.fromkeys(('raw_oracle_repeated','producer_assemble_called','fitter_called','point_in_time_verified','legal_training_input_admitted','promotion_allowed'),False))
        m.validate_panel_audit(audit,reference,p)
        bad=copy.deepcopy(audit);bad['details']['returns_cells']=True
        with self.assertRaises(ValueError):m.validate_panel_audit(bad,reference,p)
        bad=copy.deepcopy(audit);bad['fitter_called']=True
        with self.assertRaises(ValueError):m.validate_panel_audit(bad,reference,p)

    def test_bounded_zero_and_any_orphan_refuses_new_fit(self):
        p=panel(4);scope=m.enumerate_plan(p,PARAMETERS,50000)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);doc=root/'panel.json';doc.write_text('{"panel":{}}');dh=m.hashlib.sha256(doc.read_bytes()).hexdigest()
            plan=dict(scope,panel_reference=dict(path=str(doc),sha256=dh),independent_panel_audit_reference=dict(path=str(doc),sha256=dh),historical_expected_source_hashes={})
            path=root/'plan.json';path.write_text(json.dumps(plan));h=m.hashlib.sha256(path.read_bytes()).hexdigest();folder=root/'tasks'
            partition=dict(live_verified_source_hashes={},archive_resolutions=[],historical_gap_observations=[])
            with patch.object(m,'prepare',return_value=plan),patch.object(m.panel_io,'typed_decode',return_value=p),patch.object(m,'verify_sources',return_value=partition),patch.object(m.archive,'load_contract',return_value={'authority_source_hashes':{}}),patch.object(m.fitter,'refit_dynamic_cutoff_weights',side_effect=AssertionError('no fit')) as fit:
                self.assertEqual(m.run_bounded(path,h,folder,max_new=0)['completed'],0)
                (folder/'unindexed.json.started.json').write_text('{}')
                with self.assertRaises(ValueError):m.run_bounded(path,h,folder,max_new=1)
                self.assertEqual(fit.call_count,0)

    def test_nine_complete_counts_and_unverified_anchor_alias(self):
        value=m.enumerate_plan(panel(),PARAMETERS,50000)
        self.assertEqual([r['issuer_unique_combinations'] for r in value['cardinalities']],[9,36,84,126,126,84,36,9,1])
        self.assertEqual(value['complete_issuer_unique_combinations'],511)
        self.assertEqual(value['canonical_task_count'],764);self.assertEqual(value['alias_count'],382)
        self.assertTrue(all(a['numerical_equivalence_verified'] is False and a['actual_fitter_called'] is False for a in value['anchor_aliases']))
        self.assertTrue(all(t['previous_target_weights'] is None for t in value['canonical_tasks']))
    def test_dynamic_size_issuer_dedup_and_limit(self):
        value=m.enumerate_plan(panel(4),PARAMETERS,50000);self.assertEqual(value['canonical_task_count'],2)
        p=panel(5);p['universe'].loc[4,'issuer_id']=p['universe'].loc[0,'issuer_id'];p['panel_content_sha256']=core.panel_digest(p)
        value=m.enumerate_plan(p,PARAMETERS,50000);self.assertEqual(value['input_issuer_count'],4);self.assertEqual(value['canonical_task_count'],4)
        with self.assertRaises(ValueError):m.enumerate_plan(panel(),PARAMETERS,10)
        bad=dict(PARAMETERS,fit_days=True)
        with self.assertRaises(ValueError):m.enumerate_plan(panel(),bad,50000)
    def test_started_excludes_even_first_fitter_failure(self):
        p=panel(4);scope=m.enumerate_plan(p,PARAMETERS,50000);task=scope['canonical_tasks'][0]
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);doc=folder/'panel.json';doc.write_text('{"panel":{}}');dh=m.hashlib.sha256(doc.read_bytes()).hexdigest()
            plan=dict(scope,panel_reference=dict(path=str(doc),sha256=dh),independent_panel_audit_reference=dict(path=str(doc),sha256=dh),historical_expected_source_hashes={})
            path=folder/'plan.json';path.write_text(json.dumps(plan));h=m.hashlib.sha256(path.read_bytes()).hexdigest();output=folder/'result.json'
            with patch.object(m,'prepare',return_value=plan),patch.object(m.panel_io,'typed_decode',return_value=p),patch.object(m,'verify_sources',return_value={}),patch.object(m.fitter,'refit_dynamic_cutoff_weights',side_effect=RuntimeError('solver')) as fit:
                with self.assertRaises(RuntimeError):m.run_one(path,h,task['task_id'],output)
                self.assertEqual(fit.call_count,1)
                with self.assertRaises(ValueError):m.run_one(path,h,task['task_id'],output)
                self.assertEqual(fit.call_count,1)
            self.assertFalse(output.exists());self.assertTrue(Path(str(output)+'.failure.json').exists())

if __name__=='__main__':unittest.main()
