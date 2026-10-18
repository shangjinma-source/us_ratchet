import tempfile
import unittest
from copy import deepcopy
from datetime import timedelta
from fractions import Fraction
import test_current_research_intraday_monthly_selection as monthly_fixture
from data.current_research_intraday_monthly_selection import build_intraday_monthly_top1_selection
from data.current_research_intraday_retarget_sizing import build_intraday_retarget_sizing, POLICY

class SizingTests(unittest.TestCase):
    def fixture(self,root):
        state,args=monthly_fixture.BridgeTests().fixture(root)
        selection=build_intraday_monthly_top1_selection(state,**args)
        now=args.pop('now');pins=dict(args['source_hashes']);refs={};units={}
        for sid,ticker,last,low in [('sndk','SNDK','1500.001','1400'),('new','NEW','100.001','100')]:
            pins['quote-'+sid]='a'*64;pins['unit-'+sid]='b'*64
            refs[sid]=dict(session_open='2026-11-02T09:30:00-05:00',session_close='2026-11-02T16:00:00-05:00',policy=POLICY,security_id=sid,ticker=ticker,session='2026-11-02',scope_id=state['account_id']+':2026-11',last_price=last,last_at=now.isoformat(),minute_low=low,minute_start=(now-timedelta(minutes=1)).isoformat(),minute_end=now.isoformat(),captured_at=now.isoformat(),checked_at=now.isoformat(),valid_until=(now+timedelta(seconds=120)).isoformat(),prior_buy_cap=None,buy_limit=low,sell_limit='1500.01' if sid=='sndk' else '100.01',source_hashes={'quote-'+sid:'a'*64})
            units[sid]=dict(security_id=sid,selection_decision_id=selection['decision_id'],status='NO_UNPROCESSED_ACTIONS',reference_source_hashes=refs[sid]['source_hashes'],price_basis='CONDITIONAL_PROVIDER_REGULAR_QUOTE_UNITS',source_references=['unit-'+sid],covered_from=now.isoformat(),covered_through=now.isoformat(),reviewed_asof=now.isoformat())
        return state,dict(selection=selection,selection_inputs=args,execution_references=refs,execution_unit_continuity=units,source_hashes=pins,now=now)
    def test_fresh_target_actual_cash_no_sales_credit(self):
        with tempfile.TemporaryDirectory() as root:
            state,args=self.fixture(root);before=deepcopy(state)
            r=build_intraday_retarget_sizing(state,**args)
            self.assertEqual(r['status'],'READY',r)
            self.assertEqual(r['target_quantities'],{'new':202})
            self.assertEqual(r['orders'],[dict(security_id='new',side='BUY',quantity=172,limit_price='100'),dict(security_id='sndk',side='SELL',quantity=2,limit_price='150001/100')])
            self.assertEqual(r['wait_cash'][0]['remaining_deficit'],30)
            self.assertEqual(r['reserved_buy_cash'],'17200');self.assertEqual(r['unreserved_cash'],'0')
            self.assertEqual(Fraction(r['sizing_equity']),Fraction('20200.002'))
            self.assertEqual(r['selection_equity'],'20200');self.assertEqual(state,before)
            self.assertEqual(r['unfilled_sell_proceeds_available'],'0')
    def test_bad_binding_stale_capture_missing_units_fail_closed(self):
        with tempfile.TemporaryDirectory() as root:
            state,args=self.fixture(root)
            for case in ['selection','scope','capture','expiry','missing','units','price']:
                a=deepcopy(args)
                if case=='selection':a['selection']['investable_equity']='90000'
                if case=='scope':a['execution_references']['new']['scope_id']='other:2026-11'
                if case=='capture':a['execution_references']['new']['captured_at']=(a['now']-timedelta(seconds=1)).isoformat()
                if case=='expiry':a['now']+=timedelta(seconds=120)
                if case=='missing':del a['execution_references']['sndk']
                if case=='units':a['execution_unit_continuity']['sndk']['covered_from']=(a['now']+timedelta(seconds=1)).isoformat()
                if case=='price':a['execution_references']['sndk']['sell_limit']='1400'
                r=build_intraday_retarget_sizing(state,**a)
                self.assertEqual(r['status'],'BLOCKED',(case,r));self.assertNotIn('orders',r)
    def test_same_sid_identity_cannot_change(self):
        with tempfile.TemporaryDirectory() as root:
            state,args=self.fixture(root)
            ti=args['selection_inputs']['training_input'];sa=ti['search_arguments']
            for key in ['prices','metadata']:
                sa[key]['sndk']=sa[key].pop('new')
            for scenario in sa['training_scenarios']:scenario['sndk']=scenario.pop('new')
            ti['eligible_security_ids'][0]='sndk';ti['universe_security_ids'][0]='sndk'
            args['selection']=build_intraday_monthly_top1_selection(state,now=args['now'],**args['selection_inputs'])
            del args['execution_references']['new'];del args['execution_unit_continuity']['new']
            args['execution_unit_continuity']['sndk']['selection_decision_id']=args['selection']['decision_id']
            r=build_intraday_retarget_sizing(state,**args)
            self.assertEqual(r['status'],'BLOCKED');self.assertEqual(r['reason'],'HELD_IDENTITY_CHANGED')

if __name__=='__main__':unittest.main()
