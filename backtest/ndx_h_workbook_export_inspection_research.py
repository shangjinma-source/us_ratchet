"""Independent, IO-free H XLSX ZIP and saved-source table checks.

No builder imports, recalculation, accounts, source authentication or visual QA.
This is a verification foundation, NOT a complete source-bound acceptance reader.
"""
import io
import json
import math
import posixpath
import re
import zipfile
import xml.etree.ElementTree as ET
from decimal import Decimal
from fractions import Fraction

M='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
R='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
P='http://schemas.openxmlformats.org/package/2006/relationships'
C='http://schemas.openxmlformats.org/drawingml/2006/chart'
A='http://schemas.openxmlformats.org/drawingml/2006/main'
FLAGS=dict(source_bytes_authenticated=False,formal_comparison_passed=False,point_in_time_verified=False,visual_acceptance_passed=False,native_excel_open_verified=False,workbook_delivery_accepted=False,economics_recomputed=False,risk_reaggregated=False)
ROLES=('candidate_integer','incumbent_integer','candidate_continuous','incumbent_continuous','STRICT_SAME_SESSION_FX','BACKWARD_LATEST_VALID_FX')
SHARED=(ROLES[1],ROLES[3],ROLES[4],ROLES[5])
MISSING='未定义/超出展示精度'


def require(ok,msg):
    if not ok:raise ValueError(msg)
def integer(v):require(type(v) is int and v>=0,'Exact nonnegative integer');return v
def xml(blob):
    require(b'<!DOCTYPE' not in blob.upper() and b'<!ENTITY' not in blob.upper(),'No XML entities')
    return ET.fromstring(blob)
def position(address):
    m=re.fullmatch(r'([A-Z]{1,3})([1-9][0-9]*)',address);require(m is not None,'A1 coordinate')
    col=0
    for c in m[1]:col=col*26+ord(c)-64
    row=int(m[2]);require(col<=16384 and row<=1048576,'Excel bounds');return row,col
def address(row,col):
    text=''
    while col:col,n=divmod(col-1,26);text=chr(65+n)+text
    return text+str(row)
def rectangle(value):
    parts=value.replace('$','').split(':');require(1<=len(parts)<=2,'Bounded A1 range');a=position(parts[0]);b=position(parts[-1]);require(a[0]<=b[0] and a[1]<=b[1] and (b[0]-a[0]+1)*(b[1]-a[1]+1)<=2000000,'Ordered bounded rectangle');return a,b


