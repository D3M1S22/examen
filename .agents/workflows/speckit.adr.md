# Architecture Decision Record (ADR) Workflow

When invoked via `/speckit.adr`, execute this sequence to document a major technical decision:

1. **Context Gathering**: Ask the user what architectural decision was just made (e.g., "Switched from REST to GraphQL", "Adopted MMKV for storage").
2. **Analysis**: Synthesize the context into 4 sections: Status Quo, Options Considered, Decision, and Consequences.
3. **Documentation**: Create a sequentially numbered Markdown file in the `docs/adr/` directory (e.g., `docs/adr/0001-adopt-mmkv-for-storage.md`).
4. **Validation**: Output the generated ADR for user approval.
