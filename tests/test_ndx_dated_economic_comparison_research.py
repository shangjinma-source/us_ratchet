from copy import deepcopy
from decimal import localcontext,Inexact,ROUND_DOWN
from fractions import Fraction
import unittest
from backtest import ndx_dated_economic_comparison_research as core
from test_ndx_dated_account_input_research import fixture


def exact(v):return dict(numerator=str(v.numerator),denominator=str(v.denominator))
def fixture_comparison():
    calendar=next(iter(fixture()['candidate_channels_by_security'].values()))['calendar'][126:]
    def continuous(role):
        v=[Fraction(1)]+[Fraction(9,10)]*125+[Fraction(11,10)] if role=='candidate' else [Fraction(1)]*127
        count=4 if role=='candidate' else 8
        positions=[dict(security_id=f'{role}{i}',issuer_id=f'issuer:{i}',ticker=f'T{i}',target_weight=1/count) for i in range(count)]
        return dict(schema='DATED_FIXED_FRACTIONAL_WEIGHT_DIAGNOSTIC_V1',calendar=calendar,path=[dict(session=d,normalized_value=exact(x)) for d,x in zip(calendar,v)],interval_count=126,cumulative_return_exact=exact(v[-1]-1),annualized_return_exact=exact(v[-1]**2-1),max_drawdown_exact=exact(Fraction(1,10) if role=='candidate' else Fraction(0)),annualization_exponent_exact=exact(Fraction(2)),positions_preserved=positions,**dict.fromkeys(('formal_cohort_verified','point_in_time_verified','promotion_allowed','future_independent_oos','untouched_holdout','accounting_conservation_verified','dividends_included','weights_refitted','weights_normalized','daily_rebalancing_performed'),False))
    tracks={r:continuous(r) for r in ('candidate','incumbent')}
    def account(role):
        values=[25000.]+[22500.]*125+[30000.] if role=='candidate' else [25000.]*127
        return dict(schema='ndx_dynamic_frozen_execution_research_v2' if role=='candidate' else 'ndx_dynamic_frozen_incumbent_control_v1',daily=[dict(session=d,total_value_usd=v,cash_usd=25000. if i==0 else 100.,shares={}) for i,(d,v) in enumerate(zip(calendar,values))],decisions=[dict(decision_date=calendar[0],execution_date=calendar[1],targets={p['security_id']:dict(issuer_id=p['issuer_id'],target_weight=p['target_weight']) for p in tracks[role]['positions_preserved']})],executions=[dict(session=calendar[1],decision_date=calendar[0],status='FILLED' if role=='candidate' else 'REJECTED')],summary={'original':'preserved'},point_in_time_verified=False,promotion_allowed=False,dividend_modelled=False)
    values=[Fraction(1)]+[Fraction(4,5)]*125+[Fraction(6,5)]
    modes={mode:dict(mode=mode,status='RETROSPECTIVE_REFERENCE_METRICS_COMPUTED',missing_sessions=[],observation_count=127,interval_count=126,observations=[dict(session=d,saved_value_exact=str(v),normalized_value_exact=str(v)) for d,v in zip(calendar,values)],interval_returns=[dict(previous_session=calendar[i],session=calendar[i+1],return_exact=str(values[i+1]/values[i]-1)) for i in range(126)],metrics=dict(cumulative_return={'exact':'1/5'},annualized_return={'exact':'11/25'},maximum_drawdown={'exact':'1/5'})) for mode in core.MODES}
    flags=dict(point_in_time_verified=False,promotion_allowed=False,future_independent_oos=False,untouched_holdout=False)
    return dict(candidate_account=account('candidate'),incumbent_account=account('incumbent'),continuous_document=dict(schema='SOURCE_BOUND_DATED_CONTINUOUS_WEIGHT_DIAGNOSTIC_V1',tracks=tracks,**flags),nav_metrics=dict(schema='SAME_WINDOW_NAV_REFERENCE_METRICS_V1',status='HISTORICAL_EXTERNAL_REFERENCE_ONLY',mode_order=list(core.MODES),modes=modes,modes_retained_separately=True,reference_calendar={'dates':calendar},**flags),source_references={k:dict(path=k+'.json',sha256='a'*64) for k in ('candidate_account','incumbent_account','continuous','nav_metrics')})

class Tests(unittest.TestCase):
    def test_exact_metrics_distance_and_both_identical_modes(self):
        a=fixture_comparison();old=deepcopy(a);r=core.compare_dated_paths(**a)
        self.assertEqual(a,old);m=r['tracks']['candidate_integer']['metrics']
        self.assertEqual(m['cumulative_return']['exact'],'1/5');self.assertEqual(m['annualized_return']['exact'],'11/25');self.assertEqual(m['maximum_drawdown']['exact'],'1/10')
        self.assertEqual(len(r['nav_modes']),2)
        for mode in core.MODES:
            d=r['absolute_distance_comparisons'][mode]['integer'];self.assertEqual(d['annualized_return']['candidate_minus_incumbent_distance']['exact'],'-11/25');self.assertEqual(d['maximum_drawdown']['candidate_minus_incumbent_distance']['exact'],'-1/10')
        self.assertEqual(r['saved_paths_preserved']['incumbent']['integer_account']['executions'][0]['status'],'REJECTED')
        self.assertFalse(r['formal_comparison_passed']);self.assertFalse(r['winner_selected'])

    def test_missing_reorder_initial_and_fake_metrics_reject(self):
        for case in ('missing','reorder','initial','metrics','bool','future','badnav'):
            a=fixture_comparison()
            if case=='missing':a['candidate_account']['daily'].pop(40)
            if case=='reorder':a['candidate_account']['daily'][3:5]=reversed(a['candidate_account']['daily'][3:5])
            if case=='initial':a['incumbent_account']['daily'][0]['total_value_usd']=24999.
            if case=='metrics':a['continuous_document']['tracks']['candidate']['annualized_return_exact']={'numerator':'9','denominator':'1'}
            if case=='bool':a['nav_metrics']['modes'][core.MODES[0]]['interval_count']=True
            if case=='future':a['continuous_document']['future_independent_oos']=True
            if case=='badnav':a['nav_metrics']['modes'][core.MODES[0]]['observations'][40]['saved_value_exact']='0'
            with self.subTest(case=case),self.assertRaises(ValueError):core.compare_dated_paths(**a)

    def test_first_peak_and_hostile_context(self):
        a=fixture_comparison();v=a['candidate_account']['daily']
        for row in v[1:]:row['total_value_usd']=20000.
        with localcontext() as ctx:
            ctx.prec=2;ctx.rounding=ROUND_DOWN;ctx.traps[Inexact]=True
            r=core.compare_dated_paths(**a)
        m=r['tracks']['candidate_integer']['metrics'];self.assertEqual(m['maximum_drawdown']['exact'],'1/5');self.assertEqual(m['drawdown']['peak_index'],0);self.assertEqual(m['drawdown']['trough_index'],1);self.assertEqual(m['annualized_return']['exact'],'-9/25')

    def test_target_and_source_roles_cannot_be_silently_mixed(self):
        a=fixture_comparison();a['incumbent_account']['decisions'][0]['targets']['incumbent0']['target_weight']=.2
        with self.assertRaises(ValueError):core.compare_dated_paths(**a)
        a=fixture_comparison();a['source_references'].pop('nav_metrics')
        with self.assertRaises(ValueError):core.compare_dated_paths(**a)

if __name__=='__main__':unittest.main()
