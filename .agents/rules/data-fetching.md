---
description: Asynchronous state management and network requests
globs: "src/**/*.{ts,tsx}, app/**/*.{ts,tsx}"
alwaysApply: false
---
# Data Fetching & Server State

- **Library Mandate**: Use `@tanstack/react-query` for all server-state management. Never use raw `useEffect` blocks to fetch data.
- **Query Key Factories**: Strongly type and centralize query keys to prevent cache invalidation typos.
  ```typescript
  export const userKeys = {
    all: ['users'] as const,
    lists: () => [...userKeys.all, 'list'] as const,
    detail: (id: string) => [...userKeys.all, 'detail', id] as const,
  };