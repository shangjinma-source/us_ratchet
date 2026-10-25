import unittest
from datetime import datetime,timezone,timedelta
from data.strategy_rss_verified_transport_v3 import VerifiedRssTransportV3
from scripts.current_research_official_alert_capture import URL,parse_official_feed


def raw():
    return b"<rss><channel><title>Nasdaq</title><pubDate>Tue, 20 Oct 2026 14:48:22 GMT</pubDate><item><title>notice</title><pubDate>Tue, 20 Oct 2026 14:00:00 GMT</pubDate></item></channel></rss>"

class RssTests(unittest.TestCase):
    def case(self,arrival):
        point=[arrival];sinks=[];calls=[];response=dict(status=200,url=URL,body=raw())
        def fetch():calls.append(1);return response
        def sink(evidence,body):sinks.append((dict(evidence),body))
        adapter=VerifiedRssTransportV3(fetch=fetch,sink=sink,clock=lambda:point[0],sleep=lambda seconds:point.__setitem__(0,point[0]+timedelta(seconds=seconds)))
        return adapter,point,sinks,calls,response

    def test_real_wait_semantics_and_unchanged_original_parser(self):
        arrived=datetime(2026,10,20,14,48,20,540919,tzinfo=timezone.utc)
        adapter,point,sinks,calls,response=self.case(arrived)
        self.assertIs(adapter(),response)
        evidence,body=sinks[0]
        self.assertEqual(evidence["transport_received_at"],arrived.isoformat())
        self.assertEqual(body,raw());self.assertEqual(calls,[1])
        self.assertFalse(parse_official_feed(body,observed_at=point[0])["channel"]["future_publication"])
        self.assertTrue(parse_official_feed(body,observed_at=arrived)["channel"]["future_publication"])

    def test_item_future_and_monotonic_budget(self):
        arrived=datetime(2026,10,20,14,48,20,540919,tzinfo=timezone.utc)
        adapter,point,sinks,calls,response=self.case(arrived)
        response['body']=raw().replace(b'14:00:00 GMT',b'14:48:21 GMT')
        self.assertIs(adapter(),response)
        self.assertEqual(sinks[0][0]['future_item_indices'],[0])
        from data.strategy_account_notice_review import review_notices
        self.assertTrue(review_notices(response['body'],ticker='notice',issuer_names=[])['blocking'])
        self.assertFalse(review_notices(response['body'],ticker='MRNA',issuer_names=['Moderna'])['blocking'])
        self.assertEqual(calls,[1])
        adapter,point,sinks,calls,response=self.case(arrived)
        times=iter([0,6]);adapter.monotonic=lambda:next(times)
        with self.assertRaisesRegex(ValueError,'MONOTONIC'):adapter()
        self.assertEqual(calls,[1])

    def test_far_future_frozen_rollback_delay_and_sink_fail(self):
        arrived=datetime(2026,10,20,14,48,20,540919,tzinfo=timezone.utc)
        for delta in (0,-1,6):
            adapter,point,sinks,calls,_=self.case(arrived)
            adapter.sleep=lambda seconds:point.__setitem__(0,point[0]+timedelta(seconds=delta))
            with self.assertRaises(ValueError):adapter()
            self.assertEqual(calls,[1]);self.assertEqual(sinks[0][1],raw())
            self.assertEqual(sinks[0][0]["status"],"BLOCKED_BEFORE_CAPTURE_RETURN")
        adapter,point,sinks,calls,_=self.case(arrived-timedelta(seconds=5))
        with self.assertRaisesRegex(ValueError,"TOO_FAR"):adapter()
        adapter,point,sinks,calls,_=self.case(arrived)
        def fail(*_):raise OSError("disk")
        adapter.sink=fail
        with self.assertRaises(OSError):adapter()
        self.assertEqual(calls,[1])
