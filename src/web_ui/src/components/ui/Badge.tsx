import { ReactNode } from "react";

interface BadgeProps {
  children: ReactNode;
  variant?: 'outline' | 'filled' | 'active';
  className?: string;
  dot?: 'active' | 'idle' | 'none';
}

export function Badge({ children, variant = 'outline', className = '', dot = 'none' }: BadgeProps) {
  let baseClass = "px-3 py-1.5 rounded-full flex items-center gap-2 font-mono text-[9px] tracking-[0.2em] uppercase whitespace-nowrap ";
  
  if (variant === 'outline') {
    baseClass += "border border-surface-container-highest text-secondary ";
  } else if (variant === 'filled') {
    baseClass += "bg-surface-container-highest text-primary font-bold ";
  } else if (variant === 'active') {
    baseClass += "bg-surface-container-highest border border-surface-container-highest text-primary font-bold ";
  }

  return (
    <div className={baseClass + className}>
      {dot === 'active' && <div className="w-1.5 h-1.5 rounded-full bg-primary shrink-0"></div>}
      {dot === 'idle' && <div className="w-1.5 h-1.5 rounded-full bg-outline-variant shrink-0"></div>}
      {children}
    </div>
  );
}
