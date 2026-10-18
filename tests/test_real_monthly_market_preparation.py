from pathlib import Path
import json
import unittest
from datetime import datetime
from hashlib import sha256
from tempfile import TemporaryDirectory
from unittest.mock import patch
from test_coordinate_monthly_simulation import setup
from test_current_quantity_v2_monthly_known_source_review import evidence, POLICY_SCHEMA
from scripts.run_real_monthly_market_preparation import run


def fixture(folder):
    root, settings, request, old, calls, save = setup(folder)
    from data.current_quantity_v2_source_admission_policy import SOURCE_WITHDRAWALS
    for item in SOURCE_WITHDRAWALS:
        for path in item['evidence']:
            target=root/path
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes((Path(__file__).resolve().parents[1]/path).read_bytes())
    original = old['fetch']
    def fetch(url, **kwargs):
        result = original(url, **kwargs)
        obj = json.loads(result['raw'])
        obj['chart']['result'][0]['meta']['longName'] = 'Beta Business Corporation'
        result['raw'] = json.dumps(obj).encode()
        return result
    member = json.loads((root/'previous.json').read_bytes())['candidates'][0]
    source = 'synthetic-class-source.json'
    digest = save(source, dict(synthetic=True))
    row = dict(security_id=member['security_id'], ticker=member['ticker'], issuer_id=member['issuer_id'],
               status='READY_CONDITIONAL_IDENTITY', identity_reviewed=True, no_unresolved_identifier_conflict=True,
               unresolved=[], security_class='Synthetic common shares', source_references=[source])
    save('auto-class.json', dict(rows=[row], source_hashes={source:digest}))
    save('auto-identities.json', dict(candidates=[dict(member,status='READY_CONDITIONAL', identity_reviewed=True,
                                                    identity_source_references=['auto-class.json',source])]))
    pins = {p:sha256((root/p).read_bytes()).hexdigest() for p in ('synthetic-evidence.json',source,'auto-class.json','auto-identities.json')}
    descriptor = save('descriptor.json', dict(source_hashes=pins))
    bootstrap = save('bootstrap.json', dict(descriptor=dict(path='descriptor.json',sha256=descriptor),identity_manifest_path='auto-identities.json'))
    policy = dict(schema=POLICY_SCHEMA,authority='RESEARCH_BOUNDED_SOURCE_ASSUMPTION',maximum_capture_age_seconds=3600,
                  matching='ALL_VISIBLE_ITEMS_EXACT_TICKER_OR_META_NAME',coverage='INCOMPLETE_MAY_OMIT_ACTIONS',retention='UNKNOWN')
    policyhash = save('policy.json',policy)
    rss_calls = []
    def rss():
        rss_calls.append(1)
        return dict(status=200, headers={'Content-Type':'application/xml'}, body=evidence()['feed_raw'])
    args = dict(coordinator_config=old['config_path'],coordinator_sha256=old['config_sha256'],
                bootstrap_config=root/'bootstrap.json',bootstrap_sha256=bootstrap,policy_path='policy.json',policy_sha256=policyhash,
                output_directory='real-market',clock=old['clock'],fetch=fetch,rss_fetch=rss)
    return root,args,calls,rss_calls


