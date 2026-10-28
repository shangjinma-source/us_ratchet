import importlib.util, os, unittest, json
from pathlib import Path
from copy import deepcopy
from core.strategy_account_ledger import create_account, apply_event
from data.strategy_account_preview import preview_scoped_account

candidate=os.environ.get('NEWS_RISK_PLAN_CANDIDATE')
if candidate:
    spec=importlib.util.spec_from_file_location('risk_plan_candidate',candidate)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
else:
    from data import news_risk_plan_v1 as module

NOW='2026-10-28T14:00:00+00:00'
END='2026-10-28T14:01:00+00:00'
def fixture(held=None, targets=None, cash='1000'):
    held=held or {'A':4,'B':2};targets=targets or {'A':8,'B':6}
    state=create_account('synthetic-test')
    def event(**payload):
        nonlocal state
        state,_=apply_event(state,payload,expected_revision=state['revision'])
    event(event_id='initial',kind='CASH_CONFIRM',amount='100000',cash_basis='TOTAL_UNINVESTED')
    for sid,quantity in held.items():
        if quantity:event(event_id='fill'+sid,kind='DIRECT_FILL',security_id=sid,side='BUY',quantity=quantity,price='100',fees='0',executed_at=NOW)
    event(event_id='latestcash',kind='CASH_CONFIRM',amount=cash,cash_basis='TOTAL_UNINVESTED')
    marks={sid:dict(security_id=sid,currency='USD',price_basis='TEST',price='100',observed_at=NOW,source_hashes={'synthetic':'a'*64}) for sid in targets}
    limits={sid:dict(security_id=sid,price_basis='TEST',buy='100',sell='100',observed_at=NOW,buy_evaluated=targets[sid]>held.get(sid,0),evaluated_account_revision=state['revision'],evaluated_net_gap=targets[sid]-held.get(sid,0),reference_valid_until=END,sell_reason='Authenticated near-last sell',source_hashes={'synthetic':'a'*64}) for sid in targets}
    difference=preview_scoped_account(state=state,legacy_shares={},marks=marks,limits=limits,target_quantities=targets,now=NOW,maximum_mark_age_seconds=120,fee_bps='0')
    original=dict(status='READY',account_revision=state['revision'],target_id='target',proposal_id='original',risk_valid_from=NOW,risk_valid_until=END,effective_target_quantities=targets,reference_quotes=limits,difference=difference,new_orders=difference['new_orders'],policy_id='V27_ORIGINAL')
    proposal=dict(schema='NEWS_INVESTMENT_REVIEW_PROPOSAL_V1',status='REVIEW_PROPOSAL_ONLY',review_id='review',original_binding={key:original[key] for key in ('account_revision','target_id','proposal_id')},review_created_at=NOW,review_valid_until=END,orders_created=False,executable=False,rows=[dict(security_id=sid,action='KEEP',held_quantity=held.get(sid,0),original_target_quantity=q,proposed_target_quantity=q,reviewed=True) for sid,q in targets.items()])
    return state,original,proposal

