"""Conditional 2023-12-29 research SID alias; preserves dollars, not shares."""
import json,hashlib
from pathlib import Path
REVIEW='tmp/roa_continuous_identity_boundary_20261106.json'
SHA='c492e37bea9125224c176cdcaa7859d3e65b36973998110aebd7a61fb7188332'
def migrate(prior,pending,date,pins):
 if date!='2023-12-29':raise ValueError('BOUNDARY_DATE_MISMATCH')
 root=Path(__file__).resolve().parents[2];raw=(root/REVIEW).read_bytes()
 if hashlib.sha256(raw).hexdigest()!=SHA:raise ValueError('BOUNDARY_REVIEW_CHANGED')
 review=json.loads(raw);sources=dict(review['source_hashes'])
 for row in review['rows']:sources.update(row['source_financial_cik'])
 for path,digest in sources.items():
  if hashlib.sha256((root/path).read_bytes()).hexdigest()!=digest:raise ValueError('BOUNDARY_SOURCE_CHANGED:'+path)
 pins.update(sources);pins[REVIEW]=SHA
 mapping={r['old_sid']:r['new_sid'] for r in review['rows']}
 if len(mapping)!=10 or len(set(mapping.values()))!=10:raise ValueError('BOUNDARY_NOT_UNIQUE')
 if not set(prior)|set(pending)<=set(mapping):raise ValueError('BOUNDARY_UNKNOWN_HELD_SID')
 result={mapping[s]:v for s,v in prior.items()};newpending={mapping[s] for s in pending}
 if abs(sum(result.values())-sum(prior.values()))>1e-9:raise ValueError('BOUNDARY_VALUE_CHANGED')
 return result,newpending
