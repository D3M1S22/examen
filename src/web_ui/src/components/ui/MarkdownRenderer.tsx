"use client";

import React, { useState, useMemo } from "react";
import { downloadTextFile, sanitizeFilename } from "@/utils/dossierExport";

export interface MarkdownRendererProps {
  content?: string | null;
  className?: string;
  allowRawToggle?: boolean;
  defaultMode?: "rendered" | "raw";
  title?: string;
  filename?: string;
  accentColor?: "amber" | "cyan" | "purple" | "emerald";
  showDownloadButton?: boolean;
  showCopyButton?: boolean;
  emptyStateText?: string;
}

/**
 * Safely parses inline markdown tokens (bold, italic, code, links) into React nodes
 * without using dangerouslySetInnerHTML, eliminating XSS risks.
 */
function renderInlineTokens(text: string, keyPrefix: string): React.ReactNode[] {
  // Regex pattern matching:
  // 1. Inline code: `code`
  // 2. Bold: **bold** or __bold__
  // 3. Italic: *italic* or _italic_
  // 4. Links: [label](url)
  const pattern = /(`[^`]+`|\*\*[^*]+\*\*|__[^_]+__|\*[^*]+\*|_[^_]+_|\[[^\]]+\]\([^)]+\))/g;
  const parts = text.split(pattern);

  return parts.map((part, index) => {
    const key = `${keyPrefix}-${index}`;
    if (!part) return null;

    // Inline code
    if (part.startsWith("`") && part.endsWith("`") && part.length >= 2) {
      return (
        <code
          key={key}
          className="px-1.5 py-0.5 rounded bg-black/60 border border-white/10 font-mono text-[11px] text-cyan-300"
        >
          {part.slice(1, -1)}
        </code>
      );
    }

    // Bold
    if (
      (part.startsWith("**") && part.endsWith("**") && part.length >= 4) ||
      (part.startsWith("__") && part.endsWith("__") && part.length >= 4)
    ) {
      return (
        <strong key={key} className="font-bold text-white">
          {part.slice(2, -2)}
        </strong>
      );
    }

    // Italic
    if (
      (part.startsWith("*") && part.endsWith("*") && part.length >= 2) ||
      (part.startsWith("_") && part.endsWith("_") && part.length >= 2)
    ) {
      return (
        <em key={key} className="italic text-zinc-300">
          {part.slice(1, -1)}
        </em>
      );
    }

    // Link: [label](url)
    const linkMatch = part.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
    if (linkMatch) {
      const [, label, url] = linkMatch;
      const isExternal = url.startsWith("http://") || url.startsWith("https://");
      return (
        <a
          key={key}
          href={url}
          target={isExternal ? "_blank" : undefined}
          rel={isExternal ? "noopener noreferrer" : undefined}
          className="text-cyan-400 hover:text-cyan-300 underline font-medium break-all transition-colors"
        >
          {label}
        </a>
      );
    }

    return <React.Fragment key={key}>{part}</React.Fragment>;
  });
}

/**
 * Block item representation
 */
type Block =
  | { type: "code"; lang: string; content: string }
  | { type: "h1"; content: string }
  | { type: "h2"; content: string }
  | { type: "h3"; content: string }
  | { type: "h4"; content: string }
  | { type: "blockquote"; content: string[] }
  | { type: "ul"; items: string[] }
  | { type: "ol"; items: string[] }
  | { type: "table"; headers: string[]; rows: string[][] }
  | { type: "hr" }
  | { type: "p"; content: string };

function parseMarkdownBlocks(raw: string): Block[] {
  const lines = raw.replace(/\r\n/g, "\n").split("\n");
  const blocks: Block[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();

    // Empty lines
    if (!trimmed) {
      i++;
      continue;
    }

    // Code blocks
    if (trimmed.startsWith("```")) {
      const lang = trimmed.slice(3).trim();
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith("```")) {
        codeLines.push(lines[i]);
        i++;
      }
      if (i < lines.length && lines[i].trim().startsWith("```")) {
        i++; // skip closing ```
      }
      blocks.push({
        type: "code",
        lang: lang || "text",
        content: codeLines.join("\n"),
      });
      continue;
    }

    // Horizontal Rule
    if (/^(\-{3,}|\*{3,}|_{3,})$/.test(trimmed)) {
      blocks.push({ type: "hr" });
      i++;
      continue;
    }

    // Headings
    if (trimmed.startsWith("#### ")) {
      blocks.push({ type: "h4", content: trimmed.slice(5).trim() });
      i++;
      continue;
    }
    if (trimmed.startsWith("### ")) {
      blocks.push({ type: "h3", content: trimmed.slice(4).trim() });
      i++;
      continue;
    }
    if (trimmed.startsWith("## ")) {
      blocks.push({ type: "h2", content: trimmed.slice(3).trim() });
      i++;
      continue;
    }
    if (trimmed.startsWith("# ")) {
      blocks.push({ type: "h1", content: trimmed.slice(2).trim() });
      i++;
      continue;
    }

    // Blockquotes
    if (trimmed.startsWith(">")) {
      const quoteLines: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith(">")) {
        quoteLines.push(lines[i].trim().replace(/^>\s?/, ""));
        i++;
      }
      blocks.push({ type: "blockquote", content: quoteLines });
      continue;
    }

    // Tables: must contain | and have header separator
    if (trimmed.startsWith("|") && trimmed.endsWith("|")) {
      const tableLines: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith("|") && lines[i].trim().endsWith("|")) {
        tableLines.push(lines[i].trim());
        i++;
      }
      if (tableLines.length >= 2 && /^\|[\s\-:|]+\|$/.test(tableLines[1])) {
        const splitRow = (r: string) =>
          r
            .slice(1, -1)
            .split("|")
            .map((c) => c.trim());
        const headers = splitRow(tableLines[0]);
        const rows = tableLines.slice(2).map(splitRow);
        blocks.push({ type: "table", headers, rows });
        continue;
      }
    }

    // Unordered Lists (- or *)
    if (/^[\-*]\s+/.test(trimmed)) {
      const items: string[] = [];
      while (i < lines.length && /^[\-*]\s+/.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(/^[\-*]\s+/, ""));
        i++;
      }
      blocks.push({ type: "ul", items });
      continue;
    }

    // Ordered Lists (1. 2. etc.)
    if (/^\d+\.\s+/.test(trimmed)) {
      const items: string[] = [];
      while (i < lines.length && /^\d+\.\s+/.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(/^\d+\.\s+/, ""));
        i++;
      }
      blocks.push({ type: "ol", items });
      continue;
    }

    // Paragraph
    const pLines: string[] = [line];
    i++;
    while (
      i < lines.length &&
      lines[i].trim() &&
      !lines[i].trim().startsWith("```") &&
      !lines[i].trim().startsWith("#") &&
      !lines[i].trim().startsWith(">") &&
      !/^[\-*]\s+/.test(lines[i].trim()) &&
      !/^\d+\.\s+/.test(lines[i].trim()) &&
      !(lines[i].trim().startsWith("|") && lines[i].trim().endsWith("|"))
    ) {
      pLines.push(lines[i]);
      i++;
    }
    blocks.push({ type: "p", content: pLines.join(" ") });
  }

  return blocks;
}

