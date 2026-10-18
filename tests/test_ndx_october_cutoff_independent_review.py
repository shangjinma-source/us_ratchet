import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_october_cutoff_snapshot_independent_readback_20260923 as m
from test_ndx_october_cutoff_snapshot_independent_readback_20260923 import fixture


class OctoberReview(unittest.TestCase):
    def test_actual_denominator_wrong_queue_seed_and_type(self):
        q = json.loads(m.QUEUE.read_bytes())
        flags = dict.fromkeys(m.FLAGS, False)
        index = dict(schema='CORRECTED_CUTOFF_SNAPSHOT_COMPLETION_INDEX_V1',
            queue=dict(path=str(m.QUEUE), sha256=m.QUEUE_SHA), seed=None, planned=425,
            completed=[], status='PARTIAL', finalization=dict(
                schema='CORRECTED_CUTOFF_SNAPSHOT_FINALIZATION_V1', planned=425,
                completed=0, status='PARTIAL', **flags), **flags)
        self.assertEqual(len(m.validate_index(index, q)), 425)
        for defect in ('queue', 'seed', 'type'):
            bad = copy.deepcopy(index)
            if defect == 'queue': bad['queue'] = dict(path=str(m.may.QUEUE), sha256=m.may.QUEUE_SHA)
            if defect == 'seed': bad['seed'] = {}
            if defect == 'type': bad['finalization']['completed'] = False
            with self.subTest(defect=defect), self.assertRaises(ValueError):
                m.validate_index(bad, q)

    def test_success_payload_and_original_source_closure(self):
        with patch.object(m, 'PLANNED', 104), patch.object(m, 'QUEUE_SHA', '1'*64):
            for defect in ('null', 'numerical', 'attempt', 'future'):
                q,i,v,a = fixture()
                candidates = m.validate_index(i,q)
                m.validate_task(v,a,q,i,candidates)
                if defect == 'null': v['result']['refit'] = None
                if defect == 'numerical': v['result']['refit']['source_hashes'].pop(next(iter(v['result']['refit']['source_hashes'])))
                if defect == 'attempt': a['runner_source_hashes'] = {}
                if defect == 'future': v['result']['historical_cutoff'] = '2023-10-02'
                with self.subTest(defect=defect), self.assertRaises(ValueError):
                    m.validate_task(v,a,q,i,candidates)

    def test_publish_rejects_repartitioned_deleted_source_and_scope(self):
        original = dict(index=dict(path='external-index', sha256='a'*64),
            historical_expected_source_hashes={'required-source': 'b'*64},
            archive_resolution={'original': True}, promotion_allowed=False, completed=1)
        with tempfile.TemporaryDirectory() as directory, patch.object(m, 'build', return_value=original), patch.object(m, 'publish') as publish:
            for defect in ('sources','permission','count'):
                changed = copy.deepcopy(original)
                if defect == 'sources':
                    changed['historical_expected_source_hashes'] = {}
                    changed['archive_resolution'] = {'re_signed': True}
                if defect == 'permission': changed['promotion_allowed'] = 0
                if defect == 'count': changed['completed'] = True
                with self.subTest(defect=defect), self.assertRaises(ValueError):
                    m.publish_verified(Path(directory)/'audit.json', changed)
            publish.assert_not_called()


if __name__ == '__main__': unittest.main()
