import { PREBUILT_TEMPLATES, isLaunchableTemplate } from './OutreachCampaigns';
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import OutreachCampaigns from './OutreachCampaigns';

jest.mock('sonner', () => ({ toast: { success: jest.fn(), error: jest.fn() } }));

describe('Campaign template readiness', () => {
  it('allows runner-supported templates and blocks unsupported InMail steps', () => {
    expect(isLaunchableTemplate(ready(PREBUILT_TEMPLATES.find((template) => template.id === 'tpl_connect_and_follow_up')))).toBe(true);
    expect(isLaunchableTemplate(PREBUILT_TEMPLATES.find((template) => template.id === 'tpl_multitouch_inmail'))).toBe(false);
  });

  it('does not claim invented conversion metrics for starter templates', () => {
    expect(PREBUILT_TEMPLATES.every((template) => !template.acceptance && !template.reply && !template.uses)).toBe(true);
  });
});

describe('Campaign list availability', () => {
  it('shows an API failure with retry instead of an empty campaign list', async () => {
    global.IS_REACT_ACT_ENVIRONMENT = true;
    const container = document.createElement('div');
    document.body.appendChild(container);
    const root = createRoot(container);
    global.fetch = jest.fn()
      .mockResolvedValueOnce({ ok: false, json: async () => ({ detail: 'Campaign service unavailable' }) })
      .mockResolvedValueOnce({ ok: true, json: async () => [{ id: 'campaign-a', name: 'Recovered', status: 'draft' }] });
    try {
      await act(async () => root.render(<OutreachCampaigns onOpenWizard={() => {}} />));
      expect(container.textContent).toContain('Campaign service unavailable');
      const retry = [...container.querySelectorAll('button')].find((button) => button.textContent.includes('Retry'));
      await act(async () => retry.click());
      expect(container.textContent).toContain('Recovered');
    } finally {
      await act(async () => root.unmount());
      container.remove();
      delete global.fetch;
    }
  });
});

it('does not treat failed or unknown server template compatibility as ready', () => {
  const template=PREBUILT_TEMPLATES.find((item) => item.id === 'tpl_connect_and_follow_up');
  expect(isLaunchableTemplate(template)).toBe(false);
  expect(isLaunchableTemplate({...template,compatibility:{contract_version:1,valid:false}})).toBe(false);
  expect(isLaunchableTemplate({...template,compatibility:{contract_version:2,valid:true}})).toBe(false);
  expect(isLaunchableTemplate(ready(template))).toBe(true);
});

const ready = (template) => ({ ...template, workspace_access:{contract_version:1,workspace_id:'workspace',
  visibility:template.is_custom === true ? 'workspace' : 'builtin',created_by_you:false,can_configure:true,
  can_edit:template.is_custom === true,can_delete:template.is_custom === true,execution_authorized:false}, compatibility: { contract_version: 1, valid: true,
  configuration_available: true, execution_authorized: false } });

it.each(['send_email', 'find_email', 'if_email_available', 'has_data_in_column'])('allows server-reviewed %s templates for configuration', (type) => {
  expect(isLaunchableTemplate(ready({nodes: [{id:'a',type}],edges:[],tree:[{id:'a',type}]}))).toBe(true);
});

it.each([
  {compatibility: null}, {compatibility: {contract_version:1,valid:true}},
  {compatibility: {contract_version:1,valid:true,configuration_available:true,execution_authorized:true}},
  {tree: null}, {tree: []}, {edges: null}, {nodes: []},
  {nodes: [null]}, {tree: [{}]}, {tree:[{id:'hidden',type:'send_email',steps:[{id:'child',type:'send_email'}]}]},
])('rejects incomplete or authority-claiming template data %#', (change) => {
  expect(isLaunchableTemplate({...ready(PREBUILT_TEMPLATES[0]),...change})).toBe(false);
});

