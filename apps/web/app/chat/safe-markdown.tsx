"use client";

import type { ReactNode } from "react";

const LINK_RE = /\[([^\]]+)]\(([^)]+)\)/g;

export function SafeMarkdown({ value }: { value: string }) {
  const blocks = value.split(/\n{2,}/).filter(Boolean);
  if (blocks.length === 0) {
    return null;
  }
  return (
    <div className="safe-markdown">
      {blocks.map((block, index) => {
        if (block.startsWith("- ")) {
          return (
            <ul key={`${block}-${index}`}>
              {block.split("\n").map((line) => (
                <li key={line}>{renderInline(line.replace(/^- /, ""))}</li>
              ))}
            </ul>
          );
        }
        if (block.startsWith("```")) {
          return (
            <pre key={`${block}-${index}`}>{block.replaceAll("```", "")}</pre>
          );
        }
        return <p key={`${block}-${index}`}>{renderInline(block)}</p>;
      })}
    </div>
  );
}

function renderInline(value: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let cursor = 0;
  for (const match of value.matchAll(LINK_RE)) {
    const raw = match[0];
    const label = match[1] ?? "";
    const href = match[2] ?? "";
    const index = match.index ?? 0;
    if (index > cursor) {
      nodes.push(value.slice(cursor, index));
    }
    if (isSafeHref(href)) {
      nodes.push(
        <a
          key={`${href}-${index}`}
          href={href}
          target="_blank"
          rel="noreferrer noopener"
        >
          {label}
        </a>,
      );
    } else {
      nodes.push(label);
    }
    cursor = index + raw.length;
  }
  if (cursor < value.length) {
    nodes.push(value.slice(cursor));
  }
  return nodes;
}

function isSafeHref(href: string) {
  try {
    const parsed = new URL(href, "https://loomi.local");
    return ["http:", "https:", "mailto:"].includes(parsed.protocol);
  } catch {
    return false;
  }
}
