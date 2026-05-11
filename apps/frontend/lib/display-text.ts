const HTML_TAG_RE = /<[^>]+>/g;
const WHITESPACE_RE = /\s+/g;
const HTML_ENTITY_MAP: Record<string, string> = {
  "&nbsp;": " ",
  "&amp;": "&",
  "&lt;": "<",
  "&gt;": ">",
  "&quot;": '"',
  "&#39;": "'",
};

function decodeHtmlEntities(value: string): string {
  return value.replace(/&nbsp;|&amp;|&lt;|&gt;|&quot;|&#39;/g, (entity) => HTML_ENTITY_MAP[entity] ?? entity);
}

export function cleanDisplayText(value: string | null | undefined, fallback = ""): string {
  if (!value) {
    return fallback;
  }
  const normalized = decodeHtmlEntities(value).replace(HTML_TAG_RE, " ").replace(WHITESPACE_RE, " ").trim();
  return normalized || fallback;
}
