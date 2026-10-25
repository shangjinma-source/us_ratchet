from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from datetime import datetime,timezone
from hashlib import sha256
from copy import deepcopy
from unittest.mock import patch
import unittest
from fastapi import APIRouter
from core.strategy_account_ledger import canonical
from data.strategy_unified_server_preparation_v13 import attach_daily_rss_v13

class PreparationScopeTests(unittest.TestCase):
 def case(self,folder):
  root=Path(folder)
  def save(name,value):
   raw=canonical(value);(root/name).write_bytes(raw);return dict(path=name,sha256=sha256(raw).hexdigest())
  prior=dict(path='old-source.json',sha256='a'*64)
  source=save('source.json',dict(prior_configuration=prior,migration_session='2026-10-22'))
  old_app=dict(source_configuration=prior,code_pins=[dict(path='old.py',sha256='b'*64)],authorized=True,valid_until='2026-10-30T20:00:00Z',release={'fixed':True})
  app=deepcopy(old_app);app['source_configuration']=source;app['code_pins'].append(dict(path='new.py',sha256='c'*64))
  old_ref=save('old-app.json',old_app);new_ref=save('app.json',app)
  packet=SimpleNamespace(reference=prior,review_reference=old_ref,release_path='release.json',release_sha='d'*64,archive_root='archive')
  monthly=object();clock=lambda:datetime.now(timezone.utc)
  previous=SimpleNamespace(monthly=monthly,reader=SimpleNamespace(packet_reader=packet),clock=clock,enabled=True,policy_id='unchanged')
  old=SimpleNamespace(monthly=monthly,service=previous,journal=object(),clock=clock,policy_references={'old':True})
  router=APIRouter();router.add_api_route('/api/strategy-daily-v3/preview',lambda:{},methods=['POST'])
  prepared=dict(monthly=monthly,observed_daily=old,router=router,validate_code=lambda:None)
  config=dict(policy_id='unchanged',policy_execution_enabled=True,evidence=dict(configuration_path=source['path'],configuration_sha256=source['sha256'],review_configuration_path=new_ref['path'],review_configuration_sha256=new_ref['sha256'],release_path='release.json',trusted_release_sha256='d'*64,archive_root='archive'))
  return root,save,app,config,prepared
 def test_references_replaced_and_new_reader_postcheck_type(self):
  with TemporaryDirectory() as folder:
   root,save,app,config,prepared=self.case(folder)
   with patch('data.strategy_unified_server_preparation_v13.resolve_saved_context'):
    result=attach_daily_rss_v13(prepared=prepared,root=root,daily_configuration=config,daily_reference={'path':'daily.json','sha256':'e'*64},validate_v13_sources=lambda:None)
   refs=result['observed_daily'].policy_references
   self.assertEqual(refs['daily_configuration']['path'],'daily.json');self.assertEqual(refs['evidence_references'],config['evidence'])
   self.assertEqual(refs['previous_policy_references'],{'old':True})
   self.assertEqual(type(result['observed_daily'].service.reader.packet_reader).__name__,'ExplicitDomainPolicyReviewReaderV2')
 def test_policy_extension_or_old_pin_change_rejected(self):
  for mode in ('validity','pin'):
   with self.subTest(mode=mode),TemporaryDirectory() as folder:
    root,save,app,config,prepared=self.case(folder)
    if mode=='validity':app['valid_until']='2027-01-01T00:00:00Z'
    else:app['code_pins'][0]['sha256']='f'*64
    ref=save('app.json',app);config['evidence']['review_configuration_sha256']=ref['sha256']
    with patch('data.strategy_unified_server_preparation_v13.resolve_saved_context'),self.assertRaisesRegex(ValueError,'V13_APPLICATION_'):
     attach_daily_rss_v13(prepared=prepared,root=root,daily_configuration=config,daily_reference={},validate_v13_sources=lambda:None)
if __name__=='__main__':unittest.main()
