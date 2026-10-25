"""Explicit single-use recovery paths; original failed attempts stay immutable."""
from hashlib import sha256
import json
from pathlib import Path
from data.current_quantity_v2_followup_provider import read_bytes, safe_path


def recovery_attempt(*, root, original, request_path, request_sha256, event_sha256,
                     session, expected_manifest_sha256):
    def require(condition, reason):
        if not condition: raise ValueError(reason)
    root=Path(root).resolve();original=Path(original)
    raw=read_bytes(safe_path(root,request_path),65536)
    require(sha256(raw).hexdigest()==request_sha256,'RECOVERY_REQUEST_CHANGED')
    request=json.loads(raw)
    require(set(request)=={'schema','event_sha256','session','expected_manifest_sha256',
        'prior_files','diagnosis','diagnosis_reference'},'RECOVERY_REQUEST_FIELDS')
    require(request['schema']=='FOLLOWUP_CAPTURE_RECOVERY_V1' and
        request['event_sha256']==event_sha256 and request['session']==session and
        request['expected_manifest_sha256']==expected_manifest_sha256,'RECOVERY_BINDING')
    require(request['diagnosis'] in {'RSS_NON_XML_RESPONSE','RSS_FUTURE_PUBLICATION'},'RECOVERY_DIAGNOSIS')
    reference=request['diagnosis_reference']
    diagnosis_raw=read_bytes(safe_path(root,reference['path']),4*1024*1024)
    require(sha256(diagnosis_raw).hexdigest()==reference['sha256'],'RECOVERY_DIAGNOSIS_CHANGED')
    diagnosis=json.loads(diagnosis_raw)
    rows=[row for row in diagnosis['rows'] if row['event_sha256']==event_sha256]
    require(bool(rows),'RECOVERY_DIAGNOSIS_EVENT')
    require(all(('parse_error' in row if request['diagnosis']=='RSS_NON_XML_RESPONSE' else
        any(item['future_publication'] is True for item in row['invalid_items'])) for row in rows),
        'RECOVERY_DIAGNOSIS_MISMATCH')
    require(set(request['prior_files'])=={'started.json','failed.json','review.json'},'RECOVERY_PRIOR_FILES')
    prior={}
    for name,digest in request['prior_files'].items():
        body=read_bytes(safe_path(original,name),4*1024*1024)
        require(sha256(body).hexdigest()==digest,'RECOVERY_PRIOR_CHANGED')
        prior[name]=json.loads(body)
    require(not (original/'complete.json').exists(),'RECOVERY_COMPLETED_ATTEMPT')
    require(prior['failed.json']['reason']=='MATURED_HORIZON_UNRESOLVED' and
        prior['started.json']['event_sha256']==event_sha256 and
        prior['started.json']['session']==session and
        prior['started.json']['expected_manifest_sha256']==expected_manifest_sha256,'RECOVERY_PRIOR_BINDING')
    return safe_path(original,'recoveries/'+request_sha256),request
