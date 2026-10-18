import tempfile
import unittest
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
from pathlib import Path

import test_current_research_intraday_continuation as fixtures
from test_current_research_intraday_execution import NOW, payload
from data.current_research_intraday_mark_sources import review_journal_monthly_capital


class JournalCapitalTests(unittest.TestCase):
    def fixture(self, root, days=0):
        service, state, arguments = fixtures.ContinuationTests().setup(root)
        now = NOW + timedelta(days=days, seconds=10)
        data = payload()
        row = data['chart']['result'][0]
        row['meta']['regularMarketTime'] = int(now.timestamp())
        for key in ('start', 'end'):
            row['meta']['currentTradingPeriod']['regular'][key] += days * 86400
        row['timestamp'] = [stamp + days * 86400 for stamp in row['timestamp']]
        service.fetch = lambda _: data
        service.clock = lambda: now
        receipt = service.preview('a' * 24)['observation_record']
        evidence = Path(root) / 'calendar'
        evidence.write_text('Synthetic reviewed source for isolated test only.', encoding='utf-8')
        arguments.update(root=root, now=now, session=now.date().isoformat(),
            event_path=receipt['event_path'], expected_event_hashes={receipt['event_path']: receipt['event_sha256']},
            source_hashes={'calendar': sha256(evidence.read_bytes()).hexdigest()})
        arguments.pop('research_snapshot')
        arguments['market_session'].update(date=now.date().isoformat(),
            open_at=now.replace(hour=9, minute=30, second=0).isoformat(),
            close_at=now.replace(hour=16, minute=0, second=0).isoformat())
        arguments['unit_continuity'].update(to_session=arguments['session'],
            current_event_sha256=receipt['event_sha256'], covered_through=now.isoformat(), reviewed_asof=now.isoformat())
        if days:
            arguments['unit_continuity']['action_review'] = dict(covered_from=NOW.date().isoformat(),
                covered_through=arguments['session'], status='NO_UNPROCESSED_ACTIONS',
                source_references=['calendar'], reviewed_asof=now.isoformat())
        return state, arguments

    def test_actual_cash_and_last_mark_not_buy_cap(self):
        with tempfile.TemporaryDirectory() as root:
            state, arguments = self.fixture(root)
            before = deepcopy(state)
            result = review_journal_monthly_capital(state, **arguments)
            self.assertEqual(result['status'], 'READY', result)
            self.assertEqual(result['capital']['cash'], '17200')
            self.assertEqual(result['capital']['investable_equity'], '10012349/500')
            self.assertEqual(result['capital']['buy_cash_limit'], '17200')
            self.assertEqual(result['capital']['unfilled_sell_proceeds_available'], '0')
            self.assertTrue(result['source_bytes_verified'])
            self.assertEqual(state, before)

    def test_cross_month_values_old_holding_without_selecting(self):
        with tempfile.TemporaryDirectory() as root:
            state, arguments = self.fixture(root, days=18)
            result = review_journal_monthly_capital(state, **arguments)
            self.assertEqual(result['status'], 'READY', result)
            self.assertFalse(result['selection_performed'])
            self.assertFalse(result['orders_generated'])
            arguments['unit_continuity'].pop('action_review')
            with self.assertRaisesRegex(ValueError, 'CROSS_SESSION'):
                review_journal_monthly_capital(state, **arguments)

    def test_tampered_source_stale_revision_and_expired_quote_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            state, arguments = self.fixture(root)
            for patch in ({'expected_revision': 'stale'}, {'now': arguments['now'] + timedelta(seconds=121)}):
                altered = dict(arguments, **patch)
                with self.assertRaises(ValueError):
                    review_journal_monthly_capital(state, **altered)
            (Path(root) / 'calendar').write_text('changed', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'SOURCE_HASH_MISMATCH'):
                review_journal_monthly_capital(state, **arguments)


if __name__ == '__main__':
    unittest.main()
