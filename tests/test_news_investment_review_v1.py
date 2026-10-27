import unittest
from copy import deepcopy
from hashlib import sha256
from core.news_investment_review_v1 import build_review_proposal

class InvestmentReviewTests(unittest.TestCase):
    def fixture(self,action='KEEP',target=10):
        text='Verified company announcement.';digest=sha256(text.encode()).hexdigest()
        return dict(now='2026-10-27T15:01:00Z',
          account=dict(revision='r',shares={'A':4},available_cash='100',cash_confirmation_valid=True,orders={}),
          original_preview=dict(status='READY',account_revision='r',target_id='t',proposal_id='p',effective_target_quantities={'A':target},risk_valid_from='2026-10-27T15:00:00Z',risk_valid_until='2026-10-27T15:10:00Z'),
          sources={'s':dict(content_kind='FULL_TEXT',security_ids=['A'],text=text,text_sha256=digest,published_at='2026-10-27T14:00:00Z',observed_at='2026-10-27T14:01:00Z')},
          review=dict(schema='NEWS_INVESTMENT_REVIEW_V1',review_id='review',account_revision='r',target_id='t',proposal_id='p',created_at='2026-10-27T15:00:00Z',valid_until='2026-10-27T15:05:00Z',rows=[dict(security_id='A',action=action,reason='Source-bound opinion',evidence=[dict(source_id='s',source_sha256=digest,quote=text)],buy_fraction='1/2',holding_fraction='1/2')]))

    def test_actions_nonexecuting_and_inputs_unchanged(self):
        for action,target in [('KEEP',10),('PAUSE_BUY',4),('REDUCE_BUY',7),('REDUCE_HOLDING',2),('EXIT',0),('ABSTAIN',10)]:
            args=self.fixture(action);before=deepcopy(args);result=build_review_proposal(**args)
            self.assertEqual(result['rows'][0]['proposed_target_quantity'],target)
            self.assertFalse(result['executable']);self.assertNotIn('new_orders',result)
            self.assertEqual(args,before)

    def test_original_sell_never_suppressed(self):
        for action in ('KEEP','PAUSE_BUY','REDUCE_BUY','REDUCE_HOLDING','EXIT','ABSTAIN'):
            self.assertLessEqual(build_review_proposal(**self.fixture(action,target=1))['rows'][0]['proposed_target_quantity'],1)

    def test_missing_quote_wrong_security_and_changed_source_reject(self):
        for change in ('quote','security','hash'):
            args=self.fixture()
            if change=='quote':args['review']['rows'][0]['evidence'][0]['quote']='invented'
            if change=='security':args['sources']['s']['security_ids']=['B']
            if change=='hash':args['sources']['s']['text']='changed'
            with self.assertRaises(ValueError):build_review_proposal(**args)

    def test_stale_binding_source_future_and_expired_risk_reject(self):
        for change in ('binding','future','risk','review'):
            args=self.fixture()
            if change=='binding':args['account']['revision']='new'
            if change=='future':args['sources']['s']['observed_at']='2026-10-27T15:02:00Z'
            if change=='risk':args['original_preview']['risk_valid_until']=args['now']
            if change=='review':args['review']['valid_until']=args['now']
            with self.assertRaises(ValueError):build_review_proposal(**args)

    def test_open_orders_cash_and_integer_guards(self):
        args=self.fixture();args['account']['orders']={'o':{'status':'OPEN'}}
        result=build_review_proposal(**args)
        self.assertEqual(result['status'],'WAIT_RECONCILIATION');self.assertEqual(result['rows'],[])
        args=self.fixture();args['account']['cash_confirmation_valid']=False
        with self.assertRaises(ValueError):build_review_proposal(**args)
        args=self.fixture();args['account']['shares']['A']=True
        with self.assertRaises(ValueError):build_review_proposal(**args)

    def test_abstain_without_evidence_not_approval(self):
        args=self.fixture('ABSTAIN');args['review']['rows'][0]['evidence']=[]
        self.assertFalse(build_review_proposal(**args)['rows'][0]['reviewed'])
        args['review']['rows'][0]['action']='EXIT'
        with self.assertRaises(ValueError):build_review_proposal(**args)

if __name__=='__main__':unittest.main()