def read_workbook(xlsx_bytes):
    require(type(xlsx_bytes) is bytes and 0<len(xlsx_bytes)<=50*1024**2,'Published XLSX <=50MiB')
    with zipfile.ZipFile(io.BytesIO(xlsx_bytes)) as z:
        infos=z.infolist();names=[v.filename for v in infos]
        require(len(set(names))==len(names)<=10000,'Unique bounded ZIP entries')
        require(sum(v.file_size for v in infos)<=512*1024**2,'Bounded decompressed XML')
        require(not any(n.startswith('/') or '..' in n.split('/') or '\\' in n for n in names),'Safe ZIP paths')
        require(not any('vbaProject' in n or 'externalLink' in n for n in names),'No macros/external workbook links')
        for part in (n for n in names if n.endswith('.rels')):
            for rel in xml(z.read(part)):
                if rel.get('TargetMode')=='External':require(rel.get('Type')==R+'/hyperlink' and re.fullmatch(r'package-[0-9]{4}\.xlsx',rel.get('Target','')),'No external resources except declared relative package links')
        def relationships(part):
            root=xml(z.read(part));out={}
            for node in root:
                k=node.get('Id');require(k not in out,'Unique relationship id');out[k]=dict(node.attrib)
            return out
        book=xml(z.read('xl/workbook.xml'));rels=relationships('xl/_rels/workbook.xml.rels')
        strings=[]
        if 'xl/sharedStrings.xml' in names:
            for si in xml(z.read('xl/sharedStrings.xml')):strings.append(''.join(si.itertext()))
        styles=[]
        if 'xl/styles.xml' in names:
            style=xml(z.read('xl/styles.xml'));custom={x.get('numFmtId'):x.get('formatCode') for x in style.findall(f'{{{M}}}numFmts/{{{M}}}numFmt')}
            styles=[custom.get(x.get('numFmtId'),'@' if x.get('numFmtId')=='49' else None) for x in style.findall(f'{{{M}}}cellXfs/{{{M}}}xf')]
        sheets={};links=[];owners={};validations={}
        for node in book.findall(f'{{{M}}}sheets/{{{M}}}sheet'):
            name=node.get('name');require(name not in sheets,'Unique worksheet name');rel=rels[node.get(f'{{{R}}}id')]
            require(rel.get('TargetMode')!='External' and rel['Type']==R+'/worksheet','Internal worksheet')
            target=rel['Target'];part=posixpath.normpath(target.lstrip('/') if target.startswith('/') else posixpath.join('xl',target));require(part in names and part.startswith('xl/worksheets/'),'Worksheet part')
            root=xml(z.read(part));cells={}
            for cell in root.findall(f'.//{{{M}}}sheetData/{{{M}}}row/{{{M}}}c'):
                a=cell.get('r');position(a);require(a not in cells,'Duplicate cell');kind=cell.get('t','n');v=cell.find(f'{{{M}}}v');raw=None if v is None else v.text
                f=cell.find(f'{{{M}}}f');formula=None if f is None else f.text
                if f is not None:require(not f.attrib and bool(formula),'No shared/array/empty formulas')
                if kind=='inlineStr':value=''.join(cell.find(f'{{{M}}}is').itertext())
                elif kind=='s':require(raw is not None and raw.isdigit() and int(raw)<len(strings),'Shared string index');value=strings[int(raw)]
                elif kind=='str':value=raw or ''
                elif kind=='b':require(raw in ('0','1'),'Boolean encoding');value=raw=='1'
                elif kind=='e':value=raw
                else:
                    require(kind=='n','Supported cell type');value=None if raw is None else Decimal(raw);require(value is None or value.is_finite(),'Finite numeric cell')
                si=int(cell.get('s','0'));require(si>=0 and (not styles or si<len(styles)),'Style index')
                cells[a]=dict(kind=kind,value=value,formula=formula,text_format=bool(styles and styles[si]=='@'))
            sheets[name]=cells
            validations[name]=[dict(sqref=v.get('sqref'),type=v.get('type'),operator=v.get('operator'),formula1=v.findtext(f'{{{M}}}formula1'),formula2=v.findtext(f'{{{M}}}formula2')) for v in root.findall(f'{{{M}}}dataValidations/{{{M}}}dataValidation')]
            sr=posixpath.join(posixpath.dirname(part),'_rels',posixpath.basename(part)+'.rels');relationships_map=relationships(sr) if sr in names else {}
            chart_ordinal=0
            for drawing in root.findall(f'{{{M}}}drawing'):
                dr=relationships_map[drawing.get(f'{{{R}}}id')];require(dr.get('TargetMode')!='External' and dr['Type']==R+'/drawing','Internal drawing')
                target=dr['Target'];dp=posixpath.normpath(target.lstrip('/') if target.startswith('/') else posixpath.join(posixpath.dirname(part),target));require(dp.startswith('xl/drawings/') and dp in names,'Drawing part')
                droot=xml(z.read(dp));drp=posixpath.join(posixpath.dirname(dp),'_rels',posixpath.basename(dp)+'.rels');drs=relationships(drp)
                for chart in droot.findall(f'.//{{{C}}}chart'):
                    cr=drs[chart.get(f'{{{R}}}id')];require(cr.get('TargetMode')!='External' and cr['Type']==R+'/chart','Internal chart')
                    target=cr['Target'];cp=posixpath.normpath(target.lstrip('/') if target.startswith('/') else posixpath.join(posixpath.dirname(dp),target));require(re.fullmatch(r'xl/(?:drawings/)?charts/chart\d+\.xml',cp) and cp in names and cp not in owners,'Single chart owner')
                    owners[cp]=(name,chart_ordinal);chart_ordinal+=1
            for link in root.findall(f'{{{M}}}hyperlinks/{{{M}}}hyperlink'):
                r=relationships_map.get(link.get(f'{{{R}}}id'));require(r and r['Type']==R+'/hyperlink' and r.get('TargetMode')=='External','Native relative hyperlink')
                require(re.fullmatch(r'package-[0-9]{4}\.xlsx',r['Target']),'Only relative declared package links')
                links.append(dict(worksheet=name,cell=link.get('ref'),target=r['Target'],location=link.get('location')))
        charts=[]
        for part in sorted((n for n in names if re.fullmatch(r'xl/(?:drawings/)?charts/chart\d+\.xml',n)),key=lambda n:int(re.search(r'chart(\d+)\.xml',n)[1])):
            root=xml(z.read(part));series=[]
            for ser in root.findall(f'.//{{{C}}}ser'):
                cat=ser.find(f'{{{C}}}cat');val=ser.find(f'{{{C}}}val')
                require(cat is not None and val is not None,'Explicit chart category/value sources')
                catf=cat.findall(f'.//{{{C}}}f');vf=val.findall(f'.//{{{C}}}f');require(len(catf)==len(vf)==1,'One category/value formula per series')
                series.append(dict(category_formula=catf[0].text,formula=vf[0].text))
            require(series and part in owners,'Nonempty owned native chart');types=[x.tag.split('}')[-1] for x in root.findall(f'.//{{{C}}}plotArea/*') if x.tag.split('}')[-1].endswith('Chart')];require(len(types)==1,'Single chart type');owner,order=owners[part];charts.append(dict(part=part,worksheet=owner,chart_ordinal=order,chart_type=types[0],title=''.join(x.text or '' for x in root.findall(f'.//{{{C}}}title//{{{A}}}t')),series=series))
        require(set(owners)=={v['part'] for v in charts},'No orphan chart references');return dict(sheets=sheets,charts=charts,native_links=links,validations=validations)


