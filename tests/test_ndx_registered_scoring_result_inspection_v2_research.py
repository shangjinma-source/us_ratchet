"""Synthetic saved evidence only: never invoke a fitter or certificate solver."""
from copy import deepcopy
from unittest.mock import patch
import unittest
from backtest import ndx_registered_scoring_result_inspection_v2_research as m
from test_ndx_registered_scoring_result_inspection_research import fixture as original_fixture


def source_map():
    out={f'/synthetic/fitter{i}.py':'a'*64 for i in range(23)}
    out.update({f'/synthetic/{name}':sha for name,sha in m.RECOVERY_SOURCES.items()})
    return out


def certificate(names,constraints,*,passed=True):
    values=dict.fromkeys(names,.25)
    residuals=dict(simplex_abs=0.,lower=-.2,upper=-.2,top_k=-.05,hhi=-.1,effective_n_deficit=-1.2)
    if constraints['group_labels'] is not None:
        residuals.update({'group:'+label:(-.3 if passed else .45) for label in set(constraints['group_labels'].values())})
    result=dict(schema='ndx_projection_kkt_certificate_research_v1',scope='FIXED_TARGET_CONVEX_PROJECTION_ONLY',certified=passed,
        certification_kind='NUMERICAL_KKT_WITH_DISCLOSED_ABSOLUTE_TOLERANCES',target_preprocessing='CLIP_NEGATIVE_NORMALIZE_OR_UNIFORM_IF_ALL_NONPOSITIVE',
        target=values.copy(),candidate=values.copy(),constraints=deepcopy(constraints),objective_value=0.,objective='SUM_SQUARED_DISTANCE_TO_NORMALIZED_TARGET',
        top_subset_count=4,max_top_subsets=100000,tolerances=dict(primal=1e-10,active=1e-9,stationarity=1e-9,complementarity=1e-10),
        primal_residuals=residuals,individual_bound_residuals={name:dict(lower=-.2,upper=-.2) for name in names},primal_passed=passed,
        status='NUMERICAL_KKT_CERTIFIED' if passed else 'PRIMAL_REJECTED',**dict.fromkeys(m.AUTHORITY_KEYS,False))
    if passed:result.update(active_constraints=[],equality_multiplier=0.,stationarity_residuals=dict.fromkeys(names,0.),stationarity_max_abs=0.,complementarity_max_abs=0.,dual_passed=True,all_top_subsets_examined=True)
    return result


def attempt(securities,*,grouped=True,passed=True,independent_passed=True):
    names=[s['ticker'] for s in securities]
    constraints=dict(max_weight=.45,min_weight=.05,top_weight_count=3,top_weight_cap=.8,min_effective_n=2.8,group_labels={s['ticker']:s['risk_chain'] for s in securities} if grouped else None,max_group_weight=.55 if grouped else None)
    cert=certificate(names,constraints,passed=passed)
    r=dict(schema='ndx_projection_reconstruction_research_v1',scope='PROPOSED_ACTIVE_FACE_PROJECTION_ONLY',certified=passed,weights=dict.fromkeys(names,.25) if passed else None,
        proposed_candidate=dict.fromkeys(names,.25),raw_target=dict.fromkeys(names,.25),constraints=constraints,proposed_certificate=deepcopy(cert),
        source_hashes={f'/synthetic/{n}':h for n,h in m.RECOVERY_SOURCES.items()},activity_tolerance=1e-6,rank_relative_tolerance=1e-12,max_top_subsets=100000,
        active_subset_search_performed=False,status='RECONSTRUCTED_NUMERICAL_KKT_CERTIFIED' if passed else 'RECONSTRUCTION_NOT_CERTIFIED',
        affine_constraints=['SIMPLEX'],affine_rows=[[1.]*4],affine_rhs=[1.],affine_rank=1,affine_singular_values=[2.],affine_center=[.25]*4,
        nullspace_target=[0.]*4,affine_center_residuals=[0.],hhi_radius_squared=.1,certificate=cert,reconstructed_candidate=dict.fromkeys(names,.25),reconstructed_affine_residuals=[0.],**dict.fromkeys(m.AUTHORITY_KEYS,False))
    out=dict(optimizer_message='saved failed proposal',reconstruction=r)
    if passed:
        independent=deepcopy(cert)
        if not independent_passed:
            independent.update(certified=False,status='KKT_NOT_CERTIFIED',stationarity_residuals=dict.fromkeys(names,2e-9),stationarity_max_abs=2e-9)
        out.update(independent_certificate=independent,failed_optimizer_vector=[.25]*4+[0.]*5)
    return out


def fixture():
    args=original_fixture(m.SPECS[1]);args['numerical_source_hashes']=source_map();args['saved_fit']['source_hashes']=source_map()
    return args


