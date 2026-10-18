from copy import deepcopy
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from test_current_quantity_portfolio_research_v2 import fixture
from data.current_quantity_portfolio_research_v2 import CurrentQuantityPortfolioResearchV2
from data.current_cash_portfolio_research import ResearchExpiredError


class PrivateDecisionTests(unittest.TestCase):
    def test_real_tiny_isolated_worker_once_private_reads_no_search(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);_,_,descriptor=fixture(root)
            service=CurrentQuantityPortfolioResearchV2(root=root,source_loader=lambda:deepcopy(descriptor))
            real_run=subprocess.run
            with patch('data.current_quantity_portfolio_research_v2.subprocess.run',wraps=real_run) as worker:
                with self.assertRaises(ResearchExpiredError):service.decision('0'*24)
                self.assertEqual(worker.call_count,0)
                view=service.calculate('100');rid=view['research_id']
                decision=service.decision(rid);original=deepcopy(decision)
                self.assertEqual(decision['target_quantities'],view['target_quantities'])
                self.assertEqual(decision['binding']['shares'],{})
                self.assertEqual(decision['binding']['search_arguments']['entered_cash'],'100')
                decision['binding']['search_arguments']['prices'].clear()
                decision['search_result']['selected']['quantities'].clear()
                self.assertEqual(service.decision(rid),original)
                self.assertTrue(service.calculate('100')['cache_hit'])
                self.assertEqual(worker.call_count,1)
                (root/'B.json').write_bytes(b'source drift')
                with self.assertRaisesRegex(ValueError,'HASH_MISMATCH'):service.decision(rid)
                self.assertEqual(worker.call_count,1)
                service.snapshots.pop(rid)
                with self.assertRaises(ResearchExpiredError):service.decision(rid)
                self.assertEqual(worker.call_count,1)


if __name__=='__main__':unittest.main()
