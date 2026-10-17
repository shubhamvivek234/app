const {test,expect}=require('@playwright/test');
const node={id:'root',type:'visit_profile',title:'Original visit',delay_hours:5,config:{}};
const review={contract_version:1,reviewable:true,update_authorized:false,execution_authorized:false,
  workspace_id:'workspace',revision:0,review_digest:'a'.repeat(64),identity_digest:'b'.repeat(64),scope_digest:'c'.repeat(64)};
const row=()=>({id:'tpl_custom_012345abcd',is_custom:true,name:'Starter',nodes:[node],edges:[],tree:[node],graph_review:review,
  deletion_review:{...review,update_authorized:undefined,deletion_authorized:false,scope_digest:'f'.repeat(64)},
  compatibility:{contract_version:1,valid:true,configuration_available:true,execution_authorized:false}});
const json=(route,body,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
const receipt=body=>({...Object.fromEntries(Object.entries(body).filter(([key])=>key!=='graph_json')),
  status:'updated',template_id:row().id,new_revision:1,new_review_digest:'d'.repeat(64),graph_digest:'e'.repeat(64)});
async function setup(page,handler){
  await page.route('**/*',async route=>{
    const url=new URL(route.request().url());if(url.origin!=='http://127.0.0.1:4179')return route.abort();
    if(url.pathname==='/'||url.pathname==='/bundle.js')return route.continue();
    if(url.pathname.includes('/sequences/templates'))return handler(route);
    if(url.pathname.endsWith('sequence-capabilities'))return json(route,{capabilities:[]});
    return json(route,[]);
  });await page.goto('/?view=templates');await page.getByRole('button',{name:'Browse winning templates',exact:true}).click();
}
test('actual visual edit saves exact tree/nodes and refreshes deletion proof before another action',async({page})=>{
  let body,deletion,patches=0;const record=row();
  await setup(page,route=>{
    if(route.request().method()==='PATCH'){patches++;body=route.request().postDataJSON();return json(route,receipt(body));}
    if(route.request().method()==='DELETE'){
      deletion=route.request().postDataJSON();return json(route,{...deletion,status:'deleted',template_id:record.id});
    }
    return json(route,[patches?{...record,...JSON.parse(body.graph_json),graph_review:{...review,revision:1,review_digest:'d'.repeat(64)},
      deletion_review:{...record.deletion_review,revision:1,review_digest:'d'.repeat(64)}}:record]);
  });
  await page.getByRole('button',{name:'Edit template sequence Starter',exact:true}).click();
  await expect(page.getByRole('button',{name:'Use',exact:true})).toBeDisabled();
  await page.getByTitle('Edit delay',{exact:true}).click();await page.locator('input[type="number"]').fill('9');
  await page.getByTitle('Save delay',{exact:true}).click();
  await page.getByRole('button',{name:'Save template sequence',exact:true}).click();
  await expect(page.getByRole('button',{name:'Delete template Starter',exact:true})).toBeEnabled();
  const graph=JSON.parse(body.graph_json);expect(graph.nodes[0].delay_hours).toBe(9);expect(graph.tree[0].delay_hours).toBe(9);expect(patches).toBe(1);
  await page.getByRole('button',{name:'Delete template Starter',exact:true}).click();expect(deletion.revision).toBe(1);expect(deletion.review_digest).toBe('d'.repeat(64));
  await expect(page.getByText('No sequence templates are available.',{exact:true})).toBeVisible();
});
test('unknown graph update is inspected by GET without graph replay or implied confirmation',async({page})=>{
  let patches=0;
  await setup(page,route=>{
    if(route.request().method()==='PATCH'){patches++;return route.abort('failed');}
    return json(route,[patches?{...row(),graph_review:{...review,revision:1,review_digest:'d'.repeat(64)}}:row()]);
  });
  await page.getByRole('button',{name:'Edit template sequence Starter',exact:true}).click();
  await page.getByRole('button',{name:'Save template sequence',exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('Earlier sequence update is unconfirmed');
  await page.getByRole('button',{name:'Reload and review templates',exact:true}).click();
  await expect(page.getByText(/The earlier sequence update is unconfirmed/)).toBeVisible();expect(patches).toBe(1);
  await expect(page.getByRole('button',{name:'Edit template sequence Starter',exact:true})).toBeEnabled();
});
test('ordinary older catalog cannot enable graph editing without the dedicated review',async({page})=>{
  const record=row();delete record.graph_review;await setup(page,route=>json(route,[record]));
  await expect(page.getByRole('button',{name:'Edit template sequence Starter',exact:true})).toBeDisabled();
  await expect(page.getByRole('button',{name:'Use',exact:true})).toBeEnabled();
});
