"""Prearchive verified static bytes before 10:00; no quote or decision capture."""
import argparse
from datetime import datetime,timezone
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter
from scripts.bootstrap_current_quantity_v2_simulation import preflight
from data.current_quantity_v2_monthly_capture_audit import publish_blob
from backtest.current_quantity_v2_close_capture_simulation import _read
from data.current_quantity_v2_difference_plan import require


def prepare(*,config_path,config_sha256,now=None):
    began=perf_counter()
    checked=preflight(config_path=config_path,config_sha256=config_sha256,now=now or datetime.now(timezone.utc))
    config=checked['config'];research=checked['research']
    descriptor,_,_,files=research._load();pins=dict(descriptor['source_hashes'])
    month=config['initial_month'];raw=_read(checked['root'],month['path'],{month['path']:month['sha256']})
    files[month['path']]=raw;pins[month['path']]=month['sha256']
    for name,digest in json.loads(raw)['source_hashes'].items():
        require(name not in pins or pins[name]==digest,'STATIC_SOURCE_PIN_CONFLICT')
        files[name]=_read(checked['root'],name,{name:digest});pins[name]=digest
    require(set(files)==set(pins) and len(files)<=2000,'SOURCE_BYTES_LIMIT')
    require(sum(map(len,files.values()))<=128*1024*1024,'SOURCE_BYTES_LIMIT')
    for name,raw in files.items():
        require(len(raw)<=32*1024*1024 and sha256(raw).hexdigest()==pins[name],'STATIC_SOURCE_HASH_MISMATCH')
    root=Path(config['audit_directory']);created=0;reused=0
    for name,raw in files.items():
        if (root/'blobs'/pins[name]).exists():reused+=1
        else:created+=1
        publish_blob(root,raw,32*1024*1024)
    # Sources still must be rechecked by the normal bootstrap at execution time.
    return dict(status='STATIC_BYTES_PREPARED_NOT_A_CAPTURE',files=len(files),bytes=sum(map(len,files.values())),
                created=created,reused=reused,elapsed_seconds=perf_counter()-began,
                quote_calls=0,search_calls=0,account_created=False,simulation_started=False,
                bootstrap_config_sha256=config_sha256)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config-path',required=True);parser.add_argument('--config-sha256',required=True)
    print(json.dumps(prepare(**vars(parser.parse_args()))))


if __name__=='__main__':main()
