/** Literal, non-economic workbook renderer. Source authentication is external. */
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';

export const tableNames = ['轨道与阻断','已存路径指标','到NAV的逐项距离','两种NAV参考','48个决策位置','已存归一轨迹','来源索引','范围与未晋级','候选原目标证券','已保存决策风险','决策逐SID原暴露','原身份与内部列分离','控制原目标','完整每日原记录','每日SID原持仓','每日原风险与缺口','未执行阻断轨道'];
export const subtitle = '仅投影已审原值；精确数值按文本保存。无拟合、无风险重算、无晋级结论。';
export function sheets(payload) {
  assert.equal(payload.schema, 'MULTIDECISION_H_WORKBOOK_INPUT_V1');
  assert.equal(payload.full_h_delivery_complete, false);
  assert.deepEqual(payload.tables.map(t=>t.name),tableNames);
  const output=[{name:'阅读说明',headers:['项目','说明'],rows:[['交付范围','11张已存比较表与6张原持仓补充表；不是完整H。'],['数值口径','原字符串逐字保留；不转浮点、不四舍五入、不作图表近似。'],['缺失口径','480日候选连续风险原本未保存；8条阻断轨道未执行。'],['阅读方法','先读身份、日期、状态及原值；右侧JSON和来源列仅用于核对。'],['原证据限制','原表中的历史阶段缺口说明保持原文；本工作簿不改变其历史含义。'],['派生风险','未提供：不填零、不借用其他账户风险。']]}];
  const chunks=[];
  for(const table of payload.tables){
    assert(table.headers.every(v=>typeof v==='string'));
    const order=table.headers.map((_,i)=>i).sort((a,b)=>Number(/JSON|来源/.test(table.headers[a]))-Number(/JSON|来源/.test(table.headers[b])));
    const rows=table.rows.map((row,r)=>{assert.equal(row.length,table.headers.length);return order.map(i=>{
      const v=row[i];assert(v===null||typeof v==='string'||typeof v==='boolean'||Number.isSafeInteger(v),'Only literal strings and exact small integers');
      assert(typeof v!=='string'||!/[\x00-\x08\x0b\x0c\x0e-\x1f]/.test(v),'XML text capacity');
      if(typeof v==='string'&&v.length>32767){
        const chars=Array.from(v),count=Math.ceil(chars.length/14000);
        for(let part=0;part<count;part++)chunks.push([table.name,r+1,i+1,part+1,count,chars.slice(part*14000,(part+1)*14000).join('')]);
        return `原长文本分块｜${table.name}｜数据行${r+1}｜原列${i+1}｜分块${count}`;
      }
      return v;
    });});
    output.push({name:table.name,headers:order.map(i=>table.headers[i]),rows});
  }
  output.push({name:'派生风险未提供',headers:['状态','范围','说明'],rows:[['未提供','候选连续账户480日','本版本未消费派生风险证据；不将缺失风险写成0。'],['未提供','新链聚合','需另行固定来源、口径及独立审计后接入。']]});
  output.push({name:'原长文本分块',headers:['原表','数据行','原列','分块序号','总分块','原文本分块JSON'],rows:chunks});
  return output;
}
export function build(Workbook,payload){
  const wb=Workbook.create();
  for(const [index,table] of sheets(payload).entries()){
    const sheet=wb.worksheets.add(table.name);sheet.showGridLines=false;
    const n=table.headers.length, matrix=[table.headers,...table.rows];
    const area=sheet.getRangeByIndexes(0,0,table.rows.length+4,n);
    area.format.font={name:'Microsoft YaHei',size:11,color:'#183244'};
    area.format.rowHeight=44;area.format.verticalAlignment='center';area.format.wrapText=true;
    area.setNumberFormat('@');
    sheet.getRangeByIndexes(0,0,1,n).merge();sheet.getRange('A1').values=[[table.name]];
    sheet.getRangeByIndexes(0,0,1,n).format.fill='#143B53';sheet.getRangeByIndexes(0,0,1,n).format.font={bold:true,color:'#FFFFFF',size:19};
    sheet.getRange('A1').format.rowHeight=38;
    sheet.getRangeByIndexes(1,0,1,n).merge();sheet.getRange('A2').values=[[subtitle]];sheet.getRange('A2').format.rowHeight=34;sheet.getRange('A2').format.wrapText=true;
    sheet.getRangeByIndexes(3,0,matrix.length,n).values=matrix.map(row=>row.map(v=>typeof v==='string'&&v.startsWith('=')?"'"+v:v));
    const head=sheet.getRangeByIndexes(3,0,1,n);head.format.fill='#DCEAF0';head.format.font={bold:true,color:'#143B53'};head.format.rowHeight=42;head.format.wrapText=true;
    for(let c=0;c<n;c++){
      const label=table.headers[c], cells=sheet.getRangeByIndexes(0,c,table.rows.length+4,1);cells.format.columnWidth=/JSON|来源|路径/.test(label)?32:/说明|原文/.test(label)?90:/精确|Decimal|距离|SHA|文本/.test(label)?48:/ticker|SID|issuer|内部/.test(label)?23:23;
      if(/JSON|来源|路径/.test(label))cells.format.wrapText=false;
    }
    // Numeric-looking strings remain original text; literal formats prevent the
    // renderer's long-digit preview coercion without changing stored cell values.
    for(let r=0;r<matrix.length;r++)for(let c=0;c<n;c++){
      const v=matrix[r][c];if(typeof v==='string'&&/^(?:[0-9a-fA-F]{64}|[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)$/.test(v)){
        assert(v.length<=250,'Numeric text exceeds literal display format limit');sheet.getRangeByIndexes(r+3,c,1,1).setNumberFormat('"'+v+'"');
      }
    }
    if(table.rows.length)sheet.tables.add(`A4:${column(n)}${table.rows.length+4}`,true,`SavedTable${index+1}`);
    sheet.freezePanes.freezeRows(4);sheet.freezePanes.freezeColumns(1);
  }
  return wb;
}
function column(n){let s='';while(n){n--;s=String.fromCharCode(65+n%26)+s;n=Math.floor(n/26);}return s;}
async function main(){
  const [input,directory,modules]=process.argv.slice(2);assert(input&&directory&&modules,'input directory bundled-node_modules required');
  const req=createRequire(path.join(modules,'package.json'));
  const {Workbook,SpreadsheetFile}=await import(pathToFileURL(req.resolve('@oai/artifact-tool')).href);
  const payload=JSON.parse(await fs.readFile(input,'utf8')), wb=build(Workbook,payload);wb.recalculate();
  const artifact=await SpreadsheetFile.exportXlsx(wb);await artifact.save(path.join(directory,'workbook.xlsx'));
  for(const [i,t] of sheets(payload).entries()){
    const png=await wb.render({sheetName:t.name,range:`A1:${column(Math.min(t.headers.length,6))}${Math.min(t.rows.length+4,12)}`,scale:1,format:'png'});
    await fs.writeFile(path.join(directory,`preview-${String(i).padStart(2,'0')}.png`),new Uint8Array(await png.arrayBuffer()));
  }
}
if(process.argv[1]&&path.resolve(process.argv[1])===path.resolve(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/,'$1')))await main();
