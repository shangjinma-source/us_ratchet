"""Independent full-cash target execution regression; synthetic transport only."""
from copy import deepcopy
from functools import partial
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from core.strategy_account_ledger import apply_event,canonical
from data.strategy_account_target_inputs import build_target_inputs
from data.strategy_account_execution_limits import build_execution_limits
from data.current_quantity_v2_pullback_runtime import LazyPullbackCapStore
import test_strategy_account_evidence_provider as provider_tests

class AllCashExecutionAudit(unittest.TestCase):
    def test_cash_target_sells_held_sid_with_real_provider_and_no_optimizer(self):
        with TemporaryDirectory() as directory:
            provider,state,now,_=provider_tests.ProviderTests().fixture(directory)
            for order in list(state['orders'].values()):
                if order['status']=='OPEN':
                    state,_=apply_event(state,dict(event_id='cancel-'+order['order_id'],kind='CANCEL',order_id=order['order_id']),expected_revision=state['revision'])
            state,_=apply_event(state,dict(event_id='independent-cash-confirm',kind='CASH_CONFIRM',amount='500',cash_basis='TOTAL_UNINVESTED'),expected_revision=state['revision'])
            evidence=provider(state)
            inputs=build_target_inputs(state=state,now=now[0].isoformat(),maximum_mark_age_seconds=120,**{k:v for k,v in evidence.items() if k!='limits'})
            payload=dict(input_binding=inputs['binding'],input_id=inputs['input_id'],target_quantities={})
            target=dict(payload=dict(decision=dict(status='TARGET_READY',payload=payload,decision_id=sha256(canonical(payload)).hexdigest())))
            cap=LazyPullbackCapStore(Path(directory)/'caps.db',clock=lambda:now[0].isoformat(),max_history_rows=32,max_history_bytes=1024*1024)
            provider.limits=partial(build_execution_limits,cap_store=cap)
            with patch('data.strategy_account_evidence_provider.compile_saved_training',side_effect=AssertionError('no training recompile')):
                result=provider.execution(state,target)
            self.assertEqual(set(result['marks']),{'A'})
            self.assertFalse(result['limits']['A']['buy_evaluated'])
            self.assertEqual(result['limits']['A']['sell'],'10')
            self.assertFalse(cap.path.exists())

if __name__=='__main__':unittest.main()
