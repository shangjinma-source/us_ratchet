"""Synthetic equivalence only; no real month or account execution."""
import sys
import unittest
from copy import deepcopy
from pathlib import Path
from datetime import date,timedelta
from fractions import Fraction as F
from math import prod
from backtest.research_exact_fast_guided import enhanced_search as original
from backtest.research_exact_fast_guided_observed import enhanced_search as observed
from backtest.downside_candidate_observer_research import DownsideCandidateObserver


def fixture():
    days=[(date(2020,1,1)+timedelta(days=i)).isoformat() for i in range(252)]
    daily={s:[F(0)]*252 for s in ('A','B','C')}
    for i in range(12):
        daily['A'][21*i+20]=F('0.5') if i%2 else F('-0.3')
        daily['B'][21*i+20]=F('-0.2') if i%2 else F('0.3')
        daily['C'][21*i+20]=F('-0.02') if i%2 else F('0.05')
    args=dict(prices={'A':'7','B':'11','C':'5'},metadata={s:dict(ticker=s,issuer_id=s) for s in daily},
              entered_cash='100',fee_bps='0',minimum_cash_buffer='0',
              training_scenarios=[{s:prod(1+v for v in r[i*21:(i+1)*21]) for s,r in daily.items()} for i in range(12)],
              scenario_dates=days[20::21],decision_date=days[-1],max_objective_evaluations=256,fixed_seed='observer-fixture')
    kwargs=dict(max_holdings=2,search_arguments=args,stock_returns={s:dict(zip(days,r)) for s,r in daily.items()},
                qqq_reference=dict(zip(days,[F('-0.01')]*252)),max_risk_evaluations=1000)
    return args,kwargs


def traced(function, arguments, observer=None):
    """Observe original functions independently at return after visited/cache update."""
    sequence=[];last={};names={'research_exact_fast_search.py':'base','saved_quantity_candidate_comparison.py':'comparison',
                              'research_exact_fast_search_observed.py':'base','saved_quantity_candidate_comparison_observed.py':'comparison'}
    def profile(frame,event,result):
        name=Path(frame.f_code.co_filename).name
        if event!='return' or frame.f_code.co_name!='evaluate' or name not in names:return
        phase=names[name];local=frame.f_locals
        count=len(local['visited'] if phase=='base' else local['cache'])
        if count>last.get(phase,0):
            signature=local['signature'];sequence.append((phase,count-1,signature));last[phase]=count
    previous=sys.getprofile();sys.setprofile(profile)
    try:
        output=function(**arguments) if observer is None else function(candidate_observer=observer,**arguments)
    finally:sys.setprofile(previous)
    return output,sequence


class RecordingObserver:
    def __init__(self,inner):self.inner=inner;self.calls=[]
    def observe(self,q,*,phase,evaluation_index):
        self.calls.append((phase,evaluation_index,tuple(sorted(q.items()))))
        self.inner.observe(q,phase=phase,evaluation_index=evaluation_index)


class ObservedSearchTests(unittest.TestCase):
    def test_original_and_observed_complete_paths(self):
        args,kwargs=fixture();before=deepcopy(args)
        expected,original_sequence=traced(original,args)
        plain,plain_sequence=traced(observed,args)
        hook=RecordingObserver(DownsideCandidateObserver(**kwargs))
        actual,actual_sequence=traced(observed,args,hook)
        self.assertEqual(plain,expected);self.assertEqual(actual,expected)
        self.assertEqual(original_sequence,plain_sequence)
        self.assertEqual(original_sequence,actual_sequence)
        self.assertEqual(original_sequence,hook.calls)
        self.assertEqual(sum(p=='base' for p,_,_ in hook.calls),expected['objective_evaluations'])
        additional=expected['continuous_comparison']['exact_evaluations']
        self.assertEqual(sum(p=='comparison' for p,_,_ in hook.calls),additional['saved_unique']+additional['new_unique'])
        self.assertGreater(additional['new_unique'],0)
        hook.inner.end_observation();result=hook.inner.finalize()
        self.assertFalse(result['search_coverage_verified']);self.assertEqual(args,before)

    def test_failure_propagates_from_both_phases(self):
        args,_=fixture()
        for target in ('base','comparison'):
            class Fail:
                def observe(self,q,*,phase,evaluation_index):
                    if phase==target:raise RuntimeError('observer failed '+phase)
            with self.subTest(phase=target),self.assertRaisesRegex(RuntimeError,'observer failed '+target):
                observed(candidate_observer=Fail(),**args)

    def test_insufficient_original_budget_is_not_completed_stream(self):
        args,kwargs=fixture();args['max_objective_evaluations']=1
        observer=DownsideCandidateObserver(**dict(kwargs,search_arguments=args))
        result=observed(candidate_observer=observer,**args)
        self.assertIsNone(result['selected'])
        self.assertEqual(result['objective_evaluations'],0)
        with self.assertRaisesRegex(ValueError,'NOT_ENDED'):observer.finalize()


if __name__=='__main__':unittest.main()
