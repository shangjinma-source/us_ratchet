"""Conditional TSM ADS sidecar from a saved 2019 20-F; no holding conversion."""
import argparse
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(__file__).resolve()
OUTPUT = ROOT / 'data/cache/research/tsm_incumbent_identity_20261002_v1'
FILING = ROOT / 'data/cache/candidate_pools/ndx_taxonomy_v2/incumbent_overlay/raw_sec/filings/TSM/000119312519108390_d665387d20f.htm'
MANIFEST = FILING.with_suffix(FILING.suffix + '.manifest.json')
FILING_SHA = '00f2852761f4403486c0e77e11adfea7348fd4b110913083ef9735f171a11a74'
MANIFEST_SHA = '80a0f55ce540f9ae8a63b844e4f7d421a4bc9dd25b08f4b2acb1698ad027d86e'
URL = 'https://www.sec.gov/Archives/edgar/data/1046179/000119312519108390/d665387d20f.htm'
SCHEMA = 'TSM_INCUMBENT_CONDITIONAL_DATED_IDENTITY_V1'
ITEM9 = ('ITEM 9. THE OFFER AND LISTING The principal trading market for our common shares is the Taiwan Stock Exchange. '
         'Our common shares have been listed on the Taiwan Stock Exchange under the symbol “2330” since September 5, 1994, '
         'and the ADSs have been listed on the New York Stock Exchange under the symbol “TSM” since October 8, 1997. '
         'The outstanding ADSs are identified by the CUSIP number 874039100.')
CUSIP_SENTENCE = 'The outstanding ADSs are identified by the CUSIP number 874039100.'
RATIO = ('As of December 31, 2018, 1,068.2 million ADSs of TSMC were traded on the NYSE. '
         'The number of common shares represented by the ADSs was 5,340.8 million shares '
         '(one ADS represents five common shares). F - 55')
COVER = 'Taiwan Semiconductor Manufacturing Company Limited Republic of China'
FALSE_FLAGS = dict.fromkeys(('point_in_time_verified', 'promotion_allowed', 'ndx_membership_verified',
    'price_identity_verified', 'holdings_conversion_performed', 'price_conversion_performed',
    'historical_2023_identity_interval_verified', 'historical_2023_ads_ratio_verified',
    'inline_cik_field_verified', 'local_evidence_available_in_2023_verified', 'legal_identity_certified',
    'corporate_action_completeness_verified', 'live_execution_authorized', 'orders_generated',
    'fit_performed', 'account_executed', 'old_audit_repeated'), False)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


LOADED = {str(SOURCE): digest(SOURCE.read_bytes())}


class TextCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def normalized_text(raw):
    parser = TextCollector()
    parser.feed(raw.decode('utf-8', errors='strict'))
    parser.close()
    return ' '.join(' '.join(parser.parts).split())


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')


def strict(sources):
    for path, sha in sources.items():
        require(digest(Path(path).read_bytes()) == sha, 'Source drift: ' + path)


def locate(text, needle):
    require(text.count(needle) == 1, 'Missing/ambiguous source text: ' + needle[:60])
    start = text.index(needle)
    return {'text': needle, 'normalized_start': start, 'normalized_end_exclusive': start + len(needle), 'match_count': 1}