def cell_equal(cell,expected):
    if cell is None:require(expected is None or expected=='','Missing expected cell');return
    require(cell['formula'] is None and cell['kind']!='e','Literal source cell cannot be formula/error')
    value=cell['value']
    if expected is None:require(value is None or value=='','NULL not zero');return
    if type(expected) is bool:require(cell['kind']=='b' and value is expected,'Boolean not numeric');return
    if type(expected) in (int,float):
        require(cell['kind']=='n' and isinstance(value,Decimal),'Numeric type');require(type(expected) is int or math.isfinite(expected),'Finite expected value')
        if expected==0:require(value==0,'Exact zero, no hidden underflow');return
        if type(expected) is int:require(value==Decimal(expected),'Exact bounded integer');return
        actual=float(value);require(math.isfinite(actual) and abs(actual-expected)<=max(math.ulp(expected)*4,abs(expected)*1e-14),'Stored binary64 display tolerance');return
    require(type(expected) is str and cell['kind'] in ('str','s','inlineStr'),'Exact text type')
    # Artifact literal escaping may preserve apostrophe or use quotePrefix.
    require(value==expected or (expected.startswith('=') and value=="'"+expected),'Exact literal text')


def inspect_expected_cells(workbook,expected_cells,chart_sources,native_links=None):
    require(type(expected_cells) is dict and set(expected_cells)=={'sheets'},'Expected cell sidecar schema')
    require([s['name'] for s in expected_cells['sheets']]==list(workbook['sheets']),'Full worksheet order')
    count=0
    for sheet in expected_cells['sheets']:
        expected={}
        for area in sheet['ranges']:
            require(set(area) in ({'range','values'},{'range','formulas'}),'Exact rectangular sidecar');kind='values' if 'values' in area else 'formulas';a,b=rectangle(area['range']);rows=area[kind]
            require(len(rows)==b[0]-a[0]+1 and all(len(r)==b[1]-a[1]+1 for r in rows),'Complete range values')
            for i,row in enumerate(rows):
                for j,value in enumerate(row):
                    key=address(a[0]+i,a[1]+j);item=(kind,value);require(key not in expected or expected[key]==item,'No contradictory overlaps');expected[key]=item
        cells=workbook['sheets'][sheet['name']]
        for key,(kind,value) in expected.items():
            c=cells.get(key)
            if kind=='formulas' and value not in (None,''):
                require(type(value) is str and value.startswith('=') and c is not None and c['formula']==value[1:],'Exact saved formula');require(c['kind']!='e' or c['value']=='#N/A','No unexpected cached errors')
            else:cell_equal(c,value)
            count+=1
        for key,c in cells.items():require(key in expected or (c['formula'] is None and c['value'] in (None,'')),'Extra nonempty cell')
    require(workbook['charts']==chart_sources['charts'],'All native chart series/formulas exact')
    if native_links is not None:require(workbook['native_links']==native_links,'All native link targets and locations')
    else:require(not workbook['native_links'],'Unexpected hyperlinks')
    return dict(schema='H_XLSX_SIDECAR_CHECK_V1',checked_cell_count=count,worksheet_count=len(workbook['sheets']),chart_count=len(workbook['charts']),producer_expectations_are_not_independent_source_proof=True,**FLAGS)


