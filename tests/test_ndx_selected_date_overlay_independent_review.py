from copy import deepcopy
import unittest
import test_ndx_selected_date_overlay_research as fixture
from backtest import ndx_selected_date_overlay_research as core
from scripts import ndx_selected_date_overlay_research as reader


class IndependentReview(unittest.TestCase):
    def test_new_non20_result_is_preserved_not_old_risk_spliced(self):
        args=fixture.SelectedDateTests().bundle()
        for row in args['replacements']:
            row['original_result']['risk_pass']=True
            row['result']['risk_pass']=False
            row['original_result']['whole_lot_return']=100
            row['result']['whole_lot_return']=-.5
        result=core.extend_selected_date(**args)
        for record in result['records'][:2]:
            self.assertIs(record['result']['risk_pass'],False)
            self.assertEqual(record['result']['whole_lot_return'],-.5)
        self.assertFalse(result['saved_non20_fields_independently_recomputed'])
        self.assertIsNone(result['winner'])

    def test_duplicate_parent_and_duplicate_replacement_reject(self):
        for mutation in ('parent','replacement'):
            args=fixture.SelectedDateTests().bundle()
            if mutation=='parent':args['parent']['records'].append(deepcopy(args['parent']['records'][0]))
            else:args['replacements'].append(deepcopy(args['replacements'][0]))
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):core.extend_selected_date(**args)

    def test_audit_boolean_or_nonfinite_error_cannot_certify_date(self):
        for value in (True,float('nan'),float('inf'),-.1):
            index,audit,manifest=fixture.SelectedDateTests().prefix()
            audit['tasks'][0]['all_windows_max_error']=value
            with self.subTest(value=value),self.assertRaises(ValueError):reader.complete_date_rows(index,audit,manifest,'2023-04-03')


if __name__=='__main__':unittest.main()
