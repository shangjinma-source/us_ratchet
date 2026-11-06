"""Read-only frozen November ROA signal; never authorizes account mutations/orders."""
from datetime import date
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
SIGNAL_PATH = 'tmp/roa_november_signal_20261106.json'
SIGNAL_SHA256 = '2943d5ab10d6fc229f546792321c64290c918091d85d62f165778507f8911423'
MANIFEST_PATH = 'tmp/monthly_recovery_20261103/training_scoped_publication/manifest.json'
CONTRACT_PATHS = ('docs/candidates/profitability_roa_momentum_contract_20261106.md', 'docs/candidates/profitability_roa_continuous_contract_20261106.md', 'docs/candidates/roa_daily_account_contract_20261106.md')


def _read(root, name):
    name = name.replace(chr(92), chr(47))
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or ':' in name or '\\' in name:
        raise ValueError('INVALID_SIGNAL_SOURCE_PATH')
    target = (root / name).resolve()
    if not target.is_relative_to(root):
        raise ValueError('SIGNAL_SOURCE_OUTSIDE_ROOT')
    return target.read_bytes()


def load_current_signal(*, as_of_date, root=ROOT, signal_path=SIGNAL_PATH,
                        expected_signal_sha256=SIGNAL_SHA256,
                        strategy_epoch='ROA_20261106', expected_contract_hashes=None):
    """Only Nov6 frozen input. Later sessions require a newly verified market signal."""
    root = Path(root).resolve()
    if date.fromisoformat(as_of_date) != date(2026, 11, 6):
        raise ValueError('CURRENT_SIGNAL_SESSION_NOT_SUPPORTED')
    raw = _read(root, signal_path)
    if sha256(raw).hexdigest() != expected_signal_sha256:
        raise ValueError('CURRENT_SIGNAL_CHANGED')
    source = json.loads(raw)
    pins = dict(source['source_hashes'])
    for name, expected in pins.items():
        if sha256(_read(root, name)).hexdigest() != expected:
            raise ValueError('CURRENT_SIGNAL_DEPENDENCY_CHANGED:' + name)
    manifest = json.loads(_read(root, MANIFEST_PATH))
    for name, expected in manifest['source_hashes'].items():
        if pins.get(name) != expected:
            raise ValueError('TRAINING_DEPENDENCY_NOT_BOUND:' + name)
    dates = manifest['training_dates']
    if len(dates) != 253 or dates != sorted(set(dates)) or dates[-1] != '2026-10-30':
        raise ValueError('CURRENT_TRAINING_DATES_INVALID')
    selected = source['selection']['selected']
    meta = {r['security_id']: r for r in manifest['candidates']}
    if len(meta) != len(manifest['candidates']) or len(selected) != 10:
        raise ValueError('CURRENT_SIGNAL_DOMAIN_INVALID')
    securities = []
    for row in selected:
        identity = meta[row['security_id']]
        if any(row[k] != identity[k] for k in ('security_id', 'ticker', 'issuer_id')):
            raise ValueError('CURRENT_SIGNAL_IDENTITY_MISMATCH')
        if not identity['identity_reviewed'] or not identity['coordinate_reviewed']:
            raise ValueError('CURRENT_SIGNAL_IDENTITY_NOT_REVIEWED')
        securities.append({k: row[k] for k in ('security_id', 'ticker', 'issuer_id')})
    if len({r['issuer_id'] for r in securities}) != 10:
        raise ValueError('CURRENT_SIGNAL_DUPLICATE_ISSUER')
    weights = source['selected_weights']
    if set(weights) != {r['security_id'] for r in securities} or any(Fraction(w) != Fraction(1, 10) for w in weights.values()):
        raise ValueError('CURRENT_SIGNAL_WEIGHTS_CHANGED')
    market = source['market_state']
    if source['selection']['cutoff'] != '2026-10-30' or source['selection']['financial_cutoff'] != '2026-09-30' or market['as_of'] != '2026-11-05' or market['rule'] != 'QQQ_SMA200_TWO_COMPLETED_CLOSES_NEXT_OPEN' or type(market['risk_on']) is not bool:
        raise ValueError('CURRENT_SIGNAL_TIMING_OR_RULE_CHANGED')
    contracts = {p: sha256(_read(root, p)).hexdigest() for p in CONTRACT_PATHS}
    if expected_contract_hashes is not None and contracts != expected_contract_hashes:
        raise ValueError('CURRENT_SIGNAL_CONTRACT_CHANGED')
    pins[signal_path] = expected_signal_sha256
    pins.update(contracts)
    identity = dict(strategy_epoch=strategy_epoch, decision_date='2026-10-30', signal_date=market['as_of'], risk_on=market['risk_on'], weights=weights, source_hashes=pins)
    signal_id = sha256(json.dumps(identity, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return dict(identity, signal_id=signal_id, financial_cutoff='2026-09-30',
                market_state_rule=market['rule'], execution_not_before_session='2026-11-06',
                securities=securities, contract_hashes=contracts,
                quote_inputs_asof=market['as_of'], quote_inputs_scope='MARKET_SIGNAL_ONLY_NOT_EXECUTION_QUOTES',
                status='VERIFIED_READ_ONLY_CURRENT_SIGNAL', executable=False, production_activated=False,
                training_dependency_count=len(manifest['source_hashes']), verified_dependency_count=len(source['source_hashes']),
                limitations=['Historical conditional financial revisions/universe remain disclosed.',
                             'Requires server-owned strategy activation and account stopped/pending state.',
                             'Requires separately admitted fresh nominal quotes and corporate actions; no quote fallback here.'])
