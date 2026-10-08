import { ReactNode } from "react";

interface FilterButtonProps {
  children: ReactNode;
  active?: boolean;
  onClick?: () => void;
  className?: string;
}

export function FilterButton({ children, active = false, onClick, className = '' }: FilterButtonProps) {
  const baseClass = "px-5 py-2.5 rounded-full font-mono text-[10px] tracking-widest transition-colors ";
  const activeClass = "bg-primary text-background font-bold ";
  const inactiveClass = "text-secondary hover:bg-surface-container hover:text-primary ";
  
  return (
    <button 
      onClick={onClick} 
      className={`${baseClass} ${active ? activeClass : inactiveClass} ${className}`}
    >
      {children}
    </button>
  );
}
