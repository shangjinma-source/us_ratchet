"""Synthetic full daily->composition->HTTP rollover, without local research data."""
from copy import deepcopy
from datetime import datetime,date,timedelta,timezone
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zoneinfo import ZoneInfo
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.strategy_account import create_router
from data.roa_account_composition import attach_roa
from data.roa_quote_provider import RoaQuoteProvider
from data.roa_session_reader import CALENDAR
from data.roa_daily_signal import SEED
from scripts.research.prepare_roa_monthly_package import prepare


class PendingSellAdviceTests(unittest.TestCase):
    def test_sell_partial_cancel_no_duplicate_or_anticipated_cash(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);now=datetime(2026,12,1,14,32,tzinfo=timezone.utc);ny=ZoneInfo('America/New_York')
            def save(path,obj):
                path=root/path;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(obj));return sha256(path.read_bytes()).hexdigest()
            dates=[];day=date(2026,1,1)
            while day<=date(2026,12,2):
                if day.weekday()<5 and day.isoformat()!='2026-11-26':dates.append(day.isoformat())
                day+=timedelta(days=1)
            def at(day,hour,minute=0):return datetime.fromisoformat(day).replace(hour=hour,minute=minute,tzinfo=ny).astimezone(timezone.utc)
            calendar=dict(schema='FIXED_EXCHANGE_SESSIONS_V1',exchange='NASDAQ',actual_unscheduled_closure_coverage_complete=False,source_references=[],
                sessions=[dict(date=d,open=at(d,9,30).isoformat(),close=at(d,16).isoformat()) for d in dates])
            calendar_hash=save(CALENDAR,calendar)
            def chart(days):
                values=[100+dates.index(d) for d in days]
                return {'chart':{'error':None,'result':[{'meta':{'symbol':'QQQ','currency':'USD','exchangeTimezoneName':'America/New_York','dataGranularity':'1d'},
                    'timestamp':[int(at(d,9,30).timestamp()) for d in days],
                    'indicators':{'quote':[dict(open=values,high=values,low=values,close=values,volume=[100]*len(days))]}}]}}
            base_root='data/strategy_inputs/base/inputs';seed_hash=save(base_root+'/'+SEED,chart([d for d in dates if d<='2026-11-05']))
            contract='contracts/frozen.json';contract_hash=save(base_root+'/'+contract,{'rule':'frozen'})
            base=dict(signal_id='approved-base',decision_date='2026-10-30',signal_date='2026-11-05',risk_on=True,weights={'OLD':'1/10'},
                execution_not_before_session='2026-11-06',securities=[dict(security_id='OLD',ticker='OLD',issuer_id='issuer:old')],source_hashes={},financial_cutoff='2026-09-30')
            def approved_base_reader(*,as_of_date,root,expected_contract_hashes):
                self.assertEqual(Path(root).resolve(),(Path(folder)/base_root).resolve())
                self.assertEqual(expected_contract_hashes,{contract:contract_hash})
                self.assertEqual(sha256((Path(root)/contract).read_bytes()).hexdigest(),contract_hash)
                return deepcopy(base)
            cache='data/cache/facts.json';facts_hash=save(cache,{'net_income':1})
            month=dict(schema='ROA_MONTH_SELECTION_V1',effective_month='2026-12',first_execution_session='2026-12-01',decision_date='2026-11-30',
                financial_cutoff='2026-09-30',weights={'NEW':'1/10'},securities=[dict(security_id='NEW',ticker='NEW',issuer_id='issuer:new')],source_hashes={cache:facts_hash},selection={'selected':['NEW']})
            month['selection_id']=sha256(json.dumps(month,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            manifest_path='data/cache/month_manifest.json';manifest_hash=save(manifest_path,{'decision_date':'2026-11-30'})
            request=dict(manifest=dict(path=manifest_path,sha256=manifest_hash),session_calendar=dict(path=CALENDAR,sha256=calendar_hash),
                training_calendar=dict(path=CALENDAR,sha256=calendar_hash),expected_month='2026-12',output_directory='data/strategy_inputs/december_package')
            # The fixed financial selector is a fixture; real immutable packaging and loading run below.
            with patch('scripts.research.prepare_roa_monthly_package.generate_month_selection',return_value=month):
                package=prepare(root=root,request=request,now=now,create=True)
            registry=json.loads((root/package['registry_proposal']).read_text())
            month_path=registry['2026-12']['path'];month_hash=registry['2026-12']['sha256']
            runtime=json.loads((root/month_path).read_text())
            frozen_facts=next(p for p in runtime['source_hashes'] if p.replace('\\','/').endswith('/'+cache))
            update_days=[d for d in dates if '2026-11-05'<d<='2026-11-30']
            evidence='data/strategy_account/test/qqq.json';evidence_hash=save(evidence,chart(update_days))
            state_path='data/strategy_account/test/daily.json'
            save(state_path,dict(base_signal_id='approved-base',updates=[dict(session=d,close=str(100+dates.index(d)),
                raw_path=str(root/evidence),raw_sha256=evidence_hash,captured_at='2026-11-30T21:05:00+00:00') for d in update_days]))
            def fetch(ticker):
                opening=at('2026-12-01',9,30);closing=at('2026-12-01',16)
                return json.dumps({'chart':{'error':None,'result':[{'meta':{'symbol':ticker,'currency':'USD','exchangeTimezoneName':'America/New_York',
                    'dataGranularity':'1m','regularMarketPrice':10,'regularMarketTime':int(now.timestamp()),
                    'currentTradingPeriod':{'regular':{'start':int(opening.timestamp()),'end':int(closing.timestamp())}}},
                    'timestamp':[int(opening.timestamp()),int(opening.timestamp())+60],
                    'indicators':{'quote':[dict(open=[10,10],high=[10,10],low=[10,10],close=[10,10],volume=[100,100])]}}]}}).encode()
            config=dict(account_id='test',strategy_epoch='epoch',contract_sha256='a'*64,contract_hashes={contract:contract_hash},base_input_root=base_root,
                daily_signal_path=state_path,lifecycle_path='data/strategy_account/test/life.json',close_evidence_path='data/strategy_account/test/closes',
                close_recovery_path='data/strategy_account/test/recovery',monthly_selections={'2026-12':dict(path=month_path,sha256=month_hash)},
                execution_admission=dict(enabled=True,strategy_epoch='epoch',contract_sha256='a'*64,open_window_seconds=300,close_window_seconds=300,limit_policy='CENT_LAST_PRICE_LIMIT'))
            resolver=lambda ticker:dict(ticker=ticker,security_id=ticker,source_references=['synthetic'],source_hashes={'synthetic':'a'*64})
            router=create_router(database_path=root/'account.sqlite3',account_id='test',resolver=resolver,clock=lambda:now)
            close_path='data/strategy_account/test/close_source.json';close_hash=save(close_path,{'close':'10'})
            def completed_closes(**kwargs):
                return dict(prices={s:'10' for s in kwargs['identity_map']},evidence={s:dict(raw_path=str(root/close_path),raw_sha256=close_hash) for s in kwargs['identity_map']})
            with patch('data.roa_session_reader.SHA',calendar_hash),patch('data.roa_daily_signal.SHA',calendar_hash),patch('data.roa_daily_signal.SEED_SHA',seed_hash), \
                 patch('data.roa_daily_signal.load_current_signal',side_effect=approved_base_reader), \
                 patch('data.roa_account_composition.load_completed_close_prices',side_effect=completed_closes), \
                 patch('data.roa_account_composition.RoaQuoteProvider',side_effect=lambda **kw:RoaQuoteProvider(**kw,fetch=fetch)):
                prepared=attach_roa(prepared={'router':router},root=root,configuration=config,validate_sources=lambda:None,clock=lambda:now)
                service=prepared['roa_service'];account=service.account_service
                account.initialize({'event_id':'init'})
                def append(event):account.append(dict(expected_revision=account.store.read()['revision'],event=event))
                append(dict(event_id='cash1',kind='CASH_CONFIRM',amount='1000',cash_basis='TOTAL_UNINVESTED'))
                append(dict(event_id='oldfill',kind='DIRECT_FILL',ticker='OLD',side='BUY',quantity=14,price='10',fees='0',executed_at='2026-11-06T14:31:00+00:00'))
                append(dict(event_id='cash2',kind='CASH_CONFIRM',amount='860',cash_basis='TOTAL_UNINVESTED'))
                before=account.store.read()
                # Simulated prior lifecycle adoption, without changing actual holdings.
                state=service.lifecycle.plan(signal=base,session='2026-11-06',open_at='2026-11-06T14:30:00Z',open_until='2026-11-06T14:35:00Z',close_at='2026-11-06T20:55:00Z',close_until='2026-11-06T21:00:00Z')
                service.lifecycle.materialize_open(event_id=state['events'][0]['event_id'],account=before,opening_prices={'OLD':'10'},now='2026-11-06T14:31:00Z')
                for closed_day in update_days:
                    prepared['roa_observe_completed_session'](closed_day)
                save(cache,{'net_income':999})
                app=FastAPI();app.include_router(prepared['router'])
                with TestClient(app) as client:
                    result=client.get('/api/strategy-roa/snapshot').json()
                    self.assertEqual(result['status'],'READY',result)
                    self.assertEqual(result['target_quantities'],{'NEW':9})
                    actions={r['ticker']:(r['side'],r['quantity']) for r in result['rows']}
                    self.assertEqual(actions,{'OLD':('SELL',14),'NEW':('BUY',9)})
                    self.assertEqual(service.lifecycle.read()['events'][-1]['reason'],'MONTHLY_TARGET')
                    self.assertEqual(account.store.read(),before)
                    def post(event):
                        response=client.post('/api/strategy-account/events',json=dict(expected_revision=account.store.read()['revision'],event=event))
                        self.assertEqual(response.status_code,200,response.text)
                    post(dict(kind='ORDER_OPEN',event_id='sell-order',order_id='broker-old',ticker='OLD',side='SELL',quantity=14,limit_price='10',fee_per_share='0'))
                    post(dict(kind='CASH_CONFIRM',event_id='sell-reserved',amount='0',cash_basis='AVAILABLE_AFTER_RESERVATIONS'))
                    proposal=client.get('/api/strategy-roa/snapshot').json()
                    self.assertFalse(any(r.get('side') in ('BUY','SELL') and r.get('quantity',0)>0 for r in proposal.get('rows',[])),proposal)
                    self.assertEqual(account.store.read()['available_cash'],'0')
                    post(dict(kind='FILL',event_id='sell-partial',order_id='broker-old',quantity=4,price='10',fees='0',executed_at=now.isoformat()))
                    self.assertEqual(client.get('/api/strategy-roa/snapshot').json()['status'],'WAIT_CASH_CONFIRMATION')
                    # User confirms zero available buying power: no assumed sale proceeds.
                    post(dict(kind='CASH_CONFIRM',event_id='sell-partial-cash',amount='0',cash_basis='AVAILABLE_AFTER_RESERVATIONS'))
                    proposal=client.get('/api/strategy-roa/snapshot').json()
                    self.assertFalse(any(r.get('side') in ('BUY','SELL') and r.get('quantity',0)>0 for r in proposal.get('rows',[])),proposal)
                    self.assertEqual(account.store.read()['orders']['broker-old']['remaining_quantity'],10)
                    post(dict(kind='CANCEL',event_id='sell-cancel',order_id='broker-old'))
                    proposal=client.get('/api/strategy-roa/snapshot').json()
                    self.assertEqual(proposal['status'],'READY',proposal)
                    sells=[r for r in proposal['rows'] if r.get('side')=='SELL'];self.assertEqual([(r['ticker'],r['quantity']) for r in sells],[('OLD',10)])
                    self.assertFalse(any(r.get('side')=='BUY' and r.get('quantity',0)>0 for r in proposal['rows']),proposal)
                    self.assertEqual(account.store.read()['available_cash'],'0')
if __name__=='__main__':unittest.main()
