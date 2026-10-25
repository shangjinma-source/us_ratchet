"""Reuse journal safeguards and exercise release scope boundaries."""
from contextlib import contextmanager
from copy import deepcopy
import tempfile
from data.strategy_observed_daily_admission_v2 import ScopedObservedDailyAdmission
from test_daily_advice_journal_v1 import AdviceTests


class ScopedAdviceTests(AdviceTests):
    def setup_case(self, folder):
        old,journal,clock,response=super().setup_case(folder)
        monthly=old.monthly
        monthly.release={'revision':1,'archive_sha256':'a'}
        monthly.depth=0
        monthly.provider_reads=0
        @contextmanager
        def scope():
            if monthly.depth==0:
                monthly.provider_reads+=1
                monthly.current_release=deepcopy(monthly.release)
            monthly.depth+=1
            try:
                yield monthly.current_release
            finally:
                monthly.depth-=1
        monthly.snapshot_operation=scope
        current=monthly.current
        def scoped_current():
            with scope():return current()
        monthly.current=scoped_current
        service=old.service
        preview=service.preview
        def scoped_preview(**kwargs):
            with scope():return preview(**kwargs)
        service.preview=scoped_preview
        wrapper=ScopedObservedDailyAdmission(service=service,monthly=monthly,journal=journal,
            clock=old.clock,validate_sources=old.validate_sources,policy_references=old.policy_references)
        return wrapper,journal,clock,response

    def test_generation_reuses_scope_and_final_checks_reopen(self):
        with tempfile.TemporaryDirectory() as folder:
            wrapper,journal,clock,response=self.setup_case(folder)
            self.assertEqual(wrapper.preview(expected_revision='revision',target_id='target')['status'],'READY')
            self.assertEqual(wrapper.monthly.provider_reads,3)
            self.assertEqual(wrapper.monthly.depth,0)
            wrapper.preview(expected_revision='revision',target_id='target')
            self.assertEqual(wrapper.monthly.provider_reads,6,'No cross-request cache')

    def test_mutations_during_both_journal_stages_retire_orders(self):
        for stage in ('append','record_return'):
            for change in ('release','account','target'):
                with self.subTest(stage=stage,change=change),tempfile.TemporaryDirectory() as folder:
                    wrapper,journal,clock,response=self.setup_case(folder)
                    original=getattr(journal,stage)
                    def mutate(*args,**kwargs):
                        value=original(*args,**kwargs)
                        if change=='release':wrapper.monthly.release['revision']=2
                        if change=='account':wrapper.monthly.accounts.read=lambda:{'account_id':'account','revision':'changed'}
                        if change=='target':wrapper.monthly.current=lambda:{'target_id':'changed'}
                        return value
                    setattr(journal,stage,mutate)
                    result=wrapper.preview(expected_revision='revision',target_id='target')
                    self.assertEqual(result['status'],'WAIT')
                    self.assertEqual(result['new_orders'],[])
                    self.assertEqual(result['reference_quotes'],{})
                    self.assertEqual(wrapper.monthly.depth,0)

    def test_generation_failure_releases_scope(self):
        with tempfile.TemporaryDirectory() as folder:
            wrapper,journal,clock,response=self.setup_case(folder)
            wrapper.service.preview=lambda **kwargs:(_ for _ in ()).throw(ValueError('GENERATE_FAILED'))
            with self.assertRaisesRegex(ValueError,'GENERATE_FAILED'):
                wrapper.preview(expected_revision='revision',target_id='target')
            self.assertEqual(wrapper.monthly.depth,0)