class RealMarketPreparationTests(unittest.TestCase):
    def test_absolute_policy_path_normalized_before_publication(self):
        with TemporaryDirectory() as folder:
            root,args,calls,rss = fixture(folder)
            absolute = dict(args, policy_path=str(root/'policy.json'))
            self.assertEqual(run(**absolute)['status'], 'PREFLIGHT_ONLY')
            self.assertEqual(calls+rss, [])
            result = run(**absolute, execute=True)
            self.assertEqual(result['status'], 'MARKET_PUBLICATION_READY_NOT_ACTIVATED')
            self.assertEqual(run(**args, execute=True), result)
            inputs = json.loads((root/'real-market/inputs.json').read_bytes())
            self.assertEqual(inputs['policy_path'], 'policy.json')

    def test_no_account_real_publication_and_verified_reuse(self):
        with TemporaryDirectory() as folder:
            root,args,calls,rss = fixture(folder)
            with patch('backtest.current_quantity_v2_simulation_store.SimulationStore',side_effect=AssertionError('NO_ACCOUNT')):
                self.assertEqual(run(**args)['status'],'PREFLIGHT_ONLY')
                self.assertFalse((root/'real-market').exists())
                result=run(**args,execute=True)
                self.assertEqual(result['status'],'MARKET_PUBLICATION_READY_NOT_ACTIVATED',result)
                self.assertEqual(len(calls),1)
                self.assertEqual(len(rss),1)
                self.assertEqual(run(**dict(args,clock=lambda:datetime.fromisoformat('2026-12-01T15:00:00+00:00')),execute=True),result)
                self.assertFalse((root/'published').exists())
                self.assertFalse((root/'next-daily.json').exists())
                publication=json.loads((root/result['publication_path']).read_bytes())
                self.assertEqual(publication['status'],'PUBLISHED_CONDITIONAL_NOT_ACTIVATED')
                (root/'prepared/input.json').write_text('{}')
                with self.assertRaisesRegex(ValueError,'SOURCE_CHANGED'):run(**args,execute=True)

    def test_before_close_and_missed_window_no_output_or_fetch(self):
        for time,status in [('2026-11-02T20:00:00+00:00','WAITING_SESSION_CLOSE'),('2026-12-01T15:00:00+00:00',None)]:
            with TemporaryDirectory() as folder:
                root,args,calls,rss=fixture(folder)
                args['clock']=lambda:datetime.fromisoformat(time)
                if status:self.assertEqual(run(**args,execute=True)['status'],status)
                else:
                    with self.assertRaisesRegex(ValueError,'WINDOW_ELAPSED'):run(**args,execute=True)
                self.assertFalse((root/'real-market').exists());self.assertEqual(calls+rss,[])

    def test_notice_persists_wait_without_retry(self):
        with TemporaryDirectory() as folder:
            root,args,calls,rss=fixture(folder)
            args['rss_fetch']=lambda:dict(status=200,headers={},body=evidence('BBB stock split')['feed_raw'])
            result=run(**args,execute=True)
            self.assertEqual(result['status'],'WAITING_REVIEW')
            self.assertEqual(run(**args,execute=True),result)
            self.assertFalse((root/'real-market/publication.json').exists())

    def test_crossing_open_during_capture_preserves_failure(self):
        with TemporaryDirectory() as folder:
            root,args,calls,rss=fixture(folder)
            old_clock=args['clock'];original=args['fetch'];crossed=[False]
            def fetch(*values,**kwargs):
                result=original(*values,**kwargs);crossed[0]=True;return result
            args['fetch']=fetch
            args['clock']=lambda:datetime.fromisoformat('2026-12-01T15:00:00+00:00') if crossed[0] else old_clock()
            with self.assertRaises(ValueError):run(**args,execute=True)
            self.assertTrue((root/'real-market/failed.json').exists())
            self.assertFalse((root/'real-market/publication.json').exists())
            self.assertEqual(rss,[])

    def test_failure_not_retried_and_capture_stage_reused(self):
        from scripts.coordinate_monthly_simulation import run as coordinate
        with TemporaryDirectory() as folder:
            root,args,calls,rss=fixture(folder)
            coordinate(config_path=args['coordinator_config'],config_sha256=args['coordinator_sha256'],clock=args['clock'],fetch=args['fetch'],execute=True)
            args['rss_fetch']=lambda:(_ for _ in ()).throw(OSError('transport'))
            with self.assertRaises(ValueError):run(**args,execute=True)
            self.assertEqual(len(calls),1)
            with self.assertRaisesRegex(ValueError,'NO_RETRY'):run(**args,execute=True)
            self.assertTrue((root/'real-market/failed.json').exists())


if __name__=='__main__':unittest.main()
