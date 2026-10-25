from copy import deepcopy
import json
from tempfile import TemporaryDirectory
import unittest
from prospective_paper_v2_fixture import fixture
from data.strategy_prospective_paper_selection_v2 import prospective_target_training_context


class TargetTrainingContextTests(unittest.TestCase):
    def test_context_is_reconstructed_from_verified_saved_selection(self):
        with TemporaryDirectory() as folder:
            daily=fixture(folder)
            args=daily['selection_arguments']
            context=prospective_target_training_context(selection_result=daily['selection_result'],selection_arguments=args)
            review=json.loads(args['source_package']['files'][args['unit_review_path']])
            self.assertEqual(context['training_manifest_sha256'],review['training_manifest_sha256'])
            self.assertEqual(context['training_closed_at'],review['training_closed_at'])
            corrupted=deepcopy(daily['selection_result'])
            corrupted['payload']['input_binding']['historical_search_arguments']['decision_date']='2020-01-01'
            with self.assertRaises(ValueError):
                prospective_target_training_context(selection_result=corrupted,selection_arguments=args)


if __name__=='__main__':unittest.main()
