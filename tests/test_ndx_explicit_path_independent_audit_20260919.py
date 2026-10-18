from copy import deepcopy
import unittest
import pandas as pd
from scripts import ndx_explicit_path_independent_audit_20260919 as m


def fixture():
    selected={s:dict(ticker=s,issuer_id='issuer:'+s,risk_chain='chain:'+s) for s in 'BCDEFG'}
    prior={s:1/6 for s in 'ABCDEF'}
    parameters=dict(fit_days=126,shrinkage_intensity=.35,turnover_anchor_strength=.25,max_single_weight=.45,
        min_single_weight=.05,top_weight_cap=.8,minimum_effective_n_ratio=.7,risk_chain_top1_cap=.55)
    frame=pd.DataFrame(0.,index=pd.bdate_range(end='2023-04-28',periods=126),columns=list(selected))
    matrix=dict(dates=[d.date().isoformat() for d in frame.index],tickers=list(selected),returns=frame.to_numpy().tolist())
    mass=sum(prior.get(s,0) for s in selected)
    fitted=dict(schema='ndx_dynamic_cutoff_refit_research_v2',previous_target_weights=prior,
        declared_parameters={k:float(v) for k,v in parameters.items() if k!='fit_days'},
        weight_spec='constrained_fixed_shrinkage_turnover_anchor',
        anchor_policy='SURVIVING_SECURITY_TARGET_MASS_RENORMALIZED_NEW_ENTRIES_ZERO_NO_OVERLAP_DISABLED',
        targets={s:dict(ticker=s,issuer_id='issuer:'+s,target_weight=1/6) for s in selected},
        fit_start=matrix['dates'][0],fit_end='2023-04-28',cutoff='2023-04-28',fit_row_count=126,fit_data_sha256=m.digest(matrix),
        risk_chains_by_security={s:r['risk_chain'] for s,r in selected.items()},surviving_anchor_mass=mass,
        anchor_by_security={s:prior.get(s,0)/mass for s in selected},effective_anchor_strength=.25,
        declared_constraint_checks=dict(MAX_SINGLE_WEIGHT=True,MIN_SINGLE_WEIGHT=True,SECURITY_TOP3_WEIGHT=True,MINIMUM_EFFECTIVE_N=True,RISK_CHAIN_TOP1_WEIGHT=True),
        declared_constraints_passed=True,**dict.fromkeys(m.FALSE,False))
    return dict(fitted=fitted,selected=selected,parameters=parameters,returns=frame,cutoff='2023-04-28',previous=prior,weight_spec=fitted['weight_spec'])


class Tests(unittest.TestCase):
    def test_decimal_survivor_new_zero_exit_and_full_prior(self):
        args=fixture();value=m.inspect_period(**args)
        self.assertEqual(value['newly_entering_sids'],['G']);self.assertEqual(value['exiting_sids'],['A'])
        self.assertTrue(all(value['checks'].values()));self.assertEqual(value['fit_rows'],126)
        self.assertEqual(args['fitted']['anchor_by_security']['G'],0)

    def test_anchor_reset_drop_exit_and_new_entry_injection_rejected(self):
        for kind in ('reset','drop','mass','entry','strength'):
            args=fixture();f=args['fitted']
            if kind=='reset':f['previous_target_weights']={}
            if kind=='drop':f['previous_target_weights']=dict(f['previous_target_weights']);f['previous_target_weights'].pop('A')
            if kind=='mass':f['surviving_anchor_mass']=1
            if kind=='entry':f['anchor_by_security']['G']=.1
            if kind=='strength':f['effective_anchor_strength']=0
            with self.subTest(kind=kind),self.assertRaises(ValueError):m.inspect_period(**args)

    def test_matrix_risk_and_nonnumeric_metadata_rejected(self):
        for kind in ('matrix','rowcount','nan','bool','risk','identity'):
            args=fixture();f=args['fitted']
            if kind=='matrix':args['returns'].iloc[-1,0]=.01
            if kind=='rowcount':f['fit_row_count']=True
            if kind=='nan':f['targets']['B']['target_weight']=float('nan')
            if kind=='bool':f['effective_anchor_strength']=True
            if kind=='risk':
                for s in f['targets']:f['targets'][s]['target_weight']=.7 if s=='B' else .06
            if kind=='identity':f['targets']['B']['issuer_id']='OTHER'
            with self.subTest(kind=kind),self.assertRaises(ValueError):m.inspect_period(**args)


if __name__=='__main__':unittest.main()
