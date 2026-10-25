from datetime import datetime,timezone
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from scripts.capture_daily_followup_groups_v1 import capture


class CaptureGroupTests(TestCase):
    now=datetime(2026,10,23,9,tzinfo=timezone.utc)
    def plan(self):
        return json.dumps(dict(schema='DAILY_FOLLOWUP_CAPTURE_GROUPS_V1',groups=[dict(
            security_id=t,ticker=t,earliest_reference_session='2026-10-21',observations=[{}],
            sessions={'2026-10-22':'2026-10-22T20:00:00+00:00'}) for t in ('SNDK','MRNA')])).encode()
    def daily(self,ticker,left,right):
        return dict(status=200,body=json.dumps(dict(chart=dict(error=None,result=[dict(meta=dict(symbol=ticker))]))).encode())
    def test_two_daily_and_one_official_preserve_original_times(self):
        with TemporaryDirectory() as d:
            calls=[];raw=self.plan()
            def daily(*args):calls.append(args[0]);return self.daily(*args)
            def official():
                calls.append('official');return dict(status=200,body=b'<rss><channel><pubDate>Fri, 23 Oct 2026 08:00:00 GMT</pubDate><item><title>Fixture notice</title><pubDate>Fri, 23 Oct 2026 07:00:00 GMT</pubDate><description>Fixture</description></item></channel></rss>')
            out=Path(d)/'capture'
            result=capture(plan_bytes=raw,plan_sha256=sha256(raw).hexdigest(),output=out,clock=lambda:self.now,daily_fetch=daily,official_fetch=official)
            self.assertEqual(calls,['SNDK','MRNA','official']);self.assertEqual(result['network_calls'],3)
            self.assertFalse(result['capture_admitted']);self.assertFalse(result['performance_computed'])
            self.assertTrue((out/'complete.json').exists())
            with self.assertRaises(FileExistsError):capture(plan_bytes=raw,plan_sha256=sha256(raw).hexdigest(),output=out,clock=lambda:self.now,daily_fetch=daily,official_fetch=official)
            self.assertEqual(len(calls),3)
    def test_block_page_retained_and_not_completed(self):
        with TemporaryDirectory() as d:
            raw=self.plan();out=Path(d)/'capture'
            with self.assertRaises(Exception):
                capture(plan_bytes=raw,plan_sha256=sha256(raw).hexdigest(),output=out,clock=lambda:self.now,
                    daily_fetch=self.daily,official_fetch=lambda:dict(status=200,body=b'<html><body>blocked</html>'))
            self.assertTrue((out/'official.bin').exists());self.assertTrue((out/'failed.json').exists())
            self.assertFalse((out/'complete.json').exists())
    def test_unclosed_session_rejected_before_network(self):
        with TemporaryDirectory() as d:
            plan=json.loads(self.plan());plan['groups'][0]['sessions']['2026-10-23']='2026-10-23T20:00:00+00:00';raw=json.dumps(plan).encode()
            with self.assertRaisesRegex(ValueError,'GROUP_CAPTURE_NOT_CLOSED'):
                capture(plan_bytes=raw,plan_sha256=sha256(raw).hexdigest(),output=Path(d)/'capture',clock=lambda:self.now)
            self.assertFalse((Path(d)/'capture').exists())
