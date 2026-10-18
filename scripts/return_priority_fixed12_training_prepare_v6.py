"""Finalize inherited status annotations without changing frozen numeric inputs."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'tmp/fixed12_training_prepare_20261014_v5/prepared.json'
DESTINATION=ROOT/'tmp/fixed12_training_prepare_20261014_v6/prepared.json'


if __name__=='__main__':
    raw=SOURCE.read_bytes()
    if hashlib.sha256(raw).hexdigest()!='d7548a781fc868b75ca6b8e96a4695246e37695ed16c4b8a83c1f4ab7dffd476':raise ValueError('Frozen v5 differs')
    result=json.loads(raw)
    original_arguments=[w['search_arguments'] for w in result['windows']]
    result['training_price_only_limitations']=[s for s in result['training_price_only_limitations'] if not s.startswith('No runnable search_arguments')]
    result['training_price_only_limitations'].append('Search arguments are prepared for all twelve windows; independent review and Root execution are separate. No search has run.')
    for w in result['windows']:
        for row in w['candidates']:
            if 'unit_audit_required' in row:
                row['earlier_unit_audit_questions']=row.pop('unit_audit_required')
            row['current_unit_review_status']='CONDITIONALLY_RESOLVED_NOT_AUTHENTICATED' if row['decision_cost'] else 'NO_COST_REQUIRED_FOR_TRAINING_EXCLUSION'
    assert original_arguments==[w['search_arguments'] for w in result['windows']]
    result['source_hashes'][str(SOURCE)]=hashlib.sha256(raw).hexdigest()
    result['source_hashes'][str(Path(__file__).resolve())]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    for name,digest in result['source_hashes'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:raise ValueError('Source differs: '+name)
    DESTINATION.parent.mkdir(exist_ok=False)
    with DESTINATION.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(hashlib.sha256(DESTINATION.read_bytes()).hexdigest())
