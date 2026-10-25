/** H assembly foundation only. No filesystem, Artifact import, or executable publisher.
 * The final source-bound create-only publisher is intentionally NOT IMPLEMENTED.
 * Callbacks are engineering adapters, not source authentication or authority.
 */
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {buildPathComparisonWorkbook,validatePathTasks} from './ndx_dated_path_chart_component_20261003.mjs';
import {appendRiskComparisonWorkbook,prepareRiskTables} from './ndx_dated_risk_chart_component_20261003.mjs';
import {buildExtensionNavigationWorkbook} from './ndx_dated_extension_navigation_component_20261003.mjs';

export const SOURCE_PINS=Object.freeze({index:null,publication:null,independent_readback:null,tasks:null,shared:null,classification:null,
 path_component:'39fcd13d7588b4c1527bcd4dbf79bf5ec626da157d337f77323910231dc8023a',
 risk_component:'9a4112a2abaaaee7c5bb4bd6c0c632519f06cbe92a1c0314135d1efa194179d5',
 navigation_component:'65e0f0760d0730b65e177e8e884eeb82c21f1ebe3747a364879cc868cdbe75b6',
 native_hyperlinks:'267333bd62a3399c6ab3c97104bf884a737e116a51e8c62243aa3e0fcd6a475d'});
export const IMPLEMENTATION_STATUS='NO_IO_PACKAGE_BUILDER_AND_STREAM_CORE_ONLY_NOT_SOURCE_BOUND_PUBLISHER';
const sharedRoles=['incumbent_integer','incumbent_continuous','STRICT_SAME_SESSION_FX','BACKWARD_LATEST_VALID_FX'];
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const integer=x=>assert(Number.isSafeInteger(x)&&x>=0,'Exact bounded integer');
const hash=x=>assert.match(x,/^[a-f0-9]{64}$/);
const keys=(x,expected)=>assert.deepEqual(Object.keys(x).sort(),[...expected].sort());
const missing=t=>t.schema==='DATED_WORKBOOK_TASK_EXTENSION_MISSING_V1';
const missingFlags=['source_bytes_authenticated','formal_comparison_passed','point_in_time_verified','promotion_allowed','future_independent_oos','account_executed','fit_performed','economic_metrics_recomputed','risk_reaggregated','workbook_delivered','charts_rendered','visual_acceptance_passed','xlsx_actual_size_limit_verified','full_transitive_source_closure_reverified'];
// Typed runtime snapshots are mutation guards, never replacement source JSON.
export const JSON_RUNTIME_ENCODING='NATIVE_JSON_WITH_UNSAFE_INTEGER_TOKENS_AS_BIGINT_V1';
const snapshot=value=>{
 const encode=x=>typeof x==='bigint'?['bigint',x.toString()]:Array.isArray(x)?['array',x.map(encode)]:x!==null&&typeof x==='object'?['object',Object.entries(x).map(([k,v])=>[k,encode(v)])]:[typeof x,x];
 return sha(Buffer.from(JSON.stringify(encode(value))));
};
const flags={sourceBytesAuthenticated:false,workbookDelivered:false,visualAcceptancePassed:false,formalComparisonPassed:false,futureIndependentOos:false};

export function restoreTaskDisplay(compact,shared){
 assert.equal(shared.schema,'DATED_WORKBOOK_EXTENSION_SHARED_DATA_V1');
 assert.equal(Object.keys(shared.series).length,4);assert.equal(Object.keys(shared.risk).length,2);
 const result=structuredClone(compact);
 if(missing(result)){assert.equal(result.status,'COMPARISON_NOT_SUPPLIED');for(const key of missingFlags)assert.equal(result[key],false,'Missing evidence authority '+key);return result;}
 for(const role of sharedRoles){
  keys(result.series[role],['shared_series_id']);const id=result.series[role].shared_series_id;hash(id);
  const saved=shared.series[id];assert(saved,'Missing shared identity');
  assert.equal(saved.identity.role,role);assert.deepEqual(saved.identity.source_reference,result.source_index[role]);
  assert.deepEqual(saved.series.source_reference,saved.identity.source_reference);
  result.series[role]=structuredClone(saved.series);
  if(role.startsWith('incumbent')){
   keys(result.risk_tracks[role],['shared_risk_id']);assert.equal(result.risk_tracks[role].shared_risk_id,id);
   const risk=shared.risk[id];assert.deepEqual(risk.identity,saved.identity);assert.deepEqual(risk.risk.source_reference,saved.identity.source_reference);
   result.risk_tracks[role]=structuredClone(risk.risk);
  }
 }
 validatePathTasks([result],[result.numerical_task_id]);prepareRiskTables([result],[result.numerical_task_id]);
 return result;
}

