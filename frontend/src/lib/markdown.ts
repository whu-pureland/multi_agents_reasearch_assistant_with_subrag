import DOMPurify from "dompurify";
import MarkdownIt from "markdown-it";

const md = new MarkdownIt({ linkify: true, breaks: true });

export function renderMarkdown(markdown: string): string {
  return DOMPurify.sanitize(md.render(markdown || ""));
}

