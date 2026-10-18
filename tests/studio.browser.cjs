const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_EXECUTABLE_PATH?{executablePath:process.env.CHROMIUM_EXECUTABLE_PATH}:{}),args:['--no-sandbox','--no-zygote','--single-process','--disable-gpu','--disable-software-rasterizer']});
 const page=await browser.newPage({viewport:{width:1586,height:1080}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 const project='00000000-0000-4000-8000-000000000001',folder='00000000-0000-4000-8000-000000000011',text='00000000-0000-4000-8000-000000000012',file='00000000-0000-4000-8000-000000000013';
 let language='ar',version=1,welcome='أهلًا بك في مكتبتك. اختر القسم الذي تحتاجه.',conflict=false;
 let items=[{id:folder,parent_id:null,kind:'section',title:'المحاضرات والدروس',revision:'a'.repeat(64),pending:false,published:true},
  {id:text,parent_id:null,kind:'text',title:'عن المكتبة',text:'محتوى مرتب في مكان واحد.',revision:'b'.repeat(64),pending:true},
  {id:file,parent_id:null,kind:'file',title:'دليل الاستخدام',revision:'c'.repeat(64),file_ready:true,pending:false,published:true}];
 await page.route('**/api/v1/**',async route=>{const req=route.request(),url=new URL(req.url()),path=url.pathname,body=req.postDataJSON();let result={},status=200;
  if(path.endsWith('/auth/methods'))result={oidc:true,telegram:true};
  else if(path.endsWith('/auth/oidc/callback'))result={access_token:'qa-studio-not-real'};
  else if(path.endsWith('/me/preferences')){if(body)language=body.language_code;result={language_code:language};}
  else if(path.endsWith('/tenants'))result=[{id:'tenant-test',name:'المساحة الرئيسية'}];
  else if(path.endsWith('/projects'))result={items:[{id:project,name:'مكتبة QMR7S',status:'running',active_version:1}],has_more:false};
  else if(path.endsWith('/studio')){if(req.method()==='PATCH'){assert.equal(body.version,version);version++;welcome=body.welcome;}result={id:project,name:'مكتبة QMR7S',kind:'buttons',version,active_version:1,welcome,username:'ExampleLibraryBot',status:'running',commands:0,replies:0};}
  else if(path.endsWith('/studio/buttons')){const parent=url.searchParams.get('parent_id');result={items:items.filter(i=>i.parent_id===(parent||null)),has_more:false,folder:parent?items.find(i=>i.id===parent):null};}
  else if(path.includes('/studio/buttons/')){const id=path.split('/buttons/')[1].split('/')[0];if(conflict&&req.method()==='PUT'){status=409;result={detail:'The button changed. Reload before saving.'};}else if(path.endsWith('/delete')){items=items.filter(i=>i.id!==id);result={deleted:true};}else{const index=items.findIndex(i=>i.id===id);result={...body,id,revision:'d'.repeat(64),pending:true};if(index<0)items.push(result);else items[index]=result;}}
  await route.fulfill({status,contentType:'application/json',body:JSON.stringify(result)});
 });
 await page.goto((process.env.BASE_URL||'http://127.0.0.1:8765')+'/dashboard/callback?code=qa&state=qa');
 await page.getByRole('button',{name:'استوديو البوت',exact:true}).click();await page.locator('.studio-item').nth(2).waitFor();
 assert.equal(await page.title(),'QMRSmithbot');assert(await page.locator('#studio').isVisible());assert(await page.locator('.phone-message').textContent());
 if(process.env.QA_SCREENSHOT_DIR)await page.screenshot({path:process.env.QA_SCREENSHOT_DIR+'/studio-desktop.png',fullPage:true});
 await page.locator('.studio-item-main').filter({hasText:'عن المكتبة'}).click();await page.getByLabel('محتوى الرسالة').fill('شرح جديد <script>هذا نص فقط</script>');
 assert.equal(await page.locator('.phone-message').textContent(),'شرح جديد <script>هذا نص فقط</script>');
 await page.getByLabel('لون الزر في تيليجرام').selectOption('success');await page.getByLabel('موضع الزر في الصف').selectOption('join');
 await page.getByRole('button',{name:'حفظ المسودة',exact:true}).click();await page.waitForFunction(()=>!document.querySelector('#studio').inert);assert.equal(items.find(i=>i.id===text).text,'شرح جديد <script>هذا نص فقط</script>');assert.equal(items.find(i=>i.id===text).style,'success');assert.equal(items.find(i=>i.id===text).join_previous,true);assert.equal(await page.locator('.phone-buttons .telegram-success').count(),1);assert.equal(await page.locator('.telegram-button-row').first().locator('button').count(),2);
 conflict=true;await page.getByLabel('محتوى الرسالة').fill('احتفظ بهذا النص عند التعارض');await page.getByRole('button',{name:'حفظ المسودة',exact:true}).click();await page.locator('.studio-error').filter({hasText:'تغيّر المحتوى'}).waitFor();assert.equal(await page.getByLabel('محتوى الرسالة').inputValue(),'احتفظ بهذا النص عند التعارض');conflict=false;
 page.once('dialog',d=>d.accept());await page.getByRole('button',{name:'إلغاء التعديل',exact:true}).click();
 await page.getByRole('button',{name:'إضافة نص',exact:true}).click();await page.getByLabel('اسم الزر').fill('خطة الدراسة');await page.getByLabel('محتوى الرسالة').fill('مراجعة اليوم');await page.getByRole('button',{name:'حفظ المسودة',exact:true}).click();await page.waitForFunction(()=>!document.querySelector('#studio').inert);assert(items.some(i=>i.title==='خطة الدراسة'));
 await page.getByRole('button',{name:'إضافة قسم',exact:true}).click();await page.getByLabel('اسم الزر').fill('قسم تجريبي');await page.getByRole('button',{name:'حفظ المسودة',exact:true}).click();await page.waitForFunction(()=>!document.querySelector('#studio').inert);
 const newFolder=items.find(i=>i.title==='قسم تجريبي');await page.locator('.studio-item').filter({hasText:'قسم تجريبي'}).getByRole('button',{name:'قسم',exact:true}).click();await page.locator('.studio-items').filter({hasText:'هذه القائمة فارغة'}).waitFor();
 await page.getByRole('button',{name:'إضافة رابط',exact:true}).click();await page.getByLabel('اسم الزر').fill('موقعنا');await page.getByLabel('رابط HTTPS').fill('https://example.com');await page.getByRole('button',{name:'حفظ المسودة',exact:true}).click();await page.waitForFunction(()=>!document.querySelector('#studio').inert);assert.equal(items.find(i=>i.title==='موقعنا').parent_id,newFolder.id);
 page.once('dialog',d=>d.accept());await page.getByRole('button',{name:'حذف الزر',exact:true}).click();await page.waitForFunction(()=>!document.querySelector('#studio').inert);assert(!items.some(i=>i.title==='موقعنا'));
 await page.locator('.studio-breadcrumbs').getByRole('button',{name:'القائمة الرئيسية',exact:true}).click();await page.locator('.studio-item').nth(2).waitFor();await page.getByLabel('رسالة البداية',{exact:true}).fill('ترحيب جديد للجميع');await page.getByRole('button',{name:'حفظ رسالة البداية',exact:true}).click();await page.waitForFunction(()=>!document.querySelector('#studio').inert);assert.equal(welcome,'ترحيب جديد للجميع');
 await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 if(process.env.QA_SCREENSHOT_DIR)await page.screenshot({path:process.env.QA_SCREENSHOT_DIR+'/studio-mobile.png',fullPage:true});
 await page.getByRole('button',{name:'معاينة الزائر',exact:true}).click();assert(await page.locator('.studio-phone').isVisible());assert(!await page.locator('.studio-workspace').isVisible());await page.locator('.phone-buttons').getByRole('button',{name:'المحاضرات والدروس',exact:true}).click();await page.locator('.phone-buttons').getByRole('button',{name:'القائمة الرئيسية',exact:true}).waitFor();await page.locator('.phone-buttons').getByRole('button',{name:'القائمة الرئيسية',exact:true}).click();await page.locator('.phone-buttons').getByRole('button',{name:'عن المكتبة',exact:true}).waitFor();if(process.env.QA_SCREENSHOT_DIR)await page.screenshot({path:process.env.QA_SCREENSHOT_DIR+'/studio-mobile-preview.png',fullPage:true});await page.getByRole('button',{name:'التصميم',exact:true}).click();assert(await page.locator('.studio-workspace').isVisible());
 await page.locator('.studio-item-main').filter({hasText:'دليل الاستخدام'}).click();assert((await page.getByRole('link',{name:'رفع أو استبدال الملف داخل بوتك'}).getAttribute('href')).startsWith('https://t.me/ExampleLibraryBot?start=upload_'));
 await page.locator('#language').click();await page.waitForFunction(()=>document.documentElement.lang==='en');await page.locator('.studio-item').nth(2).waitFor();await page.getByRole('button',{name:'Visitor preview',exact:true}).click();assert(await page.getByRole('heading',{name:'Visitor preview'}).isVisible());
 assert.deepEqual(errors,[]);await browser.close();console.log('Studio passed: desktop/mobile, edits, nested creation/deletion, conflict keeps text, draft welcome, file link, preview escaping, language, console.');
})().catch(e=>{console.error(e);process.exit(1)});
