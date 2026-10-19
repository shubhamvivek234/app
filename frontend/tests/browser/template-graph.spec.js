const {test,expect}=require('@playwright/test');
const {createHash}=require('crypto');
const row=()=>({id:'tpl_custom_012345abcd',is_custom:true,name:'Starter',description:'Original',
  workspace_access:{contract_version:1,workspace_id:'workspace',visibility:'workspace',created_by_you:false,
    can_configure:true,can_edit:true,can_delete:true,execution_authorized:false},
  nodes:[{id:'root',type:'visit_profile',title:'Original visit ☕',delay_hours:5,config:{}}],edges:[],tree:[{id:'root',type:'visit_profile',title:'Original visit ☕',delay_hours:5,config:{}}],
  compatibility:{contract_version:1,valid:true,configuration_available:true,execution_authorized:false},
  graph_review:{contract_version:1,reviewable:true,update_authorized:false,execution_authorized:false,
    workspace_id:'workspace',revision:0,review_digest:'a'.repeat(64),identity_digest:'b'.repeat(64),scope_digest:'c'.repeat(64)}});
const context={contract_version:1,workspace_id:'workspace',scope_digest:'f'.repeat(64),execution_authorized:false};
const json=(route,body,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
const receipt=body=>{const original=JSON.parse(body.content_json);return {contract_version:1,workspace_id:body.workspace_id,
  request_id:body.request_id,scope_digest:body.scope_digest,input_digest:body.input_digest,status:'updated',
  template_id:original.template_id,revision:original.revision,review_digest:original.review_digest,identity_digest:original.identity_digest,
  review_scope_digest:original.scope_digest,new_revision:1,new_review_digest:'d'.repeat(64),graph_digest:'e'.repeat(64)};};
async function setup(page,handler){
  await page.route('**/*',async route=>{
    const url=new URL(route.request().url());
    if(url.origin!=='http://127.0.0.1:4179')return route.abort();
    if(url.pathname==='/'||url.pathname==='/bundle.js')return route.continue();
    if(url.pathname.endsWith('/template-graph-updates/context'))return json(route,context);
    if(url.pathname.includes('/sequences/templates')||url.pathname.includes('/template-graph-updates'))return handler(route);
    return json(route,[]);
  });
  await page.goto('/?view=templates');await page.getByRole('button',{name:'Browse winning templates',exact:true}).click();
}
test('real canvas graph POST freezes exact Unicode operation and refreshes current gallery',async({page})=>{
  let posts=0,body;
  await setup(page,route=>{
    if(route.request().method()==='POST'){posts++;body=route.request().postDataJSON();return json(route,receipt(body));}
    return json(route,[posts?{...row(),name:'Renamed',description:''}:row()]);
  });
  await page.getByRole('button',{name:'Edit template sequence Starter',exact:true}).click();
  await expect(page.getByRole('button',{name:'Use',exact:true})).toBeDisabled();
  await page.locator('[title="Edit delay"]').click();
  await page.locator('input[type="number"]').fill('9');
  await page.locator('[title="Save delay"]').click();
  await page.getByRole('button',{name:'Save template sequence',exact:true}).click();
  await expect(page.getByRole('button',{name:'Edit template sequence Renamed',exact:true})).toBeVisible();
  const frozen=JSON.parse(body.content_json);
  expect(frozen).toMatchObject({contract_version:1,workspace_id:'workspace',revision:0,review_digest:'a'.repeat(64),
    identity_digest:'b'.repeat(64),scope_digest:'c'.repeat(64),template_id:row().id});
  expect(frozen.nodes[0].title).toBe('Original visit ☕');expect(frozen.tree[0].title).toBe('Original visit ☕');
  expect(frozen.nodes[0].delay_hours).toBe(9);expect(frozen.tree[0].delay_hours).toBe(9);
  expect(Object.keys(frozen).sort()).toEqual(['contract_version','workspace_id','revision','review_digest','identity_digest','scope_digest','template_id','nodes','edges','tree'].sort());
  expect(body.input_digest).toBe(createHash('sha256').update(body.content_json,'utf8').digest('hex'));
  expect(body.scope_digest).toBe(context.scope_digest);expect(posts).toBe(1);
});
test('lost response recovers the historical original update by GET while current details may differ',async({page})=>{
  let posts=0,checks=0,body;
  await setup(page,route=>{
    if(route.request().method()==='POST'){posts++;body=route.request().postDataJSON();return route.abort('failed');}
    if(route.request().url().includes('/template-graph-updates/')){checks++;return json(route,receipt(body));}
    return json(route,[checks?{...row(),name:'Later server edit'}:row()]);
  });
  await page.getByRole('button',{name:'Edit template sequence Starter',exact:true}).click();
  await page.getByRole('button',{name:'Save template sequence',exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('Earlier sequence update is unconfirmed');
  await page.getByRole('button',{name:'Check original sequence update status',exact:true}).click();
  await expect(page.getByRole('button',{name:'Edit template sequence Later server edit',exact:true})).toBeVisible();
  expect(posts).toBe(1);expect(checks).toBe(1);
});
test('missing original receipt remains held without POST replay or fresh update',async({page})=>{
  let posts=0,checks=0;
  await setup(page,route=>{
    if(route.request().method()==='POST'){posts++;return route.abort('failed');}
    if(route.request().url().includes('/template-graph-updates/')){checks++;return json(route,{},404);}
    return json(route,[row()]);
  });
  await page.getByRole('button',{name:'Edit template sequence Starter',exact:true}).click();
  await page.getByRole('button',{name:'Save template sequence',exact:true}).click();
  await page.getByRole('button',{name:'Check original sequence update status',exact:true}).click();
  await expect.poll(()=>checks).toBe(1);
  await expect(page.getByRole('button',{name:'Check original sequence update status',exact:true})).toBeEnabled();
  await expect(page.getByRole('button',{name:'Save template sequence',exact:true})).toBeDisabled();
  await expect(page.getByRole('button',{name:'Cancel',exact:true})).toBeDisabled();
  await expect(page.getByRole('button',{name:'Use',exact:true})).toBeDisabled();
  expect(posts).toBe(1);expect(checks).toBe(1);
});
test('older catalogs without dedicated review cannot enable details editing',async({page})=>{
  const record=row();delete record.graph_review;await setup(page,route=>json(route,[record]));
  await expect(page.getByRole('button',{name:'Edit template sequence Starter',exact:true})).toBeDisabled();
  await expect(page.getByRole('button',{name:'Use',exact:true})).toBeEnabled();
});

test('reload recovers only the original graph request while preserving a later template',async({page})=>{
  let posts=0,checks=0,body;
  await setup(page,route=>{
    if(route.request().method()==='POST'){posts++;body=route.request().postDataJSON();return route.abort('failed');}
    if(route.request().url().includes('/template-graph-updates/')){checks++;return json(route,receipt(body));}
    return json(route,[checks?{...row(),name:'Replacement'}:row()]);
  });
  await page.getByRole('button',{name:'Edit template sequence Starter',exact:true}).click();
  await page.getByRole('button',{name:'Save template sequence',exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('Earlier sequence update is unconfirmed');
  const raw=await page.evaluate(()=>sessionStorage.getItem('unravler.outreach.templateGraphReferences.v1'));
  expect(raw).not.toContain('nodes');expect(raw).not.toContain('Original visit');expect(JSON.parse(raw).references).toHaveLength(1);
  await page.reload();await page.getByRole('button',{name:'Browse winning templates',exact:true}).click();
  await expect(page.getByRole('button',{name:'Use',exact:true})).toBeDisabled();expect(posts).toBe(1);expect(checks).toBe(0);
  await page.getByRole('button',{name:'Check saved sequence update status',exact:true}).click();
  await expect(page.getByRole('button',{name:'Edit template sequence Replacement',exact:true})).toBeEnabled();
  expect(posts).toBe(1);expect(checks).toBe(1);
});

test('graph locator written without POST remains held after reload and404',async({page})=>{
  let posts=0,checks=0;await setup(page,route=>{
    if(route.request().method()==='POST'){posts++;return route.abort('failed');}
    if(route.request().url().includes('/template-graph-updates/')){checks++;return json(route,{},404);}
    return json(route,[row()]);
  });
  await page.evaluate(()=>sessionStorage.setItem('unravler.outreach.templateGraphReferences.v1',JSON.stringify({contract_version:1,
    references:[{contract_version:1,workspace_id:'workspace',scope_digest:'f'.repeat(64),
      request_id:'01234567-89ab-cdef-0123-456789abcdef',input_digest:'a'.repeat(64)}]})));
  await page.reload();await page.getByRole('button',{name:'Browse winning templates',exact:true}).click();
  await page.getByRole('button',{name:'Check saved sequence update status',exact:true}).click();
  await expect.poll(()=>checks).toBe(1);await expect(page.getByRole('button',{name:'Check saved sequence update status',exact:true})).toBeEnabled();
  await expect(page.getByRole('button',{name:'Use',exact:true})).toBeDisabled();expect(posts).toBe(0);expect(checks).toBe(1);
});
