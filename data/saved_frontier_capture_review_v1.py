"""Review original capture bytes through versioned proposal-domain first-window checks."""
import json
from hashlib import sha256
from core.strategy_account_ledger import canonical, require

def review_supplement_packets(*, root, capture, request, binding, state, target,
                              configurations, proposal, extra_security_ids=(), clock=None):
    """Produce native reviewed SID packets without policy approval or publication.

    Configurations are supplied by the server, including pinned identity/baseline
    closure and fixed calendar. Original capture receipts remain in each closure.
    """
    from data.saved_frontier_first_window_v1 import review_first_window
    require(capture['status']=='CAPTURED_REVIEW_REQUIRED' and capture['binding']==binding and
        capture['capture_id']==sha256(canonical(dict(binding=binding,request=request))).hexdigest(),
        'SUPPLEMENT_REVIEW_BINDING')
    require(state['account_id']==binding['account_id'] and state['revision']==binding['account_revision'] and
        target['target_id']==binding['target_id'],'SUPPLEMENT_SNAPSHOT_CHANGED')
    files=capture['files'];pins=capture['source_hashes'];documents=capture['documents']
    require(set(files)==set(pins) and sum(map(len,files.values()))<=128*1024*1024,'SUPPLEMENT_SOURCE_BUDGET')
    for name,raw in files.items():require(sha256(raw).hexdigest()==pins[name],'SUPPLEMENT_SOURCE_CHANGED')
    require(set(configurations)==set(documents['action_receipts'])==set(request['securities']),
        'SUPPLEMENT_PACKET_DOMAIN')
    rss=files[documents['rss_raw']];rss_receipt=json.loads(files[documents['rss_receipt']])
    packets={}
    for sid,configuration in configurations.items():
        require(configuration['security_id']==sid,'SUPPLEMENT_PACKET_IDENTITY')
        original=json.loads(files[documents['action_receipts'][sid]])
        require(original['security_id']==sid and original['ticker']==request['securities'][sid]['ticker'] and
            original['http_status']==200 and original['body_truncated'] is False and original['transport_error'] is None,
            'SUPPLEMENT_PACKET_RECEIPT')
        daily=files[original['raw_path']]
        require(original['raw_sha256']==sha256(daily).hexdigest() and rss_receipt['raw_sha256']==sha256(rss).hexdigest(),
            'SUPPLEMENT_PACKET_HASH')
        # Derived receipt fields are an adapter view of the saved original;
        # never replace its real request/receipt timestamps with the review time.
        daily_receipt=dict(status='CAPTURED',attempts=1,http_status=original['http_status'],
            stored_bytes=len(daily),raw_sha256=original['raw_sha256'],url=original['url'],
            requested_from=original['requested_from'],started_at=original['requested_through'],received_at=original['received_at'])
        official_receipt=dict(status='CAPTURED',attempts=1,http_status=rss_receipt['http_status'],
            stored_bytes=rss_receipt['stored_bytes'],raw_sha256=rss_receipt['raw_sha256'],url=rss_receipt['url'],
            started_at=rss_receipt['started_at'],received_at=rss_receipt['received_at'])
        raw=canonical(configuration)
        reviewed=review_first_window(root=root,configuration_bytes=raw,configuration_sha256=sha256(raw).hexdigest(),
            capture_files={'daily.response.bin':daily,'daily.receipt.json':canonical(daily_receipt),
                'official.response.bin':rss,'official.receipt.json':canonical(official_receipt)},
            state=state,target=target,proposal=proposal,extra_security_ids=extra_security_ids,clock=clock)
        require(reviewed.get('receipt') is not None,'SUPPLEMENT_REVIEW_FAILED:'+str(reviewed.get('reason')))
        closure=reviewed['files']
        for name,body in files.items():
            name='supplement-original/'+capture['capture_id']+'/'+name
            require(name not in closure or closure[name]==body,'SUPPLEMENT_SOURCE_COLLISION');closure[name]=body
        closure['supplement-original/'+capture['capture_id']+'/binding.json']=canonical(dict(binding=binding,request=request))
        require(len(closure)<=2000 and sum(map(len,closure.values()))<=32*1024*1024,'SUPPLEMENT_PACKET_BUDGET')
        receipt=dict(reviewed['receipt'],source_sha256={name:sha256(body).hexdigest() for name,body in closure.items()})
        receipt_raw=canonical(receipt)
        packets[sid]=dict(receipt_bytes=receipt_raw,trusted_receipt_sha256=sha256(receipt_raw).hexdigest(),files=closure)
    return dict(status='SUPPLEMENT_PACKETS_REVIEWED_POLICY_UNRELEASED',packets=packets,
                account_writes=False,policy_approved=False)
