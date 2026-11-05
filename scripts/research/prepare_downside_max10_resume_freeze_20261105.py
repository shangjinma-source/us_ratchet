"""Freeze the one-parent META-only execution continuation; does not run it."""
from pathlib import Path
from hashlib import sha256
import json,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from scripts.research.prepare_downside_max10_freeze_20261105 import dependency_closure
ARTIFACT='tmp/meta_dividend_evidence_20261105/supplement.json'
ARTIFACT_HASH='3781f42104301307194fa91d82a9db9696f0c1e2a5d7c2f47ca240c438492413'


def main():
    prior=json.loads((ROOT/'research_contracts/downside_max10_20261105/freeze.json').read_bytes());pins=dict(prior['source_hashes'])
    for name,h in pins.items():
        if sha256((ROOT/name).read_bytes()).hexdigest()!=h:raise ValueError('V1_FROZEN_SOURCE_CHANGED:'+name)
    def add(name,expected=None):
        h=sha256((ROOT/name).read_bytes()).hexdigest()
        if expected is not None and h!=expected:raise ValueError('EVIDENCE_CHANGED:'+name)
        if name in pins and pins[name]!=h:raise ValueError('FREEZE_PIN_CONFLICT:'+name)
        pins[name]=h
    add(ARTIFACT,ARTIFACT_HASH);artifact=json.loads((ROOT/ARTIFACT).read_bytes())
    for name,h in artifact['source_hashes'].items():add(name,h)
    roots=['scripts/research/run_downside_account_candidate_20261105_v2.py','docs/candidates/qqq_risk_budget_account_runner.py','tmp/two_stage_bull_bear_20261029/wbd_local_review/legacy_absence_adapter.py']
    closure=dependency_closure(roots)
    for name in closure:add(name)
    for name in ['scripts/research/prepare_downside_max10_resume_freeze_20261105.py','docs/candidates/downside_max10_resume_contract_20261105.md','research_contracts/downside_max10_20261105/freeze.json']:add(name)
    out=ROOT/'research_contracts/downside_max10_resume_20261105';out.mkdir(parents=True,exist_ok=False)
    doc=dict(schema='DOWNSIDE_MAX10_RESUME_EXECUTION_V2',status='READY_FOR_FIXED_MAX10_EXECUTION',max_holdings=10,windows={'2024_2026':31},seconds_per_window=10800,seconds_per_month=600,additional_execution_artifact=ARTIFACT,source_hashes=pins,local_import_closure=sorted(closure),parent_freeze='research_contracts/downside_max10_20261105/freeze.json',scope='META_EXECUTION_MAPPING_ONLY_NO_STRATEGY_CHANGE_NO_BUDGET_RESET')
    (out/'freeze.json').write_text(json.dumps(doc,indent=2),encoding='utf-8');print(len(pins))

if __name__=='__main__':main()
