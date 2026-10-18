"""Date-routed FISV/FI nominal-cache coverage only; never a merged price panel."""
import csv
from datetime import date
from fractions import Fraction
import hashlib
import io
import json
from pathlib import Path
import yaml


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT/'tmp/historical_rename_coverage_20261014_v1'
COVERAGE = 'tmp/historical_proxy_ohlc_coverage_20261014_v1/coverage.json'
AUDIT = 'tmp/historical_proxy_ohlc_coverage_20261014_v1/raw_cache_supplement_audit.json'
LIFECYCLE = 'config/ndx_security_lifecycle.yaml'
PANEL = 'tmp/current_ohlc_actual_projection_20261013_v1/panel.json'
RAW = 'data/cache/candidate_pools/ndx_fundamentals/price_basis_v1/raw/'
PINS = {
    COVERAGE: 'eaa2d8e9b958226e34ed39013f425188a27dc21861d8e0a2af602574bee43f51',
    AUDIT: '4ac4d856d196d309e5ac33c6906685da6e100212ecea3f3fd63fbee5b39fb969',
    LIFECYCLE: '8505e22f1c18b4a691d8b14bdb1dfc382dda8c59721201fb3276617a3a639179',
    PANEL: '92361a7321765594a5544ab3cb9128410c8296799d99b3d23090e24a37df9822',
    RAW+'FISV.csv': '2e970c697398ae2ebf0454a9c65df659df2ed69be0228ca35c4cd4338ebbcfa2',
    RAW+'FI.csv': '0961863ff95574bffa06f282ac9d3f5d684ef3c5c008622495ffd614cb5b5f97',
    RAW+'FISV.csv.manifest.json': 'd982b7caab223969da9fcf10fd7c1eaf81e139f758565360c103eea7effb98b4',
    RAW+'FI.csv.manifest.json': '193d88e556e210dcae2210708682fa1b46bba099b04208626a3da00bc9630ac4',
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def validate_rule(rule):
    require(rule['rule_id']=='fiserv_fisv_to_fi_2023' and rule['cik']=='0000798354'
            and rule['cusip']=='337738108' and set(rule['recognized_tickers'])=={'FISV', 'FI'}, 'Wrong identity rule')
    intervals = [{key: str(value) if value is not None else None for key, value in row.items()}
                 for row in rule['intervals']]
    require(intervals==[dict(effective_from=None, effective_to='2023-06-06', price_ticker='FISV'),
                        dict(effective_from='2023-06-07', effective_to=None, price_ticker='FI')], 'Wrong rename boundary')
    return intervals


def read_cache(raw, manifest, ticker):
    require(manifest['content_sha256']==sha(raw) and manifest['content_bytes']==len(raw), 'Raw hash/size mismatch')
    require(manifest['dataset_key']==ticker and manifest['price_basis']=='unadjusted_nominal_trade_price'
            and manifest['corporate_action_adjustment']=='none' and manifest['valuation_use_only'] is True,
            'Nominal valuation-only source contract required')
    rows = list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
    dates = [row['Date'] for row in rows]
    require(dates and dates==sorted(set(dates)) and len(rows)==manifest['row_count'], 'Duplicate/date/count mismatch')
    require(dates[0]==manifest['data_start'] and dates[-1]==manifest['data_end'], 'Manifest date range mismatch')
    result = {}
    for row in rows:
        day = row['Date']
        require(date.fromisoformat(day).isoformat()==day, 'Canonical date required')
        try:
            o, h, l, c = [Fraction(row[key]) for key in ('Open', 'High', 'Low', 'Close')]
        except (ValueError, ZeroDivisionError) as error:
            raise ValueError('Invalid observed OHLC') from error
        require(0 < l <= min(o,c) <= max(o,c) <= h, 'Invalid observed OHLC range')
        result[day] = {key: row[key] for key in ('Open', 'High', 'Low', 'Close')}
    return result


def map_dates(dates, caches):
    rows = []
    for day in dates:
        require(date.fromisoformat(day).isoformat()==day, 'Canonical requested date required')
        ticker = 'FISV' if day <= '2023-06-06' else 'FI'
        require(ticker in caches, 'Missing required date-specific source; alias fallback forbidden')
        values = caches[ticker].get(day)
        rows.append(dict(session=day, price_ticker=ticker, raw_source_path=RAW+ticker+'.csv',
                         source_row_date=day if values is not None else None,
                         present=values is not None, reason=None if values is not None else 'DATE_MISSING_IN_REQUIRED_SOURCE'))
    return rows


def main():
    require(not OUTPUT.exists(), 'Create-only output already exists')
    sources = {path: (ROOT/path).read_bytes() for path in PINS}
    require(all(sha(raw)==PINS[path] for path, raw in sources.items()), 'Pinned input changed')
    coverage, audit, panel = [json.loads(sources[path]) for path in (COVERAGE, AUDIT, PANEL)]
    rule = next(row for row in yaml.safe_load(sources[LIFECYCLE])['rules'] if row['rule_id']=='fiserv_fisv_to_fi_2023')
    intervals = validate_rule(rule)
    caches, manifests = {}, {}
    for ticker in ('FISV', 'FI'):
        manifests[ticker] = json.loads(sources[RAW+ticker+'.csv.manifest.json'])
        caches[ticker] = read_cache(sources[RAW+ticker+'.csv'], manifests[ticker], ticker)
    audit_hashes = {path.replace('\\','/'): value for path, value in audit['source_hashes'].items()}
    require(audit_hashes[COVERAGE]==PINS[COVERAGE] and audit_hashes[PANEL]==PINS[PANEL]
            and audit_hashes[RAW+'FISV.csv']==PINS[RAW+'FISV.csv'], 'Prior audit binding mismatch')
    require(len(coverage['dates'])==len(audit['dates'])==15, 'All fifteen cutoffs required')
    calendar = panel['calendar']
    require(calendar==sorted(set(calendar)), 'Unique unchanged calendar required')
    outcomes = []
    for original, prior in zip(coverage['dates'], audit['dates']):
        cutoff = original['decision_cutoff']
        require(cutoff==prior['decision_cutoff'] and original['proxy_security_count']==prior['proxy_security_count']==len(original['rows']), 'Full original denominator mismatch')
        next_dates = [day for day in calendar if day > cutoff][:21]
        require(len(next_dates)==21 and next_dates[0]==prior['next21_first'] and next_dates[-1]==prior['next21_last'], 'Next21 calendar differs')
        mapped = map_dates(next_dates, caches)
        members = [row for row in original['rows'] if row['ticker']=='FISV']
        require(len(members)<=1, 'Duplicate FISV denominator entry')
        applicable = bool(members)
        before = None
        if applicable:
            member = members[0]
            require(member['cusip']==rule['cusip'] and member['existing_local_security_id']=='security:'+rule['cik']+':'+rule['cusip'], 'Proxy CIK/CUSIP identity conflict')
            old = next(row for row in prior['rows'] if row['ticker']=='FISV')
            before = old['complete_next21_ohlc']
            require(old['next21_missing_dates']==[day for day in next_dates if day not in caches['FISV']], 'Old FISV missing-date audit differs')
        complete = all(row['present'] for row in mapped)
        improvement = int(applicable and complete and not before)
        remaining = [ticker for ticker in prior['remaining_missing_tickers'] if not (ticker=='FISV' and improvement)]
        outcomes.append(dict(decision_cutoff=cutoff, proxy_security_count=original['proxy_security_count'],
            original_member_tickers=[row['ticker'] for row in original['rows']],
            fisv_in_proxy=applicable, mapping_scope='APPLICABLE_EXISTING_MEMBER' if applicable else 'DIAGNOSTIC_ONLY_NOT_ADDED_TO_DENOMINATOR',
            old_fisv_complete_next21=before, mapped_next21_complete=complete,
            next21_date_mapping=mapped, mapped_missing_dates=[row['session'] for row in mapped if not row['present']],
            before_numeric_coverage_count=prior['conditional_combined_next21_numeric_count'],
            after_numeric_coverage_count=prior['conditional_combined_next21_numeric_count']+improvement,
            coverage_improvement_count=improvement, remaining_missing_tickers=remaining))
    result = dict(status='COMPLETE_DATE_ROUTED_NOMINAL_COVERAGE_DIAGNOSTIC', dates=outcomes,
        source_hashes=PINS, script_sha256=sha(Path(__file__).read_bytes()),
        identity_rule=dict(rule_id=rule['rule_id'], cik=rule['cik'], cusip=rule['cusip'], intervals=intervals),
        identity_scope='LOCAL_LIFECYCLE_RULE_AND_PROXY_CIK_CUSIP_CONSISTENCY_ONLY',
        evidence_available_at=None, evidence_available_at_inferred=False,
        manifest_fetched_at={ticker: row['fetched_at'] for ticker, row in manifests.items()},
        price_basis='unadjusted_nominal_trade_price', corporate_action_adjustment='none', valuation_use_only=True,
        member_denominator_preserved=True, cutoff_count=15,
        improved_cutoffs=[row['decision_cutoff'] for row in outcomes if row['coverage_improvement_count']],
        provider_identity_authenticated=False, formal_pit_eligible=False, adjusted_return_use_allowed=False,
        total_return_verified=False, original_panel_modified=False, price_channels_synthesized=False,
        strategy_runs=0, book_calls=0, network_calls=0)
    require(all(sha((ROOT/path).read_bytes())==digest for path, digest in PINS.items()), 'Inputs changed during read-only diagnostic')
    OUTPUT.mkdir()
    raw = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8')
    with (OUTPUT/'result.json').open('xb') as stream:
        stream.write(raw)
    print(json.dumps(dict(result=str(OUTPUT/'result.json'), sha256=sha(raw), improved_cutoffs=result['improved_cutoffs'])))


if __name__ == '__main__':
    main()
