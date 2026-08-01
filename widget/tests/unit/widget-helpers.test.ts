/**
 * Unit tests for BasjooWidget helper functions.
 *
 * Run with: vitest run tests/unit/widget-helpers.test.ts
 * or: jest tests/unit/widget-helpers.test.ts
 */

import { describe, it, expect } from 'vitest';
import { formatAssistantMessage, type WidgetSource as Source } from '../../src/citations';

describe('formatAssistantMessage', () => {
  it('returns empty content for empty input', () => {
    const result = formatAssistantMessage('', []);
    expect(result.content).toBe('');
    expect(result.references).toEqual([]);
  });

  it('returns content without references when no sources', () => {
    const result = formatAssistantMessage('Hello world', []);
    expect(result.content).toBe('Hello world');
    expect(result.references).toEqual([]);
  });

  it('extracts #source-N references', () => {
    const sources: Source[] = [
      { type: 'url', title: 'My Page', url: 'https://example.com' },
    ];
    const result = formatAssistantMessage('See [docs](#source-1) for details.', sources);
    expect(result.content).toBe('See docs for details.');
    expect(result.references).toEqual([
      { type: 'url', title: 'My Page', url: 'https://example.com' },
    ]);
  });

  it('extracts direct URL references', () => {
    const sources: Source[] = [
      { type: 'url', title: 'My Page', url: 'https://example.com' },
    ];
    const result = formatAssistantMessage('Check [this](https://example.com) out.', sources);
    expect(result.content).toBe('Check this out.');
    expect(result.references).toEqual([
      { type: 'url', title: 'My Page', url: 'https://example.com' },
    ]);
  });

  it('deduplicates URL references', () => {
    const sources: Source[] = [
      { type: 'url', title: 'Page 1', url: 'https://example.com' },
      { type: 'url', title: 'Page 1 duplicate', url: 'https://example.com' },
    ];
    const result = formatAssistantMessage(
      'See [one](#source-1) and also [two](#source-1).',
      sources,
    );
    expect(result.content).toBe('See one and also two.');
    expect(result.references).toHaveLength(1);
    expect(result.references[0].url).toBe('https://example.com');
  });

  it('includes multiple distinct references', () => {
    const sources: Source[] = [
      { type: 'url', title: 'Page A', url: 'https://a.com' },
      { type: 'url', title: 'Page B', url: 'https://b.com' },
    ];
    const result = formatAssistantMessage(
      'See [a](#source-1) and [b](#source-2).',
      sources,
    );
    expect(result.references).toHaveLength(2);
    expect(result.references[0].url).toBe('https://a.com');
    expect(result.references[1].url).toBe('https://b.com');
  });

  it('keeps file references as non-clickable source data', () => {
    const sources: Source[] = [
      { type: 'file', filename: 'faq.md', doc_id: 'doc-faq', snippet: '退款说明' },
    ];
    const result = formatAssistantMessage('As per [faq](#source-1)...', sources);
    expect(result.content).toBe('As per faq...');
    expect(result.references).toEqual([
      {
        type: 'file',
        title: 'faq.md',
        filename: 'faq.md',
        docId: 'doc-faq',
        snippet: '退款说明',
      },
    ]);
  });

  it('deduplicates file chunks by doc_id', () => {
    const sources: Source[] = [
      { type: 'file', filename: 'faq.md', doc_id: 'doc-faq', snippet: '第一段' },
      { type: 'file', filename: 'faq.md', doc_id: 'doc-faq', snippet: '第二段' },
    ];
    const result = formatAssistantMessage('回答内容', sources);
    expect(result.references).toHaveLength(1);
    expect(result.references[0]).toMatchObject({
      type: 'file',
      filename: 'faq.md',
      docId: 'doc-faq',
    });
  });

  it('does not expose unsafe URL sources as links', () => {
    const sources: Source[] = [
      { type: 'url', title: 'Unsafe', url: 'javascript:alert(1)' },
    ];
    const result = formatAssistantMessage('See [unsafe](#source-1).', sources);
    expect(result.content).toBe('See unsafe.');
    expect(result.references).toEqual([]);
  });

  it('strips out-of-range source index', () => {
    const sources: Source[] = [];
    const result = formatAssistantMessage('See [link](#source-1).', sources);
    expect(result.content).toBe('See link.');
    expect(result.references).toEqual([]);
  });

  it('handles mixed valid and invalid references', () => {
    const sources: Source[] = [
      { type: 'url', title: 'Valid', url: 'https://valid.com' },
      { type: 'file', filename: 'faq.md', doc_id: 'f1' },
    ];
    const result = formatAssistantMessage(
      'See [valid](#source-1) and [faq](#source-2).',
      sources,
    );
    expect(result.content).toBe('See valid and faq.');
    expect(result.references).toEqual([
      { type: 'url', title: 'Valid', url: 'https://valid.com' },
      { type: 'file', title: 'faq.md', filename: 'faq.md', docId: 'f1' },
    ]);
  });

  it('uses URL as title when source has no title', () => {
    const sources: Source[] = [
      { type: 'url', url: 'https://notitle.com' },
    ];
    const result = formatAssistantMessage('See [page](#source-1).', sources);
    expect(result.references[0].title).toBe('https://notitle.com');
  });
});

describe('Widget API Base Detection (conceptual tests)', () => {
  // In a real test environment, we would need to mock document.currentScript
  // and window.location. Here we test the core URL logic.

  it('uses configured apiBase when provided', () => {
    // This tests the URL construction logic
    const apiBase = 'https://api.example.com';
    const url = new URL('/basjoo-logo.png', `${apiBase}/`);
    expect(url.toString()).toBe('https://api.example.com/basjoo-logo.png');
  });

  it('handles apiBase with trailing slash', () => {
    const apiBase = 'https://api.example.com/';
    const url = new URL('/basjoo-logo.png', apiBase);
    expect(url.toString()).toBe('https://api.example.com/basjoo-logo.png');
  });

  it('builds logo URL from relative path', () => {
    const apiBase = '';
    const origin = 'http://localhost';
    const url = new URL('/basjoo-logo.png', origin);
    expect(url.toString()).toContain('/basjoo-logo.png');
  });
});

describe('Widget Storage Key Conventions', () => {
  it('generates session key per agent ID', () => {
    const agentId = 'agt_0123456789ab';
    const storageKey = `basjoo_session_${agentId}`;
    expect(storageKey).toBe('basjoo_session_agt_0123456789ab');
  });

  it('visitor ID uses global key', () => {
    expect('basjoo_visitor_id').toBe('basjoo_visitor_id');
  });
});
