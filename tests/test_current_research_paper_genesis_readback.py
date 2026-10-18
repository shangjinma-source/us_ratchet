"""Synthetic lifecycle persistence; no market fixtures, API, or production DB."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from data.current_research_limit_plan import build_current_research_limit_plan
from data.current_research_paper_store import ResearchPaperStore
from data.current_research_paper_service import CurrentResearchPaperService


def make_plan(*, revision, decision, active, cash='100', shares=None):
    return build_current_research_limit_plan(
        research_snapshot=dict(research_id='a'*24, as_of='2030-01-01',
            stocks=[dict(security_id='a', ticker='AAA')], source_hashes={'synthetic':'b'*64}),
        quotes=[dict(security_id='a', price='10', as_of=decision,
            price_kind='DECLARED_DECIMAL_REFERENCE', price_basis='SYNTHETIC', source_references=['synthetic'])],
        available_cash=cash, shares=shares or {}, account_revision=revision,
        decision_date=decision, active_date=active, calendar=[decision, active],
        strategy_version='synthetic', target_quantities={'a':5})


class GenesisReadbackTests(unittest.TestCase):
    def test_activated_plan_keeps_genesis_account_and_full_history(self):
        with TemporaryDirectory() as directory:
            store = ResearchPaperStore(directory)
            initial = make_plan(revision='initial', decision='2030-01-01', active='2030-01-02')
            account_id = 'paper-' + initial['plan_id'][:24]
            state = store.create(account_id, initial)
            cancel = dict(event_id='cancel', mode='PAPER_MANUAL_FILL', event_type='CANCEL',
                plan_id=initial['plan_id'], order_id=initial['orders'][0]['order_id'], expected_revision=state['revision'])
            state = store.record_order_event(account_id, cancel)
            next_plan = make_plan(revision=state['revision'], decision='2030-01-02', active='2030-01-03',
                cash=state['cash'], shares=state['shares'])
            activate = dict(event_id='activate', mode='PAPER_MANUAL_FILL', event_type='ACTIVATE_PLAN',
                plan_id=next_plan['plan_id'], expected_revision=state['revision'])
            expected = store.activate_plan(account_id, next_plan, activate)
            service = CurrentResearchPaperService(directory=Path(directory))
            actual = service._read_account(account_id)
            self.assertEqual(actual, expected)
            self.assertEqual(actual['plans'], [initial, next_plan])
            self.assertEqual([e['event_id'] for e in actual['events']], ['cancel', 'activate'])
            self.assertEqual(actual['account_id'], account_id)
            self.assertEqual(actual['plan'], next_plan)
            with self.assertRaisesRegex(ValueError, '未找到'):
                service._read_account('paper-' + next_plan['plan_id'][:24])
            # A valid replayable ledger under an arbitrary account is still rejected.
            wrong_id = 'paper-' + 'f'*24
            store.create(wrong_id, initial)
            with self.assertRaisesRegex(ValueError, '不匹配'):
                service._read_account(wrong_id)


if __name__ == '__main__':
    unittest.main()
