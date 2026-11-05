import unittest
from tempfile import TemporaryDirectory
from docs.candidates.news_investment_service_context_validation_20261106 import NewsInvestmentService

class ContextValidationTests(unittest.TestCase):
    def test_dedup_preserves_fresh_validation_and_binding(self):
        calls=[]; changed=[False]; revision=['r']
        def validate():
            calls.append('validate')
            if changed[0]: raise ValueError('SOURCE_CHANGED')
        def context():
            validate()
            return {'revision':revision[0]}, {'target_id':'t','proposal_id':'p'}, {}
        with TemporaryDirectory() as cache:
            service=NewsInvestmentService(cache=cache,context=context,preview=lambda:None,validate=validate,context_validates_sources=True)
            binding=dict(expected_revision='r',target_id='t',expected_proposal_id='p')
            service.bound_context(binding)
            self.assertEqual(len(calls),1)
            service.bound_context(binding)
            self.assertEqual(len(calls),2)
            changed[0]=True
            with self.assertRaisesRegex(ValueError,'SOURCE_CHANGED'):service.bound_context(binding)
            changed[0]=False; revision[0]='changed'
            with self.assertRaisesRegex(ValueError,'STALE_ACCOUNT_OR_TARGET'):service.bound_context(binding)
            service.context_validates_sources=False;revision[0]='r';calls.clear()
            service.bound_context(binding)
            self.assertEqual(len(calls),2)
if __name__=='__main__': unittest.main()


class RealCompositionTests(unittest.TestCase):
    def test_real_compose_checks_inside_snapshot_and_rereads(self):
        from contextlib import contextmanager
        from types import SimpleNamespace
        from unittest.mock import patch
        from pathlib import Path
        from docs.candidates import news_investment_composition_context_validation_20261106 as composition
        depth=[0]; checks=[]; changed=[False]; revision=['r']; captured=[]
        @contextmanager
        def operation():
            depth[0]+=1
            try: yield
            finally: depth[0]-=1
        def validate():
            checks.append(depth[0])
            if changed[0]: raise ValueError('SOURCE_CHANGED')
        def read_account():return {'revision':revision[0],'events':[]}
        def current():return {'target_id':'t','proposal_id':'p','payload':{'decision':{'payload':{'input_binding':{'search_arguments':{'metadata':{}}}}}}}
        monthly=SimpleNamespace(snapshot_operation=operation,accounts=SimpleNamespace(read=read_account),current=current)
        observed=SimpleNamespace(preview=lambda **kwargs:None,service=SimpleNamespace(reader=None))
        def constructor(**kwargs):
            service=NewsInvestmentService(**kwargs);captured.append(service);return service
        with TemporaryDirectory() as folder, patch.object(composition,'NewsInvestmentService',side_effect=constructor), patch('data.news_risk_skill_v1.load_risk_skill',return_value={'binding':{}}), patch('data.news_risk_skill_v1.require_risk_skill'):
            composition.compose(root=Path(folder),monthly_view=monthly,observed_daily=observed,validate=validate)
            service=captured[0];checks.clear()
            binding=dict(expected_revision='r',target_id='t',expected_proposal_id='p')
            service.bound_context(binding)
            self.assertEqual(checks,[1])
            changed[0]=True
            with self.assertRaisesRegex(ValueError,'SOURCE_CHANGED'):service.bound_context(binding)
            self.assertEqual(depth[0],0)
            changed[0]=False;revision[0]='new'
            with self.assertRaisesRegex(ValueError,'STALE_ACCOUNT_OR_TARGET'):service.bound_context(binding)

    def test_default_unvalidated_context_still_validates(self):
        calls=[]
        with TemporaryDirectory() as folder:
            service=NewsInvestmentService(cache=folder,context=lambda:({'revision':'r'},{'target_id':'t','proposal_id':'p'},{}),preview=lambda:None,validate=lambda:calls.append(1))
            service.bound_context(dict(expected_revision='r',target_id='t',expected_proposal_id='p'))
            self.assertEqual(calls,[1])
