const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_EXECUTABLE_PATH?{executablePath:process.env.CHROMIUM_EXECUTABLE_PATH}:{}),args:['--no-sandbox','--no-zygote','--single-process','--disable-gpu','--disable-software-rasterizer']});
 const page=await browser.newPage({viewport:{width:1586,height:1080}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 const id='00000000-0000-4000-8000-000000000021';let version=2,language='ar',welcome='أهلًا بك في التسجيل.',conflict=false;
 let model={title:'نموذج التسجيل',completion:'تم استلام طلبك بنجاح',questions:[
  {id:'purpose',prompt:'شنو تحتاج؟',kind:'choice',required:true,minimum:null,maximum:null,choices:[{label:'تسجيل جديد',next:'age'},{label:'إنهاء',next:'end'}]},
  {id:'name',prompt:'ما اسمك؟',kind:'text',required:false,minimum:null,maximum:null,choices:[]},
  {id:'age',prompt:'كم عمرك؟',kind:'number',required:true,minimum:18,maximum:90,choices:[]}]};
 let submissions=[{id:'00000000-0000-4000-8000-000000000031',visitor_id:123456789,version:1,created_at:'2026-10-18T08:00:00Z',data:{title:'نموذج التسجيل',answers:[{question_id:'purpose',question:'شنو تحتاج؟',answer:'تسجيل جديد'},{question_id:'age',question:'كم عمرك؟',answer:'٢٣'}]}}];
 const overview=()=>({id,name:'طلبات QMR7S',kind:'form',version,active_version:1,welcome,username:'ExampleFormsBot',status:'running',commands:0,replies:0,form:model});
 await page.route('**/api/v1/**',async route=>{const req=route.request(),url=new URL(req.url()),path=url.pathname,body=req.postDataJSON();let result={},status=200;
  if(path.endsWith('/auth/methods'))result={oidc:true,telegram:true};
  else if(path.endsWith('/auth/oidc/callback'))result={access_token:'qa-forms-not-real'};
  else if(path.endsWith('/me/preferences')){if(body)language=body.language_code;result={language_code:language};}
  else if(path.endsWith('/tenants'))result=[{id:'tenant-test',name:'المساحة الرئيسية'}];
  else if(path.endsWith('/projects'))result={items:[{id,name:'طلبات QMR7S',status:'running',active_version:1}],has_more:false};
  else if(path.endsWith('/studio/form')){if(conflict){status=409;result={detail:'Draft changed'};}else{assert.equal(body.version,version);model=body.form;version++;result=overview();}}
  else if(path.endsWith('/studio')){if(req.method()==='PATCH'){assert.equal(body.version,version);welcome=body.welcome;version++;}result=overview();}
  else if(path.endsWith('/submissions'))result={items:submissions,has_more:false};
  else if(path.includes('/submissions/')&&path.endsWith('/delete')){submissions=[];result={deleted:true};}
  await route.fulfill({status,contentType:'application/json',body:JSON.stringify(result)});
 });
 await page.goto((process.env.BASE_URL||'http://127.0.0.1:8765')+'/dashboard/callback?code=qa&state=qa');await page.getByRole('button',{name:'استوديو البوت',exact:true}).click();await page.locator('.form-question').nth(2).waitFor();
 assert.equal(await page.title(),'QMRSmithbot');assert.equal(await page.locator('.form-question').count(),3);
 await page.locator('.phone-buttons').getByRole('button',{name:'بدء النموذج',exact:true}).click();await page.locator('.phone-buttons').getByRole('button',{name:'تسجيل جديد',exact:true}).click();assert((await page.locator('.phone-message').textContent()).includes('كم عمرك'));
 await page.locator('.phone-buttons input').fill('17');await page.locator('.phone-buttons').getByRole('button',{name:'متابعة',exact:true}).click();assert((await page.locator('.phone-message').textContent()).includes('كم عمرك'));
 await page.locator('.phone-buttons input').fill('23');await page.locator('.phone-buttons').getByRole('button',{name:'متابعة',exact:true}).click();assert.equal(await page.locator('.phone-message').textContent(),'تم استلام طلبك بنجاح');assert.equal(submissions.length,1);
 await page.locator('.phone-buttons').getByRole('button',{name:'إعادة المعاينة',exact:true}).click();
 const first=page.locator('.form-question').first();await first.getByRole('button',{name:'نقل لأسفل',exact:true}).click();await page.locator('.form-question').nth(1).getByRole('button',{name:'نقل لأسفل',exact:true}).click();assert((await page.locator('.form-builder form>.studio-error').textContent()).includes('يعود للخلف'));await page.locator('.form-question').nth(1).getByRole('button',{name:'نقل لأعلى',exact:true}).click();
 // Save after changing the welcome must use its new workflow version without losing form edits.
 await page.getByLabel('عنوان النموذج',{exact:true}).fill('نموذج طلبات جديد');await page.locator('details.studio-card>summary').click();await page.getByLabel('رسالة البداية',{exact:true}).fill('ترحيب جديد');await page.getByRole('button',{name:'حفظ رسالة البداية',exact:true}).click();await page.waitForFunction(()=>!document.querySelector('#studio').inert);
 assert.equal(await page.getByLabel('عنوان النموذج',{exact:true}).inputValue(),'نموذج طلبات جديد');await page.getByRole('button',{name:'حفظ النموذج كمسودة',exact:true}).click();await page.waitForFunction(()=>!document.querySelector('#studio').inert);assert.equal(model.title,'نموذج طلبات جديد');
 conflict=true;await page.getByLabel('عنوان النموذج',{exact:true}).fill('لا تفقد هذا التعديل');await page.getByRole('button',{name:'حفظ النموذج كمسودة',exact:true}).click();await page.locator('.studio-workspace>.studio-error').filter({hasText:'تغيّر المحتوى'}).waitFor();assert.equal(await page.getByLabel('عنوان النموذج',{exact:true}).inputValue(),'لا تفقد هذا التعديل');conflict=false;
 await page.getByRole('button',{name:'حفظ النموذج كمسودة',exact:true}).click();await page.waitForFunction(()=>!document.querySelector('#studio').inert);
 await page.getByRole('button',{name:'إضافة سؤال',exact:true}).click();assert.equal(await page.locator('.form-question').count(),4);await page.locator('.form-question').last().getByLabel('نص السؤال',{exact:true}).fill('ما مدينتك؟');await page.getByRole('button',{name:'حفظ النموذج كمسودة',exact:true}).click();await page.waitForFunction(()=>!document.querySelector('#studio').inert);assert.equal(model.questions.length,4);
 const submission=page.locator('.form-submission');await submission.locator('summary').click();assert((await submission.textContent()).includes('٢٣'));const downloadPromise=page.waitForEvent('download');await submission.getByRole('button',{name:'تنزيل JSON',exact:true}).click();const download=await downloadPromise;assert(download.suggestedFilename().endsWith('.json'));
 if(process.env.QA_SCREENSHOT_DIR)await page.screenshot({path:process.env.QA_SCREENSHOT_DIR+'/forms-desktop.png',fullPage:false});
 page.once('dialog',d=>d.accept());await submission.getByRole('button',{name:'حذف الإجابة المكتملة',exact:true}).click();await page.locator('.form-inbox').filter({hasText:'لا توجد إجابات'}).waitFor();assert.equal(submissions.length,0);
 await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await page.getByRole('button',{name:'معاينة الزائر',exact:true}).click();await page.locator('.phone-buttons').getByRole('button',{name:'بدء النموذج',exact:true}).click();if(process.env.QA_SCREENSHOT_DIR)await page.screenshot({path:process.env.QA_SCREENSHOT_DIR+'/forms-mobile-question.png',fullPage:true});await page.locator('.phone-buttons').getByRole('button',{name:'إنهاء',exact:true}).click();assert.equal(await page.locator('.phone-message').textContent(),'تم استلام طلبك بنجاح');if(process.env.QA_SCREENSHOT_DIR)await page.screenshot({path:process.env.QA_SCREENSHOT_DIR+'/forms-mobile.png',fullPage:true});
 assert.deepEqual(errors,[]);await browser.close();console.log('Forms passed: branching preview, number validation, welcome/form revisions, conflict preservation, question creation, owner inbox, JSON export, deletion, mobile, console.');
})().catch(e=>{console.error(e);process.exit(1)});
