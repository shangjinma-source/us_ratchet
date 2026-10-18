import copy
from collections import Counter
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import unittest

from scripts import ndx_historical_cross_k_economic_summary_20260923 as m


def read(ref):
    raw = Path(ref['path']).read_bytes()
    if hashlib.sha256(raw).hexdigest() != ref['sha256']:
        raise AssertionError('Actual referenced bytes differ')
    return json.loads(raw)


class EconomicIndependentTests(unittest.TestCase):
    def test_exact_decimal_pareto_independent_fraction_oracle(self):
        tiny = '0.' + '0'*99 + '1'
        values = [('a',['0','0','0','0']), ('b',[tiny,'0','0','0']),
                  ('btie',[tiny,'0','0','0']), ('c',['0','1','0','0']),
                  ('d',['-1','0','0','0'])]
        rows = [dict(task_id=name,pareto_coordinates=coordinates) for name,coordinates in values]
        vectors = {name:tuple(Fraction(v) for v in coords) for name,coords in values}
        dominated = set()
        for name, vector in vectors.items():
            for other, other_vector in vectors.items():
                differences = tuple(a-b for a,b in zip(other_vector,vector))
                if other != name and min(differences) >= 0 and max(differences) > 0:
                    dominated.add(name)
        self.assertEqual(m.pareto(rows), [name for name,_ in values if name not in dominated])
        self.assertEqual(m.pareto(rows), ['b','btie','c'])

    def test_all_101_saved_shapes_cash_is_not_rejection(self):
        audit = read(dict(path=str(m.AUDIT),sha256=m.AUDIT_SHA))
        self.assertEqual(len(audit['details']),101)
        rows=[]; outcomes=Counter(); zero_without_rejection=[]
        for detail in audit['details']:
            saved=read(detail['result_reference']); raw=read(detail['raw_reference']) if detail['raw_reference'] else None
            row=m.summarize_detail(detail,saved,raw); rows.append(row)
            execution=saved['execution']
            status='NO_PLAN' if execution['decisions'][0]['status']=='NO_PLAN' else execution['executions'][0]['status']
            outcomes[status]+=1
            self.assertEqual(row['outcome'],status)
            if row['metrics']['path_return']=='0' and status=='NO_PLAN':
                zero_without_rejection.append(row['task_id'])
                self.assertEqual(sum(fill['status']=='REJECTED' for fill in execution['executions']),0)
                self.assertEqual(row['rejection_reasons'],[])
            for reference in ('original_incumbent','nav_012922_native_currency'):
                for metric in m.METRICS:
                    expected=Fraction(row['metrics'][metric])-Fraction(row['benchmark_metrics'][reference][metric])
                    self.assertEqual(Fraction(row['candidate_minus_benchmark'][reference][metric]),expected)
        self.assertTrue(zero_without_rejection)
        result=m.aggregate(rows,101)
        self.assertEqual(result['outcome_counts'],dict(outcomes))
        self.assertEqual(sum(item['count'] for item in result['by_target_k']),101)
        self.assertGreater(sum(row.get('all_cash_last_session',False) for row in rows),outcomes['REJECTED'])
        self.assertTrue(all(result[key] is False for key in m.FALSE))

    def test_native_nav_upgrade_and_raw_linkage_refused(self):
        audit=read(dict(path=str(m.AUDIT),sha256=m.AUDIT_SHA))
        detail=audit['details'][0]
        saved=read(detail['result_reference']); raw=read(detail['raw_reference'])
        changed=copy.deepcopy(detail)
        changed['independent_result']['comparison']['currency_fx_equivalence_verified']=True
        with self.assertRaises(ValueError):m.summarize_detail(changed,saved,raw)
        changed=copy.deepcopy(raw);changed['parameter_digest']='0'*64
        with self.assertRaises(ValueError):m.summarize_detail(detail,saved,changed)


if __name__=='__main__':unittest.main()
