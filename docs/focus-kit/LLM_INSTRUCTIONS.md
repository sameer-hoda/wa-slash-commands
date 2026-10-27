# Instructions for the coding LLM

Paste this file (plus `SPEC.md`) into your coding agent, with the `wa-slash-commands` repo open.

---

## Your task

Add the **Mosaic Focus** UI to the macOS app in `mac/`. It shows the user's top 10 work tasks in a menu-bar popover and a main window, re-ranked hourly, in the "Quiet Zellige" theme described in `SPEC.md`. The Swift files in this kit are complete and meant to be dropped in as-is. Your job is to place them, wire them into `MosaicApp.swift`, fix the listed shell issues, and verify.

**Do not change** `Supervisor.swift`, the Go bridge, packaging, or the onboarding logic in `BridgeState.swift`. Do not touch back-end LLM code unless step 6 applies.

## Steps

### 1. Copy files

Copy the kit's `Sources/Mosaic/Focus/` folder to `mac/Sources/Mosaic/Focus/` (SwiftPM picks up subfolders automatically; `Package.swift` needs no change). Copy `Fixtures/top10.sample.json` to `mac/Tests/Fixtures/` if a test target exists, otherwise to `mac/tools/`.

```
mac/Sources/Mosaic/Focus/
  Theme/MosaicTheme.swift        tokens (colour, type, space, motion)
  Theme/ZelligeBackground.swift  pattern + Tessera glyph
  Model/FocusItem.swift          JSON contract
  Model/FocusStore.swift         hourly refresh, providers, done-state
  Model/FocusSample.swift        preview data
  Views/FocusComponents.swift    header, rosette, chips, buttons, card style
  Views/FocusRow.swift           row + hero tile
  Views/FocusSurfaces.swift      popover, window, footer, empty/loading
  FocusWindowing.swift           NSWindow helper + menu-bar star icon
```

### 2. Wire into `MosaicApp.swift`

Add a store and switch the menu-bar extra to the window style:

```swift
@StateObject private var focus = FocusStore(provider: BridgeFocusProvider())
```

In `init()`, create it alongside the others (same pattern as `supervisor`/`setup`):

```swift
let store = FocusStore(provider: BridgeFocusProvider())
_focus = StateObject(wrappedValue: store)
```

and in the launch `DispatchQueue.main.async` block, open the right window:

```swift
sup.start(); mod.start()
if UserDefaults.standard.bool(forKey: "onboarded") {
    FocusWindow.show(store: store); store.start()
} else {
    showSetupWindow(supervisor: sup, setup: mod)
}
```

Replace the `MenuBarExtra` scene:

```swift
MenuBarExtra {
    if setup.state.mechat_jid.isEmpty {
        MenuPopover(supervisor: supervisor, setup: setup)   // existing, until onboarded
    } else {
        FocusPopover(store: focus, openWindow: { FocusWindow.show(store: focus) })
    }
} label: {
    if supervisor.menuIcon == "exclamationmark.triangle" {
        Image(systemName: "exclamationmark.triangle")
    } else {
        Image(nsImage: MenuBarStar.image)
    }
}
.menuBarExtraStyle(.window)
```

When onboarding reaches `DoneStage` (i.e. `mechat_jid` becomes non-empty), set `@AppStorage("onboarded") = true`, close the setup window, call `FocusWindow.show(store:)` and `focus.start()`. Do this from an `.onChange(of: setup.state.mechat_jid)` in `OnboardingView` via a callback closure on `SetupModel` (e.g. `onOnboarded`), matching how `onKeyValidated` already works.

The onboarding header keeps using `NSApp.applicationIconImage`; the star is only for the menu bar.

### 3. Fix shell issues (SPEC §2)

1. `MenuPopover` "Open Setup" → call `showSetupWindow(...)` so a closed window reopens (it's retained; `makeKeyAndOrderFront` is enough).
2. `SetupModel`: after `mechat_jid` is non-empty, slow the poll from 2 s to 30 s.
3. `SettingsView`: replace placeholder tabs per SPEC §9. *General* gets "Launch at login" (`Supervisor.setLoginItem`) and a refresh-interval picker bound to `@AppStorage("focus.intervalMinutes")` (30/60/120). `FocusStore.interval` already reads that key (default 60). Remove *Privacy* and *Advanced*.

### 4. Re-skin onboarding (SPEC §9, light touch)

Wrap `OnboardingView`'s `VStack` in `.mosaicCard()` with padding, place it over `ZelligeBackground(fade: .vignette)`, and swap `StatusLine`'s `Circle()` for `Tessera(shape: .diamond, color: …, size: 8)` using `Mosaic.Palette.teal / ochre / terracotta`. Make the setup window `fullSizeContentView` + transparent titlebar like `FocusWindow`. Do not change any copy or stage logic.

### 5. Snapshot mode

Extend `renderShotAndExitMain()`: if `--render-shot-focus <path>` is passed, render `FocusWindowView(store:)` with a `FocusStore(provider: SampleFocusProvider())` (call `await store.refresh(force: false)` first) at 760×780 and write the PNG. Never start a supervisor in this mode.

### 6. Back-end endpoint (only if `/focus/top10` doesn't exist yet)

The UI reads `GET http://127.0.0.1:8081/focus/top10` (and `?refresh=1`). If the endpoint isn't there, **don't build ranking logic here** — add a stub route in `bridge/setup_web.go` that serves `$STORE_DIR/focus.json` (404 if absent), and leave a TODO for the owner's Gemini pipeline to write that file using the schema in SPEC §6. `FocusStore` shows the skeleton until data arrives.

## Rules

- Use only `Mosaic.*` tokens in views; no hex, no new colours.
- macOS 14 APIs only. No third-party packages.
- Keep every animation behind `withAnimationIfAllowed` or a Reduce Motion check.
- Keep all user-facing copy exactly as written in the kit.

## Acceptance checklist

- [ ] `./build.sh` succeeds with zero warnings in `Focus/`.
- [ ] Xcode previews "Popover" and "Window" render with sample data in light and dark.
- [ ] Menu-bar shows the star; clicking opens a 380-pt popover with all 10 rows and the zellige band at the top.
- [ ] Window shows 3 hero tiles + 7 rows; marking a hero done promotes the next item; undo works; state survives relaunch.
- [ ] Footer reads "Updated N min ago · next h:mm"; ⌘R spins the icon and re-fetches with `?refresh=1`.
- [ ] With the bridge stopped, the list stays and the footer says "Bridge offline · showing …".
- [ ] System Settings → Accessibility → Increase Contrast removes the pattern; Reduce Motion removes all motion.
- [ ] VoiceOver reads each row as one element with a "Mark done" action.
- [ ] `--render-shot-focus /tmp/focus.png` writes a PNG and exits without starting the bridge.
- [ ] Existing `pytest` and Go tests still pass.
