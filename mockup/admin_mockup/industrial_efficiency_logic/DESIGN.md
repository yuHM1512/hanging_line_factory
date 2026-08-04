---
name: Industrial Efficiency Logic
colors:
  surface: '#f8f9ff'
  surface-dim: '#cbdbf5'
  surface-bright: '#f8f9ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#eff4ff'
  surface-container: '#e5eeff'
  surface-container-high: '#dce9ff'
  surface-container-highest: '#d3e4fe'
  on-surface: '#0b1c30'
  on-surface-variant: '#44464f'
  inverse-surface: '#213145'
  inverse-on-surface: '#eaf1ff'
  outline: '#757780'
  outline-variant: '#c5c6d0'
  surface-tint: '#4a5d8f'
  primary: '#000000'
  on-primary: '#ffffff'
  primary-container: '#001848'
  on-primary-container: '#7082b7'
  inverse-primary: '#b3c5fe'
  secondary: '#5b5f62'
  on-secondary: '#ffffff'
  secondary-container: '#dde0e4'
  on-secondary-container: '#5f6367'
  tertiary: '#000000'
  on-tertiary: '#ffffff'
  tertiary-container: '#00174d'
  on-tertiary-container: '#6480d7'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#dae2ff'
  primary-fixed-dim: '#b3c5fe'
  on-primary-fixed: '#001848'
  on-primary-fixed-variant: '#324576'
  secondary-fixed: '#e0e3e7'
  secondary-fixed-dim: '#c3c7cb'
  on-secondary-fixed: '#181c1f'
  on-secondary-fixed-variant: '#43474b'
  tertiary-fixed: '#dbe1ff'
  tertiary-fixed-dim: '#b5c4ff'
  on-tertiary-fixed: '#00174d'
  on-tertiary-fixed-variant: '#214195'
  background: '#f8f9ff'
  on-background: '#0b1c30'
  surface-variant: '#d3e4fe'
typography:
  display-lg:
    fontFamily: Manrope
    fontSize: 32px
    fontWeight: '700'
    lineHeight: 40px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Manrope
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  title-sm:
    fontFamily: Manrope
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 24px
  body-md:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-sm:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  label-numeric:
    fontFamily: JetBrains Mono
    fontSize: 14px
    fontWeight: '500'
    lineHeight: 20px
  label-caps:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.05em
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  sidebar-width: 280px
  gutter: 24px
  container-padding: 32px
  stack-gap: 16px
  grid-columns: '12'
---

## Brand & Style
This design system is engineered for the high-throughput environment of Vietnamese garment manufacturing. The brand personality is **Professional, Precise, and Industrial**, balancing the heavy-duty nature of hanging conveyor hardware with a sophisticated, modern administrative interface. 

The visual style follows a **refined Corporate Modern** approach, drawing heavily from Material Design 3 principles but with a distinct focus on data density and operational clarity. It utilizes deep navy tones to signify authority and stability, paired with expansive white space to reduce cognitive load for factory administrators. The emotional response should be one of "controlled efficiency"—where every interaction feels deliberate and every data point is legible at a glance.

## Colors
The palette is rooted in a high-contrast industrial logic. 
- **Primary:** Deep Navy (#001848) used for core branding, primary actions, and navigational anchors. 
- **Gradients:** Primary elements utilize a subtle linear gradient (from #001848 to #002B80 at 135°) to add depth without compromising professionalism.
- **Surface Strategy:** A clean White (#FFFFFF) base is used for primary cards and content areas, while Off-white (#F4F7FB) provides a soft "mechanical" backdrop for the main application canvas.
- **Functional Colors:** Standardized semantic colors for Error, Success, and Warning are high-chroma to ensure visibility in brightly lit factory office environments.

## Typography
The typographic hierarchy is optimized for Vietnamese diacritics and technical data.
- **Headings (Manrope):** Chosen for its modern, geometric structure which conveys a sense of engineering precision.
- **Body (Inter):** Used for all administrative labels and descriptions due to its exceptional legibility at small sizes.
- **Data & Numbers (JetBrains Mono/Roboto Mono):** All throughput numbers, conveyor IDs, and timestamps must use a monospaced font to ensure vertical alignment in tables and dashboards.
- **Localization:** All labels should be in Vietnamese (Tiếng Việt), ensuring that line-heights are generous enough (minimum 1.5x for body) to accommodate stacked diacritical marks without clipping.

## Layout & Spacing
The system uses a **Fixed-Fluid hybrid** layout model:
- **Sidebar:** A fixed 280px navigation column. It features a White background with a subtle Navy-to-transparent gradient (5% opacity) originating from the top-left to define the brand anchor.
- **Main Canvas:** A fluid 12-column grid that adjusts based on viewport width.
- **Spacing Rhythm:** Based on an 8px scale. Standard page margins are set to 32px to provide a "breathable" feel amidst dense technical data.
- **Mobile Adaptation:** At the 768px breakpoint, the sidebar collapses into a bottom-sheet or "hamburger" drawer, and page padding reduces to 16px.

## Elevation & Depth
Depth is used sparingly to signify interactivity and container hierarchy:
- **Level 1 (Cards):** Uses an ambient, highly diffused shadow `(0 18px 48px rgba(21,28,40,0.05))` against the Off-white background.
- **Level 2 (Modals/Popovers):** Standard Material 3 "Elevated" shadows with a slightly darker tint to pull the element forward.
- **Surface Toning:** Instead of heavy shadows, the system relies on tonal shifts. For example, the sidebar is white while the main background is #F4F7FB, creating a natural cliff-edge depth without needing heavy borders.

## Shapes
The shape language is "Optimistically Industrial." 
- **Primary Containers:** Large cards use a generous `1.25rem` (20px) radius to soften the technical environment.
- **Interactive Elements:** Buttons and input fields use a tighter `0.8rem` (approx 12px) radius, providing a professional "tool-like" appearance that remains approachable.
- **Functional Uniformity:** All interactive targets must maintain these radii to ensure the UI feels like a singular, cohesive toolset.

## Components
- **Buttons:**
  - *Primary:* Navy gradient background, white text, 0.8rem radius.
  - *Danger:* Solid #B3261E, used for "Dừng khẩn cấp" (Emergency Stop) or "Xóa" (Delete) actions.
  - *Tertiary:* Transparent background with Navy text; used for secondary navigation or "Hủy" (Cancel).
- **Tables:**
  - No vertical or horizontal internal borders.
  - Alternate rows or standard rows use #F4F7FB background.
  - First cell (Left) and Last cell (Right) must have 12px rounded corners to create a "pill-row" effect.
- **Forms:**
  - Inputs use the Off-white (#F4F7FB) background with no borders in their default state.
  - Focus state: 2px solid Navy border.
  - Labels must be placed above the input, using `label-caps` for technical clarity.
- **Cards:**
  - Must use the 1.25rem radius and the defined ambient shadow. 
  - Padding within cards should be a consistent 24px.
- **Status Chips:**
  - Small, high-contrast pills for status like "Đang chạy" (Running), "Bảo trì" (Maintenance), or "Lỗi" (Error).