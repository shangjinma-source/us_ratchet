"""Create-only V11 wrapper configuration. No journal import or activation."""
from copy import deepcopy
from hashlib import sha256
import os
from pathlib import Path
from core.strategy_account_ledger import canonical,require
from data.strategy_unified_server_preparation_v7 import _read
from data.strategy_bounded_source_gate_v1 import _no_links,_read_digest
from data.strategy_unified_server_preparation_v11 import V11_SOURCES,JOURNAL_PATH
from scripts.register_quantity_v2_paper_protocol import safe_path

def materialize_capital_v11(*,root,base_v10,source_pins,output_path,validate_sources):
 root=Path(root).absolute();_no_links(root)
 require(type(source_pins) is dict and set(source_pins)==V11_SOURCES,'V11_SOURCE_SCOPE')
 raw,base=_read(root,base_v10)
 require(base['schema']=='LATEST_DISPLAY_UNIFIED_PREPARATION_V10','V11_BASE_REQUIRED')
 executing=Path(__file__).resolve().parents[1]
 def gate():
  validate_sources();require(_read(root,base_v10)[0]==raw,'V11_BASE_CHANGED')
  for path,digest in source_pins.items():
   require(_read_digest(root/path,32*1024*1024)==digest and _read_digest(executing/path,32*1024*1024)==digest,'V11_SOURCE_CHANGED')
 gate();destination=safe_path(root,output_path);_no_links(destination)
 require(not destination.exists(),'V11_OUTPUT_EXISTS')
 doc=dict(schema='CAPITAL_ARRIVAL_UNIFIED_PREPARATION_V11',base_v10=deepcopy(base_v10),source_pins=deepcopy(source_pins),capital_journal_path=JOURNAL_PATH)
 body=canonical(doc);destination.parent.mkdir(parents=True,exist_ok=True)
 with destination.open('xb') as stream:
  stream.write(body);stream.flush();os.fsync(stream.fileno())
 # Failure leaves the candidate in place; it is not an active manifest.
 gate()
 return dict(status='PREPARED_NOT_ACTIVATED',server_reference=dict(path=destination.relative_to(root).as_posix(),sha256=sha256(body).hexdigest()),base_v10=deepcopy(base_v10),journal_import_required=True,account_mutated=False,target_mutated=False)
