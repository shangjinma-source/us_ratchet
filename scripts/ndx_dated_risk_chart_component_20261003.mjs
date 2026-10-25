/** Saved risk charts only. No IO, financial aggregation, or workbook export. */
import assert from 'node:assert/strict';
import {validatePathTasks} from './ndx_dated_path_chart_component_20261003.mjs';
const tracks=['candidate_integer','incumbent_integer','candidate_continuous','incumbent_continuous'];
const blockRoles=['candidate_target','incumbent_target',...tracks];
const labels=['候选原目标（非引擎或持仓）','原8原目标（非引擎或持仓）','候选整数：股票权重 / 现金另列','原8整数：股票权重 / 现金另列','候选连续：成本后贡献','原8连续：成本后贡献'];
const exact=(a,b)=>assert.deepEqual(a,b);
const integer=n=>{assert(Number.isSafeInteger(n)&&n>=0);return n;};
const literal=v=>typeof v==='string'&&v.startsWith('=')?`'${v}`:v;
const json=v=>JSON.stringify(v);
const missing='未定义/超出展示精度';
function ratio(v){
 assert(v&&typeof v==='object'&&!Array.isArray(v));exact(Object.keys(v).sort(),['denominator','numerator']);
 assert.equal(typeof v.numerator,'string');assert.equal(typeof v.denominator,'string');assert.match(v.numerator,/^\d+$/);assert.match(v.denominator,/^\d+$/);
 assert(v.numerator.length<=10000&&v.denominator.length<=10000);const n=BigInt(v.numerator),d=BigInt(v.denominator);assert(d>0n);return[n,d];
}
function display(v){
 if(v===null)return null;let[n,d]=ratio(v);if(n===0n)return 0;
 let e=n.toString(2).length-d.toString(2).length;if(e>=0?n<(d<<BigInt(e)):(n<<BigInt(-e))<d)e--;
 if(e>1023||e< -1075)return null;const scale=e< -1022?1074:52-e;
 const a=scale>=0?n<<BigInt(scale):n,b=scale>=0?d:d<<BigInt(-scale);let q=a/b,r=a%b;
 if(2n*r>b||(2n*r===b&&q%2n===1n))q++;const value=Number(q)*2**(-scale);return Number.isFinite(value)&&value!==0?value:null;
}
function aggregation(a){
 assert(a&&Array.isArray(a.rows));integer(a.security_count);assert.equal(typeof a.stock_denominator_defined,'boolean');ratio(a.saved_literal_total);ratio(a.unknown_saved_literal_total);
 if(a.stock_denominator_defined){assert(a.normalized_display_denominator!==null);assert(ratio(a.normalized_display_denominator)[0]>0n);}
 else assert.equal(a.normalized_display_denominator,null);
 const ids=new Set(),groups=new Set();
 for(const g of a.rows){
  assert(g.risk_chain===null||typeof g.risk_chain==='string'&&g.risk_chain.length>0);assert.equal(g.unknown,g.risk_chain===null||g.risk_chain==='unclassified');
  const key=json([g.unknown,g.risk_chain]);assert(!groups.has(key));groups.add(key);ratio(g.saved_literal_sum);
  if(a.stock_denominator_defined)ratio(g.normalized_display_share);else assert.equal(g.normalized_display_share,null);
  assert(Array.isArray(g.members)&&g.members.length>0);
  for(const member of g.members){assert.equal(typeof member.security_id,'string');assert(member.security_id.length>0&&!ids.has(member.security_id));ids.add(member.security_id);exact(member.risk_chain,g.risk_chain);}
 }
 assert.equal(ids.size,a.security_count);
}
export function validateRiskTasks(tasks,expectedTaskIds){
 const calendar=validatePathTasks(tasks,expectedTaskIds);
 for(const task of tasks){
  exact(Object.keys(task.risk_tracks).sort(),[...tracks].sort());exact(Object.keys(task.original_target_chain_evidence).sort(),['candidate','incumbent']);
  assert(task.engine_normalization_evidence&&typeof task.engine_normalization_evidence==='object');
  for(const role of ['candidate','incumbent']){
   const target=task.original_target_chain_evidence[role];assert.equal(target.role,'ORIGINAL_UNNORMALIZED_TARGET_NOT_ENGINE_EFFECTIVE_OR_ACTUAL_HOLDING');
   exact(target.source_evidence,task.original_target_evidence[role]);aggregation(target.aggregation);
  }
  for(const name of tracks){
   const track=task.risk_tracks[name];assert.equal(track.status,task.series[name].status);
   if(track.status!=='AVAILABLE'){assert.equal(name,'candidate_integer');assert.equal(track.rows,null);exact(track.calendar_slots,calendar.map(session=>({session,value:null})));continue;}
   exact(track.source_reference,task.series[name].source_reference);assert.equal(track.rows.length,127);exact(track.rows.map(r=>r.session),calendar);
   for(const row of track.rows){
    integer(row.source_row_index);assert.equal(calendar[row.source_row_index],row.session);aggregation(row.aggregation);
    assert.equal(row.denominator_scope,name.endsWith('integer')?'SAVED_STOCK_ONLY_WEIGHTS_CASH_SEPARATE_NOT_ACCOUNT_WEIGHT':'SAVED_AFTER_COST_CONTRIBUTION_SUM_NOT_TARGET_WEIGHT_OR_CASH_ACCOUNT');
    if(name.endsWith('integer')){ratio(row.cash_fraction_display);assert(Object.hasOwn(row,'saved_risk'));assert(Object.hasOwn(row,'cash_usd_preserved'));}
   }
   if(name.startsWith('incumbent'))exact(track,tasks[0].risk_tracks[name]);
  }
  // Target evidence belongs to each task input; equal weights do not make its source shared.
 }
 return calendar;
}

