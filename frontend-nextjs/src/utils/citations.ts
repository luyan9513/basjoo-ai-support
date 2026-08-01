import type { Source } from '../services/api';

export interface CitationReference {
  type: 'url' | 'file';
  title: string;
  url?: string;
  filename?: string;
  snippet?: string;
  docId?: string;
}

export interface CitationDisplayContent {
  content: string;
  references: CitationReference[];
}

const INLINE_CITATION_PATTERN = /\[([^\]]+)\]\((#source-(\d+)|https?:\/\/[^\s)]+)\)/g;

function isUrlSource(source: Source | undefined): source is Source & { type: 'url'; url: string } {
  return Boolean(
    source
      && source.type === 'url'
      && typeof source.url === 'string'
      && /^https?:\/\//.test(source.url)
  );
}

function toReference(source: Source): CitationReference | null {
  if (isUrlSource(source)) {
    return {
      type: 'url',
      title: source.title?.trim() || source.url,
      url: source.url,
      ...(source.snippet?.trim() ? { snippet: source.snippet.trim() } : {}),
    };
  }

  if (source.type !== 'file') {
    return null;
  }

  const filename = source.filename?.trim();
  const title = filename || source.title?.trim();
  if (!title) {
    return null;
  }

  return {
    type: 'file',
    title,
    ...(filename ? { filename } : {}),
    ...(source.snippet?.trim() ? { snippet: source.snippet.trim() } : {}),
    ...(source.doc_id?.trim() ? { docId: source.doc_id.trim() } : {}),
  };
}

function getReferenceKey(reference: CitationReference): string {
  if (reference.type === 'url') {
    return `url:${reference.url}`;
  }
  return `file:${reference.docId || reference.filename || reference.title}`;
}

export function formatAssistantMessageContent(
  content: string,
  sources: Source[] = [],
): CitationDisplayContent {
  if (!content) {
    return { content, references: [] };
  }

  const references: CitationReference[] = [];
  const seenReferences = new Set<string>();
  const sourceByUrl = new Map<string, Source & { type: 'url'; url: string }>();

  for (const source of sources) {
    if (isUrlSource(source) && !sourceByUrl.has(source.url)) {
      sourceByUrl.set(source.url, source);
    }

    const reference = toReference(source);
    if (!reference) {
      continue;
    }
    const key = getReferenceKey(reference);
    if (seenReferences.has(key)) {
      continue;
    }
    seenReferences.add(key);
    references.push(reference);
  }

  const formattedContent = content.replace(
    INLINE_CITATION_PATTERN,
    (_match, label: string, target: string, sourceIndexText?: string) => {
      if (sourceIndexText) {
        return label;
      }

      if (sourceByUrl.has(target)) {
        return label;
      }

      return _match;
    },
  );

  return {
    content: formattedContent,
    references,
  };
}
