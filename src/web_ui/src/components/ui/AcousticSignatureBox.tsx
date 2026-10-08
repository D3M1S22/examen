import { ReactNode } from "react";

interface AcousticSignatureBoxProps {
  label: string;
  confidence: string;
  description: ReactNode;
  icon?: ReactNode;
  waveformType?: 'flat' | 'active' | 'spiked';
}

export function AcousticSignatureBox({ label, confidence, description, icon, waveformType = 'active' }: AcousticSignatureBoxProps) {
  return (
    <div className="bg-[#121316] border border-surface-container-highest rounded-lg p-space-lg mb-8">
      <div className="flex items-center justify-between mb-6">
         <div className="font-mono text-[9px] text-secondary uppercase tracking-widest">{label}</div>
         <div className="font-mono text-[9px] text-secondary uppercase tracking-widest">{confidence}</div>
      </div>
      <div className="flex items-start gap-3 text-primary text-[12px] font-sans mb-6">
        {icon && <div className="shrink-0 mt-0.5">{icon}</div>}
        <div>{description}</div>
      </div>
      {/* Waveform renderer */}
      <svg width="100%" height="40" viewBox="0 0 400 40" preserveAspectRatio="none" className="text-secondary stroke-current" fill="none" strokeWidth="1.5">
         {waveformType === 'flat' && <path d="M0,20 L400,20" strokeWidth="1" />}
         {waveformType === 'active' && <path d="M0,20 L150,20 L160,10 L170,30 L180,5 L190,20 L400,20" />}
         {waveformType === 'spiked' && <path d="M0,20 L50,20 L55,5 L60,35 L65,15 L70,25 L75,20 L400,20" />}
      </svg>
    </div>
  );
}
