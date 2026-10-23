import React from "react";
import { THEME } from "../constants";

interface HeaderBarProps {
  currentSection: string;
}

export const HeaderBar: React.FC<HeaderBarProps> = ({ currentSection }) => {
  return (
    <div
      style={{
        position: "absolute",
        top: 36,
        left: 60,
        right: 60,
        height: 56,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        zIndex: 50,
      }}
    >
      {/* Brand & Tagline */}
      <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
        <div
          style={{
            fontSize: 24,
            fontWeight: 800,
            letterSpacing: "0.08em",
            color: THEME.textPrimary,
            display: "flex",
            alignItems: "center",
            gap: 10,
          }}
        >
          <span
            style={{
              display: "inline-block",
              width: 12,
              height: 12,
              borderRadius: "50%",
              backgroundColor: THEME.amazonOrange,
              boxShadow: `0 0 14px ${THEME.amazonOrange}`,
            }}
          />
          EXAMEN
        </div>
        <div
          style={{
            height: 20,
            width: 1,
            backgroundColor: THEME.bgCardBorder,
          }}
        />
        <div
          style={{
            fontSize: 14,
            fontWeight: 500,
            color: THEME.textSecondary,
            letterSpacing: "0.03em",
          }}
        >
          Ambient Executive Intelligence
        </div>
      </div>

      {/* Section Pill & Live URL */}
      <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
        <div
          style={{
            padding: "6px 14px",
            borderRadius: 20,
            backgroundColor: "rgba(255, 153, 0, 0.12)",
            border: `1px solid rgba(255, 153, 0, 0.3)`,
            color: THEME.amazonOrange,
            fontSize: 13,
            fontWeight: 600,
            letterSpacing: "0.04em",
            textTransform: "uppercase",
          }}
        >
          {currentSection}
        </div>

        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            padding: "6px 16px",
            borderRadius: 20,
            backgroundColor: "rgba(255, 255, 255, 0.05)",
            border: `1px solid rgba(255, 255, 255, 0.1)`,
            color: THEME.textPrimary,
            fontSize: 13,
            fontWeight: 500,
          }}
        >
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: "50%",
              backgroundColor: THEME.successGreen,
            }}
          />
          examen.devgiov.com
        </div>
      </div>
    </div>
  );
};

