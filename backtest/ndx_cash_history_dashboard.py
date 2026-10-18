"""Read fixed, published cash-history evidence without running any research job."""
from copy import deepcopy
from decimal import Decimal, localcontext, ROUND_HALF_EVEN
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'data/cache/research/cash_combined_readable_report_20261008_v1'
COMPARISON = ROOT / 'data/cache/research/cash_neighbor_combined_path_comparison_20261008_v1'
AUDIT = ROOT / 'data/cache/research/cash_neighbor_combined_path_comparison_independent_readback_20261008_v1'
BOUND = {
    'started': (REPORT / 'started.json', 'a54fce05992a85f1357414e86e72009c93d4d67f79418d72fb7fe4f0a696222e'),
    'projection': (REPORT / 'projection.json', 'ac0fcd34cc0a9ef2458cb618d16488397109b48da8f72e0dee6a50ded21dead8'),
    'report': (REPORT / 'report.md', 'b8f492a63488c5d25c5155a252c75b2b7420b4131f1ed59cd20a33c36d11df39'),
    'publication': (REPORT / 'publication.json', '1b88b2ed4557a68c155059ccadf84c4af85a30301bd6f67d8395739448551700'),
    'index': (COMPARISON / 'index.json', 'd36303c57eb4643c841d019fca5dbf0caa95e964961b327fa4aa49bdaa4d7fb9'),
    'comparison_publication': (COMPARISON / 'publication.json', '2477e5eeea1014dcee9886e34cc1dedd69e269b9b6cf63a92ea4d73e26b4f0d0'),
    'audit': (AUDIT / 'independent_readback.json', '11aa3998d8f710c54a5c584a2b4f3de0d2307c094f6ca49bf5540c8f7e9426b6'),
    'reader': (ROOT / 'scripts/ndx_cash_neighbor_combined_path_comparison_independent_readback_20261008.py', 'f56c3f3ba06c7548595b9f84d2992320577ce3372180fad32654e47ace0a3bd7'),
}
FALSE = ('account_executed', 'cross_window_ranking_performed', 'currency_fx_equivalence_verified',
         'financial_recomputation_performed', 'formal_dual_benchmark_admission', 'fresh_oos_claimed',
         'point_in_time_verified', 'promotion_allowed', 'selection_reexecuted')
ROLES = ('candidate', 'same_flow_zero_trade_control', 'same_flow_incumbent', 'fund_012922_cny_nav_reference')


def require(value, message):
    if not value:
        raise ValueError(message)


