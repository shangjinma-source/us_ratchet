import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {validateRiskTasks,prepareRiskTables,appendRiskComparisonWorkbook} from '../scripts/ndx_dated_risk_chart_component_20261003.mjs';
const original=JSON.parse(fs.readFileSync(new URL('../tmp/dated_workbook_qa_20261003/path-chart-fixture.json',import.meta.url),'utf8'));
const fixture=()=>structuredClone(original);const ids=t=>t.map(x=>x.numerical_task_id);
const roles=['candidate_target','incumbent_target','candidate_integer','incumbent_integer','candidate_continuous','incumbent_continuous'];
const missing='未定义/超出展示精度';
const smallFloat=r=>r===null?missing:Number(r.numerator)/Number(r.denominator);

test('all task day blocks resolve across pages to every original group and member without truncation',()=>{
 const t=fixture(),before=structuredClone(t);const out=prepareRiskTables(t,ids(t),{maxRowsPerSheet:17});const coords=out.indexPages.flat();assert.equal(coords.length,t.length*127);assert.deepEqual(t,before);
 for(let ti=0;ti<t.length;ti++)for(let day=0;day<127;day++){
  const coord=coords[ti*127+day];assert.equal(coord[0],ti+1);assert.equal(coord[1],t[ti].calendar[day]);
  for(let ri=0;ri<6;ri++){
   const role=roles[ri],target=ri<2;const holder=target?t[ti].original_target_chain_evidence[ri===0?'candidate':'incumbent']:t[ti].risk_tracks[role];const saved=target?holder:holder.rows?.[day];const groups=saved?.aggregation.rows??[];
   const [page,start,count,status,denominator,cash]=coord.slice(2+6*ri,8+6*ri);assert.equal(count,Math.max(1,groups.length));assert.equal(status,target?'SAVED_ORIGINAL_TARGET':holder.status);assert.equal(denominator,JSON.stringify(saved?.aggregation.normalized_display_denominator??null));
   const block=out.pages[page-1].slice(start-2,start-2+count);assert.equal(block.length,count);
   for(let gi=0;gi<count;gi++){
    const row=block[gi],g=groups[gi];assert.equal(row[2],role);assert.equal(row[16],status);const source=out.sourceIndex[row[15]];assert.equal(source.role,role);assert.equal(source.task_pointer,target?`/original_target_chain_evidence/${ri===0?'candidate':'incumbent'}`:`/risk_tracks/${role}/rows/${day}`);
    if(g){assert.equal(row[4],g.risk_chain??'UNKNOWN（原null）');assert.equal(row[5],g.unknown);assert.deepEqual(JSON.parse(row[6]),g.saved_literal_sum);assert.deepEqual(JSON.parse(row[8]),g.normalized_display_share);assert.equal(row[14],g.members.map(m=>m.security_id).join(' | '));assert.equal(row[7],smallFloat(g.saved_literal_sum));}
    else assert.equal(row[7],missing);
   }
   if(!target&&role.endsWith('integer')&&holder.status==='AVAILABLE'){assert.equal(cash,smallFloat(saved.cash_fraction_display));assert.equal(block[0][12],JSON.stringify(saved.cash_usd_preserved));}
  }
 }
 assert.equal(out.totalDetailRows,out.pages.flat().length);assert.equal(out.sourceBytesAuthenticated,false);assert.equal(out.riskReaggregated,false);
});
test('shared evidence only once while candidate original zero and unknown stay distinct',()=>{
 const t=fixture(),out=prepareRiskTables(t,ids(t));const coordinates=out.indexPages.flat();
 for(let ti=1;ti<t.length;ti++)for(let day=0;day<127;day++)for(const ri of [3,5])assert.deepEqual(coordinates[ti*127+day].slice(2+ri*6,8+ri*6),coordinates[day].slice(2+ri*6,8+ri*6));
 assert.equal(out.sourceIndex.filter(r=>r.role==='incumbent_target').length,t.length);assert.equal(out.sourceIndex.filter(r=>r.role==='incumbent_integer').length,127);assert.equal(out.sourceIndex.filter(r=>r.role==='incumbent_continuous').length,127);
 assert(out.pages.flat().some(r=>r[5]===true));assert(out.pages.flat().some(r=>JSON.parse(r[6])?.numerator==='0'));assert(out.pages.flat().filter(r=>r[11]===false).every(r=>r[10]==='null'&&r[9]===missing));
 for(let i=0;i<t.length;i++){assert.deepEqual(out.engineEvidence[i].engine_normalization_evidence,t[i].engine_normalization_evidence);assert.deepEqual(out.engineEvidence[i].original_target_evidence,t[i].original_target_evidence);}
});
test('cross task shared changes duplicate members bool index and oversized domain fail closed',()=>{
 for(const mutate of [t=>t[0].risk_tracks.candidate_integer.rows[0].source_row_index=true,t=>t[1].risk_tracks.incumbent_continuous.rows[0].aggregation.saved_literal_total.numerator='987',t=>{let a=t[0].original_target_chain_evidence.candidate.aggregation;a.rows[0].members.push(structuredClone(a.rows[0].members[0]));},t=>t[0].original_target_chain_evidence.candidate.aggregation.stock_denominator_defined=0,t=>t[0].original_target_chain_evidence.candidate.aggregation.rows[0].unknown=1]){
  const t=fixture();mutate(t);assert.throws(()=>validateRiskTasks(t,ids(t)));
 }
 for(const limits of [{maxGroupsPerBlock:1},{maxRowsPerSheet:1},{maxTotalRows:1},{maxRowsPerSheet:true}]){const t=fixture();assert.throws(()=>prepareRiskTables(t,ids(t),limits));}
});
test('subnormal underflow exact group value remains preserved with nonzero not rendered as zero',()=>{
 const t=fixture(),g=t[0].original_target_chain_evidence.candidate.aggregation.rows[0];g.saved_literal_sum={numerator:'1',denominator:'1'+'0'.repeat(400)};
 const out=prepareRiskTables(t,ids(t));const row=out.pages.flat().find(r=>r[2]==='candidate_target');assert.deepEqual(JSON.parse(row[6]),g.saved_literal_sum);assert.equal(row[7],missing);
});