def number(q):
    if q is None:return None
    x=Fraction(int(q['numerator']),int(q['denominator']))
    try:v=float(x)
    except OverflowError:return None
    return v if math.isfinite(v) and (v!=0 or x==0) else None

def literal(v):return json.dumps(v,ensure_ascii=False,separators=(',',':'),allow_nan=False)
def same_json(a,b):
    if type(a) in (int,float) and type(b) in (int,float):return Fraction(str(a))==Fraction(str(b))
    if type(a) is not type(b):return False
    if type(a) is dict:return set(a)==set(b) and all(same_json(a[k],b[k]) for k in a)
    if type(a) is list:return len(a)==len(b) and all(same_json(x,y) for x,y in zip(a,b))
    return a==b

def json_cell(cell,value):
    require(cell and cell['formula'] is None and cell['kind'] in ('str','s','inlineStr'),'JSON source text')
    parsed=json.loads(cell['value']);require(same_json(parsed,value),'Original structured literal')
def source_table(workbook,name,rows,json_columns=()):
    cells=workbook['sheets'][name];width=len(rows[0]) if rows else 0
    for i,row in enumerate(rows,2):
        require(len(row)==width,'Rectangular independent projection')
        for j,value in enumerate(row,1):
            cell=cells.get(address(i,j))
            if j in json_columns:json_cell(cell,value)
            else:cell_equal(cell,value)
    for a,c in cells.items():
        r,k=position(a)
        if r>len(rows)+1 or k>width:require(c['formula'] is None and c['value'] in (None,''),'Extra source table tail/column')
    return len(rows)*width


