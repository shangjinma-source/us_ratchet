"""Read candidate SEC identities for nine uncovered current symbols; no alias admission."""
from concurrent.futures import ThreadPoolExecutor
import csv
import hashlib
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import ndx_current_component_evidence_research as transport
from scripts.ndx_current_22_price_capture_20260919 import save

BASE = ROOT / 'data/cache'
OUTPUT = BASE / 'research/current_nine_identity_capture_20260919_v1'
OBS = BASE / 'research/ndx_current_quote_list_capture_20260919_v1/observation.json'
OBS_SHA = '50cbca76647e14d99f4990deff0c6adc7226f31109393df2fa0298b062fc5c77'
NAMES = {
    'TER': ['TERADYNE INC', 'TERADYNE, INC'],
    'NBIS': ['NEBIUS GROUP N.V.'],
    'LITE': ['LUMENTUM HOLDINGS INC.'],
    'RKLB': ['ROCKET LAB CORP', 'ROCKET LAB USA, INC.'],
    'ALAB': ['ASTERA LABS, INC.'],
    'SNDK': ['SANDISK CORP'],
    'CRWV': ['COREWEAVE, INC.'],
    'SPCX': ['SPACE EXPLORATION TECHNOLOGIES CORP'],
    'HONA': ['HONEYWELL AEROSPACE INC.', 'HONEYWELL AEROSPACE LLC'],
}


def build_plan():
    source = Path(__file__).resolve()
    lookup = BASE / 'candidate_pools/ndx_fundamentals/sec_cik_lookup_data.txt'
    history = BASE / 'candidate_pools/ndx_taxonomy_v2/security_identity.csv'
    current = BASE / 'candidate_pools/ndx_taxonomy_v2/current_review_20260713/current_target_universe.csv'
    paths = (source, OBS, lookup, history, current, Path(transport.__file__).resolve(),
             ROOT / 'scripts/ndx_current_22_price_capture_20260919.py')
    sources = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    if sources[str(OBS)] != OBS_SHA:
        raise ValueError('Hard current observation differs')
    symbols = json.loads(OBS.read_bytes())['observed_symbols']
    old = list(csv.DictReader(current.open(encoding='utf-8-sig')))
    identities = list(csv.DictReader(history.open(encoding='utf-8-sig')))
    old_known = {row['ticker'] for row in old if row['cik']}
    historical_known = {symbol for row in identities for symbol in row['ticker_set'].split(';')}
    if set(symbols) - old_known != set(NAMES) or set(symbols) - historical_known != set(NAMES):
        raise ValueError('Original two identity tables no longer have the exact nine gaps')
    wanted = {name for names in NAMES.values() for name in names}
    matches = {name: [] for name in wanted}
    for line in lookup.read_text(encoding='utf-8-sig').splitlines():
        pieces = line.rsplit(':', 2)
        if len(pieces) == 3 and pieces[0] in wanted:
            if len(pieces[1]) != 10 or not pieces[1].isdigit() or pieces[2]:
                raise ValueError('Named SEC lookup row format differs')
            matches[pieces[0]].append(pieces[1])
    if any(not ciks for ciks in matches.values()):
        raise ValueError('Declared local name candidate not present')
    rows = [dict(ticker=ticker, local_name_matches={name: matches[name] for name in names},
                 candidate_ciks=sorted({cik for name in names for cik in matches[name]}),
                 name_match_is_ticker_binding=False) for ticker, names in NAMES.items()]
    ciks = sorted({cik for row in rows for cik in row['candidate_ciks']})
    if len(ciks) != 11:
        raise ValueError('Expected eleven distinct candidate CIKs, including two ambiguities')
    return dict(schema='CURRENT_NINE_CANDIDATE_IDENTITY_QUERY_PLAN_V1', rows=rows,
                query_ciks=ciks, source_hashes=sources, historical_identity_verified=False,
                current_security_identity_verified=False, point_in_time_verified=False,
                promotion_allowed=False, historical_alias_join_allowed=False)


if __name__ == '__main__':
    plan = build_plan()
    OUTPUT.mkdir(parents=True, exist_ok=False)
    plan_path = OUTPUT / 'plan.json'
    plan_sha = save(plan_path, plan)
    transport.OUTPUT = OUTPUT
    requests = [(cik, 'https://data.sec.gov/submissions/CIK' + cik + '.json') for cik in plan['query_ciks']]
    with ThreadPoolExecutor(max_workers=2) as pool:
        captures = list(pool.map(transport.capture, requests))
    for path, expected in plan['source_hashes'].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
            raise ValueError('Identity query source changed')
    path = OUTPUT / 'manifest.json'
    digest = save(path, dict(schema='CURRENT_NINE_CANDIDATE_IDENTITY_RAW_CAPTURE_V1',
                            plan_path=str(plan_path), plan_sha256=plan_sha, captures=captures,
                            source_hashes=plan['source_hashes'], current_identity_adjudicated=False,
                            historical_identity_verified=False, point_in_time_verified=False,
                            promotion_allowed=False))
    print(json.dumps(dict(path=str(path), sha256=digest,
                          statuses=[(row['name'], row.get('http_status')) for row in captures])))
