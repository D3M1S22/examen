# 🗣️ Alexa+ MCP Add-on — 04: Add-on Package, Public Pages and Tools

> **Document Status:** Planned
> **Related:** [01_alexa_requirements.md](01_alexa_requirements.md) §5, [03_alexa_mcp_serving.md](../../03_alexa_mcp_serving.md)

---

## 1. Repository layout

```
deploy/alexa/
├── addon-package/addon.json     # created by `alexa-ai new mcp`, then edited and versioned
├── assets/                      # source images (icons, carousel) → published under /alexa/ (see §3)
└── README.md                    # how to deploy / redeploy / submit, link to this doc
```

The project is created once with:
```
alexa-ai new mcp --name "Examen" --locale en-US --mcp-server-url "https://examen.devgiov.com/mcp"
```
Answer **Y** to account linking. The generated files are then committed.

- **Secrets stay out of the repository:** the OAuth client secret is passed through `ALEXA_CLIENT_SECRET`, `~/.alexa-ai/credentials` stays local.
- **Add-on id:** once known, it is recorded in `deploy/alexa/README.md` with the stage it lives in.

## 2. `addon.json` (draft)

```json
{
  "manifestVersion": "1.0",
  "storeListing": {
    "distributionCountries": ["US"],
    "locales": {
      "en-US": {
        "default": "DEFAULT",
        "name": { "value": "Examen" },
        "shortDescription": "Ask what you said you did, what you promised and what is due, from your Bee wearable.",
        "fullDescription": "Examen listens to the transcripts of your Bee wearable and keeps track of the routines you complete, the reminders you set, the people you meet and the topics you discuss. Ask Alexa whether you locked the door, what is due today, what you promised to Marco, or confirm the things Examen was not sure you said.",
        "examplePhrases": [
          "Ask Examen if I locked the front door",
          "Ask Examen what I have to do today",
          "Ask Examen what I promised Marco",
          "Ask Examen what I need to confirm"
        ],
        "privacyAndCompliance": {
          "privacyPolicyUrl": "https://examen.devgiov.com/privacy",
          "termsOfUseUrl": "https://examen.devgiov.com/terms"
        },
        "mediaAssets": {
          "icons": { "light": [
            { "size": "72x72",   "uri": "https://examen.devgiov.com/alexa/icon-72.png" },
            { "size": "64x64",   "uri": "https://examen.devgiov.com/alexa/icon-64.png" },
            { "size": "88x88",   "uri": "https://examen.devgiov.com/alexa/icon-88.png" },
            { "size": "126x126", "uri": "https://examen.devgiov.com/alexa/icon-126.png" },
            { "size": "180x180", "uri": "https://examen.devgiov.com/alexa/icon-180.png" },
            { "size": "241x241", "uri": "https://examen.devgiov.com/alexa/icon-241.png" }
          ], "dark": [] },
          "carouselImages": [
            { "uri": "https://examen.devgiov.com/alexa/carousel-1.png", "altText": "Examen answering whether the front door was locked, with the spoken sentence as proof", "size": "600x900" }
          ],
          "bannerImages": []
        }
      }
    }
  },
  "integrations": [
    { "type": "MCP", "config": { "endpoints": { "default": { "type": "HTTPS", "uri": "https://examen.devgiov.com/mcp" } } } }
  ]
}
```

- **Name:** at most 30 characters. Check that "Examen" is pronounced correctly; if not, add an IPA `spokenForm`.
- **Example phrases:** 3–4, at most 200 characters each. They must work end to end, because certification runs them.

## 3. Public pages and assets

| Path | Content | Served by |
|---|---|---|
| `/privacy` | Privacy policy, public version of `PrivacyNotice.tsx`: what is stored, Bee transcripts, AWS region, retention, erasure (Account → delete), contact | Next.js page in the static export (`src/web_ui/src/app/privacy/page.tsx`), no sign-in |
| `/terms` | Terms of use (hackathon project, no warranty, acceptable use) | `src/web_ui/src/app/terms/page.tsx` |
| `/alexa/*.png` | Icons (6 sizes), carousel 600×900, optional banner 1200×600 | `src/web_ui/public/alexa/`, copied into the export |

- The pages must be outside the auth wall. Static files under `/` already are; only `/api/*` and `/mcp` are protected.
- The image URIs must be reachable without cookies. CloudFront serves them uncached, which is fine for a store listing.

## 4. Tool adjustments

| Change | Why |
|---|---|
| **Annotations on the 12 original tools.** `readOnlyHint=True` on the read tools; `create_planned_task` is idempotent=false and non-destructive | Alexa (and other clients) can call reads without confirmation |
| **Typed results** (`TypedDict` / Pydantic return types) for the most used tools: `verify_action_status`, `get_daily_actions_recap`, `get_upcoming_tasks`, `query_social_contact`, `get_social_commitments`, `list_items_to_review` | `structuredContent` with real fields and an `outputSchema`, instead of `{"result": {...}}` |
| **Drop the Echo Show blobs from MCP results** (`card_payload`, `display_template`, `ui_card_type`) behind a flag, or move them to `_meta` | Alexa renders data itself; the blobs only add size and latency. The dashboard does not use them through MCP |
| **Keep `spoken_summary`** as the first `content` text item | Alexa may quote it; it carries "Bee could not confirm it was your voice" |
| **Alexa-facing tool set.** Hide `get_ingestion_coverage` and `get_live_event_outline` from the add-on (a deny list for OAuth clients, or a separate FastMCP mount at `/mcp/alexa`) | Fewer, clearer tools improve Alexa's tool selection. Admin-flavoured tools add nothing by voice |
| **Measure latency** of each tool through CloudFront and fix anything above about 300 ms server time | 500 ms round-trip budget (01 §2) |
| **Error text for unlinked or empty users:** "Examen has no data yet: pair your Bee in the Examen dashboard" | No dead ends (certification) |

## 5. MCP Apps (optional, decision A6)

- **What it adds.** Alexa+ renders a tool's custom UI when the result has `_meta.ui.resourceUri = "ui://…"` and the server serves that resource (`resources/read`). It is the official replacement for our home-made Echo Show `ext-app` idea.
- **Candidates:**
  - **Daily recap card:** routines done / due, review items with ✔ / ✕ that call `accept_item` / `dismiss_item`;
  - **Contact card:** web profile, commitments.
- **How:** use the `@modelcontextprotocol/ext-apps` SDK. Each card is a small self-contained HTML bundle registered as a FastMCP resource, with `_meta.ui` on the tool result.
- **Later:** after the text add-on is certified; it needs the design guide's display modes, accessibility and contrast rules.
