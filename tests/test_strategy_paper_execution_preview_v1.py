from copy import deepcopy
from datetime import datetime,timedelta
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from core.strategy_account_ledger import canonical,apply_event
from data.strategy_paper_execution_preview_v1 import preview_paper_execution,CODE_PATHS,SCOPE
from data.strategy_paper_execution_caps_v1 import PaperExecutionCaps
from data.strategy_execution_limits_common_v1 import build_real_execution_limits
from data.strategy_halt_aware_execution_limits_v1 import build_execution_limits
from data.strategy_account_preview import preview_scoped_account
from data.strategy_account_mark_reference import decode_current_mark
from data.strategy_halt_gap_diagnostic_v1 import HEADER,SOURCE_URL
from data.strategy_halt_aware_pullback_sources_v1 import candidate_from_yahoo_bytes
from test_strategy_paper_daily_signal_v1 import setup,reference

ROOT=Path(__file__).resolve().parents[1]


def capture(book,now,price=1000,recent_only=False,halt=True):
    """Explicit synthetic raw bytes + reviewer fixture, never a live attestation."""
    at=now.isoformat();opening=int(now.replace(hour=14,minute=30,second=0).timestamp())
    files={'identity':b'synthetic identity fixture'};marks={};identities={}
    for sid in ('A','B'):
        value=price if sid=='B' else 200
        times=[opening+60*i for i in range(30)]
        if recent_only:times=times[-1:]
        n=len(times)
        raw=canonical(dict(chart=dict(error=None,result=[dict(meta=dict(symbol=sid,currency='USD',
            instrumentType='EQUITY',exchangeTimezoneName='America/New_York',dataGranularity='1m',
            regularMarketPrice=value,regularMarketTime=int(now.timestamp()),
            currentTradingPeriod=dict(regular=dict(start=opening,end=opening+23400))),timestamp=times,
            indicators=dict(quote=[dict(open=[value]*n,high=[value+2]*n,low=[value-20]*n,
                close=[value]*n,volume=[100]*n)]))])))
        raw_path=sid+'.raw';receipt_path=sid+'.receipt.json'
        files[raw_path]=raw
        files[receipt_path]=canonical(dict(security_id=sid,ticker=sid,started_at=at,captured_at=at,checked_at=at,
            raw_path=raw_path,raw_sha256=sha256(raw).hexdigest()))
        decoded=decode_current_mark(raw,ticker=sid,now=now,captured_at=now)
        marks[sid]=dict(security_id=sid,ticker=sid,currency='USD',price=decoded['last_price'],
            price_basis='CONDITIONAL_PROVIDER_REGULAR_QUOTE_UNITS',observed_at=decoded['last_at'],
            captured_at=at,checked_at=at,source_references=[raw_path,receipt_path],
            source_hashes={p:sha256(files[p]).hexdigest() for p in (raw_path,receipt_path)})
        identities[sid]=dict(security_id=sid,ticker=sid,source_references=['identity'],
            source_hashes={'identity':sha256(files['identity']).hexdigest()})
    package=dict(status='MARKS_CAPTURED_UNIT_REVIEW_REQUIRED',account_id=book['application']['account_id'],
        account_revision=book['revision'],session=now.date().isoformat(),finished_at=at,marks=marks,identities=identities,files=files)
    if halt:
        raw=('All times are Eastern Time<h3>Non-Cboe Listed Halts</h3><table><tr>'+''.join('<th>'+h+'</th>' for h in HEADER)+'</tr></table>').encode()
        files['halt.raw']=raw
        files['halt.receipt']=canonical(dict(url=SOURCE_URL,http_status=200,bytes=len(raw),raw_sha256=sha256(raw).hexdigest(),started_at=at,received_at=at))
        package['halt_evidence']=dict(raw_path='halt.raw',receipt_path='halt.receipt')
    package['source_hashes']={p:sha256(raw).hexdigest() for p,raw in files.items()}
    review=dict(schema='STRATEGY_TARGET_UNIT_REVIEW_V1',status='CONDITIONAL_CURRENT_UNITS_REVIEWED',
        account_revision=book['revision'],marks_sha256=sha256(canonical(marks)).hexdigest(),unresolved=[],pending_rights=[],
        coverage_complete=False,source_authenticated=False,reviewed_at=at,securities={sid:dict(security_id=sid,
            current_mark_sha256=sha256(canonical(mark)).hexdigest(),current_price_basis=mark['price_basis'],
            held_quantities_in_current_units=True,covered_through=at) for sid,mark in marks.items()})
    return package,review


