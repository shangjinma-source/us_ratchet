"""Verify saved historical eligibility artifacts, not reconstruct missing rules."""
import csv
from datetime import date
import hashlib
import io
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
MANIFEST=ROOT/'data/cache/research/ndx_variable_cardinality_discovery_v1/manifest.json'
MANIFEST_SHA='c19ccc5a1a8159cb420f72b8b149e9702c3b4986923a0cd0cdc65665f788a4a1'
_SOURCE=Path(__file__).resolve()
_LOADED=hashlib.sha256(_SOURCE.read_bytes()).hexdigest()


def _date(value):
    if type(value) is not str or date.fromisoformat(value).isoformat()!=value:
        raise ValueError('Canonical YYYY-MM-DD required')
    return date.fromisoformat(value)


def _object(pairs):
    result={}
    for key,value in pairs:
        if key in result: raise ValueError('Duplicate JSON key')
        result[key]=value
    return result


def _csv(raw):
    rows=list(csv.reader(io.StringIO(raw.decode('utf-8-sig'))))
    if not rows or len(set(rows[0]))!=len(rows[0]) or any(len(row)!=len(rows[0]) for row in rows[1:]):
        raise ValueError('Invalid CSV width/header')
    return [dict(zip(rows[0],row)) for row in rows[1:]]


def _active(row, selection):
    return (_date(row['effective_from'])<=selection
            and (not row['effective_to'] or selection<=_date(row['effective_to']))
            and _date(row['evidence_available_date'])<=selection)


def _observed(row, snapshot, selection):
    """Taxonomy record endpoints are membership observations, not expiry."""
    dates=[_date(value) for value in row['selection_dates'].split(';')]
    if (not dates or dates!=sorted(set(dates)) or snapshot not in dates
            or _date(row['effective_from'])!=dates[0] or _date(row['effective_to'])!=dates[-1]
            or _date(row['selection_date_start'])!=dates[0] or _date(row['selection_date_end'])!=dates[-1]
            or str(len(dates))!=str(row['observations_count'])):
        return False
    available=[_date(value) for value in row['evidence_available_date'].split(';')]
    return snapshot<=selection and all(value<=snapshot for value in available)


def _verify_rows(*, selection_date, securities, universe_track, eligible, records, evidence):
    selection=_date(selection_date)
    if universe_track not in ('strict_technology','technology_plus_adjacent'):
        raise ValueError('Explicit historical universe track required')
    if type(securities) is not dict or not securities:
        raise ValueError('Explicit securities required')
    tickers=set(); result=[]
    for security,item in securities.items():
        if type(item) is not dict or set(item)!={'ticker','issuer_id'}:
            raise ValueError('Exact requested identity schema required')
        for value in (security,item['ticker'],item['issuer_id']):
            if type(value) is not str or not value or value.strip()!=value:
                raise ValueError('Canonical identity required')
        if item['ticker']!=item['ticker'].upper() or item['ticker'] in tickers:
            raise ValueError('Unique ticker identity required')
        tickers.add(item['ticker'])
        matches=[row for row in eligible if row['selection_date']==selection_date and row['universe_track']==universe_track
                 and row['security_id']==security]
        if len(matches)>1: raise ValueError('Ambiguous historical eligible identity')
        if not matches:
            result.append(dict(security_id=security,**item,historical_artifact_verified=False,
                status='NOT_IN_SAVED_ELIGIBLE_ARTIFACT',current_technology_qualification='UNKNOWN'))
            continue
        row=matches[0]
        if row['ticker']!=item['ticker'] or row['issuer_id']!=item['issuer_id']:
            raise ValueError('Historical requested ticker/issuer mismatch')
        snapshot=_date(row['membership_snapshot_date'])
        if not _observed(row,snapshot,selection):
            raise ValueError('Historical eligible observation/evidence coordinate invalid')
        if (row['status']!='accepted' or row[universe_track+'_eligible']!='True'
                or row['membership_window_eligible']!='True' or row['event_gap_blocked']!='False'):
            raise ValueError('Saved eligible row gates do not pass')
        candidates=[record for record in records if record['security_id']==security
            and record['issuer_id']==item['issuer_id'] and record['ticker'] in row['taxonomy_ticker_aliases'].split(';')
            and record['status']=='accepted' and record['risk_chain']==row['risk_chain']
            and record['evidence_ids']==row['evidence_ids'] and _observed(record,snapshot,selection)]
        if len(candidates)!=1:
            raise ValueError('Taxonomy record binding absent or ambiguous')
        record=candidates[0]
        for field in ('effective_from','effective_to','selection_date_start','selection_date_end',
                      'selection_dates','observations_count','evidence_locator','evidence_source_type'):
            if record[field]!=row[field]:
                raise ValueError('Eligible/taxonomy observation fields differ')
        if record['evidence_available_date']!=row['evidence_available_date']:
            raise ValueError('Taxonomy available date differs')
        ids=row['evidence_ids'].split(';')
        if not all(ids) or len(ids)!=len(set(ids)):
            raise ValueError('Invalid evidence ids')
        linked=[]
        for evidence_id in ids:
            matching=[entry for entry in evidence if entry['evidence_id']==evidence_id
                and entry['security_id']==security and entry['issuer_id']==item['issuer_id']]
            if len(matching)!=1: raise ValueError('Evidence identity absent/ambiguous')
            entry=matching[0]
            if (entry['status']!='accepted' or entry['validation_status']!='valid'
                    or entry['risk_chain']!=row['risk_chain'] or not _active(entry,selection)
                    or entry['evidence_locator'] not in row['evidence_locator'].split(';')):
                raise ValueError('Evidence validity/risk/locator mismatch')
            linked.append(dict(evidence_id=evidence_id,evidence_available_date=entry['evidence_available_date'],
                effective_from=entry['effective_from'],effective_to=entry['effective_to'],
                locator=entry['evidence_locator'],scope=entry['scope']))
        result.append(dict(security_id=security,**item,historical_artifact_verified=True,
            status='SAVED_ELIGIBLE_AND_TAXONOMY_EVIDENCE_LINKED',risk_chain=row['risk_chain'],
            membership_snapshot_date=row['membership_snapshot_date'],evidence=linked,
            current_technology_qualification='UNKNOWN'))
    return result


