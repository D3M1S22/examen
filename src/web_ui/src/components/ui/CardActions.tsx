import React from "react";

interface CardActionsProps {
  /** What the buttons act on, for the accessible labels (e.g. "action", "routine") */
  noun: string;
  onEdit?: () => void;
  onDelete?: () => void;
}

/** Edit (✏️) and delete (🗑️) icon buttons of a result card. */
export function CardActions({ noun, onEdit, onDelete }: CardActionsProps) {
  return (
    <div className="flex items-center gap-1">
      {onEdit && (
        <button
          type="button"
          onClick={onEdit}
          className="p-1.5 rounded-md hover:bg-white/10 text-secondary hover:text-primary transition-colors"
          title={`Edit ${noun}`}
          aria-label={`Edit ${noun}`}
        >
          ✏️
        </button>
      )}
      {onDelete && (
        <button
          type="button"
          onClick={onDelete}
          className="p-1.5 rounded-md hover:bg-rose-950/60 text-secondary hover:text-rose-400 transition-colors"
          title={`Delete ${noun}`}
          aria-label={`Delete ${noun}`}
        >
          🗑️
        </button>
      )}
    </div>
  );
}
