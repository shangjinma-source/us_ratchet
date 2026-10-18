"""Entirely synthetic physical H recovery tree; no SDK or saved research data."""
import copy,io,json,zipfile
from decimal import Decimal
from pathlib import Path
from xml.sax.saxutils import escape,quoteattr
from scripts import ndx_h_failed_export_recovery_independent_readback_20261003 as r
from backtest import ndx_h_workbook_export_inspection_research as z
from test_ndx_h_workbook_export_inspection_research import source_fixture,cells


def pack(wb):
 parts={};sheets=[];bookrels=[];chartnum=0
 for si,(name,table)in enumerate(wb['sheets'].items(),1):
  sheets.append(f'<sheet name={quoteattr(name)} sheetId="{si}" r:id="r{si}"/>');bookrels.append(f'<Relationship Id="r{si}" Type="{z.R}/worksheet" Target="worksheets/sheet{si}.xml"/>')
  rows={}
  for a,c in table.items():
   row,col=z.position(a);v=c['value'];kind=c['kind'];f=c.get('formula');body='' if not f else '<f>'+escape(f)+'</f>'
   if kind=='str':body+='<is><t xml:space="preserve">'+escape(v or '')+'</t></is>';kind='inlineStr'
   elif v is not None:body+='<v>'+escape(('1'if v else'0')if kind=='b'else str(v))+'</v>'
   rows.setdefault(row,[]).append(f'<c r="{a}" t="{kind}">{body}</c>')
  tail='';rels=[];owner=[c for c in wb.get('charts',[])if c['worksheet']==name]
  if owner:
   tail+='<drawing r:id="draw"/>';rels.append(f'<Relationship Id="draw" Type="{z.R}/drawing" Target="../drawings/drawing{si}.xml"/>');anchors=[];drawrels=[]
   for c in owner:
    chartnum+=1;rid=f'c{chartnum}';anchors.append(f'<xdr:twoCellAnchor><c:chart r:id="{rid}"/></xdr:twoCellAnchor>');drawrels.append(f'<Relationship Id="{rid}" Type="{z.R}/chart" Target="../charts/chart{chartnum}.xml"/>')
    series=''.join('<c:ser><c:cat><c:strRef><c:f>'+escape(s['category_formula'])+'</c:f></c:strRef></c:cat><c:val><c:numRef><c:f>'+escape(s['formula'])+'</c:f></c:numRef></c:val></c:ser>'for s in c['series'])
    parts[f'xl/charts/chart{chartnum}.xml']=f'<c:chartSpace xmlns:c="{z.C}" xmlns:a="{z.A}"><c:chart><c:title><c:tx><a:t>{escape(c["title"])}</a:t></c:tx></c:title><c:plotArea><c:{c["chart_type"]}>{series}</c:{c["chart_type"]}></c:plotArea></c:chart></c:chartSpace>'
   parts[f'xl/drawings/drawing{si}.xml']=f'<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" xmlns:c="{z.C}" xmlns:r="{z.R}">'+''.join(anchors)+'</xdr:wsDr>'
   parts[f'xl/drawings/_rels/drawing{si}.xml.rels']=f'<Relationships xmlns="{z.P}">'+''.join(drawrels)+'</Relationships>'
  links=[l for l in wb.get('native_links',[])if l['worksheet']==name]
  if links:
   items=[]
   for j,l in enumerate(links):
    rid=f'h{j}';items.append(f'<hyperlink ref={quoteattr(l["cell"])} r:id="{rid}" location={quoteattr(l["location"])}/>');rels.append(f'<Relationship Id="{rid}" Type="{z.R}/hyperlink" Target={quoteattr(l["target"])} TargetMode="External"/>')
   tail+='<hyperlinks>'+''.join(items)+'</hyperlinks>'
  vals=wb.get('validations',{}).get(name,[])
  if vals:tail+='<dataValidations>'+''.join('<dataValidation '+ ' '.join(k+'='+quoteattr(v[k])for k in ('sqref','type','operator'))+'><formula1>'+v['formula1']+'</formula1><formula2>'+v['formula2']+'</formula2></dataValidation>'for v in vals)+'</dataValidations>'
  parts[f'xl/worksheets/sheet{si}.xml']=f'<worksheet xmlns="{z.M}" xmlns:r="{z.R}"><sheetData>'+''.join(f'<row r="{n}">'+''.join(v)+'</row>'for n,v in sorted(rows.items()))+'</sheetData>'+tail+'</worksheet>'
  if rels:parts[f'xl/worksheets/_rels/sheet{si}.xml.rels']=f'<Relationships xmlns="{z.P}">'+''.join(rels)+'</Relationships>'
 parts['xl/workbook.xml']=f'<workbook xmlns="{z.M}" xmlns:r="{z.R}"><sheets>'+''.join(sheets)+'</sheets></workbook>'
 parts['xl/_rels/workbook.xml.rels']=f'<Relationships xmlns="{z.P}">'+''.join(bookrels)+'</Relationships>'
 out=io.BytesIO()
 with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED)as archive:
  for n,b in parts.items():archive.writestr(n,b)
 return out.getvalue()


