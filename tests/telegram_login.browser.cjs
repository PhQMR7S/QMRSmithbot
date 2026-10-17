// Browser plugin not available: use Playwright with the local application and mocked auth APIs.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const fs=require('node:fs');
(async()=>{
  const base=process.env.BASE_URL||'http://127.0.0.1:8877';
  const server=process.env.BASE_URL?null:spawn(process.env.QA_PYTHON||'python',
    ['-m','uvicorn','qmrsmithbot.api.app:app','--host','127.0.0.1','--port','8877'],{stdio:'ignore'});
  let browser;
  try{
    for(let attempt=0;attempt<80;attempt++){
      try{if((await fetch(base+'/health')).ok)break;}catch{}
      if(attempt===79)throw new Error('Local QA application did not start');
      await new Promise(resolve=>setTimeout(resolve,100));
    }
    browser=await chromium.launch({headless:true,
      ...(process.env.CHROMIUM_EXECUTABLE_PATH?{executablePath:process.env.CHROMIUM_EXECUTABLE_PATH}:{}),
      args:['--no-sandbox','--no-zygote','--single-process','--disable-dev-shm-usage',
        '--disable-gpu','--disable-software-rasterizer']});
    const page=await browser.newPage({viewport:{width:1366,height:900}}),errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    let finishAttempts=0,cancellations=0;
    await page.route('**/api/v1/**',async route=>{
      const req=route.request(),path=new URL(req.url()).pathname;let status=200,result={};
      if(path.endsWith('/auth/methods'))result={telegram:true,oidc:false};
      else if(path.endsWith('/telegram/start')){finishAttempts=0;result={challenge_id:'B'.repeat(32),
        browser_secret:'A'.repeat(43),verification_code:'123456',expires_at:new Date(Date.now()+300000).toISOString(),
        telegram_url:'https://t.me/qmrsmith_test_bot?start=login_'+'B'.repeat(32)};}
      else if(path.endsWith('/telegram/finish')){
        assert.equal(req.postDataJSON().browser_secret,'A'.repeat(43));
        if(++finishAttempts===1){status=202;result={status:'pending'};}
        else result={access_token:'test-session-only'};
      }else if(path.endsWith('/telegram/cancel')){cancellations++;status=204;}
      else if(path.endsWith('/me/preferences'))result={language_code:'ar'};
      else if(path.endsWith('/tenants'))result=[{id:'test-tenant',name:'مساحتي'}];
      else if(path.endsWith('/projects'))result={items:[],has_more:false};
      else if(path.endsWith('/auth/logout'))status=204;
      await route.fulfill({status,contentType:'application/json',body:status===204?'':JSON.stringify(result)});
    });
    await page.goto(base+'/dashboard');
    assert.equal(await page.title(),'QMRSmithbot');
    await page.locator('#telegramLogin').waitFor({state:'visible'});
    assert(await page.locator('#login').isHidden());
    await page.locator('#telegramLogin').click();
    await page.locator('#telegramLoginPanel').waitFor({state:'visible'});
    assert.equal(await page.locator('#verificationCode').textContent(),'123456');
    assert(!(await page.locator('#telegramLink').getAttribute('href')).includes('123456'));
    await page.locator('#finishLogin').click();
    await page.waitForFunction(()=>document.getElementById('loginStatus').textContent.includes('بانتظار'));
    assert((await page.locator('#loginStatus').textContent()).includes('بانتظار'));
    if(process.env.QA_SCREENSHOT_DIR){fs.mkdirSync(process.env.QA_SCREENSHOT_DIR,{recursive:true});
      await page.screenshot({path:process.env.QA_SCREENSHOT_DIR+'/telegram-login-desktop.png',fullPage:true});}
    await page.locator('#cancelLogin').click();
    await page.locator('#telegramLoginPanel').waitFor({state:'hidden'});
    assert.equal(cancellations,1);assert(await page.locator('#telegramLoginPanel').isHidden());
    assert.equal(await page.locator('#verificationCode').textContent(),'');
    await page.locator('#telegramLogin').click();
    await page.locator('#telegramLoginPanel').waitFor({state:'visible'});
    await page.locator('#finishLogin').click();await page.locator('#finishLogin').click();
    await page.locator('#content').waitFor({state:'visible'});
    assert(await page.locator('#auth').isHidden());
    assert(!await page.evaluate(()=>Object.values(localStorage).some(value=>value.includes('test-session')||value.includes('AAAA'))));
    await page.locator('#logout').click();await page.locator('#auth').waitFor({state:'visible'});
    await page.setViewportSize({width:390,height:844});
    await page.locator('#telegramLogin').click();
    await page.locator('#telegramLoginPanel').waitFor({state:'visible'});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    if(process.env.QA_SCREENSHOT_DIR)await page.screenshot({path:process.env.QA_SCREENSHOT_DIR+'/telegram-login-mobile.png',fullPage:true});
    assert.deepEqual(errors,[]);
    console.log('PASS: Telegram login UI, pending, cancel, completion, logout, memory-only secrets, mobile layout and console. API responses mocked.');
  }finally{if(browser)await browser.close();if(server)server.kill();}
})().catch(error=>{console.error(error);process.exit(1);});
