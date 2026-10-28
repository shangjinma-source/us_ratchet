'use strict';
// Pure DOM extractor for an already-open Cua-controlled page. Does not launch
// a browser, click, fetch, inject financial data or invoke model/account routes.
// External capture orchestration must add account_before/account_after and the
// observed write audit. The extractor cannot certify these from DOM alone.
function captureDailyDom() {
 const tables=[...document.querySelectorAll('#strategyMonthlyTarget table')];
 if(tables.length!==1)throw Error('EXACTLY_ONE_DAILY_TABLE_REQUIRED');
 const saves=[...document.querySelectorAll('#strategyMonthlyTarget button[type=submit]')];
 const refresh=document.getElementById('btnRefresh');
 if(saves.length!==1||!refresh)throw Error('UI_SETTLED_CONTROLS_REQUIRED');
 const ui_controls={cash_button_text:saves[0].textContent.trim(),cash_button_disabled:saves[0].disabled,refresh_button_disabled:refresh.disabled};
 const table=tables[0],domRows=[...table.querySelectorAll('tr')].filter(row=>row.querySelector('td'));
 const text=node=>node?.textContent.trim()||'';
 const dom_rows=domRows.map(dom=>{
  const cells=[...dom.querySelectorAll('td')];
  if(cells.length!==4)throw Error('FOUR_DOM_CELLS_REQUIRED');
  const ai=cells[3].querySelector('.daily-ai-note');
  const parts={position:text(cells[1].querySelector('strong')),monthly_note:text(cells[1].querySelector('small')),
   actions:[...cells[2].querySelectorAll('strong')].map(text),limits:[...cells[2].querySelectorAll('small')].map(text),
   reason:text(cells[3].firstElementChild),ai_label:text(ai?.firstElementChild),
   ai_text:ai?[...ai.children].slice(1).map(text).join(''):''};
  return {ticker:text(cells[0]),dom_cells:cells.map(text),dom_parts:parts};
 });
 return {capture_schema:'DAILY_FOUR_COLUMN_DOM_CAPTURE_V2',scope:'READ_ONLY_PAGE_CAPTURE',
  observed_at:new Date().toISOString(),dom_rows,ui_controls,
  dom_row_count:domRows.length,table_headers:[...table.querySelectorAll('th')].map(text),page_text:document.body.innerText};
}
if(typeof module!=='undefined')module.exports={captureDailyDom};
