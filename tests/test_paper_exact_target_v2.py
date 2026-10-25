"""Exact arithmetic parity plus the existing independent exhaustive checks."""
from copy import deepcopy
from random import Random
from unittest.mock import patch
import unittest
import test_return_priority_fresh_cash_quantity_search_v2 as legacy
from backtest.paper_exact_integer_quantity_search_v2 import search_fresh_cash_quantities
from backtest.return_priority_fresh_cash_quantity_search_v2 import search_fresh_cash_quantities as reference
from data.strategy_paper_exact_target_v2 import select_target_core
from data.strategy_paper_target_common_v1 import select_target_core as reference_target


class ExactArithmeticCoverageTests(legacy.CoverageV2Tests):
    def setUp(self):
        patcher=patch.object(legacy,'search_fresh_cash_quantities',search_fresh_cash_quantities)
        patcher.start();self.addCleanup(patcher.stop)

    def test_full_search_parity_with_fees_buffers_and_shared_issuer(self):
        random=Random(20261024)
        for index in range(24):
            args=legacy.inputs()
            args['prices']={sid:f'{random.randint(1,20)}/{random.randint(1,7)}' for sid in 'ABC'}
            args['entered_cash']=str(random.randint(4,30))
            args['fee_bps']=str(random.choice([0,7,35,99]))
            args['minimum_cash_buffer']=str(random.randint(0,4))
            args['training_scenarios']=[{sid:f'{random.randint(1,30)}/{random.randint(1,13)}'
                for sid in 'ABC'} for unused in range(2)]
            if index%3==0:args['metadata']['B']['issuer_id']='A'
            with self.subTest(index=index):
                self.assertEqual(reference(**deepcopy(args)),search_fresh_cash_quantities(**deepcopy(args)))

    def test_paper_adapter_preserves_full_payload_and_identity(self):
        for budget in (1,400):
            args=legacy.inputs();args['max_objective_evaluations']=budget
            inputs=dict(input_id='synthetic-input',binding=dict(valuation_date='2026-01-02',search_arguments=args))
            self.assertEqual(select_target_core(deepcopy(inputs),scope='TEST'),
                             reference_target(deepcopy(inputs),scope='TEST'))


if __name__=='__main__':unittest.main()
