'use strict';
// Isolated served-page observation. No clicks; reject every non-GET request.
const fs = require('node:fs');
const assert = require('node:assert/strict');
const {chromium} = require('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const {captureDailyDom} = require('./capture_daily_ui_acceptance_v3.cjs');

(async () => {
  const directory = process.argv[2];
  assert(directory, 'New private output directory required');
  fs.mkdirSync(directory);
  const browser = await chromium.launch({headless:true, executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
  try {
    const context = await browser.newContext({viewport:{width:1600,height:1100}});
    const page = await context.newPage();
    const unexpected = [], reads = [], responses = [];
    let current = null, calendar = null;
    const account = async () => {
      const response = await context.request.get('http://127.0.0.1:8010/api/strategy-account');
      assert.equal(response.status(), 200);
      return (await response.json()).account;
    };
    const before = await account();
    await page.route('**/*', async route => {
      if (route.request().method() !== 'GET') {
        unexpected.push(new URL(route.request().url()).pathname);
        return route.abort();
      }
      return route.continue();
    });
    page.on('response', response => {
      const path = new URL(response.url()).pathname;
      if (!['/api/strategy-daily-v3/current','/api/news/scheduled-earnings'].includes(path)) return;
      reads.push((async () => {
        const body = await response.json();
        responses.push({path,status:response.status(),body});
        assert.equal(response.status(),200);
        if (path === '/api/strategy-daily-v3/current') current = body;
        else calendar = body;
      })());
    });
    await page.goto('http://127.0.0.1:8010/', {waitUntil:'domcontentloaded'});
    await page.waitForFunction(() => {
      const submit = document.querySelector('#strategyMonthlyTarget form.monthly-cash-form > button[type=submit]');
      return submit && !submit.disabled && !document.getElementById('btnRefresh').disabled &&
        document.querySelectorAll('#strategyMonthlyTarget table td').length > 0;
    }, null, {timeout:240000});
    await Promise.all(reads);
    assert(current && calendar, 'Current advice and calendar GET evidence required');
    const capture = await page.evaluate(captureDailyDom);
    capture.api_state = {account:current.account,target:current.target,daily:current.daily};
    capture.scheduled_context = calendar;
    capture.account_before = before;
    capture.account_after = await account();
    capture.cash_posts_intercepted = 0;
    capture.unexpected_writes = unexpected;
    capture.api_responses = responses;
    fs.writeFileSync(directory+'/capture.json', JSON.stringify(capture,null,2));
    await page.screenshot({path:directory+'/page.png',fullPage:true});
    console.log(JSON.stringify({captured:true,daily_status:current.daily?.status,blocked_writes:unexpected.length,directory}));
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
