const {test,expect}=require('@playwright/test');
const row=()=>({id:'tpl_custom_012345abcd',name:'Reviewed template',is_custom:true,
  nodes:[{id:'root',type:'visit_profile'}],edges:[],tree:[{id:'root',type:'visit_profile'}],
  compatibility:{contract_version:1,valid:true,configuration_available:true,execution_authorized:false},
  deletion_review:{contract_version:1,reviewable:true,revision:0,workspace_id:'workspace',
    identity_digest:'b'.repeat(64),review_digest:'a'.repeat(64),scope_digest:'c'.repeat(64),
    deletion_authorized:false,execution_authorized:false}});
const receipt=(record)=>({contract_version:1,status:'deleted',template_id:record.id,
  workspace_id:record.deletion_review.workspace_id,revision:record.deletion_review.revision,
  identity_digest:record.deletion_review.identity_digest,review_digest:record.deletion_review.review_digest,scope_digest:record.deletion_review.scope_digest});
async function setup(page,handler){
  await page.route('**/*',async(route)=>{
    const request=route.request(),url=new URL(request.url());
    if(url.origin!=='http://127.0.0.1:4179')return route.abort();
    if(url.pathname==='/'||url.pathname==='/bundle.js')return route.continue();
    if(url.pathname.includes('/sequences/templates'))return handler(route);
    return route.fulfill({status:200,contentType:'application/json',body:'[]'});
  });
  await page.goto('/?view=templates');
  await page.getByRole('button',{name:'Browse winning templates',exact:true}).click();
}
test('exact native deletion receipt removes only the reviewed template',async({page})=>{
  const record=row();let body,deleteUrl;
  await setup(page,(route)=>{
    if(route.request().method()==='DELETE'){
      body=route.request().postDataJSON();deleteUrl=route.request().url();return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(receipt(record))});
    }
    return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify([record])});
  });
  await page.getByRole('button',{name:'Delete template Reviewed template',exact:true}).click();
  await expect(page.getByText('No sequence templates are available.',{exact:true})).toBeVisible();
  expect(body).toEqual({contract_version:1,workspace_id:'workspace',revision:0,review_digest:'a'.repeat(64),identity_digest:'b'.repeat(64),scope_digest:'c'.repeat(64)});
  expect(deleteUrl).toBe('http://127.0.0.1:4179/api/v1/outreach/sequences/templates/tpl_custom_012345abcd/reviewed');
});
test('missing acknowledgement stays unconfirmed after catalog absence without replay',async({page})=>{
  let deletes=0;
  await setup(page,(route)=>{
    if(route.request().method()==='DELETE'){
      deletes++;return route.abort('failed');
    }
    return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(deletes?[]:[row()])});
  });
  await page.getByRole('button',{name:'Delete template Reviewed template',exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('Earlier deletion is unconfirmed');
  await page.getByRole('button',{name:'Reload and review templates',exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('A refreshed catalog is not a deletion receipt');
  await expect(page.getByText('No sequence templates are available.',{exact:true})).toBeVisible();
  expect(deletes).toBe(1);
});
test('202 with exact body cannot confirm deletion',async({page})=>{
  const record=row();let deletes=0;
  await setup(page,(route)=>{
    if(route.request().method()==='DELETE'){
      deletes++;return route.fulfill({status:202,contentType:'application/json',body:JSON.stringify(receipt(record))});
    }
    return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify([record])});
  });
  await page.getByRole('button',{name:'Delete template Reviewed template',exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('Earlier deletion is unconfirmed');
  await expect(page.getByRole('button',{name:'Delete template Reviewed template',exact:true})).toBeDisabled();
  await expect(page.getByText('Reviewed template',{exact:true})).toBeVisible();
  expect(deletes).toBe(1);
});
