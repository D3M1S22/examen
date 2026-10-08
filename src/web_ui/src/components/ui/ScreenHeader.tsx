import { ReactNode } from "react";

interface ScreenHeaderProps {
  directive: ReactNode;
  title: string;
  description: ReactNode;
  rightElement?: ReactNode;
  icon?: ReactNode;
}

export function ScreenHeader({ directive, title, description, rightElement, icon }: ScreenHeaderProps) {
  return (
    <div className="card-elevated p-space-xl flex flex-col md:flex-row justify-between items-start gap-space-lg mb-space-lg bg-surface-container-low border-surface-container-highest">
      <div className="flex gap-space-lg max-w-4xl">
        {icon && (
          <div className="w-16 h-16 rounded-xl bg-surface-container-highest border border-outline-variant flex items-center justify-center text-primary shrink-0">
            {icon}
          </div>
        )}
        <div>
          <div className="font-mono text-[9px] text-secondary uppercase tracking-[0.2em] mb-4 flex items-center gap-3">
          <span className="w-1.5 h-1.5 bg-secondary rounded-full inline-block"></span>
          {directive}
        </div>
        <h2 className="font-serif text-[32px] md:text-[36px] leading-tight text-primary uppercase mb-4 font-normal">
          {title}
        </h2>
        <p className="font-sans text-body-md text-secondary leading-relaxed max-w-3xl pr-4">
          {description}
        </p>
        </div>
      </div>
      {rightElement && (
        <div className="shrink-0 flex flex-col items-end gap-3 self-start md:self-auto mt-4 md:mt-0">
          {rightElement}
        </div>
      )}
    </div>
  );
}
