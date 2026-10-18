import copy
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from scripts import ndx_remaining_standard_cash_inputs_20261002 as m
from test_ndx_first_period_standard_cash_inputs_20261002 import fixture as first_fixture

def fixture():
    d,r=first_fixture(); base=copy.deepcopy(d['inventory']['rows'][0]); d['inventory']['rows']=[];d['scenarios']['rows']=[]
    clocks=[('2023-03-31','2023-04-03'),('2023-04-28','2023-05-01'),('2023-05-31','2023-06-01'),('2023-06-30','2023-07-03'),('2023-07-31','2023-08-01'),('2023-08-31','2023-09-01')]
    for lane in (*m.LANES,'INCUMBENT_ADD_ONLY_CONTROL','CASH_RETENTION_CONTROL'):
        for day,execution in clocks:
            row=copy.deepcopy(base);row.update(lane=lane,decision_date=day,execution_date=execution)
            row['lane_target'].update(decision_date=day,execution_date=execution)
            row['baseline']['shares']={'s0':2,'s1':3,'s2':4,'s3':5}
            for sec in row['securities']:sec['dated_identity_evidence']=[]
            if lane=='CASH_RETENTION_CONTROL':row['lane_target']['targets']={}
            index=len(d['inventory']['rows']); d['inventory']['rows'].append(row)
            for amount in ('1000','10000'):
                d['scenarios']['rows'].append({'scenario_id':lane+day+amount,'lane':lane,'decision_date':day,'execution_date':execution,'standardized_cash_injection_usd':amount,'parent_row_reference':dict(r['inventory'],json_pointer=f'/rows/{index}'),'hypothetical_research_only':True,'real_user_cash_claimed':False,'fork_executable':False})
    return d,r

class RemainingTests(unittest.TestCase):
    def test_64_roles_and_preservation(self):
        d,r=fixture();before=copy.deepcopy(d);out=m.assemble(d,r)
        self.assertEqual(d,before);self.assertEqual(len(out['rows']),64)
        from collections import Counter
        self.assertEqual(Counter(v['branch_role'] for v in out['rows']),{'MAIN_LANE':40,'MIGRATION_CONTROL':12,'CASH_RETENTION_CONTROL':12})
        for row in out['rows']:
            self.assertEqual(row['holdings'],row['original_inventory_row']['baseline']['shares'])
            if row['zero_buy_only']:self.assertFalse(row['target_l1_applicable']);self.assertEqual(row['allowed_buy_security_ids'],[])
    def test_bad_union_issuer_risk_price(self):
        for case in ('union','issuer','risk','price'):
            d,r=fixture();row=d['inventory']['rows'][1];sec=row['securities'][0]
            if case=='union':row['baseline']['shares']['missing']=1
            elif case=='issuer':sec['dated_identity_evidence']=[{'value':{'security_id':'s0','ticker':'T0','issuer_id':'other'}}]
            elif case=='risk':sec['risk_observations'][0]['observation_date']='2024-01-01'
            else:sec['execution_open_observations'].append({'currency':'USD','decimal_literal':'101'})
            with self.assertRaises(ValueError):m.assemble(d,r)
    def test_same_issuer_distinct_sid_preserved(self):
        d,r=fixture();row=d['inventory']['rows'][1]
        row['lane_target']['targets']['s1']['issuer_id']='i0'
        row['securities'][1]['saved_coordinates'][0]['value']['issuer_id']='i0'
        out=m.assemble(d,r);self.assertEqual(out['rows'][0]['securities']['s0']['issuer_id'],out['rows'][0]['securities']['s1']['issuer_id'])
        self.assertEqual(len(out['rows'][0]['holdings']),4)
    def test_existing_namespace_refuses_before_assembly(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(m,'OUTPUT',Path(temp)),patch.object(m,'assemble') as call:
            with self.assertRaises(ValueError):m.publish()
            call.assert_not_called()

if __name__=='__main__':unittest.main()
