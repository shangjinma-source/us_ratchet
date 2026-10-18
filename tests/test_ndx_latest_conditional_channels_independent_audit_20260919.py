import copy
import unittest
from pathlib import Path

from scripts import ndx_latest_conditional_channels_independent_audit_20260919 as audit


class BatchReaderTests(unittest.TestCase):
    def make_index(self):
        folder = Path('channel_test_output').resolve()
        tasks = [dict(ticker='T' + str(i)) for i in range(101)]
        entries = [dict(ticker=t['ticker'], path=str(folder / (t['ticker'] + '.json')),
                        sha256='a' * 64, started_sha256='b' * 64) for t in tasks]
        index = dict(schema='LATEST_CHANNEL_INDEX_V1', plan_sha256='c' * 64,
                     output_directory=str(folder), planned=101, completed=101, status='COMPLETE',
                     entries=entries, **dict.fromkeys(audit.recipe.FALSE, False))
        return index, folder, tasks

    def test_complete_typed_denominator_and_no_partial_prefix(self):
        index, folder, tasks = self.make_index()
        audit.validate_index(index, 'c' * 64, folder, tasks)
        variants = []
        for key, value in (('completed', 101.0), ('status', 'PARTIAL'), ('promotion_allowed', 0)):
            changed = copy.deepcopy(index); changed[key] = value; variants.append(changed)
        changed = copy.deepcopy(index); changed['entries'].pop(); variants.append(changed)
        changed = copy.deepcopy(index); changed['entries'][1] = changed['entries'][0]; variants.append(changed)
        for changed in variants:
            with self.assertRaises(ValueError):
                audit.validate_index(changed, 'c' * 64, folder, tasks)

    def test_blocked_cannot_acquire_output_and_false_is_not_zero(self):
        task = dict(ticker='TRI', mode='BLOCKED', reason='NO_CONDITIONAL_PRICE_REFERENCE')
        value = dict(schema='LATEST_CONDITIONAL_CHANNEL_TASK_V1', plan_sha256='c', task=task,
                     status='BLOCKED', result=None, **dict.fromkeys(audit.recipe.FALSE, False))
        audit.validate_wrapper(value, task, 'c')
        for key, change in (('result', {}), ('fit_performed', 0), ('status', 'CONDITIONAL_NUMERIC_RESULT')):
            changed = copy.deepcopy(value); changed[key] = change
            with self.assertRaises(ValueError):
                audit.validate_wrapper(changed, task, 'c')

    def test_extra_authorization_or_wrong_result_address_reject(self):
        index, folder, tasks = self.make_index()
        index['entries'][0]['path'] = str(folder.parent / 'elsewhere.json')
        with self.assertRaises(ValueError):
            audit.validate_index(index, 'c' * 64, folder, tasks)
        index, folder, tasks = self.make_index(); index['search_admission_allowed'] = True
        with self.assertRaises(ValueError):
            audit.validate_index(index, 'c' * 64, folder, tasks)


if __name__ == '__main__':
    unittest.main()
