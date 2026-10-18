"""Audit full historical NPORT proxy gaps; never call it exact NDX membership."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.ndx_joint_weight_verify import _restore_input

INVENTORY = ROOT / 'data/cache/research/dynamic_fractional_frontiers_v1/inventory_20260912.json'
INVENTORY_SHA = '8ec2ab2d22c2441190606f301e62380c93345a7c66f9ad8987c3dd229eee124d'
INDEX = ROOT / 'data/cache/research/dynamic_frozen_v2/training_plan_index_20260911.json'
INDEX_SHA = 'afaccee2fedb481747bb5b0c5ef1d483dfa852980c79dcd34a7091a8e2f970b0'
_LOADED = {str((ROOT / name).resolve()): hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    for name in ('scripts/ndx_full_membership_coverage_research.py', 'scripts/ndx_joint_weight_verify.py',
                 'backtest/ndx_joint_weight_runner.py')}


def verify_sources(sources):
    for path, expected in sources.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
            raise ValueError('Coverage source drift: ' + path)


def validate_inventory(inventory):
    reports = inventory['reports']
    if len(reports) != 15 or inventory['date_count'] != 15 or inventory['record_count'] != 351255:
        raise ValueError('Explicit complete historical inventory required')
    coordinates = [tuple(row['coordinate'][key] for key in ('source_batch', 'universe_track', 'selection_date')) for row in reports]
    dates = [coordinate[-1] for coordinate in coordinates]
    if len(set(coordinates)) != 15 or dates != sorted(set(dates)):
        raise ValueError('Unique strictly increasing full inventory dates required')
    if sum(row['counts']['expected_task_count'] for row in reports) != 351255:
        raise ValueError('Inventory full task denominator differs')


def snapshot_asof(history, day):
    """Use filing availability, retaining CUSIP strings and all securities."""
    eligible = history.loc[history.available_date <= day]
    if eligible.empty:
        raise ValueError('No public NPORT proxy available by explicit cutoff')
    latest = eligible.available_date.max()
    snapshot = eligible.loc[eligible.available_date == latest].copy()
    if (snapshot.report_date.nunique() != 1 or snapshot.accession_number.nunique() != 1
            or snapshot.cusip.duplicated().any() or snapshot.ticker.duplicated().any()):
        raise ValueError('Ambiguous or duplicate NPORT snapshot')
    return snapshot


def audit_snapshot(snapshot, *, cutoff, universe, returns, nominal, identities, taxonomy):
    old_names = set(universe.ticker)
    candidates = []
    issuers = set()
    for proxy in snapshot.to_dict('records'):
        matches = identities.loc[(identities.cusip == proxy['cusip']) & (identities.available_from <= cutoff)]
        declarations = set(matches[['security_id', 'issuer_id', 'identity_status']].itertuples(index=False, name=None))
        resolved = len(declarations) == 1 and next(iter(declarations))[2] == 'resolved'
        sid = str(matches.iloc[0].security_id) if resolved else None
        issuer = str(matches.iloc[0].issuer_id) if resolved else None
        if issuer:
            issuers.add(issuer)
        risk = taxonomy.loc[(taxonomy.security_id == sid) & (taxonomy.status == 'accepted')
            & (taxonomy.evidence_available_date != '') & (taxonomy.evidence_available_date.str[:10] <= cutoff)] if sid else taxonomy.iloc[:0]
        risk = risk.loc[risk.selection_dates.str.split(';').map(lambda dates: proxy['available_date'] in dates)]
        risk_values = sorted(set(risk.risk_chain) - {'', 'unclassified'})
        candidates.append(dict(ticker=proxy['ticker'], cusip=proxy['cusip'], isin=proxy['isin'],
            name=proxy['name'], source_report_date=proxy['report_date'], source_available_date=proxy['available_date'],
            in_old_trained_universe=proxy['ticker'] in old_names,
            return_column_in_old_frozen_inputs=proxy['ticker'] in returns.columns,
            nominal_column_in_old_frozen_inputs=proxy['ticker'] in nominal.columns,
            local_identity_mapping_status='RESOLVED_LOCAL_MAPPING_NOT_PIT_AUTHENTICATED' if resolved else 'UNRESOLVED_OR_AMBIGUOUS',
            security_id=sid, issuer_id=issuer, local_risk_chain_evidence=risk_values,
            unambiguous_local_risk_evidence=len(risk_values) == 1,
            exact_membership_verified=False, provider_price_identity_verified=False))
    return dict(proxy_security_count=len(candidates), locally_mapped_issuer_count=len(issuers),
        full_issuer_upper_bound_verified=False, exact_membership_security_count=None, exact_membership_issuer_count=None,
        old_trained_security_count=len(universe), old_trained_issuer_count=universe.issuer_id.nunique(),
        added_proxy_tickers=sorted(set(snapshot.ticker) - old_names),
        old_trained_tickers_not_in_proxy=sorted(old_names - set(snapshot.ticker)),
        missing_return_columns_in_old_inputs=[row['ticker'] for row in candidates if not row['return_column_in_old_frozen_inputs']],
        missing_nominal_columns_in_old_inputs=[row['ticker'] for row in candidates if not row['nominal_column_in_old_frozen_inputs']],
        unresolved_local_identity_tickers=[row['ticker'] for row in candidates if row['security_id'] is None],
        unresolved_local_risk_tickers=[row['ticker'] for row in candidates if not row['unambiguous_local_risk_evidence']],
        candidates=candidates)


def run():
    verify_sources(_LOADED)
    sources = dict(_LOADED)
    def read(path, expected=None):
        path = Path(path).resolve()
        raw = path.read_bytes()
        actual = hashlib.sha256(raw).hexdigest()
        if expected is not None and actual != expected:
            raise ValueError('Bound coverage source changed: ' + str(path))
        if str(path) in sources and sources[str(path)] != actual:
            raise ValueError('Coverage source changed during read')
        sources[str(path)] = actual
        return raw
    def csv(path):
        path = Path(path)
        manifest = json.loads(read(str(path) + '.manifest.json'))
        raw = read(path, manifest['content_sha256'])
        frame = pd.read_csv(io.BytesIO(raw), dtype=str, keep_default_na=False)
        if len(frame) != manifest['row_count']:
            raise ValueError('CSV manifest denominator differs')
        return frame
    inventory = json.loads(read(INVENTORY, INVENTORY_SHA))
    indexed = json.loads(read(INDEX, INDEX_SHA))
    validate_inventory(inventory)
    base = ROOT / 'data/cache/candidate_pools'
    history = csv(base / 'ndx_history/qqq_nport_constituents.csv')
    identities = csv(base / 'ndx_taxonomy_v2/security_identity.csv')
    taxonomy = csv(base / 'ndx_taxonomy_v2/taxonomy_records.csv')
    events = csv(base / 'ndx_history/exact_events/exact_events.csv')
    event_gaps = csv(base / 'ndx_history/exact_events/unresolved_gaps.csv')
    proxy_gaps = csv(base / 'ndx_history/event_proxy_audit/unresolved_proxy_gaps.csv')
    for row in events.to_dict('records'):
        if row['raw_path']:
            read(base / 'ndx_history/exact_events' / row['raw_path'], row['content_sha256'])
    dates = []
    for descriptor in inventory['reports']:
        coordinate = descriptor['coordinate']
        matching = [row for row in indexed['coordinates'] if all(row[key] == value for key, value in coordinate.items()) and row['context_sha256']]
        if not matching:
            raise ValueError('Missing bound old training context')
        sha = matching[0]['context_sha256']
        context = json.loads(read(ROOT / 'data/cache/research/ndx_joint_weight_runs_v3' / sha / 'context.json', sha))
        inputs = {key: _restore_input(value) for key, value in context['prepared_inputs'].items()}
        cutoff = inputs['returns'].index[-1].date().isoformat()
        proxy = snapshot_asof(history, cutoff)
        execution_proxy = snapshot_asof(history, coordinate['selection_date'])
        report_day = proxy.report_date.iloc[0]
        changes = events.loc[(events.effective_date > report_day) & (events.effective_date <= cutoff)
            & (events.source_available_date <= cutoff) & events.action.isin(['add', 'remove'])]
        details = audit_snapshot(proxy, cutoff=cutoff, universe=inputs['universe'], returns=inputs['returns'],
            nominal=inputs['nominal_prices'], identities=identities, taxonomy=taxonomy)
        dates.append(dict(coordinate=coordinate, decision_cutoff=cutoff, old_context_sha256=sha,
            proxy_report_date=report_day, proxy_available_date=proxy.available_date.iloc[0],
            execution_day_proxy_available_date=execution_proxy.available_date.iloc[0],
            execution_day_only_proxy_tickers=sorted(set(execution_proxy.ticker) - set(proxy.ticker)),
            execution_day_snapshot_changed=proxy.available_date.iloc[0] != execution_proxy.available_date.iloc[0],
            official_event_actions_since_proxy_report=changes[['event_id','effective_date','source_available_date','action','ticker']].to_dict('records'),
            **details))
    verify_sources(sources)
    return dict(schema='ndx_full_membership_coverage_research_v1', requested_universe_scope='ALL_POINT_IN_TIME_NASDAQ100_MEMBERS',
        source_hashes=sources, dates=dates, date_count=len(dates), old_completed_training_records=351255,
        old_completed_evidence_reused_without_rerun=True, membership_mode='LAST_PUBLIC_NPORT_PROXY_AVAILABLE_BY_DECISION_CUTOFF',
        source_event_gaps=event_gaps.to_dict('records'), source_proxy_gaps=proxy_gaps.to_dict('records'),
        exact_daily_membership_verified=False, exact_issuer_k_upper_bound_verified=False,
        current_constituents_backfilled=False, local_mapping_is_external_identity_authentication=False,
        data_gap_scope='ABSENCE_FROM_OLD_FROZEN_INPUT_COLUMNS_NOT_GLOBAL_CACHE_UNAVAILABILITY',
        training_or_refit_performed=False, execution_performed=False, promotion_allowed=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    destination = Path(args.output).resolve()
    if (ROOT / 'data/cache/research').resolve() not in destination.parents:
        raise ValueError('Research output required')
    result = run()
    content = (json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('xb') as stream:
        stream.write(content)
    if destination.read_bytes() != content:
        raise ValueError('Coverage artifact readback differs')
    verify_sources(result['source_hashes'])
    print(json.dumps(dict(path=str(destination), sha256=hashlib.sha256(content).hexdigest(), dates=[
        {key: row[key] for key in ('coordinate','decision_cutoff','proxy_security_count','locally_mapped_issuer_count',
            'old_trained_security_count','execution_day_snapshot_changed')} for row in result['dates']]), indent=2))
