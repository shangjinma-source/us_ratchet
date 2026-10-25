"""Synthetic same-month cash competition through real runtime, HTTP and SQLite."""
from copy import deepcopy
from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from core.strategy_account_ledger import canonical
from data.strategy_account_runtime import build_runtime, ACCOUNT_ID
from data.strategy_account_identity import PinnedStrategyIdentity
from data.current_quantity_v2_paper_action_sources import daily_url
from api.strategy_monthly_target import create_router as target_router
from api.strategy_account import create_router as account_router
from test_current_quantity_v2_monthly_training import fixture as training_fixture
import test_strategy_account_runtime as runtime_fixture


class SameMonthCashCompetitionTests(unittest.TestCase):
    def test_deposit_reselects_two_candidates_and_only_buys_missing_shares(self):
        with TemporaryDirectory() as directory:
            root, config = runtime_fixture.RuntimeTests().fixture(directory)
            _, _, package, days = training_fixture(directory)
            manifest = json.loads(package['files']['manifest.json'])
            template = deepcopy(manifest['candidates'][0])
            rows = []
            for sid, ticker, price in [('A', 'AAA', 60), ('B', 'BBB', 40)]:
                raw = json.loads(package['files']['B.daily'])
                bar = raw['chart']['result'][0]
                bar['meta']['symbol'] = ticker
                # Twelve alternating 21-session gains; no mocked search result.
                prices = [price * (2 if sid == 'A' else .5) if (i // 21) % 2 else price for i in range(253)]
                bar['indicators']['quote'][0].update({k: prices for k in ('open', 'high', 'low', 'close')})
                path = sid + '.daily'
                package['files'][path] = canonical(raw)
                row = deepcopy(template)
                row.update(ticker=ticker, security_id=sid, issuer_id='I'+sid, training_source=path,
                           price_coordinate_factors=[], true_share_events=[], decision_nominal_close=str(price))
                rows.append(row)
            manifest.update(candidates=rows, members=['AAA', 'BBB'])
            manifest['admission'].update(members=['AAA', 'BBB'], training_exclusions={})
            manifest['source_hashes'] = {p: sha256(v).hexdigest() for p,v in package['files'].items() if p != 'manifest.json'}
            package['files']['manifest.json'] = canonical(manifest)
            for path, raw in package['files'].items():
                destination=root/path;destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(raw)
            identity = dict(candidates=rows,source_hashes=manifest['source_hashes'])
            (root/'identity.json').write_bytes(canonical(identity))
            config.update(target_month='2026-11',training_manifest='manifest.json',
                training_sha256=sha256(canonical(manifest)).hexdigest(),training_closed_at='2026-10-30T20:00:00Z',
                identity_sha256=sha256(canonical(identity)).hexdigest())
            now=[datetime.fromisoformat('2026-11-02T15:00:00+00:00')]
            service=build_runtime(root=root,configuration=config,clock=lambda:now[0])
            provider=service.execution_provider.__self__
            def fetch(ticker):
                price={'AAA':60,'BBB':40}[ticker]
                start=int(datetime.fromisoformat('2026-11-02T14:30:00+00:00').timestamp())
                return canonical(dict(chart=dict(error=None,result=[dict(meta=dict(symbol=ticker,currency='USD',
                    instrumentType='EQUITY',exchangeTimezoneName='America/New_York',dataGranularity='1m',regularMarketPrice=price,
                    regularMarketTime=int(now[0].timestamp()),currentTradingPeriod=dict(regular=dict(start=start,end=start+23400))),
                    timestamp=list(range(start,start+1800,60)),indicators=dict(quote=[dict(open=[price]*30,
                    high=[price]*30,low=[price]*30,close=[price]*30,volume=[10]*30)]))])))
            provider.market.fetch=fetch
            provider.actions.fetch=lambda t,start,end:dict(status=200,url=daily_url(t,start,end),body=canonical(dict(chart=dict(error=None,result=[dict(meta=dict(symbol=t,currency='USD',instrumentType='EQUITY'),events={})]))))
            provider.actions.rss_fetch=lambda:dict(status=200,body=b'<rss><channel><title>Nasdaq</title><item><title>Unrelated</title><pubDate>Mon, 02 Nov 2026 14:00:00 GMT</pubDate></item></channel></rss>')
            calls=[];original=provider.selection
            def selection(state):
                calls.append(deepcopy(state));return original(state)
            provider.selection=selection
            service.accounts.initialize(ACCOUNT_ID,operation_id='init')
            app=FastAPI();app.include_router(target_router(service=service))
            app.include_router(account_router(database_path=service.accounts.path,account_id=ACCOUNT_ID,
                resolver=PinnedStrategyIdentity(root,'identity.json',config['identity_sha256']),clock=lambda:now[0]))
            with TestClient(app) as client:
                def event(value):
                    response=client.post('/api/strategy-account/events',json=dict(expected_revision=service.accounts.read()['revision'],event=value))
                    self.assertEqual(response.status_code,200,response.text)
                def generate(identifier,reason):
                    previous=service.current()
                    body=dict(event_id=identifier,reason=reason,expected_revision=service.accounts.read()['revision'],previous_target_id=previous['target_id'] if previous else None)
                    response=client.post('/api/strategy-account/target/generate',json=body)
                    self.assertEqual(response.status_code,200,response.text)
                    return service.current(),body
                def preview():
                    target=service.current()
                    response=client.post('/api/strategy-account/target/preview',json=dict(target_id=target['target_id'],expected_revision=service.accounts.read()['revision']))
                    self.assertEqual(response.status_code,200,response.text)
                    return response.json()['difference']
                event(dict(event_id='initial-cash',kind='CASH_CONFIRM',amount='60',cash_basis='AVAILABLE_AFTER_RESERVATIONS'))
                first,_=generate('first','INITIAL')
                self.assertEqual(first['payload']['target_quantities'],{'B':1})
                self.assertEqual(first['payload']['decision']['payload']['search_result']['selected']['actual_k'],1)
                event(dict(event_id='filled-b',kind='DIRECT_FILL',ticker='BBB',side='BUY',quantity=1,price='40',fees='0',executed_at=now[0].isoformat()))
                event(dict(event_id='remaining-cash',kind='CASH_CONFIRM',amount='20',cash_basis='AVAILABLE_AFTER_RESERVATIONS'))
                self.assertEqual(preview()['new_orders'],[])
                self.assertEqual(len(calls),1)
                now[0]+=timedelta(seconds=1)
                event(dict(event_id='deposited-cash',kind='CASH_CONFIRM',amount='60',cash_basis='AVAILABLE_AFTER_RESERVATIONS'))
                self.assertEqual(client.get('/api/strategy-account/target').json()['configuration_reason'],'EXPLICIT_RECONFIGURE')
                second,body=generate('second','EXPLICIT_RECONFIGURE')
                p=second['payload'];binding=p['decision']['payload']['input_binding']
                self.assertEqual(p['previous_target_id'],first['target_id'])
                self.assertEqual(p['target_quantities'],{'A':1,'B':1})
                self.assertEqual(binding['strategy_equity'],'100')
                self.assertEqual(binding['strategy_shares'],{'B':1})
                selected=p['decision']['payload']['search_result']['selected']
                self.assertEqual(selected['actual_k'],2)
                from fractions import Fraction
                self.assertEqual({k:Fraction(v) for k,v in selected['actual_weights'].items()},{'A':Fraction(3,5),'B':Fraction(2,5)})
                self.assertEqual(binding['documents']['training_manifest'],first['payload']['decision']['payload']['input_binding']['documents']['training_manifest'])
                self.assertEqual(binding['source_hashes']['manifest.json'],config['training_sha256'])
                difference=preview()
                self.assertEqual([(o['security_id'],o['side'],o['quantity']) for o in difference['new_orders']],[('A','BUY',1)])
                self.assertEqual(difference['spendable_cash'],'60')
                self.assertLessEqual(sum(Fraction(o['limit_price'])*o['quantity'] for o in difference['new_orders']),60)
                self.assertEqual(service.accounts.read()['shares'],{'B':1})
                self.assertEqual(len(calls),2)
                repeated=client.post('/api/strategy-account/target/generate',json=body)
                self.assertEqual(repeated.status_code,200,repeated.text)
                self.assertEqual(service.current()['target_id'],second['target_id'])
                self.assertEqual(len(calls),2)


if __name__=='__main__':unittest.main()
