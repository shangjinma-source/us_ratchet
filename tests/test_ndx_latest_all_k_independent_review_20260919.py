import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from test_ndx_latest_conditional_all_k_refit_20260919 import panel,PARAMETERS
from scripts import ndx_latest_conditional_all_k_refit_20260919 as recipe


def diagnostic(task,p):
    selected=task['selected'];sids=sorted(selected);tickers=[selected[s]['ticker'] for s in sids];frame=p['returns'][tickers]
    payload=dict(dates=[d.date().isoformat() for d in frame.index],tickers=tickers,returns=frame.to_numpy().tolist())
    return dict(schema='ndx_dynamic_cutoff_refit_research_v2',cutoff=task['cutoff'],weight_spec=task['weight_spec'],fit_row_count=126,
        effective_anchor_strength=0.,fit_data_sha256=recipe.digest(payload),fit_start=payload['dates'][0],fit_end=payload['dates'][-1],
        declared_parameters={k:float(v) for k,v in PARAMETERS.items() if k!='fit_days'},previous_target_weights={},surviving_anchor_mass=0.,
        anchor_by_security={s:0. for s in sids},risk_chains_by_security={s:selected[s]['risk_chain'] for s in sids},
        targets={s:dict(ticker=selected[s]['ticker'],issuer_id=selected[s]['issuer_id'],target_weight=.25) for s in sids},
        declared_constraint_checks={k:True for k in ('MAX_SINGLE_WEIGHT','MIN_SINGLE_WEIGHT','SECURITY_TOP3_WEIGHT','MINIMUM_EFFECTIVE_N','RISK_CHAIN_TOP1_WEIGHT')},
        declared_constraints_passed=True,source_hashes=recipe.fitter._sources(),
        **dict.fromkeys(('checkpoint_weights_used','point_in_time_verified','source_authenticity_verified','promotion_allowed','historical_task_evaluation_performed','order_generation_allowed'),False))


