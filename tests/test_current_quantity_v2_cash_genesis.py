from copy import deepcopy
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from test_current_quantity_portfolio_research_v2 import fixture
from test_current_quantity_v2_difference_plan import fixture as difference_fixture
from data.current_quantity_portfolio_research_v2 import CurrentQuantityPortfolioResearchV2
from data.current_quantity_v2_difference_plan import build_account_difference_plan
from data.current_quantity_v2_paper_store import QuantityV2PaperStore


class CashGenesisTests(unittest.TestCase):
    def test_real_tiny_decision_genesis_store_partial_retry_and_negative_bindings(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);_,_,descriptor=fixture(root)
            service=CurrentQuantityPortfolioResearchV2(root=root,source_loader=lambda:deepcopy(descriptor))
            view=service.calculate('100');decision=service.decision(view['research_id'])
            original=deepcopy(decision);template=difference_fixture();pins=deepcopy(descriptor['source_hashes'])
            account=dict(account_id='isolated-cash-pool',revision=decision['binding']['state_revision'],cash='100',shares={},
                observed_at='2026-10-15T11:00:00-04:00',open_orders=[],reserved_cash='0',reserved_shares={},pending_rights=[])
            evidence='admission.json';refs={};units={};securities=decision['binding']['search_arguments']['metadata']
            for sid,security in securities.items():
                refs[sid]=deepcopy(template['execution_references']['A'])
                refs[sid].update(security_id=sid,ticker=security['ticker'],last_price='50' if sid=='A' else '30',
                    minute_low='50' if sid=='A' else '30',source_hashes={evidence:pins[evidence]})
                units[sid]=deepcopy(template['unit_continuity']['A'])
                units[sid].update(security_id=sid,ticker=security['ticker'],capital_decision_id=decision['decision_id'],
                    reference_source_hashes={evidence:pins[evidence]},source_references=[evidence],
                    valuation_source_references=decision['binding']['valuation_quotes'][sid]['source_references'])
            mandate=dict(account_id=account['account_id'],capital_decision_id=decision['decision_id'],
                target_month='2026-10',active_date='2026-10-14',source_references=[evidence])
            genesis=dict(purpose='PAPER_INITIALIZATION_NOT_BROKER_BALANCE',account_id=account['account_id'],
                research_id=decision['research_id'],decision_id=decision['decision_id'],capital_origin_revision=account['revision'],
                initial_cash_exact='100',target_month='2026-10',declared_at=account['observed_at'],source_references=[evidence])
            args=dict(capital_decision=decision,account_state=account,securities=securities,execution_references=refs,
                unit_continuity=units,source_hashes=pins,now=template['now'],target_scope='NEW_CASH_STRATEGY_INITIAL_TARGET',
                target_mandate=mandate,genesis_declaration=genesis)
            proposal=build_account_difference_plan(**args);self.assertEqual(proposal['status'],'READY',proposal)
            self.assertTrue(all(o['side']=='BUY' for o in proposal['orders']))
            self.assertEqual(proposal['reserved_buy_cash'],'80');self.assertEqual(decision,original)
            store=QuantityV2PaperStore(root/'paper.sqlite3');calls=[]
            def factory(now):calls.append(now);return dict(proposal=deepcopy(proposal),account_state=deepcopy(account))
            request=dict(account_id=account['account_id'],proposal_id=proposal['proposal_id'],operation_id='genesis',factory=factory,
                clock=lambda:datetime.fromisoformat(args['now']))
            state=store.accept(**request);order=next(o for o in state['ledger']['orders'].values() if o['security_id']=='A')
            event=dict(event_id='fill-A',type='FILL',order_id=order['order_id'],expected_revision=state['ledger']['revision'],
                quantity=1,price='49',fees='1',executed_at='2026-10-15T13:00:00-04:00')
            state=store.record_event(account_id=account['account_id'],event=event,clock=lambda:datetime.fromisoformat('2026-10-15T13:01:00-04:00'))
            self.assertEqual(state['ledger']['cash'],'50');self.assertEqual(state['ledger']['shares'],{'A':1})
            self.assertEqual(store.accept(**dict(request,factory=lambda _:self.fail('second funding'))),state)
            self.assertEqual(len(calls),1)
            with self.assertRaises(ValueError):store.accept(**dict(request,operation_id='second-initial'))
            for mutate in (lambda a:a['account_state'].update(cash='101'),lambda a:a['account_state'].update(shares={'OLD':1}),
                    lambda a:a.update(now='2026-10-15T12:03:00-04:00'),lambda a:a['unit_continuity'].pop('A'),
                    lambda a:a['genesis_declaration'].update(account_id='other'),lambda a:a['genesis_declaration'].update(initial_cash_exact='99'),
                    lambda a:a['genesis_declaration'].update(purpose='REAL_BROKER_BALANCE'),lambda a:a.update(genesis_declaration=None)):
                bad=deepcopy(args);mutate(bad)
                self.assertEqual(build_account_difference_plan(**bad)['status'],'BLOCKED')
            self.assertEqual(service.decision(view['research_id']),original)


if __name__=='__main__':unittest.main()
