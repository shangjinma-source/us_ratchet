from copy import deepcopy
from datetime import datetime,timedelta
import json
import unittest
from test_current_quantity_v2_current_cash_ledger import frozen_fixture
import test_current_quantity_v2_current_cash_plan as base
from data.current_quantity_v2_paper_ledger import accept_proposal
from data.current_quantity_v2_paper_chain import create_chain,record_chain_event,build_continuation,accept_continuation,review_chain
from data.current_quantity_v2_current_cash_plan import BASIS


def event(state,kind,oid,at,identifier,**fields):
    e=dict(event_id=identifier,type=kind,order_id=oid,expected_revision=state['ledger']['revision'],recorded_at=at,**fields)
    return record_chain_event(state,e,now=at)


def fixture(args):
    p,args=frozen_fixture(args);t=datetime.fromisoformat(args['now'])
    state=create_chain(accept_proposal(p,account_state=args['account_state'],now=t))
    oid=next(k for k,o in state['ledger']['orders'].items() if o['security_id']=='A')
    state=event(state,'FILL',oid,(t+timedelta(seconds=1)).isoformat(),'partial',quantity=2,price='9',fees='1/5',executed_at=(t+timedelta(seconds=1)).isoformat())
    for i,oid in enumerate(state['ledger']['orders']):
        state=event(state,'CANCEL',oid,(t+timedelta(seconds=2)).isoformat(),'cancel'+str(i),cancelled_at=(t+timedelta(seconds=2)).isoformat())
    now=t+timedelta(seconds=10);inputs=dict(securities=deepcopy(p['securities']),execution_references={},unit_continuity={},source_hashes=deepcopy(p['causal_inputs']['frozen_execution_package']['source_hashes']))
    for row in p['rows']:
        sid=row['security_id'];ref=deepcopy(row['reference']);pins={'continuation/'+sid:'a'*64};inputs['source_hashes'].update(pins)
        ref.update(security_id=sid,ticker=p['securities'][sid]['ticker'],currency='USD',price_basis='CONDITIONAL_PROVIDER_REGULAR_QUOTE_UNITS',
            captured_at=now.isoformat(),checked_at=now.isoformat(),last_at=now.isoformat(),valid_until=ref.pop('refresh_by'),source_hashes=pins,last_price='5',minute_low='4')
        inputs['execution_references'][sid]=ref
        inputs['unit_continuity'][sid]=dict(security_id=sid,ticker=ref['ticker'],security_class=p['securities'][sid]['security_class'],
            price_basis=ref['price_basis'],initial_price_basis=BASIS,status='NO_UNPROCESSED_ACTIONS',initial_execution_target_id=p['execution_target_id'],
            initial_reference_source_hashes=row['source_hashes'],reference_source_hashes=pins,covered_from=row['captured_at'],
            covered_through=now.isoformat(),reviewed_at=now.isoformat(),source_references=list(pins))
    return state,inputs,now.isoformat()


class CurrentContinuationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):base.CurrentCashTests.setUpClass();cls.args=base.CurrentCashTests.args
    @classmethod
    def tearDownClass(cls):base.CurrentCashTests.tearDownClass()

    def test_repeat_accept_fill_preserves_new_targets_and_fees(self):
        state,inputs,now=fixture(self.args);capital=deepcopy(state['genesis']['acceptance']['proposal']['causal_inputs']['capital_decision'])
        p=build_continuation(state,execution_inputs=inputs,now=now)
        self.assertEqual(p['binding']['target_quantities'],{'A':6,'B':4});self.assertEqual({r['security_id']:r['quantity'] for r in p['orders']},{'A':4,'B':4})
        accepted=accept_continuation(state,p,acceptance_id='continue1',now=now)
        self.assertEqual(accepted['ledger']['cash'],'459/5');self.assertEqual(accepted['ledger']['recorded_fees'],'1/5')
        for i,oid in enumerate(accepted['ledger']['orders']):
            accepted=event(accepted,'CANCEL',oid,now,'again'+str(i),cancelled_at=now)
        q=build_continuation(accepted,execution_inputs=inputs,now=now)
        again=accept_continuation(accepted,q,acceptance_id='continue2',now=now)
        self.assertEqual(accept_continuation(again,p,acceptance_id='continue1',now='2030-01-01T00:00:00+00:00'),again)
        for i,(oid,o) in enumerate(again['ledger']['orders'].items()):
            again=event(again,'FILL',oid,now,'done'+str(i),quantity=o['quantity'],price='4',fees='0',executed_at=now)
        self.assertEqual(again['ledger']['shares'],{'A':6,'B':4});self.assertEqual(again['ledger']['cash'],'299/5')
        self.assertEqual(build_continuation(again,execution_inputs=inputs,now=now)['action'],'NO_ACTION')
        self.assertEqual(review_chain(json.loads(json.dumps(again))),again)
        self.assertEqual(again['genesis']['acceptance']['proposal']['causal_inputs']['capital_decision'],capital)

    def test_bad_evidence_time_and_scope_reject(self):
        state,inputs,now=fixture(self.args)
        for change in ('missing','origin','coverage','pin','class','expired','month','open','known_actions','pending_actions'):
            i=deepcopy(inputs);s=deepcopy(state);at=now
            if change in ('known_actions','pending_actions'):i['unit_continuity']['A'][change]=[{'type':'split'}]
            elif change=='missing':i['unit_continuity'].pop('A')
            elif change=='origin':i['unit_continuity']['A']['initial_execution_target_id']='wrong'
            elif change=='coverage':i['unit_continuity']['A']['covered_from']=now
            elif change=='pin':i['source_hashes'][next(iter(s['genesis']['acceptance']['proposal']['causal_inputs']['frozen_execution_package']['source_hashes']))]='0'*64
            elif change=='class':i['securities']['A']['security_class']='Other'
            elif change=='expired':at=i['execution_references']['A']['valid_until']
            elif change=='month':at='2026-11-02T17:00:00+00:00'
            else:s=create_chain(s['genesis'])
            with self.subTest(change=change),self.assertRaises(ValueError):build_continuation(s,execution_inputs=i,now=at)
        p=build_continuation(state,execution_inputs=inputs,now=now);a=accept_continuation(state,p,acceptance_id='one',now=now)
        bad=deepcopy(p);bad['orders'][0]['quantity']+=1
        with self.assertRaises(ValueError):accept_continuation(a,bad,acceptance_id='one',now=now)
        with self.assertRaises(ValueError):accept_continuation(a,p,acceptance_id='two',now=now)
