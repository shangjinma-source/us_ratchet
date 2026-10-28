import json
from unittest.mock import patch
from data.news_investment_model_v1 import analyze_review

SOURCE = dict(id='s',text='Material operating loss confirmed.',security_ids=['sid'],content_kind='FULL_TEXT',published_at='2026-10-27T10:00:00Z',observed_at='2026-10-27T10:01:00Z')
POSITION = dict(security_id='sid',ticker='X',original_qty=10,target_qty=12,account_name='PRIVATE',cash=100)
def response(action='REDUCE_HOLDING', buy='0', hold='1/2'):
    return {'rows':[dict(security_id='sid',ticker='X',action=action,reason='risk',counterevidence=['uncertain'],uncertainty=['not certain'],buy_fraction=buy,holding_fraction=hold,evidence=[dict(source_id='s',quote='Material operating loss confirmed.')])]}

import unittest
import tempfile
from pathlib import Path

class ModelAdapterTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.tmp_path=Path(self.folder.name)/'analysis'
        self.tmp_path.mkdir()
        # Adapter tests use an isolated real coordinator with a deterministic
        # elapsed cooldown. Coordinator policy itself has its own tests.
        from data.news_investment_model_v1 import ModelCoordinator
        from datetime import datetime, timezone
        self.coordinator_tick=0
        def coordinator(cache):
            self.coordinator_tick+=61
            instant=datetime.fromtimestamp(1800000000+self.coordinator_tick,timezone.utc)
            return ModelCoordinator(cache,clock=lambda:instant)
        mocked=patch('data.news_investment_model_v1.ModelCoordinator',side_effect=coordinator)
        mocked.start();self.addCleanup(mocked.stop)

    def test_full_input_and_cache_position_binding(self):
        tmp_path=self.tmp_path
        with patch('data.news_investment_model_v1._invoke', return_value=(response(),{'input_tokens':10})) as invoke:
            result=analyze_review([SOURCE],[POSITION],tmp_path)
            assert result['status']=='SUCCEEDED' and result['rows'][0]['evidence'][0]['source_sha256']
            assert 'PRIVATE' not in invoke.call_args.args[0] and '"cash"' not in invoke.call_args.args[0]
            assert analyze_review([SOURCE],[POSITION],tmp_path)['status']=='CACHED'
            assert invoke.call_count==1
            analyze_review([SOURCE],[dict(POSITION,target_qty=15)],tmp_path)
            assert invoke.call_count==2
            assert result['receipt']['finished_at'] and result['receipt']['usage']['input_tokens']==10

    def test_no_body_and_budget_no_call(self):
        tmp_path=self.tmp_path
        with patch('data.news_investment_model_v1._invoke') as invoke:
            assert analyze_review([dict(SOURCE,content_kind='RSS_EXCERPT')],[POSITION],tmp_path)['attempts']==0
            assert analyze_review([dict(SOURCE,text='a'*60000)],[POSITION],tmp_path,max_chars=60000)['status']=='INPUT_BUDGET_EXCEEDED'
            invoke.assert_not_called()

    def test_bad_quote_failed_without_retry(self):
        tmp_path=self.tmp_path
        bad=response();bad['rows'][0]['evidence'][0]['quote']='invented'
        with patch('data.news_investment_model_v1._invoke',return_value=(bad,{'input_tokens':10})) as invoke:
            result=analyze_review([SOURCE],[POSITION],tmp_path)
            assert result['status']=='FAILED' and result['rows']==[]
            assert result['receipt']['usage']=={'input_tokens':10}
            assert analyze_review([SOURCE],[POSITION],tmp_path)['status']=='PREVIOUS_ATTEMPT_NOT_RETRIED'
            assert invoke.call_count==1

    def test_unrelated_source_rejected(self):
        tmp_path=self.tmp_path
        with patch('data.news_investment_model_v1._invoke',return_value=(response(),{})):
            result=analyze_review([dict(SOURCE,security_ids=['other'])],[POSITION],tmp_path)
            assert result['status']=='FAILED' and result['rows']==[]
            assert result['receipt']['error']=='SOURCE_MODEL_UNAVAILABLE_OR_UNVERIFIED'
        from data.news_investment_model_v1 import _project,_validate
        with self.assertRaisesRegex(ValueError,'SOURCE_SECURITY_NOT_BOUND'):
            _validate(response(),_project([dict(SOURCE,security_ids=['other'])],[POSITION])[0])

    def test_exit_allowed_and_invalid_fraction_rejected(self):
        tmp_path=self.tmp_path
        with patch('data.news_investment_model_v1._invoke',return_value=(response('EXIT','0','0'),{})):
            assert analyze_review([SOURCE],[POSITION],tmp_path/'exit')['status']=='SUCCEEDED'
        with patch('data.news_investment_model_v1._invoke',return_value=(response('EXIT','1','0'),{})):
            assert analyze_review([SOURCE],[POSITION],tmp_path/'bad')['status']=='FAILED'

    def test_refresh_observed_time_reuses_cache(self):
        with patch('data.news_investment_model_v1._invoke',return_value=(response(),{})) as invoke:
            first=analyze_review([SOURCE],[POSITION],self.tmp_path)
            second=analyze_review([dict(SOURCE,observed_at='2026-10-27T10:02:00Z')],[POSITION],self.tmp_path)
            self.assertEqual(second['status'],'CACHED')
            self.assertEqual(first['receipt'],second['receipt'])
            saved=json.loads((self.tmp_path/first['cache_key']/'input.json').read_text(encoding='utf-8'))
            self.assertEqual(saved['sources'][0]['observed_at'],SOURCE['observed_at'])
            self.assertEqual(invoke.call_count,1)

    def test_bool_float_string_quantities_rejected(self):
        for value in (True,2.0,'2'):
            with self.assertRaises(ValueError):
                analyze_review([SOURCE],[dict(POSITION,original_qty=value)],self.tmp_path)

    def test_release_excerpt_rejected(self):
        with patch('data.news_investment_model_v1._invoke') as invoke:
            result=analyze_review([dict(SOURCE,content_kind='ISSUER_RELEASE_BODY')],[POSITION],self.tmp_path)
            self.assertEqual(result['attempts'],0)
            invoke.assert_not_called()

    def test_model_output_accepts_core_and_canonical_whitespace(self):
        from core.news_investment_review_v1 import build_review_proposal
        source=dict(SOURCE,text='Material  operating\nloss confirmed.')
        with patch('data.news_investment_model_v1._invoke',return_value=(response(),{})):
            result=analyze_review([source],[POSITION],self.tmp_path)
        self.assertEqual(result['status'],'SUCCEEDED')
        row=result['rows'][0]
        self.assertEqual(row['evidence'][0]['quote'],source['text'])
        from hashlib import sha256
        source['text_sha256']=sha256(source['text'].encode()).hexdigest()
        proposal=build_review_proposal(now='2026-10-27T10:04:00Z',
            account=dict(revision='r',shares={'sid':10},available_cash='100',cash_confirmation_valid=True,orders={}),
            original_preview=dict(status='READY',account_revision='r',target_id='t',proposal_id='p',effective_target_quantities={'sid':12},risk_valid_from='2026-10-27T10:00:00Z',risk_valid_until='2026-10-27T10:10:00Z'),
            sources={'s':source},review=dict(schema='NEWS_INVESTMENT_REVIEW_V1',review_id='x',account_revision='r',target_id='t',proposal_id='p',created_at='2026-10-27T10:03:00Z',valid_until='2026-10-27T10:08:00Z',rows=result['rows']))
        self.assertEqual(proposal['rows'][0]['proposed_target_quantity'],5)
        self.assertFalse(proposal['executable'])

    def test_invoke_inherits_windows_proxy(self):
        from data.news_investment_model_v1 import _invoke
        def process(args, **kwargs):
            self.assertEqual(kwargs['env']['HTTPS_PROXY'],'http://local-test:9000')
            Path(args[args.index('--output-last-message')+1]).write_text(json.dumps(response()))
            from unittest.mock import Mock
            child=Mock(returncode=0)
            child.communicate.return_value=(json.dumps({'type':'turn.completed','usage':{'input_tokens':1}})+'\n','')
            return child
        with patch('data.news_investment_model_v1.shutil.which',return_value='codex'), patch('data.news_investment_model_v1.getproxies',return_value={'https':'http://local-test:9000'}), patch.dict('os.environ',{},clear=True), patch('data.news_investment_model_v1.subprocess.Popen',side_effect=process):
            answer,usage=_invoke('prompt',self.tmp_path,120)
            self.assertEqual(usage['input_tokens'],1)

if __name__=='__main__':unittest.main()
