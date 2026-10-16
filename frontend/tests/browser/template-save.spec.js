const { test, expect } = require('@playwright/test');
const { createHash } = require('node:crypto');
const context = { contract_version: 1, workspace_id: 'workspace', scope_digest: 'a'.repeat(64), execution_authorized: false };
const node = { id: 'root', type: 'visit_profile', delay_hours: 0, config: {} };
const receipt = (body) => ({ ...Object.fromEntries(['contract_version','workspace_id','scope_digest','request_id','input_digest'].map((key) => [key,body[key]])),
  status: 'saved', template_id: 'tpl_custom_012345abcd', template_revision: 1,
  template_identity_digest: 'b'.repeat(64), template_review_digest: 'c'.repeat(64) });

async function install(page, post, status) {
  const calls = []; let original;
  await page.route('**/*', async (route) => {
    const req = route.request(); const url = new URL(req.url());
    if (url.origin !== 'http://127.0.0.1:4179') return route.abort();
    if (url.pathname === '/' || url.pathname === '/bundle.js') return route.continue();
    if (url.pathname.endsWith('/template-saves/context')) return route.fulfill({ json: context });
    if (url.pathname.endsWith('/template-saves')) { original = req.postDataJSON(); calls.push(original); return post(route,original); }
    if (url.pathname.includes('/template-saves/')) return status(route,original);
    const data = url.pathname.includes('/auto-draft') ? { id: 'synthetic-campaign', name: 'Café template' }
      : url.pathname.endsWith('/sequences/synthetic-campaign') ? { nodes:[node], edges:[], tree:[node] }
      : url.pathname.endsWith('/accounts') ? []
      : url.pathname.endsWith('/preflight') ? { campaign_id:'synthetic-campaign',can_launch:false,blockers:['Fixture only'],checklist:[],summary:{},execution_checks:[] }
      : url.pathname.includes('/leads') ? { leads:[],total:0 } : {};
    return route.fulfill({ json:data });
  });
  await page.goto('/?view=wizard');
  await expect(page.getByRole('button',{name:'Save as template',exact:true})).toBeVisible();
  return calls;
}

test('real browser hashes frozen Unicode content and confirms exact historical creation', async ({ page }) => {
  const calls=await install(page,(route,body)=>route.fulfill({json:receipt(body)}));
  await page.getByRole('button',{name:'Save as template',exact:true}).click();
  await expect(page.getByRole('status')).toContainText('Original template save confirmed');
  expect(calls).toHaveLength(1);
  expect(calls[0].input_digest).toBe(createHash('sha256').update(calls[0].content_json,'utf8').digest('hex'));
  expect(calls[0].content_json).toContain('Café');
});

test('lost response recovers only through explicit original status GET', async ({ page }) => {
  const calls=await install(page,route=>route.abort(),(route,body)=>route.fulfill({json:receipt(body)}));
  await page.getByRole('button',{name:'Save as template',exact:true}).click();
  await expect(page.getByRole('status')).toContainText('unconfirmed');
  await expect(page.getByRole('button',{name:'Save as template',exact:true})).toBeDisabled();
  await page.getByRole('button',{name:'Check save status',exact:true}).click();
  await expect(page.getByRole('status')).toContainText('Original template save confirmed');
  expect(calls).toHaveLength(1);
});

test('missing status keeps the hold without silently creating another template', async ({ page }) => {
  const calls=await install(page,route=>route.abort(),route=>route.fulfill({status:404,json:{detail:'Unconfirmed'}}));
  await page.getByRole('button',{name:'Save as template',exact:true}).click();
  await page.getByRole('button',{name:'Check save status',exact:true}).click();
  await expect(page.getByRole('status')).toContainText('unconfirmed');
  await expect(page.getByRole('button',{name:'Save as template',exact:true})).toBeDisabled();
  expect(calls).toHaveLength(1);
});

test('reload retains only original references and status recovery never posts another graph',async({page})=>{
  const calls=await install(page,route=>route.abort(),(route,body)=>route.fulfill({json:receipt(body)}));
  await page.getByRole('button',{name:'Save as template',exact:true}).click();
  await expect(page.getByRole('status')).toContainText('unconfirmed');
  const stored=await page.evaluate(()=>sessionStorage.getItem('unravler.outreach.templateSaveReferences.v1'));
  expect(stored).not.toContain('Café');expect(stored).not.toContain('content_json');
  await page.reload();await expect(page.getByRole('button',{name:'Save as template',exact:true})).toBeDisabled();
  await page.getByRole('button',{name:'Check save status',exact:true}).click();
  await expect(page.getByRole('status')).toContainText('Original template save confirmed');expect(calls).toHaveLength(1);
});

test('reload with missing original status retains the hold and the same reference',async({page})=>{
  const calls=await install(page,route=>route.abort(),route=>route.fulfill({status:404,json:{detail:'Unconfirmed'}}));
  await page.getByRole('button',{name:'Save as template',exact:true}).click();
  await expect(page.getByRole('status')).toContainText('unconfirmed');await page.reload();
  await page.getByRole('button',{name:'Check save status',exact:true}).click();
  await expect(page.getByRole('button',{name:'Save as template',exact:true})).toBeDisabled();expect(calls).toHaveLength(1);
});
