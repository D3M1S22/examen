export interface PitchVideoProps {
  showSubtitles?: boolean;
  language?: "it" | "en";
  primaryColor?: string;
  accentColor?: string;
}

export interface SubtitleCue {
  fromFrame: number;
  toFrame: number;
  text: string;
}

