# 09. Frontend Technical Assessment: UI Gaps & Required Additions from `next_steps`

**Author:** EXAMEN Core Architecture & Frontend Engineering  
**Branch:** `update/web_ui` (Merged with `origin/Next_steps`)  
**Target Platform:** Next.js 14 App Router (`src/web_ui/src/`) & Amazon Echo Show Multimodal Dashboard  
**Status:** Architecture Assessment & UI Implementation Specification  

---

## 1. Executive Summary

A clean merge of `origin/Next_steps` into `update/web_ui` has been completed. The merged codebase passes **100% of the comprehensive test suite (154/154 pytest cases passing)**.

The `Next_steps` branch introduces critical AI capabilities for disambiguating real-world human entities, preventing directory scraping contamination, extracting spoken portfolio URLs from ambient audio, and auditing external web intelligence.

However, while the backend Pydantic models (`src/core/schemas.py`), SQLite storage (`src/core/storage/sqlite_store.py`), LangGraph enrichment pipeline (`src/pipeline/nodes/`), and FastMCP REST endpoints (`src/serving/mcp_server.py`) now fully support these capabilities, **the Next.js TypeScript frontend (`src/web_ui/src/`) does not yet surface these features to the user or judging panel**.

Furthermore, during the merge, we discovered that the upstream colleague had made modifications to the legacy vanilla JavaScript file (`src/web_ui/app.js`), unaware that the `update/web_ui` branch had migrated the entire frontend to Next.js 14 / TypeScript (`src/web_ui/src/`). Resolving this merge conflict preserved our Next.js architecture while cataloging all intended UI capabilities to be faithfully implemented in the modern React component hierarchy.

This document serves as the **exhaustive architectural specification** for all frontend changes, data contracts, and UI components required to bridge the gap.

---

## 2. Deep Dive: What Was Introduced in `next_steps`

### A. Data Contracts (`src/core/schemas.py`)
1. **`SourceType` (Enum):**
   - Values: `direct_profile` (personal LinkedIn/GitHub), `single_aggregator` (company bio), `multi_directory` (whitepages/LinkedIn directory listing), `irrelevant` (homonym/noise).
2. **`EvaluatedSource` (Pydantic Model):**
   - Represents an LLM-screened search result snippet with:
     - `index: int`
     - `source_type: SourceType`
     - `is_target_individual: bool`
     - `is_redundant_of_index: Optional[int]`
     - `usable_facts_extracted: List[str]`
     - `reason: str`
3. **`DisambiguationResult` (Pydantic Model):**
   - Detailed audit trail of entity verification:
     - `primary_direct_profile_index: Optional[int]`
     - `canonical_linkedin_url: Optional[str]`
     - `canonical_github_url: Optional[str]`
     - `verified_source_indices: List[int]`
     - `rejected_source_indices: List[int]`
     - `clean_combined_facts: List[str]`
     - `confidence_score: float` (0.0 to 1.0)
     - `rationale: str`
4. **`SocialWebProfile` Extensions:**
   - Added `disambiguation_report: Optional[DisambiguationResult]`
5. **`SocialEntity` Extensions:**
   - Added `website_url: Optional[str]` for personal portfolios, startup homepages, or blogs.

### B. Storage Layer (`src/core/storage/sqlite_store.py`)
- Added column `website_url TEXT` to table `social_contacts`.
- Automatic non-destructive schema migration via `_init_db()`.
- Persists both conversational website URLs and enriched web profile URLs.
- Homonym protection in `save_social_contact`: distinct contacts with identical names but differing company affiliations are stored separately rather than erroneously collapsed.

### C. Pipeline & Extraction Nodes (`src/pipeline/nodes/`)
1. **`social.py`:**
   - Added spoken URL recognition: `extract_verbalized_urls(text)` (e.g. converting *"w w w punto example punto it"* or *"marco dot dev"* into clickable `https://` URLs).
   - Added compound Italian/European surname matching (`de`, `di`, `del`, `della`, `van`, `von`, `da`).
   - Added role sanitization: `sanitize_company_or_role(role)` strips conversational clutter.
2. **`social_profiler.py`:**
   - Multi-tier LLM verification: screens candidate sources, rejects directory listings (e.g. `pub/dir` LinkedIn listings), eliminates homonym contamination, and filters candidate skill tags against rejected sources.
3. **`topic_research.py`:**
   - Search query normalization: strips Italian and English stopwords from research queries.
4. **`web_search.py`:**
   - Quotes stripping on queries with >3 words to prevent zero-result exact match penalties on DuckDuckGo.

