"""Capture one unregistered paper historical parent; stdout result, no orders."""
import argparse
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo
from core.strategy_account_ledger import canonical,require
from data.strategy_daily_rolling_parent_v3 import pinned
from data.strategy_daily_session_capture import stamp,reject_links
from data.strategy_prospective_paper_first_window_v1 import review_paper_first_window
from data.current_quantity_v2_paper_action_sources import fetch_daily_actions,daily_url
from scripts.current_research_official_alert_capture import fetch_official_feed,URL


def capture(*,root,configuration_bytes,configuration_sha256,output,execute=False,clock=None,
            fetch_daily=None,fetch_official=None):
    clock=clock or (lambda:datetime.now(timezone.utc));now=stamp(clock())
    root=Path(root).absolute();reject_links(root)
    require(sha256(configuration_bytes).hexdigest()==configuration_sha256,'FIRST_CAPTURE_CONFIG')
    config=json.loads(configuration_bytes)
    require(config['schema']=='PAPER_FIRST_WINDOW_SOURCE_PREPARATION_V1','FIRST_CAPTURE_SCHEMA')
    calendar=json.loads(pinned(root,config['calendar']));sessions=calendar['sessions']
    dates=[r['date'] for r in sessions];today=now.astimezone(ZoneInfo('America/New_York')).date().isoformat()
    if today not in dates or dates.index(today)<20 or now>=stamp(sessions[dates.index(today)]['close']):
        return dict(status='WAIT_NEXT_SESSION_NO_CAPTURE',observed_at=now.isoformat(),network_calls=0,book_created=False)
    index=dates.index(today);window=sessions[index-20:index]
    training=json.loads(pinned(root,config['training'],maximum=32*1024*1024))
    members=[r for r in training['candidates'] if r['security_id']==config['security_id']]
    require(len(members)==1,'FIRST_CAPTURE_SECURITY');ticker=members[0]['ticker']
    if not execute:return dict(status='DRY_RUN_SINGLE_SECURITY',ticker=ticker,session=today,network_calls=0)
    directory=Path(output).absolute();reject_links(directory)
    require(directory.resolve().is_relative_to(root.resolve()) and directory!=root,'FIRST_CAPTURE_OUTPUT')
    directory.mkdir(parents=True,exist_ok=False)
    def save(name,raw):
        path=directory/name;require(path.resolve().is_relative_to(directory.resolve()),'FIRST_ARCHIVE_PATH')
        path.parent.mkdir(parents=True,exist_ok=True);reject_links(path)
        with path.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    save('intent.json',canonical(dict(configuration_sha256=configuration_sha256,started_at=now.isoformat(),ticker=ticker)))
    save('configuration.json',configuration_bytes);calls=0;captured={}
    try:
        for name in ('daily','official'):
            started=stamp(clock());calls+=1
            response=((fetch_daily or fetch_daily_actions)(ticker,stamp(window[0]['open'])-timedelta(days=1),started)
                if name=='daily' else (fetch_official or fetch_official_feed)())
            received=stamp(clock());body=response['body']
            require(started<=received and type(body)is bytes and 0<len(body)<=4*1024*1024,'FIRST_CAPTURE_BYTES_CLOCK')
            url=daily_url(ticker,stamp(window[0]['open'])-timedelta(days=1),started) if name=='daily' else URL
            receipt=dict(status='CAPTURED',attempts=1,http_status=response['status'],raw_sha256=sha256(body).hexdigest(),
                stored_bytes=len(body),started_at=started.isoformat(),received_at=received.isoformat(),url=url)
            captured[name+'.response.bin']=body;captured[name+'.receipt.json']=canonical(receipt)
            save(name+'.response.bin',body);save(name+'.receipt.json',canonical(receipt))
        result=review_paper_first_window(root=root,configuration_bytes=configuration_bytes,
            configuration_sha256=configuration_sha256,capture_files=captured,clock=clock)
        if result['receipt'] is None:
            save('failed.json',canonical(dict(status=result['status'],reason=result['reason'],network_calls=calls)))
            return dict(status=result['status'],reason=result['reason'],network_calls=calls,directory=str(directory))
        for name,body in result['files'].items():save('source-root/'+name,body)
        raw=canonical(result['receipt']);save('source-root/parent-receipt.json',raw)
        finished=stamp(clock());require(now<=finished<stamp(sessions[index]['close']),'FIRST_CAPTURE_FINISH')
        complete=dict(status='UNBOUND_PAPER_PARENT_SAVED_NOT_REGISTERED',parent_sha256=sha256(raw).hexdigest(),
            configuration_sha256=configuration_sha256,source_sha256=result['receipt']['source_sha256'],
            finished_at=finished.isoformat(),network_calls=calls)
        save('complete.json',canonical(complete))
        return dict(complete,directory=str(directory),book_created=False,orders_created=False)
    except Exception as error:
        if not (directory/'failed.json').exists():save('failed.json',canonical(dict(status='FAILED_PRESERVED',reason=str(error),network_calls=calls)))
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('root','configuration','configuration-sha256','output'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    raw=pinned(Path(args.root),dict(path=args.configuration,sha256=args.configuration_sha256))
    result=capture(root=args.root,configuration_bytes=raw,configuration_sha256=args.configuration_sha256,
        output=args.output,execute=args.execute)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
