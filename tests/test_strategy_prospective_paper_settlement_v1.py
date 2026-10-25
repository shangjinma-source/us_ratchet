from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from core.strategy_account_ledger import canonical
import test_strategy_prospective_paper_integration_v1 as integration
from data.strategy_prospective_paper_decision_v1 import produce_prospective_decision
from backtest.current_strategy_prospective_paper_book_v1 import transact
from data.strategy_prospective_paper_settlement_v1 import CODE_PATHS,accepted_references,produce_prospective_settlement
from data.current_quantity_v2_completed_session_minutes import capture
from data.current_quantity_v2_late_unit_review import BoundedLateUnitReview
from data.current_quantity_v2_paper_action_sources import PaperActionEvidenceSources

NOW=datetime.fromisoformat('2026-11-03T21:01:00+00:00')


def setup(folder,missing=False,production_halt=False,ambiguous=False):
    with patch.object(integration,'CODE_PATHS',integration.CODE_PATHS|CODE_PATHS):daily=integration.fixture(folder)
    args=integration.execution(daily,lambda:'2026-11-03T15:00:10+00:00')
    if production_halt:
        package=args['market_capture'];old=package['halt_evidence']['receipt_path']
        raw=package['files'].pop(old);package['source_hashes'].pop(old)
        path='halt-source/'+sha256(raw).hexdigest()+'.receipt.json'
        package['files'][path]=raw;package['source_hashes'][path]=sha256(raw).hexdigest()
        package['halt_evidence']['receipt_path']=path
        admission=json.loads(args['execution_admission_bytes']);admission['source_sha256']=package['source_hashes']
        args['execution_admission_bytes']=canonical(admission)
        args['trusted_execution_admission_sha256']=sha256(args['execution_admission_bytes']).hexdigest()
    try:decision=produce_prospective_decision(**args)
    finally:args['caps'].close()
    if ambiguous:
        payload=json.loads(decision['decision_bytes']);sid=payload['new_orders'][0]['security_id']
        limit=payload['limits'][sid]
        original=next(p for p in limit['source_hashes'] if p.endswith('.receipt.json') and not p.startswith('halt-source/'))
        duplicate='ambiguous.receipt.json';raw=args['market_capture']['files'][original]
        args['market_capture']['files'][duplicate]=raw
        limit['source_hashes'][duplicate]=sha256(raw).hexdigest()
        decision['decision_bytes']=canonical(payload);decision['decision_sha256']=sha256(decision['decision_bytes']).hexdigest()
    admitted={decision['decision_sha256']:decision['decision_bytes']}
    book=transact(daily['book'],dict(kind='ACCEPT',operation_id='accept',expected_revision=daily['book']['revision'],
        decision_bytes=decision['decision_bytes'].decode()),authority=daily['authority'],admitted_decisions=admitted,
        current_target_id=daily['selection_result']['decision_id'],clock=lambda:datetime.fromisoformat('2026-11-03T15:00:11+00:00'))
    files=deepcopy(args['market_capture']['files']);pins={p:sha256(b).hexdigest() for p,b in files.items()}
    refs=accepted_references(book=book,authority=daily['authority'],admitted_decisions=admitted,files=files,source_hashes=pins,now=NOW)
    captures={};reviews={}
    for oid,ref in refs.items():
        opening=datetime.fromisoformat('2026-11-03T14:30:00+00:00');closing=datetime.fromisoformat('2026-11-03T21:00:00+00:00')
        times=list(range(int(opening.timestamp()),int(closing.timestamp()),60))
        if missing:times=[]
        n=len(times)
        raw=canonical(dict(chart=dict(error=None,result=[dict(meta=dict(symbol=ref['ticker'],currency='USD',instrumentType='EQUITY',dataGranularity='1m',exchangeTimezoneName='America/New_York'),timestamp=times,indicators=dict(quote=[dict(open=[990]*n,high=[1010]*n,low=[900]*n,close=[990]*n,volume=[10]*n)]))])))
        path=Path(folder)/'completed';capture(directory=path,security_id=ref['security_id'],ticker=ref['ticker'],session='2026-11-03',session_open=opening.isoformat(),session_close=closing.isoformat(),calendar_source_reference='sha256:'+json.loads(daily['authority']['descriptor_arguments']['descriptor_bytes'])['calendar_sha256'],fetch=lambda _:raw,clock=lambda:NOW)
        paths={k:'capture/'+v for k,v in dict(raw='response.bin',receipt='receipt.json',started='started.json',minutes='minutes.json').items()}
        for p in paths.values():files[p]=(path/Path(p).name).read_bytes()
        captures[oid]=paths
        def action(ticker,start,end):return dict(status=200,body=canonical(dict(chart=dict(error=None,result=[dict(meta=dict(symbol=ticker,currency='USD',instrumentType='EQUITY'),events={})]))))
        rss=b'<rss><channel><title>Nasdaq</title><item><title>Unrelated notice</title><pubDate>Tue, 03 Nov 2026 20:00:00 GMT</pubDate></item></channel></rss>'
        source=PaperActionEvidenceSources(fetch=action,rss_fetch=lambda:dict(status=200,body=rss),clock=lambda:NOW)
        late=BoundedLateUnitReview(action_sources=source,clock=lambda:NOW).capture(reference=ref,capture_raw=raw,captured_at=NOW,origin_files=files,account_id=book['account_id'],state_revision=book['revision'])
        for p,b in late['files'].items():
            assert p not in files or files[p]==b
            files[p]=b
        reviews[oid]=late['review_path']
    return dict(book=book,authority=daily['authority'],admitted_decisions=admitted,captures=captures,unit_reviews=reviews,files=files,source_hashes={p:sha256(b).hexdigest() for p,b in files.items()},clock=lambda:NOW)


