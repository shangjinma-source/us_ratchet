"""Exact pre-existing LRCX quote identity bridge; no economic authorization."""
import hashlib,json,gzip
from fractions import Fraction as F
from pathlib import Path
OLD='security:0000707549:512807108'
NEW='security:0000707549:512807306'
SOURCE='tmp/fixed12_training_prepare_20261014_v6/prepared.json'
SHA='226210854041216e8ace37fb52395809d6cff64e45e2f125197da9e2f7047606'
def series(document,sid,dates,index,pins):
 if sid!=OLD:raise ValueError('WRONG_LRCX_SID')
 event=[e for e in document['dated_identity_transitions'] if e.get('old_sid')==OLD]
 if len(event)!=1:raise ValueError('LRCX_EVENT_NOT_UNIQUE')
 e=event[0]
 if e.get('new_sid')!=NEW or e.get('date')!='2024-10-03' or F(e.get('share_ratio',0))!=10 or e.get('identity_quote_binding_only') is not True or e.get('source_references')!=[SOURCE]:raise ValueError('LRCX_BINDING_MISMATCH')
 root=Path(__file__).resolve().parents[2]
 if hashlib.sha256((root/SOURCE).read_bytes()).hexdigest()!=SHA:raise ValueError('LRCX_SOURCE_CHANGED')
 pins[SOURCE]=SHA
 provider='data/cache/research/current_raw_capture_20261014_v1/LRCX.response.bin';raw=(root/provider).read_bytes();digest=hashlib.sha256(raw).hexdigest()
 if digest!='3432b85b9111a4a581fa4da50af2042cc0ea684d201ad2d28cfb076afdca992c':raise ValueError('LRCX_PROVIDER_CHANGED')
 payload=json.loads(gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw);splits=payload['chart']['result'][0]['events']['splits'];matches=[e for e in splits.values() if e.get('date')==1727962200 and e.get('numerator')==10 and e.get('denominator')==1]
 if len(matches)!=1:raise ValueError('LRCX_PROVIDER_SPLIT_MISMATCH')
 pins[provider]=digest;values=[None]*index
 for d in dates[index:]:
  source=OLD if d<'2024-10-03' else NEW;bar=document['ohlc'].get(source,{}).get(d)
  if not bar or not bar.get('close'):raise ValueError('LRCX_PRICE_MISSING:'+d)
  values.append(F(bar['close'])*(1 if source==OLD else 10))
 return values
