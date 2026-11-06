"""Fixed old-share SMCI price coordinate bridge; not an account settlement."""
from pathlib import Path
from hashlib import sha256
from fractions import Fraction as F
import json
from backtest.research_exact_fraction_json import loads
ROOT=Path(__file__).resolve().parents[2]
OLD='security:0001375365:86800U104';NEW='security:0001375365:86800U302'
INPUT='tmp/old_continuous_baseline_20261026_v9/execution_inputs.json'
MAPPING='tmp/momentum_split_mapping_20261105/mapping.json'
PINS={INPUT:'b777b58c23b1f36ee30463e926c170e1983b844b96b8e2a2cb27b6b4f11d2672',MAPPING:'6dc917e61e9b2d74e0e104659f3f9627800a6a79d24c631215d05f0900d0f1f0','tmp/fixed12_extended_quote_capture_20261014_v1/SMCI.response.bin':'de16278803b800a8b9d393e5b8cb848566a876da8537fae21a141edce1e5ad6a'}
def load_bridge(pins):
 raw={}
 for name,digest in PINS.items():
  raw[name]=(ROOT/name).read_bytes()
  if sha256(raw[name]).hexdigest()!=digest:raise ValueError('SMCI_SOURCE_HASH_CHANGED:'+name)
  pins[name]=digest
 mapping=json.loads(raw[MAPPING]);record=next(r for r in mapping['records'] if r['ticker']=='SMCI');event=record['event']
 assert (event['security_id'],event['new_security_id'],event['date'],event['old_shares'],event['new_shares'])==(OLD,NEW,'2024-10-01','1','10')
 for source in event['source_references']:
  normalized={k.replace('\\','/'):v for k,v in mapping['source_hashes'].items()}
  digest=normalized[source.replace('\\','/')]
  if sha256((ROOT/source).read_bytes()).hexdigest()!=digest:raise ValueError('SMCI_EVENT_SOURCE_CHANGED:'+source)
  pins[source]=digest
 data=json.loads(raw[INPUT]);data=loads(raw[INPUT].decode()) if data.get('encoding') else data;document=data.get('document',data)
 assert event in document['assembled']['actions'] or any(all(e.get(k)==event[k] for k in ('type','security_id','new_security_id','date','old_shares','new_shares')) for e in document['assembled']['actions'])
 return document['ohlc']
def old_share_series(sid,dates,start,ohlc):
 if sid!=OLD:raise ValueError('SMCI_EXACT_OLD_SID_REQUIRED')
 if dates[start]!='2024-09-30':raise ValueError('SMCI_EXACT_TRANSITION_MONTH_REQUIRED')
 result=[None]*start
 for day in dates[start:]:
  target=OLD if day<'2024-10-01' else NEW
  if day not in ohlc.get(target,{}):raise ValueError('SMCI_MISSING_EXACT_DAY:'+day)
  result.append(F(ohlc[target][day]['close'])*(1 if target==OLD else 10))
 return result
