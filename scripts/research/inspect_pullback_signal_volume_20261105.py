"""Read-only actual signal/volume pairing, not volume-unit admission."""
import json
from hashlib import sha256
from pathlib import Path
from backtest.research_exact_fraction_json import loads


def inspect():
    result = {'scope': 'SAME_SOURCE_PAIRS_NOT_SPLIT_UNIT_OR_DOLLAR_VOLUME_ADMISSION', 'source_hashes': {}, 'windows': {}}
    for window, run in [('early', 'early_price_v5'), ('late', 'late_price_v5')]:
        inventory_path = Path(f'tmp/pullback_volume_inventory_20261105_v3_final/{window}.json')
        signal_path = Path(f'tmp/pullback_account_20261105/{run}/signals.json')
        for path in (inventory_path, signal_path):
            result['source_hashes'][path.as_posix()] = sha256(path.read_bytes()).hexdigest()
        inventory = json.loads(inventory_path.read_text())
        signals = loads(signal_path.read_text())
        rows = []
        for day, signal in signals.items():
            for entry in signal['entries']:
                sid, breakout = entry['security_id'], entry['breakout_date']
                sources = inventory['securities'].get(sid, {}).get('volume_by_source', {})
                pairs = [dict(source=path, breakout_volume=values[breakout], confirmation_volume=values[day])
                         for path, values in sources.items() if breakout in values and day in values]
                distinct = {(item['breakout_volume'], item['confirmation_volume']) for item in pairs}
                rows.append(dict(security_id=sid, breakout=breakout, confirmation=day, pairs=pairs,
                                 source_conflict=len(distinct) > 1,
                                 raw_contraction=(pairs[0]['confirmation_volume'] < pairs[0]['breakout_volume'])
                                 if len(distinct) == 1 else None))
        result['windows'][window] = dict(rows=rows, signals=len(rows),
            matched=sum(bool(row['pairs']) for row in rows),
            conflicts=sum(row['source_conflict'] for row in rows),
            raw_contractions=sum(row['raw_contraction'] is True for row in rows))
    return result


if __name__ == '__main__':
    result = inspect()
    Path('tmp/pullback_account_20261105/signal_volume_pairs_review.json').write_text(json.dumps(result, indent=2))
    print(json.dumps({key: {field: value for field, value in item.items() if field != 'rows'}
                      for key, item in result['windows'].items()}))