def loads(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def percentage(value, difference=False):
    """Literal display only, retaining all original exact values in the response."""
    if value is None:
        return '缺项'
    with localcontext() as context:
        if isinstance(value, dict):
            context.prec = len(value['numerator']) + len(value['denominator']) + 40
            number = Decimal(value['numerator']) * 100 / Decimal(value['denominator'])
        else:
            original = Decimal(value)
            context.prec = max(len(original.as_tuple().digits), original.adjusted() + 1, 0) + 40
            number = original * 100
        rounded = number.quantize(Decimal('0.0001'), rounding=ROUND_HALF_EVEN)
    unit = ' pp' if difference else '%'
    if number == 0:
        return '0.0000' + unit
    if rounded == 0:
        return ('负且绝对值 < ' if number < 0 else '正且 < ') + '0.0001' + unit
    return format(rounded, 'f') + unit


def read_cash_history_evidence():
    """No caller paths; hashes authenticate saved bytes, not economic admission."""
    inventories = ((REPORT, {'started.json', 'projection.json', 'report.md', 'publication.json'}),
                          (COMPARISON, {'started.json', 'cases.jsonl', 'index.json', 'publication.json'}),
                          (AUDIT, {'started.json', 'independent_readback.json'}))
    for folder, names in inventories:
        require(not folder.is_symlink() and {p.name for p in folder.iterdir()} == names, 'Failed or changed evidence namespace')
        require(all(p.is_file() and not p.is_symlink() for p in folder.iterdir()), 'Regular evidence files required')
    raw = {}
    for role, (path, digest) in BOUND.items():
        require(path.is_file() and not any(p.is_symlink() for p in (path, *path.parents)), 'Regular fixed evidence path')
        require(path.stat().st_size <= 4_000_000, 'Evidence document resource bound')
        raw[role] = path.read_bytes()
        require(hashlib.sha256(raw[role]).hexdigest() == digest, 'Cash evidence SHA mismatch: ' + role)
    docs = {role: loads(value) for role, value in raw.items() if role not in ('report', 'reader')}
    projection, publication, audit, index = (docs[k] for k in ('projection', 'publication', 'audit', 'index'))
    refs = {k: {'path': str(p), 'sha256': h} for k, (p, h) in BOUND.items()}
    require(projection['schema'] == 'CASH_COMBINED_LITERAL_REPORT_PROJECTION_V1'
            and publication['schema'] == 'CASH_COMBINED_LITERAL_REPORT_PUBLICATION_V1', 'Cash report schema')
    require(publication['projection_reference'] == refs['projection'] and publication['report_reference'] == refs['report'], 'Report publication links')
    expected_inputs = {'index': refs['index'], 'publication': refs['comparison_publication'], 'audit': refs['audit'], 'reader': refs['reader']}
    require(projection['input_references'] == publication['input_references'] == docs['started']['input_references'] == expected_inputs, 'Audited report inputs')
    require(projection['source_hashes'] == publication['source_hashes'] == docs['started']['source_hashes'], 'Saved report source closure')
    require(audit['schema'] == 'CASH_NEIGHBOR_PATH_COMPARISON_INDEPENDENT_READBACK_V1' and audit['status'] == 'PASS'
            and type(audit['scenario_count']) is int and audit['scenario_count'] == 40, 'Independent comparison audit')
    require(audit['index_reference'] == docs['comparison_publication']['index_reference'] == refs['index']
            and audit['publication_reference'] == refs['comparison_publication'] and audit['reader_sha256'] == refs['reader']['sha256'], 'Independent audit links')
    for value in (projection, publication):
        require(all(value[k] is False for k in FALSE), 'Historical evidence authority')
    require(len(projection['rows']) == len(index['cases']) == len(audit['cases']) == 40, 'Complete original forty cases')
    rows = deepcopy(projection['rows'])
    coordinates = set()
    for i, row in enumerate(rows):
        require(type(row['scenario_index']) is int and row['scenario_index'] == i
                and row['scenario_id'] == index['cases'][i]['scenario_id']
                and row['jsonl_descriptor'] == index['cases'][i], 'Original scenario identity/order')
        require(row['candidate_status'] in ('AVAILABLE_NEW', 'AVAILABLE_REUSED'), 'Saved candidate status')
        require(tuple(m['role'] for m in row['metrics']) == ROLES, 'Complete saved references')
        coordinates.add((row['decision_date'], row['execution_date'], row['cash_amount_usd']))
        for key in ('metrics', 'differences'):
            for metric in row[key]:
                metric['display'] = {field: percentage(metric.get(field), key == 'differences') for field in
                                     ('cumulative_return', 'maximum_drawdown', 'annualized_return_diagnostic_decimal')}
    require(len(coordinates) == 10, 'Original historical coordinate domain')
    # Recheck only fixed small inputs; never follow arbitrary saved source claims.
    for role, (path, digest) in BOUND.items():
        require(hashlib.sha256(path.read_bytes()).hexdigest() == digest and not (path.parent / 'failure.json').exists(), 'Evidence changed while reading')
    for folder, names in inventories:
        require({p.name for p in folder.iterdir()} == names and all(p.is_file() and not p.is_symlink() for p in folder.iterdir()), 'Evidence inventory changed while reading')
    return {'available': True, 'research_track': 'portfolio_optimization', 'evidence_role': 'SAVED_HISTORICAL_CASH_NEIGHBOR_DIAGNOSTICS',
            'scenario_count': 40, 'rows': rows, 'limitations': projection['limitations'], 'references': refs,
            'saved_source_hash_claims': deepcopy(projection['source_hashes']), 'saved_artifact_bytes_verified': True,
            'full_transitive_source_closure_reverified': False, 'current_cash_input_consumed': False,
            'candidate_admission_allowed': False, 'research_only': True, **dict.fromkeys(FALSE, False)}