/** Counts actual saved risk rows, including repeated shared rows in each workbook. */
export function inspectPackage(tasks,ids,limits={}){
 assert(tasks.length>0);assert.deepEqual(tasks.map(t=>t.numerical_task_id),ids);
 assert.equal(new Set(ids).size,ids.length);
 const statuses=tasks.map(missing);assert(statuses.every(x=>x===statuses[0]),'Split missing/present runs, never invent missing curves');
 if(statuses[0])return {missing:true,taskCount:tasks.length,dataRows:tasks.length+1,taskIds:[...ids]};
 const risk=prepareRiskTables(tasks,ids,limits);
 // Include detail/index/source headings, source index, task evidence and path rows.
 const dataRows=risk.totalDetailRows+risk.totalCoordinateRows+risk.sourceIndex.length+tasks.length*127+127+tasks.length+1+risk.pages.length+risk.indexPages.length;
 assert(dataRows<=(limits.maxTotalRows??250000),'BLOCKED_DELIVERY_LAYOUT_LIMIT total workbook data rows');
 return {missing:false,taskCount:tasks.length,dataRows,taskIds:[...ids],riskDetailRows:risk.totalDetailRows,riskCoordinateRows:risk.totalCoordinateRows};
}

export function buildDisplayPackage(Workbook,tasks,expectedTaskIds,limits={}){
 const costs=inspectPackage(tasks,expectedTaskIds,limits);
 if(costs.missing){
  const workbook=Workbook.create(),sheet=workbook.worksheets.add('任务索引');
  sheet.getRange('A1:C1').values=[['任务序号','任务ID（原样）','缺失状态']];
  sheet.getRangeByIndexes(1,0,tasks.length,3).values=tasks.map((t,i)=>[i+1,'ID: '+t.numerical_task_id,'COMPARISON_NOT_SUPPLIED']);
  const note=workbook.worksheets.add('缺失说明');note.getRange('A1').values=[['未提供比较数据；无虚构全现金路径、曲线或风险。原始记录须随完整JSONL交付。']];
  return {workbook,costs,charts:[],missingEvidence:true,...flags};
 }
 const paths=buildPathComparisonWorkbook(Workbook,tasks,expectedTaskIds);
 const risk=appendRiskComparisonWorkbook(paths.workbook,tasks,expectedTaskIds,limits);
 return {workbook:paths.workbook,costs,charts:[...paths.charts,...risk.charts],taskSelector:'路径查看!B4',dateSelector:'风险查看!B4',
  riskSourceIndex:risk.sourceIndex,engineEvidence:risk.engineEvidence,taskEvidence:risk.taskEvidence,...flags};
}

export function buildNavigation(Workbook,index,classification,packages,expectedTaskIds){
 // Returned OOXML link intents MUST subsequently pass the pinned native helper.
 return {...buildExtensionNavigationWorkbook(Workbook,index,classification,packages,expectedTaskIds),nativeHelperRequired:true,...flags};
}

function parseRow(bytes){
 const text=new TextDecoder('utf-8',{fatal:true}).decode(bytes);
 // Only original integer tokens may become BigInt; decimal/exponent numbers keep
 // native JSON semantics. Original UTF8 bytes, offsets and SHA remain untouched.
 return JSON.parse(text,(_key,value,context)=>{
  if(typeof value==='number'){
   assert(Number.isFinite(value),'Nonfinite JSON number');
   if(Number.isInteger(value)&&!Number.isSafeInteger(value)){
    assert(typeof context?.source==='string'&&/^-?(0|[1-9][0-9]*)$/.test(context.source),'Unsafe non-integer token or missing lossless reviver source');
    return BigInt(context.source);
   }
  }
  return value;
 });
}

/** Consume complete JSONL lines serially. No output is authorized before final EOF.
 * exportPackage returns {bytes:Uint8Array,chartSources:Array}; preserveAttempt must
 * durably keep every exported attempt, INCLUDING oversize ones. This core cannot
 * authenticate callback durability. The final publisher owns sources/create-only.
 */