def inspect_saved_source_tables(workbook,tasks,expected_task_ids,classification=None,max_rows_per_sheet=100000):
    """Independent literal projection, never calls the JS producers/aggregator.

    Validates source-bearing tables. Dynamic selector formulas/chart-to-sheet
    ownership still require the future graph verifier; not full H acceptance.
    """
    require(tasks and [t['numerical_task_id'] for t in tasks]==expected_task_ids and len(set(expected_task_ids))==len(tasks),'Full package source order')
    require(type(max_rows_per_sheet) is int and 0<max_rows_per_sheet<=100000,'Saved pagination engineering bound')
    calendar=tasks[0]['calendar'];require(len(calendar)==127 and calendar==sorted(set(calendar)),'Full127 calendar')
    index=[];candidate=[];shared=[];count=0
    for i,t in enumerate(tasks):
        require(t['schema']=='DATED_WORKBOOK_TASK_EXTENSION_TABLES_V1' and t['calendar']==calendar,'Restored actual source rows')
        for k in ('source_bytes_authenticated','formal_comparison_passed','point_in_time_verified','promotion_allowed','future_independent_oos','economics_recomputed','risk_recomputed','risk_chains_reaggregated','account_executed','winner_selected'):require(t[k] is False,'Original display limits')
        require(set(t['series'])==set(ROLES),'Six roles without merge')
        index.append([i+1,'ID: '+t['numerical_task_id'],t['original_task_summary_row']['k'],t['original_task_summary_row']['weight_spec'],t['series']['candidate_integer']['status'],t['numerical_task_id']])
        for day in range(127):
            a=t['series']['candidate_integer']['slots'][day];b=t['series']['candidate_continuous']['slots'][day]
            require(a['session']==b['session']==calendar[day],'Source slot dates')
            candidate.append([calendar[day],a['display_value'] if a['display_value'] is not None else '缺失或超出展示精度',b['display_value'] if b['display_value'] is not None else '缺失或超出展示精度',a['exact_value'],b['exact_value'],a['display_status'],b['display_status']])
        for role in SHARED:require(same_json(t['series'][role],tasks[0]['series'][role]),'Shared role exact identity and payload')
        for role in ('incumbent_integer','incumbent_continuous'):require(same_json(t['risk_tracks'][role],tasks[0]['risk_tracks'][role]),'Shared daily risk exact identity and payload')
    for day in range(127):
        slots=[tasks[0]['series'][role]['slots'][day] for role in SHARED]
        shared.append([calendar[day]]+[v['display_value'] if v['display_value'] is not None else '缺失或超出展示精度' for v in slots]+[v['exact_value'] for v in slots])
    count+=source_table(workbook,'任务索引',index,(4,));count+=source_table(workbook,'候选路径',candidate,(4,5));count+=source_table(workbook,'共享路径',shared,(6,7,8,9))
    pages=[[]];coordinates=[];sources=[];reuse={}
    def block(t,ti,role,day):
        target=role.endswith('_target');who=role.split('_')[0];holder=t['original_target_chain_evidence'][who] if target else t['risk_tracks'][role]
        status='SAVED_ORIGINAL_TARGET' if target else holder['status'];row=None if target or holder['rows'] is None else holder['rows'][day];agg=holder['aggregation'] if target else (row['aggregation'] if row else None)
        key=(role,day) if not target and role.startswith('incumbent') else None
        if key in reuse:return reuse[key]
        groups=agg['rows'] if agg else [];n=max(1,len(groups));require(n<=max_rows_per_sheet,'No split group block')
        if len(pages[-1])+n>max_rows_per_sheet:pages.append([])
        start=len(pages[-1])+2;source_id=len(sources);source_ref=holder['source_evidence']['source_reference'] if target else holder.get('source_reference')
        pointer='/original_target_chain_evidence/'+who if target else f'/risk_tracks/{role}/rows/{day}'
        sources.append([source_id,'ID: '+t['numerical_task_id'],role,'原目标' if target else calendar[day],pointer,source_ref])
        denominator=agg['normalized_display_denominator'] if agg else None;cash=number(row.get('cash_fraction_display')) if row else None;cash=MISSING if cash is None else cash
        for g in groups or [None]:
            raw=number(g['saved_literal_sum']) if g else None;share=number(g['normalized_display_share']) if g else None
            pages[-1].append(['共享' if key else ti+1,'ID: '+t['numerical_task_id'],role,'原目标固定' if target else calendar[day],('UNKNOWN（原null）' if g['risk_chain'] is None else g['risk_chain']) if g else ('无保存分组' if status=='AVAILABLE' else status),g['unknown'] if g else None,g['saved_literal_sum'] if g else None,MISSING if raw is None else raw,g['normalized_display_share'] if g else None,MISSING if share is None else share,denominator,agg['stock_denominator_defined'] if agg else False,row.get('cash_usd_preserved') if row else None,cash,' | '.join(m['security_id'] for m in g['members']) if g else '',source_id,status])
        out=[len(pages),start,n,status,literal(denominator),cash]
        if key:reuse[key]=out
        return out
    for i,t in enumerate(tasks):
        targets=block(t,i,'candidate_target',0)+block(t,i,'incumbent_target',0)
        for day in range(127):coordinates.append([i+1,calendar[day]]+targets+sum((block(t,i,role,day) for role in ROLES[:4]),[]))
    for prefix,data,jcols in [('风险明细',pages,(7,9,11,13)),('风险定位',[coordinates[i:i+max_rows_per_sheet] for i in range(0,len(coordinates),max_rows_per_sheet)],()),('风险来源',[sources[i:i+max_rows_per_sheet] for i in range(0,len(sources),max_rows_per_sheet)],(6,))]:
        names=[f'{prefix}{i+1:03d}' for i in range(len(data))];require(sorted(n for n in workbook['sheets'] if n.startswith(prefix))==names,'Every paginated risk table')
        for name,rows in zip(names,data):count+=source_table(workbook,name,rows,jcols)
    if classification is not None:count+=inspect_classification_table(workbook,classification)
    return dict(schema='H_INDEPENDENT_SAVED_SOURCE_TABLE_CHECK_V1',task_count=len(tasks),calendar_count=127,risk_detail_rows=sum(map(len,pages)),source_cells_verified=count,risk_detail_page_lengths=[len(p) for p in pages],risk_coordinate_page_lengths=[len(coordinates[i:i+max_rows_per_sheet]) for i in range(0,len(coordinates),max_rows_per_sheet)],max_saved_group_slots=max([1]+[len(v['aggregation']['rows']) for t in tasks for v in t['original_target_chain_evidence'].values()]+[len(d['aggregation']['rows']) for t in tasks for v in t['risk_tracks'].values() for d in (v['rows'] or [])]),chart_graph_semantics_verified=False,source_projection_scope='PATH_AND_COMPLETE_RISK_GROUP_LITERAL_TABLES;NO_DYNAMIC_FORMULA_EVALUATION_OR_CHART_OWNERSHIP_CERTIFICATION',**FLAGS)


