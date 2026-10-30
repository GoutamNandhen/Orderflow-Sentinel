// Verify both built applications and actual recovery on a deployed same-origin URL.
import { chromium } from 'playwright';
import { expect } from '@playwright/test';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
const runtime=JSON.parse(readFileSync('work/cloud-runtime.json','utf8'));
const base=(process.argv[2]||'http://localhost:8002').replace(/\/$/,'');
let browser;
try {
  browser=await chromium.launch({headless:true});
  const context=await browser.newContext({viewport:{width:1440,height:1000},timezoneId:'Asia/Kolkata'});
  const shop=await context.newPage(), consolePage=await context.newPage();
  const failures=[];
  for(const page of [shop,consolePage]) {
    page.on('pageerror',e=>failures.push(e.message));
    page.on('console',m=>{if(m.type()==='error')failures.push(m.text());});
  }
  await shop.goto(base+'/shop/',{timeout:120000});
  await expect(shop.locator('.product-card')).toHaveCount(20);
  await consolePage.goto(base+'/console/');
  await expect(consolePage.locator('input[name=password]')).toBeVisible();
  await expect(consolePage.locator('input[name=password]')).toHaveValue('');
  await consolePage.locator('input[name=password]').fill(runtime.OPERATOR_PASSWORD);
  await consolePage.getByRole('button',{name:'Sign In',exact:true}).click();
  await expect(consolePage.getByText('Connection: Live',{exact:true}).first()).toBeVisible({timeout:30000});
  const token=await consolePage.evaluate(()=>localStorage.getItem('sentinel_operator'));
  const customer=await shop.evaluate(()=>document.cookie.split('; ').find(c=>c.startsWith('of_customer=')).split('=')[1]);
  const headers={Authorization:'Bearer '+token,'X-Customer-Session':customer,'Idempotency-Key':crypto.randomUUID()};
  const result=await context.request.post(base+'/api/console/demo',{headers,data:{profile:'next',error_type:'API_TIMEOUT'}});
  expect(result.status()).toBe(201);
  const order=await result.json();
  await shop.goto(base+`/shop/?order=${order.id}&token=${encodeURIComponent(order.tracking_token)}`);
  await expect(shop.getByText('Connection: Live',{exact:true}).first()).toBeVisible({timeout:30000});
  await expect.poll(async()=>{
    const response=await context.request.get(base+'/api/orders/'+order.id,{headers});
    return (await response.json()).status;
  },{timeout:45000}).toBe('CONFIRMED');
  await expect(shop.locator('.tracking-head')).toContainText(order.id);
  await expect(consolePage.locator('.kpi').first()).not.toContainText('Unavailable');
  await shop.setViewportSize({width:390,height:844});
  expect(await shop.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await expect(shop.getByText('UNFULFILLED',{exact:true})).toBeVisible();
  expect(failures).toEqual([]);
  mkdirSync('work/production-verification',{recursive:true});
  await shop.screenshot({path:'work/production-verification/shop.png',fullPage:true});
  await consolePage.screenshot({path:'work/production-verification/console.png'});
  const summary={passed:true,base,timestamp:new Date().toISOString(),checks:{both_built_apps:true,private_operator_login:true,secure_or_local_websocket_connections:true,shared_customer_session:true,actual_timeout_recovery:true,delivery_not_falsely_completed:true,mobile_no_overflow:true,console_errors:failures.length}};
  writeFileSync('work/production-verification/results.json',JSON.stringify(summary,null,2));
  console.log(JSON.stringify(summary,null,2));
}catch(error){
  console.error(String(error).replaceAll(runtime.OPERATOR_PASSWORD,'[REDACTED]').replaceAll(runtime.DATABASE_URL,'[REDACTED]'));
  process.exitCode=1;
}finally{await browser?.close();}
