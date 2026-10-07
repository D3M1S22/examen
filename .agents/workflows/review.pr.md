# Pull Request Review Workflow

When invoked via `/review.pr`, execute this exact sequence:

1. **Diff Analysis**: Run `git diff main...HEAD` in the terminal to gather all current changes.
2. **Security Audit**: Scan the diff for accidentally committed secrets, hardcoded credentials, or SQL injection vectors.
3. **Performance Check**: Identify any O(N^2) loops, missing database indexes in Prisma/Drizzle schemas, or missing React memoizations.
4. **Architectural Compliance**: Verify that Controller logic has not leaked into Services, and UI components have not absorbed data-fetching logic.
5. **Report Generation**: Output a markdown summary bulleting any blocking issues, suggestions, and a final "Approve" or "Request Changes" verdict.