# DevOps & Infrastructure Standards

These constraints govern how you manage system dependencies and infrastructure.
- **Nix Flakes**: Treat `flake.nix` as the ultimate source of truth for dependencies. Do not run `npm install -g` or use OS-level package managers.
- **Docker**: Always use multi-stage builds. Default to Alpine-based images (e.g., `node:18-alpine`) for production to reduce attack surfaces.
- **Privileges**: Never run Docker containers as the root user.
