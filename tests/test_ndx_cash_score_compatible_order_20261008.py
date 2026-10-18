from copy import deepcopy
from fractions import Fraction
import unittest
from backtest import ndx_cash_neighbor_combined_stream_selection_research as frozen
from backtest import ndx_cash_neighbor_combined_stream_selection_v2_research as compatible
from scripts import ndx_cash_neighbor_combined_selection_independent_readback_v2_20261008 as reader
from test_ndx_cash_neighbor_combined_selection_20261008 import combined,fixture

class Tests(unittest.TestCase):
    def test_string_old_int_new_exact_same_choice_and_saved_representation(self):
        base=combined(fixture());oldrows=[];expected=frozen.select_scenario_stream(**base,emit_ledger_row=lambda r:oldrows.append(r))
        changed=deepcopy(base)
        for saved in changed['previous_row']['feasible_scores']:
            for field in ('distance','fees_usd'):
                saved[field]={key:str(value)for key,value in saved[field].items()}
        rows=[];actual=compatible.select_scenario_stream(**changed,emit_ledger_row=lambda r:rows.append(r))
        self.assertEqual(actual['selected']['identity'],expected['selected']['identity'])
        self.assertEqual(actual['status'],expected['status'])
        self.assertEqual(len(rows),len(oldrows))
        for row,old in zip(rows,oldrows):
            self.assertEqual(row['identity'],old['identity'])
            if row['feasible']:
                for field in ('distance','fees_usd'):
                    self.assertEqual(reader.ratio(row['saved_score'][field]),frozen.ratio(old['saved_score'][field]))
                if row['origin']=='OLD':self.assertIs(type(row['saved_score']['distance']['numerator']),str)

if __name__=='__main__':unittest.main()
