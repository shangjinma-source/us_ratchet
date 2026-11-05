"""One approved bounded accounting supplement; original daily engine unchanged."""
import argparse,json
from pathlib import Path
from hashlib import sha256
from scripts.research import run_pullback_account_20261105 as base
from scripts.research.run_pullback_mxim_20261105 import prepare as previous_prepare
ROOT=base.ROOT
REVIEW='tmp/pullback_action_sources_20261105/atvi_root_review.json'
EXPECTED='b07b0b64f01b8c10389efbd881bd9ae595ec7bf8c94a8272a6c389d1a6743e2e'
_original_prepare=previous_prepare
def prepare(**kwargs):
 document,review=_original_prepare(**kwargs)
 if kwargs['window']!='2021_2023':raise ValueError('EARLY_ONLY')
 raw=(ROOT/REVIEW).read_bytes();base.need(sha256(raw).hexdigest()==EXPECTED,'ATVI_ROOT_PIN');approval=json.loads(raw);path=approval['evidence_path'];raw=(ROOT/path).read_bytes();base.need(sha256(raw).hexdigest()==approval['evidence_sha256'],'ATVI_EVIDENCE_PIN');evidence=json.loads(raw)
 pins={REVIEW:EXPECTED,path:approval['evidence_sha256'],**evidence['local_evidence_hashes']}
 for source,digest in pins.items():base.need(sha256((ROOT/source).read_bytes()).hexdigest()==digest,'ATVI_SOURCE_PIN')
 source=evidence['price_source_path'];sid=approval['security_id'];base.need(document['assembled']['price_source_references'][sid]==[source] and document['source_hashes'][source]==pins[source],'ATVI_PRICE_BINDING')
 for day in ('2022-07-29','2022-08-01'):
  review['rows'].append(dict(status='REVIEWED_NO_ACTION_FOR_PERIOD',security_id=sid,ticker='ATVI',start_exclusive=day,end_inclusive='2022-08-02',selected_price_sources=[source],source_references=[REVIEW,path,source],limitation=approval['assumption']))
 own=Path(__file__).relative_to(ROOT).as_posix();pins[own]=sha256(Path(__file__).read_bytes()).hexdigest();kwargs['pins'].update(pins);review['source_hashes'].update(pins);return document,review
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--first-only',action='store_true');a=p.parse_args();base.original.prepare_actions=prepare;base.run('2021_2023',a.output,a.first_only)