### D. Serving Layer & FastMCP Telemetry (`src/serving/mcp_server.py`)
- Endpoint `GET /api/contacts`: returns `website_url` and `web_profile.disambiguation_report`.
- Endpoint `POST /api/contacts/{id}/enrich`: returns enriched profile with `disambiguation_report` and broadcasts SSE event `contact_enriched`.
- MCP Tool `query_social_contact`: returns `links.website` and top-level `website_url`.

### E. Diagnostic & Database Management Tooling (`scripts/reset_db.py`)
- Standalone CLI script supporting `--backup` and `--seed` to quickly reset the local SQLite context store to a pristine baseline during judge evaluation sessions.

---

## 3. Current Frontend State vs. Required Additions (Gap Analysis)

The current Next.js application in `src/web_ui/src/` has 4 primary views and 2 modal portals:
- `OverviewHub.tsx`: High-level metrics, Peace of Mind banner, and recent micro-events.
- `PeaceOfMind.tsx`: Real-time safety verification timeline.
- `DailyRoutines.tsx`: Domestic checklist and ambient voice schedule manager.
- `SocialRolodex.tsx`: Passive conversational CRM and bilateral commitments.
- `TopicDossiers.tsx`: Deep-dive technical briefings.
- `AmbientSimulator.tsx`: Multi-scenario audio feeder.
- `ExecutiveDossierModal.tsx`: Slide-in modal for contact deep dives.
- `FollowUpModal.tsx`: Follow-up message composer.

### Gap Matrix

| Subsystem / Component | Current Frontend State | Gap / Missing from `next_steps` | Priority |
| :--- | :--- | :--- | :--- |
| **`types/schemas.ts`** | Lacks `website_url`, `disambiguation_report`, and all related disambiguation models. | Missing types: `website_url`, `SourceType`, `EvaluatedSource`, `DisambiguationResult`. | **Critical (P0)** |
| **`SocialRolodex.tsx`** (Card View) | Shows contact name, role, contact info, key topics, and commitments. No external link pills are rendered. | 1. Missing external link pills: LinkedIn, GitHub, and Website/Portfolio.<br>2. Missing visual badge when an interlocutor has an audited web dossier.<br>3. Missing filter for "Verified Dossiers" / "Spoken Website". | **High (P1)** |
| **`ExecutiveDossierModal.tsx`** | Shows basic bio, role, organization, topics, and commitments. | 1. Missing external link pills header (`LinkedIn`, `GitHub`, `Personal Website`).<br>2. Missing **Disambiguation & Source Audit Drawer** displaying:<br>&nbsp;&nbsp;• Disambiguation Confidence Score Gauge.<br>&nbsp;&nbsp;• Verified sources vs. Rejected Homonyms.<br>&nbsp;&nbsp;• Isolated clean facts list.<br>&nbsp;&nbsp;• LLM rationale explaining source filtering.<br>3. Missing visual indicator when URL was spoken in ambient audio. | **High (P1)** |
| **`AmbientSimulator.tsx`** | Contains 8 standard conversation scenarios. | Missing scenario simulating a meeting with a spoken website/portfolio (e.g. *"Piacere sono Marco, visita il mio sito marco punto dev"*) and a homonym disambiguation test scenario. | **Medium (P2)** |
| **`OverviewHub.tsx`** | Displays recent social contacts as text pills. | Does not indicate if contacts have verified web profiles or website links. | **Low (P3)** |
| **Administrative UI** | No database reset trigger. | No UI button to reset/seed the database via `reset_db.py` during live judging. | **Medium (P2)** |

---

## 4. Detailed Component Design & Specifications

### 4.1 TypeScript Schema Additions (`src/web_ui/src/types/schemas.ts`)

```typescript
export type SourceType = "direct_profile" | "single_aggregator" | "multi_directory" | "irrelevant";

export interface EvaluatedSource {
  index: number;
  source_type: SourceType;
  is_target_individual: boolean;
  is_redundant_of_index?: number | null;
  usable_facts_extracted: string[];
  reason: string;
}

export interface DisambiguationResult {
  primary_direct_profile_index?: number | null;
  canonical_linkedin_url?: string | null;
  canonical_github_url?: string | null;
  verified_source_indices: number[];
  rejected_source_indices: number[];
  clean_combined_facts: string[];
  confidence_score: number;
  rationale: string;
}

export interface SocialWebProfile {
  headline?: string;
  organization?: string;
  current_role?: string;
  bio_summary?: string;
  executive_summary?: string;
  areas_of_expertise: string[];
  linkedin_url?: string | null;
  github_url?: string | null;
  website_url?: string | null;
  confidence_score?: number;
  enrichment_source?: string;
  enriched_at: string;
  disambiguation_report?: DisambiguationResult | null;
}

export interface SocialEntity {
  id: string;
  name: string;
  person_name?: string;
  company_or_role?: string;
  contact_info?: string;
  website_url?: string | null;            // <-- NEW: Spoken/Explicit Website URL
  first_met?: string;
  key_topics: string[];
  commitments: (SocialCommitment | string)[];
  web_profile?: SocialWebProfile;
  location_encountered?: string;
  session_id?: string;
  timestamp: string;
}
```

