import { readFileSync } from 'node:fs';
import path from 'node:path';

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { MarkdownRenderer } from '../../src/components/MarkdownRenderer';

describe('MarkdownRenderer', () => {
  it('keeps paragraphs, inline code, and block code distinguishable', () => {
    const { container } = render(
      <MarkdownRenderer
        content={'普通段落包含 `INLINE-CODE-123`。\n\n```text\nBLOCK-CODE-456\n```'}
      />,
    );

    expect(screen.getByText(/普通段落包含/).tagName).toBe('P');

    const inlineCode = screen.getByText('INLINE-CODE-123');
    const blockCode = screen.getByText(/BLOCK-CODE-456/);

    expect(inlineCode.tagName).toBe('CODE');
    expect(inlineCode.closest('pre')).toBeNull();
    expect(blockCode.tagName).toBe('CODE');
    expect(blockCode.closest('pre')).not.toBeNull();
    expect(container.firstElementChild).toHaveClass('markdown-renderer');
  });

  it('defines theme-aware foreground colors for inline and block code', () => {
    const styles = readFileSync(
      path.resolve(process.cwd(), 'src/index.css'),
      'utf8',
    );

    expect(styles).toMatch(
      /\.markdown-renderer :not\(pre\) > code\s*\{[\s\S]*?color:\s*var\(--color-text-primary\)/,
    );
    expect(styles).toMatch(
      /\.markdown-renderer pre\s*\{[\s\S]*?color:\s*var\(--color-text-primary\)/,
    );
  });
});
