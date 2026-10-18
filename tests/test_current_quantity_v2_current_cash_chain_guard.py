"""New-scope ledgers reject missing evidence and old-unit continuation proposals."""
from copy import deepcopy
from datetime import datetime, timedelta
import unittest
import test_current_quantity_v2_current_cash_plan as cash_fixture
import test_current_quantity_v2_current_cash_ledger as adapter_fixture
import test_current_quantity_v2_paper_chain as old_fixture
from data.current_quantity_v2_paper_ledger import accept_proposal, record_event, review_ledger
from data.current_quantity_v2_paper_chain import (
    create_chain, review_chain, build_continuation, accept_continuation)


class CurrentCashChainGuardTests(unittest.TestCase):
    def test_real_accept_close_read_and_explicit_continuation_rejection(self):
        cash_fixture.CurrentCashTests.setUpClass()
        try:
            proposal,args=adapter_fixture.frozen_fixture(cash_fixture.CurrentCashTests.args)
            now=datetime.fromisoformat(args['now'])+timedelta(seconds=1)
            ledger=accept_proposal(proposal,account_state=args['account_state'],now=now)
            for index,oid in enumerate(list(ledger['orders'])):
                now+=timedelta(seconds=1)
                event=dict(event_id='close-'+str(index),type='CANCEL',order_id=oid,
                    expected_revision=ledger['revision'],recorded_at=now.isoformat(),cancelled_at=now.isoformat())
                ledger=record_event(ledger,event,now=now)
            self.assertEqual(ledger['cash'],'110')
            self.assertEqual(ledger['reserved_cash'],'0')
            self.assertEqual(ledger['shares'],{})
            self.assertEqual(review_ledger(ledger),ledger)
            chain=create_chain(ledger);before=deepcopy(chain)
            self.assertEqual(review_chain(chain),chain)
            with self.assertRaisesRegex(ValueError,'EXECUTION_INPUT_FIELDS'):
                build_continuation(chain,execution_inputs={},now=now)
            # A genuinely valid old-scope continuation cannot be applied to this new scope.
            old,args_old=old_fixture.ready()
            old_proposal=build_continuation(old,execution_inputs=old_fixture.inputs(args_old),
                now='2026-10-15T13:03:30-04:00')
            with self.assertRaises(ValueError):
                accept_continuation(chain,old_proposal,acceptance_id='wrong-scope',
                    now='2026-10-15T13:03:31-04:00')
            self.assertEqual(chain,before)
        finally:
            cash_fixture.CurrentCashTests.tearDownClass()


if __name__=='__main__':unittest.main()
