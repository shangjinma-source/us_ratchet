import json,unittest
from hashlib import sha256
from tempfile import TemporaryDirectory
from datetime import datetime
from scripts.monthly_experimental_domain_capture import run,prepare
from test_monthly_experimental_domain_capture import fixture
from data.current_quantity_v2_monthly_known_source_review import review,POLICY_SCHEMA
from scripts.current_research_official_alert_capture import URL


def setup(folder,names=True):
    args,plan,ph,original,calls=fixture(folder)
    def fetch(url,**kw):
        response=original(url,**kw);obj=json.loads(response['raw'])
        if names:obj['chart']['result'][0]['meta']['longName']='Beta Business Corporation'
        response['raw']=json.dumps(obj).encode();return response
    run('experiment.json',ph,root=args['root'],clock=args['clock'],capture=True,fetch=fetch)
    args.update(previous_manifest_sha256=plan['previous_manifest_sha256'],plan_path='experiment.json',plan_sha256=ph,capture_index_path='actual-capture/completion_index.json',capture_index_sha256=sha256((args['root']/'actual-capture/completion_index.json').read_bytes()).hexdigest(),plan_validator=prepare)
    policy=dict(schema=POLICY_SCHEMA,authority='RESEARCH_BOUNDED_SOURCE_ASSUMPTION',maximum_capture_age_seconds=3600,matching='ALL_VISIBLE_ITEMS_EXACT_TICKER_OR_META_NAME',coverage='INCOMPLETE_MAY_OMIT_ACTIONS',retention='UNKNOWN')
    return args,json.dumps(policy).encode()


def evidence(title='Other issuer announcement',date='Tue, 03 Nov 2026 10:00:00 GMT'):
    raw=('<rss><channel><item><title>'+title+'</title><pubDate>'+date+'</pubDate><description>notice</description></item></channel></rss>').encode()
    receipt=dict(url=URL,http_status=200,body_truncated=False,transport_error=None,raw_sha256=sha256(raw).hexdigest(),stored_bytes=len(raw),request_started_at_utc='2026-11-03T10:15:00+00:00',received_at_utc='2026-11-03T10:16:00+00:00')
    return dict(feed_raw=raw,feed_receipt_raw=json.dumps(receipt).encode())


class MonthlyKnownSourceTests(unittest.TestCase):
    def test_real_capture_preparation_and_finite_no_match_evidence(self):
        with TemporaryDirectory() as d:
            args,p=setup(d);r=review(preparation_arguments=args,policy_raw=p,evidence_prefix='screen',**evidence())
            self.assertEqual(r['status'],'NO_MATCH_UNDER_BOUNDED_POLICY');self.assertEqual(r['review']['unresolved'],[])
            scan=json.loads(r['evidence_files']['screen/scan.json']);self.assertFalse(scan['coverage_complete']);self.assertTrue(scan['retention_unknown'])
            self.assertEqual(scan['rows'][0]['names'],['Beta Business Corporation'])
            for path,h in r['source_hashes'].items():self.assertEqual(sha256(r['evidence_files'][path]).hexdigest(),h)
            self.assertEqual(set(r['review']),{'schema','decision_date','reviewed_at','source_references','reviewed_members','unresolved'})

    def test_positive_name_ticker_missing_date_receipt_and_names_block(self):
        with TemporaryDirectory() as d:
            args,p=setup(d)
            for feed in (evidence('BBB split'),evidence('Beta Business Corporation merger'),evidence(date=''),dict(evidence(),feed_receipt_raw=b'{}'),evidence(date='Wed, 04 Nov 2026 10:00:00 GMT')):
                r=review(preparation_arguments=args,policy_raw=p,evidence_prefix='screen',**feed)
                self.assertEqual(r['status'],'UNRESOLVED');self.assertEqual(r['review']['unresolved'][0]['ticker'],'BBB')
        with TemporaryDirectory() as d:
            args,p=setup(d,False);r=review(preparation_arguments=args,policy_raw=p,evidence_prefix='screen',**evidence())
            self.assertEqual(r['status'],'UNRESOLVED')

    def test_before_close_and_changed_training_are_rejected(self):
        with TemporaryDirectory() as d:
            args,p=setup(d)
            early=dict(args,clock=lambda:datetime.fromisoformat('2026-11-02T20:59:00+00:00'))
            with self.assertRaises(ValueError):review(preparation_arguments=early,policy_raw=p,evidence_prefix='screen',**evidence())
            (args['root']/'actual-capture').joinpath('unexpected').write_text('not evidence')
            source=args['root']/'previous.json';source.write_bytes(b'{}')
            with self.assertRaises(ValueError):review(preparation_arguments=args,policy_raw=p,evidence_prefix='screen',**evidence())

    def test_escaped_html_name_and_invalid_feed_boundaries(self):
        with TemporaryDirectory() as d:
            args,p=setup(d)
            escaped=evidence('Beta&amp;nbsp;&lt;b&gt;Business&lt;/b&gt;   Corporation merger')
            empty=evidence();empty['feed_raw']=b'<rss><channel></channel></rss>'
            rec=json.loads(empty['feed_receipt_raw']);rec.update(raw_sha256=sha256(empty['feed_raw']).hexdigest(),stored_bytes=len(empty['feed_raw']))
            empty['feed_receipt_raw']=json.dumps(rec).encode()
            stale=evidence();rec=json.loads(stale['feed_receipt_raw'])
            rec.update(request_started_at_utc='2026-11-02T21:15:00+00:00',received_at_utc='2026-11-02T21:16:00+00:00')
            stale['feed_receipt_raw']=json.dumps(rec).encode()
            for feed in (escaped,empty,stale):
                r=review(preparation_arguments=args,policy_raw=p,evidence_prefix='screen',**feed)
                self.assertEqual(r['status'],'UNRESOLVED')
                self.assertTrue(r['review']['unresolved'])
            r=review(preparation_arguments=args,policy_raw=p,evidence_prefix='screen',**escaped)
            self.assertIn('OFFICIAL_NOTICE_MATCH_REQUIRES_RESOLUTION',[row['reason'] for row in r['review']['unresolved']])

if __name__=='__main__':unittest.main()
