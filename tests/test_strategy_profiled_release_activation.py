from pathlib import Path
from hashlib import sha256
from copy import deepcopy
import json,unittest
from core.strategy_account_ledger import canonical
from data.strategy_continuous32_runtime import RUNTIME_PATHS
from data.strategy_profiled_ready_release import PROFILE_ADMISSION_SOURCES,validate_ready_release
from data.strategy_profiled_release_activation import ProfiledMonthlyReleaseActivation
from data.strategy_continuous32_target_decision import PROFILE_ID
from data.strategy_dynamic_source_gate import DYNAMIC_SOURCE_PATHS,bind_dynamic_source_gate
from scripts.review_prepare_real_monthly_release import run
from data.strategy_profiled_server_preparation import SOURCES,build_preparation
import test_review_prepare_real_monthly_release as fixtures

class ProfileActivationTests(unittest.TestCase):
 def test_real_ready_capture_profile_adoption_and_replay_no_target(self):
  f=fixtures.ReviewPrepareTests();f.setUp();self.addCleanup(f.doCleanups);root=f.root
  pins=dict(f.f.entry['runtime_pins'])
  for name in SOURCES:
   raw=(Path(__file__).resolve().parents[1]/name).read_bytes();dest=root/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw);pins[name]=sha256(raw).hexdigest()
  f.f.entry['runtime_pins']=pins
  base=run(**f.arguments)
  def put(name,value):
   raw=canonical(value);(root/name).write_bytes(raw);return dict(path=name,sha256=sha256(raw).hexdigest())
  def load(ref):return json.loads((root/ref['path']).read_bytes())
  base_ref=dict(path='reviewed-package/ready.json',sha256=sha256((root/'reviewed-package/ready.json').read_bytes()).hexdigest())
  original=load(base['files']['runtime']);config=dict(original,schema='REAL_STRATEGY_CONTINUOUS32_RUNTIME_V1',selector_profile=PROFILE_ID)
  config_ref=put('profile-runtime.json',config)
  registry=put('profile-registry.json',dict(schema='PROFILED_MONTHLY_RELEASES_V1',original_registry=base['files']['registry'],profiles=[dict(target_month='2026-12',selector_profile=PROFILE_ID)]))
  archive=load(base['files']['archive']);archive['schema']='PROFILED_STRATEGY_RUNTIME_ARCHIVE_V1';archive['entries'].append(dict(configuration_path=config_ref['path'],configuration_sha256=config_ref['sha256']))
  archive_ref=put('profile-archive.json',archive)
  receipt=dict(schema='PROFILED_READY_RELEASE_V1',status='READY_FOR_REVIEW_NOT_ACTIVATED',base_ready=base_ref,registry=registry,archive=archive_ref,runtime=config_ref)
  receipt_ref=put('profile-ready.json',receipt)
  gate=bind_dynamic_source_gate(root=root,source_pins=pins)
  initial={k:f.arguments[k] for k in ('registry_path','registry_sha256','archive_path','archive_sha256')}
  from data.strategy_account_release_activation import MonthlyReleaseActivation
  old=MonthlyReleaseActivation(root=root,initial_snapshot=initial,validate_code=gate,clock=lambda:f.now)
  old.adopt(receipt_path=base_ref['path'],receipt_sha256=base_ref['sha256'],expected_release_revision=0)
  oldrow=old.releases.current();oldbytes=old.releases.path.read_bytes()
  anchor=dict(revision=oldrow['revision'],record_sha256=sha256(canonical(oldrow)).hexdigest(),snapshot=old.snapshot())
  activation=ProfiledMonthlyReleaseActivation(root=root,initial_snapshot=initial,validate_code=gate,legacy_anchor=anchor,clock=lambda:f.now)
  self.assertEqual(activation.snapshot()['registry_path'],base['files']['registry']['path'])
  stale=dict(anchor,revision=0)
  blocked=ProfiledMonthlyReleaseActivation(root=root,initial_snapshot=initial,validate_code=gate,legacy_anchor=stale,clock=lambda:f.now)
  with self.assertRaisesRegex(ValueError,'LEGACY_MIGRATION_ANCHOR_CHANGED'):blocked.snapshot()
  # Persist a synthetic pre-existing original-profile target; no selector run.
  binding=dict(account_id=f.store.read()['account_id'],documents=dict(training_manifest=original['training_manifest']),source_hashes={original['training_manifest']:original['training_sha256'],original['identity_manifest']:original['identity_sha256']})
  payload=dict(input_binding=binding,input_id=sha256(canonical(binding)).hexdigest(),target_quantities={})
  decision=dict(payload=payload,decision_id=sha256(canonical(payload)).hexdigest())
  oldtarget=activation.targets.append(dict(schema='REAL_STRATEGY_MONTHLY_TARGET_V1',account_id=f.store.read()['account_id'],target_month='2026-12',created_at=f.now.isoformat(),request=dict(event_id='existing-original-fixture'),previous_target_id=None,decision=decision,target_quantities={},runtime_pins=original['runtime_pins']))
  targetbytes=activation.targets.path.read_bytes()
  before=f.store.path.read_bytes()
  result=activation.adopt(receipt_path=receipt_ref['path'],receipt_sha256=receipt_ref['sha256'],expected_release_revision=0)
  self.assertEqual(result['revision'],1);self.assertEqual(activation.snapshot()['revision'],1)
  self.assertEqual(f.store.path.read_bytes(),before)
  self.assertEqual(activation.targets.path.read_bytes(),targetbytes)
  self.assertEqual(old.releases.path.read_bytes(),oldbytes)
  factory_ref=put('profile-server.json',dict(schema='PROFILED_SERVER_PREPARATION_V2',initial_snapshot=initial,source_pins=pins,legacy_anchor=anchor))
  prepared=build_preparation(root=root,configuration_path=factory_ref['path'],configuration_sha256=factory_ref['sha256'],clock=lambda:f.now)
  with prepared['router'].snapshot_operation() as snapshot:self.assertEqual(snapshot['revision'],1)
  self.assertEqual(prepared['router'].current(),oldtarget)
  resolved=prepared['router']._for_target(oldtarget)[1]
  self.assertEqual(resolved,original)
  self.assertEqual(f.store.path.read_bytes(),before)
  (root/'profile-registry.json').write_bytes(b'corrupt')
  with self.assertRaises(ValueError):activation.snapshot()
