from copy import deepcopy
from datetime import timedelta
from fractions import Fraction
from hashlib import sha256
import json
import unittest
from unittest.mock import patch

import test_current_quantity_v2_current_cash_pullback_sources as initial_fixture
from test_current_quantity_v2_current_cash_continuation import event
from data.current_quantity_v2_current_cash_sources import CurrentQuantityV2CurrentCashSources
from data.current_quantity_v2_current_cash_continuation_sources import CurrentCashContinuationSources
from data.current_quantity_v2_current_cash_plan import build_current_cash_plan, canonical, BASIS
from data.current_quantity_v2_current_cash_ledger_adapter import freeze_current_cash_proposal
from data.current_quantity_v2_paper_ledger import accept_proposal
from data.current_quantity_v2_paper_chain import create_chain, build_continuation
from data.current_quantity_v2_difference_service import decode_execution_package

POLICY=initial_fixture.POLICY


class PullbackContinuationTests(unittest.TestCase):
    setUp = initial_fixture.CurrentCashPullbackSourceTests.setUp
    fetch = initial_fixture.CurrentCashPullbackSourceTests.fetch
    provider_arguments = initial_fixture.CurrentCashPullbackSourceTests.provider_arguments
    row_count = initial_fixture.CurrentCashPullbackSourceTests.row_count

    def prepared(self):
        source=CurrentQuantityV2CurrentCashSources(**self.provider_arguments(),
            pullback_policy=POLICY,pullback_cap_store=self.cap)
        source.capture(self.view['decision_id']);supplied=source.resolve(self.view['decision_id'])
        plan=build_current_cash_plan(**supplied,now=self.current.isoformat())
        proposal=freeze_current_cash_proposal(plan,supplied['execution_package'])
        state=create_chain(accept_proposal(proposal,account_state=supplied['account_state'],now=self.current))
        self.current+=timedelta(seconds=1)
        for i,oid in enumerate(state['ledger']['orders']):
            state=event(state,'CANCEL',oid,self.current.isoformat(),'cancel'+str(i),cancelled_at=self.current.isoformat())
        self.current+=timedelta(seconds=1)
        def fetch(ticker):
            doc=json.loads(self.fetch(ticker));doc['chart']['result'][0]['meta']['regularMarketPrice']=12
            return canonical(doc)
        def review(snapshot):
            evidence='synthetic/continuation-review.json';units={}
            for sid,origin in snapshot['origins'].items():
                sec=snapshot['securities'][sid];current=snapshot['current_receipts'][sid]
                units[sid]=dict(security_id=sid,ticker=sec['ticker'],security_class=sec['security_class'],
                    price_basis='CONDITIONAL_PROVIDER_REGULAR_QUOTE_UNITS',initial_price_basis=BASIS,
                    status='NO_UNPROCESSED_ACTIONS',initial_execution_target_id=snapshot['execution_target_id'],
                    initial_reference_source_hashes=origin['source_hashes'],reference_source_hashes=current['source_hashes'],
                    covered_from=origin['captured_at'],covered_through=current['captured_at'],
                    reviewed_at=self.current.isoformat(),source_references=[evidence])
            files={evidence:canonical({'synthetic':True}),'synthetic/continuation-units.json':canonical(units)}
            return dict(files=files,source_hashes={p:sha256(v).hexdigest() for p,v in files.items()},
                unit_continuity_path='synthetic/continuation-units.json')
        args=dict(root=self.root,unit_review_reader=review,fetch=fetch,clock=lambda:self.current)
        return state,args

    def test_accepted_cancelled_initial_then_higher_reference_does_not_raise_buy(self):
        state,args=self.prepared()
        service=CurrentCashContinuationSources(**args,pullback_policy=POLICY,pullback_cap_store=self.cap)
        capture=service.capture(state);self.assertEqual(self.row_count(),4)
        with patch.object(self.cap,'candidate',side_effect=AssertionError('resolve writes')):
            package=service.resolve(capture['account_id'],capture['decision_id'])
        inputs=decode_execution_package(package,needed={'A','B'},now=self.current)
        result=build_continuation(state,execution_inputs=inputs,now=self.current)
        self.assertTrue(result['orders'])
        self.assertTrue(all(Fraction(row['limit_price'])==9 for row in result['orders']))
        self.assertTrue(all(Fraction(ref['last_price'])==12 for ref in inputs['execution_references'].values()))
        self.assertEqual(self.row_count(),4)
        missing=deepcopy(inputs);missing['execution_references']['A'].pop('pullback')
        with self.assertRaisesRegex(ValueError,'PULLBACK_POLICY_REQUIRED'):
            build_continuation(state,execution_inputs=missing,now=self.current)
        changed=deepcopy(inputs);changed['execution_references']['A']['pullback']['limit_price']='10'
        with self.assertRaisesRegex(ValueError,'INVALID_PULLBACK_LIMIT'):
            build_continuation(state,execution_inputs=changed,now=self.current)
        changed=deepcopy(inputs);changed['execution_references']['A']['pullback']['policy']['rebound_fraction']='1/4'
        with self.assertRaisesRegex(ValueError,'PULLBACK_POLICY_MISMATCH'):
            build_continuation(state,execution_inputs=changed,now=self.current)

    def test_missing_or_changed_server_policy_rejected_before_fetch(self):
        state,args=self.prepared();count=len(self.fetches)
        for config in [{},dict(pullback_policy={**POLICY,'rebound_fraction':'1/4'},pullback_cap_store=self.cap)]:
            with self.assertRaisesRegex(ValueError,'SERVER_CONFIGURATION_REQUIRED'):
                CurrentCashContinuationSources(**args,**config).capture(state)
        self.assertEqual(len(self.fetches),count)
        self.assertEqual(self.row_count(),2)

    def test_monthly_transition_refuses_unported_policy(self):
        from data.current_quantity_v2_monthly_retarget import proposal_for_month
        state,_=self.prepared()
        with self.assertRaisesRegex(ValueError,'PULLBACK_MONTHLY_POLICY_REQUIRED'):
            proposal_for_month(state['ledger'],{},self.current)


if __name__=='__main__':unittest.main()
