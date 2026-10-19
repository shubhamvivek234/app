const {test,expect}=require('@playwright/test');
const {createHash}=require('crypto');
const context={contract_version:1,workspace_id:'workspace☕',scope_digest:'f'.repeat(64),execution_authorized:false};
const row=()=>({id:'tpl_custom_012345abcd',name:'Reviewed template ☕',is_custom:true,
  workspace_access:{contract_version:1,workspace_id:context.workspace_id,visibility:'workspace',created_by_you:false,
    can_configure:true,can_edit:true,can_delete:true,execution_authorized:false},
  nodes:[{id:'root',type:'visit_profile'}],edges:[],tree:[{id:'root',type:'visit_profile'}],
  compatibility:{contract_version:1,valid:true,configuration_available:true,execution_authorized:false},
  deletion_review:{contract_version:1,reviewable:true,revision:0,workspace_id:context.workspace_id,
    identity_digest:'b'.repeat(64),review_digest:'a'.repeat(64),scope_digest:'c'.repeat(64),
    deletion_authorized:false,execution_authorized:false}});
const receipt=body=>{const original=JSON.parse(body.content_json),{content_json,...reference}=body;
  return {...reference,status:'deleted',template_id:original.template_id,revision:original.revision,
    identity_digest:original.identity_digest,review_digest:original.review_digest,review_scope_digest:original.scope_digest};};
const json=(route,data,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)});
async function setup(page,handler){
  await page.route('**/*',async(route)=>{
    const request=route.request(),url=new URL(request.url());
    if(url.origin!=='http://127.0.0.1:4179')return route.abort();
    if(url.pathname==='/'||url.pathname==='/bundle.js')return route.continue();
    if(url.pathname.endsWith('/template-deletions/context'))return json(route,context);
    if(url.pathname.includes('/sequences/templates')||url.pathname.includes('/sequences/template-deletions'))return handler(route,url);
    return json(route,[]);
  });
  await page.goto('/?view=templates');
  await page.getByRole('button',{name:'Browse winning templates',exact:true}).click();
}
const deleteButton=page=>page.getByRole('button',{name:'Delete template Reviewed template ☕',exact:true});

test('whole original Unicode review SHA and exact receipt confirm deletion before current catalog reload',async({page})=>{
  const record=row();let body,posts=0;
  await setup(page,(route)=>{
    if(route.request().method()==='POST'){posts++;body=route.request().postDataJSON();return json(route,receipt(body));}
    return json(route,posts?[]:[record]);
  });
  await deleteButton(page).click();
  await expect(page.getByText('No sequence templates are available.',{exact:true})).toBeVisible();
  expect(posts).toBe(1);expect(body.input_digest).toBe(createHash('sha256').update(body.content_json,'utf8').digest('hex'));
  expect(JSON.parse(body.content_json)).toEqual({contract_version:1,workspace_id:context.workspace_id,revision:0,
    review_digest:'a'.repeat(64),identity_digest:'b'.repeat(64),scope_digest:'c'.repeat(64),template_id:record.id});
  expect(body.scope_digest).toBe(context.scope_digest);expect(body.scope_digest).not.toBe(JSON.parse(body.content_json).scope_digest);
});

test('lost response recovers original deletion and preserves a later replacement',async({page})=>{
  const original=row(),replacement={...row(),deletion_review:{...row().deletion_review,identity_digest:'e'.repeat(64),review_digest:'d'.repeat(64)}};
  let body,posts=0,gets=0,statusQuery;
  await setup(page,(route,url)=>{
    if(route.request().method()==='POST'){posts++;body=route.request().postDataJSON();return route.abort('failed');}
    if(url.pathname.includes('/template-deletions/')){gets++;statusQuery=url.searchParams;return json(route,receipt(body));}
    return json(route,posts?[replacement]:[original]);
  });
  await deleteButton(page).click();
  await expect(page.getByRole('alert')).toContainText('Earlier deletion is unconfirmed');
  await page.getByRole('button',{name:'Check original deletion status',exact:true}).click();
  await expect(deleteButton(page)).toBeEnabled();await expect(page.getByText('Reviewed template ☕',{exact:true})).toBeVisible();
  expect(posts).toBe(1);expect(gets).toBe(1);expect(statusQuery.get('input_digest')).toBe(body.input_digest);
  expect(statusQuery.get('scope_digest')).toBe(body.scope_digest);
});