def inspect_capture_records(workbook,records,chart_index,native_links=None):
    """Adapt publisher rectangle records; formulas take precedence over caches."""
    sheets={}
    for r in records:
        name=r['worksheet'];sr=integer(r['start_row_zero_based']);sc=integer(r['start_column_zero_based']);nr=integer(r['row_count']);nc=integer(r['column_count']);require(nr and nc,'Nonempty captured range')
        values=r['values'];formulas=r['formulas'];require(len(values)==len(formulas)==nr and all(len(x)==nc for x in values+formulas),'Complete values and formula rectangles')
        ranges=sheets.setdefault(name,[])
        for i in range(nr):
            for j in range(nc):
                f=formulas[i][j];key='formulas' if f not in (None,'') else 'values';ranges.append({'range':address(sr+i+1,sc+j+1),key:[[f if key=='formulas' else values[i][j]]]})
    expected={'sheets':[{'name':name,'ranges':ranges} for name,ranges in sheets.items()]}
    charts=[];by_owner={}
    for c in chart_index['charts']:
        key=(c['worksheet'],integer(c['chart_ordinal']));require(key not in by_owner,'Unique sidecar chart owner/order');by_owner[key]=c
    require(len(by_owner)==len(workbook['charts']),'Complete chart list')
    for actual in workbook['charts']:
        key=(actual['worksheet'],actual['chart_ordinal']);require(key in by_owner,'Chart source sidecar owner/order');c=by_owner[key]
        normalize=lambda f:f[1:] if f.startswith('=') else f
        charts.append({'part':actual['part'],'worksheet':actual['worksheet'],'chart_ordinal':actual['chart_ordinal'],'chart_type':actual['chart_type'],'title':actual['title'],'series':[{'category_formula':normalize(s['categoryFormula']),'formula':normalize(s['formula'])} for s in c['series']]})
    return inspect_expected_cells(workbook,expected,{'charts':charts},native_links)


def expected_navigation_links(packages,expected_task_ids):
    require(len(expected_task_ids)==1632 and len(set(expected_task_ids))==1632,'Full navigation denominator')
    links=[];ordinal=0
    for pi,p in enumerate(packages):
        require(p['package_index']==pi and p['start_task_ordinal']==ordinal and re.fullmatch(r'package-[0-9]{4}\.xlsx',p['filename']),'Ordered package')
        for local,t in enumerate(p['tasks'],1):
            require(t['task_ordinal']==ordinal and t['numerical_task_id']==expected_task_ids[ordinal] and t['local_task_number']==local and t['navigation_row']==local+1,'Exact navigation identity')
            links.append(dict(worksheet='全部任务',cell=f'H{ordinal+2}',target=p['filename'],location=f"'任务索引'!A{local+1}"));ordinal+=1
        require(p['stop_task_ordinal']==ordinal,'Complete package span')
    require(ordinal==1632,'No unprocessed tasks');return links


