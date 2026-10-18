import unittest
from unittest.mock import patch
from scripts import ndx_dynamic_training_context as loader


class TrainingContextTests(unittest.TestCase):
    def test_context_identity_required(self):
        for value in ('', '../context', None, 'a'*63):
            with self.subTest(value=value), self.assertRaises(ValueError):
                loader.load_context(value)

    def test_real_context_keeps_failed_rows(self):
        restored = loader.load_context('d0f08030cfda7261a6d51823f252a76a5f66904476230e50862f0c337dbbb6f7')
        summary = restored['summary']
        self.assertEqual(summary['planned'], 110)
        self.assertEqual(summary['evaluated'], 110)
        self.assertEqual(summary['declared_failure_rows_retained'], 107)
        self.assertEqual(summary['training_cutoff'], '2024-01-31')
        self.assertFalse(summary['portfolio_selected'])
        self.assertFalse(summary['promotion_allowed'])
        self.assertTrue(all(row['saved_weights_role']=='LAST_HISTORICAL_FIT_NOT_CURRENT_TARGET'
                            for row in restored['records']))

    def test_loaded_source_change_rejected(self):
        with patch.object(loader, '_LOADED', '0'*64):
            with self.assertRaisesRegex(ValueError, 'source changed'):
                loader.load_context('d0f08030cfda7261a6d51823f252a76a5f66904476230e50862f0c337dbbb6f7')


if __name__ == '__main__':
    unittest.main()
