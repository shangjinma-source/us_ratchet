/** Layout-only adapter. The caller authenticates frozen builder bytes before use. */
import assert from 'node:assert/strict';
const units = value => [...String(value)].reduce((n,c)=>n+(c.codePointAt(0)>255?2:1),0);
export function layoutPlan(payload) {
  const weights=payload.display.tables[4],sources=payload.display.tables[5];
  assert.equal(weights.name,'原始目标权重');assert.equal(sources.name,'来源索引');
  assert.equal(sources.rows.length,5);
  const securityMax=Math.max(units(weights.headers[3]),...weights.rows.map(r=>units(r[3])));
  const securityWidth=Math.max(48,securityMax+6);assert(securityWidth<=120,'Security ID layout exceeds supported width');
  const sourceRows=sources.rows.map((row,i)=>{
    assert.equal(typeof row[1],'string');
    const height=Math.max(72,Math.ceil(units(row[1])/80)*20+16);
    assert(height<=400,'Source path requires a separately reviewed layout');
    return {row:i+5,height};
  });
  return {schema:'DATED_SIX_TABLE_READABLE_LAYOUT_V1',security_id:{sheet:weights.name,column:'D',column_index:3,width:securityWidth,maximum_display_units:securityMax,wrap:false},source_paths:{sheet:sources.name,column:'B',column_index:1,width:100,wrap:true,rows:sourceRows},values_changed:false,text_styles_changed:false};
}
export function buildReadableWorkbook(Workbook,payload,builder) {
  const original=structuredClone(payload),plan=layoutPlan(payload);
  const result=builder.buildWorkbook(Workbook,payload);
  assert.deepEqual(payload,original,'Frozen builder must preserve input');
  const weights=result.workbook.worksheets.getItem(plan.security_id.sheet);
  weights.getRangeByIndexes(0,3,payload.display.tables[4].rows.length+4,1).format.columnWidth=plan.security_id.width;
  weights.getRangeByIndexes(4,3,payload.display.tables[4].rows.length,1).format.wrapText=false;
  const sources=result.workbook.worksheets.getItem(plan.source_paths.sheet);
  sources.getRangeByIndexes(0,1,9,1).format.columnWidth=100;
  sources.getRangeByIndexes(4,1,5,1).format.wrapText=true;
  for(const item of plan.source_paths.rows)sources.getRangeByIndexes(item.row-1,0,1,3).format.rowHeight=item.height;
  assert.deepEqual(payload,original,'Layout must preserve input');
  return {...result,layoutAdjustments:plan};
}
