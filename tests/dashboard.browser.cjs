const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_EXECUTABLE_PATH?{executablePath:process.env.CHROMIUM_EXECUTABLE_PATH}:{}),args:['--no-sandbox']});const page=await browser.newPage({viewport:{width:1586,height:992}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
let projects=[{id:'00000000-0000-4000-8000-000000000001',name:'خدمة العملاء',status:'draft',active_version:null},{id:'00000000-0000-4000-8000-000000000002',name:'ردود تلقائية',status:'stopped',active_version:1},{id:'00000000-0000-4000-8000-000000000003',name:'قائمة الأوامر',status:'running',active_version:1}];let language='ar',savedName='',created=false;
await page.route('**/api/v1/**',async route=>{const request=route.request(),url=new URL(request.url()),path=url.pathname,body=request.postDataJSON();let result={};
if(path.endsWith('/auth/oidc/callback'))result={access_token:'qa-session-not-real'};
else if(path.endsWith('/me/preferences')){if(body)language=body.language_code;result={language_code:language,direction:language==='ar'?'rtl':'ltr'};}
else if(path.endsWith('/tenants'))result=[{id:'tenant-test',name:'المساحة الرئيسية'}];
else if(path.endsWith('/templates'))result=[{id:'welcome',title:language==='ar'?'بوت ترحيب':'Welcome bot'},{id:'auto-replies',title:language==='ar'?'ردود تلقائية':'Auto replies'},{id:'command-menu',title:language==='ar'?'قائمة أوامر':'Commands'}];
else if(path.includes('/templates/')&&request.method()==='POST'){created=true;projects.push({id:'new',name:body.name,status:'draft',active_version:null});result={};}
else if(path.endsWith('/projects')){let items=projects.filter(p=>p.name.includes(url.searchParams.get('query')||'')&&(!url.searchParams.get('status')||p.status===url.searchParams.get('status')));result={items,has_more:false,limit:20,offset:0};}
else if(path.endsWith('/versions'))result=[{version:1,published_at:null}];
else if(request.method()==='PATCH'){savedName=body.name;projects[0].name=body.name;result=projects[0];}
else if(path.endsWith('/stop'))projects.find(p=>path.includes(p.id)).status='stopped';
else if(path.endsWith('/resume'))projects.find(p=>path.includes(p.id)).status='running';
else if(path.includes('/publish/'))projects[0].active_version=1;
await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(result)});});
await page.goto((process.env.BASE_URL||'http://127.0.0.1:8765')+'/dashboard/callback?code=qa&state=qa');await page.locator('#rows tr').nth(2).waitFor();assert(!page.url().includes('code='));
if(process.env.QA_SCREENSHOT_DIR)await page.screenshot({path:process.env.QA_SCREENSHOT_DIR+'/desktop.png',fullPage:true});
await page.getByRole('button',{name:'إعادة التسمية',exact:true}).first().click();await page.locator('#fields input').fill('اسم جديد');await page.locator('#save').click();await page.locator('#modal').waitFor({state:'hidden'});assert.equal(savedName,'اسم جديد');
await page.getByRole('button',{name:'إيقاف',exact:true}).click();await page.locator('#save').click();await page.locator('#modal').waitFor({state:'hidden'});assert.equal(projects[2].status,'stopped');
await page.locator('#query').fill('لا يوجد');await page.locator('#search button').click();await page.locator('#empty').waitFor();await page.locator('#query').fill('');await page.locator('#search button').click();
await page.locator('#create').click();await page.getByRole('button',{name:'اختيار القالب',exact:true}).first().click();await page.locator('#fields input').fill('بوت تجريبي');await page.locator('#save').click();await page.locator('#modal').waitFor({state:'hidden'});assert(created);
await page.locator('#language').click();await page.waitForFunction(()=>document.documentElement.lang==='en');assert.equal(await page.locator('html').getAttribute('dir'),'ltr');await page.locator('#language').click();await page.waitForFunction(()=>document.documentElement.lang==='ar');
await page.setViewportSize({width:390,height:844});if(process.env.QA_SCREENSHOT_DIR)await page.screenshot({path:process.env.QA_SCREENSHOT_DIR+'/mobile.png',fullPage:true});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
assert.deepEqual(errors,[]);await browser.close();console.log('Passed browser flows: callback, projects, rename, stop confirmation, empty search, draft create, language switch, mobile overflow, JS errors.');
})().catch(e=>{console.error(e);process.exit(1)});
