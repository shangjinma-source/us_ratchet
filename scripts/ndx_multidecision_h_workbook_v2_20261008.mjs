/** Audited literal evidence plus explicitly approximate main views and charts. */
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import {pathToFileURL,fileURLToPath} from 'node:url';
export const subtitle='展示近似仅见主视图与曲线；全部精确原值另表保留。尚未晋级，不是新的OOS或PIT证明。';
export function sheets(payload){
  assert.equal(payload.schema,'MULTIDECISION_H_WORKBOOK_DISPLAY_V2');assert.equal(payload.full_h_delivery_complete,false);
  assert.equal(payload.tables.length,25);assert.equal(payload.charts.length,16);
  const result=[{name:'阅读说明',headers:['项目','说明'],rows:[['交付内容','真实股票及比例、16轨净值曲线、完整原风险与三种来源链暴露。'],['未晋级原因','缺独立cohort P50/P10/P90、正式逐项非劣比较及新前瞻OOS/PIT证据。'],['近似边界','主视图百分比和有效N显示两位小数；曲线采用binary64近似。精确原分数/Decimal/数量全部另表保留。'],['空仓与阻断','108个空仓日保留undefined；8条来源阻断路径未执行，不绘制假零曲线。'],['数值来源','原存控制连续链、已审候选连续派生链、原整股权重逐链相加分别标明，未重新归一。'],['原证据说明','原表中的历史阶段缺口声明保持原文，不能据此抹掉后来补充的证据，也不能冒称原先已完成。FX指汇率模式，lane指目标类型，SID指证券标识；尾部对应坏尾部，目标包络对应目标距离。'],['长文本','超长原JSON在原长文本分块页无损保存；主表保留精确定位。'],['阅读顺序','组合主视图 → 期末真实股票比例 → 曲线01至16 → 原始证据表。']]}],chunks=[];
  function add(table){
    const order=table.headers.map((_,i)=>i).sort((a,b)=>Number(/JSON|来源/.test(table.headers[a]))-Number(/JSON|来源/.test(table.headers[b])));
    const rows=table.rows.map((row,r)=>{assert.equal(row.length,table.headers.length);return order.map(i=>{
      const v=row[i];assert(v===null||typeof v==='string'||typeof v==='boolean'||Number.isSafeInteger(v),'Exact evidence cell type');
      assert(typeof v!=='string'||!/[\x00-\x08\x0b\x0c\x0e-\x1f]/.test(v),'XML control characters rejected');
      if(typeof v==='string'&&v.length>32767){const chars=Array.from(v),count=Math.ceil(chars.length/14000);for(let j=0;j<count;j++)chunks.push([table.name,r+1,i+1,j+1,count,chars.slice(j*14000,(j+1)*14000).join('')]);return `原长文本分块｜${table.name}｜数据行${r+1}｜原列${i+1}｜分块${count}`;}return v;
    });});
    result.push({name:table.name,headers:order.map(i=>table.headers[i]),rows});
  }
  payload.tables.slice(0,2).forEach(add);
  for(const chart of payload.charts){assert.equal(chart.rows.length,120);assert(chart.rows.every(r=>typeof r[0]==='string'&&r.slice(1).every(v=>typeof v==='number'&&Number.isFinite(v))));result.push({...chart,chart:true});}
  payload.tables.slice(2).forEach(add);
  result.push({name:'原长文本分块',headers:['原表','数据行','原列','分块序号','总分块','原文本分块JSON'],rows:chunks});
  assert.equal(new Set(result.map(x=>x.name)).size,result.length);return result;
}
function column(n){let text='';while(n){n--;text=String.fromCharCode(65+n%26)+text;n=Math.floor(n/26);}return text;}
export function build(Workbook,payload){
  const wb=Workbook.create();
  for(const [index,t]of sheets(payload).entries()){
    const sheet=wb.worksheets.add(t.name),n=t.headers.length,matrix=[t.headers,...t.rows];sheet.showGridLines=false;
    const area=sheet.getRangeByIndexes(0,0,t.rows.length+4,Math.max(n,t.chart?17:n));area.format.font={name:'Microsoft YaHei',size:11,color:'#183244'};area.format.rowHeight=t.name==='组合主视图'?132:44;area.format.verticalAlignment='center';area.format.wrapText=true;area.setNumberFormat('@');
    const width=t.chart?17:Math.min(n,6);
    sheet.getRangeByIndexes(0,0,1,width).merge();sheet.getRange('A1').values=[[t.name]];sheet.getRangeByIndexes(0,0,1,width).format.fill='#143B53';sheet.getRangeByIndexes(0,0,1,width).format.font={bold:true,color:'#FFFFFF',size:19};sheet.getRange('A1').format.rowHeight=38;
    sheet.getRangeByIndexes(1,0,1,width).merge();sheet.getRange('A2').values=[[t.chart?t.note:subtitle]];sheet.getRange('A2').format.rowHeight=38;sheet.getRange('A3').format.rowHeight=12;
    sheet.getRangeByIndexes(3,0,matrix.length,n).values=matrix.map(row=>row.map(v=>typeof v==='string'&&v.startsWith('=')?"'"+v:v));
    const head=sheet.getRangeByIndexes(3,0,1,n);head.format.fill='#DCEAF0';head.format.font={bold:true,color:'#143B53'};head.format.rowHeight=48;
    for(let c=0;c<n;c++){
      const label=t.headers[c],range=sheet.getRangeByIndexes(0,c,t.rows.length+4,1);range.format.columnWidth=/口径/.test(label)?60:/JSON|来源/.test(label)?32:/说明|未晋级/.test(label)?70:/期末真实|逐链权重/.test(label)?55:/精确|Decimal|原文|文本|SHA/.test(label)?44:22;
      if(/JSON|来源/.test(label))range.format.wrapText=false;
    }
    if(t.chart){
      sheet.getRangeByIndexes(4,1,120,n-1).setNumberFormat('0.000000');sheet.getRange('F:Q').format.columnWidth=10;
      const chart=sheet.charts.add('line',sheet.getRange(`A4:${column(n)}124`));chart.setPosition('F4','Q16');chart.title=t.title;
      chart.titleTextStyle.fontSize=14;chart.titleTextStyle.typeface='Microsoft YaHei';chart.legend={position:'bottom',textStyle:{typeface:'Microsoft YaHei',fontSize:11}};
      chart.xAxis={axisType:'textAxis',tickLabelInterval:24,textStyle:{typeface:'Microsoft YaHei',fontSize:10}};
      chart.yAxis={numberFormatCode:'0.00',numberFormatSourceLinked:false,textStyle:{typeface:'Microsoft YaHei',fontSize:10}};
      chart.yAxis.title.text='归一净值（展示近似）';
      for(const [j,s]of chart.series.items.entries())s.fill=t.headers[j+1].startsWith('候选')?'#16799A':t.headers[j+1].startsWith('原八只')?'#CF7B28':'#7161A8';
    }else{
      for(let r=0;r<matrix.length;r++)for(let c=0;c<n;c++){const v=matrix[r][c];if(typeof v==='string'&&/^(?:[0-9a-fA-F]{64}|[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)$/.test(v)){assert(v.length<=250);sheet.getRangeByIndexes(r+3,c,1,1).setNumberFormat('"'+v+'"');}}
      if(t.rows.length)sheet.tables.add(`A4:${column(n)}${t.rows.length+4}`,true,`SavedV2Table${index}`);
    }
    sheet.freezePanes.freezeRows(4);sheet.freezePanes.freezeColumns(['组合主视图','期末真实股票比例'].includes(t.name)?4:1);
  }return wb;
}
async function main(){
  const [input,directory,modules]=process.argv.slice(2);assert(input&&directory&&modules);
  const req=createRequire(path.join(modules,'package.json'));const{Workbook,SpreadsheetFile}=await import(pathToFileURL(req.resolve('@oai/artifact-tool')).href);
  const payload=JSON.parse(await fs.readFile(input,'utf8')),wb=build(Workbook,payload);wb.recalculate();
  const file=await SpreadsheetFile.exportXlsx(wb);await file.save(path.join(directory,'workbook.xlsx'));
  for(const [i,t]of sheets(payload).entries()){
    const range=t.chart?'A1:Q17':`A1:${column(Math.min(t.headers.length,t.name==='组合主视图'?15:t.name==='期末真实股票比例'?13:6))}${Math.min(t.rows.length+4,t.name==='组合主视图'?7:12)}`;
    const png=await wb.render({sheetName:t.name,range,scale:1,format:'png'});await fs.writeFile(path.join(directory,`preview-${String(i).padStart(2,'0')}.png`),new Uint8Array(await png.arrayBuffer()));
  }
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url))await main();
