import { createElement, Fragment, type ReactNode } from "react";

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function safeHref(value: unknown): string | undefined {
  if (typeof value !== "string" || /[\s\u0000-\u001f\u007f]/u.test(value)) {
    return undefined;
  }
  try {
    const url = new URL(value);
    if (["https:", "http:", "mailto:"].includes(url.protocol)) return value;
  } catch {
    // Relative URLs and malformed links are intentionally rendered as text.
  }
  return undefined;
}

/** Render the editor's stored JSON, never stored HTML or arbitrary attributes. */
export function RichTextBody({ content }: { content: unknown }) {
  let hasText = false;
  let remaining = 10_000;
  let exceededLimit = false;

  function renderNode(value: unknown, depth: number): ReactNode {
    if (--remaining < 0 || depth > 32) {
      exceededLimit = true;
      return null;
    }
    const node = record(value);
    if (!node) return null;

    if (node.type === "text") {
      if (typeof node.text !== "string") return null;
      if (node.text.trim()) hasText = true;
      let text: ReactNode = node.text;
      for (const value of Array.isArray(node.marks) ? node.marks.slice(0, 16) : []) {
        const mark = record(value);
        switch (mark?.type) {
          case "bold":
            text = <strong>{text}</strong>;
            break;
          case "italic":
            text = <em>{text}</em>;
            break;
          case "strike":
            text = <s>{text}</s>;
            break;
          case "underline":
            text = <u>{text}</u>;
            break;
          case "code":
            text = <code>{text}</code>;
            break;
          case "link": {
            const href = safeHref(record(mark.attrs)?.href);
            if (href)
              text = (
                <a href={href} rel="noopener noreferrer">
                  {text}
                </a>
              );
            break;
          }
        }
      }
      return text;
    }

    // Unknown nodes (including HTML, scripts, images and embeds) are dropped,
    // not interpreted. Only these editor-supported semantic tags can reach DOM.
    const tags = {
      doc: "div",
      paragraph: "p",
      heading: "h2",
      bulletList: "ul",
      orderedList: "ol",
      listItem: "li",
      blockquote: "blockquote",
      codeBlock: "pre",
      hardBreak: "br",
      horizontalRule: "hr",
    } as const;
    if (typeof node.type !== "string" || !Object.hasOwn(tags, node.type)) return null;
    const type = node.type as keyof typeof tags;
    if (type === "hardBreak") return <br />;
    if (type === "horizontalRule") return <hr />;
    const children = (Array.isArray(node.content) ? node.content : [])
      .slice(0, 10_001)
      .map((child, index) => <Fragment key={index}>{renderNode(child, depth + 1)}</Fragment>);
    if (Array.isArray(node.content) && node.content.length > 10_000) exceededLimit = true;
    if (type === "heading") {
      const level = record(node.attrs)?.level;
      const tag = level === 1 ? "h1" : level === 3 ? "h3" : "h2";
      return createElement(tag, null, children);
    }
    if (type === "orderedList") {
      const start = record(node.attrs)?.start;
      return (
        <ol
          start={
            typeof start === "number" && Number.isSafeInteger(start) && start > 0
              ? start
              : undefined
          }
        >
          {children}
        </ol>
      );
    }
    if (type === "codeBlock")
      return (
        <pre>
          <code>{children}</code>
        </pre>
      );
    return createElement(tags[type], null, children);
  }

  const body = record(content)?.type === "doc" ? renderNode(content, 0) : null;
  if (!hasText || exceededLimit) {
    return <p className="text-sm text-muted-foreground">No article content is available yet.</p>;
  }

  return (
    <div className="min-w-0 max-w-full whitespace-pre-wrap break-words text-sm leading-relaxed [overflow-wrap:anywhere] [&_h1]:mb-4 [&_h1]:text-2xl [&_h1]:font-bold [&_h2]:mb-3 [&_h2]:text-xl [&_h2]:font-semibold [&_h3]:mb-2 [&_h3]:text-lg [&_h3]:font-medium [&_p]:mb-3 [&_ul]:mb-3 [&_ul]:list-disc [&_ul]:pl-6 [&_ol]:mb-3 [&_ol]:list-decimal [&_ol]:pl-6 [&_li]:mb-1 [&_blockquote]:border-l-4 [&_blockquote]:border-muted [&_blockquote]:pl-4 [&_blockquote]:italic [&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_pre]:overflow-x-auto [&_pre]:whitespace-pre [&_pre]:p-3 [&_a]:text-foreground [&_a]:underline [&_a]:underline-offset-2 [&_a:focus-visible]:outline-2 [&_a:focus-visible]:outline-offset-2 [&_hr]:my-4">
      {body}
    </div>
  );
}
