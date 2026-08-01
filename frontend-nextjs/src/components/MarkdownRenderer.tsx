import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface MarkdownRendererProps {
  content: string;
}

export function MarkdownRenderer({ content }: MarkdownRendererProps) {
  return (
    <div className="markdown-renderer">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <p style={{ margin: '0 0 0.75rem 0' }}>{children}</p>,
          ul: ({ children }) => <ul style={{ margin: '0 0 0.75rem 1.25rem', padding: 0 }}>{children}</ul>,
          ol: ({ children }) => <ol style={{ margin: '0 0 0.75rem 1.25rem', padding: 0 }}>{children}</ol>,
          li: ({ children }) => <li style={{ marginBottom: '0.25rem' }}>{children}</li>,
          blockquote: ({ children }) => (
            <blockquote
              style={{
                margin: '0 0 0.75rem 0',
                padding: '0.25rem 0 0.25rem 0.875rem',
                borderLeft: '3px solid var(--color-accent-primary)',
                color: 'var(--color-text-secondary)',
              }}
            >
              {children}
            </blockquote>
          ),
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              style={{ color: 'var(--color-accent-primary)' }}
            >
              {children}
            </a>
          ),
          code: ({ className, children }) => (
            <code className={className}>{children}</code>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
