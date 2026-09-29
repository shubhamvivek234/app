import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import LeadActivityDrawer from './LeadActivityDrawer';

const mockLeadData = {
  lead: {
    id: 'lead_123',
    campaign_id: 'camp_1',
    campaign_name: 'Q4 Enterprise',
    first_name: 'John',
    last_name: 'Doe',
    job_title: 'Head of Growth',
    company_name: 'Acme Corp',
    linkedin_url: 'https://linkedin.com/in/johndoe',
    execution_state: 'paused',
    pause_reason: 'Lead replied to outreach',
    current_node_id: 'node_message_2',
    assigned_sender_name: 'Sarah Connor',
    next_action_due_at: '2026-10-01T15:00:00Z',
    source: 'pasted_urls',
    email: 'john@acme.com',
  },
  activities: [
    {
      id: 'task_1',
      kind: 'task',
      task_type: 'connection_request',
      status: 'completed',
      node_id: 'node_invite',
      timestamp: '2026-09-29T10:00:00Z',
    },
    {
      id: 'msg_1',
      kind: 'message',
      sender_type: 'lead',
      body: 'Thanks for reaching out! Happy to chat.',
      timestamp: '2026-09-29T12:00:00Z',
    },
    {
      id: 'note_1',
      kind: 'note',
      author: 'Sarah Connor',
      note: 'Booked follow up call for next Tuesday',
      timestamp: '2026-09-29T13:00:00Z',
    },
    {
      id: 'event_1',
      kind: 'lifecycle',
      description: 'Lead enrolled in campaign',
      timestamp: '2026-09-29T09:00:00Z',
    },
  ],
  total_activities: 4,
};

const response = (body, ok = true, status = 200) => ({
  ok,
  status,
  json: async () => body,
});

describe('LeadActivityDrawer', () => {
  let container;
  let root;

  beforeEach(() => {
    global.IS_REACT_ACT_ENVIRONMENT = true;
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    localStorage.clear();
    global.fetch = jest.fn((url, options) => {
      if (url.includes('/activity')) {
        return Promise.resolve(response(mockLeadData));
      }
      if (url.includes('/notes')) {
        return Promise.resolve(response({ status: 'success', note: { id: 'note_2' } }));
      }
      if (url.includes('/resume')) {
        return Promise.resolve(response({ status: 'resumed', lead_id: 'lead_123' }));
      }
      return Promise.resolve(response({}));
    });
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    container.remove();
    jest.restoreAllMocks();
    delete global.fetch;
  });

  it('renders nothing when isOpen is false', async () => {
    await act(async () => {
      root.render(<LeadActivityDrawer leadId="lead_123" isOpen={false} onClose={() => {}} />);
    });
    expect(container.innerHTML).toBe('');
  });

  it('renders lead information, sequence position, and pause reason', async () => {
    await act(async () => {
      root.render(<LeadActivityDrawer leadId="lead_123" isOpen={true} onClose={() => {}} />);
    });

    expect(container.textContent).toContain('John Doe');
    expect(container.textContent).toContain('Head of Growth');
    expect(container.textContent).toContain('Acme Corp');
    expect(container.textContent).toContain('Paused:');
    expect(container.textContent).toContain('Lead replied to outreach');
    expect(container.textContent).toContain('node_message_2');
    expect(container.textContent).toContain('Sarah Connor');
  });

  it('renders full timeline with task, message, note, and lifecycle', async () => {
    await act(async () => {
      root.render(<LeadActivityDrawer leadId="lead_123" isOpen={true} onClose={() => {}} />);
    });

    expect(container.textContent).toContain('Connection Request');
    expect(container.textContent).toContain('Prospect replied');
    expect(container.textContent).toContain('Thanks for reaching out! Happy to chat.');
    expect(container.textContent).toContain('Note by Sarah Connor');
    expect(container.textContent).toContain('Booked follow up call for next Tuesday');
    expect(container.textContent).toContain('Lead enrolled in campaign');
  });

  it('allows adding an internal note and calling resume outreach', async () => {
    const onLeadUpdated = jest.fn();
    await act(async () => {
      root.render(
        <LeadActivityDrawer
          leadId="lead_123"
          isOpen={true}
          onClose={() => {}}
          onLeadUpdated={onLeadUpdated}
        />
      );
    });

    // 1. Test adding note
    const textarea = container.querySelector('textarea');
    expect(textarea).not.toBeNull();

    const nativeTextareaValueSetter = Object.getOwnPropertyDescriptor(
      window.HTMLTextAreaElement.prototype,
      'value'
    ).set;
    await act(async () => {
      nativeTextareaValueSetter.call(textarea, 'New note from QA test');
      textarea.dispatchEvent(new Event('input', { bubbles: true }));
      textarea.dispatchEvent(new Event('change', { bubbles: true }));
    });

    const form = container.querySelector('form');
    expect(form).not.toBeNull();

    await act(async () => {
      form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    });

    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/notes'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ note: 'New note from QA test' }),
      })
    );

    // 2. Test resume outreach
    const resumeBtn = Array.from(container.querySelectorAll('button')).find(
      (b) => b.textContent.includes('Resume outreach')
    );
    expect(resumeBtn).not.toBeNull();

    await act(async () => {
      resumeBtn.click();
    });

    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/resume'),
      expect.objectContaining({ method: 'POST' })
    );
  });
});
