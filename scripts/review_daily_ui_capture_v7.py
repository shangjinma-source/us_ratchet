"""Calendar-aware actual DOM review; all financial checks delegate to V6."""
import argparse
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo
from scripts.review_daily_ui_capture_v6 import review as review_v6, require


def timestamp(value):
    require(isinstance(value,str), 'CALENDAR_TIMESTAMP_REQUIRED')
    value=datetime.fromisoformat(value.replace('Z','+00:00'))
    require(value.utcoffset() is not None,'CALENDAR_AWARE_TIME_REQUIRED')
    return value


def review(capture):
    require(capture.get('capture_schema')=='DAILY_FOUR_COLUMN_DOM_CAPTURE_V3','CALENDAR_DOM_CAPTURE_REQUIRED')
    projected=deepcopy(capture)
    observed=timestamp(capture['observed_at'])
    page=''.join(capture.get('page_text','').split())
    context=capture.get('scheduled_context')
    require(isinstance(context,dict),'SEPARATE_CALENDAR_CONTEXT_REQUIRED')
    rows=capture.get('dom_rows')
    require(isinstance(rows,list) and bool(rows),'DOM_ROWS_REQUIRED')
    require(len({row.get('ticker') for row in rows})==len(rows),'DUPLICATE_DOM_TICKER')
    verified=0
    for original,row in zip(capture['dom_rows'],projected['dom_rows']):
        notes=original.get('scheduled_notes')
        require(isinstance(notes,list) and all(isinstance(x,str) for x in notes),'CALENDAR_NOTES_REQUIRED')
        require(len(notes)==(1 if original['ticker']=='MRNA' else 0),'CALENDAR_DOM_DOMAIN')
        cells=original.get('dom_cells');parts=original.get('dom_parts')
        require(isinstance(cells,list) and len(cells)==4 and isinstance(parts,dict),'CALENDAR_DOM_SHAPE')
        plain=parts['reason']+parts['ai_label']+parts['ai_text']
        require(cells[3]==plain+''.join(notes),'CALENDAR_FULL_CELL_MISMATCH')
        full=''.join(''.join(cells).split())
        require(page.count(full)==1,'CALENDAR_FULL_PAGE_ROW_MISMATCH')
        if notes and notes[0]!='财报安排未核实':
            require(context.get('status')=='CONTEXT_ONLY','CALENDAR_CONTEXT_NOT_VALID')
            eligible=[]
            for event in context.get('events',[]):
                if event.get('ticker')!='MRNA' or event.get('event_kind')!='EARNINGS_CALL':continue
                if event.get('eligible_as_new_trigger') is not False or event.get('may_refresh_event_window') is not False:continue
                scheduled,seen=timestamp(event.get('scheduled_at')),timestamp(event.get('observed_at'))
                if scheduled>observed and 0<=(observed-seen).total_seconds()<=86400:eligible.append(scheduled)
            require(bool(eligible),'CALENDAR_EXPIRED_OR_MISSING')
            local=eligible[0].astimezone(ZoneInfo('Asia/Shanghai'))
            expected=f'财报会议：{local.month}/{local.day} {local.hour:02d}:{local.minute:02d}（北京时间）；非业绩结论'
            require(notes==[expected],'CALENDAR_TEXT_CONTEXT_MISMATCH')
            verified+=1
        row['dom_cells'][3]=plain
        row.pop('scheduled_notes')
        page=page.replace(full,''.join(''.join(row['dom_cells']).split()),1)
    projected['page_text']=page
    projected['capture_schema']='DAILY_FOUR_COLUMN_DOM_CAPTURE_V2'
    result=review_v6(projected)
    return dict(result,acceptance_version=7,calendar_rows_matched=verified,
                calendar_scope='DOM matched to separately captured context only; unverified placeholder grants no calendar validity')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('capture_path',type=Path)
    print(json.dumps(review(json.loads(parser.parse_args().capture_path.read_bytes())),ensure_ascii=False,indent=2))