export function prepareRiskTables(tasks,expectedTaskIds,{maxRowsPerSheet=100000,maxGroupsPerBlock=128,maxTotalRows=250000}={}){
 const calendar=validateRiskTasks(tasks,expectedTaskIds);
 for(const n of [maxRowsPerSheet,maxGroupsPerBlock,maxTotalRows])assert(integer(n)>0);assert(maxRowsPerSheet<=100000);
 const pages=[[]],indexRows=[],shared=new Map(),sourceIndex=[];let total=0,maxGroups=1;
 function block(task,ordinal,role,dayIndex){
  const target=role.endsWith('_target'),who=role.split('_')[0],holder=target?task.original_target_chain_evidence[who]:task.risk_tracks[role];
  const status=target?'SAVED_ORIGINAL_TARGET':holder.status,day=target?null:holder.rows?.[dayIndex];
  const a=target?holder.aggregation:day?.aggregation;
  const key=!target&&role.startsWith('incumbent')?role+':'+dayIndex:null;
  if(key&&shared.has(key))return shared.get(key);
  const groups=a?.rows??[];assert(groups.length<=maxGroupsPerBlock,'BLOCKED_DELIVERY_LAYOUT_LIMIT no group truncation');maxGroups=Math.max(maxGroups,groups.length);
  const count=Math.max(1,groups.length);assert(count<=maxRowsPerSheet,'BLOCKED_DELIVERY_LAYOUT_LIMIT block larger than page');
  if(pages.at(-1).length+count>maxRowsPerSheet)pages.push([]);
  const page=pages.at(-1),start=page.length+2,sourceId=sourceIndex.length;
  sourceIndex.push({source_id:sourceId,numerical_task_id:task.numerical_task_id,role,session:target?null:calendar[dayIndex],task_pointer:target?`/original_target_chain_evidence/${who}`:`/risk_tracks/${role}/rows/${dayIndex}`,task_pointer_scope:'RESOLVED_DISPLAY_TASK_NOT_RAW_JSONL_POINTER',source_reference:target?holder.source_evidence.source_reference:holder.source_reference??null,saved_missing_evidence:holder.missing_evidence??null});
  for(let i=0;i<count;i++){
   const g=groups[i]??null;
   const row=[key?'共享':ordinal+1,`ID: ${task.numerical_task_id}`,role,target?'原目标固定':calendar[dayIndex],g?(g.risk_chain??'UNKNOWN（原null）'):(status==='AVAILABLE'?'无保存分组':status),g?g.unknown:null,
    g?json(g.saved_literal_sum):'null',g?(display(g.saved_literal_sum)??missing):missing,g?json(g.normalized_display_share):'null',g?(display(g.normalized_display_share)??missing):missing,
    json(a?.normalized_display_denominator??null),a?.stock_denominator_defined??false,day&&Object.hasOwn(day,'cash_usd_preserved')?json(day.cash_usd_preserved):'null',day?.cash_fraction_display?display(day.cash_fraction_display)??missing:missing,
    g?g.members.map(m=>m.security_id).join(' | '):'',sourceId,status];
   for(const v of row)assert(typeof v!=='string'||v.length<=32767,'BLOCKED_DELIVERY_LAYOUT_LIMIT exact cell too long');page.push(row);
  }
  total+=count;const result=[pages.length,start,count,status,json(a?.normalized_display_denominator??null),day?.cash_fraction_display?display(day.cash_fraction_display)??missing:missing];
  if(key)shared.set(key,result);return result;
 }
 for(let ti=0;ti<tasks.length;ti++){
  const task=tasks[ti],targets=[block(task,ti,'candidate_target',0),block(task,ti,'incumbent_target',0)];
  for(let day=0;day<127;day++)indexRows.push([ti+1,calendar[day],...targets.flat(),...tracks.flatMap(role=>block(task,ti,role,day))]);
 }
 assert(total+indexRows.length+sourceIndex.length<=maxTotalRows,'BLOCKED_DELIVERY_LAYOUT_LIMIT package detail plus coordinate rows');
 const indexPages=[];for(let i=0;i<indexRows.length;i+=maxRowsPerSheet)indexPages.push(indexRows.slice(i,i+maxRowsPerSheet));
 const taskEvidence=tasks.map(task=>Object.fromEntries(['numerical_task_id','source_index','input_references','original_provenance_and_missing','preserved_evidence_sidecars',...(Object.hasOwn(task,'source_jsonl_records')?['source_jsonl_records']:[])].map(key=>[key,structuredClone(task[key])])));
 return{pages,indexPages,maxGroups,calendar,maxRowsPerSheet,totalDetailRows:total,totalCoordinateRows:indexRows.length,taskIds:[...expectedTaskIds],sourceIndex,taskEvidence,engineEvidence:tasks.map(t=>({numerical_task_id:t.numerical_task_id,engine_normalization_evidence:structuredClone(t.engine_normalization_evidence),original_target_evidence:structuredClone(t.original_target_evidence)})),riskReaggregated:false,sourceBytesAuthenticated:false};
}
const column=n=>{let s='';for(n++;n;n=Math.floor((n-1)/26))s=String.fromCharCode(65+(n-1)%26)+s;return s;};
function writeTable(sheet,headers,rows){
 sheet.showGridLines=false;sheet.getRangeByIndexes(0,0,rows.length+1,headers.length).format.font={name:'Microsoft YaHei',size:10};
 sheet.getRangeByIndexes(0,0,rows.length+1,headers.length).format.rowHeight=26;
 const widths=headers.length===17?[12,82,28,16,30,12,42,22,42,22,42,18,32,26,90,14,48]:headers.length===6?[14,82,30,18,72,100]:[14,18,...Array.from({length:6},()=>[18,18,18,48,44,28]).flat()];
 widths.forEach((width,i)=>{sheet.getRangeByIndexes(0,i,rows.length+1,1).format.columnWidth=width;});
 sheet.getRangeByIndexes(0,0,1,headers.length).values=[headers];sheet.getRangeByIndexes(0,0,1,headers.length).format.fill='#123B56';sheet.getRangeByIndexes(0,0,1,headers.length).format.font={color:'#FFFFFF',bold:true};
 sheet.getRangeByIndexes(0,0,1,headers.length).format.wrapText=true;sheet.getRangeByIndexes(0,0,1,headers.length).format.rowHeight=44;
 if(rows.length)sheet.getRangeByIndexes(1,0,rows.length,headers.length).values=rows.map(r=>r.map(literal));sheet.freezePanes.freezeRows(1);
}
export function appendRiskComparisonWorkbook(workbook,tasks,expectedTaskIds,limits){
 const data=prepareRiskTables(tasks,expectedTaskIds,limits);
 assert(data.pages.length<=254&&data.indexPages.length<=254,'BLOCKED_DELIVERY_LAYOUT_LIMIT CHOOSE option count');
 // Conservative bound for the generated CHOOSE/INDEX formulas, including the
 // duplicated finite-value guard. Reject before modifying the workbook.
 assert(data.pages.length*240+512<=8192&&data.indexPages.length*200+512<=8192,'BLOCKED_DELIVERY_LAYOUT_LIMIT Excel formula length');
 const path=workbook.worksheets.getItem('路径查看');assert(path);assert.equal(path.getRange('B4').values[0][0],1,'Initial original task must remain first');
 const detailNames=data.pages.map((rows,i)=>{const name=`风险明细${String(i+1).padStart(3,'0')}`;writeTable(workbook.worksheets.add(name),['任务序号','原始任务ID显示','风险角色','日期','原链名','未知','原合计精确','原合计展示','归一占比精确','归一占比展示','分母精确','分母有定义','现金原金额','现金占账户','完整SID','源索引','状态'],rows);return name;});
 const indexNames=data.indexPages.map((rows,i)=>{const name=`风险定位${String(i+1).padStart(3,'0')}`;writeTable(workbook.worksheets.add(name),['任务序号','日期',...blockRoles.flatMap(r=>[r+'页',r+'首行',r+'行数',r+'状态',r+'分母',r+'现金'])],rows);return name;});
 const sourceRows=data.sourceIndex.map(s=>[s.source_id,`ID: ${s.numerical_task_id}`,s.role,s.session??'原目标',s.task_pointer,json(s.source_reference)]);
 // Pointer text only; large original evidence stays in the returned exact sidecar.
 for(let i=0;i<sourceRows.length;i+=data.maxRowsPerSheet)writeTable(workbook.worksheets.add(`风险来源${String(i/data.maxRowsPerSheet+1).padStart(3,'0')}`),['源索引','任务ID显示','角色','日期','解析后展示数据指针（非原JSONL）','原来源引用'],sourceRows.slice(i,i+data.maxRowsPerSheet));
 const chartHeight=Math.max(22,data.maxGroups*2),panelStride=chartHeight+8,helperStart=8+6*panelStride+10;
 const view=workbook.worksheets.add('风险查看');view.showGridLines=false;view.getRange(`A1:N${helperStart}`).format.font={name:'Microsoft YaHei',size:11};view.getRange(`A1:N${helperStart}`).format.columnWidth=14;
 view.getRange('A1').values=[['保存风险分组：条件标签，非重新计算风险']];view.getRange('A3').values=[['任务取路径查看']];view.getRange('B3').formulas=[["='路径查看'!B4"]];view.getRange('A4').values=[['日期序号']];view.getRange('B4').values=[[1]];
 view.dataValidations.add({range:'B4',rule:{type:'whole',operator:'between',formula1:1,formula2:127}});view.getRange('B4').format.fill='#FFF2CC';view.getRange('D4').values=[['只切换显示；现金单列；分母未定义不填0。']];
 const globalIndex='(($B$3-1)*127+$B$4)',pageIndex=`INT((${globalIndex}-1)/${data.maxRowsPerSheet})+1`,localIndex=`MOD(${globalIndex}-1,${data.maxRowsPerSheet})+1`;
 const validSelection=`AND($B$3=INT($B$3),$B$3>=1,$B$3<=${tasks.length},$B$4=INT($B$4),$B$4>=1,$B$4<=127)`;
 const coord=col=>`IF(AND(ISNUMBER($B$3),ISNUMBER($B$4)),IF(${validSelection},CHOOSE(${pageIndex},${indexNames.map((name,i)=>`INDEX('${name}'!$${column(col)}$2:$${column(col)}$${data.indexPages[i].length+1},MIN(${localIndex},${data.indexPages[i].length}))`).join(',')}),NA()),NA())`;
 view.getRange('A5').values=[['当前日期']];view.getRange('B5').formulas=[['='+coord(1)]];
 const charts=[];
 for(let role=0;role<6;role++){
  const panel=8+role*panelStride,helper=helperStart+role*(data.maxGroups+3),startCol=2+role*6;
  view.getRange(`A${panel}`).values=[[labels[role]]];
  view.getRange(`A${panel+1}`).values=[['保存状态']];view.getRange(`B${panel+1}:H${panel+1}`).merge();view.getRange(`B${panel+1}`).formulas=[['='+coord(startCol+3)]];
  view.getRange(`A${panel+2}`).values=[['原精确分母']];view.getRange(`B${panel+2}:H${panel+2}`).merge();view.getRange(`B${panel+2}`).formulas=[['='+coord(startCol+4)]];
  view.getRange(`A${panel+3}`).values=[['现金占账户']];view.getRange(`B${panel+3}:H${panel+3}`).merge();view.getRange(`B${panel+3}`).formulas=[['='+coord(startCol+5)]];
  view.getRange(`J${panel}:L${panel}`).values=[['页','首行','组槽位']];view.getRange(`J${panel+1}:L${panel+1}`).formulas=[[...([0,1,2].map(k=>'='+coord(startCol+k)))]];
  view.getRange(`A${helper}:C${helper}`).values=[['保存链名','原合计（未改）','保存归一展示占比']];
  const get=(col,i)=>`CHOOSE($J$${panel+1},${detailNames.map((name,p)=>`INDEX('${name}'!$${col}$2:$${col}$${data.pages[p].length+1},MIN($K$${panel+1}-1+${i},${data.pages[p].length}))`).join(',')})`;
  const formulas=[];
  for(let i=0;i<data.maxGroups;i++){
   const label=get('E',i),raw=get('H',i),share=get('J',i),inside=`${i}<$L$${panel+1}`;
   formulas.push([`=IF(${inside},${label},"")`,`=IF(${inside},IF(ISNUMBER(${raw}),${raw},NA()),NA())`,`=IF(${inside},IF(ISNUMBER(${share}),${share},NA()),NA())`]);
  }
  assert(formulas.flat().every(formula=>formula.length<=8192),'BLOCKED_DELIVERY_LAYOUT_LIMIT Excel formula length');
  view.getRange(`A${helper+1}:C${helper+data.maxGroups}`).formulas=formulas;
  const chart=view.charts.add('bar',view.getRange(`A${helper}:C${helper+data.maxGroups}`));chart.title=labels[role];chart.titleTextStyle.typeface='Microsoft YaHei';chart.titleTextStyle.fontSize=13;chart.legend={position:'top',textStyle:{typeface:'Microsoft YaHei',fontSize:10}};chart.yAxis={numberFormatCode:'0.00',numberFormatSourceLinked:false};chart.setPosition(`A${panel+5}`,`N${panel+5+chartHeight}`);
  charts.push({role:blockRoles[role],categoryRange:`风险查看!A${helper+1}:A${helper+data.maxGroups}`,series:chart.series.items.map(s=>({formula:s.formula,categoryFormula:s.categoryFormula}))});
 }
 workbook.recalculate();return{...data,charts,componentScope:'SAVED_RISK_CHART_COMPONENT_NOT_COMPLETE_H_DELIVERY',taskSelector:'路径查看!B4',dateSelector:'风险查看!B4',originalTargetsNormalized:false,exportedWorkbookVerified:false};
}
