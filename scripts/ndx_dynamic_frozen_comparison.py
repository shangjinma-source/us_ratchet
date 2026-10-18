"""Compare explicit execution diagnostics; never select/admit a winner."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.ndx_dynamic_frozen_input_probe import _check_sources

DIRECTORY = ROOT/'data/cache/research/dynamic_frozen_v2'
REPORTS = {
    'RETURN': ('strict_return_20260911.json', 'bc991ddc992bae2171d69338095e77a98a041cca3adcb375daa761386d5c6a56'),
    'USER_PREFERENCE': ('strict_user_preference_20260911.json', 'e5f4919f2819404d26e8148c995e34de611d26463f93e3d0689a224b5b545892'),
    'INCUMBENT': ('strict_return_control_20260911.json', '87b081061374a368c0c7d1b6a3d953ba964c3ac2e30d56f3a7173e21d1c3b58b'),
    '012922': ('strict_return_nav_20260911.json', 'fb8f5c36001e3e235b6c0b99e3641a7f8a06ca8a248ef07fd9076409e782b08d'),
}


def compare():
    loaded, sources = {}, {}
    for role, (name, digest) in REPORTS.items():
        path = DIRECTORY/name
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError('Comparison report identity differs: '+role)
        report = json.loads(raw)
        if report['promotion_allowed'] is not False:
            raise ValueError('Research-only report required')
        for source, value in report['source_hashes'].items():
            if source in sources and sources[source] != value:
                raise ValueError('Conflicting source versions')
            sources[source] = value
        sources[str(path)] = digest
        loaded[role] = report
    control = loaded['INCUMBENT']['execution']
    dates = [row['session'] for row in control['daily']]
    clock = [(row['decision_date'], row['execution_date']) for row in control['decisions']]
    rows = []
    for role in ('RETURN', 'USER_PREFERENCE', 'INCUMBENT'):
        execution = loaded[role]['execution']
        if ([row['session'] for row in execution['daily']] != dates
                or [(row['decision_date'], row['execution_date']) for row in execution['decisions']] != clock
                or execution['execution_policy'] != control['execution_policy']
                or execution['daily'][0]['total_value_usd'] != control['daily'][0]['total_value_usd']):
            raise ValueError('Execution comparison coordinates differ')
        if role == 'USER_PREFERENCE' and any(
                {target['ticker'] for target in row['targets'].values()} != {'AMAT','AVGO','CDNS','GOOG'}
                for row in execution['decisions']):
            raise ValueError('User preference identity differs')
        summary = execution['summary']
        rows.append(dict(role=role, path_return=summary['path_return_net'],
            annualized_return_252_session=(1+summary['path_return_net'])**(252/(len(dates)-1))-1,
            path_max_drawdown=summary['path_max_drawdown'],
            fees_usd=sum(row['transaction_cost_usd'] for row in execution['trades']),
            invested_risk_failure_days=sum(any(row['shares'].values()) and not row['risk']['all_passed']
                                           for row in execution['daily']),
            target_cardinalities=sorted(set(summary['k_path']))))
    nav = loaded['012922']
    if [row['session'] for row in nav['rows']] != dates:
        raise ValueError('NAV comparison dates differ')
    rows.append({key: nav[key] for key in ('role', 'path_return', 'annualized_return_252_session',
                                         'path_max_drawdown')})
    _check_sources(sources)
    return dict(rows=rows, source_hashes=sources, date_start=dates[0], date_end=dates[-1],
        historical_diagnostic_only=True, current_pool_reselected=False,
        candidate_search_exhaustive=False, independent_oos=False,
        nav_currency_and_publication_equivalence_verified=False,
        winner_selected=False, promotion_allowed=False)


if __name__ == '__main__':
    print(json.dumps(compare(), indent=2))