class SettlementTests(unittest.TestCase):
    def test_two_bound_market_receipts_are_ambiguous(self):
        with TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError,'ORIGIN_RECEIPT'):
                setup(folder,production_halt=True,ambiguous=True)

    def test_production_halt_receipt_shape_keeps_full_closure(self):
        with TemporaryDirectory() as folder:
            args=setup(folder,production_halt=True)
            result=produce_prospective_settlement(**args)
            halt_paths=[p for p in args['files'] if p.startswith('halt-source/')]
            self.assertEqual(len(halt_paths),1)
            self.assertIn(halt_paths[0],result['evidence']['source_review']['source_sha256'])
            args['files'][halt_paths[0]]+=b' '
            with self.assertRaisesRegex(ValueError,'SOURCE_CHANGED'):produce_prospective_settlement(**args)

    def test_original_capture_decode_units_to_actual_book_fill(self):
        with TemporaryDirectory() as folder:
            args=setup(folder);before=deepcopy(args['book']);result=produce_prospective_settlement(**args)
            evidence=result['evidence']
            filled=transact(args['book'],dict(kind='SETTLE',operation_id='settle',expected_revision=args['book']['revision'],minutes=evidence['minutes'],observed_through=evidence['observed_through'],settlement_bytes=result['settlement_bytes'].decode()),authority=args['authority'],admitted_decisions=args['admitted_decisions'],admitted_settlements={result['settlement_sha256']:result['settlement_bytes']},clock=lambda:NOW)
            self.assertEqual(filled['shares'],{'B':10});self.assertEqual(args['book'],before)
            self.assertFalse(evidence['source_review']['source_authenticated'])

    def test_missing_minutes_unknown_does_not_advance_book(self):
        with TemporaryDirectory() as folder:
            args=setup(folder,True);result=produce_prospective_settlement(**args);e=result['evidence']
            changed=transact(args['book'],dict(kind='SETTLE',operation_id='missing',expected_revision=args['book']['revision'],minutes=e['minutes'],observed_through=e['observed_through'],settlement_bytes=result['settlement_bytes'].decode()),authority=args['authority'],admitted_decisions=args['admitted_decisions'],admitted_settlements={result['settlement_sha256']:result['settlement_bytes']},clock=lambda:NOW)
            self.assertEqual(changed['shares'],{});self.assertIsNone(changed['last_observed_at'])

    def test_raw_calendar_review_and_clock_fail_closed(self):
        for mode in ('raw','calendar','review','future','rollback'):
            with self.subTest(mode=mode),TemporaryDirectory() as folder:
                args=setup(folder);oid=next(iter(args['captures']));paths=args['captures'][oid]
                if mode=='raw':args['files'][paths['raw']]+=b' '
                elif mode in ('calendar','future'):
                    row=json.loads(args['files'][paths['receipt']]);row['calendar_source_reference']='wrong' if mode=='calendar' else row['calendar_source_reference']
                    if mode=='future':row['captured_at']='2026-11-04T21:00:00+00:00'
                    args['files'][paths['receipt']]=canonical(row)
                elif mode=='review':
                    p=args['unit_reviews'][oid];row=json.loads(args['files'][p]);row.pop('bounded_evidence');args['files'][p]=canonical(row)
                else:
                    ticks=iter([NOW,datetime.fromisoformat('2026-11-03T21:00:59+00:00')]);args['clock']=lambda:next(ticks)
                if mode!='raw':args['source_hashes']={p:sha256(b).hexdigest() for p,b in args['files'].items()}
                with self.assertRaises(ValueError):produce_prospective_settlement(**args)


if __name__=='__main__':unittest.main()