class RiskPlanTests(unittest.TestCase):
    def build(self,state,original,proposal):
        return module.build_risk_plan(account=state,original_preview=original,proposal=proposal,now=NOW)
    def test_real_ledger_lower_target_and_no_mutation(self):
        state,original,proposal=fixture();before=deepcopy((state,original,proposal))
        proposal['rows'][0].update(action='REDUCE_HOLDING',proposed_target_quantity=2)
        before=deepcopy((state,original,proposal));result=self.build(state,original,proposal)
        self.assertEqual(result['status'],'READY',result)
        self.assertEqual([(o['security_id'],o['side'],o['quantity']) for o in result['candidate_orders']],[('A','SELL',2),('B','BUY',4)])
        self.assertEqual(result['cash']['new_buy_cash_required'],'400')
        self.assertFalse(result['cash']['sell_proceeds_assumed']);self.assertFalse(result['executable'])
        self.assertEqual((state,original,proposal),before)
    def test_freed_budget_cannot_expand_other_buy(self):
        state,original,proposal=fixture(cash='200')
        proposal['rows'][0].update(action='PAUSE_BUY',proposed_target_quantity=4)
        result=self.build(state,original,proposal);self.assertEqual(result['status'],'READY',result)
        self.assertEqual([(o['security_id'],o['quantity']) for o in result['candidate_orders']],[('B',1)])
        self.assertEqual(result['rows'][1]['desired_target_quantity'],6)
        self.assertEqual(result['rows'][1]['planned_target_quantity'],3)
        self.assertEqual(result['constraints'][0]['reason'],'BUY_CAPPED_TO_ORIGINAL_PREVIEW')
        self.assertEqual(result['waiting_cash'],[])
    def test_original_sell_and_risk_exit_cannot_be_raised(self):
        state,original,proposal=fixture(targets={'A':0,'B':6},cash='0')
        result=self.build(state,original,proposal);self.assertEqual(result['status'],'READY',result)
        self.assertEqual([(o['side'],o['quantity']) for o in result['candidate_orders']],[('SELL',4)])
        self.assertEqual(result['cash']['new_buy_cash_required'],'0')
        proposal['rows'][0]['proposed_target_quantity']=1
        self.assertEqual(self.build(state,original,proposal)['reason'],'AI_CANNOT_RAISE_ORIGINAL_RISK_TARGET')
    def test_hold_and_expiry_do_not_expose_prices(self):
        state,original,proposal=fixture();original['status']='HOLD'
        result=self.build(state,original,proposal)
        self.assertEqual(result['reason'],'WAIT_NEW_QUOTES_REQUIRED');self.assertEqual(result['candidate_orders'],[])
        original['status']='READY';proposal['review_valid_until']=NOW
        self.assertEqual(self.build(state,original,proposal)['reason'],'REVIEW_EXPIRED')
    def test_quote_side_and_source_binding_rejected(self):
        for field,value in [('sell_reason',''),('source_hashes',{}),('reference_valid_until',NOW)]:
            state,original,proposal=fixture();proposal['rows'][0].update(action='EXIT',proposed_target_quantity=0)
            original['reference_quotes']['A'][field]=value
            # Rebuild a consistent original accounting proof, but authentication is invalid.
            proof=original['difference']['binding'];proof['limits']=deepcopy(original['reference_quotes'])
            original['difference']=preview_scoped_account(state=state,legacy_shares={},marks=proof['marks'],limits=proof['limits'],target_quantities=proof['target_quantities'],now=NOW,maximum_mark_age_seconds=120,fee_bps='0')
            original['new_orders']=original['difference']['new_orders']
            result=self.build(state,original,proposal)
            self.assertEqual(result['status'],'WAIT',result);self.assertEqual(result['candidate_orders'],[])
    def test_account_revision_and_ledger_tamper_rejected(self):
        state,original,proposal=fixture();state['shares']['A']+=1
        self.assertEqual(self.build(state,original,proposal)['reason'],'ACCOUNT_REPLAY_MISMATCH')
        state,original,proposal=fixture();state['revision']='different-revision'
        self.assertEqual(self.build(state,original,proposal)['reason'],'RISK_PLAN_BINDING_CHANGED')
    def test_mixed_unreviewed_or_wrong_action_cannot_sell(self):
        for action,reviewed in [('ABSTAIN',False),('KEEP',True),('PAUSE_BUY',True),('REDUCE_BUY',True)]:
            state,original,proposal=fixture()
            proposal['rows'][0].update(action=action,reviewed=reviewed,proposed_target_quantity=2)
            result=self.build(state,original,proposal)
            self.assertEqual(result['status'],'WAIT',result)
            self.assertEqual(result['candidate_orders'],[])
        state,original,proposal=fixture()
        proposal['rows'][0].update(action='EXIT',proposed_target_quantity=1)
        self.assertEqual(self.build(state,original,proposal)['reason'],'EXIT_TARGET_MUST_BE_ZERO')

    def test_abstain_and_pending_order(self):
        state,original,proposal=fixture()
        for row in proposal['rows']:row.update(action='ABSTAIN',reviewed=False)
        self.assertEqual(self.build(state,original,proposal)['status'],'ABSTAIN')
        state['orders']['pending']={'status':'OPEN'}
        self.assertEqual(self.build(state,original,proposal)['reason'],'WAIT_PENDING_RECONCILIATION')

if __name__=='__main__':unittest.main()