export function MarkdownRenderer({
  content,
  className = "",
  allowRawToggle = true,
  defaultMode = "rendered",
  title,
  filename,
  accentColor = "amber",
  showDownloadButton = true,
  showCopyButton = true,
  emptyStateText = "No markdown content provided.",
}: MarkdownRendererProps) {
  const [mode, setMode] = useState<"rendered" | "raw">(defaultMode);
  const [copied, setCopied] = useState(false);
  const [copiedCodeIdx, setCopiedCodeIdx] = useState<number | null>(null);

  const rawContent = (typeof content === "string" ? content : content ? String(content) : "").trim();
  const blocks = useMemo(() => (rawContent ? parseMarkdownBlocks(rawContent) : []), [rawContent]);

  const wordCount = useMemo(() => {
    if (!rawContent) return 0;
    return rawContent.split(/\s+/).filter(Boolean).length;
  }, [rawContent]);

  const handleCopy = () => {
    if (!rawContent) return;
    if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(rawContent).then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      }).catch(() => {});
    }
  };

  const handleCopyCode = (codeText: string, idx: number) => {
    if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(codeText).then(() => {
        setCopiedCodeIdx(idx);
        setTimeout(() => setCopiedCodeIdx(null), 2000);
      }).catch(() => {});
    }
  };

  const handleDownload = () => {
    if (!rawContent) return;
    const finalFilename = sanitizeFilename(filename || title || "dossier_research", ".md");
    downloadTextFile(rawContent, finalFilename);
  };

  if (!rawContent) {
    return (
      <div className={`p-6 rounded-xl bg-black/40 border border-white/5 text-center text-zinc-500 font-mono text-xs italic ${className}`}>
        {emptyStateText}
      </div>
    );
  }

  const accentBorder = {
    amber: "border-amber-500/30",
    cyan: "border-cyan-500/30",
    purple: "border-purple-500/30",
    emerald: "border-emerald-500/30",
  }[accentColor];

  const accentBadge = {
    amber: "bg-amber-950/60 text-amber-300 border-amber-500/40",
    cyan: "bg-cyan-950/60 text-cyan-300 border-cyan-500/40",
    purple: "bg-purple-950/60 text-purple-300 border-purple-500/40",
    emerald: "bg-emerald-950/60 text-emerald-300 border-emerald-500/40",
  }[accentColor];

  return (
    <div className={`rounded-xl bg-[#0c0e12] border ${accentBorder} overflow-hidden shadow-lg ${className}`}>
      {/* Visualizer Toolbar Bar */}
      <div className="bg-[#12151c] px-4 py-2.5 border-b border-white/10 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          {title && (
            <span className="font-mono text-[10px] text-zinc-300 uppercase tracking-widest font-semibold truncate max-w-xs sm:max-w-md">
              {title}
            </span>
          )}
          <span className={`px-2 py-0.5 rounded-full font-mono text-[9px] uppercase tracking-wider border ${accentBadge}`}>
            MARKDOWN
          </span>
          <span className="font-mono text-[9px] text-zinc-500 hidden sm:inline">
            {wordCount} words
          </span>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-1.5">
          {allowRawToggle && (
            <div className="flex items-center bg-black/60 p-0.5 rounded-lg border border-white/10 text-[10px] font-mono">
              <button
                type="button"
                onClick={() => setMode("rendered")}
                className={`px-2.5 py-1 rounded-md transition-colors flex items-center gap-1 cursor-pointer ${
                  mode === "rendered"
                    ? "bg-zinc-800 text-white font-bold shadow-sm"
                    : "text-zinc-400 hover:text-white"
                }`}
                title="Render formatted markdown"
              >
                <span>📖</span>
                <span>Rendered</span>
              </button>
              <button
                type="button"
                onClick={() => setMode("raw")}
                className={`px-2.5 py-1 rounded-md transition-colors flex items-center gap-1 cursor-pointer ${
                  mode === "raw"
                    ? "bg-zinc-800 text-white font-bold shadow-sm"
                    : "text-zinc-400 hover:text-white"
                }`}
                title="View raw markdown syntax"
              >
                <span>💻</span>
                <span>Raw</span>
              </button>
            </div>
          )}

          {showCopyButton && (
            <button
              type="button"
              onClick={handleCopy}
              className="px-2.5 py-1 rounded-lg bg-black/40 hover:bg-zinc-800 border border-white/10 text-zinc-300 hover:text-white font-mono text-[10px] tracking-wider uppercase transition-colors flex items-center gap-1 cursor-pointer"
              title="Copy markdown text to clipboard"
            >
              <span>{copied ? "✓" : "📋"}</span>
              <span className="hidden xs:inline">{copied ? "Copied" : "Copy"}</span>
            </button>
          )}

          {showDownloadButton && (
            <button
              type="button"
              onClick={handleDownload}
              className="px-2.5 py-1 rounded-lg bg-cyan-950/70 hover:bg-cyan-900 border border-cyan-500/40 text-cyan-300 font-mono text-[10px] tracking-wider uppercase transition-colors flex items-center gap-1 cursor-pointer font-semibold shadow-sm"
              title="Download research dossier as .md file"
            >
              <span>💾</span>
              <span>Download .md</span>
            </button>
          )}
        </div>
      </div>

      {/* Content Area */}
      <div className="p-4 sm:p-6 text-zinc-100 font-sans leading-relaxed">
        {mode === "raw" ? (
          <div className="relative">
            <pre className="font-mono text-xs text-zinc-300 bg-[#07080a] border border-white/5 rounded-xl p-4 overflow-x-auto whitespace-pre-wrap leading-relaxed select-text max-h-[500px]">
              {rawContent}
            </pre>
          </div>
        ) : (
          <div className="space-y-4 max-h-[550px] overflow-y-auto pr-1">
            {blocks.map((block, idx) => {
              const key = `block-${idx}`;
              switch (block.type) {
                case "h1":
                  return (
                    <h1
                      key={key}
                      className="font-serif text-2xl sm:text-3xl text-white font-bold border-b border-white/10 pb-2 mt-4 first:mt-0"
                    >
                      {renderInlineTokens(block.content, key)}
                    </h1>
                  );
                case "h2":
                  return (
                    <h2
                      key={key}
                      className="font-serif text-xl sm:text-2xl text-white font-bold border-b border-white/5 pb-1.5 mt-4 first:mt-0 text-cyan-200"
                    >
                      {renderInlineTokens(block.content, key)}
                    </h2>
                  );
                case "h3":
                  return (
                    <h3
                      key={key}
                      className="font-serif text-lg text-white font-semibold mt-3 first:mt-0 text-amber-200"
                    >
                      {renderInlineTokens(block.content, key)}
                    </h3>
                  );
                case "h4":
                  return (
                    <h4
                      key={key}
                      className="font-mono text-xs uppercase tracking-wider text-zinc-300 font-bold mt-2"
                    >
                      {renderInlineTokens(block.content, key)}
                    </h4>
                  );
                case "blockquote":
                  return (
                    <blockquote
                      key={key}
                      className="border-l-4 border-cyan-400/80 bg-cyan-950/20 rounded-r-lg p-3 font-sans italic text-zinc-200 text-sm leading-relaxed space-y-1"
                    >
                      {block.content.map((cLine, cIdx) => (
                        <p key={`${key}-q-${cIdx}`}>
                          {renderInlineTokens(cLine, `${key}-q-${cIdx}`)}
                        </p>
                      ))}
                    </blockquote>
                  );
                case "ul":
                  return (
                    <ul key={key} className="space-y-1.5 pl-4 text-sm text-zinc-200">
                      {block.items.map((item, itemIdx) => {
                        const isChecked = item.startsWith("[x] ") || item.startsWith("[X] ");
                        const isUnchecked = item.startsWith("[ ] ");
                        const cleanItem = isChecked || isUnchecked ? item.slice(4) : item;
                        return (
                          <li key={`${key}-li-${itemIdx}`} className="flex items-start gap-2.5">
                            {isChecked ? (
                              <span className="text-emerald-400 font-bold select-none">☑</span>
                            ) : isUnchecked ? (
                              <span className="text-zinc-500 font-bold select-none">☐</span>
                            ) : (
                              <span className="text-cyan-400 font-bold select-none">•</span>
                            )}
                            <span className={`flex-1 ${isChecked ? "line-through text-zinc-400" : ""}`}>
                              {renderInlineTokens(cleanItem, `${key}-item-${itemIdx}`)}
                            </span>
                          </li>
                        );
                      })}
                    </ul>
                  );
                case "ol":
                  return (
                    <ol key={key} className="space-y-1.5 pl-4 text-sm text-zinc-200">
                      {block.items.map((item, itemIdx) => (
                        <li key={`${key}-oli-${itemIdx}`} className="flex items-start gap-2.5">
                          <span className="font-mono text-xs text-amber-400 font-bold select-none shrink-0">
                            {itemIdx + 1}.
                          </span>
                          <span className="flex-1">
                            {renderInlineTokens(item, `${key}-oitem-${itemIdx}`)}
                          </span>
                        </li>
                      ))}
                    </ol>
                  );
                case "table":
                  return (
                    <div key={key} className="overflow-x-auto rounded-lg border border-white/10 my-3">
                      <table className="w-full text-left text-xs border-collapse">
                        <thead>
                          <tr className="bg-white/5 border-b border-white/10 font-mono uppercase text-zinc-300">
                            {block.headers.map((h, hIdx) => (
                              <th key={`${key}-th-${hIdx}`} className="p-2.5 font-semibold">
                                {renderInlineTokens(h, `${key}-th-${hIdx}`)}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-white/5 font-sans text-zinc-200">
                          {block.rows.map((row, rIdx) => (
                            <tr key={`${key}-tr-${rIdx}`} className="hover:bg-white/5 transition-colors">
                              {row.map((cell, cIdx) => (
                                <td key={`${key}-td-${rIdx}-${cIdx}`} className="p-2.5">
                                  {renderInlineTokens(cell, `${key}-td-${rIdx}-${cIdx}`)}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  );
                case "hr":
                  return <hr key={key} className="border-t border-white/10 my-4" />;
                case "code":
                  return (
                    <div key={key} className="rounded-xl bg-[#07080a] border border-white/10 overflow-hidden my-3">
                      <div className="bg-black/80 px-3 py-1.5 border-b border-white/5 flex items-center justify-between text-[10px] font-mono text-zinc-400">
                        <span className="uppercase text-cyan-400 font-semibold">{block.lang || "code"}</span>
                        <button
                          type="button"
                          onClick={() => handleCopyCode(block.content, idx)}
                          className="hover:text-white transition-colors"
                        >
                          {copiedCodeIdx === idx ? "✓ Copied" : "Copy code"}
                        </button>
                      </div>
                      <pre className="p-3.5 overflow-x-auto font-mono text-xs text-zinc-200 leading-relaxed">
                        <code>{block.content}</code>
                      </pre>
                    </div>
                  );
                case "p":
                default:
                  return (
                    <p key={key} className="text-sm text-zinc-200 leading-relaxed">
                      {renderInlineTokens(block.content, key)}
                    </p>
                  );
              }
            })}
          </div>
        )}
      </div>
    </div>
  );
}
