# Security & Secrets Management

These rules are inviolable security boundaries for all agent and sub-agent operations.
- **Never Output Secrets**: NEVER output raw API keys, production passwords, or database URIs in chat responses or log files.
- **ENV Generation**: When scaffolding `.env` files, use obvious placeholder values (e.g., `sk_test_placeholder`).
- **Code Injection**: Never hardcode credentials into source code. Always instruct the system to read from `process.env`.