def arguments(folder,clock,held=True):
    daily=setup(folder,held=held)
    caps=PaperExecutionCaps(book=daily['book'],clock=clock)
    app=dict(schema='PAPER_EXECUTION_APPLICATION_V1',scope=SCOPE,authorized=True,automatic_acceptance_allowed=False,
        account_id=daily['book']['application']['account_id'],
        account_genesis_sha256=sha256(canonical(daily['book']['application'])).hexdigest(),
        daily_application_sha256=daily['trusted_application_sha256'],cap_namespace_id=caps.namespace_id,
        approved_at='2026-10-30T20:01:00+00:00',valid_from='2026-11-03T14:30:00+00:00',valid_until='2026-11-03T21:00:00+00:00',
        code_sha256={p:sha256((ROOT/p).read_bytes()).hexdigest() for p in CODE_PATHS})
    package,review=capture(daily['book'],datetime.fromisoformat(clock()))
    return dict(daily_arguments=daily,application_bytes=canonical(app),trusted_application_sha256=sha256(canonical(app)).hexdigest(),
        market_capture=package,unit_review=review,trusted_unit_review_sha256=sha256(canonical(review)).hexdigest(),caps=caps,clock=clock)


class Cap:
    def candidate(self,**kwargs):return candidate_from_yahoo_bytes(previous_cap=None,**kwargs)


