# Design

Pinned direction: Apple HIG with native macOS conventions, interpreted within the existing cross-platform webview. Mode: Operate. Calm hierarchy, compact controls, stable navigation, readable state and one emphasized task action per screen.

Use a persistent labeled sidebar, a screen toolbar, flat inset groups, separators and focused inspectors. Keep all seven screens (Modules, Samples, Logo, Stems, Install the mod, Settings and Drive) and every existing control. Modules uses a full-width list. The dedicated Install the mod screen contains the selection recap, destination and prerequisites; manual key management remains in its optional settings. Other inspectors may stack at compact widths without hiding primary actions or introducing horizontal scroll.

Use only the specified system font stack. Draw original line icons with inline SVG or CSS. No raster assets, bundled Apple fonts, CDN, framework or build tooling.

Keep all design tokens in one top-of-file CSS region. Use separate semantic light/dark palettes, System/Light/Dark override, blue accent and restrained success/warning/destructive roles. Preview theme is independent of application theme. Runtime pad colors and artwork are content.

Use 4 px spacing increments, 32 px normal control targets, 28 px absolute minimum targets, deliberate focus rings and 160-240 ms state-change motion. Respect reduced motion. No decorative animation.

Every applicable asynchronous task has empty/prerequisite, loading, progress, error and success states. Destructive actions use a named modal confirmation. Legal acquisition retains scrolling and explicit consent. Preserve keyboard navigation, editing focus, accessible names, drafts and all Python contracts.

Validate both languages and themes at 880x560 and 1440x900 in the actual app. Run one finish review, fix its findings, and stop after a bounded confirmation. Record untested environments and unresolved issues without claiming certification.

Stem Preview shows one full-track waveform with direct mouse/keyboard seeking and a play/pause control; it has no origin selector, refresh button or separate seek bar. The track picker is inside Preview. Source buttons (USB and XML) sit side by side. Preparation writes to the selected USB drive, always includes waveforms, and leaves only actionable track problems visible. Hardware guides and their mocks sit with their individual modules.

There is no Tutorial navigation destination. Preparation screens provide contextual instructions, and Install the mod includes First installation. Hardware guides retain their progress when modules rerender. Harmonic previews remain inline. Emergency disable instructions are permanent text in Drive, with renaming or deletion of autoexec.bin as alternatives.