def reference_range(formula):
    """Canonical direct chart range; no names/external/union/formulas accepted."""
    require(type(formula) is str,'Chart reference text');f=formula[1:] if formula.startswith('=') else formula
    match=re.fullmatch(r"(?:'((?:[^']|'')+)'|([^'!]+))!\$?([A-Z]+)\$?([1-9][0-9]*):\$?([A-Z]+)\$?([1-9][0-9]*)",f)
    require(match is not None,'Explicit single finite chart range')
    sheet=(match[1].replace("''", "'") if match[1] is not None else match[2]);a=match[3]+match[4];b=match[5]+match[6];rectangle(a+':'+b)
    return sheet,a,b


def static_graph_contract(task_count,source_report,max_rows_per_sheet=100000):
    """Independent fixed selector-to-verified-table graph, not formula evaluation."""
    require(type(task_count) is int and task_count>0,'Package count')
    groups=source_report['max_saved_group_slots'];integer(groups);require(1<=groups<=128,'Saved group capacity')
    detail=source_report['risk_detail_page_lengths'];coords=source_report['risk_coordinate_page_lengths'];require(detail and coords,'Source-verified full risk pages')
    formulas={};literals={};charts=[]
    def formula(sheet,cell,value):formulas[(sheet,cell)]=value
    def lit(sheet,cell,value):literals[(sheet,cell)]=value
    lit('路径查看','B4',1);lit('风险查看','B4',1);formula('风险查看','B3',"'路径查看'!B4")
    def selected(value):return f'IF(ISNUMBER($B$4),IF(AND($B$4=INT($B$4),$B$4>=1,$B$4<={task_count}),{value},NA()),NA())'
    formula('路径查看','B5',selected(f"INDEX('任务索引'!$B$2:$B${task_count+1},$B$4)"))
    for i in range(127):
        refs=[f"INDEX('候选路径'!$B$2:$B${task_count*127+1},($B$4-1)*127+{i+1})",f"'共享路径'!B{i+2}",f"INDEX('候选路径'!$C$2:$C${task_count*127+1},($B$4-1)*127+{i+1})",f"'共享路径'!C{i+2}",f"'共享路径'!D{i+2}",f"'共享路径'!E{i+2}"]
        formula('路径查看',f'A{i+49}',f"'共享路径'!A{i+2}")
        for j,r in enumerate(refs,2):formula('路径查看',address(i+49,j),selected(f'IF(ISNUMBER({r}),{r},NA())'))
    for ordinal,columns in enumerate(('BCFG','DEFG')):
        charts.append(dict(worksheet='路径查看',chart_ordinal=ordinal,chart_type='lineChart',title=['整数账户与012922（期初=1）','连续权重与012922（期初=1）'][ordinal],roles=[ROLES[0],ROLES[1],ROLES[4],ROLES[5]] if ordinal==0 else [ROLES[2],ROLES[3],ROLES[4],ROLES[5]],series=[dict(category_formula='路径查看!A49:A175',formula=f'路径查看!{c}49:{c}175') for c in columns]))
    global_index='(($B$3-1)*127+$B$4)';page=f'INT(({global_index}-1)/{max_rows_per_sheet})+1';local=f'MOD(({global_index}-1),{max_rows_per_sheet})+1'
    # Match the fixed explicit MOD syntax used by the reviewed component.
    local=f'MOD({global_index}-1,{max_rows_per_sheet})+1'
    valid=f'AND($B$3=INT($B$3),$B$3>=1,$B$3<={task_count},$B$4=INT($B$4),$B$4>=1,$B$4<=127)'
    def coord(col):
        letter=address(1,col+1)[:-1]
        options=','.join(f"INDEX('风险定位{i+1:03d}'!${letter}$2:${letter}${n+1},MIN({local},{n}))" for i,n in enumerate(coords))
        return f'IF(AND(ISNUMBER($B$3),ISNUMBER($B$4)),IF({valid},CHOOSE({page},{options}),NA()),NA())'
    formula('风险查看','B5',coord(1));height=max(22,groups*2);stride=height+8;helper_start=8+6*stride+10
    labels=['候选原目标（非引擎或持仓）','原8原目标（非引擎或持仓）','候选整数：股票权重 / 现金另列','原8整数：股票权重 / 现金另列','候选连续：成本后贡献','原8连续：成本后贡献']
    roles=['candidate_target','incumbent_target']+list(ROLES[:4])
    for ri,role in enumerate(roles):
        panel=8+ri*stride;helper=helper_start+ri*(groups+3);start=2+ri*6
        lit('风险查看',f'A{panel}',labels[ri])
        for step,offset in ((1,3),(2,4),(3,5)):formula('风险查看',f'B{panel+step}',coord(start+offset))
        for j in range(3):formula('风险查看',address(panel+1,10+j),coord(start+j))
        def source(col,i):
            options=','.join(f"INDEX('风险明细{p+1:03d}'!${col}$2:${col}${n+1},MIN($K${panel+1}-1+{i},{n}))" for p,n in enumerate(detail))
            return f'CHOOSE($J${panel+1},{options})'
        for i in range(groups):
            inside=f'{i}<$L${panel+1}';label=source('E',i);raw=source('H',i);share=source('J',i)
            formula('风险查看',f'A{helper+1+i}',f'IF({inside},{label},"")')
            formula('风险查看',f'B{helper+1+i}',f'IF({inside},IF(ISNUMBER({raw}),{raw},NA()),NA())')
            formula('风险查看',f'C{helper+1+i}',f'IF({inside},IF(ISNUMBER({share}),{share},NA()),NA())')
        charts.append(dict(worksheet='风险查看',chart_ordinal=ri,chart_type='barChart',title=labels[ri],roles=[role],series=[dict(category_formula=f'风险查看!A{helper+1}:A{helper+groups}',formula=f'风险查看!{c}{helper+1}:{c}{helper+groups}') for c in 'BC']))
    return dict(formulas=formulas,literals=literals,charts=charts)