---

### 4.2 Contact Card Links Tray in `SocialRolodex.tsx`

Each contact card in `SocialRolodex.tsx` will be upgraded to feature a **Verified Web Intelligence Pill Tray** directly beneath the role description:

```tsx
{/* Verified Links Tray */}
<div className="flex flex-wrap items-center gap-2 mt-2">
  {contact.web_profile?.linkedin_url && (
    <a
      href={contact.web_profile.linkedin_url}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-[#0077b5]/15 border border-[#0077b5]/40 text-[#70b5f9] font-mono text-[9px] tracking-wider uppercase hover:bg-[#0077b5]/30 transition-colors"
      onClick={(e) => e.stopPropagation()}
    >
      <span>💼</span>
      <span>LinkedIn</span>
    </a>
  )}

  {contact.web_profile?.github_url && (
    <a
      href={contact.web_profile.github_url}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-[#24292e]/60 border border-white/20 text-[#e6edf3] font-mono text-[9px] tracking-wider uppercase hover:bg-white/10 transition-colors"
      onClick={(e) => e.stopPropagation()}
    >
      <span>🐙</span>
      <span>GitHub</span>
    </a>
  )}

  {(contact.website_url || contact.web_profile?.website_url) && (
    <a
      href={contact.website_url || contact.web_profile?.website_url || "#"}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-emerald-500/15 border border-emerald-500/40 text-emerald-300 font-mono text-[9px] tracking-wider uppercase hover:bg-emerald-500/30 transition-colors"
      onClick={(e) => e.stopPropagation()}
    >
      <span>🌐</span>
      <span>Website</span>
      {contact.website_url && !contact.web_profile?.website_url && (
        <span className="text-[7px] bg-emerald-400/20 px-1 rounded text-emerald-200">VOICE</span>
      )}
    </a>
  )}

  {contact.web_profile?.disambiguation_report && (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-amber-500/10 border border-amber-500/30 font-mono text-[8px] text-amber-300">
      <span>🛡️</span>
      <span>{(contact.web_profile.disambiguation_report.confidence_score * 100).toFixed(0)}% Disambiguated</span>
    </span>
  )}
</div>
```

---

### 4.3 Executive Dossier Modal Verification & Audit Drawer (`ExecutiveDossierModal.tsx`)

In `ExecutiveDossierModal.tsx`, we add two new sections:

#### A. External Web Dossier Links Bar
A prominent link bar below the contact header offering direct navigation to LinkedIn, GitHub, and Portfolio:
```tsx
<div className="flex flex-wrap items-center gap-3 p-4 bg-[#0e1014] border border-[#232731] rounded-xl">
  <span className="font-mono text-[8px] text-secondary tracking-widest uppercase">Verified Profiles:</span>
  {/* LinkedIn Pill */}
  {/* GitHub Pill */}
  {/* Website Pill */}
</div>
```

#### B. Disambiguation & Source Integrity Audit Drawer
When `contact.web_profile?.disambiguation_report` is present, display a dedicated accordion / audit box:
- **Confidence Gauge:** Visual progress bar indicating entity matching certainty (e.g. `95% Corroborated`).
- **Entity Rationalization:** Display `report.rationale` describing why external sources were clustered to this specific person.
- **Isolated Target Facts:** Display bullet points from `report.clean_combined_facts`.
- **Source Filtering Diagnostics:**
  - `Verified Sources`: Green pills with source indices.
  - `Rejected Sources / Directory Noise`: Red pills indicating discarded homonyms or low-signal aggregators.