class IndependentAllKTests(unittest.TestCase):
    def test_resume_cannot_resign_false_archive_partition(self):
        p=panel(4);scope=recipe.enumerate_plan(p,PARAMETERS,50000);task=scope['canonical_tasks'][0]
        partition=dict(live_verified_source_hashes={},archive_resolutions=[],historical_gap_observations=[],historical_full_source_closure_recovered=False,point_in_time_verified=False,promotion_allowed=False)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);folder=root/'tasks';folder.mkdir();doc=root/'panel.json';doc.write_text('{"panel":{}}');dh=recipe.hashlib.sha256(doc.read_bytes()).hexdigest()
            sources=dict(recipe.LOADED);sources.update(recipe.fitter._sources())
            plan=dict(scope,panel_reference=dict(path=str(doc),sha256=dh),independent_panel_audit_reference=dict(path=str(doc),sha256=dh),historical_expected_source_hashes=sources)
            pp=root/'plan.json';pp.write_text(json.dumps(plan));ph=recipe.hashlib.sha256(pp.read_bytes()).hexdigest();pr=dict(path=str(pp),sha256=ph)
            output=folder/(task['task_id']+'.json');marker=Path(str(output)+'.started.json')
            marker.write_text(json.dumps(dict(schema='LATEST_ALL_K_SINGLE_ATTEMPT_V1',plan_sha256=ph,task_id=task['task_id'],attempt_count=1)))
            mh=recipe.hashlib.sha256(marker.read_bytes()).hexdigest();complete=dict(sources,**{str(pp):ph,str(marker):mh})
            partition['live_verified_source_hashes']=complete
            value=dict(schema='LATEST_CONDITIONAL_ALL_K_SINGLE_REFIT_V1',task=task,plan_reference=pr,attempt_count=1,
                result=diagnostic(task,p),status='FITTED_ORIGINAL_FIVE_RISKS_PASSED',historical_expected_source_hashes=complete,
                archive_resolution=partition,**dict.fromkeys(recipe.FALSE,False))
            with patch.object(recipe,'prepare',return_value=plan),patch.object(recipe.panel_io,'typed_decode',return_value=p),patch.object(recipe,'verify_sources',return_value=partition),patch.object(recipe.archive,'load_contract',return_value={'authority_source_hashes':{},'rows':{}}),patch.object(recipe.archive,'verify_expected_sources',return_value=partition),patch.object(recipe.fitter,'refit_dynamic_cutoff_weights',side_effect=AssertionError('no refit')) as fit:
                for bad in (False,'partition','sources'):
                    saved=copy.deepcopy(value)
                    if bad=='partition':saved['archive_resolution']['point_in_time_verified']=True
                    if bad=='sources':saved['result']['source_hashes']={}
                    output.write_text(json.dumps(saved));entry=dict(task_id=task['task_id'],path=str(output),sha256=recipe.hashlib.sha256(output.read_bytes()).hexdigest(),started_sha256=mh)
                    index=recipe.bounded_index(pr,folder,[entry],len(scope['canonical_tasks']));ip=folder/'index_external.json';ip.write_text(json.dumps(index));ih=recipe.hashlib.sha256(ip.read_bytes()).hexdigest()
                    if bad:
                        with self.assertRaises(ValueError):recipe.run_bounded(pp,ph,folder,max_new=0,index_path=ip,index_sha256=ih)
                    else:self.assertEqual(recipe.run_bounded(pp,ph,folder,max_new=0,index_path=ip,index_sha256=ih)['completed'],1)
                self.assertEqual(fit.call_count,0)

    def test_result_schema_matrix_and_overall_verdict(self):
        p=panel(4);task=recipe.enumerate_plan(p,PARAMETERS,50000)['canonical_tasks'][0];value=diagnostic(task,p)
        recipe.check_result(value,task,p)
        for key,replacement in (('schema','fake'),('fit_row_count',True),('effective_anchor_strength',.25),('declared_constraints_passed',False),('fit_data_sha256','0'*64)):
            bad=copy.deepcopy(value);bad[key]=replacement
            with self.subTest(key=key),self.assertRaises(ValueError):recipe.check_result(bad,task,p)

    def test_boolean_anchor_values_do_not_mean_no_prior(self):
        p=panel(4);task=recipe.enumerate_plan(p,PARAMETERS,50000)['canonical_tasks'][0]
        for field in ('surviving_anchor_mass','anchor_by_security'):
            value=diagnostic(task,p)
            if field=='surviving_anchor_mass':value[field]=False
            else:value[field][next(iter(value[field]))]=False
            with self.subTest(field=field),self.assertRaises(ValueError):recipe.check_result(value,task,p)

    def test_exclusive_marker_failure_happens_before_fitter(self):
        p=panel(4);scope=recipe.enumerate_plan(p,PARAMETERS,50000);task=scope['canonical_tasks'][0]
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);doc=root/'panel.json';doc.write_text('{"panel":{}}');h=recipe.hashlib.sha256(doc.read_bytes()).hexdigest()
            plan=dict(scope,panel_reference=dict(path=str(doc),sha256=h),independent_panel_audit_reference=dict(path=str(doc),sha256=h),historical_expected_source_hashes={})
            path=root/'plan.json';path.write_text(json.dumps(plan));ph=recipe.hashlib.sha256(path.read_bytes()).hexdigest()
            with patch.object(recipe,'prepare',return_value=plan),patch.object(recipe.panel_io,'typed_decode',return_value=p),patch.object(recipe,'verify_sources',return_value={}),patch.object(recipe,'exclusive_publish',side_effect=FileExistsError('racing marker')),patch.object(recipe.fitter,'refit_dynamic_cutoff_weights',side_effect=AssertionError('must not fit')) as fit:
                with self.assertRaises(FileExistsError):recipe.run_one(path,ph,task['task_id'],root/'task.json')
                self.assertEqual(fit.call_count,0)


if __name__=='__main__':unittest.main()