def inspect_static_chart_graph(workbook,tasks,expected_task_ids,max_rows_per_sheet=100000):
    source=inspect_saved_source_tables(workbook,tasks,expected_task_ids,max_rows_per_sheet=max_rows_per_sheet)
    contract=static_graph_contract(len(tasks),source,max_rows_per_sheet)
    for (sheet,a),value in contract['literals'].items():cell_equal(workbook['sheets'][sheet].get(a),value)
    for (sheet,a),value in contract['formulas'].items():
        cell=workbook['sheets'][sheet].get(a);require(cell and cell['formula']==value,'Selector/source formula mismatch '+sheet+'!'+a)
    for sheet,maxvalue in [('路径查看',len(tasks)),('风险查看',127)]:
        actual=workbook['validations'].get(sheet,[]);require(actual==[dict(sqref='B4',type='whole',operator='between',formula1='1',formula2=str(maxvalue))],'Only explicit task/date selector validation')
    charts=workbook['charts'];require(len(charts)==8,'Two path plus six complete risk charts')
    mapping={(c['worksheet'],c['chart_ordinal']):c for c in charts};require(len(mapping)==8,'Unique chart ownership/order')
    for expected in contract['charts']:
        actual=mapping.get((expected['worksheet'],expected['chart_ordinal']));require(actual and actual['chart_type']==expected['chart_type'] and actual['title']==expected['title'],'Chart worksheet/type/title/role')
        require(len(actual['series'])==len(expected['series']),'Complete fixed role series')
        for got,wanted in zip(actual['series'],expected['series']):
            for key in ('category_formula','formula'):require(reference_range(got[key])==reference_range(wanted[key]),'Chart role source range')
    return dict(schema='H_INDEPENDENT_STATIC_CHART_GRAPH_CHECK_V1',source_tables=source,chart_count=8,selector_formula_count=len(contract['formulas']),static_chart_source_graph_verified=True,dynamic_formula_evaluation_verified=False,**FLAGS)


def inspect_classification_table(workbook,classification):
    rows=classification['rows'];require(len(rows)==101,'All101 classifications')
    expected=[]
    for i,r in enumerate(rows):expected.append([i+1,r['ticker'],r['security_id'],r['issuer_id'],r['saved_risk_chain'] if r['saved_risk_chain'] is not None else '未知','是' if r['training_selected'] else '否',r['classification_status'],r['nonselection_evidence'],r['original_wiring_row']['original_windows'],r['original_wiring_row']['new_assumed_window'],'未认证',f'classification.json#/rows/{i}',r['wiring_row_reference'],r['training_provenance_reference']])
    return source_table(workbook,'分类覆盖',expected,(8,9,10,13,14))