class PaperExecutionTests(unittest.TestCase):
    def test_current_real_shared_and_paper_buy_sell_price_quantity_parity(self):
        with TemporaryDirectory() as folder:
            args=arguments(folder,lambda:'2026-11-03T15:00:00+00:00');self.addCleanup(args['caps'].close)
            result=preview_paper_execution(**args)
            self.assertEqual(result['status'],'CONDITIONAL_PREVIEW_READY')
            self.assertEqual({o['side'] for o in result['new_orders']},{'BUY','SELL'})
            real=reference(args['daily_arguments'])['state']
            real,_=apply_event(real,dict(event_id='cash',kind='CASH_CONFIRM',amount=args['daily_arguments']['book']['cash'],cash_basis='TOTAL_UNINVESTED'),expected_revision=real['revision'])
            package=deepcopy(args['market_capture']);package.update(account_id=real['account_id'],account_revision=real['revision'])
            review=deepcopy(args['unit_review']);review['account_revision']=real['revision']
            inputs=dict(state=real,target_quantities=result['effective_target_quantities'],market_capture=package,
                unit_review=review,cap_store=Cap(),now=args['clock']())
            old=build_execution_limits(**inputs);shared=build_real_execution_limits(**inputs)
            self.assertEqual(old,shared)
            for sid,limit in old['limits'].items():
                for field in ('buy','sell','buy_evaluated','reference_valid_until','evaluated_net_gap'):
                    self.assertEqual(limit[field],result['limits'][sid][field])
            diff=preview_scoped_account(state=real,legacy_shares={},target_quantities=result['effective_target_quantities'],
                now=args['clock'](),maximum_mark_age_seconds=120,fee_bps='0',**old)
            self.assertEqual([(o['security_id'],o['side'],o['quantity'],o['limit_price']) for o in diff['new_orders']],
                [(o['security_id'],o['side'],o['quantity'],o['limit_price']) for o in result['new_orders']])

    def test_same_day_cap_not_raised_and_namespace_replacement_rejected(self):
        with TemporaryDirectory() as folder:
            now=[datetime.fromisoformat('2026-11-03T15:00:00+00:00')]
            args=arguments(folder,lambda:now[0].isoformat());self.addCleanup(args['caps'].close)
            first=preview_paper_execution(**args)
            now[0]+=timedelta(seconds=10)
            args['market_capture'],args['unit_review']=capture(args['daily_arguments']['book'],now[0],price=1100)
            args['trusted_unit_review_sha256']=sha256(canonical(args['unit_review'])).hexdigest()
            second=preview_paper_execution(**args)
            self.assertLessEqual(Fraction(second['limits']['B']['buy']),Fraction(first['limits']['B']['buy']))
            self.assertEqual(second['cap_proofs'][0]['cap_store_receipt']['prior_history_replayed'],1)
            original=args['caps'];args['caps']=PaperExecutionCaps(book=args['daily_arguments']['book'],clock=args['clock'])
            self.addCleanup(args['caps'].close)
            with self.assertRaisesRegex(ValueError,'PAPER_CAP_NAMESPACE_REPLACED'):preview_paper_execution(**args)
            args['caps']=original;original.close()
            with self.assertRaisesRegex(ValueError,'PAPER_CAP_ACCOUNT_BINDING'):preview_paper_execution(**args)

    def test_buy_history_failure_preserved_independent_fresh_sell_still_works(self):
        with TemporaryDirectory() as folder:
            args=arguments(folder,lambda:'2026-11-03T15:00:00+00:00');self.addCleanup(args['caps'].close)
            args['market_capture'],args['unit_review']=capture(args['daily_arguments']['book'],datetime.fromisoformat(args['clock']()),recent_only=True)
            args['trusted_unit_review_sha256']=sha256(canonical(args['unit_review'])).hexdigest()
            original=deepcopy(args['market_capture'])
            args['sell_market_capture'],args['sell_unit_review']=capture(args['daily_arguments']['book'],datetime.fromisoformat(args['clock']()),recent_only=True,halt=False)
            args['trusted_sell_unit_review_sha256']=sha256(canonical(args['sell_unit_review'])).hexdigest()
            result=preview_paper_execution(**args)
            self.assertEqual(result['status'],'CONDITIONAL_SELL_PREVIEW_BUYS_WAIT')
            self.assertEqual([(o['side'],o['quantity']) for o in result['new_orders']],[('SELL',14)])
            self.assertEqual(result['effective_target_quantities']['B'],10)
            self.assertEqual(result['execution_quantities']['B'],0)
            self.assertEqual(result['buy_data_failure']['source_hashes'],original['source_hashes'])
            self.assertEqual(args['market_capture'],original)
            self.assertEqual(result['difference']['spendable_cash'],'18600')
            self.assertEqual(result['cap_proofs'],[])

    def test_no_holdings_bad_buy_data_is_wait_not_order(self):
        with TemporaryDirectory() as folder:
            args=arguments(folder,lambda:'2026-11-03T15:00:00+00:00',held=False);self.addCleanup(args['caps'].close)
            args['market_capture'].pop('halt_evidence')
            result=preview_paper_execution(**args)
            self.assertEqual(result['status'],'WAIT_BUY_MINUTE_DATA');self.assertEqual(result['new_orders'],[])

    def test_pending_sale_proceeds_do_not_finance_buy_quantity(self):
        with TemporaryDirectory() as folder:
            args=arguments(folder,lambda:'2026-11-03T15:00:00+00:00');self.addCleanup(args['caps'].close)
            args['market_capture'],args['unit_review']=capture(args['daily_arguments']['book'],datetime.fromisoformat(args['clock']()),price=2000)
            args['trusted_unit_review_sha256']=sha256(canonical(args['unit_review'])).hexdigest()
            result=preview_paper_execution(**args)
            buy=next(o for o in result['new_orders'] if o['side']=='BUY')
            self.assertEqual(buy['quantity'],9)
            self.assertLessEqual(Fraction(buy['limit_price'])*buy['quantity'],18600)
            self.assertEqual(result['difference']['spendable_cash'],'18600')

    def test_independent_sell_still_requires_own_fresh_review(self):
        with TemporaryDirectory() as folder:
            args=arguments(folder,lambda:'2026-11-03T15:00:00+00:00');self.addCleanup(args['caps'].close)
            args['market_capture'].pop('halt_evidence')
            args['sell_market_capture'],args['sell_unit_review']=capture(args['daily_arguments']['book'],datetime.fromisoformat(args['clock']()),recent_only=True,halt=False)
            args['sell_unit_review']['reviewed_at']='2026-11-03T14:57:59+00:00'
            args['trusted_sell_unit_review_sha256']=sha256(canonical(args['sell_unit_review'])).hexdigest()
            with self.assertRaisesRegex(ValueError,'UNIT_REVIEW_BINDING_INVALID'):preview_paper_execution(**args)

    def test_changed_raw_bad_review_and_expiry_rejected(self):
        for mode in ('raw','review','expiry','scope'):
            with self.subTest(mode=mode),TemporaryDirectory() as folder:
                now=[datetime.fromisoformat('2026-11-03T15:00:00+00:00')]
                args=arguments(folder,lambda:now[0].isoformat());self.addCleanup(args['caps'].close)
                if mode=='raw':args['market_capture']['files']['A.raw']+=b' '
                elif mode=='review':args['unit_review']['source_authenticated']=True
                elif mode=='scope':
                    app=json.loads(args['application_bytes']);app['scope']='WEB_MANUAL_ADVICE_RULE_ONLY'
                    args['application_bytes']=canonical(app);args['trusted_application_sha256']=sha256(canonical(app)).hexdigest()
                else:
                    original=args['caps'].candidate
                    def expire(**kwargs):
                        answer=original(**kwargs);now[0]+=timedelta(seconds=121);return answer
                    args['caps'].candidate=expire
                with self.assertRaises(ValueError):preview_paper_execution(**args)


if __name__=='__main__':unittest.main()
