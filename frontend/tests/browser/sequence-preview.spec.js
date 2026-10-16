const { test, expect } = require('@playwright/test');
const TREE = [{ id: 'check', type: 'if_connected', title: 'Connection check', config: {}, branches: { right: { condition: 'connected', steps: [{ id: 'next', type: 'visit_profile', title: 'Visit', delay_days: 1, config: {} }] } } }];
const SCOPE = 'c'.repeat(64);
async function setup(page, preview, tree = TREE) {
  page.on('pageerror', (error) => { throw error; });
  await page.route('**/api/v1/outreach/**', async (route) => {
    const path = new URL(route.request().url()).pathname;
    let body;
    if (path.endsWith('/sequences/preview')) return preview(route, route.request().postDataJSON());
    if (path.endsWith('/sequences/preview-context')) body = { contract_version: 1, request_scope: SCOPE };
    else if (path.endsWith('/sequence-capabilities')) body = { capabilities: ['visit_profile', 'if_connected'].map((type) => ({ type, supported: true, builder_available: true, live_enabled: false, reason: 'Live actions disabled' })) };
    else if (path.endsWith('/node-counts')) body = { node_counts: {}, execution_state_counts: {}, total_leads: 0 };
    else if (path.includes('/sequences/preview-campaign')) body = { tree };
    else if (path.endsWith('/sequences')) body = { status: 'success' };
    else throw new Error(`Unexpected API ${path}`);
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
  });
  await page.goto('/?view=sequence');
  await expect(page.getByText('Connection check', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Validate & preview sequence', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Validate & preview path', exact: true })).toBeEnabled();
}
function result(request, known = false) {
  return { request_id: request.request_id, request_scope: SCOPE, contract_version: 1, valid: true, execution_authorized: false, provider_outcomes_verified: false,
    input_digest: 'a'.repeat(64), graph_digest: 'b'.repeat(64), issues: [], ending: known ? 'finished' : 'waiting_for_observation', configured_delay_hours: known ? 24 : 0, assumed_wait_hours: 0,
    steps: known ? [{ node_id: 'check', type: 'if_connected', status: 'assumed_branch', branch: 'positive', assumed_observation: 'yes', configured_delay_hours: 0 }, { node_id: 'next', type: 'visit_profile', status: 'would_attempt', assumed_completion: true, configured_delay_hours: 24 }]
      : [{ node_id: 'check', type: 'if_connected', status: 'waiting_for_observation', assumed_observation: 'unknown', configured_delay_hours: 0 }] };
}

test('actual sequence canvas keeps unknown observations held and only illustrates explicitly assumed continuation', async ({ page }) => {
  let calls = 0;
  await setup(page, async (route, request) => {
    ++calls; expect(request.request_scope).toBe(SCOPE); expect(request.tree).toEqual(TREE);
    expect(request.nodes.find((node) => node.id === 'next').delay_hours).toBe(24);
    const known = request.observations.check === 'yes' && request.assume_action_completion;
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(result(request, known)) });
  });
  await page.getByRole('button', { name: 'Validate & preview path', exact: true }).click();
  await expect(page.getByText('Waiting for an observation', { exact: true }).last()).toBeVisible();
  await page.getByLabel('Assumed observation check').selectOption('yes');
  await page.getByLabel('Assume successful action completion').check();
  await page.getByRole('button', { name: 'Validate & preview path', exact: true }).click();
  await expect(page.getByText('Illustrated path ends here', { exact: true })).toBeVisible();
  await expect(page.getByText('Configured delay: 24 hours', { exact: true })).toBeVisible();
  await expect(page.getByText('Successful completion is assumed for this illustration.', { exact: true })).toBeVisible();
  expect(calls).toBe(2);
});

