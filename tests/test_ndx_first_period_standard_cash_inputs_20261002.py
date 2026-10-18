import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import ndx_first_period_standard_cash_inputs_20261002 as m

def fixture():
    refs={k:{'path':k,'sha256':str(i)*64} for i,k in enumerate(m.BOUND)}
    inv={'schema':'CONDITIONAL_NEW_CASH_SIX_COORDINATE_INVENTORY_V2','rows':[],'source_hashes':{},'cash_fork_called':False,'point_in_time_verified':False,'promotion_allowed':False}
    scenarios={'schema':'STANDARD_CASH_RESEARCH_SCENARIOS_V1','rows':[],'parent_inventory_reference':refs['inventory'],'cash_fork_called':False,'point_in_time_verified':False,'promotion_allowed':False}
    for i,lane in enumerate(m.LANES):
        targets={f's{j}':{'ticker':f'T{j}','issuer_id':f'i{j}','target_weight':0.25} for j in range(4)}
        row={'lane':lane,'decision_date':'2023-03-31','execution_date':'2023-04-03','baseline':{'shares':{},'cash_usd':25000.0},'baseline_cash_encoding':{'decimal_literal':'25000.0','encoding':'SAVED_JSON_FLOAT_TO_STR_NO_PRECISION_UPGRADE'},'cash_event_amount_usd':None,'fork_executable':False,'lane_target':{'decision_date':'2023-03-31','execution_date':'2023-04-03','targets':targets},'union_security_ids':list(targets),'gaps':[],'securities':[]}
        for sid,t in targets.items(): row['securities'].append({'security_id':sid,'identity_interval_certified':False,'provider_binding_verified':False,'saved_coordinates':[{'value':t}],'execution_open_observations':[{'currency':'USD','decimal_literal':'100.000'}],'risk_observations':[{'observation_date':'2023-03-31','risk_chain':sid}]})
        inv['rows'].append(row)
        for amount in ('1000','10000'): scenarios['rows'].append({'scenario_id':lane+amount,'lane':lane,'decision_date':'2023-03-31','execution_date':'2023-04-03','standardized_cash_injection_usd':amount,'parent_row_reference':dict(refs['inventory'],json_pointer=f'/rows/{i}'),'hypothetical_research_only':True,'real_user_cash_claimed':False,'fork_executable':False})
    inv['rows'] += [{} for _ in range(32)]
    scenarios['rows'] += [{'decision_date':'2023-04-28'} for _ in range(64)]
    receipt={'inventory_reference':refs['inventory'],'source_hashes':{},'status':'SOURCE_LOCKED_INVENTORY_ONLY_NOT_FORK_READY','fork_executed':False}
    contract=dict(zip(m.RISK,(.45,.05,.8,.7,.55)),transaction_cost_bps=10,minimum_cash_buffer_usd=100)
    return {'inventory':inv,'scenarios':scenarios,'publication':receipt,'account':{'execution_contract':contract}},refs

class InputsTests(unittest.TestCase):
    def test_positive_preserves(self):
        d,r=fixture(); before=copy.deepcopy(d); result=m.assemble(d,r)
        self.assertEqual(d,before); self.assertEqual(result['scenario_count'],8)
        self.assertEqual(result['rows'][0]['original_inventory_row'],d['inventory']['rows'][0]);self.assertEqual(result['rows'][0]['transaction_cost_bps'],'10')
        self.assertFalse(result['cash_fork_called']);self.assertFalse(result['rows'][0]['target_weights_normalized'])
    def test_open_and_future_risk(self):
        for kind in ('open','risk','currency'):
            d,r=fixture(); s=d['inventory']['rows'][0]['securities'][0]
            if kind=='open':s['execution_open_observations'].append({'currency':'USD','decimal_literal':'101'})
            elif kind=='risk':s['risk_observations'][0]['observation_date']='2023-04-01'
            else:s['execution_open_observations'][0]['currency']='EUR'
            with self.assertRaises(ValueError):m.assemble(d,r)
    def test_duplicates_and_ref(self):
        for kind in ('duplicate','ref','issuer','authority'):
            d,r=fixture()
            if kind=='duplicate':d['scenarios']['rows'][1]=copy.deepcopy(d['scenarios']['rows'][0])
            elif kind=='ref':d['scenarios']['rows'][0]['parent_row_reference']['sha256']='x'
            elif kind=='issuer':d['inventory']['rows'][0]['lane_target']['targets']['s1']['issuer_id']='i0'
            else:d['inventory']['rows'][0]['securities'][0]['provider_binding_verified']=True
            with self.assertRaises(ValueError):m.assemble(d,r)
    def test_namespace_precedes_read(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(m,'OUTPUT',Path(temp)),patch.object(m,'assemble') as build:
            with self.assertRaises(ValueError):m.publish()
            build.assert_not_called()

if __name__=='__main__':unittest.main()
