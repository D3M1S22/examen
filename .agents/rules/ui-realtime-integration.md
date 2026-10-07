# Rule: EXAMEN Real-Time UI & Gatekeeper Integration

## 1. Schema Fidelity
All frontend state, props, and API clients MUST mirror `src/core/schemas.py`:
- `ChunkClassification`: Categories (`actionable`, `social_insight`, `curiosity_topic`, `noop`), `confidence` (0.0 to 1.0), and `summary_hint`.
- `ActionItem` & `PlannedTask`: Statuses must strictly adhere to `'pending' | 'in_progress' | 'completed' | 'cancelled'`. Task cards must expose structured steps, execution plans, and action triggers.
- `SocialObservation`: People tags, sentiment, and relationship context notes.
- `ResearchItem`: Generated web queries, syntheses, and citations.

## 2. Interaction & State Machine Standards
- **Optimistic Task Updates**: When triggering task actions (Approve, Complete, Snooze), transition the UI state immediately. Roll back gracefully with an error indicator if the request fails.
- **Status Badges & Visual Telemetry**:
  - Expose live audio ingestion states (`Listening`, `Processing`, `Idle`).
  - Render Gatekeeper qualification cards clearly showing when background chatter is filtered (`noop`) versus when actionable context is extracted.
- **Scroll & Focus Preservation**: Periodic polling or event stream updates must never reset scroll position or cause layout flicker.

## 3. MCP Serving Integration
- Wire UI actions directly to tools exposed in `src/serving/mcp_server.py` and `src/serving/tools/` (`execute_task_plan`, `update_task_status`, `complete_active_task`).