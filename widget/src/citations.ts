export interface WidgetSource {
  type: 'url' | 'file';
  title?: string;
  url?: string;
  filename?: string;
  snippet?: string;
  doc_id?: string;
}

export interface WidgetReference {
  type: 'url' | 'file';
  title: string;
  url?: string;
  filename?: string;
  snippet?: string;
  docId?: string;
}

const INLINE_CITATION_PATTERN = /\[([^\]]+)\]\((#source-(\d+)|https?:\/\/[^\s)]+)\)/g;

function isSafeUrl(source: WidgetSource): source is WidgetSource & { type: 'url'; url: string } {
  return source.type === 'url'
    && typeof source.url === 'string'
    && /^https?:\/\//.test(source.url);
}

function toReference(source: WidgetSource): WidgetReference | null {
  if (isSafeUrl(source)) {
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

function referenceKey(reference: WidgetReference): string {
  return reference.type === 'url'
    ? `url:${reference.url}`
    : `file:${reference.docId || reference.filename || reference.title}`;
}

export function formatAssistantMessage(
  content: string,
  sources: WidgetSource[] = [],
): { content: string; references: WidgetReference[] } {
  if (!content) {
    return { content, references: [] };
  }

  const references: WidgetReference[] = [];
  const seenReferences = new Set<string>();
  const sourceByUrl = new Set<string>();

  for (const source of sources) {
    if (isSafeUrl(source)) {
      sourceByUrl.add(source.url);
    }
    const reference = toReference(source);
    if (!reference) {
      continue;
    }
    const key = referenceKey(reference);
    if (seenReferences.has(key)) {
      continue;
    }
    seenReferences.add(key);
    references.push(reference);
  }

  const formattedContent = content.replace(
    INLINE_CITATION_PATTERN,
    (match, label: string, target: string, sourceIndexText?: string) => {
      if (sourceIndexText || sourceByUrl.has(target)) {
        return label;
      }
      return match;
    },
  );

  return { content: formattedContent, references };
}