function workbookMock(){
 const sheets=new Map();
 function sheet(name){const ranges=new Map();const x={ranges,getRange(address){if(!ranges.has(address))ranges.set(address,{format:{},values:address==='B4'&&name==='路径查看'?[[1]]:undefined,merge(){}});return ranges.get(address);},getRangeByIndexes(){return{format:{}};},freezePanes:{freezeRows(){}},dataValidations:{add(){}},charts:{add(){return{titleTextStyle:{},series:{items:[]},setPosition(){}};}}};sheets.set(name,x);return x;}
 sheet('路径查看');return{worksheets:{add:sheet,getItem:name=>sheets.get(name)},sheets,recalculate(){}};
}
test('full sidecars retained and bounded selector formulas reject unintended cross task display',()=>{
 const t=fixture(),out=prepareRiskTables(t,ids(t));assert.equal(out.taskEvidence.length,t.length);
 for(let i=0;i<t.length;i++)for(const key of ['numerical_task_id','source_index','input_references','original_provenance_and_missing','preserved_evidence_sidecars'])assert.deepEqual(out.taskEvidence[i][key],t[i][key]);
 assert(out.sourceIndex.every(x=>x.task_pointer_scope==='RESOLVED_DISPLAY_TASK_NOT_RAW_JSONL_POINTER'));
 const w=workbookMock();const made=appendRiskComparisonWorkbook(w,t,ids(t));const formula=w.sheets.get('风险查看').getRange('B5').formulas[0][0];
 for(const text of ['ISNUMBER($B$3)','ISNUMBER($B$4)','$B$3=INT($B$3)','$B$4=INT($B$4)','$B$3>=1','$B$3<=3','$B$4>=1','$B$4<=127','NA()'])assert(formula.includes(text));
 assert.equal(made.charts.length,6);assert.equal(made.exportedWorkbookVerified,false);
 for(const limits of [{maxRowsPerSheet:2},{maxRowsPerSheet:17}])assert.throws(()=>appendRiskComparisonWorkbook(workbookMock(),t,ids(t),limits),/BLOCKED_DELIVERY_LAYOUT_LIMIT/);
});

test('equal incumbent targets retain distinct per-task source evidence while daily tracks remain shared',()=>{
 const tasks=fixture();for(let i=0;i<tasks.length;i++){
  const ref={path:`inputs/task-${i}/inputs.json`,sha256:String(i+1).repeat(64)};
  tasks[i].original_target_evidence.incumbent.source_reference=structuredClone(ref);
  tasks[i].original_target_chain_evidence.incumbent.source_evidence.source_reference=structuredClone(ref);
 }
 const before=structuredClone(tasks),out=prepareRiskTables(tasks,ids(tasks));
 const sources=out.sourceIndex.filter(x=>x.role==='incumbent_target');assert.equal(sources.length,tasks.length);
 for(let i=0;i<tasks.length;i++){assert.equal(sources[i].numerical_task_id,tasks[i].numerical_task_id);assert.deepEqual(sources[i].source_reference,tasks[i].original_target_evidence.incumbent.source_reference);assert.deepEqual(out.engineEvidence[i].original_target_evidence,tasks[i].original_target_evidence);}
 assert.equal(out.sourceIndex.filter(x=>x.role==='incumbent_integer').length,127);assert.equal(out.sourceIndex.filter(x=>x.role==='incumbent_continuous').length,127);assert.deepEqual(tasks,before);
 tasks[1].risk_tracks.incumbent_integer.source_reference.path='different-daily-source';assert.throws(()=>prepareRiskTables(tasks,ids(tasks)));
});
