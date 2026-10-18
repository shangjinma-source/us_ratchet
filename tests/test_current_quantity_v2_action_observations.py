from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from data.current_quantity_v2_action_observations import read_saved_action_observations
from scripts.current_research_official_alert_capture import URL

NOW=datetime(2026,10,15,15,0,tzinfo=timezone.utc)


class ActionObservationTests(unittest.TestCase):
    def fixture(self,root):
        items=[('XSNDKZ unrelated','Thu, 15 Oct 2026 14:00:00 GMT','Other'),
            ('SNDK possible split tomorrow','Thu, 15 Oct 2026 16:00:00 GMT','Unknown New Category'),
            ('Sandisk Corporation update','','Equity Corporate Actions Alert'),
            ('Other stock update','Thu, 15 Oct 2026 14:00:00 GMT','Equity Corporate Actions Alert')]
        raw=('<rss xmlns:n="urn:test"><channel>'+''.join(
            '<item><title>'+title+'</title><pubDate>'+day+'</pubDate><n:NewsCategory>'+category+
            '</n:NewsCategory><link>https://example.invalid/detail</link><guid>'+str(i)+'</guid></item>'
            for i,(title,day,category) in enumerate(items))+'</channel></rss>').encode()
        (root/'feed.xml').write_bytes(raw)
        receipt=dict(url=URL,http_status=200,body_truncated=False,transport_error=None,
            raw_sha256=sha256(raw).hexdigest(),stored_bytes=len(raw),
            received_at_utc=NOW.isoformat(),request_started_at_utc=NOW.isoformat())
        (root/'receipt.json').write_text(json.dumps(receipt))
        return dict(root=root,raw_path='feed.xml',raw_sha256=sha256(raw).hexdigest(),
            receipt_path='receipt.json',receipt_sha256=sha256((root/'receipt.json').read_bytes()).hexdigest(),
            securities={'sid':dict(ticker='SNDK',issuer_aliases=['Sandisk'])},now=NOW)

    def test_boundary_alias_unknown_category_future_and_unknown_not_approved(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);args=self.fixture(root);before={p.name:p.read_bytes() for p in root.iterdir()}
            r=read_saved_action_observations(**args);rows=r['securities']['sid']['unresolved_candidates']
            self.assertEqual([x['source_item_index'] for x in rows],[1,2])
            self.assertTrue(rows[0]['future_publication_at_review']);self.assertIsNone(rows[1]['published_at'])
            self.assertTrue(all(not x['usable_as_effective_action'] for x in rows))
            self.assertFalse(r['coverage_complete']);self.assertFalse(r['unit_continuity_approved'])
            self.assertEqual(before,{p.name:p.read_bytes() for p in root.iterdir()})
            args['securities']={'absent':dict(ticker='MSFT',issuer_aliases=[])}
            self.assertEqual(read_saved_action_observations(**args)['securities']['absent']['status'],
                'NO_MATCH_IN_OBSERVED_SOURCE_NOT_NO_ACTION')

    def test_tamper_future_capture_paths_xml_and_http_rejected(self):
        for mode in ('raw','receipt','future','path','xml','http'):
            with self.subTest(mode=mode),TemporaryDirectory() as folder:
                root=Path(folder);args=self.fixture(root)
                if mode=='raw':(root/'feed.xml').write_bytes(b'tampered')
                elif mode=='receipt':(root/'receipt.json').write_text('{}')
                elif mode=='future':args['now']=NOW.replace(hour=14)
                elif mode=='path':args['raw_path']='../feed.xml'
                else:
                    doc=json.loads((root/'receipt.json').read_text())
                    if mode=='xml':
                        raw=b'<!DOCTYPE rss><rss><channel/></rss>';(root/'feed.xml').write_bytes(raw)
                        args['raw_sha256']=sha256(raw).hexdigest();doc.update(raw_sha256=args['raw_sha256'],stored_bytes=len(raw))
                    else:doc['http_status']=403
                    (root/'receipt.json').write_text(json.dumps(doc));args['receipt_sha256']=sha256((root/'receipt.json').read_bytes()).hexdigest()
                with self.assertRaises(ValueError):read_saved_action_observations(**args)


if __name__=='__main__':unittest.main()
