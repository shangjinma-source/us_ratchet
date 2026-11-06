"""Exact approved ROA economic supplements; no absence admission."""
import json
from pathlib import Path
from hashlib import sha256
from fractions import Fraction as F
from copy import deepcopy
ROOT=Path(__file__).resolve().parents[2]
PINS={'tmp/roa_amat_first_dividend_20261106.json':'f92906a97b825cc4e997a3e7f8012aee57a19382b843589fd3a4e0be577f17ef','tmp/roa_aapl_actual_dividends_20261106.json': 'ad5b4db8404106e62dde844752392828454d3fde3aadc57bcac2c52a771b2b32', 'tmp/roa_four_split_economic_review_20261106.json': '69f67bcc0658c4f3a7af4d28b1c59d02fb2f290ac5c03a73352f81977e1e55da'}

def install(packs,pins):
    rows=[]
    for path,expected in PINS.items():
        raw=(ROOT/path).read_bytes()
        if sha256(raw).hexdigest()!=expected:raise ValueError('SUPPLEMENT_CHANGED')
        data=json.loads(raw);sources=data.get('source_hashes',data.get('source_sha256',{}))
        for name,h in sources.items():
            if sha256((ROOT/name).read_bytes()).hexdigest()!=h:raise ValueError('SUPPLEMENT_SOURCE_CHANGED:'+name)
        pins.update(sources);pins[path]=expected
        for row in data.get('review_rows',data.get('rows',[])):
            for name,h in row.get('source_sha256',row.get('source_hashes',{})).items():
                if sha256((ROOT/name).read_bytes()).hexdigest()!=h:raise ValueError('SUPPLEMENT_ROW_SOURCE_CHANGED:'+name)
                pins[name]=h
            event=row.get('event')
            day=event['date'] if event else row['ex_date']
            doc=packs['2021_2023' if day<='2023-12-29' else '2024_2026']['document']
            if event:
                coordinate=row['nominal_coordinate'];old=event['security_id'];new=event.get('new_security_id',old)
                for sid,date,bar in [(old,coordinate['previous_date'],coordinate['previous']),(new,day,coordinate['effective'])]:
                    for field,value in bar.items():
                        if F(doc['ohlc'][sid][date][field])!=F(value):raise ValueError('SPLIT_COORDINATE_CHANGED')
                for field in ('actions','provider_actions'):
                    matches=[e for e in doc['assembled'][field] if (e['security_id'],e['date'])==(old,day)]
                    if matches and matches!=[event]:raise ValueError('SPLIT_CONFLICT')
                    if not matches:doc['assembled'][field].append(deepcopy(event))
            else:
                event=next(e for e in data['dividend_events'] if e['security_id']==row['security_id'] and e['ex_date']==day)
                matches=[e for e in doc['dividend_events'] if e['security_id']==row['security_id'] and e['ex_date']==day]
                if matches:
                    if any(F(e['amount_per_share'])!=F(event['amount_per_share']) or e['payment_date']!=event['payment_date'] for e in matches):raise ValueError('DIVIDEND_CONFLICT')
                else:doc['dividend_events'].append(deepcopy(event))
            rows.append((row,event))
    return rows

def admit(value,rows):
    result=deepcopy(value);remaining=[];accepted=[]
    def normalized(payload):
        return {k:str(F(str(v))) if k!='splitRatio' else v for k,v in payload.items()}
    for observed in result['unmapped_events']:
        found=False
        for row,event in rows:
            sid=event['security_id'];day=event.get('date',event.get('ex_date'))
            if observed.get('security_id')!=sid or observed['date']!=day:continue
            for witness in row['observed_provider_events']:
                expected_hash=witness.get('source_sha256')
                if expected_hash is not None and observed.get('source_sha256')!=expected_hash:
                    continue
                observed_hash=observed.get('source_sha256')
                source_hashes=row.get('source_sha256',row.get('source_hashes',{}))
                if observed_hash is not None and observed['source'] in source_hashes and observed_hash!=source_hashes[observed['source']]:
                    continue
                if observed['source']==witness['source'] and observed['kind']==witness['kind'] and normalized(observed.get('provider_event',observed.get('provider_payload',{})))==normalized(witness.get('provider_event',witness.get('provider_payload',{}))):
                    found=True;break
            if found:break
        (accepted if found else remaining).append(observed)
    result.update(unmapped_events=remaining,roa_exact_supplements=accepted,admitted=not remaining and not result['missing_action_streams'])
    return result
