import json
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest

from data.news_issuer_source import API, parse_issuer_story
from data.news_scheduled_earnings_v1 import build_scheduled_earnings


class ScheduledEarningsTests(unittest.TestCase):
    def fixture(self, root, date='November 6, 2026', weekday='Friday', extra=''):
        observed = '2026-11-04T05:00:00+00:00'
        published = '2026-10-13T11:00:00+00:00'
        title = f'Moderna to Report Third Quarter 2026 Financial Results on {weekday}, {date}'
        body = ('SOURCE: Moderna, Inc. NASDAQ:MRNA press@modernatx.com '
                f'will host a live conference call and webcast at 8:00 a.m. ET on {weekday}, '
                f'{date} to report its third quarter 2026 financial results. '+extra)
        headline = dict(newsid=date, headline=title, datetime=published, qmsource='bayaw',
                        topic='MRNA', storyurl='https://api.quotemedia.com/supplement/news-story/?id='+date)
        story = {'qmcistory': {'storyid': date, 'source': 'ACCESS Newswire', 'qmnews': {
            'qmstory': {'qmheadline': title, 'datetime': published, 'qmtext': body}}}}
        event = parse_issuer_story(headline, story, observed)
        receipts = []
        (root/'raw').mkdir(exist_ok=True)
        for endpoint, document, params in [
            ('getHeadlines.json', {'results': {'news': [{'topicstring': 'MRNA', 'newsitem': [headline]}]}}, {}),
            ('getStory.json', story, {'storyId': date})]:
            raw = json.dumps(document).encode()
            digest = sha256(raw).hexdigest()
            (root/'raw'/('issuer-'+digest+'.json')).write_bytes(raw)
            receipts.append(dict(url=API+endpoint, params=params, sha256=digest, fetched_at=observed))
        return dict(generated_at=observed, events=[event], source_receipts=receipts)

    def build(self, snapshot, root):
        return build_scheduled_earnings(snapshot, root, [dict(ticker='MRNA', security_id='synthetic')])

    def test_old_notice_future_call_preserves_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); snapshot = self.fixture(root)
            result = self.build(snapshot, root); event = result['events'][0]
            self.assertEqual(event['scheduled_at'], '2026-11-06T13:00:00+00:00')
            self.assertEqual(event['published_at'], '2026-10-13T11:00:00+00:00')
            self.assertFalse(event['eligible_as_new_trigger'])
            self.assertFalse(result['changes_strategy'])
            self.assertIsNone(event['automatic_trade_action'])

    def test_stale_capture_and_reached_call_do_not_admit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); snapshot = self.fixture(root)
            snapshot['generated_at'] = '2026-11-05T05:00:01+00:00'
            self.assertEqual(self.build(snapshot, root)['coverage'][0]['reason'], 'SCHEDULE_REFRESH_REQUIRED')
            # Move decision and receipt collection together to test the call boundary.
            snapshot['generated_at'] = '2026-11-06T13:00:00+00:00'
            snapshot['events'][0]['collected_at'] = snapshot['generated_at']
            for receipt in snapshot['source_receipts']: receipt['fetched_at'] = snapshot['generated_at']
            self.assertEqual(self.build(snapshot, root)['coverage'][0]['reason'], 'SCHEDULE_OUTSIDE_FUTURE_WINDOW')

    def test_cancellation_bad_weekday_and_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for kwargs, reason in [({'extra': 'The call is postponed.'}, 'SCHEDULE_CHANGE_REQUIRES_REVIEW'),
                                   ({'weekday': 'Thursday'}, 'SCHEDULE_WEEKDAY_CONFLICT')]:
                result = self.build(self.fixture(root, **kwargs), root)
                self.assertFalse(result['events']); self.assertEqual(result['coverage'][0]['reason'], reason)
            snapshot = self.fixture(root); snapshot['events'][0]['content_sha256'] = '0'*64
            self.assertFalse(self.build(snapshot, root)['events'])

    def test_conflicting_reschedule_not_latest_wins(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); first = self.fixture(root)
            second = self.fixture(root, date='November 9, 2026', weekday='Monday')
            first['events'] += second['events']; first['source_receipts'] += second['source_receipts']
            result = self.build(first, root)
            self.assertEqual(result['status'], 'REVIEW_REQUIRED'); self.assertFalse(result['events'])


if __name__ == '__main__':
    unittest.main()
