"""Add dated action-document coordinate candidates without approving issuer joins."""
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'data/cache/research'
REFERENCES = {
    'base': ('latest_security_source_inventory_20260919_v1/inventory_draft.json', 'c8ded89c059abafc09883deda141c60a8f3e246748b2b879b596d38693c19a3a'),
    'prior_events': ('standard_split_official_evidence_20260912_v1/specific_split_fact_readback.json', 'f421d8b95c6542139b016a853c3ab9e7f69d76daaff79e4592918fce8e8e4d55'),
    'new_events': ('remaining_standard_split_evidence_20260912_v1/all_32_event_status.json', '99119e5c3664b272d65eec498fb18714feb4fa7aa43e0ceff9682c79df8cafae'),
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build():
    sources = {str(Path(__file__).resolve()): sha(__file__)}
    values = {}
    for name, (relative, expected) in REFERENCES.items():
        path = (BASE / relative).resolve()
        if sha(path) != expected:
            raise ValueError('Sealed source differs')
        sources[str(path)] = expected
        values[name] = json.loads(path.read_text(encoding='utf-8'))
    output = copy.deepcopy(values['base'])
    output['schema'] = 'LATEST_SECURITY_SOURCE_CANDIDATE_INVENTORY_DRAFT_V2'
    events = [dict(source='prior_events', fact=r) for r in values['prior_events']['specific_events']]
    events += [dict(source='new_events', fact=r) for r in values['new_events']['specific_new_events']]
    for row in output['rows']:
        row['dated_action_document_candidates'] = [r for r in events if r['fact']['ticker'] == row['ticker']]
        row['action_document_issuer_join_approved'] = False
        row['action_document_limit'] = 'Ticker selects a document candidate only; memo CUSIP/class does not prove current CIK, full interval or provider binding.'
    ready = [r for r in output['rows'] if r['fit127_date_coverage_only']]
    output['counts']['ready_with_action_document_cusip_candidates'] = sum(any(e['fact'].get('cusip') for e in r['dated_action_document_candidates']) for r in ready)
    output['counts']['ready_with_dated_identity_or_action_cusip_candidates'] = sum(bool(r['dated_security_fact_candidates']) or any(e['fact'].get('cusip') for e in r['dated_action_document_candidates']) for r in ready)
    output['counts']['ready_with_any_historical_risk_candidate'] = sum(bool(r['historical_conditional_business_chain_candidates'] or r['historical_original_risk_labels']) for r in ready)
    output['sources'].update(sources)
    for path, expected in output['sources'].items():
        if sha(path) != expected:
            raise ValueError('Source changed')
    return output


if __name__ == '__main__':
    value = build()
    path = BASE / 'latest_security_source_inventory_20260919_v1/inventory_with_events_draft.json'
    with path.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=True, indent=2, allow_nan=False)
    print(json.dumps(dict(path=str(path), sha256=sha(path), counts=value['counts'])))
