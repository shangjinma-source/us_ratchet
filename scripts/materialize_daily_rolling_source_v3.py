"""Create an uninstalled v3 single-SID source configuration; no capture or policy approval."""
import argparse,json
from hashlib import sha256
from pathlib import Path
from core.strategy_account_ledger import canonical
from data.strategy_daily_rolling_parent_v3 import pinned
from data.strategy_daily_session_capture import reject_links,require
from data.strategy_daily_continuity_normalizer import NORMALIZATION_CODE_PATHS
from data.strategy_daily_rolling_runner_v3 import V3_SOURCES

V2=dict(path='research_contracts/daily_source_pipeline_20261020_v2/pipeline.json',sha256='63a4b9e7b4a01ae654b25d680ad7abcc9798437705694e8fbeb3ba720a6a247c')
CALENDAR=dict(path='research_contracts/daily_calendar_2026_extension_v1/calendar.candidate.json',sha256='1440d82ecc956baab15df4b49da444e4878459e353cf7c280dd5d3dcf2a109af')

def materialize(root,output):
 reject_links(root);root=Path(root).resolve();directory=root/output;reject_links(directory)
 require(directory.resolve().is_relative_to(root) and directory.resolve()!=root,'ROLLING_CONFIG_OUTPUT_PATH')
 old=json.loads(pinned(root,V2));capture=json.loads(pinned(root,old['capture_configuration']))
 calendar=pinned(root,CALENDAR);receipt=json.loads(pinned(root,old['parent_reference']))
 # Preserve reviewed identity and policy bindings exactly. Candidate calendar is separately pinned.
 pinned(root,capture['identity_review'])
 directory.mkdir(parents=True,exist_ok=False)
 def save(name,value):
  raw=value if isinstance(value,bytes) else canonical(value)
  with (directory/name).open('xb') as stream:stream.write(raw)
  return dict(path=(directory/name).relative_to(root).as_posix(),sha256=sha256(raw).hexdigest())
 def source(name):
  path=root/name;reject_links(path)
  return dict(path=name,sha256=sha256(path.read_bytes()).hexdigest())
 calendar_ref=save('calendar.json',calendar)
 capture.update(calendar=calendar_ref,output_root='data/daily_source_pipeline_v3/capture',
  source_pins=[source(name) for name in sorted(NORMALIZATION_CODE_PATHS)])
 capture_ref=save('capture.json',capture)
 config=dict(schema='SERVER_ROLLING_DAILY_SOURCE_V3',source_pins=[source(name) for name in sorted(V3_SOURCES)],
  capture_configuration=capture_ref,first_execution_date='2026-10-21',seed_receipt=old['parent_reference'],
  seed_source_paths={name:name for name in receipt['source_sha256']},accepted_prior_configuration_sha256=[],
  runs_root='data/daily_source_pipeline_v3/runs',account_database=old['account_database'],target_database=old['target_database'],
  account_id=old['account_id'],policy_approved=False,scheduler_installed=False,
  calendar_source=CALENDAR,limitations=['single SID only; other target/held/pending SIDs wait','32MB/2000 inherited source closure bound','published sessions do not certify unexpected closures'])
 reference=save('pipeline.json',config)
 save('materialization.json',dict(status='V3_CANDIDATE_NOT_INSTALLED',pipeline_reference=reference,
  old_configuration_unchanged=V2,http_calls=0,policy_approved=False,calendar_last_date='2026-12-31'))
 return reference

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--root',required=True);parser.add_argument('--output',required=True)
 args=parser.parse_args();print(json.dumps(materialize(args.root,args.output)))