def capture(wb):
 out=[];ranges=[]
 for name,table in wb['sheets'].items():
  nr=max([z.position(a)[0]for a in table]or[1]);nc=max([z.position(a)[1]for a in table]or[1]);values=[[None]*nc for _ in range(nr)];formulas=copy.deepcopy(values)
  for a,c in table.items():
   i,j=z.position(a);v=c['value'];values[i-1][j-1]=float(v)if type(v)is Decimal else v;formulas[i-1][j-1]='='+c['formula']if c.get('formula')else None
  out.append(dict(worksheet=name,start_row_zero_based=0,start_column_zero_based=0,row_count=nr,column_count=nc,values=values,formulas=formulas));ranges.append(dict(worksheet=name,rows=nr,columns=nc))
 return b''.join(r.enc(x)+b'\n'for x in out),ranges


def encode(v):return json.dumps(v,ensure_ascii=False,separators=(",",":"),allow_nan=False).encode()

def physical(root):
 parent=root/'failed';recovery=root/'recovered';data=root/'data';auditdir=root/'audit';output=root/'readback';code=root/'code'
 for p in (parent,recovery,data,auditdir,code):p.mkdir()
 def put(p,value):
  p.parent.mkdir(parents=True,exist_ok=True);b=value if type(value)is bytes else encode(value);p.write_bytes(b);return r.reference(p,r.sha(b))
 def snap(p,wb):
  b,ranges=capture(wb);return dict(**put(p,b),byte_count=len(b),record_count=len(ranges),ranges=ranges)
 f=dict.fromkeys(r.EXPORT_FALSE,False);f.update(source_bytes_authenticated=False,native_excel_open_verified=False)
 codes={k:put(code/(k+'.txt'),('UNEXECUTABLE '+k).encode())for k in r.CODE}
 refs={k:put(code/(k+'.txt'),('UNEXECUTABLE '+k).encode())for k in ('source_phase','recovery_publisher')}
 for k in ('inspection','zip_core'):refs[k]=r.reference(*r.BOUND[k])
 original_wb,original_task=source_fixture();baseid=original_task['numerical_task_id'];base=copy.deepcopy(original_task)
 base.update(source_index={role:copy.deepcopy(base['series'][role]['source_reference'])for role in z.ROLES},input_references={},original_provenance_and_missing={},preserved_evidence_sidecars={},engine_normalization_evidence={},original_target_evidence={})
 shared={'series':{},'risk':{}}
 for role in z.SHARED:
  identity=dict(role=role,source_reference=base['source_index'][role]);shared['series'][role]=dict(identity=identity,series=copy.deepcopy(base['series'][role]))
  if role.startswith('incumbent'):shared['risk'][role]=dict(identity=identity,risk=copy.deepcopy(base['risk_tracks'][role]))
 ids=[f'{i:064x}'for i in range(1632)];lines=[];indexrows=[];offset=0
 for i,tid in enumerate(ids):
  if i<44:
   t=copy.deepcopy(base);t['numerical_task_id']=tid;t['task_ordinal']=i
   for role in z.SHARED:
    t['series'][role]={'shared_series_id':role}
    if role.startswith('incumbent'):t['risk_tracks'][role]={'shared_risk_id':role}
  else:t=dict(schema='DATED_WORKBOOK_TASK_EXTENSION_MISSING_V1',task_ordinal=i,numerical_task_id=tid)
  line=encode(t)+b'\n';lines.append(line);indexrows.append(dict(task_ordinal=i,numerical_task_id=tid,status='DISPLAY_PROJECTED'if i<44 else'COMPARISON_NOT_SUPPLIED',k=4,weight_spec='equal',jsonl_record=dict(record_index=i,byte_start=offset,byte_stop=offset+len(line),row_sha256=r.sha(line))));offset+=len(line)
 classification={'rows':[dict(ticker='T'+str(i),security_id='S'+str(i),issuer_id='I'+str(i),saved_risk_chain=None,training_selected=False,classification_status='UNKNOWN',nonselection_evidence=None,original_wiring_row=dict(original_windows=[],new_assumed_window=None),wiring_row_reference={},training_provenance_reference={})for i in range(101)]}
 inputs=dict(codes);inputs.update(tasks=put(data/'tasks.jsonl',b''.join(lines)),shared=put(data/'shared_display.json',shared),classification=put(data/'classification.json',classification))
 index=dict(schema='SOURCE_BOUND_DATED_WORKBOOK_EXTENSION_DATA_V1',planned_task_count=1632,projected_task_count=44,not_supplied_task_count=1588,task_index=indexrows,task_jsonl_reference=dict(**inputs['tasks'],record_count=1632,byte_count=offset),shared_display_reference=inputs['shared'],classification_reference=inputs['classification'],source_hashes={codes['data_producer']['path']:codes['data_producer']['sha256']},**dict.fromkeys(r.DATA_FALSE,False))
 inputs['index']=put(data/'index.json',index)
 pub=dict(schema='DATED_WORKBOOK_EXTENSION_DATA_PUBLICATION_V1',status='PUBLISHED_DISPLAY_DATA_NOT_WORKBOOK_DELIVERY',index_reference=inputs['index'],source_hashes=index['source_hashes'],**{k:index[k]for k in ('task_jsonl_reference','shared_display_reference','classification_reference')},**dict.fromkeys(r.DATA_FALSE,False));inputs['publication']=put(data/'publication.json',pub);put(data/'started.json',{})
 audit=dict(schema='DATED_WORKBOOK_EXTENSION_DATA_INDEPENDENT_READBACK_V1',status='PASS',index_reference=inputs['index'],publication_reference=inputs['publication'],reader_sha256=codes['data_reader']['sha256'],detail=dict(planned_tasks=1632,projected_tasks=44,missing_tasks=1588,output_rows=1632),classification_rows_verified=101,verified_jsonl_bytes=offset,verified_jsonl_sha256=inputs['tasks']['sha256'],producer_called=False,pure_projection_called=False,source_hashes={inputs[k]['path']:inputs[k]['sha256']for k in ('index','publication','tasks','shared','classification','data_producer')},**dict.fromkeys(r.DATA_FALSE,False));inputs['audit']=put(auditdir/'independent_readback.json',audit)
 roles=('index','publication','audit','tasks','shared','classification','data_producer','data_reader','core','path_component','risk_component','navigation_component','native_helper');oldsrc={inputs[k]['path']:inputs[k]['sha256']for k in (*roles,'publisher')};oldsrc.update(index['source_hashes']);oldsrc.update(audit['source_hashes'])
 inputs['started']=put(parent/'started.json',dict(schema='DATED_H_WORKBOOK_EXTENSION_STARTED_V1',default_task_id=ids[0],input_references={k:inputs[k]for k in roles},source_hashes=oldsrc,**f));inputs['failure']=put(parent/'failure.json',dict(schema='DATED_H_WORKBOOK_EXTENSION_FAILURE_V1',status='FAILED_DO_NOT_CONSUME',retry_allowed=False,stream_completed=True,all_attempts_retained=True,error='Full ordered task link cells',**f))
 for k in ('index','publication','audit','shared','classification'):put(parent/'sources'/f'{k}.json',Path(inputs[k]['path']).read_bytes())
 for name,key in [('tasks.jsonl','tasks'),('shared_display.json','shared'),('classification.json','classification')]:put(parent/name,Path(inputs[key]['path']).read_bytes())
 shards=[];locations=[]
 for si,start in enumerate(range(0,1632,32)):
  raw=b''.join(lines[start:start+32]);name=f'machine/tasks-{si:05d}.jsonl';ref=put(parent/name,raw);stop=min(start+32,1632);shards.append(dict(shard_index=si,filename=name,start_task_ordinal=start,stop_task_ordinal=stop,record_count=stop-start,byte_count=len(raw),sha256=ref['sha256'],reference=ref));local=0
  for i in range(start,stop):locations.append(dict(task_ordinal=i,shard_index=si,byte_start=local,byte_stop=local+len(lines[i]),row_sha256=r.sha(lines[i])));local+=len(lines[i])
 originals=[];packages=[];cursor=0;links=[]
 for pi,n in enumerate([1]*44+[7]*190+[6]*43):
  a=cursor;b=a+n;cursor=b;tid=ids[a];is_present=a<44;folder=parent/'attempts'/f'attempt-{pi:05d}';filename=f'package-{pi+1:04d}.xlsx';identity=dict(attempt_index=pi,start_task_ordinal=a,stop_task_ordinal=b,task_ids=ids[a:b]);folder.mkdir(parents=True)
  if is_present:
   wb=copy.deepcopy(original_wb)
   for table in wb['sheets'].values():
    for c in table.values():
     if c['value']==baseid:c['value']=tid
     elif c['value']=='ID: '+baseid:c['value']='ID: '+tid
   t=copy.deepcopy(base);t['numerical_task_id']=tid;t['task_ordinal']=a;detail=z.inspect_saved_source_tables(wb,[t],[tid]);graph=z.static_graph_contract(1,detail)
   for (sheet,address),v in graph['literals'].items():wb['sheets'].setdefault(sheet,{})[address]=dict(kind='n'if type(v)is int else'str',value=Decimal(v)if type(v)is int else v,formula=None)
   for (sheet,address),v in graph['formulas'].items():wb['sheets'].setdefault(sheet,{})[address]=dict(kind='n',value=None,formula=v)
   wb['validations']={sheet:[dict(sqref='B4',type='whole',operator='between',formula1='1',formula2=str(count))]for sheet,count in [('路径查看',1),('风险查看',127)]};wb['charts']=graph['charts']
   label=wb['sheets']['路径查看']['B5'];label.update(kind='e',value='#VALUE!');old_wb=copy.deepcopy(wb);label.update(kind='str',value='ID: '+tid,formula="IF(ISNUMBER($B$4),IF(AND($B$4=INT($B$4),$B$4>=1,$B$4<=1),'任务索引'!$B$2,NA()),NA())")
   sources=[]
   for role,day in [('candidate_target',None),('incumbent_target',None)]+[(role,day)for day in range(127)for role in ('candidate_integer','incumbent_integer','candidate_continuous','incumbent_continuous')]:
    who=role.split('_')[0];target=day is None;holder=t['original_target_chain_evidence'][who]if target else t['risk_tracks'][role]
    sources.append(dict(source_id=len(sources),numerical_task_id=tid,role=role,session=None if target else t['calendar'][day],task_pointer='/original_target_chain_evidence/'+who if target else f'/risk_tracks/{role}/rows/{day}',task_pointer_scope='RESOLVED_DISPLAY_TASK_NOT_RAW_JSONL_POINTER',source_reference=holder['source_evidence']['source_reference']if target else holder['source_reference'],saved_missing_evidence=None))
   chart=dict(charts=[dict(worksheet=c['worksheet'],chart_ordinal=c['chart_ordinal'],chart_type=c['chart_type'],title=c['title'],series=[dict(categoryFormula=x['category_formula'],formula=x['formula'])for x in c['series']])for c in wb['charts']],risk_source_index=sources,task_evidence=[{k:t[k]for k in ('numerical_task_id','source_index','input_references','original_provenance_and_missing','preserved_evidence_sidecars')}],engine_evidence=[{k:t[k]for k in ('numerical_task_id','engine_normalization_evidence','original_target_evidence')}],task_selector='路径查看!B4',date_selector='风险查看!B4',default_local_task=1,default_date_index=1)
   data_rows=detail['risk_detail_rows']+254+len(sources)+127+2+len(detail['risk_detail_page_lengths'])+len(detail['risk_coordinate_page_lengths'])
  else:
   wb=dict(sheets={'任务索引':cells([[j+1,'ID: '+ids[i],'COMPARISON_NOT_SUPPLIED']for j,i in enumerate(range(a,b))])},charts=[],native_links=[]);old_wb=wb;data_rows=n+1;chart=dict(charts=[],risk_source_index=[],task_evidence=[],engine_evidence=[],task_selector=None,date_selector=None)
  oldbytes=pack(old_wb);oldref=put(parent/filename,oldbytes);artifact=put(folder/'artifact.xlsx',oldbytes);oldcapture=snap(folder/'expected_cells.jsonl',old_wb)
  chart.update(schema='DATED_H_PACKAGE_CHART_SOURCE_INDEX_V1',**identity,source_jsonl_records=[dict(numerical_task_id=ids[i],task_ordinal=i,source_record=indexrows[i]['jsonl_record'])for i in range(a,b)],**f);oldchart=put(folder/'chart_source_index.json',chart)
  views=[('路径查看','A1:G46'),('风险查看','A1:N43')]if is_present else[('任务索引','A1:C20')];previews=[dict(**put(folder/f'preview-{j}.png',b'png'),worksheet=sheet,range=area)for j,(sheet,area)in enumerate(views)]
  costs=dict(missing=not is_present,taskCount=n,taskIds=ids[a:b],dataRows=data_rows)
  pending=dict(schema='DATED_H_EXPORT_ATTEMPT_V1',status='PENDING_COMPLETE_STREAM_AND_SOURCE_PUBLICATION',**identity,bytes=len(oldbytes),sha256=oldref['sha256'],reference=artifact,expected_cells_reference=oldcapture,chart_source_index_reference=oldchart,previews=previews,costs=costs,**f);pr=put(folder/'pending.json',pending);put(folder/'started.json',dict(status='PENDING_EXPORT_ATTEMPT',**identity,**f))
  old=dict(package_index=pi,filename=filename,start_task_ordinal=a,stop_task_ordinal=b,task_ids=ids[a:b],attempt_index=pi,original_workbook_reference=oldref,byte_count=len(oldbytes),pending_reference=pr,action='REBUILD_SINGLETON_WITH_REGISTERED_B5_ONLY_DELTA'if is_present else'COPY_ORIGINAL_BYTES_NO_SDK_EXPORT');originals.append(old)
  newbytes=pack(wb)if is_present else oldbytes;newref=put(recovery/filename,newbytes);newcapture=oldcapture;newchart=oldchart;repair=None
  if is_present:
   repairdir=recovery/f'repair-{pi:04d}';newcapture=snap(repairdir/'expected_cells.jsonl',wb);newchart=put(repairdir/'chart_source_index.json',encode(chart));previews=[dict(**put(repairdir/f'preview-{j}.png',b'new png'),worksheet=sheet,range=area)for j,(sheet,area)in enumerate(views)]
   count=sum(x['rows']*x['columns']for x in oldcapture['ranges']);repair=put(repairdir/'repair_evidence.json',dict(schema='DATED_H_FAILED_PARENT_SINGLETON_REPAIR_V1',original_attempt_is_not_new_export=True,original_pending_reference=pr,original_workbook_reference=oldref,new_workbook_reference=newref,source_record=indexrows[a]['jsonl_record'],new_byte_count=len(newbytes),cell_preservation=dict(checked_cells=count,changed_cells=1),**f))
  taskmeta=[dict(task_ordinal=i,numerical_task_id=ids[i],comparison_status=indexrows[i]['status'],integer_status='AVAILABLE'if is_present else'COMPARISON_NOT_SUPPLIED',continuous_status='AVAILABLE'if is_present else'COMPARISON_NOT_SUPPLIED',local_task_number=i-a+1,navigation_row=i-a+2)for i in range(a,b)]
  packages.append(dict(old,tasks=taskmeta,workbook_reference=newref,byte_count=len(newbytes),sha256=newref['sha256'],actual_data_rows=data_rows,expected_cells_reference=newcapture,chart_source_index_reference=newchart,previews=previews,repair_evidence_reference=repair))
  links.extend(dict(worksheet='全部任务',cell=f'H{i+2}',target=filename,location=f"'任务索引'!A{i-a+2}")for i in range(a,b))
 navrows=[]
 for p in packages:
  for t in p['tasks']:
   i=t['task_ordinal'];e=indexrows[i];navrows.append([i+1,'ID: '+ids[i],4,'equal',e['status'],t['integer_status'],t['continuous_status'],p['filename'],t['local_task_number'],'分类/来源与风险时点待认证；非独立OOS',e['jsonl_record'],ids[i]])
 classrows=[]
 for i,t in enumerate(classification['rows']):classrows.append([i+1,t['ticker'],t['security_id'],t['issuer_id'],'未知','否','UNKNOWN',None,[],None,'未认证',f'classification.json#/rows/{i}',{},{}])
 nav=dict(sheets={'全部任务':cells(navrows,(4,11)),'分类覆盖':cells(classrows,(8,9,10,13,14))},charts=[],native_links=links)
 navcapture=snap(recovery/'navigation_expected_cells.jsonl',nav);oldnav=copy.deepcopy(nav);oldnav['native_links']=[];snap(parent/'navigation_expected_cells.jsonl',oldnav);put(parent/'attempts/navigation-artifact.xlsx',pack(oldnav));navref=put(recovery/'路径与风险导航.xlsx',pack(nav))
 linkref=put(recovery/'navigation_links.json',dict(schema='DATED_H_RECOVERED_NATIVE_LINKS_V1',links=links,helper_reference=inputs['native_helper'],utf8_transport_reference=inputs['wire'],**f))
 def inv(folder):return [dict(path=p.relative_to(folder).as_posix(),sha256=r.sha(p.read_bytes()),byte_count=p.stat().st_size)for p in sorted(folder.rglob('*'))if p.is_file()]
 oldinv=inv(parent);inventoryref=put(recovery/'parent_inventory.json',dict(parent_root=str(parent),files=oldinv,parent_failure_reference=inputs['failure'],**f))
 plan=dict(schema='DATED_H_FAILED_EXPORT_RECOVERY_PLAN_V1',status='STRUCTURAL_PLAN_PENDING_INDEPENDENT_BYTES_AND_FULL_EOF_VALIDATION',parent_status='FAILED_DO_NOT_CONSUME',old_publication_existed=False,recovery_is_new_attempt=True,package_count=277,planned_task_count=1632,packages=originals,parent_inventory_preserved=oldinv,parent_references=dict(failure=inputs['failure'],started=inputs['started'],index_copy=r.reference(parent/'sources/index.json',inputs['index']['sha256'])),navigation_links=links,singleton_rebuild_count=44,machine_shards=[s['filename']for s in shards],preserved_oversize_attempts=[],machine_eof_verified=False,recovery_dispatch_authorized=False,chart_and_cell_data_verified=False,path_containment_physical_verified=False,**f);planref=put(recovery/'recovery_plan.json',plan)
 machine=dict(schema='DATED_H_RECOVERED_MACHINE_DATA_INDEX_V1',original_bytes_not_reencoded=True,full_tasks_reference=r.reference(parent/'tasks.jsonl',inputs['tasks']['sha256']),shared_reference=r.reference(parent/'shared_display.json',inputs['shared']['sha256']),classification_reference=r.reference(parent/'classification.json',inputs['classification']['sha256']),record_count=1632,byte_count=offset,sha256=inputs['tasks']['sha256'],shards=shards,task_locations=locations,**f);machref=put(recovery/'machine_index.json',machine)
 sources=dict(oldsrc)
 for item in list(inputs.values())+[refs['source_phase'],refs['recovery_publisher']]:sources[item['path']]=item['sha256']
 put(recovery/'started.json',dict(schema='DATED_H_FAILED_EXPORT_RECOVERY_STARTED_V1',parent_status='FAILED_DO_NOT_CONSUME',input_references=inputs,source_hashes=sources,**f))
 m=dict(schema='DATED_H_FAILED_EXPORT_RECOVERY_V1',status='RECOVERED_PENDING_INDEPENDENT_READBACK_AND_VISUAL_ACCEPTANCE',parent_status='FAILED_DO_NOT_CONSUME',old_publication_existed=False,recovery_is_new_attempt=True,parent_failure_reference=inputs['failure'],parent_started_reference=inputs['started'],parent_inventory_reference=inventoryref,recovery_plan_reference=planref,input_references=inputs,source_hashes=sources,planned_task_count=1632,packaged_task_count=1632,unprocessed_task_count=0,packages=packages,machine_index_reference=machref,navigation=dict(workbook_reference=navref,expected_cells_reference=navcapture,native_links_reference=linkref,previews=[],link_count=1632),output_inventory=inv(recovery),output_inventory_excludes=['export_manifest.json','publication.json'],**f)
 refs['manifest']=put(recovery/'export_manifest.json',m);refs['recovery_publication']=put(recovery/'publication.json',dict(schema='DATED_H_FAILED_EXPORT_RECOVERY_PUBLICATION_V1',status='PUBLISHED_RECOVERY_PENDING_INDEPENDENT_READBACK_AND_VISUAL_ACCEPTANCE',manifest_reference=refs['manifest'],source_hashes=sources,**f))
 return dict(BOUND={k:(v['path'],v['sha256'])for k,v in refs.items()},INPUT_BOUND={k:(v['path'],v['sha256'])for k,v in inputs.items()},PARENT=parent,RECOVERY=recovery,DATA=data,OUTPUT=output),m