class Tests(unittest.TestCase):
    def test_original_all_three_specs_source_and_score_checks_unchanged(self):
        for spec in m.SPECS:
            args=original_fixture(spec);before=deepcopy(args)
            with patch.object(m.arithmetic,'inspect_fitted_scoring_windows',wraps=m.arithmetic.inspect_fitted_scoring_windows) as score:
                out=m.inspect_registered_scoring_result(**args)
            self.assertEqual(out['status'],'PASS');self.assertEqual(score.call_count,1);self.assertEqual(args,before)
            self.assertEqual(out['schema'],'REGISTERED_SCORING_RESULT_INSPECTION_V1')
            self.assertFalse(out['recovery_certificates_recomputed'])

    def test_thirteen_failed_group_recoveries_normal_fallback_no_fake_unique_assignment(self):
        args=fixture();fit=args['saved_fit'];sec=fit['securities']
        fit['reconstruction_attempts']=[attempt(sec,passed=False) for _ in range(13)]
        for w in fit['windows']:w['projection_relaxed']=True
        # Reproduce saved score from explicit synthetic windows, never fit.
        from backtest import ndx_multidecision_window_scoring_research as reducer
        args['saved_score']=reducer.reduce_fitted_scoring_windows(**args['assembled']['reducer_inputs'],fitted_windows=fit['windows'])
        args['saved_score_inspection']=m.arithmetic.inspect_fitted_scoring_windows(**args['assembled']['reducer_inputs'],fitted_windows=fit['windows'],saved_score=args['saved_score'])
        out=m.inspect_registered_scoring_result(**args)
        self.assertEqual(out['recovery_evidence_inspection']['failed_group_attempt_count'],13)
        self.assertFalse(out['recovery_evidence_inspection']['unique_window_assignment_claimed'])
        self.assertEqual(out['reconstruction_attempts_preserved'],fit['reconstruction_attempts'])

    def test_two_and_four_field_modes_legal_order_and_terminal_weights(self):
        args=fixture();sec=args['saved_fit']['securities'];windows=args['saved_fit']['windows'];sources=source_map()
        pairs=[attempt(sec,passed=False),attempt(sec,grouped=False)]
        windows[0]['projection_relaxed']=True
        self.assertTrue(m.inspect_recovery_evidence(pairs,windows,sec,m.SPECS[1],sources)['ordered_window_assignment_exists'])
        four_failed=attempt(sec,independent_passed=False)
        m.inspect_recovery_evidence([four_failed],windows,sec,m.SPECS[1],sources)
        for change in ('reversed','no_relaxed','ungrouped_failure','weights','too_many'):
            a=deepcopy(pairs);w=deepcopy(windows)
            if change=='reversed':a.reverse();w=w[:1]
            elif change=='no_relaxed':
                for row in w:row['projection_relaxed']=False
            elif change=='ungrouped_failure':a=[attempt(sec,grouped=False,passed=False)]
            elif change=='weights':
                for row in w:row['weights']=[.1,.2,.3,.4]
            else:a=[attempt(sec,passed=False)]*27
            with self.subTest(change=change),self.assertRaises(ValueError):m.inspect_recovery_evidence(a,w,sec,m.SPECS[1],sources)

    def test_strict_status_certificate_source_flags_and_vectors(self):
        args=fixture();sec=args['saved_fit']['securities'];windows=args['saved_fit']['windows']
        original=attempt(sec)
        for change in ('extra','source','authority','tol','vector','candidate','constraints','ticker','certified','primal','active','stationarity','two_true'):
            a=deepcopy(original);r=a['reconstruction'];c=a['independent_certificate']
            if change=='extra':a['window_index']=0
            elif change=='source':r['source_hashes'][next(iter(r['source_hashes']))]='f'*64
            elif change=='authority':r['task_recomputed']=0
            elif change=='tol':c['tolerances']['primal']=1e-8
            elif change=='vector':a['failed_optimizer_vector'][0]=True
            elif change=='candidate':c['candidate'][sec[0]['ticker']]=.4
            elif change=='constraints':r['constraints']['max_group_weight']=.9
            elif change=='ticker':r['raw_target']['FOREIGN']=.25
            elif change=='certified':c['certified']=1
            elif change=='primal':c['primal_residuals']['upper']=.1
            elif change=='active':c['active_constraints']=[dict(name='FOREIGN',residual=0.,multiplier=0.,complementarity_residual=0.)]
            elif change=='stationarity':c['stationarity_max_abs']=1e-10
            else:a={k:v for k,v in a.items() if k in {'optimizer_message','reconstruction'}}
            with self.subTest(change=change),self.assertRaises(ValueError):m.inspect_recovery_evidence([a],windows,sec,m.SPECS[1],source_map())


if __name__=='__main__':unittest.main()
