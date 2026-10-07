# Rule: Alexa Echo Show & Multimodal Smart Display Standards

## 1. Ergonomics & Glanceability (10-Foot UI)
The web application must be fully usable when displayed on smart displays (Amazon Echo Show 8, 10, 15) as well as desktop browsers:
- **No Hover Dependencies:** All actions, disclosure widgets, and status pills must be accessible without mouse `:hover` events. Rely on active, pressed, and focus-visible states.
- **Touch Target Sizing:** Minimum tap target size of **48x48px** with at least 8px spacing between touch elements to prevent accidental taps on hardware touchscreens.
- **Typography & Scannability:**
  - Base body font should scale cleanly (minimum 16px desktop, adaptable to 18–20px for high-legibility glanceability).
  - High contrast text ratios (WCAG AAA compliant where possible) to maintain visibility under kitchen/ambient room lighting.
  - Headings and summary hints must truncate or break gracefully without pushing action buttons off-screen.

## 2. Fixed Viewports & Glanceable Information Architecture
- Echo Show devices operate primarily at **1280x800** (Echo Show 8 / 10) and **1920x1080** (Echo Show 15):
  - Avoid infinite scrolling containers with no clear end. Favor card decks, horizontal pagination, or constrained lists with clear sticky headers.
  - Critical live telemetry (Gatekeeper qualification badge, device connection state) must remain docked and visible in the top status bar regardless of feed scroll.
- Split-screen / Dashboard Grid:
  - On widescreen (1920px+), use a 3-column split view (Live Gatekeeper Telemetry | Active Tasks & Actions | Social & Topic Memory).
  - On Echo Show viewports (1280px), collapse gracefully to a 2-column or tabbed card deck with persistent bottom/top navigation.

## 3. Multimodal Voice Synchronization
- Every visible `PlannedTask` card or `ActionItem` must surface an explicit title and step list matching what Alexa announces via MCP serving tools (`src/serving/tools/action_tools.py`).
- Include prominent visual confirmation states (e.g., active highlight border or glowing accent) when an item is being actively executed or queried by Alexa.