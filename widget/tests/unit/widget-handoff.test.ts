import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { BasjooWidget } from '../../src/BasjooWidget';

describe('BasjooWidget human handoff', () => {
  beforeEach(() => {
    const values = new Map<string, string>();
    const localStorageStub: Storage = {
      get length() { return values.size; },
      clear: () => values.clear(),
      getItem: (key) => values.get(key) ?? null,
      key: (index) => Array.from(values.keys())[index] ?? null,
      removeItem: (key) => { values.delete(key); },
      setItem: (key, value) => { values.set(key, String(value)); },
    };
    Object.defineProperty(window, 'localStorage', {
      configurable: true,
      value: localStorageStub,
    });
    document.body.innerHTML = '';
    document.title = 'Widget test';
    window.localStorage.clear();
    window.localStorage.setItem('basjoo_session_agent-handoff', 'public-session-1');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    document.body.innerHTML = '';
    document.querySelector('#basjoo-widget-styles')?.remove();
  });

  it('lets an existing visitor request a human once and disables repeat clicks', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes('/api/v1/config:public')) {
        return {
          ok: true,
          json: async () => ({ widget_title: 'Support', widget_color: '#3B82F6' }),
        } as Response;
      }
      if (url.includes('/api/v1/chat/messages')) {
        return {
          ok: true,
          json: async () => ([
            { id: 7, role: 'user', content: 'I need help', sources: [] },
          ]),
        } as Response;
      }
      if (url.includes('/api/v1/chat/handoff') && init?.method === 'POST') {
        return {
          ok: true,
          json: async () => ({
            success: true,
            status: 'handoff_requested',
            created: true,
            message: 'Your request for a human agent has been received.',
            message_id: 8,
          }),
        } as Response;
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    const widget = new BasjooWidget({
      agentId: 'agent-handoff',
      apiBase: 'http://localhost:8000',
      language: 'en-US',
    });
    await widget.init();

    await vi.waitFor(() => {
      const button = document.querySelector('.basjoo-handoff') as HTMLButtonElement;
      expect(button).toBeTruthy();
      expect(button.disabled).toBe(false);
    });

    const button = document.querySelector('.basjoo-handoff') as HTMLButtonElement;
    button.click();

    await vi.waitFor(() => {
      expect(button.disabled).toBe(true);
      expect(button.textContent).toContain('Requested');
      expect(document.body.textContent).toContain(
        'Your request for a human agent has been received.',
      );
    });

    const handoffCalls = fetchMock.mock.calls.filter(([input]) =>
      String(input).includes('/api/v1/chat/handoff'),
    );
    expect(handoffCalls).toHaveLength(1);
    widget.destroy();
  });
});
