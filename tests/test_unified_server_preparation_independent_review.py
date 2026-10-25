import json,unittest
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from core.strategy_account_ledger import canonical
from data.strategy_unified_server_preparation_v3 import SOURCES,build_unified_server_preparation_v3
ROOT=Path(__file__).resolve().parents[1]
class UnifiedPreparationReview(unittest.TestCase):
 def test_candidate_refs_and_all_source_pins_exact(self):
  path=ROOT/'research_contracts/unified_server_20261020_v1/server.json';raw=path.read_bytes()
  self.assertEqual(sha256(raw).hexdigest(),'ddd59e23fc2e32dbcfef36cdf64950ccfbaf16aeb22d1fb4bee28d6e88a8646c')
  config=json.loads(raw);self.assertTrue(SOURCES<=set(config['source_pins']))
  for name,digest in config['source_pins'].items():self.assertEqual(sha256((ROOT/name).read_bytes()).hexdigest(),digest,name)
  for key in ('preparation','upgrade','legacy_ui_configuration','daily_configuration'):
   ref=config[key];self.assertEqual(sha256((ROOT/ref['path']).read_bytes()).hexdigest(),ref['sha256'])
  daily=json.loads((ROOT/config['daily_configuration']['path']).read_bytes());self.assertIs(daily['policy_execution_enabled'],False);self.assertIsNone(daily['policy_id']);self.assertNotIn('trusted_release_sha256',daily['evidence'])
 def test_bad_hash_unknown_fields_missing_source_scope_fail_before_runtime(self):
  base=json.loads((ROOT/'research_contracts/unified_server_20261020_v1/server.json').read_bytes())
  for mode in ('hash','fields','scope'):
   with self.subTest(mode=mode),TemporaryDirectory() as folder:
    cfg=deepcopy(base)
    if mode=='fields':cfg['browser_policy_override']=True
    if mode=='scope':cfg['source_pins'].pop('data/strategy_unified_server_preparation_v3.py')
    raw=canonical(cfg);(Path(folder)/'server.json').write_bytes(raw)
    digest='0'*64 if mode=='hash' else sha256(raw).hexdigest()
    with self.assertRaisesRegex(ValueError,{'hash':'UNIFIED_SERVER_CONFIGURATION_CHANGED','fields':'UNIFIED_SERVER_CONFIGURATION_FIELDS','scope':'UNIFIED_SERVER_SOURCE_SCOPE'}[mode]):
     build_unified_server_preparation_v3(root=folder,configuration_path='server.json',configuration_sha256=digest)
    self.assertEqual([p.name for p in Path(folder).iterdir()],['server.json'])
