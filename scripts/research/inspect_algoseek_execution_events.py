"""Validate exact historical event sessions from locally downloaded AlgoSeek day ZIPs."""
import argparse
import csv
from datetime import datetime
from hashlib import sha256
import io
import json
from pathlib import Path
import zipfile
from zoneinfo import ZoneInfo
from scripts.research.probe_aapl_historical_execution_events import inspect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    events = [e for e in json.loads(args.manifest.read_text())['records'] if e['date'].startswith('2021')]
    results = []
    for event in events:
        symbol = event['security_id'].split(':')[-1].upper()
        date = event['date'].replace('-', '')
        result = dict(event=event, symbol=symbol)
        try:
            path = args.directory/(date+'.zip')
            with zipfile.ZipFile(path) as archive:
                names = [n for n in archive.namelist() if n.endswith('/'+symbol+'.csv')]
                if len(names) != 1:
                    raise ValueError('SYMBOL_NOT_UNIQUE_OR_MISSING')
                raw = archive.read(names[0])
            rows = [row for row in csv.DictReader(io.StringIO(raw.decode())) if '09:30' <= row['TimeBarStart'] < '16:00']
            data = dict(s='ok', t=[], o=[], h=[], l=[], c=[], v=[])
            for row in rows:
                if row['Date'] != date or row['Ticker'] != symbol:
                    raise ValueError('IDENTITY_MISMATCH')
                stamp = datetime.fromisoformat(event['date']+'T'+row['TimeBarStart']).replace(tzinfo=ZoneInfo('America/New_York'))
                data['t'].append(int(stamp.timestamp()))
                no_trade = all(not row[k] for k in ('FirstTradePrice','HighTradePrice','LowTradePrice','LastTradePrice')) and row['Volume']=='0' and row['TotalTrades']=='0' and row['FinraVolume']=='0'
                for key, column in [('o','FirstTradePrice'),('h','HighTradePrice'),('l','LowTradePrice'),('c','LastTradePrice'),('v','Volume')]:
                    data[key].append(None if no_trade and key!='v' else float(row[column]))
            normalized = json.dumps(data).encode()
            checked = inspect(normalized, event, allow_no_trade=True)
            result.update(status='VALID_MINUTE_STRUCTURE_NOT_COORDINATE_CERTIFIED', csv_sha256=sha256(raw).hexdigest(),
                          rows=len(rows), first_trade=data['o'][0], close=data['c'][-1])
            normalized_directory = args.directory/'normalized'
            normalized_directory.mkdir(exist_ok=True)
            (normalized_directory/(date+'_'+symbol+'.json')).write_bytes(normalized)
        except Exception as error:
            result.update(status='EXCLUDED', error=str(error))
        results.append(result)
    output = dict(scope='2021 original execution events only; no missing-minute padding; trade columns only.',
                  limitations='Raw prices must be reconciled to original split/dividend coordinates before replay.', results=results)
    (args.directory/'event_validation.json').write_text(json.dumps(output,indent=2),encoding='utf-8')
    print(json.dumps(dict(events=len(results),valid=sum(r['status'].startswith('VALID') for r in results),
                         excluded=[r for r in results if r['status']=='EXCLUDED']),indent=2))


if __name__ == '__main__':
    main()
