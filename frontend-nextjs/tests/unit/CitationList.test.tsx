import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { CitationList } from '../../src/components/CitationList';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

describe('CitationList', () => {
  it('renders URL sources as links and file sources as non-clickable cards', () => {
    render(
      <CitationList
        references={[
          { type: 'url', title: '帮助中心', url: 'https://example.com/help' },
          {
            type: 'file',
            title: '04-payments.md',
            filename: '04-payments.md',
            docId: 'doc-payments',
            snippet: 'PayPal 退款预计 3–5 个工作日到账。',
          },
        ]}
      />,
    );

    expect(screen.getByRole('link', { name: '帮助中心' })).toHaveAttribute(
      'href',
      'https://example.com/help',
    );
    expect(screen.getByText('04-payments.md').closest('a')).toBeNull();
    expect(screen.getByText(/1\. ↗/)).toBeVisible();
    expect(screen.getByText(/2\. 📄/)).toBeVisible();
    expect(screen.getByText('PayPal 退款预计 3–5 个工作日到账。')).toBeVisible();
  });

  it('renders untrusted file metadata as text instead of markup', () => {
    const { container } = render(
      <CitationList
        references={[
          {
            type: 'file',
            title: '<img src=x onerror=alert(1)>',
            snippet: '[伪链接](javascript:alert(1))',
          },
        ]}
      />,
    );

    expect(screen.getByText('<img src=x onerror=alert(1)>')).toBeVisible();
    expect(screen.getByText('[伪链接](javascript:alert(1))')).toBeVisible();
    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('a')).toBeNull();
  });
});
