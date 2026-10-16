const { test, expect } = require('@playwright/test');

const template = () => ({ id: 'custom-email', name: 'Email follow-up', description: 'Synthetic email starter',
  nodes: [{ id: 'email', type: 'send_email', delay_hours: 24, config: { subject: 'Hello', body: 'Hello {{first_name}}' } }],
  edges: [], tree: [{ id: 'email', type: 'send_email', delay_hours: 24, config: { subject: 'Hello', body: 'Hello {{first_name}}' } }],
  compatibility: { contract_version: 1, valid: true, configuration_available: true, execution_authorized: false } });

async function setup(page, catalog) {
  const writes = [];
  await page.route('**/*', async (route) => {
    const request=route.request(), url=new URL(request.url());
    if (url.origin !== 'http://127.0.0.1:4179') return route.abort();
    if (url.pathname === '/' || url.pathname === '/bundle.js') return route.continue();
    if (url.pathname.endsWith('/sequences/templates')) return catalog(route);
    if (request.method() === 'POST') writes.push({path:url.pathname,body:request.postDataJSON()});
    const body=url.pathname.endsWith('/auto-draft') ? {id:'synthetic-draft'} : [];
    return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body)});
  });
  await page.goto('/?view=templates');
  await page.getByRole('button',{name:'Browse winning templates',exact:true}).click();
  return writes;
}

test('supported email template copies the exact graph into a draft without launching', async ({page}) => {
  const row=template();
  const writes=await setup(page,(route)=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify([row])}));
  await expect(page.getByText('Ready to configure',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Use',exact:true}).click();
  await expect(page.locator('body')).toHaveAttribute('data-opened-draft','synthetic-draft');
  expect(writes.map((write)=>write.path)).toEqual(['/api/v1/outreach/campaigns/auto-draft','/api/v1/outreach/sequences']);
  expect(writes[1].body).toEqual({campaign_id:'synthetic-draft',nodes:row.nodes,edges:row.edges,tree:row.tree});
});

test('failed catalog has no starter fallback and can recover with explicit retry', async ({page}) => {
  let requests=0;
  const writes=await setup(page,(route)=>route.fulfill({status:++requests===1?503:200,contentType:'application/json',body:JSON.stringify(requests===1?{}:[template()])}));
  await expect(page.getByRole('alert')).toContainText('Could not load');
  await expect(page.getByRole('button',{name:'Use',exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:'Retry templates',exact:true}).click();
  await expect(page.getByRole('button',{name:'Use',exact:true})).toBeEnabled();
  expect(writes).toEqual([]);
});

test('claimed compatibility cannot substitute a missing visual graph', async ({page}) => {
  const row=template();delete row.tree;
  const writes=await setup(page,(route)=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify([row])}));
  await expect(page.getByRole('button',{name:'Unavailable',exact:true})).toBeDisabled();
  await expect(page.getByRole('cell').filter({hasText:'Graph needs review'})).toBeVisible();
  expect(writes).toEqual([]);
});