```tsx
{/* Disambiguation Audit Panel */}
{disambiguation && (
  <div className="bg-[#101217] border border-amber-500/30 rounded-xl p-5 space-y-4">
    <div className="flex items-center justify-between border-b border-white/5 pb-3">
      <div className="flex items-center gap-2">
        <span className="text-amber-400 text-base">🛡️</span>
        <span className="font-mono text-[10px] text-amber-300 tracking-widest uppercase font-bold">
          Source Disambiguation & Anti-Contamination Audit
        </span>
      </div>
      <div className="flex items-center gap-2">
        <span className="font-mono text-[9px] text-secondary">CERTAINTY:</span>
        <span className="font-mono text-xs font-bold text-amber-400">
          {(disambiguation.confidence_score * 100).toFixed(0)}%
        </span>
      </div>
    </div>

    {/* Rationale */}
    {disambiguation.rationale && (
      <div>
        <div className="font-mono text-[8px] text-secondary tracking-widest uppercase mb-1">Deduplication Rationale</div>
        <p className="font-sans text-xs text-secondary italic leading-relaxed">
          "{disambiguation.rationale}"
        </p>
      </div>
    )}

    {/* Verified Facts */}
    {disambiguation.clean_combined_facts?.length > 0 && (
      <div>
        <div className="font-mono text-[8px] text-secondary tracking-widest uppercase mb-1.5">Corroborated Facts</div>
        <ul className="space-y-1">
          {disambiguation.clean_combined_facts.map((fact, i) => (
            <li key={i} className="font-sans text-xs text-emerald-300 flex items-start gap-2">
              <span className="text-emerald-400 mt-0.5">✓</span>
              <span>{fact}</span>
            </li>
          ))}
        </ul>
      </div>
    )}

    {/* Source Diagnostics Pill Row */}
    <div className="flex items-center gap-4 pt-2 font-mono text-[8px]">
      <div className="flex items-center gap-1.5 text-emerald-400">
        <span>Verified Sources:</span>
        <span className="px-1.5 py-0.5 rounded bg-emerald-950 border border-emerald-500/40 font-bold">
          {disambiguation.verified_source_indices?.length || 0}
        </span>
      </div>
      <div className="flex items-center gap-1.5 text-rose-400">
        <span>Rejected Noise/Homonyms:</span>
        <span className="px-1.5 py-0.5 rounded bg-rose-950 border border-rose-500/40 font-bold">
          {disambiguation.rejected_source_indices?.length || 0}
        </span>
      </div>
    </div>
  </div>
)}
```

---

### 4.4 Ambient Audio Simulator Preset Additions (`AmbientSimulator.tsx`)

Add a new preset scenario to `AmbientSimulator.tsx`:
```typescript
{
  id: "scenario_social_spoken_url",
  title: "Conference Intro with Spoken Website & Portfolio",
  domain: "social",
  speaker: "Luca Bianchi",
  transcript: "Piacere Damiano, sono Luca Bianchi, Lead Architect presso Cyberdyne. Se vuoi approfondire la nostra architettura distribuita trovi tutte le specifiche sul mio sito www punto lucabianchi punto dev. Ci sentiamo venerdì per una call.",
  expectedTags: ["social", "website", "commitment"],
}
```

---

### 4.5 FastMCP & Database Reset Admin Endpoint

To empower live demo resets on the Echo Show touchscreen, expose a lightweight endpoint in `src/serving/mcp_server.py`:
- `POST /api/admin/reset-db?seed=true`
- Invokes `scripts.reset_db.reset_database(backup=True, seed=True)`
- Triggers a button in the frontend header: **"RESET DEMO DATA"** with a confirmation modal.

---

## 5. Implementation Roadmap & Verification Gates

Once approved, the implementation should follow this ordered plan:

1. **Step 1: TypeScript Schemas** (`src/web_ui/src/types/schemas.ts`)
   - Add `DisambiguationResult`, `EvaluatedSource`, `SourceType`.
   - Update `SocialWebProfile` and `SocialEntity` to include `website_url` and `disambiguation_report`.
2. **Step 2: Social Rolodex Card Upgrade** (`src/web_ui/src/components/views/SocialRolodex.tsx`)
   - Add external links tray (`LinkedIn`, `GitHub`, `Website`).
   - Add disambiguation certainty badge.
3. **Step 3: Executive Dossier Modal Enhancement** (`src/web_ui/src/components/ui/ExecutiveDossierModal.tsx`)
   - Add links header bar.
   - Add Disambiguation & Source Integrity Audit Drawer with facts and source rejection diagnostics.
4. **Step 4: Simulator Scenario Update** (`src/web_ui/src/components/views/AmbientSimulator.tsx`)
   - Add the spoken portfolio scenario preset.
5. **Step 5: Frontend Build & Static Export**
   - Run Next.js build: `bun run build` or `npm run build` in `src/web_ui/`.
   - Confirm exported files in `src/web_ui/out/`.
   - Verify `pytest tests/test_mcp_server.py` passes (verifying static asset serving).

---

## 6. Conclusion

The merge of `origin/Next_steps` into `update/web_ui` was executed with zero regressions on existing pipeline logic, test suites, or telemetry systems. The frontend gaps identified above represent pure user-facing enrichment opportunities that will make EXAMEN's AI entity resolution, privacy guardrails, and ambient audio intelligence shine during hackathon judging.
