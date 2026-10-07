# Spec-Driven Development: Planning Phase
When the user invokes `/speckit.plan`, execute the following sequential steps:
1. Analyze the user intent and the existing architecture.
2. Delegate the system design to the `system-architect` sub-agent.
3. Generate a `plan.md` outlining the data model, API signatures, and component hierarchy.
4. Pause and request human approval before generating code.
