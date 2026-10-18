from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
import unittest
from core.strategy_account_ledger import create_account, apply_event, canonical
from data.current_quantity_v2_paper_action_sources import PaperActionEvidenceSources
from data.strategy_account_unit_review import review_interval

NOW = datetime.fromisoformat('2026-10-16T14:00:00+00:00')


def fixture(events=None, notice='Unrelated notice', held=False):
    state = create_account('review-test')
    if held:
        state, _ = apply_event(state, dict(event_id='fill', kind='DIRECT_FILL', security_id='S',
            side='BUY', quantity=2, price='10', fees='0', executed_at='2026-10-15T14:00:00Z'),
            expected_revision=state['revision'])
    securities = {'S': {'ticker': 'AAA'}}
    marks = {'S': dict(security_id='S', currency='USD', price='10', price_basis='CURRENT',
                       observed_at=NOW.isoformat(),captured_at=NOW.isoformat())}
    def daily(ticker, start, end):
        return dict(status=200, body=canonical(dict(chart=dict(error=None, result=[dict(
            meta=dict(symbol=ticker, currency='USD', instrumentType='EQUITY'), events=events or {})]))))
    rss = ('<rss><channel><title>Nasdaq</title><item><title>'+notice+
           '</title><pubDate>Fri, 16 Oct 2026 13:00:00 GMT</pubDate></item></channel></rss>').encode()
    source = PaperActionEvidenceSources(fetch=daily, rss_fetch=lambda:dict(status=200, body=rss), clock=lambda:NOW)
    closed = '2026-10-14T20:00:00Z'
    package = source.capture(dict(account_id=state['account_id'], state_revision=state['revision'],
        window_start=closed, observed_floor=closed, securities=securities, current_target_quantities={}))
    return dict(state=state, securities=securities, marks=marks, action_package=package,
        training_manifest_sha256='a'*64, historical_search_arguments_sha256='b'*64,
        historical_price_basis='HISTORICAL', training_closed_at=closed,
        marks_sha256=sha256(canonical(marks)).hexdigest(), now=NOW.isoformat())


class UnitReviewTests(unittest.TestCase):
    def test_future_dated_received_notice_is_scanned_not_globally_vetoed(self):
        for title in ('Unrelated future notice', 'AAA future split'):
            args=fixture(notice=title); package=args['action_package']
            rawpath=package['documents']['rss_raw']; receiptpath=package['documents']['rss_receipt']
            raw=package['files'][rawpath].replace(b'Fri, 16 Oct 2026 13:00:00 GMT',b'Fri, 16 Oct 2026 20:00:00 GMT')
            receipt=json.loads(package['files'][receiptpath]);receipt.update(raw_sha256=sha256(raw).hexdigest(),stored_bytes=len(raw))
            package['files'][rawpath]=raw;package['files'][receiptpath]=canonical(receipt)
            for path in (rawpath,receiptpath):package['source_hashes'][path]=sha256(package['files'][path]).hexdigest()
            if title.startswith('AAA'):
                with self.assertRaisesRegex(ValueError,'KNOWN_NOTICE'):review_interval(**args)
            else:self.assertEqual(review_interval(**args)['status'],'CONDITIONAL_CURRENT_UNITS_REVIEWED')

    def test_conditional_review_without_synthetic_intraday_origin(self):
        args = fixture(); original = deepcopy(args)
        result = review_interval(**args)
        self.assertEqual(result['status'], 'CONDITIONAL_CURRENT_UNITS_REVIEWED')
        self.assertFalse(result['coverage_complete'])
        self.assertFalse(result['source_authenticated'])
        self.assertEqual(result['training_cutoff_date'], '2026-10-14')
        self.assertEqual(args, original)

    def test_observed_actions_rights_and_notices_block(self):
        for args, reason in [
            (fixture(events={'splits': {'1': {'numerator': 2}}}), 'KNOWN_UNIT_CHANGE'),
            (fixture(events={'dividends': {'1': {'amount': 1}}}, held=True), 'POSSIBLE_CASH_RIGHTS'),
            (fixture(notice='AAA announces action'), 'KNOWN_NOTICE')]:
            with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, reason):
                review_interval(**args)

    def test_capture_later_than_action_window_and_unknown_empty_events_rejected(self):
        args=fixture()
        args['marks']['S']['captured_at']='2026-10-16T14:00:01+00:00'
        args['marks_sha256']=sha256(canonical(args['marks'])).hexdigest()
        args['now']='2026-10-16T14:00:02+00:00'
        with self.assertRaisesRegex(ValueError,'ACTION_INTERVAL_NOT_COVERED'):review_interval(**args)
        for events in ({'unknownAction':{}},{'dividends':[]},{'splits':None}):
            with self.subTest(events=events), self.assertRaisesRegex(ValueError,'ACTION_EVENTS_INVALID'):
                review_interval(**fixture(events=events))

    def test_rehashed_short_interval_wrong_identity_and_corrupt_raw_rejected(self):
        for kind in ('interval', 'ticker', 'corrupt'):
            args = fixture(); package = args['action_package']; path = package['documents']['action_receipts']['S']
            row = json.loads(package['files'][path])
            if kind == 'interval': row['requested_from'] = NOW.isoformat()
            elif kind == 'ticker': row['ticker'] = 'BBB'
            else:
                package['files'][row['raw_path']] += b' '
                package['source_hashes'][row['raw_path']] = sha256(package['files'][row['raw_path']]).hexdigest()
            package['files'][path] = canonical(row)
            package['source_hashes'][path] = sha256(package['files'][path]).hexdigest()
            with self.subTest(kind=kind), self.assertRaises(ValueError): review_interval(**args)


if __name__ == '__main__': unittest.main()
