import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import Sessions from '../../src/views/Sessions';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('react-router-dom', () => ({
  useParams: () => ({ agentId: 'agent-handoff' }),
}));

vi.mock('../../src/context/AuthContext', () => ({
  useAuth: () => ({ token: 'test-token' }),
}));

vi.mock('../../src/hooks/useMediaQuery', () => ({
  useIsMobile: () => false,
}));

vi.mock('../../src/components/AdminLayout', () => ({
  default: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));

class WebSocketStub {
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  close() {}
}

describe('Sessions handoff queue', () => {
  beforeEach(() => {
    Object.defineProperty(Element.prototype, 'scrollIntoView', {
      configurable: true,
      value: vi.fn(),
    });
    vi.stubGlobal('WebSocket', WebSocketStub);
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/messages')) {
        return { ok: true, json: async () => [] } as Response;
      }
      return {
        ok: true,
        json: async () => ({
          items: [{
            id: 'db-session-1',
            session_id: 'public-session-1',
            visitor_id: 'visitor-1',
            status: 'handoff_requested',
            message_count: 2,
            created_at: '2026-07-30T00:00:00Z',
            updated_at: '2026-07-30T00:01:00Z',
            last_message: 'Need human help',
          }],
          total: 1,
        }),
      } as Response;
    }));
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('shows a waiting-for-human filter, badge and takeover action', async () => {
    render(<Sessions />);

    expect(
      await screen.findByRole('button', { name: 'status.handoffRequested' }),
    ).toBeInTheDocument();
    expect(await screen.findAllByText('status.handoffRequested')).toHaveLength(2);

    fireEvent.click(screen.getByText('Need human help'));

    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: 'labels.takeoverSession' }),
      ).toBeInTheDocument();
    });
  });
});
