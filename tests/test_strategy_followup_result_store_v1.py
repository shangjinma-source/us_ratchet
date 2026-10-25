from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from data.strategy_followup_result_store_v1 import publish,read_observation


class ResultStoreTests(TestCase):
    def fixture(self):
        sources={'daily':b'daily','official':b'official'}
        row=dict(observation_id='a'*64,status='CONDITIONAL_PRICE_OBSERVATION',actual_fill_inferred=False,performance_computed=False,
            daily_sha256=sha256(sources['daily']).hexdigest(),official_sha256=sha256(sources['official']).hexdigest(),closing_price='100')
        return row,sources
    def test_readback_and_duplicate_publication(self):
        with TemporaryDirectory() as d:
            row,sources=self.fixture();first=publish(d,rows=[row],sources=sources)
            self.assertEqual(publish(d,rows=[row],sources=sources),first)
            self.assertEqual(read_observation(d,row['observation_id']),row)
    def test_price_conflict_cannot_overwrite(self):
        with TemporaryDirectory() as d:
            row,sources=self.fixture();publish(d,rows=[row],sources=sources)
            with self.assertRaisesRegex(ValueError,'ALREADY_PUBLISHED'):publish(d,rows=[dict(row,closing_price='99')],sources=sources)
            self.assertEqual(read_observation(d,row['observation_id'])['closing_price'],'100')
    def test_corrupt_source_and_missing_completion_rejected(self):
        with TemporaryDirectory() as d:
            row,sources=self.fixture();result=publish(d,rows=[row],sources=sources)
            source=Path(d)/'sources'/(row['daily_sha256']+'.bin');source.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'SOURCE_CHANGED'):read_observation(d,row['observation_id'])
            source.write_bytes(b'daily');(Path(d)/'bundles'/result['manifest_sha256']/'complete.json').unlink()
            with self.assertRaises(FileNotFoundError):read_observation(d,row['observation_id'])
