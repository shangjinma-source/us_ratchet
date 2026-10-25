"""Read-only-to-account source capture entry; explicit execute, no simulated clock.

Request JSON contains book, authority, admitted_decisions, admitted_settlements,
securities, target_quantities, window_start, identity_manifest and output_directory.
Bytes use {"source_file": "relative/path", "sha256": "..."} references under root.
This entry does not initialize a paper book, authorize source bytes, or accept orders.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from data.strategy_account_identity import PinnedStrategyIdentity
from data.strategy_prospective_paper_source_capture_v1 import capture_prospective_sources
from data.strategy_paper_application_descriptor_v1 import require
from data.strategy_daily_session_capture import reject_links


def load_request(root,request_path,expected_sha256):
    root=Path(root).absolute();reject_links(root)
    request_path=Path(request_path).absolute();reject_links(request_path)
    raw=request_path.read_bytes()
    require(len(raw)<=16*1024*1024 and sha256(raw).hexdigest()==expected_sha256,'PAPER_CAPTURE_REQUEST_CHANGED')
    budget=[0]
    def resolve(value):
        if type(value) is dict:
            if set(value)=={'source_file','sha256'}:
                path=root/value['source_file'];reject_links(path)
                require(not Path(value['source_file']).is_absolute() and path.resolve().is_relative_to(root.resolve()),'PAPER_CAPTURE_SOURCE_PATH')
                require(path.stat().st_nlink==1,'PAPER_CAPTURE_SOURCE_ALIAS')
                body=path.read_bytes();budget[0]+=len(body)
                require(len(body)<=16*1024*1024 and budget[0]<=256*1024*1024 and sha256(body).hexdigest()==value['sha256'],'PAPER_CAPTURE_SOURCE_CHANGED')
                return body
            return {k:resolve(v) for k,v in value.items()}
        if type(value) is list:return [resolve(v) for v in value]
        return value
    request=resolve(json.loads(raw))
    require(set(request)=={'book','authority','admitted_decisions','admitted_settlements','securities','target_quantities','window_start','identity_manifest','output_directory'},'PAPER_CAPTURE_REQUEST_FIELDS')
    identity=request.pop('identity_manifest')
    request['identity_resolver']=PinnedStrategyIdentity(root,identity['path'],identity['sha256'])
    output=root/request['output_directory'];reject_links(output)
    require(not Path(request['output_directory']).is_absolute() and output.resolve().is_relative_to(root.resolve()),'PAPER_CAPTURE_OUTPUT_PATH')
    request['output_directory']=output
    return request


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',required=True);parser.add_argument('--request',required=True)
    parser.add_argument('--request-sha256',required=True);parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    request=load_request(args.root,args.request,args.request_sha256)
    if not args.execute:
        result=dict(status='READY_FOR_SOURCE_CAPTURE_ONLY',securities_count=len(request['securities']),account_mutated=False,orders_created=False)
    else:result=capture_prospective_sources(**request)['receipt']
    print(json.dumps(result,ensure_ascii=False,sort_keys=True))


if __name__=='__main__':main()
