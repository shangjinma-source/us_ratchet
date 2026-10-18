import json
import unittest
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from test_coordinate_monthly_simulation import setup
from test_current_quantity_v2_monthly_known_source_review import evidence, POLICY_SCHEMA
from scripts.monthly_experimental_domain_capture import run, prepare
from scripts.build_monthly_market_review_request import construct
from scripts.publish_monthly_market_configuration import publish


def fixture(folder):
    root, settings, _, args, calls, save = setup(folder)
    original = args['fetch']
    def fetch(url, **kwargs):
        result = original(url, **kwargs)
        body = json.loads(result['raw'])
        body['chart']['result'][0]['meta']['longName'] = 'Beta Business Corporation'
        result['raw'] = json.dumps(body).encode()
        return result
    run(settings['plan_path'], settings['plan_sha256'], root=root,
        clock=args['clock'], capture=True, fetch=fetch)
    preparation = {k: settings[k] for k in ('previous_manifest_path', 'previous_manifest_sha256',
                                           'capture_index_path', 'plan_path', 'plan_sha256')}
    preparation.update(root=root, clock=args['clock'], plan_validator=prepare,
                       capture_index_sha256=sha256((root/settings['capture_index_path']).read_bytes()).hexdigest())
    member = json.loads((root/'previous.json').read_bytes())['candidates'][0]
    source = 'class-source.json'
    source_hash = save(source, {'synthetic': True})
    row = dict(security_id=member['security_id'], ticker=member['ticker'], issuer_id=member['issuer_id'],
               status='READY_CONDITIONAL_IDENTITY', identity_reviewed=True,
               no_unresolved_identifier_conflict=True, unresolved=[], security_class='Synthetic common shares',
               source_references=[source])
    save('class.json', dict(rows=[row], source_hashes={source: source_hash}))
    candidate = dict(member, status='READY_CONDITIONAL', identity_reviewed=True,
                     identity_source_references=['class.json', source])
    save('identity.json', dict(candidates=[candidate]))
    feed = evidence()
    (root/'feed.xml').write_bytes(feed['feed_raw'])
    (root/'feed-receipt.json').write_bytes(feed['feed_receipt_raw'])
    save('policy.json', dict(schema=POLICY_SCHEMA, authority='RESEARCH_BOUNDED_SOURCE_ASSUMPTION',
                            maximum_capture_age_seconds=3600, matching='ALL_VISIBLE_ITEMS_EXACT_TICKER_OR_META_NAME',
                            coverage='INCOMPLETE_MAY_OMIT_ACTIONS', retention='UNKNOWN'))
    paths = ['synthetic-evidence.json', source, 'class.json', 'identity.json', 'feed.xml', 'feed-receipt.json', 'policy.json']
    inputs = dict(schema='MONTHLY_MARKET_REVIEW_INPUTS_V1',
                  source_hashes={p: sha256((root/p).read_bytes()).hexdigest() for p in paths},
                  feed_path='feed.xml', feed_receipt_path='feed-receipt.json',
                  policy_path='policy.json', identity_manifest_path='identity.json')
    return root, dict(preparation_arguments=preparation, settings=settings, inputs=inputs, output_prefix='market-review'), save


class MarketRequestTests(unittest.TestCase):
    def test_real_capture_compile_review_publish_without_account(self):
        with TemporaryDirectory() as folder:
            root, args, _ = fixture(folder)
            self.assertEqual(list(root.rglob('*.sqlite*')), [])
            before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
            result = construct(**args)
            self.assertEqual(result['status'], 'READY_REQUEST')
            self.assertEqual(before, {p: p.read_bytes() for p in root.rglob('*') if p.is_file()})
            self.assertEqual(result['request']['held_bar_sources'], {})
            self.assertNotIn('revision', result)
            for path, raw in result['artifacts'].items():
                target = root/path
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open('xb') as stream:
                    stream.write(raw)
            request = dict(result['request'], preparation_arguments=args['preparation_arguments'])
            published = publish(**request)
            self.assertEqual(published['status'], 'PUBLISHED_CONDITIONAL_NOT_ACTIVATED')
            self.assertFalse(published['account_writes'])
            self.assertEqual(list(root.rglob('*.sqlite*')), [])

    def test_identity_conflict_and_notice_block_without_writes(self):
        for mode in ('identity', 'notice'):
            with self.subTest(mode=mode), TemporaryDirectory() as folder:
                root, args, save = fixture(folder)
                inputs = args['inputs']
                if mode == 'identity':
                    document = json.loads((root/'identity.json').read_bytes())
                    document['candidates'][0]['issuer_id'] = 'conflicting-issuer'
                    inputs['source_hashes']['identity.json'] = save('identity.json', document)
                else:
                    feed = evidence('BBB split notice')
                    for path, key in [('feed.xml', 'feed_raw'), ('feed-receipt.json', 'feed_receipt_raw')]:
                        (root/path).write_bytes(feed[key])
                        inputs['source_hashes'][path] = sha256(feed[key]).hexdigest()
                before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
                if mode == 'identity':
                    with self.assertRaisesRegex(ValueError, 'CURRENT_MANIFEST_IDENTITY_REQUIRED'):
                        construct(**args)
                else:
                    result = construct(**args)
                    self.assertEqual(result['status'], 'WAITING_REVIEW')
                    self.assertIsNone(result['request'])
                self.assertEqual(before, {p: p.read_bytes() for p in root.rglob('*') if p.is_file()})

    def test_existing_account_bytes_untouched_and_account_fields_rejected(self):
        with TemporaryDirectory() as folder:
            root, args, _ = fixture(folder)
            db = root/'data/strategy_account/real_strategy.sqlite3'
            db.parent.mkdir(parents=True)
            db.write_bytes(b'not a database: must never be opened')
            before = db.read_bytes()
            self.assertEqual(construct(**args)['status'], 'READY_REQUEST')
            self.assertEqual(db.read_bytes(), before)
            args['inputs']['expected_revision'] = '0'*64
            with self.assertRaisesRegex(ValueError, 'MARKET_REVIEW_INPUT_FIELDS'):
                construct(**args)

    def test_changed_pins_and_unsafe_output_rejected(self):
        with TemporaryDirectory() as folder:
            root, args, _ = fixture(folder)
            for prefix in ('../outside', '/absolute', 'a/../b'):
                with self.assertRaises(ValueError):
                    construct(**dict(args, output_prefix=prefix))
            (root/'feed.xml').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'REGISTRY_SOURCE_CHANGED'):
                construct(**args)

    def test_close_time_and_fixed_calendar_pins_cannot_be_bypassed(self):
        with TemporaryDirectory() as folder:
            root, args, _ = fixture(folder)
            early = dict(args['preparation_arguments'],
                         clock=lambda: datetime.fromisoformat('2026-11-02T20:59:00+00:00'))
            with self.assertRaises(ValueError):
                construct(**dict(args, preparation_arguments=early))
            calendar_path = args['settings']['calendar_path']
            (root/calendar_path).write_bytes(b'{}')
            # Updating the supplemental pin cannot override the fixed authority.
            args['inputs']['source_hashes'][calendar_path] = sha256(b'{}').hexdigest()
            with self.assertRaisesRegex(ValueError, 'MARKET_REVIEW_PIN_CONFLICT'):
                construct(**args)


if __name__ == '__main__':
    unittest.main()