test('actual preview clears prior validity after editing and does not turn an unavailable response into success', async ({ page }) => {
  let calls = 0;
  await setup(page, async (route, request) => {
    if (++calls === 1) await route.fulfill({ contentType: 'application/json', body: JSON.stringify(result(request)) });
    else await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'Preview unavailable' }) });
  });
  await page.getByRole('button', { name: 'Validate & preview path', exact: true }).click();
  await expect(page.getByText('Graph checks passed; execution is not authorized', { exact: true })).toBeVisible();
  await page.getByLabel('Sequence sample first_name').fill('Changed');
  await expect(page.getByText('Graph checks passed; execution is not authorized', { exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: 'Validate & preview path', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Preview unavailable');
  await expect(page.getByLabel('Sequence preview result')).toHaveCount(0);
});

for (const fault of ['missing', 'hidden']) {
  test(`actual sequence editor holds a ${fault} visual tree without replacing the saved graph`, async ({ page }) => {
    let mutations=0;
    await page.route('**/api/v1/outreach/**',async (route)=>{
      const path=new URL(route.request().url()).pathname;
      if(route.request().method()!=='GET')++mutations;
      const body=path.endsWith('/sequences/preview-campaign')
        ? {tree:fault==='missing'?null:[{id:'one',type:'visit_profile',steps:[{id:'hidden',type:'visit_profile'}]}]}
        : path.endsWith('/sequence-capabilities')?{capabilities:[]}:{};
      await route.fulfill({contentType:'application/json',body:JSON.stringify(body)});
    });
    await page.goto('/?view=sequence');
    await expect(page.getByRole('alert')).toContainText(fault==='missing'?'no faithful visual tree':'not displayed');
    await expect(page.getByRole('button',{name:'Validate & preview sequence',exact:true})).toHaveCount(0);
    expect(mutations).toBe(0);
  });
}

test('actual editor cannot preview its local default while an existing sequence is loading',async ({page})=>{
  let release;
  const held=new Promise((resolve)=>{release=resolve;});
  await page.route('**/api/v1/outreach/**',async(route)=>{
    const path=new URL(route.request().url()).pathname;
    if(path.endsWith('/sequences/preview-campaign')){await held;await route.fulfill({contentType:'application/json',body:JSON.stringify({tree:TREE})});}
    else await route.fulfill({contentType:'application/json',body:JSON.stringify(path.endsWith('/sequence-capabilities')?{capabilities:[]}:{})});
  });
  await page.goto('/?view=sequence');
  await expect(page.getByRole('button',{name:'Validate & preview sequence',exact:true})).toBeDisabled();
  release();
  await expect(page.getByRole('button',{name:'Validate & preview sequence',exact:true})).toBeEnabled();
  await expect(page.getByText('No path saved; this outcome ends here.',{exact:true})).toBeVisible();
});

test('hour-only saved timing displays and edits exactly without inventing an absent branch',async({page})=>{
  const tree=JSON.parse(JSON.stringify(TREE));
  delete tree[0].branches.right.steps[0].delay_days;
  tree[0].branches.right.steps[0].delay_hours=24;
  let sent;
  await setup(page,async(route,request)=>{sent=request;await route.fulfill({contentType:'application/json',body:JSON.stringify(result(request,true))});},tree);
  await page.getByRole('button',{name:'Close sequence preview'}).click();
  await expect(page.getByText('Wait 1 day, then',{exact:true})).toBeVisible();
  await page.getByTitle('Edit delay',{exact:true}).last().click();
  await page.getByRole('spinbutton').fill('2');
  await page.getByTitle('Save delay',{exact:true}).click();
  await expect(page.getByText('Wait 2 days, then',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Validate & preview sequence',exact:true}).click();
  await page.getByRole('button',{name:'Validate & preview path',exact:true}).click();
  await expect(page.getByText('Graph checks passed; execution is not authorized',{exact:true})).toBeVisible();
  expect(sent.nodes.find((node)=>node.id==='next').delay_hours).toBe(48);
  expect(sent.tree[0].branches.left).toBeUndefined();
  expect(sent.tree[0].branches.right.steps[0].delay_days).toBeUndefined();
  expect(sent.tree[0].branches.right.steps[0].delay_hours).toBe(48);
});

for (const oneSided of [false, true]) {
  test(`stored-field editor preserves reversed branch meaning and typed decimal samples (${oneSided})`, async ({ page }) => {
    const tree = [{ id: 'check', type: 'has_data_in_column', title: 'Stored field check', config: { condition_contract_version: 1, field: 'custom_variables.score', operator: 'equals', value_type: 'number', value: 1 }, branches: { right: { condition: 'No', steps: [{ id: 'no', type: 'visit_profile', title: 'No path' }] }, ...(oneSided ? {} : { left: { condition: 'Yes', steps: [{ id: 'yes', type: 'visit_profile', title: 'Yes path' }] } }) } }];
    let sent;
    await page.route('**/api/v1/outreach/**', async (route) => {
      const path = new URL(route.request().url()).pathname;
      let body = {};
      if (path.endsWith('/sequence-capabilities')) body = { capabilities: ['has_data_in_column','visit_profile'].map((type) => ({type, supported: true, builder_available: true, live_enabled: false})) };
      else if (path.endsWith('/sequences/preview-context')) body = {contract_version:1, request_scope:SCOPE};
      else if (path.endsWith('/sequences/preview-campaign')) body = {tree};
      else if (path.endsWith('/sequences/preview')) { sent = route.request().postDataJSON(); body = {...result(sent), steps:[{node_id:'check',type:'has_data_in_column',status:'evaluated_branch',branch:'positive',configured_delay_hours:0}],ending:'finished'}; }
      await route.fulfill({contentType:'application/json',body:JSON.stringify(body)});
    });
    await page.goto('/?view=sequence');
    await page.getByText('Stored field check',{exact:true}).click();
    const target = page.getByLabel('Condition comparison value');
    await target.fill(''); await target.pressSequentially('1.5');
    await expect(target).toHaveValue('1.5');
    await page.getByRole('button',{name:'Done',exact:true}).click();
    await page.getByRole('button',{name:'Validate & preview sequence',exact:true}).click();
    await expect(page.getByLabel('Assumed observation check')).toHaveCount(0);
    await page.getByLabel('Condition sample type custom_variables.score').selectOption('number');
    const sample = page.getByLabel('Condition sample value custom_variables.score');
    await sample.fill('1e');
    await page.getByRole('button',{name:'Validate & preview path',exact:true}).click();
    await expect(page.getByRole('alert')).toContainText('Enter complete, finite');
    expect(sent).toBeUndefined();
    await sample.fill(''); await sample.pressSequentially('1.5'); await expect(sample).toHaveValue('1.5');
    await page.getByRole('button',{name:'Validate & preview path',exact:true}).click();
    await expect(page.getByText('Branch from supplied field value',{exact:false})).toBeVisible();
    expect(sent.nodes[0].config.value).toBe(1.5);
    expect(sent.condition_values.custom_variables.score).toBe(1.5);
    expect(sent.tree[0].branches.right.condition).toBe('No');
    if (!oneSided) expect(sent.tree[0].branches.left.condition).toBe('Yes');
    expect(sent.edges.find((edge) => edge.target === 'no').label).toBe('No');
  });
}
