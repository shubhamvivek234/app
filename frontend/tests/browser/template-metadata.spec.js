const {test,expect}=require('@playwright/test');
const {createHash}=require('crypto');
const row=()=>({id:'tpl_custom_012345abcd',is_custom:true,name:'Starter',description:'Original',
  nodes:[{id:'root',type:'visit_profile'}],edges:[],tree:[{id:'root',type:'visit_profile'}],
  compatibility:{contract_version:1,valid:true,configuration_available:true,execution_authorized:false},
  metadata_review:{contract_version:1,reviewable:true,update_authorized:false,execution_authorized:false,
    workspace_id:'workspace',revision:0,review_digest:'a'.repeat(64),identity_digest:'b'.repeat(64),scope_digest:'c'.repeat(64)}});
const context={contract_version:1,workspace_id:'workspace',scope_digest:'f'.repeat(64),execution_authorized:false};
const json=(route,body,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
const receipt=body=>{const original=JSON.parse(body.content_json);return {contract_version:1,workspace_id:body.workspace_id,
  request_id:body.request_id,scope_digest:body.scope_digest,input_digest:body.input_digest,status:'updated',
  template_id:original.template_id,revision:original.revision,review_digest:original.review_digest,identity_digest:original.identity_digest,
  review_scope_digest:original.scope_digest,new_revision:1,new_review_digest:'d'.repeat(64)};};
async function setup(page,handler){
  await page.route('**/*',async route=>{
    const url=new URL(route.request().url());
    if(url.origin!=='http://127.0.0.1:4179')return route.abort();
    if(url.pathname==='/'||url.pathname==='/bundle.js')return route.continue();
    if(url.pathname.endsWith('/template-metadata-updates/context'))return json(route,context);
    if(url.pathname.includes('/sequences/templates')||url.pathname.includes('/template-metadata-updates'))return handler(route);
    return json(route,[]);
  });
  await page.goto('/?view=templates');await page.getByRole('button',{name:'Browse winning templates',exact:true}).click();
}
test('reviewed details POST freezes exact input and refreshes current gallery',async({page})=>{
  let posts=0,body;
  await setup(page,route=>{
    if(route.request().method()==='POST'){posts++;body=route.request().postDataJSON();return json(route,receipt(body));}
    return json(route,[posts?{...row(),name:'Renamed',description:''}:row()]);
  });
  await page.getByRole('button',{name:'Edit template details Starter',exact:true}).click();
  await expect(page.getByRole('button',{name:'Use',exact:true})).toBeDisabled();
  await page.getByLabel('Template name',{exact:true}).fill('Renamed');
  await page.getByLabel('Template description',{exact:true}).fill('');
  await page.getByRole('button',{name:'Save details',exact:true}).click();
  await expect(page.getByRole('button',{name:'Edit template details Renamed',exact:true})).toBeVisible();
  expect(JSON.parse(body.content_json)).toEqual({contract_version:1,workspace_id:'workspace',revision:0,review_digest:'a'.repeat(64),
    identity_digest:'b'.repeat(64),scope_digest:'c'.repeat(64),template_id:row().id,name:'Renamed',description:''});
  expect(body.input_digest).toBe(createHash('sha256').update(body.content_json,'utf8').digest('hex'));
  expect(body.scope_digest).toBe(context.scope_digest);expect(posts).toBe(1);
});
test('lost response recovers the historical original update by GET while current details may differ',async({page})=>{
  let posts=0,checks=0,body;
  await setup(page,route=>{
    if(route.request().method()==='POST'){posts++;body=route.request().postDataJSON();return route.abort('failed');}
    if(route.request().url().includes('/template-metadata-updates/')){checks++;return json(route,receipt(body));}
    return json(route,[checks?{...row(),name:'Later server edit'}:row()]);
  });
  await page.getByRole('button',{name:'Edit template details Starter',exact:true}).click();
  await page.getByRole('button',{name:'Save details',exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('Earlier update is unconfirmed');
  await page.getByRole('button',{name:'Check original update status',exact:true}).click();
  await expect(page.getByRole('button',{name:'Edit template details Later server edit',exact:true})).toBeVisible();
  expect(posts).toBe(1);expect(checks).toBe(1);
});
test('missing original receipt remains held without POST replay or fresh update',async({page})=>{
  let posts=0,checks=0;
  await setup(page,route=>{
    if(route.request().method()==='POST'){posts++;return route.abort('failed');}
    if(route.request().url().includes('/template-metadata-updates/')){checks++;return json(route,{},404);}
    return json(route,[row()]);
  });
  await page.getByRole('button',{name:'Edit template details Starter',exact:true}).click();
  await page.getByRole('button',{name:'Save details',exact:true}).click();
  await page.getByRole('button',{name:'Check original update status',exact:true}).click();
  await expect(page.getByRole('button',{name:'Save details',exact:true})).toBeDisabled();
  await expect(page.getByRole('button',{name:'Cancel',exact:true})).toBeDisabled();
  await expect(page.getByRole('button',{name:'Use',exact:true})).toBeDisabled();
  expect(posts).toBe(1);expect(checks).toBe(1);
});
test('older catalogs without dedicated review cannot enable details editing',async({page})=>{
  const record=row();delete record.metadata_review;await setup(page,route=>json(route,[record]));
  await expect(page.getByRole('button',{name:'Edit template details Starter',exact:true})).toBeDisabled();
  await expect(page.getByRole('button',{name:'Use',exact:true})).toBeEnabled();
});