def extract(raw, manifest, filing_reference, manifest_reference):
    """Content extraction; callers must still verify external manifest hash."""
    require(digest(raw) == filing_reference['sha256'] == manifest['content_sha256'], 'Saved raw hash mismatch')
    require(type(manifest['content_bytes']) is int and manifest['content_bytes'] == len(raw), 'Saved raw length mismatch')
    require(Path(manifest['cache_path']).resolve() == Path(filing_reference['path']).resolve()
            and Path(manifest['manifest_path']).resolve() == Path(manifest_reference['path']).resolve(), 'Manifest saved paths mismatch')
    expected = {'schema_version': 1, 'dataset_type': 'ndx_incumbent_overlay_sec_annual_filing',
                'source': 'sec_edgar_incumbent_overlay', 'form': '20-F', 'ticker': 'TSM', 'cik': '0001046179',
                'overlay_id': 'incumbent_overlay:TSM', 'source_locator': URL,
                'dataset_key': 'incumbent_overlay:TSM:0001193125-19-108390',
                'report_date': '2018-12-31', 'filed_date': '2019-04-17',
                'evidence_available_date': '2019-04-18', 'fetched_at': '2026-07-14T17:38:21+00:00'}
    for key, value in expected.items():
        require(type(manifest.get(key)) is type(value) and manifest[key] == value, 'Manifest field mismatch: ' + key)
    require(manifest['research_only'] is True and manifest['classification_automatic'] is False
            and manifest['price_data_used'] is False and manifest['return_data_read'] is False
            and manifest['backtest_results_used'] is False, 'Manifest research scope mismatch')
    text = normalized_text(raw)
    require(text.count('874039100') == 1 and text.count('CUSIP') == 1, 'Unexpected CUSIP denominator')
    require(text.count('0001046179') == 0, 'Unexpected inline CIK; cannot retain archive-only claim')
    evidence = {'item9': locate(text, ITEM9), 'ads_cusip': locate(text, CUSIP_SENTENCE),
                'ratio_2018': locate(text, RATIO), 'cover_issuer_name': locate(text, COVER)}
    require(evidence['item9']['normalized_start'] <= evidence['ads_cusip']['normalized_start']
            < evidence['ads_cusip']['normalized_end_exclusive'] <= evidence['item9']['normalized_end_exclusive'], 'CUSIP not within same Item9 context')
    require(evidence['ratio_2018']['normalized_start'] > evidence['item9']['normalized_end_exclusive'], 'Unexpected financial-note order')
    return {'schema': SCHEMA, 'ticker': 'TSM', 'security_id': 'security:incumbent_overlay:TSM',
            'issuer_id': 'issuer:0001046179', 'issuer_cik': '0001046179', 'cusip': '874039100',
            'security_class': 'American Depositary Shares', 'ordinary_shares_per_ads': 5,
            'fact_as_of': '2018-12-31', 'report_date': manifest['report_date'], 'filed_date': manifest['filed_date'],
            'evidence_available_date': manifest['evidence_available_date'], 'fetched_at': manifest['fetched_at'],
            'date_semantics': 'SAVED_MANIFEST_DATES_NOT_NEW_SEC_ACCEPTANCE_CERTIFICATION',
            'issuer_cik_binding_kind': 'SAVED_MANIFEST_AND_SEC_ARCHIVE_PATH_NOT_INLINE_FIELD',
            'evidence': evidence, 'original_manifest': json.loads(encoded(manifest)),
            'normalized_text_sha256': digest(text.encode('utf-8')), 'normalized_text_character_count': len(text),
            'normalization': 'UTF8_STRICT_HTMLPARSER_ALL_HANDLE_DATA_JOIN_WHITESPACE_ZERO_BASED_CHAR_OFFSETS',
            'source_references': {'filing': filing_reference, 'manifest': manifest_reference},
            'overlay_join_assumption': 'Conditionally associate the saved TSM incumbent overlay with the dated NYSE ADS disclosure; retain the overlay SID without remapping holdings or quote units. This is not proof of 2023 identity or ADS-ratio continuity.',
            'ads_ratio_scope': '2018-12-31_FINANCIAL_NOTE_F55_ONLY_NOT_A_2023_CONVERSION_INSTRUCTION',
            'research_only': True, 'dated_ads_cusip_text_observed': True, **FALSE_FLAGS}


def build():
    strict(LOADED)
    raw, manifest_raw = FILING.read_bytes(), MANIFEST.read_bytes()
    require(digest(raw) == FILING_SHA and digest(manifest_raw) == MANIFEST_SHA, 'Hard input SHA mismatch')
    filing_ref, manifest_ref = {'path': str(FILING), 'sha256': FILING_SHA}, {'path': str(MANIFEST), 'sha256': MANIFEST_SHA}
    result = extract(raw, json.loads(manifest_raw), filing_ref, manifest_ref)
    sources = {**LOADED, str(FILING): FILING_SHA, str(MANIFEST): MANIFEST_SHA}
    strict(sources)
    result['source_hashes'] = sources
    return result


def durable(path, raw):
    with path.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def publish():
    require(not OUTPUT.exists(), 'Fixed namespace exists; no overwrite or retry')
    result = build()
    strict(result['source_hashes'])
    OUTPUT.mkdir(parents=True, exist_ok=False)
    try:
        raw = encoded(result)
        path = OUTPUT / 'identity.json'
        durable(path, raw)
        strict(result['source_hashes'])
        require(path.read_bytes() == raw and {p.name for p in OUTPUT.iterdir()} == {'identity.json'}, 'Publication readback/orphan failure')
        reference = {'path': str(path), 'sha256': digest(raw)}
        receipt = encoded({'schema': 'TSM_CONDITIONAL_IDENTITY_PUBLICATION_V1', 'identity_reference': reference,
                           'source_hashes': result['source_hashes'], 'status': 'PUBLISHED_CONDITIONAL_SID_SIDECAR_ONLY'})
        durable(OUTPUT / 'publication.json', receipt)
        strict(result['source_hashes'])
        require(path.read_bytes() == raw and (OUTPUT / 'publication.json').read_bytes() == receipt
                and {p.name for p in OUTPUT.iterdir()} == {'identity.json', 'publication.json'}, 'Final publication readback/orphan failure')
        return dict(reference, publication_sha256=digest(receipt))
    except Exception as error:
        durable(OUTPUT / 'failure.json', encoded({'status': 'FAILED_NOT_CONSUMABLE', 'error': str(error), 'retry_allowed': False}))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', help='Publish this new conditional sidecar once')
    args = parser.parse_args()
    if not args.execute:
        parser.error('Explicit --execute required; no implicit build')
    print(json.dumps(publish(), indent=2))