test('missing original receipt remains held without another POST or absence confirmation',async({page})=>{
  let posts=0,gets=0;
  await setup(page,(route,url)=>{
    if(route.request().method()==='POST'){posts++;return route.abort('failed');}
    if(url.pathname.includes('/template-deletions/')){gets++;return json(route,{detail:'Unconfirmed'},404);}
    return json(route,[row()]);
  });
  await deleteButton(page).click();await page.getByRole('button',{name:'Check original deletion status',exact:true}).click();
  await expect.poll(()=>gets).toBe(1);
  await expect(page.getByRole('button',{name:'Check original deletion status',exact:true})).toBeEnabled();
  await expect(page.getByRole('alert')).toContainText('Earlier deletion is unconfirmed');
  await expect(deleteButton(page)).toBeDisabled();await expect(page.getByRole('button',{name:'Use',exact:true})).toBeDisabled();
  expect(posts).toBe(1);expect(gets).toBe(1);
});

test('202 exact body cannot confirm deletion or unlock another request',async({page})=>{
  let posts=0;
  await setup(page,(route)=>{
    if(route.request().method()==='POST'){posts++;return json(route,receipt(route.request().postDataJSON()),202);}
    return json(route,[row()]);
  });
  await deleteButton(page).click();await expect(page.getByRole('alert')).toContainText('Earlier deletion is unconfirmed');
  await expect(deleteButton(page)).toBeDisabled();expect(posts).toBe(1);
});

test('reload checks only the saved original deletion and preserves a replacement template',async({page})=>{
  let body,posts=0,checks=0,statusQuery;
  const replacement={...row(),name:'Replacement template',deletion_review:{...row().deletion_review,identity_digest:'e'.repeat(64)}};
  await setup(page,(route,url)=>{
    if(route.request().method()==='POST'){posts++;body=route.request().postDataJSON();return route.abort('failed');}
    if(url.pathname.includes('/template-deletions/')){checks++;statusQuery=url.searchParams;return json(route,receipt(body));}
    return json(route,checks?[replacement]:[row()]);
  });
  await deleteButton(page).click();await expect(page.getByRole('alert')).toContainText('Earlier deletion is unconfirmed');
  const raw=await page.evaluate(()=>sessionStorage.getItem('unravler.outreach.templateDeletionReferences.v1'));
  expect(JSON.parse(raw)).toEqual({contract_version:1,references:[{contract_version:1,workspace_id:context.workspace_id,
    scope_digest:context.scope_digest,request_id:body.request_id,input_digest:body.input_digest}]});
  expect(raw).not.toContain('Reviewed template');expect(raw).not.toContain('template_id');expect(raw).not.toContain('content_json');
  await page.reload();await page.getByRole('button',{name:'Browse winning templates',exact:true}).click();
  await expect(page.getByRole('button',{name:'Use',exact:true})).toBeDisabled();expect(posts).toBe(1);expect(checks).toBe(0);
  await page.getByRole('button',{name:'Check saved deletion status',exact:true}).click();
  await expect(page.getByRole('button',{name:'Delete template Replacement template',exact:true})).toBeEnabled();
  expect(posts).toBe(1);expect(checks).toBe(1);expect(statusQuery.get('input_digest')).toBe(body.input_digest);
  expect(statusQuery.get('scope_digest')).toBe(body.scope_digest);
  expect(await page.evaluate(()=>JSON.parse(sessionStorage.getItem('unravler.outreach.templateDeletionReferences.v1')).references)).toEqual([]);
});

test('write-ahead deletion locator with no POST remains held after reload and404',async({page})=>{
  let posts=0,checks=0;
  await setup(page,(route,url)=>{
    if(route.request().method()==='POST'){posts++;return route.abort('failed');}
    if(url.pathname.includes('/template-deletions/')){checks++;return json(route,{},404);}
    return json(route,[row()]);
  });
  const original={contract_version:1,workspace_id:context.workspace_id,scope_digest:context.scope_digest,
    request_id:'01234567-89ab-cdef-0123-456789abcdef',input_digest:'a'.repeat(64)};
  await page.evaluate(ref=>sessionStorage.setItem('unravler.outreach.templateDeletionReferences.v1',
    JSON.stringify({contract_version:1,references:[ref]})),original);
  await page.reload();await page.getByRole('button',{name:'Browse winning templates',exact:true}).click();
  await page.getByRole('button',{name:'Check saved deletion status',exact:true}).click();
  await expect.poll(()=>checks).toBe(1);await expect(page.getByRole('button',{name:'Check saved deletion status',exact:true})).toBeEnabled();
  await expect(deleteButton(page)).toBeDisabled();await expect(page.getByRole('button',{name:'Use',exact:true})).toBeDisabled();
  expect(posts).toBe(0);expect(checks).toBe(1);
  expect(await page.evaluate(()=>JSON.parse(sessionStorage.getItem('unravler.outreach.templateDeletionReferences.v1')).references)).toEqual([original]);
});
