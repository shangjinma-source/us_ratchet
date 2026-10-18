import json
import unittest
from unittest.mock import patch
from scripts import ndx_new_cutoff_nav_snapshot_20260923 as module


def frozen_input(name):
    # Replay the exact original bytes preserved by the sealed snapshot.
    raw = (module.ROOT / 'data/cache/research/new_cutoff_nav_snapshot_20260923_v1' / name).read_bytes()
    if module.digest(raw) != module.INPUTS[name][1]:
        raise ValueError('Frozen NAV fixture differs from original input SHA')
    return raw


class SnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw=frozen_input('nav.csv')
        cls.metadata=frozen_input('original_manifest.json')

    def test_real_bytes_are_observations_without_calendar_mapping(self):
        result=module.validate(self.raw,self.metadata)
        self.assertEqual(result['row_count'],1101)
        self.assertEqual(result['data_end'],'2026-09-21')
        self.assertFalse(result['source_pagination_independently_reverified'])

    def test_wrong_identity_counts_publication_and_nonfinite_rejected(self):
        for attack in ('identity','count','publication','nonfinite','duplicate_date'):
            raw=self.raw;metadata=json.loads(self.metadata)
            if attack=='identity':metadata['fund_code']='000000'
            if attack=='count':metadata['row_count']=True
            if attack=='publication':metadata['publication_time_known']=True
            if attack=='nonfinite':raw=raw.replace(b'2022-01-11,1.0,1.0,,1.0',b'2022-01-11,NaN,1.0,,NaN')
            if attack=='duplicate_date':
                lines=raw.splitlines();second_date=lines[2].split(b',')[0]
                raw=raw.replace(second_date+b',',lines[1].split(b',')[0]+b',',1)
                self.assertNotEqual(raw,self.raw)
            metadata.update(content_sha256=module.digest(raw),content_bytes=len(raw))
            with self.subTest(attack=attack),self.assertRaises(ValueError):module.validate(raw,json.dumps(metadata).encode())

    def test_source_drift_or_existing_namespace_never_writes(self):
        with patch.object(module.Path,'exists',return_value=False),patch.object(module,'guard',side_effect=ValueError('drift')),\
                patch.object(module,'publish_bytes') as publish:
            with self.assertRaises(ValueError):module.run()
            publish.assert_not_called()
        with patch.object(module.Path,'exists',return_value=True),patch.object(module,'guard') as guard:
            with self.assertRaises(ValueError):module.run()
            guard.assert_not_called()


if __name__=='__main__':unittest.main()
