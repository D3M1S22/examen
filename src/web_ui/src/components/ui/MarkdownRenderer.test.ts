import { describe, expect, it } from "bun:test";
import { generateTopicMarkdown } from "@/utils/dossierExport";

describe("MarkdownRenderer & Dossier Content Pipeline", () => {
  it("compiles and outputs full markdown with valid syntax tokens", () => {
    const md = generateTopicMarkdown({
      topic_title: "Test Topic Title",
      context_type: "academic",
      explanatory_synthesis: "This is the thesis statement.",
      executive_summary: ["Point 1", "Point 2"],
      action_items: ["Task 1", "Task 2"],
      web_sources: ["https://example.com/source"],
      deep_dive_markdown: "# Technical Architecture\n\n```python\nprint('hello')\n```",
    });

    expect(md).toContain("# Test Topic Title");
    expect(md).toContain("## ⚡ Explanatory Synthesis & Core Thesis");
    expect(md).toContain("## 📌 Executive Summary & Key Insights");
    expect(md).toContain("## ✅ Action Items & Strategic Follow-ups");
    expect(md).toContain("## 🔗 Corroborating Citations & Web Sources");
    expect(md).toContain("## 🔬 Deep Dive Research & Technical Specification");
    expect(md).toContain("```python");
  });

  it("handles edge case of topic with only deep_dive_markdown", () => {
    const md = generateTopicMarkdown({
      topic_title: "Pure Markdown Dossier",
      deep_dive_markdown: "## Section 1\n\nContent here.\n\n- [ ] Task A\n- [x] Task B",
    });

    expect(md).toContain("# Pure Markdown Dossier");
    expect(md).toContain("## Section 1");
    expect(md).toContain("- [ ] Task A");
    expect(md).toContain("- [x] Task B");
  });

  it("handles empty strings and nulls safely in all fields", () => {
    const md = generateTopicMarkdown({
      topic_title: "",
      explanatory_synthesis: "",
      executive_summary: [],
      action_items: [],
      web_sources: [],
      deep_dive_markdown: "",
    });

    expect(md).toContain("# Autonomous Topic Research Dossier");
    expect(md).not.toContain("## ⚡ Explanatory Synthesis & Core Thesis");
    expect(md).not.toContain("## 📌 Executive Summary & Key Insights");
  });
});
