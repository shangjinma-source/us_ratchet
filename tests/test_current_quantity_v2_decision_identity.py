from copy import deepcopy
from pathlib import Path
from fractions import Fraction
from tempfile import TemporaryDirectory
import unittest
from test_current_quantity_portfolio_research_v2 import fixture
from data.current_quantity_portfolio_research_v2 import CurrentQuantityPortfolioResearchV2
from data.current_cash_portfolio_research import ResearchExpiredError


class DecisionIdentityTests(unittest.TestCase):
    def test_tiny_isolated_cash_ids_cache_and_snapshot(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);_,_,descriptor=fixture(root)
            service=CurrentQuantityPortfolioResearchV2(root=root,source_loader=lambda:deepcopy(descriptor))
            a=service.calculate('60');b=service.calculate('100')
            self.assertNotEqual(a['decision_id'],b['decision_id'])
            for result in (a,b):
                rid=result['research_id'];identifier=result['decision_id']
                self.assertEqual(len(identifier),64);self.assertEqual(identifier[:24],rid)
                self.assertEqual(service.snapshot(rid)['decision_id'],identifier)
                self.assertEqual(service.decision(rid)['decision_id'],identifier)
                decision=service.decision(rid)
                expected={sid:str(q*Fraction(decision['binding']['search_arguments']['prices'][sid]))
                          for sid,q in decision['target_quantities'].items() if q>0}
                self.assertEqual(result['frozen_dollar_allocations_exact'],expected)
                self.assertEqual(service.snapshot(rid)['frozen_dollar_allocations_exact'],expected)
            cached=service.calculate('100.00')
            self.assertEqual(cached['decision_id'],b['decision_id']);self.assertEqual(cached['generator_calls_this_request'],0)
            with self.assertRaises(ResearchExpiredError):service.snapshot('0'*24)
            (root/'A.json').write_bytes(b'drift')
            with self.assertRaises(ValueError):service.snapshot(b['research_id'])
            with self.assertRaises(ValueError):service.decision(b['research_id'])


if __name__=='__main__':unittest.main()
