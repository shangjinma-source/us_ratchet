"""A new frozen identity manifest remains usable on the next session."""
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from datetime import datetime
import json
import unittest

from scripts.bootstrap_current_quantity_v2_simulation import run
from backtest.current_quantity_v2_simulation_store import SimulationStore
from backtest.current_quantity_v2_continuation_simulation import apply_continuation
from data.current_quantity_v2_current_cash_sources import MANIFEST
from data.current_quantity_v2_pullback_runtime import LazyPullbackCapStore
from test_bootstrap_current_quantity_v2_simulation import fixture,fetch,NOW
from test_current_quantity_v2_continuation_simulation import expire_all,daily_arguments,cash_review


class ExplicitManifestContinuationTests(unittest.TestCase):
    def test_bootstrap_new_manifest_then_expiry_and_next_session_without_old_manifest(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);config,boot=fixture(root)
            new='identity/new-fixed-domain.json';(root/new).write_bytes((root/MANIFEST).read_bytes())
            (root/MANIFEST).unlink()
            def save(path,value):
                raw=json.dumps(value).encode();(root/path).write_bytes(raw);return sha256(raw).hexdigest()
            descriptor=json.loads((root/'descriptor.json').read_bytes())
            descriptor['source_hashes'][new]=descriptor['source_hashes'].pop(MANIFEST)
            config['descriptor']['sha256']=save('descriptor.json',descriptor)
            month=json.loads((root/'month.json').read_bytes());month['original_source_hashes']=descriptor['source_hashes']
            config['initial_month']['sha256']=save('month.json',month)
            config['identity_manifest_path']=new;boot['config_sha256']=save('config.json',config)
            result=run(**boot,execute=True,clock=lambda:NOW,fetch=fetch)
            self.assertEqual(result['status'],'CREATED_ISOLATED_SIMULATION')
            state=SimulationStore(config['database_path']).read(config['simulation_id'])['simulation']
            closed=expire_all(state);args,calls,_=daily_arguments(folder,closed,'2026-10-16')
            original_fetch=args['fetch']
            def full_minutes(ticker):
                raw=json.loads(original_fetch(ticker));chart=raw['chart']['result'][0]
                start=chart['meta']['currentTradingPeriod']['regular']['start']
                end=(chart['meta']['regularMarketTime']+1)//60*60
                chart['timestamp']=list(range(start,end,60));n=len(chart['timestamp'])
                chart['indicators']['quote']=[dict(open=[10]*n,high=[11]*n,low=[9]*n,close=[10]*n,volume=[10]*n)]
                return json.dumps(raw).encode()
            args.update(fetch=full_minutes,unit_review_reader=cash_review,pullback_policy=config['pullback']['policy'],
                pullback_cap_store=LazyPullbackCapStore(Path(config['pullback']['database_path']),clock=lambda:args['clock']().isoformat(),max_history_rows=512,max_history_bytes=128*1024*1024))
            with patch('subprocess.run',side_effect=AssertionError('No next-session research')):
                renewed=apply_continuation(**args)
            ledger=renewed['simulation']['chain']['ledger']
            self.assertEqual(ledger['target_quantities'],closed['chain']['ledger']['target_quantities'])
            self.assertEqual(ledger['cash'],closed['chain']['ledger']['cash'])
            self.assertTrue(ledger['orders']);self.assertEqual(calls,['AAA','BBB'])
            self.assertFalse((root/MANIFEST).exists())


if __name__=='__main__':unittest.main()


