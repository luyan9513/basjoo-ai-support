import { describe, expect, it } from 'vitest';

import { formatAssistantMessageContent } from '../../src/utils/citations';

describe('formatAssistantMessageContent', () => {
  it('keeps file sources even when persisted content has no source placeholder', () => {
    const result = formatAssistantMessageContent('退款将在 3–5 个工作日到账。', [
      {
        type: 'file',
        title: '支付说明',
        filename: '04-payments.md',
        doc_id: 'doc-payments',
        snippet: 'PayPal 退款预计 3–5 个工作日到账。',
      },
    ]);

    expect(result.references).toEqual([
      {
        type: 'file',
        title: '04-payments.md',
        filename: '04-payments.md',
        docId: 'doc-payments',
        snippet: 'PayPal 退款预计 3–5 个工作日到账。',
      },
    ]);
  });

  it('deduplicates chunks from the same file by doc_id', () => {
    const result = formatAssistantMessageContent('答案', [
      { type: 'file', filename: 'faq.md', doc_id: 'doc-faq', snippet: '第一段' },
      { type: 'file', filename: 'faq.md', doc_id: 'doc-faq', snippet: '第二段' },
    ]);

    expect(result.references).toHaveLength(1);
    expect(result.references[0].snippet).toBe('第一段');
  });

  it('keeps URL and file references in source order and strips placeholders', () => {
    const result = formatAssistantMessageContent(
      '参见 [官网](#source-1) 和 [退款文件](#source-2)。',
      [
        { type: 'url', title: '帮助中心', url: 'https://example.com/help' },
        { type: 'file', filename: 'returns.md', doc_id: 'doc-returns' },
      ],
    );

    expect(result.content).toBe('参见 官网 和 退款文件。');
    expect(result.references.map((reference) => reference.type)).toEqual(['url', 'file']);
  });

  it('does not create clickable references for unsafe URLs', () => {
    const result = formatAssistantMessageContent('查看 [来源](#source-1)。', [
      { type: 'url', title: '危险来源', url: 'javascript:alert(1)' },
    ]);

    expect(result.content).toBe('查看 来源。');
    expect(result.references).toEqual([]);
  });
});
