"""Dated raw business statements and conditional taxonomy suggestions, no admission."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import yaml
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import ndx_pcar_cprt_conditional_identity_20260923 as identity
from scripts.ndx_corrected_frontier_single_refit_archive_research import publish

TAXONOMY = ROOT / 'config/candidate_taxonomy_v2.yaml'
TAXONOMY_SHA = '3f1457a3d2de4b41f8e885ff4efb6e0f4191cf1b4463f979fb05b83af7cc1cc6'
BASE = ROOT / 'data/cache/research/local_business_excerpt_research_20260912_v1'
SUGGESTIONS = BASE / 'nontechnology_business_suggestions_20260912.json'
SUGGESTIONS_SHA = '22f9cd5073989a41f59cfba159d562da95d69dad91e9c8f32a75c415dfefdcbc'
REVIEW = BASE / 'nontechnology_business_independent_review_20260912.json'
REVIEW_SHA = '944107267a24bb3fada56d7362fce89101ab4f27f8f2a88199457a1de17a381b'
FALSE = ('risk_chain_assigned', 'classification_uniquely_proven', 'current_interval_verified',
    'segment_revenue_dominance_verified', 'source_publication_time_verified', 'point_in_time_verified',
    'provider_security_binding_verified', 'legal_training_input_ready', 'promotion_allowed',
    'execution_authorized', 'fit_performed', 'existing_panel_modified', 'prior_reports_transitive_sources_reverified')
CLAUSES = {
    'PCAR': [
        '(1) The Truck segment includes the design, manufacture and distribution of high-quality, light-, medium- and heavy-duty commercial trucks.',
        '(2) The Parts segment includes the distribution of aftermarket parts for trucks and related commercial vehicles.',
        '(3) The Financial Services segment includes finance and leasing products and services provided to customers and dealers.',
        'The Company also designs and manufactures diesel engines, primarily for use in the',
    ],
    'CPRT': [
        'We are a leading global provider of online auctions and vehicle remarketing services with operations in the United States',
        'We provide vehicle sellers with a full range of services to process and sell vehicles primarily over the internet through our Virtual Bidding Third Generation internet auction-style sales technology, which we refer to as VB3.',
        'Vehicle sellers consist primarily of insurance companies, but also include banks, finance companies, charities, fleet operators, dealers, vehicle rental companies, and individuals.',
    ],
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


LOADED = {**identity.LOADED, str(Path(__file__).resolve()): sha(__file__)}


def extract(ticker, raw):
    spec = identity.CASES[ticker]
    soup = BeautifulSoup(raw.decode('utf-8'), 'lxml')
    fields = {}
    for name, value in {'entitycentralindexkey': spec['cik'], 'entityregistrantname': spec['company'],
        'tradingsymbol': ticker, 'documentperiodenddate': spec['period'], 'security12btitle': spec['title']}.items():
        nodes = [n for n in soup.find_all(attrs={'name': True}) if n['name'].lower() == 'dei:' + name]
        if len(nodes) != 1 or nodes[0].get('contextref') != spec['context'] or ' '.join(nodes[0].get_text(' ', strip=True).split()) != value:
            raise ValueError('Unique same-context dated issuer cover required')
        fields[name] = dict(text=value, context=spec['context'])
    text = ' '.join(soup.get_text(' ', strip=True).split())
    section_offset = 0
    if ticker == 'CPRT':
        heading = 'Item 1. Business Corporate Information'
        if text.count(heading) != 1:
            raise ValueError('Unique operative business section required')
        section_offset = text.index(heading)
        end = text.find('Item 1A. Risk Factors', section_offset)
        if end < 0:
            raise ValueError('Business section closing heading required')
        text = text[section_offset:end]
    evidence = []
    for clause in CLAUSES[ticker]:
        if text.count(clause) != 1:
            raise ValueError('Unique operative business clause required')
        start = text.index(clause)
        end = start + len(clause)
        # Preserve the complete source sentence, including original encoding artifacts.
        if not clause.endswith('.'):
            marker = 'PACCAR competes in the North American' if ticker == 'PCAR' else 'Our goals are to generate'
            end = text.find(marker, end)
            if end < 0:
                raise ValueError('Full sentence boundary missing')
        original = text[start:end].strip()
        evidence.append(dict(marker=clause, normalized_text_offset=section_offset + start, original_text=original,
            text_sha256=hashlib.sha256(original.encode()).hexdigest()))
    return dict(ticker=ticker, issuer_id='issuer:' + spec['cik'], original_cover_fields=fields,
        original_business_clauses=evidence, text_normalization='HTML_TEXT_WHITESPACE_ONLY_NO_ENCODING_REPAIR',
        section_locator='Item 1. Business Corporate Information -> Item 1A. Risk Factors' if ticker == 'CPRT' else 'UNIQUE_EXACT_OPERATIVE_CLAUSES_IN_COMPLETE_DOCUMENT',
        section_normalized_start_offset=section_offset,
        annual_period_text=spec['period'], annual_filing_date=None, annual_receipt_time=None)


def classify(rows, taxonomy, prior_suggestion, prior_review):
    required = ['internet_ecommerce', 'automotive', 'industrial']
    if any(k not in taxonomy or not isinstance(taxonomy[k].get('description'), str) for k in required):
        raise ValueError('Original taxonomy definitions required')
    if prior_suggestion['document_ticker_label'] != 'CPRT' or prior_suggestion['suggested_risk_chain'] != required[0] or prior_suggestion['alternative_risk_chains'] != required[1:] or prior_suggestion['risk_chain_assigned'] is not False:
        raise ValueError('Preserve original CPRT alternatives')
    if prior_review['ticker'] != 'CPRT' or prior_review['boundary_status'] != 'UNRESOLVED_EXISTING_ALTERNATIVES' or prior_review['automatic_adoption_allowed'] is not False:
        raise ValueError('Preserve unresolved independent review')
    if [row['ticker'] for row in rows] != ['PCAR', 'CPRT']:
        raise ValueError('Both complete business rows required')
    result = []
    for row in rows:
        pcar = row['ticker'] == 'PCAR'
        result.append(dict(row, conditional_suggested_risk_chain='automotive' if pcar else 'internet_ecommerce',
            candidate_risk_chains=['automotive'] if pcar else required,
            assigned_risk_chain=None, boundary_status='CONDITIONAL_SUGGESTION_REQUIRES_INDEPENDENT_REVIEW' if pcar else 'UNRESOLVED_EXISTING_ALTERNATIVES',
            rationale='Commercial trucks and aftermarket vehicle parts directly support the automotive definition; finance and industrial products remain additional exposures, and no revenue dominance is inferred.' if pcar else 'Online vehicle auctions support a market-platform hypothesis, but automotive versus industrial service alternatives remain unresolved.',
            prior_suggestion=prior_suggestion if not pcar else None, prior_independent_review=prior_review if not pcar else None,
            **dict.fromkeys(FALSE, False)))
    return result


def verify_sources(sources):
    if any(sources.get(p) != h for p, h in LOADED.items()):
        raise ValueError('Loaded source missing or changed')
    for path, expected in sources.items():
        if sha(path) != expected:
            raise ValueError('Source bytes changed: ' + path)


def build():
    sources = {**LOADED, str(TAXONOMY): TAXONOMY_SHA, str(SUGGESTIONS): SUGGESTIONS_SHA, str(REVIEW): REVIEW_SHA}
    for spec in identity.CASES.values():
        sources[str(ROOT / 'data/cache/candidate_pools/ndx_taxonomy_v2/raw_sec' / spec['cover'])] = spec['cover_sha']
    verify_sources(sources)
    rows = [extract(t, (ROOT / 'data/cache/candidate_pools/ndx_taxonomy_v2/raw_sec' / s['cover']).read_bytes()) for t,s in identity.CASES.items()]
    suggestions = [r for r in json.loads(SUGGESTIONS.read_text(encoding='utf-8'))['suggestions'] if r['document_ticker_label'] == 'CPRT']
    reviews = [r for r in json.loads(REVIEW.read_text(encoding='utf-8'))['rows'] if r['ticker'] == 'CPRT']
    if len(suggestions) != 1 or len(reviews) != 1:
        raise ValueError('Unique original CPRT history required')
    taxonomy = yaml.safe_load(TAXONOMY.read_bytes())['risk_chains']
    rows = classify(rows, taxonomy, suggestions[0], reviews[0])
    verify_sources(sources)
    return dict(schema='PCAR_CPRT_DATED_BUSINESS_FACTS_AND_CONDITIONAL_SUGGESTIONS_V1', rows=rows,
        security_count=2, taxonomy_definitions={k:taxonomy[k] for k in ('automotive','industrial','internet_ecommerce')},
        source_hashes=sources, prior_reports_usage='HARD_ARTIFACT_HISTORICAL_DECLARATIONS_ONLY_DIRECT_ANNUAL_BYTES_REEXTRACTED',
        date_role='ANNUAL_PERIOD_NOT_FILING_OR_JOINT_AVAILABILITY', **dict.fromkeys(FALSE, False))


def verify(value):
    if identity.canonical(value) != identity.canonical(build()):
        raise ValueError('Complete business evidence rebuild differs')
    verify_sources(value['source_hashes'])


def publish_verified(path, value):
    verify(value)
    ref = publish(path, value)
    verify_sources(value['source_hashes'])
    return ref


if __name__ == '__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--output', required=True); args=parser.parse_args()
    print(json.dumps(publish_verified(args.output, build())))