export async function streamDisplayPackages({lines,index,shared,expectedTaskIds,exportPackage,preserveAttempt,onFailure,
 maxBufferedTasks=8,maxXlsxBytes=50*1024*1024,maxLineBytes=64*1024*1024,limits={}}){
 integer(maxBufferedTasks);assert(maxBufferedTasks>0&&maxBufferedTasks<=32);integer(maxXlsxBytes);assert(maxXlsxBytes>0&&maxXlsxBytes<=50*1024*1024);integer(maxLineBytes);assert(maxLineBytes>0&&maxLineBytes<=64*1024*1024);
 assert.equal(index.planned_task_count,expectedTaskIds.length);assert.deepEqual(index.task_index.map(t=>t.numerical_task_id),expectedTaskIds);assert.equal(new Set(expectedTaskIds).size,expectedTaskIds.length);
 assert(expectedTaskIds.length>0);expectedTaskIds.forEach(hash);
 assert.equal(typeof exportPackage,'function');assert.equal(typeof preserveAttempt,'function');assert.equal(typeof onFailure,'function');
 const descriptor=index.task_jsonl_reference;hash(descriptor.sha256);integer(descriptor.byte_count);integer(descriptor.record_count);assert.equal(descriptor.record_count,expectedTaskIds.length);
 const planned=index.package_plan.packages;assert(Array.isArray(planned)&&planned.length>0);
 const boundaries=new Set();let declared=0;
 for(const bundle of planned){assert(Array.isArray(bundle.tasks)&&bundle.tasks.length);for(const t of bundle.tasks){assert.equal(t.task_ordinal,declared);assert.equal(t.numerical_task_id,expectedTaskIds[declared++]);}boundaries.add(declared);}
 assert.equal(declared,expectedTaskIds.length);
 let offset=0,ordinal=0,attempt=0,buffer=[],unresolvedAttempt=null;const digest=createHash('sha256'),packages=[],attempts=[];
 async function emit(tasks){
  const ids=tasks.map(t=>t.numerical_task_id),start=tasks[0].task_ordinal;
  try{inspectPackage(tasks,ids,limits);}catch(error){
   if(!String(error.message).includes('BLOCKED_DELIVERY_LAYOUT_LIMIT')||tasks.length===1)throw error;
   const middle=Math.floor(tasks.length/2);await emit(tasks.slice(0,middle));await emit(tasks.slice(middle));return;
  }
  const number=attempt++,draft={attempt_index:number,start_task_ordinal:start,stop_task_ordinal:start+tasks.length,task_ids:ids};
  const callbackTasks=structuredClone(tasks),callbackIds=[...ids],callbackDraft=structuredClone(draft);
  const before=snapshot([callbackTasks,callbackIds,callbackDraft]);unresolvedAttempt={...structuredClone(draft),stage:'EXPORT_INVOKED'};
  let exported=await exportPackage(callbackTasks,callbackIds,callbackDraft);
  assert.equal(snapshot([callbackTasks,callbackIds,callbackDraft]),before,'Export callback mutated task evidence');
  assert(exported&&exported.bytes instanceof Uint8Array&&exported.bytes.byteLength>0);assert(Array.isArray(exported.chartSources));
  const chartSources=structuredClone(exported.chartSources);
  const over=exported.bytes.byteLength>maxXlsxBytes;
  const evidence={...draft,status:over?'OVERSIZE_ATTEMPT_NOT_ACCEPTED':'PENDING_COMPLETE_STREAM_AND_SOURCE_PUBLICATION',bytes:exported.bytes.byteLength,sha256:sha(exported.bytes)};
  const callbackEvidence=structuredClone(evidence),evidenceHash=snapshot(callbackEvidence);unresolvedAttempt={...structuredClone(draft),stage:'PRESERVE_INVOKED',exported_bytes:evidence.bytes,exported_sha256:evidence.sha256};
  const savedReference=await preserveAttempt(callbackEvidence,exported.bytes);
  assert.equal(snapshot(callbackEvidence),evidenceHash,'Preserve callback mutated byte evidence');
  assert.equal(exported.bytes.byteLength,evidence.bytes);assert.equal(sha(exported.bytes),evidence.sha256,'Preserve callback mutated exported bytes');
  const attemptRef=structuredClone(savedReference);assert(attemptRef&&typeof attemptRef.path==='string'&&attemptRef.path.length>0);assert.equal(attemptRef.sha256,evidence.sha256);attempts.push({...evidence,reference:attemptRef});unresolvedAttempt=null;
  exported=null; // Release potentially oversize bytes before recursive subdivision.
  if(over){assert(tasks.length>1,'BLOCKED_SINGLE_TASK_XLSX_OVER_50_MIB');const middle=Math.floor(tasks.length/2);await emit(tasks.slice(0,middle));await emit(tasks.slice(middle));return;}
  const packageIndex=packages.length;
  packages.push({package_index:packageIndex,filename:`package-${String(packageIndex+1).padStart(4,'0')}.xlsx`,start_task_ordinal:start,stop_task_ordinal:start+tasks.length,attempt_reference:attemptRef,byte_count:evidence.bytes,sha256:evidence.sha256,chart_sources:chartSources,
   tasks:tasks.map((t,i)=>({numerical_task_id:t.numerical_task_id,task_ordinal:t.task_ordinal,local_task_number:i+1,navigation_row:i+2,
    comparison_status:index.task_index[t.task_ordinal].status,integer_status:missing(t)?'COMPARISON_NOT_SUPPLIED':t.series.candidate_integer.status,continuous_status:missing(t)?'COMPARISON_NOT_SUPPLIED':t.series.candidate_continuous.status}))});
 }
 try{
  for await(const raw of lines){
   assert(raw instanceof Uint8Array&&raw.byteLength>0&&raw.byteLength<=maxLineBytes);const bytes=Buffer.from(raw);assert.equal(bytes.at(-1),10,'Complete JSONL line');assert(ordinal<expectedTaskIds.length,'Extra source row');
   const entry=index.task_index[ordinal],location=entry.jsonl_record;assert.equal(entry.task_ordinal,ordinal,'Original index ordinal');assert.deepEqual(location,{record_index:ordinal,byte_start:offset,byte_stop:offset+bytes.length,row_sha256:sha(bytes)});
   const compact=parseRow(bytes);assert.equal(compact.numerical_task_id,expectedTaskIds[ordinal]);assert.equal(compact.task_ordinal,ordinal);
   const task=restoreTaskDisplay(compact,shared);assert.equal(missing(task)?task.status:'DISPLAY_PROJECTED',entry.status);
   if(buffer.length&&(missing(buffer[0])!==missing(task))){await emit(buffer);buffer=[];}
   buffer.push(task);digest.update(bytes);offset+=bytes.length;ordinal++;
   if(buffer.length===maxBufferedTasks||boundaries.has(ordinal)){await emit(buffer);buffer=[];}
  }
  assert.equal(ordinal,expectedTaskIds.length,'Missing source tail');assert.equal(offset,descriptor.byte_count);assert.equal(digest.digest('hex'),descriptor.sha256,'Whole JSONL EOF hash');
  if(buffer.length)await emit(buffer);
  assert.deepEqual(packages.flatMap(p=>p.tasks.map(t=>t.numerical_task_id)),expectedTaskIds);
  return {schema:'DATED_H_STREAM_PACKAGE_CORE_RESULT_V1',implementationStatus:IMPLEMENTATION_STATUS,status:'COMPLETE_STREAM_ENGINEERING_ONLY_REQUIRES_SOURCE_BOUND_PUBLICATION',packages,attempts,taskCount:ordinal,unprocessedTaskCount:0,
   jsonRuntimeEncoding:JSON_RUNTIME_ENCODING,originalJsonlBytesReencoded:false,exportAttemptCount:attempt,unresolvedAttempt:null,measuredPackageBytesWithinLimit:true,measuredLimitBytes:maxXlsxBytes,streamSha256:descriptor.sha256,preservedOversizeAttemptCount:attempts.filter(a=>a.status==='OVERSIZE_ATTEMPT_NOT_ACCEPTED').length,
   callbackDurabilityAuthenticated:false,nativeNavigationLinksApplied:false,sourceDataCopiedToDelivery:false,...flags};
 }catch(error){await onFailure({status:'FAILED_DO_NOT_CONSUME',error:String(error.message),consumedTaskCount:ordinal,expectedTaskCount:expectedTaskIds.length,attempts,exportAttemptCount:attempt,unresolvedAttempt:structuredClone(unresolvedAttempt),acceptedPendingPackages:packages,retryAllowed:false});throw error;}
}

export function run(){throw new Error('NOT_IMPLEMENTED_SOURCE_BOUND_PUBLISHER: future external pins null; no actual export authorized');}
