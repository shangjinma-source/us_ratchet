import unittest
from copy import deepcopy
from datetime import date, timedelta
from fractions import Fraction as F
from docs.candidates.qqq_risk_budget_exact import scale_targets_to_qqq_risk

DAYS=[]
day=date(2026,1,1)
while len(DAYS)<63:
    if day.weekday()<5:DAYS.append(day.isoformat())
    day+=timedelta(days=1)


def gross(amplitude):
    return {day:str(1+F(amplitude)*(1 if i%2 else -1)) for i,day in enumerate(DAYS)}


def fixture():
    return dict(decision_date=DAYS[-1],target_quantities={'A':100},decision_prices={'A':'1'},
                tradable_equity='100',stock_gross_returns={'A':gross('1/50')},qqq_gross_returns=gross('1/100'))


class Tests(unittest.TestCase):
    def test_half_scale_exact_sample_variance(self):
        args=fixture();before=deepcopy(args);r=scale_targets_to_qqq_risk(**args)
        self.assertEqual(r['target_quantities'],{'A':50});self.assertEqual(r['scale_squared_exact'],'1/4')
        self.assertEqual(F(r['portfolio_variance']),F(r['qqq_variance'])*4)
        values=[F(v)-1 for v in args['qqq_gross_returns'].values()];mean=sum(values)/63
        self.assertEqual(F(r['qqq_variance']),sum((v-mean)**2 for v in values)/62)
        self.assertEqual(args,before)

    def test_cash_weight_zero_return_not_renormalized(self):
        args=fixture();args['target_quantities']['A']=50
        r=scale_targets_to_qqq_risk(**args)
        self.assertEqual(r['target_quantities'],{'A':50});self.assertEqual(r['original_cash_weight'],'1/2')
        self.assertEqual(r['scale_squared_exact'],'1')

    def test_covariance_changes_portfolio_risk(self):
        args=fixture();args.update(target_quantities={'A':50,'B':50},decision_prices={'A':1,'B':1},stock_gross_returns={'A':gross('1/50'),'B':gross('1/50')})
        self.assertEqual(scale_targets_to_qqq_risk(**args)['target_quantities'],{'A':25,'B':25})
        args['stock_gross_returns']['B']=gross('-1/50')
        r=scale_targets_to_qqq_risk(**args)
        self.assertEqual(r['portfolio_variance'],'0');self.assertEqual(r['target_quantities'],{'A':50,'B':50})

    def test_zero_benchmark_and_zero_portfolio(self):
        args=fixture();args['qqq_gross_returns']=gross('0')
        self.assertEqual(scale_targets_to_qqq_risk(**args)['target_quantities'],{'A':0})
        args['stock_gross_returns']['A']=gross('0')
        self.assertEqual(scale_targets_to_qqq_risk(**args)['target_quantities'],{'A':100})

    def test_integer_boundary_uses_no_float(self):
        args=fixture();args.update(target_quantities={'A':2},decision_prices={'A':50})
        self.assertEqual(scale_targets_to_qqq_risk(**args)['target_quantities'],{'A':1})
        args['qqq_gross_returns']=gross(F(1,50)*(F(1,2)-F(1,10**30)))
        self.assertEqual(scale_targets_to_qqq_risk(**args)['target_quantities'],{'A':0})

    def test_no_leverage_low_risk(self):
        args=fixture();args['qqq_gross_returns']=gross('1/10')
        self.assertEqual(scale_targets_to_qqq_risk(**args)['target_quantities'],{'A':100})

    def test_bad_inputs_fail_instead_of_fill_or_fallback(self):
        mutations=[lambda a:a['stock_gross_returns']['A'].pop(DAYS[0]),
                   lambda a:a['qqq_gross_returns'].pop(DAYS[0]),
                   lambda a:a.update(decision_date='2026-12-31'),
                   lambda a:a['stock_gross_returns']['A'].__setitem__(DAYS[0],'0'),
                   lambda a:a['stock_gross_returns']['A'].__setitem__(DAYS[0],True),
                   lambda a:a['decision_prices'].__setitem__('A',0),
                   lambda a:a.update(tradable_equity=0),
                   lambda a:a['target_quantities'].__setitem__('A',101),
                   lambda a:a['target_quantities'].__setitem__('A',-1),
                   lambda a:a['target_quantities'].__setitem__('A',True),
                   lambda a:a['decision_prices'].__setitem__('B',1),
                   lambda a:a['stock_gross_returns']['A'].__setitem__('2026-12-31','1')]
        for i,mutate in enumerate(mutations):
            args=fixture();mutate(args)
            with self.subTest(case=i),self.assertRaises(ValueError):scale_targets_to_qqq_risk(**args)

    def test_real_long_fraction_serialization_is_bounded_and_process_local(self):
        import subprocess,sys
        from pathlib import Path
        root=Path(__file__).resolve().parents[1]
        original_limit=sys.get_int_max_str_digits()
        # Real archived gross-return fractions create >4300 digit ratios.
        code="""
import json,sys
from fractions import Fraction
from pathlib import Path
from docs.candidates.qqq_risk_budget_exact import scale_targets_to_qqq_risk
from docs.candidates.qqq_risk_budget_offline_limits import configure_offline_fraction_serialization
rows=json.loads(Path('tmp/risk_budget_64d_inventory_20261105/risk_inputs.json').read_bytes())['windows']
sys.set_int_max_str_digits(4300)
failed=None
for row in rows:
    try:scale_targets_to_qqq_risk(**row['arguments'])
    except ValueError as error:
        if '4300' not in str(error):raise
        failed=row;break
assert failed is not None
policy=configure_offline_fraction_serialization()
assert policy['integer_string_digits']==100000
result=scale_targets_to_qqq_risk(**failed['arguments'])
assert max(len(x) for x in result['scale_squared_exact'].split('/'))>4300
assert str(Fraction(result['scale_squared_exact']))==result['scale_squared_exact']
try:int('9'*100001)
except ValueError:pass
else:raise AssertionError('Bounded limit was disabled')
print('REAL_LONG_FRACTION_ROUNDTRIP_PASS')
"""
        child=subprocess.run([sys.executable,'-c',code],cwd=root,capture_output=True,text=True,timeout=30)
        self.assertEqual(child.returncode,0,child.stderr)
        self.assertIn('REAL_LONG_FRACTION_ROUNDTRIP_PASS',child.stdout)
        self.assertEqual(sys.get_int_max_str_digits(),original_limit)

if __name__=='__main__':unittest.main()
