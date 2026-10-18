from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from scripts.monthly_experimental_domain_capture import prepare, run, SCHEMA
from scripts.prepare_monthly_captured_training import build
from test_prepare_monthly_captured_training import fixture as preparation_fixture


def fixture(folder):
    args=preparation_fixture(folder);root=args['root'];old=json.loads((root/'previous.json').read_bytes())
    old['candidates']=old['candidates'][:1];row=old['candidates'][0];old['members']=[row['ticker']]
    old['admission']['members']=old['members'];old['admission']['training_exclusions']={}
    old['membership_observation_asof']='2026-10-30'
    def save(path,value):
        raw=json.dumps(value).encode();(root/path).write_bytes(raw);return sha256(raw).hexdigest()
    previous_hash=save('previous.json',old)
    observed=json.loads((root/'members.json').read_bytes())
    original=json.loads((root/'plan.json').read_bytes())
    fixed=dict(search_arguments=dict(prices={row['security_id']:row['decision_nominal_close']},
        metadata={row['security_id']:dict(ticker=row['ticker'],issuer_id=row['issuer_id'])},decision_date=old['decision_date']))
    ih=save('fixed.json',fixed);mh=sha256((root/'members.json').read_bytes()).hexdigest()
    domain=dict(schema='EXPERIMENTAL_DERIVED_DOMAIN_V1',point_in_time_membership_verified=False,
        new_membership_observation=False,production_replacement=False,original_observation_path='members.json',original_observation_sha256=mh,
        original_observed_count=2,membership_observation_date='2026-10-30',fixed_security_count=1,members=old['members'],
        securities=[dict(ticker=row['ticker'],issuer_id=row['issuer_id'],security_id=row['security_id'],security_type='EQUITY')],
        exclusions=[dict(ticker='CCC',reason='SYNTHETIC_SHORT_HISTORY_EXCLUSION')],fixed_input_path='fixed.json',fixed_input_sha256=ih,
        source_hashes={'members.json':mh,'fixed.json':ih})
    dh=save('domain.json',domain)
    plan=dict(schema=SCHEMA,status='SYNTHETIC_TEST_ONLY',domain_path='domain.json',domain_source_hashes={**domain['source_hashes'],'domain.json':dh},
        calendar_path=original['calendar_path'],calendar_source_hashes=original['calendar_source_hashes'],
        session=original['session'],history_start_date=original['history_start_date'],securities=[original['securities'][0]],
        output_directory='actual-capture',previous_manifest_path='previous.json',previous_manifest_sha256=previous_hash)
    ph=save('experiment.json',plan)
    body=(root/'new/BBB.response.bin').read_bytes();calls=[]
    def fetch(url,**kwargs):
        calls.append(url);return dict(raw=body,http_status=200,final_url=url,response_headers={})
    return args,plan,ph,fetch,calls


class ExperimentalCaptureTests(unittest.TestCase):
    def test_actual_batch_capture_to_existing_training_build(self):
        with TemporaryDirectory() as folder:
            args,plan,ph,fetch,calls=fixture(folder)
            before=run('experiment.json',ph,root=args['root'],clock=args['clock'])
            self.assertEqual(before['declared_count'],1);self.assertEqual(calls,[])
            result=run('experiment.json',ph,root=args['root'],clock=args['clock'],capture=True,fetch=fetch)
            self.assertEqual(result['status'],'EXPERIMENTAL_DOMAIN_CAPTURED_NOT_ADMITTED',result)
            index=args['root']/'actual-capture/completion_index.json'
            args.update(previous_manifest_sha256=plan['previous_manifest_sha256'],plan_path='experiment.json',plan_sha256=ph,
                        capture_index_path='actual-capture/completion_index.json',capture_index_sha256=sha256(index.read_bytes()).hexdigest(),plan_validator=prepare)
            manifest,compiled,_=build(**args)
            self.assertEqual(manifest['membership_observation_asof'],'2026-10-30')
            self.assertEqual(set(compiled['input']['search_arguments']['prices']),{'B'})
            self.assertEqual(len(calls),1)
            with self.assertRaisesRegex(ValueError,'NO_RETRY'):
                run('experiment.json',ph,root=args['root'],clock=args['clock'],capture=True,fetch=fetch)
            self.assertEqual(len(calls),1)

    def test_future_capture_zero_http_and_bound_domain_tamper(self):
        with TemporaryDirectory() as folder:
            args,plan,ph,fetch,calls=fixture(folder)
            with self.assertRaisesRegex(ValueError,'SESSION_NOT_CLOSED'):
                run('experiment.json',ph,root=args['root'],clock=lambda:datetime.fromisoformat('2026-11-02T20:59:00+00:00'),capture=True,fetch=fetch)
            self.assertEqual(calls,[]);self.assertFalse((args['root']/'actual-capture').exists())
            plan['securities'][0]['security_id']='wrong'
            raw=json.dumps(plan).encode();(args['root']/'experiment.json').write_bytes(raw)
            with self.assertRaisesRegex(ValueError,'PLAN_DOMAIN_MISMATCH'):
                run('experiment.json',sha256(raw).hexdigest(),root=args['root'],clock=args['clock'],capture=True,fetch=fetch)
            self.assertEqual(calls,[])

    def test_transport_failure_is_retained_and_not_retried(self):
        with TemporaryDirectory() as folder:
            args,plan,ph,_,calls=fixture(folder)
            def fail(url,**kwargs):calls.append(url);raise OSError('synthetic missing source')
            result=run('experiment.json',ph,root=args['root'],clock=args['clock'],capture=True,fetch=fail)
            self.assertEqual(result['status'],'INCOMPLETE_NOT_ADMITTED');self.assertEqual(len(calls),1)
            with self.assertRaisesRegex(ValueError,'NO_RETRY'):
                run('experiment.json',ph,root=args['root'],clock=args['clock'],capture=True,fetch=fail)
            self.assertEqual(len(calls),1)


if __name__=='__main__':unittest.main()
