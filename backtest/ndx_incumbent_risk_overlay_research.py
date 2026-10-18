"""Read-only historical reviewed incumbent labels, not candidate admission."""
import csv
import hashlib
import io
import json
from datetime import date
from pathlib import Path
import re

import yaml

_SOURCE = Path(__file__).resolve()
_LOADED_SOURCE_SHA256 = hashlib.sha256(_SOURCE.read_bytes()).hexdigest()


def _unique_mapping(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate structured mapping key')
        result[key] = value
    return result


class _UniqueYamlLoader(yaml.SafeLoader):
    pass


def _yaml_mapping(loader, node):
    loader.flatten_mapping(node)
    return _unique_mapping((loader.construct_object(key), loader.construct_object(value))
                           for key, value in node.value)


_UniqueYamlLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _yaml_mapping)


def load_incumbent_risk_overlay(*, reviewed_manifest_path, expected_manifest_sha256,
                                tickers, date_start, date_end):
    def require(condition, message):
        if not condition:
            raise ValueError(message)

    def day(value):
        require(type(value) is str and date.fromisoformat(value).isoformat() == value,
                'Canonical date required')
        return value

    start, end = day(date_start), day(date_end)
    require(start <= end, 'Invalid date interval')
    require(type(tickers) in (list, tuple) and tickers and len(set(tickers)) == len(tickers)
            and all(type(t) is str and t and t == t.strip() for t in tickers), 'Explicit unique tickers required')
    observed = {}
    def read(path, digest):
        require(type(digest) is str and re.fullmatch('[0-9a-f]{64}', digest), 'Explicit source SHA required')
        path = Path(path).resolve()
        raw = path.read_bytes()
        require(hashlib.sha256(raw).hexdigest() == digest, 'Source digest differs: '+str(path))
        if path in observed:
            require(observed[path] == digest, 'Conflicting source identity')
        observed[path] = digest
        return raw

    manifest_path = Path(reviewed_manifest_path).resolve()
    read(_SOURCE, _LOADED_SOURCE_SHA256)
    def parse_json(raw):
        return json.loads(raw, object_pairs_hook=_unique_mapping)
    manifest = parse_json(read(manifest_path, expected_manifest_sha256))
    require(manifest['manifest_type'] == 'ndx_incumbent_overlay_reviewed_bundle'
            and manifest['classification_status'] == 'accepted_evidence_applied', 'Reviewed bundle required')
    def artifact(key):
        item = manifest['artifacts'][key]
        name = item['filename']
        require(type(name) is str and Path(name).name == name, 'Artifact filename must be local')
        raw = read(manifest_path.parent/name, item['sha256'])
        return raw
    def rows(raw):
        parsed = list(csv.reader(io.StringIO(raw.decode('utf-8-sig'))))
        require(parsed and parsed[0] and all(parsed[0]) and len(set(parsed[0])) == len(parsed[0]),
                'Duplicate or empty CSV header')
        header = parsed[0]
        require(all(len(row) == len(header) for row in parsed[1:]), 'CSV row width differs')
        return [dict(zip(header, row)) for row in parsed[1:]]
    coverage = rows(artifact('coverage'))
    evidence = rows(artifact('evidence_reviewed'))
    decisions = yaml.load(artifact('decision_snapshot'), Loader=_UniqueYamlLoader)['decisions']
    require(manifest['artifacts']['decision_snapshot']['sha256'] == manifest['decision_registry_sha256'],
            'Decision registry binding differs')
    documents = rows(read(manifest_path.parent.parent/'review_documents.csv',
        manifest['summary']['input_versions']['documents']['content_sha256']))
    read(manifest_path.parent/'fetch_manifest_snapshot.json', manifest['source_overlay_manifest_sha256'])
    def indexed(values):
        require(isinstance(values, list) and all(isinstance(row, dict) and 'ticker' in row for row in values),
                'Invalid source records')
        require(len(values) == len(tickers) and {row['ticker'] for row in values} == set(tickers),
                'Ticker coverage or uniqueness differs')
        return {row['ticker']: row for row in values}
    covered, reviewed, decided, sourced = map(indexed, (coverage, evidence, decisions, documents))
    for ticker in tickers:
        c, e, d, s = covered[ticker], reviewed[ticker], decided[ticker], sourced[ticker]
        for key in ('security_id', 'issuer_id', 'risk_chain', 'confidence', 'effective_from',
                    'effective_to', 'evidence_available_date', 'status', 'evidence_locator', 'accession_number'):
            require(c[key] == e[key], 'Coverage/evidence field differs: '+key)
        require(c['status'] == d['status'] == 'accepted' and c['risk_chain'] not in ('', 'unclassified'),
                'Accepted classified evidence required')
        for key in ('security_id', 'issuer_id', 'risk_chain', 'confidence'):
            require(c[key] and c[key] == d[key], 'Decision identity differs: '+key)
        require(d['evidence_id'] == e['evidence_id']
                and d['expected_accession_number'] == c['accession_number']
                and d['effective_from'] == 'evidence_available_date'
                and (d.get('effective_to') or '') == c['effective_to'], 'Decision evidence binding differs')
        available, effective = day(c['evidence_available_date']), day(c['effective_from'])
        require(available == effective and effective <= start
                and (not c['effective_to'] or day(c['effective_to']) >= end), 'Evidence does not cover requested interval')
        for field in ('security_id', 'issuer_id', 'accession_number', 'evidence_available_date'):
            require(c[field] == s[field], 'Document identity differs: '+field)
        require(c['evidence_locator'] == s['document_url'] and s['raw_manifest_verified'] == 'True',
                'Document locator/source verification differs')
        require(d['expected_raw_sha256'] == s['raw_sha256']
                and d['expected_excerpt_sha256'] == s['business_excerpt_sha256'], 'Reviewed raw/excerpt differs')
        require(hashlib.sha256(s['business_excerpt'].encode()).hexdigest() == s['business_excerpt_sha256'],
                'Excerpt content digest differs')
        require(e['evidence_excerpt'] == s['business_excerpt'], 'Reviewed excerpt differs')
        read(s['raw_path'], s['raw_sha256'])
        sidecar = parse_json(read(s['raw_manifest_path'], s['raw_manifest_sha256']))
        require(sidecar['content_sha256'] == s['raw_sha256']
                and sidecar['evidence_available_date'] == available,
                'Raw sidecar content/date differs')
    for path, digest in observed.items():
        require(hashlib.sha256(path.read_bytes()).hexdigest() == digest, 'Source changed during overlay load')
    return dict(risk_chain_by_ticker={t: covered[t]['risk_chain'] for t in tickers},
        coverage=coverage, evidence=evidence, provenance=dict(
            schema='ndx_incumbent_risk_overlay_research_v1', source_hashes={str(p): h for p,h in observed.items()},
            date_start=start, date_end=end, role='NEW_INCUMBENT_CONTROL_RISK_SOURCE',
            reviewed_at=manifest.get('generated_at'), historical_filing_open_interval_mapping=True,
            external_point_in_time_authenticity_verified=False, annual_revalidation_verified=False,
            overlay_identity_tickers=[t for t in tickers if covered[t]['security_id'].startswith('security:incumbent_overlay:')],
            complete_cusip_identity_claim_allowed=False, promotion_allowed=False))