def verify_historical_eligibility(*, selection_date, securities, universe_track,
        discovery_manifest_path=MANIFEST, expected_manifest_sha256=MANIFEST_SHA):
    sources={str(_SOURCE):_LOADED}
    def read(path,digest):
        if type(digest) is not str or re.fullmatch('[0-9a-f]{64}',digest) is None:
            raise ValueError('Explicit source SHA required')
        path=Path(path).resolve(); raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=digest: raise ValueError('Historical source digest mismatch')
        sources[str(path)]=digest
        return raw
    manifest=json.loads(read(discovery_manifest_path,expected_manifest_sha256),object_pairs_hook=_object)
    if manifest['manifest_type']!='ndx_variable_cardinality_discovery_preflight' or manifest['schema_version']!=1:
        raise ValueError('Wrong discovery manifest schema')
    eligible_descriptor=manifest['artifacts']['eligible_securities']
    eligible=_csv(read(eligible_descriptor['path'],eligible_descriptor['sha256']))
    if len(eligible)!=eligible_descriptor['rows']: raise ValueError('Eligible denominator differs')
    descriptor=manifest['inputs']['taxonomy_manifest']
    taxonomy_path=Path(descriptor['path'])
    taxonomy=json.loads(read(taxonomy_path,descriptor['sha256']),object_pairs_hook=_object)
    if taxonomy['manifest_type']!='ndx_taxonomy_v2_bundle' or taxonomy['taxonomy_version']!=manifest['taxonomy_version']:
        raise ValueError('Taxonomy manifest identity differs')
    descriptor=manifest['inputs']['taxonomy_records']; bound=taxonomy['artifacts']['records']
    if descriptor['sha256']!=bound['sha256'] or Path(descriptor['path']).resolve()!=(taxonomy_path.parent/bound['filename']).resolve():
        raise ValueError('Taxonomy record descriptor mismatch')
    records=_csv(read(descriptor['path'],descriptor['sha256']))
    if len(records)!=bound['rows']: raise ValueError('Taxonomy record denominator differs')
    bound=taxonomy['artifacts']['evidence_input']
    evidence=_csv(read(taxonomy_path.parent/bound['filename'],bound['sha256']))
    if len(evidence)!=bound['rows']: raise ValueError('Evidence denominator differs')
    verified=_verify_rows(selection_date=selection_date,securities=securities,universe_track=universe_track,
        eligible=eligible,records=records,evidence=evidence)
    unavailable=[]
    for name in ('base_search_plan_spec','plan_manifest'):
        item=manifest['inputs'][name]
        # Record the historical expectation only: never parse current replacement.
        unavailable.append(dict(name=name,expected_source=item,status='NOT_RECONSTRUCTED_NOT_USED'))
    if any(hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest for path,digest in sources.items()):
        raise ValueError('Historical lineage source changed during read')
    return dict(schema='ndx_historical_eligibility_lineage_v1',selection_date=selection_date,
        universe_track=universe_track,securities=verified,source_hashes=sources,
        unavailable_historical_rules=unavailable,historical_rule_reconstruction_verified=False,
        exact_ndx_membership_verified=False,external_source_authenticity_verified=False,
        current_technology_qualification='UNKNOWN',promotion_allowed=False,
        source_manifest_status={key:manifest[key] for key in ('status','readiness_status','exact_ndx_membership_valid',
            'historical_backtest_allowed','real_history_execution_allowed','limitation')})