describe('Server-reviewed gallery selection', () => {
  let container, root, opened;
  const response = (data, ok = true) => ({ok, json: async () => data});
  const button = (text) => [...container.querySelectorAll('button')].find((item) => item.textContent.trim() === text);
  const email = () => ready({id: 'email', name: 'Email template', nodes: [{id:'root',type:'send_email',config:{subject:'Hi',body:'Hello'}}],
    edges: [], tree: [{id:'root',type:'send_email',config:{subject:'Hi',body:'Hello'}}]});
  const open = async () => {
    await act(async () => root.render(<OutreachCampaigns onOpenWizard={opened} />));
    await act(async () => button('Browse winning templates').click());
  };
  beforeEach(() => {
    global.IS_REACT_ACT_ENVIRONMENT = true;
    container = document.createElement('div'); document.body.appendChild(container);
    root = createRoot(container); opened = jest.fn();
  });
  afterEach(async () => {
    await act(async () => root.unmount()); container.remove(); delete global.fetch;
  });

  it('shows no selectable fallback while loading and after failure; explicit retry recovers', async () => {
    let resolve;
    global.fetch = jest.fn().mockResolvedValueOnce(response([]))
      .mockImplementationOnce(() => new Promise((done) => {resolve=done;}))
      .mockResolvedValueOnce(response([email()]));
    await open();
    expect(container.textContent).toContain('Loading templates');
    expect(button('Use')).toBeUndefined();
    await act(async () => resolve(response({}, false)));
    expect(container.querySelector('[role="alert"]')).not.toBeNull();
    expect(container.textContent).not.toContain('Connect and follow up');
    await act(async () => button('Retry templates').click());
    expect(container.textContent).toContain('Email template');
    expect(button('Use').disabled).toBe(false);
  });

  it.each([[], {}, [{id:'a',name:{bad:true}}], [email(),email()]])('holds empty or malformed catalog without substituting starters %#', async (data) => {
    global.fetch = jest.fn().mockResolvedValueOnce(response([])).mockResolvedValueOnce(response(data));
    await open();
    expect(button('Use')).toBeUndefined();
    expect(container.textContent).not.toContain('Connect and follow up');
    expect(container.textContent).toMatch(/No sequence templates|needs review/);
  });

  it('does not replace missing graph data by an identically named local template', async () => {
    const original = PREBUILT_TEMPLATES[0];
    global.fetch = jest.fn().mockResolvedValueOnce(response([]))
      .mockResolvedValueOnce(response([{id:original.id,name:original.name,compatibility:ready({}).compatibility}]));
    await open();
    expect(button('Unavailable').disabled).toBe(true);
    expect(global.fetch).toHaveBeenCalledTimes(2);
  });

  it('copies the received email graph exactly into a draft and prevents overlapping Use', async () => {
    const row=email(); let resolveDraft;
    global.fetch = jest.fn().mockResolvedValueOnce(response([])).mockResolvedValueOnce(response([row]))
      .mockImplementationOnce(() => new Promise((done) => {resolveDraft=done;}))
      .mockResolvedValueOnce(response({status:'success'}));
    await open();
    await act(async () => {button('Use').click();button('Use').click();});
    expect(global.fetch).toHaveBeenCalledTimes(3);
    expect(button('Creating draft…').disabled).toBe(true);
    await act(async () => resolveDraft(response({id:'saved-draft'})));
    const save = global.fetch.mock.calls.find(([url]) => url === '/api/v1/outreach/sequences');
    expect(JSON.parse(save[1].body)).toEqual({campaign_id:'saved-draft',nodes:row.nodes,edges:row.edges,tree:row.tree});
    expect(opened).toHaveBeenCalledWith('saved-draft',2,row.name);
    expect(global.fetch.mock.calls.some(([url]) => url.includes('/launch'))).toBe(false);
  });

  it('ignores late catalog responses after closing and reopening', async () => {
    let resolveOld;
    global.fetch = jest.fn().mockResolvedValueOnce(response([]))
      .mockImplementationOnce(() => new Promise((done) => {resolveOld=done;}))
      .mockResolvedValueOnce(response([email()]));
    await open();
    await act(async () => button('← Campaigns').click());
    await act(async () => button('Browse winning templates').click());
    await act(async () => resolveOld(response([ready({...email(),id:'old',name:'Old response'})])));
    expect(container.textContent).toContain('Email template');
    expect(container.textContent).not.toContain('Old response');
    expect(button('Use').disabled).toBe(false);
  });

  it('stops dependent transport and navigation when unmounted during draft creation', async () => {
    let resolveDraft;
    global.fetch = jest.fn().mockResolvedValueOnce(response([])).mockResolvedValueOnce(response([email()]))
      .mockImplementationOnce(() => new Promise((done) => {resolveDraft=done;}));
    await open();
    await act(async () => button('Use').click());
    await act(async () => root.unmount());
    root=createRoot(container);
    await act(async () => resolveDraft(response({id:'saved-before-unmount'})));
    expect(global.fetch).toHaveBeenCalledTimes(3);
    expect(opened).not.toHaveBeenCalled();
  });

  it('handles row menu actions Resume draft, Edit sequence, Duplicate, and View details', async () => {
    const draft = {
      id: 'camp-draft-1',
      workspace_id: 'ws-1',
      name: 'Connect and follow up',
      status: 'draft',
      draft_step: 2,
      draft_progress: 60,
    };
    const cloned = { ...draft, id: 'camp-draft-copy', name: 'Connect and follow up (Copy)' };
    global.fetch = jest.fn((url, opts) => {
      if (url.endsWith('/duplicate') && opts?.method === 'POST') {
        return Promise.resolve(response(cloned));
      }
      if (url.endsWith('/camp-draft-1')) {
        return Promise.resolve(response(draft));
      }
      return Promise.resolve(response([draft]));
    });
    const onSelectCampaign = jest.fn();
    await act(async () => root.render(<OutreachCampaigns onOpenWizard={opened} onSelectCampaign={onSelectCampaign} />));

    const openRowMenu = async () => {
      const row = container.querySelector('tbody tr');
      const menuBtn = row.querySelector('td:last-child button');
      await act(async () => menuBtn.click());
    };

    // 1. Resume draft from row menu passes id, draft_step, and name
    await openRowMenu();
    const resumeMenuBtn = [...container.querySelectorAll('tbody tr td:last-child button')].find((b) => b.textContent.includes('Resume draft'));
    await act(async () => resumeMenuBtn.click());
    expect(opened).toHaveBeenCalledWith('camp-draft-1', 2, 'Connect and follow up');

    // 2. Edit sequence from row menu passes id, step 2, and name
    opened.mockClear();
    await openRowMenu();
    const editSeqBtn = [...container.querySelectorAll('tbody tr td:last-child button')].find((b) => b.textContent.includes('Edit sequence'));
    await act(async () => editSeqBtn.click());
    expect(opened).toHaveBeenCalledWith('camp-draft-1', 2, 'Connect and follow up');

    // 3. View details from row menu selects campaign
    await openRowMenu();
    const viewDetailsBtn = [...container.querySelectorAll('tbody tr td:last-child button')].find((b) => b.textContent.includes('View details'));
    await act(async () => viewDetailsBtn.click());
    expect(onSelectCampaign).toHaveBeenCalledWith('camp-draft-1');

    // 4. Duplicate from row menu posts to /duplicate
    await openRowMenu();
    const duplicateBtn = [...container.querySelectorAll('tbody tr td:last-child button')].find((b) => b.textContent.includes('Duplicate'));
    await act(async () => duplicateBtn.click());
    expect(global.fetch.mock.calls.some(([url, opts]) => url.endsWith('/camp-draft-1/duplicate') && opts?.method === 'POST')).toBe(true);
  });

  it('filters campaigns across All, Sending, Warming up, Paused, and Draft submenus', async () => {
    const sampleCampaigns = [
      { id: 'c-active', name: 'Active Outbound', status: 'active', leads_count: 25, leads_contacted: 10 },
      { id: 'c-warm', name: 'Warmup Cohort', status: 'warming_up', leads_count: 15, auto_launch_missing_count: 3 },
      { id: 'c-paused', name: 'Paused Outreach', status: 'paused', leads_count: 40 },
      { id: 'c-draft', name: 'Draft Sequence', status: 'draft', draft_step: 2, draft_progress: 60 },
    ];
    global.fetch = jest.fn(() => Promise.resolve(response(sampleCampaigns)));
    await act(async () => root.render(<OutreachCampaigns onOpenWizard={opened} />));

    const clickTab = async (labelPrefix) => {
      const tab = [...container.querySelectorAll('button')].find((b) => b.textContent.trim().startsWith(labelPrefix));
      expect(tab).toBeTruthy();
      await act(async () => tab.click());
    };

    // All tab shows all 4 campaigns and draft banner
    expect(container.textContent).toContain('Active Outbound');
    expect(container.textContent).toContain('Warmup Cohort');
    expect(container.textContent).toContain('Paused Outreach');
    expect(container.textContent).toContain('Your draft: Draft Sequence');

    // Sending tab
    await clickTab('Sending');
    expect(container.textContent).toContain('Active Outbound');
    expect(container.textContent).not.toContain('Paused Outreach');
    expect(container.textContent).not.toContain('Your draft: Draft Sequence');

    // Warming up tab
    await clickTab('Warming up');
    expect(container.textContent).toContain('Warmup Cohort');
    expect(container.textContent).toContain('3 awaiting warmup');
    expect(container.textContent).not.toContain('Active Outbound');

    // Paused tab
    await clickTab('Paused');
    expect(container.textContent).toContain('Paused Outreach');
    expect(container.textContent).not.toContain('Warmup Cohort');

    // Draft tab
    await clickTab('Draft');
    expect(container.textContent).toContain('Draft Sequence');
    expect(container.textContent).toContain('Your draft: Draft Sequence');
    expect(container.textContent).not.toContain('Active Outbound');
  });

  it('supports Dripify Active only checkbox, Overview progress bar, Email metrics, and inline pause/resume status switch', async () => {
    const sampleCampaigns = [
      {
        id: 'c-live',
        name: 'Enterprise ABM',
        status: 'active',
        leads_count: 100,
        leads_contacted: 45,
        acceptances_count: 18,
        replies_count: 7,
        emails_delivered: 12,
        emails_replied: 4,
      },
      {
        id: 'c-paused',
        name: 'Legacy Cohort',
        status: 'paused',
        leads_count: 50,
        leads_contacted: 10,
      },
    ];
    global.fetch = jest.fn((url, opts) => {
      if (url.endsWith('/c-live/pause') && opts?.method === 'POST') {
        return Promise.resolve(response({ status: 'paused' }));
      }
      return Promise.resolve(response(sampleCampaigns));
    });

    await act(async () => root.render(<OutreachCampaigns onOpenWizard={opened} />));

    // Overview progress bar and Email metrics rendered
    expect(container.querySelector('[data-testid="campaign-overview-progress-c-live"]')).toBeTruthy();
    expect(container.textContent).toContain('Enterprise ABM');
    expect(container.textContent).toContain('Legacy Cohort');

    // Active only checkbox filters out paused campaign
    const activeOnlyCheckbox = container.querySelector('[data-testid="active-only-checkbox"]');
    expect(activeOnlyCheckbox).toBeTruthy();
    await act(async () => activeOnlyCheckbox.click());
    expect(container.textContent).toContain('Enterprise ABM');
    expect(container.textContent).not.toContain('Legacy Cohort');

    // Inline status toggle switch pauses active campaign
    const toggleSwitch = container.querySelector('[data-testid="campaign-status-toggle-c-live"]');
    expect(toggleSwitch).toBeTruthy();
    await act(async () => toggleSwitch.click());
    expect(global.fetch.mock.calls.some(([url, opts]) => url.endsWith('/c-live/pause') && opts?.method === 'POST')).toBe(true);
  });
});
