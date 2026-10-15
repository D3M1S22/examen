import { describe, expect, it } from "bun:test";
import {
  sanitizeFilename,
  generateTopicMarkdown,
  generateContactMarkdown,
} from "./dossierExport";
import { BriefingReport, SocialEntity } from "@/types/schemas";

describe("dossierExport - sanitizeFilename", () => {
  it("handles standard topic titles", () => {
    expect(sanitizeFilename("AWS Bedrock MicroVM Runtime", ".md")).toBe(
      "aws_bedrock_microvm_runtime.md"
    );
  });

  it("handles punctuation and special characters", () => {
    expect(
      sanitizeFilename("Sub-second Persistence: Why It Matters! (v1.0)", ".md")
    ).toBe("sub-second_persistence_why_it_matters_v1_0.md");
  });

  it("handles empty or whitespace strings with safe fallback", () => {
    expect(sanitizeFilename("", ".md")).toBe("dossier_export.md");
    expect(sanitizeFilename("   ", ".md")).toBe("dossier_export.md");
    expect(sanitizeFilename(null as any, ".md")).toBe("dossier_export.md");
    expect(sanitizeFilename(undefined as any, ".md")).toBe("dossier_export.md");
  });

  it("clamps extremely long filenames to 64 chars", () => {
    const longName = "a".repeat(100);
    const sanitized = sanitizeFilename(longName, ".md");
    expect(sanitized.length).toBeLessThanOrEqual(67); // 64 + .md
    expect(sanitized.endsWith(".md")).toBe(true);
  });
});

describe("dossierExport - generateTopicMarkdown", () => {
  it("safely handles null or undefined topic", () => {
    expect(generateTopicMarkdown(null as any)).toBe("");
    expect(generateTopicMarkdown(undefined as any)).toBe("");
    expect(generateTopicMarkdown({} as any)).toContain("# Autonomous Topic Research Dossier");
  });

  it("generates publication-grade markdown for a complete topic", () => {
    const topic: BriefingReport = {
      id: "topic-1",
      topic_title: "Bedrock AgentCore MicroVMs",
      context_type: "tech_stack",
      kind: "standalone",
      created_at: "2026-10-15T18:00:00Z",
      explanatory_synthesis: "AgentCore provides microVM isolation for ambient agent execution.",
      executive_summary: [
        "Sub-second boot times",
        "Deterministic LangGraph state checkpointing",
      ],
      action_items: [
        "Deploy Docker container to AWS AgentCore",
        "Benchmark FastMCP latency under 200ms",
      ],
      web_sources: [
        "https://aws.amazon.com/bedrock",
        "https://docs.aws.amazon.com/bedrock/agentcore",
      ],
      deep_dive_markdown: "```python\n# Execution engine\ndef run(): pass\n```",
    };

    const md = generateTopicMarkdown(topic);
    expect(md).toContain("# Bedrock AgentCore MicroVMs");
    expect(md).toContain("**Domain / Context**: `TECH STACK`");
    expect(md).toContain("**Kind**: `STANDALONE`");
    expect(md).toContain("## ⚡ Explanatory Synthesis & Core Thesis");
    expect(md).toContain("AgentCore provides microVM isolation");
    expect(md).toContain("## 📌 Executive Summary & Key Insights");
    expect(md).toContain("- Sub-second boot times");
    expect(md).toContain("## ✅ Action Items & Strategic Follow-ups");
    expect(md).toContain("- [ ] Deploy Docker container to AWS AgentCore");
    expect(md).toContain("## 🔗 Corroborating Citations & Web Sources");
    expect(md).toContain("- [https://aws.amazon.com/bedrock](https://aws.amazon.com/bedrock)");
    expect(md).toContain("## 🔬 Deep Dive Research & Technical Specification");
    expect(md).toContain("```python");
  });

  it("safely handles partial and malformed properties without throwing", () => {
    const malformedTopic: any = {
      topic_title: null,
      context_type: 12345, // not a string
      created_at: null,
      executive_summary: [null, "Valid summary item", 42],
      action_items: [undefined, "Valid action item"],
      web_sources: [{ title: "AWS Documentation", url: "https://aws.amazon.com" }],
    };

    const md = generateTopicMarkdown(malformedTopic);
    expect(md).toContain("# Autonomous Topic Research Dossier");
    expect(md).toContain("- Valid summary item");
    expect(md).toContain("- 42");
    expect(md).toContain("- [ ] Valid action item");
    expect(md).toContain("- [AWS Documentation](https://aws.amazon.com)");
  });
});

describe("dossierExport - generateContactMarkdown", () => {
  it("safely handles null or undefined contact", () => {
    expect(generateContactMarkdown(null as any)).toBe("");
    expect(generateContactMarkdown(undefined as any)).toBe("");
    expect(generateContactMarkdown({} as any)).toContain("# Executive Intelligence Dossier: Executive Contact");
  });

  it("generates structured markdown with anti-contamination audit & bilateral commitments", () => {
    const contact: SocialEntity = {
      id: "cont-1",
      name: "Dr. Elena Rostova",
      company_or_role: "VP of AI Research, CloudScale",
      contact_info: "elena@cloudscale.ai",
      location_encountered: "Zurich AI Summit",
      timestamp: "2026-10-15T12:00:00Z",
      commitments: [
        {
          id: "cmt-1",
          description: "Send pitch deck tomorrow at 10 AM",
          debtor: "user",
          status: "open",
        },
      ],
      web_profile: {
        headline: "Leader in Distributed AI Architecture",
        bio_summary: "Dr. Rostova leads next-gen consensus algorithms.",
        linkedin_url: "https://linkedin.com/in/elena-rostova",
        areas_of_expertise: ["Distributed Systems", "Agentic Workflows"],
        confidence_score: 0.96,
        disambiguation_report: {
          confidence_score: 0.96,
          rationale: "Matched by affiliation with CloudScale and co-authored papers.",
          clean_combined_facts: ["VP at CloudScale", "PhD from ETH Zurich"],
          verified_source_indices: [0, 1],
          rejected_source_indices: [2],
        },
      },
      key_topics: ["microVMs", "LangGraph"],
    };

    const md = generateContactMarkdown(contact);
    expect(md).toContain("# Executive Intelligence Dossier: Dr. Elena Rostova");
    expect(md).toContain("**Role / Organization**: VP of AI Research, CloudScale");
    expect(md).toContain("**AI Match Certainty**: 96%");
    expect(md).toContain("- **LinkedIn**: [https://linkedin.com/in/elena-rostova](https://linkedin.com/in/elena-rostova)");
    expect(md).toContain("## 👤 Executive Profile Summary");
    expect(md).toContain("Dr. Rostova leads next-gen consensus algorithms.");
    expect(md).toContain("## 🛡️ Anti-Contamination & Disambiguation Audit");
    expect(md).toContain("Matched by affiliation with CloudScale");
    expect(md).toContain("- ✓ VP at CloudScale");
    expect(md).toContain("## 🤝 Bilateral Commitments");
    expect(md).toContain("**[You Promised]** [OPEN] Send pitch deck tomorrow at 10 AM");
    expect(md).toContain("## 🏷️ Key Discussion Topics");
    expect(md).toContain("#microVMs #LangGraph");
  });
});
