---
description: Core architectural constraints for modern React SPAs or Next.js applications
globs: "src/**/*.{ts,tsx}, app/**/*.{ts,tsx}"
alwaysApply: true
---
# React Web Architecture Standards

- **Component Typologies**: Maintain a strict separation between "Smart" (Container) components and "Dumb" (Presentational) components. Presentational components must have zero side effects and rely entirely on props.
- **Strict Typing**: Use strict TypeScript. Avoid `any` entirely. Avoid `Partial<T>` when creating component props; explicitly define required vs. optional (`?`) fields. 
- **Custom Hooks**: Extract complex state logic and `useEffect` orchestrations into custom hooks (`useFeatureName.ts`). Components should ideally only consume hooks and return JSX.
- **Immutability**: Never mutate state objects directly. Use functional state updates `setState(prev => ...)` or leverage Immer for deeply nested object updates.