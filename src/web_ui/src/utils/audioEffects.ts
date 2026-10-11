/**
 * Web Audio and Speech Synthesis utilities for EXAMEN Hackathon Demo.
 * Provides authentic acoustic confirmation tones and synthetic voice reassurance.
 */

// Generate pleasant acoustic verification chime via Web Audio API
export function playAcousticVerificationTone(): void {
  if (typeof window === "undefined") return;
  try {
    const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
    if (!AudioCtx) return;
    const ctx = new AudioCtx();
    
    // First harmonic
    const osc1 = ctx.createOscillator();
    const gain1 = ctx.createGain();
    osc1.type = "sine";
    osc1.frequency.setValueAtTime(587.33, ctx.currentTime); // D5
    osc1.frequency.exponentialRampToValueAtTime(880.0, ctx.currentTime + 0.15); // A5

    gain1.gain.setValueAtTime(0.15, ctx.currentTime);
    gain1.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.4);

    osc1.connect(gain1);
    gain1.connect(ctx.destination);

    // Second harmonic chime
    const osc2 = ctx.createOscillator();
    const gain2 = ctx.createGain();
    osc2.type = "triangle";
    osc2.frequency.setValueAtTime(1174.66, ctx.currentTime + 0.08); // D6
    gain2.gain.setValueAtTime(0.08, ctx.currentTime + 0.08);
    gain2.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.45);

    osc2.connect(gain2);
    gain2.connect(ctx.destination);

    osc1.start(ctx.currentTime);
    osc1.stop(ctx.currentTime + 0.4);
    osc2.start(ctx.currentTime + 0.08);
    osc2.stop(ctx.currentTime + 0.45);
  } catch (err) {
    console.warn("Web Audio not supported or blocked by browser policy:", err);
  }
}

// Speak Alexa / Ambient reassurance voice
export function speakAlexaReassurance(message: string): void {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
  try {
    // Play chime first
    playAcousticVerificationTone();

    // Cancel any ongoing utterance
    window.speechSynthesis.cancel();

    setTimeout(() => {
      const utterance = new SpeechSynthesisUtterance(message);
      utterance.rate = 1.0;
      utterance.pitch = 1.05; // Slightly clear and calm Alexa tone

      // Try selecting an English female voice if available
      const voices = window.speechSynthesis.getVoices();
      const preferred = voices.find(
        (v) =>
          (v.name.includes("Samantha") ||
            v.name.includes("Victoria") ||
            v.name.includes("Google UK English Female") ||
            v.name.includes("Natural")) &&
          v.lang.startsWith("en")
      );
      if (preferred) {
        utterance.voice = preferred;
      }

      window.speechSynthesis.speak(utterance);
    }, 180);
  } catch (err) {
    console.warn("Speech synthesis error:", err);
  }
}
