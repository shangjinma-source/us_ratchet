"""Separate no-action review admission; never creates cash entitlements."""
from copy import deepcopy
from pathlib import Path
from hashlib import sha256
import json
import importlib.util
from docs.candidates.downside_resume_chain_20261105 import append_ordinary_artifact
from scripts.run_old_continuous_probe_v4 import validate_absence_review

ROOT=Path(__file__).resolve().parents[2]


def append_execution_artifact(document, review, artifact):
    if artifact.get('schema')!='BOUNDED_PROVIDER_ABSENCE_V1':
        return append_ordinary_artifact(document,review,artifact)
    if artifact.get('status')!='REVIEWED_CONDITIONAL_PROVIDER_ABSENCE' or 'dividend_events' in artifact or not artifact.get('review_rows'):
        raise ValueError('ABSENCE_NOT_DIVIDEND_ARTIFACT')
    pins=artifact['source_hashes']
    for name,h in pins.items():
        p=(ROOT/name).resolve()
        if not p.is_relative_to(ROOT) or sha256(p.read_bytes()).hexdigest()!=h:
            raise ValueError('ABSENCE_SOURCE_CHANGED:'+name)
        if name in review['source_hashes'] and review['source_hashes'][name]!=h:
            raise ValueError('ABSENCE_PIN_CONFLICT')
    normalized=[]
    for original in artifact['review_rows']:
        row=deepcopy(original)
        if row['status']!='REVIEWED_NO_ACTION_FOR_PERIOD':raise ValueError('ABSENCE_REVIEW_STATUS')
        if row['security_id']!=artifact['security_id']:raise ValueError('ABSENCE_SID_BINDING')
        # The frozen artifact carries SID and selected source paths, not the old
        # validator's redundant ticker/request_checks fields. Derive identity from
        # the pinned baseline metadata; the validator then reads actual receipts,
        # URLs, body bytes and requested intervals itself. Do not fabricate checks.
        row['ticker']=document['prepared_input_candidate']['metadata'][row['security_id']]['ticker']
        row['request_checks']=[dict(source=source) for source in row['selected_price_sources']]
        receipts=[json.loads((ROOT/source.replace('.response.bin','.receipt.json')).read_bytes())
                  for source in row['selected_price_sources']]
        if all('body_truncated' in receipt for receipt in receipts):
            validate_absence_review(row,artifact,document)
        else:
            if (row['ticker']!='INSM' or row['start_exclusive']!='2023-12-29' or
                row['end_inclusive']!='2026-07-30' or len(receipts)!=1 or 'body_truncated' in receipts[0]):
                raise ValueError('EXACT_INSM_LEGACY_SCOPE_REQUIRED')
            legacy_path=ROOT/'tmp/two_stage_bull_bear_20261029/wbd_local_review/legacy_absence_adapter.py'
            if sha256(legacy_path.read_bytes()).hexdigest()!='2016ac8bfc802ae3042bd7592e3a897bcb0568c88a79161a8de05d58dc8f3aa5':
                raise ValueError('LEGACY_INSPECTOR_SOURCE_CHANGED')
            spec=importlib.util.spec_from_file_location('isolated_insm_legacy_request_check',legacy_path)
            legacy=importlib.util.module_from_spec(spec);spec.loader.exec_module(legacy)
            source=row['selected_price_sources'][0]
            receipt=receipts[0];started_path=source.replace('.response.bin','.started.json')
            started=json.loads((ROOT/started_path).read_bytes())
            if (row['security_id']!='security:0001104506:457669307' or
                source!='tmp/next12_missing_quote_capture_20261014_v1/INSM.response.bin' or
                pins[source]!=document['source_hashes'][source] or
                receipt['ticker']!=started['ticker'] or receipt['started_at_utc']!=started['started_at_utc']
                or not {source,source.replace('.response.bin','.receipt.json'),started_path}<=set(row['source_references'])):
                raise ValueError('LEGACY_REQUEST_PIN_BINDING')
            sessions=document['assembled']['session_dates']
            if len(sessions)!=647 or sessions[0]!='2023-12-29' or sessions[-1]!='2026-07-30':
                raise ValueError('LEGACY_EXACT_CALENDAR_REQUIRED')
            row['legacy_request_check']=legacy.inspect((ROOT/source).read_bytes(),receipt,
                started,required_sessions=sessions,expected_symbol='INSM')
        if any(r.get('security_id')==row['security_id'] and r.get('start_exclusive')==row['start_exclusive']
               and r.get('end_inclusive')==row['end_inclusive'] and r['status']==row['status'] for r in review['rows']):
            raise ValueError('DUPLICATE_ABSENCE_REVIEW')
        normalized.append(row)
    review['rows'].extend(normalized)
    review['source_hashes'].update(pins)
