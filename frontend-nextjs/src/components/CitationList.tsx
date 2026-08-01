'use client';

import { useTranslation } from 'react-i18next';

import type { CitationReference } from '../utils/citations';

interface CitationListProps {
  references: CitationReference[];
  inverse?: boolean;
}

export function CitationList({ references, inverse = false }: CitationListProps) {
  const { t } = useTranslation('common');

  if (references.length === 0) {
    return null;
  }

  const borderColor = inverse ? 'rgba(255,255,255,0.25)' : 'var(--color-border)';
  const cardBackground = inverse ? 'rgba(255,255,255,0.14)' : 'var(--color-bg-tertiary)';
  const cardColor = inverse ? 'inherit' : 'var(--color-text-primary)';

  return (
    <div
      style={{
        marginTop: 'var(--space-3)',
        paddingTop: 'var(--space-3)',
        borderTop: `1px solid ${borderColor}`,
      }}
    >
      <div
        style={{
          marginBottom: 'var(--space-2)',
          color: inverse ? 'inherit' : 'var(--color-text-muted)',
          fontSize: 'var(--text-xs)',
          fontWeight: 600,
          opacity: inverse ? 0.85 : 1,
        }}
      >
        {t('citations.references')}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
        {references.map((reference, index) => {
          const content = (
            <>
              <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, wordBreak: 'break-word' }}>
                <span aria-hidden="true">
                  {index + 1}. {reference.type === 'file' ? '📄 ' : '↗ '}
                </span>
                <span>{reference.title}</span>
              </div>
              {reference.snippet && (
                <div
                  style={{
                    marginTop: 'var(--space-1)',
                    fontSize: 'var(--text-xs)',
                    lineHeight: 1.5,
                    opacity: 0.78,
                    overflow: 'hidden',
                    display: '-webkit-box',
                    WebkitBoxOrient: 'vertical',
                    WebkitLineClamp: 2,
                  }}
                >
                  {reference.snippet}
                </div>
              )}
            </>
          );
          const style = {
            display: 'block',
            padding: 'var(--space-2) var(--space-3)',
            border: `1px solid ${borderColor}`,
            borderRadius: 'var(--radius-md)',
            background: cardBackground,
            color: cardColor,
            textDecoration: 'none',
          };
          const key = reference.type === 'url'
            ? `url:${reference.url}`
            : `file:${reference.docId || reference.filename || reference.title}`;

          return reference.type === 'url' && reference.url ? (
            <a
              key={key}
              href={reference.url}
              target="_blank"
              rel="noopener noreferrer"
              aria-label={reference.title}
              style={style}
            >
              {content}
            </a>
          ) : (
            <div key={key} style={style}>
              {content}
            </div>
          );
        })}
      </div>
    </div>
  );
}
