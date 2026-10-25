"""Display-only explanations from the exact archive returned by the daily service.

The caller must supply the server-owned archive root and an already admitted
preview. This function neither admits signals nor changes orders/targets.
"""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from backtest.partial_trend_exposure import partial_sma20_target
from core.strategy_account_ledger import require


def explain_preview(preview, *, archive_root, policy_id):
    result = deepcopy(preview)
    if result.get('status') not in {'READY', 'HOLD'} or not result.get('evidence_archive'):
        return result
    require(policy_id == 'SMA20_HALF_OFF_RESEARCH', 'EXPLANATION_POLICY_UNSUPPORTED')
    archive = result['evidence_archive']
    root = Path(archive_root).absolute()
    digest = archive['receipt_sha256']
    require(type(digest) is str and len(digest) == 64 and
            all(c in '0123456789abcdef' for c in digest), 'EXPLANATION_RECEIPT_HASH')
    folder = root / digest
    require(Path(archive['receipt_path']).absolute() == folder / 'receipt.json', 'EXPLANATION_ARCHIVE_SCOPE')
    budget = 0
    def read(path):
        nonlocal budget
        require(not path.is_symlink() and not any(p.is_symlink() for p in path.parents), 'EXPLANATION_SYMLINK')
        require(path.stat().st_size <= 32*1024*1024, 'EXPLANATION_SIZE')
        raw = path.read_bytes();budget += len(raw)
        require(budget <= 34*1024*1024, 'EXPLANATION_BUDGET')
        return raw
    receipt_raw = read(folder/'receipt.json')
    require(sha256(receipt_raw).hexdigest() == digest, 'EXPLANATION_RECEIPT_CHANGED')
    receipt = json.loads(receipt_raw)
    manifest_raw = read(folder/'manifest.json')
    manifest = json.loads(manifest_raw)
    complete = json.loads(read(folder/'complete.json'))
    require(complete['receipt_sha256'] == digest and
            complete['manifest_sha256'] == sha256(manifest_raw).hexdigest() and
            manifest['receipt_sha256'] == digest and
            manifest['source_sha256'] == receipt['source_sha256'], 'EXPLANATION_ARCHIVE_CHANGED')
    require(receipt['account_revision'] == result['account_revision'] and
            receipt['target_id'] == result['target_id'], 'EXPLANATION_BINDING_MISMATCH')
    pins = receipt['source_sha256']
    require(type(pins) is dict and 0 < len(pins) <= 2000, 'EXPLANATION_SOURCE_DOMAIN')
    sources = {}
    for name, value in pins.items():
        require(type(value) is str and len(value)==64 and all(c in '0123456789abcdef' for c in value), 'EXPLANATION_SOURCE_HASH')
        raw = read(folder/'sources'/(value+'.bin'))
        require(sha256(raw).hexdigest()==value, 'EXPLANATION_SOURCE_CHANGED')
        sources[name]=raw
    inputs=json.loads(sources[receipt['normalized_inputs_path']])
    calculated=partial_sma20_target(**inputs)
    effective=result.get('effective_target_quantities')
    if effective is None:
        effective={r['security_id']:r['effective_target'] for r in result.get('daily_gate',{}).get('rows',[]) if 'effective_target' in r}
    require(type(effective) is dict and bool(effective), 'EXPLANATION_EFFECTIVE_TARGET_REQUIRED')
    require(all(calculated['target_quantities'].get(sid,0)==quantity for sid,quantity in effective.items()), 'EXPLANATION_TARGET_MISMATCH')
    result['signal_explanations']={sid:dict(
        policy=calculated['policy'],signal_date=inputs['signal_date'],
        close=values['close'],sma20=values['sma20'],above_sma20=values['on'],
        monthly_target=values['monthly_ceiling'],effective_target=calculated['target_quantities'][sid],
        receipt_sha256=digest)
        for sid,values in calculated['diagnostics'].items() if sid in effective}
    return result
