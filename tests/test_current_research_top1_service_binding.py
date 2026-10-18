from copy import deepcopy
import unittest
from unittest.mock import patch
import data.current_research_snapshot_resolver as resolver
from data.current_cash_portfolio_research import ResearchExpiredError
from data.current_research_paper_service import TOP1_RESEARCH_VERSION, TOP1_METHOD
from test_current_research_paper_service import PaperServiceTests


class Top1BindingTests(PaperServiceTests):
    def test_top1_preview_method_month_and_allcash_without_db(self):
        self.snap.update(research_version=TOP1_RESEARCH_VERSION,method=TOP1_METHOD)
        result=self.service.preview('a'*24)
        snapshot=result['plan']['causal_inputs']['research_snapshot']
        self.assertEqual(snapshot['selection_method'],TOP1_METHOD)
        self.assertEqual(snapshot['target_month'],'2026-10')
        self.assertEqual(result['plan']['strategy_version'],'PAPER_FROZEN_TOP1_V1')
        self.assertFalse((self.root/'paper').exists())
        self.snap.update(status='ALL_CASH',stocks=[])
        cash=self.service.preview('a'*24)
        self.assertEqual(cash['plan']['orders'],[])
        self.assertEqual(cash['plan']['available_cash'],'105')


class ResolverTests(unittest.TestCase):
    def test_known_new_old_unknown_and_source_failure(self):
        rid='a'*24
        with patch.object(resolver,'read_current_top1_research_snapshot',return_value={'research_id':rid}), patch.object(resolver,'read_current_quantity_research_snapshot') as old:
            self.assertEqual(resolver.read_known_research_snapshot(rid)['research_id'],rid);old.assert_not_called()
        with patch.object(resolver,'read_current_top1_research_snapshot',side_effect=ResearchExpiredError('missing')), patch.object(resolver,'read_current_quantity_research_snapshot',return_value={'research_id':rid}):
            self.assertEqual(resolver.read_known_research_snapshot(rid)['research_id'],rid)
        with patch.object(resolver,'read_current_top1_research_snapshot',side_effect=ResearchExpiredError('missing')), patch.object(resolver,'read_current_quantity_research_snapshot',side_effect=ResearchExpiredError('unknown')):
            with self.assertRaises(ResearchExpiredError):resolver.read_known_research_snapshot(rid)
        with patch.object(resolver,'read_current_top1_research_snapshot',side_effect=ValueError('source changed')), patch.object(resolver,'read_current_quantity_research_snapshot') as old:
            with self.assertRaisesRegex(ValueError,'source changed'):resolver.read_known_research_snapshot(rid)
            old.assert_not_called()
