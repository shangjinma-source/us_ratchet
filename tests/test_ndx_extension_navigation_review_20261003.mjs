import test from 'node:test';
import assert from 'node:assert/strict';
import {validateNavigation,buildExtensionNavigationWorkbook} from '../scripts/ndx_dated_extension_navigation_component_20261003.mjs';
const pureFlags=['source_bytes_authenticated','formal_comparison_passed','point_in_time_verified','promotion_allowed','future_independent_oos','economics_recomputed','risk_recomputed','risk_chains_reaggregated','account_executed','winner_selected'];
const indexFlags=['source_bytes_authenticated','formal_comparison_passed','point_in_time_verified','promotion_allowed','future_independent_oos','account_executed','fit_performed','economic_metrics_recomputed','risk_reaggregated','workbook_delivered','charts_rendered','visual_acceptance_passed','xlsx_actual_size_limit_verified','full_transitive_source_closure_reverified'];
const flags=keys=>Object.fromEntries(keys.map(k=>[k,false]));
const ref={path:'evidence.json',sha256:'a'.repeat(64),json_pointer:'/rows/0'};
export function fixture() {
 const task_index=[];
 for(let k=4;k<=20;k++)for(const kind of ['equal','fixed','anchor'])for(let i=0;i<32;i++) {
  const ordinal=task_index.length;task_index.push({numerical_task_id:(ordinal+1).toString(16).padStart(64,'0'),task_ordinal:ordinal,k,weight_spec:{kind,literal:'100000000000000000000000000000000000001'},status:ordinal%2?'COMPARISON_NOT_SUPPLIED':'DISPLAY_PROJECTED',jsonl_record:{record_index:ordinal,byte_start:ordinal*10,byte_stop:ordinal*10+10,row_sha256:'b'.repeat(64)}});
 }
 const index={schema:'SOURCE_BOUND_DATED_WORKBOOK_EXTENSION_DATA_V1',planned_task_count:1632,task_index,classification_reference:{...ref},task_jsonl_reference:{...ref},...flags(indexFlags)};
 const rows=Array.from({length:101},(_,i)=>({ticker:`T${i}`,security_id:i<78?`security:${i}`:null,issuer_id:i<78?`issuer:${i===76?75:i}`:null,saved_risk_chain:i<78?'industrial':null,training_selected:i<77,conditional_label_present:i<78,formally_verified:false,classification_status:i<77?'SELECTED':'NOT_SELECTED',nonselection_evidence:{why:'原理由',original_value:'=1+2',exact:'999999999999999999999999999999999'},original_wiring_row:{original_windows:{first:'2026-03-20'},new_assumed_window:{last:'2026-09-21'}},wiring_row_reference:{...ref,json_pointer:`/rows/${i}`},training_provenance_reference:{...ref,json_pointer:`/rows/${i}`}}));
 const classification={schema:'DATED_WORKBOOK_CLASSIFICATION_TABLE_V1',rows,counts:{observed_security_rows:101,conditional_labeled_security_count:78,unknown_label_rows:23,training_selected_security_count:77,training_selected_issuer_count:76,formally_verified_rows:0},...flags(pureFlags)};
 const packages=[];
 // Valid derived split boundaries may differ from the saved package plan.
 for(let start=0;start<1632;start+=100) {
  const package_index=packages.length;const part=task_index.slice(start,start+100);
  packages.push({package_index,filename:`package-${String(package_index).padStart(4,'0')}.xlsx`,start_task_ordinal:start,stop_task_ordinal:start+part.length,tasks:part.map((r,i)=>({task_ordinal:r.task_ordinal,numerical_task_id:r.numerical_task_id,local_task_number:i+1,navigation_row:i+2,comparison_status:r.status,integer_status:'NOT_EXECUTED_NONPOSITIVE_TARGET',continuous_status:'AVAILABLE'}))});
 }
 return {index,classification,packages,ids:task_index.map(r=>r.numerical_task_id)};
}
function validate(f){return validateNavigation(f.index,f.classification,f.packages,f.ids);}
function fakeWorkbook() {
 const sheets=[];
 const Workbook={create(){return {worksheets:{add(name){const ranges=[];const tables=[];const sheet={name,ranges,tableCalls:tables,showGridLines:true,freezePanes:{freezeRows(n){sheet.frozen=n;}},getRange(address){const r={address,format:{},setNumberFormat(v){r.numberFormat=v;}};ranges.push(r);return r;},getRangeByIndexes(row,col,count,width){const r={coordinates:[row,col,count,width],format:{}};ranges.push(r);return r;}};sheet.tables={add(address,headers,name){tables.push({address,headers,name});}};sheets.push(sheet);return sheet;}},recalculate(){}};}};
 return {Workbook,sheets};
}
test('real index and classification distinct permission schemas pass full original order',()=>{
 const f=fixture();const got=validate(f);assert.equal(got.size,1632);
 for(const [target,key] of [['index','fit_performed'],['classification','economics_recomputed']]){const q=fixture();q[target][key]=true;assert.throws(()=>validate(q));}
});
test('omission duplicate swapped task or wrong navigation location rejected',()=>{
 for(const mutate of [f=>f.packages.pop(),f=>f.packages[0].tasks[1].numerical_task_id=f.packages[0].tasks[0].numerical_task_id,f=>{const t=f.packages[0].tasks;[t[0],t[1]]=[t[1],t[0]];},f=>f.packages[0].tasks[0].navigation_row=3,f=>f.ids.reverse(),f=>f.packages[1].filename=f.packages[0].filename,f=>f.packages[0].filename='evil".xlsx']){
  const f=fixture();mutate(f);assert.throws(()=>validate(f));
 }
});
test('101 original classification denominators and exact false booleans',()=>{
 for(const mutate of [f=>f.classification.rows.pop(),f=>f.classification.rows[0].formally_verified=0,f=>f.classification.rows[0].training_selected=1,f=>f.classification.rows[0].saved_risk_chain=null,f=>f.classification.rows[76].issuer_id='other',f=>f.classification.counts.unknown_label_rows=22,f=>f.classification.rows[0].wiring_row_reference.json_pointer='rows/0']){
  const f=fixture();mutate(f);assert.throws(()=>validate(f));
 }
});
test('literal formulas huge string values original reasons pointers and full table ranges',()=>{
 const f=fixture();f.classification.rows[0].ticker='=HYPERLINK("evil","x")';f.index.task_jsonl_reference.path='=1+1';const before=JSON.stringify(f);const mock=fakeWorkbook();const result=buildExtensionNavigationWorkbook(mock.Workbook,f.index,f.classification,f.packages,f.ids);
 assert.equal(JSON.stringify(f),before);assert.equal(result.sourceBytesAuthenticated,false);assert.equal(result.exportedWorkbookVerified,false);assert.equal(result.defaultTaskId,f.ids[0]);
 const nav=mock.sheets.find(s=>s.name==='全部任务');const values=nav.ranges.find(r=>r.coordinates?.[0]===1&&r.coordinates[3]===12).values;
 assert.equal(values.length,1632);assert.equal(values[0][11],f.ids[0]);assert.equal(JSON.parse(values[0][3]).literal,f.index.task_index[0].weight_spec.literal);
 const cl=mock.sheets.find(s=>s.name==='分类覆盖');const cv=cl.ranges.find(r=>r.coordinates?.[0]===1&&r.coordinates[3]===14).values;
 assert.equal(cv.length,101);assert.equal(cv[0][1],`'${f.classification.rows[0].ticker}`);assert.deepEqual(JSON.parse(cv[0][7]),f.classification.rows[0].nonselection_evidence);assert.equal(JSON.parse(cv[0][12]).json_pointer,'/rows/0');
 assert.equal(nav.tableCalls[0].address,'A1:L1633');assert.equal(cl.tableCalls[0].address,'A1:N102');assert.equal(mock.sheets.find(s=>s.name==='数据来源').tableCalls[0].address,'A1:D3');
 const src=mock.sheets.find(s=>s.name==='数据来源').ranges.find(r=>r.coordinates?.[0]===1&&r.coordinates[3]===4).values;assert.equal(src[0][1],"'=1+1");
 assert.equal(result.nativeHyperlinks.length,1632);assert.equal(result.hyperlinksApplied,false);assert.deepEqual(result.nativeHyperlinks[0],{worksheet:'全部任务',cell:'H2',target:'package-0000.xlsx',location:"'任务索引'!A2"});assert.deepEqual(result.nativeHyperlinks[1631],{worksheet:'全部任务',cell:'H1633',target:'package-0016.xlsx',location:"'任务索引'!A33"});
});

test('nonstring risk labels and escaped overlength cells reject rather than silently coerce',()=>{
 const f=fixture();f.classification.rows[0].saved_risk_chain=123;assert.throws(()=>validate(f));
 const q=fixture();q.index.task_jsonl_reference.path='='+ 'x'.repeat(32766);const mock=fakeWorkbook();assert.throws(()=>buildExtensionNavigationWorkbook(mock.Workbook,q.index,q.classification,q.packages,q.ids));
});
