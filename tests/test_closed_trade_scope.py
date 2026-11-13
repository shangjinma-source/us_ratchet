import json
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from datetime import datetime,timezone
from hashlib import sha256
from api.strategy_account import StrategyAccountService
from core.strategy_account_ledger import canonical

class ScopeTests(unittest.TestCase):
    def test_archive_preserves_cash_and_future_same_ticker_trades(self):
        with TemporaryDirectory() as d:
            svc=StrategyAccountService(database_path=Path(d)/'a.db',account_id='a',resolver=lambda t:dict(ticker=t,security_id=t,source_references=['id'],source_hashes={'id':'a'*64}),clock=lambda:datetime(2026,11,14,tzinfo=timezone.utc))
            svc.initialize({'event_id':'init'})
            def append(e):return svc.append(dict(expected_revision=svc.read()['account']['revision'],event=e))
            append(dict(kind='CASH_CONFIRM',event_id='cash',amount='1000',cash_basis='TOTAL_UNINVESTED'))
            def fill(identifier,ticker,side,quantity,price):
                return append(dict(kind='DIRECT_FILL',event_id=identifier,ticker=ticker,side=side,quantity=quantity,price=price,fees='0',executed_at='2026-11-13T15:00:00Z'))
            fill('oldbuy','AAA','BUY',2,'10');fill('oldsell','AAA','SELL',2,'12')
            fill('other','BBB','BUY',1,'20')
            before=svc.read()['account'];raw=svc.store.path.read_bytes()
            state=svc.audit_state();events={r['payload']['event_id']:r['payload'] for r in state['events']}
            path=svc.store.path.with_name('a.trade_scope.json')
            doc=dict(schema='CLOSED_TRADE_ARCHIVE_V1',account_id='a',archived_events={k:sha256(canonical(events[k])).hexdigest() for k in ['oldbuy','oldsell']})
            path.write_text(json.dumps(doc))
            after=svc.read()['account']
            self.assertEqual([f['fill_id'] for f in after['fills']],['other'])
            self.assertEqual([r['ticker'] for r in after['trade_results']],['BBB'])
            for key in ['revision','cash_summary','holdings','holding_costs','cash_confirmation_valid']:
                self.assertEqual(before[key],after[key])
            self.assertEqual(raw,svc.store.path.read_bytes())
            fill('newbuy','AAA','BUY',1,'30')
            self.assertEqual([f['fill_id'] for f in svc.read()['account']['fills']],['other','newbuy'])
            doc['archived_events'].pop('oldsell');path.write_text(json.dumps(doc))
            with self.assertRaisesRegex(ValueError,'TRADE_SCOPE_OPEN_POSITION'):svc.read()
            doc['archived_events']={'oldsell':sha256(canonical(events['oldsell'])).hexdigest()};path.write_text(json.dumps(doc))
            with self.assertRaisesRegex(ValueError,'TRADE_SCOPE_PARTIAL_HISTORY'):svc.read()
            doc['archived_events']={'other':'0'*64};path.write_text(json.dumps(doc))
            with self.assertRaisesRegex(ValueError,'TRADE_SCOPE_FILL_CHANGED'):svc.read()

if __name__=='__main__':unittest.main()
