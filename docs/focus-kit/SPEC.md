# Mosaic Focus — UI Spec ("Quiet Zellige")

Version 1 · 27 Oct 2026 · target: `mac/` in `sameer-hoda/wa-slash-commands` (macOS 14+, SwiftUI, Swift 5.10)

Live preview: open `preview/index.html` in a browser (light/dark toggle, hover, mark-done, refresh all work).

---

## 1. What we're building

One job: **show the user the ten work things they must not drop, re-ranked every hour, and nothing else.**

Two surfaces, one store:

| Surface | When | Size | Content |
|---|---|---|---|
| **Menu-bar popover** | Click the star in the menu bar | 380 pt wide, ≤ 600 tall | Header + all 10 rows + footer |
| **Focus window** | "Open Mosaic" in popover, Dock click, or launch after onboarding | min 640×600, content max 820 | Header + 3 hero tiles + 7 rows + footer |

Onboarding (key → pair → Me chat) stays as is but is re-skinned with the same tokens (§9). Once onboarding is done, the Focus window replaces the setup window.

---

## 2. Review of the current Mac app (bf97a75)

What's there is a solid **shell**, not yet a product UI:

- `MosaicApp.swift` — `MenuBarExtra` with the default **menu** style (so no rich popover is possible), a retained AppKit `NSWindow` for setup, and an empty `Settings` scene.
- `Onboarding.swift` — clean 4-stage setup. Unthemed system look. `MenuPopover` is 3 lines (status, summary, two buttons).
- `SettingsView` — five tabs that are placeholder `Text`s.
- `BridgeState.swift` — polls `/setup/state` every 2 s forever, even after setup completes and when no window is visible.
- `Supervisor.swift` — bridge lifecycle, Keychain key, crash-loop guard. Good; leave it alone.

Issues to fix while integrating:

1. **"Open Setup" doesn't reopen a closed window.** It only calls `activate`. It must call `makeKeyAndOrderFront` on the retained window (or the new Focus window).
2. **Menu-bar icon** is SF `message.fill` — generic and reads as "Messages". Replace with an 8-point star template image (drawn in code, §8).
3. **No Focus data path.** There's no `/focus/top10` endpoint; `/pending` in `sandbox/approaches/pending.py` is per-chat, WhatsApp-formatted text. The UI needs a cross-chat JSON digest (§6).
4. Stop the 2 s setup poll once `mechat_jid` is set; Focus has its own hourly schedule.
5. Remove placeholder Settings tabs or fill them (§9); empty tabs read as broken.

---

## 3. Design direction

**"Quiet Zellige."** Apple-minimal layout and type, with Moroccan zellige tilework as the only ornament. The palette is taken from the app icon: cream marble, glazed teal, terracotta, umber.

Principles:

1. **The mosaic is the ground, never the content.** Pattern lives on the window edges and the popover's top band, at ~5–10 % strength, faded out wherever text sits.
2. **One colour, one meaning.** Glaze colours encode state (§4.2). Nothing is coloured for decoration.
3. **Editorial numerals.** Ranks are set in New York (Apple's serif) like museum labels; everything else is SF Pro.
4. **The ten tasks *are* the mosaic.** A 10-tile rosette in the header. Each tile = one task in its glaze. Open = outlined, done = solid ("laid"). The centre shows how many remain.
5. **Calm motion.** Only three motions exist: hover lift, re-rank reorder, staggered "tile-laying" on refresh. All disabled under Reduce Motion.

References studied (Mobbin): SCMP "My Daily 5" for big serif rank numerals in a curated short list; Asana Home for a single summary card above the list; Tiimo To-do for soft priority tinting; Attio My Tasks for small inline metadata chips.

---

## 4. Tokens (source of truth: `Theme/MosaicTheme.swift`)

### 4.1 Colour

| Token | Light | Dark | Use |
|---|---|---|---|
| `plaster` | `#F7F2EA` | `#17110E` | Window ground |
| `plasterDeep` | `#EFE6D8` | `#120D0B` | Behind pattern edges |
| `card` | `#FFFDF9` @ 78 % | `#221A16` @ 72 % | On top of `.regularMaterial` |
| `cardStroke` | umber @ 8 % | cream @ 10 % | 0.5 pt card border |
| `ink` | `#2A1F1A` | `#F3EADB` | Titles |
| `inkSecondary` | ink @ 62 % | ink @ 62 % | "Why" lines, chips |
| `inkTertiary` | ink @ 40 % | ink @ 40 % | Ranks 4–10, eyebrow, footer |
| `teal` | `#1F6F6B` | `#4FB3AA` | **Note to self** |
| `terracotta` | `#B9562F` | `#E07E57` | **Critical / overdue** |
| `ochre` | `#C48A1E` | `#E2B04F` | **High** · refreshing dot |
| `indigo` | `#2F4E7A` | `#7FA3D6` | **Normal** · waiting on them |
| `cream` | `#E9D9BB` | `#5A4A3A` | Pattern stars, empty-state medallion |
| `grout` | umber @ 7 % | cream @ 8 % | Dividers, hover fill |

### 4.2 Tone rules (one function: `FocusItem.tone`)

1. `source == self_note` → **teal**, always. The user's own voice wins.
2. else `urgency` → critical **terracotta**, high **ochre**, normal **indigo**.
3. Due chip turns **terracotta** with `exclamationmark.circle` when overdue, regardless of tone.

### 4.3 Type

| Role | Font | Size / weight |
|---|---|---|
| Eyebrow date | SF Pro, expanded width, uppercase, +1.2 kern | 11 semibold |
| Title "Your ten" | New York | 26 semibold (popover 22) |
| Headline | SF Pro | 13 regular, 2 lines max |
| Hero rank | New York | 34 regular |
| Row rank | New York | 17 regular, tabular |
| Hero title | SF Pro | 15 semibold, 2 lines |
| Row title | SF Pro | 13 semibold, 2 lines |
| Why | SF Pro | 12 regular, 1 line in rows (3 on hover), 3 in heroes |
| Chip | SF Pro | 10.5 medium |
| Footer | SF Pro, monospaced digits | 11 regular |

### 4.4 Space, shape, motion

- 8-pt grid with 4-pt half steps: `2 4 8 12 16 24 32`.
- Radii (continuous corners): chip 6, row 10, card 14, window 18.
- Card = `.regularMaterial` + `card` tint + 0.5 pt `cardStroke` + shadow `black 5 %, r12, y4`. **Only** heroes and the 4–10 list container are cards. Rows are not.
- Motion: hover `spring(0.25, 0.9)`; reorder `spring(0.45, 0.85)`; settle `easeOut 0.35`; refresh stagger 35 ms per row.

---

## 5. Components (all in `Sources/Mosaic/Focus/`)

| Component | File | Notes |
|---|---|---|
| `ZelligeBackground(fade:cell:intensity:)` | Theme/ZelligeBackground.swift | Canvas. `.topBand(height:)` for popover, `.vignette` for window, `.none` for small wells. Hidden under Increase Contrast. |
| `Tessera(shape:color:filled:size:)` | Theme/ZelligeBackground.swift | Single tile glyph: `.star` / `.diamond` / `.square`. Used everywhere a dot would be. |
| `FocusHeader` | Views/FocusComponents.swift | Eyebrow date, "Your ten", headline, rosette. |
| `ProgressRosette` | Views/FocusComponents.swift | 10 tiles on a ring, open count in centre, VoiceOver "7 of 10 still open". |
| `MetaChip` / `ItemChips` | Views/FocusComponents.swift | Chat or "Note to self", due, "Waiting on them". Max 3 chips. |
| `RankNumeral` | Views/FocusComponents.swift | Serif, tabular. |
| `RowActions` / `IconButton` | Views/FocusComponents.swift | "Open in WhatsApp" (1:1 chats only) and Mark done/undo. Visible on hover / focus. |
| `FocusRow` | Views/FocusRow.swift | Compact row. |
| `HeroTile` + `GlazeStrip` | Views/FocusRow.swift | Ranks 1–3 in the window; leading strip of 6 tiles carries the tone. |
| `FocusPopover` | Views/FocusSurfaces.swift | Menu-bar surface. |
| `FocusWindowView` | Views/FocusSurfaces.swift | Window surface. |
| `RefreshFooter` + `StatusDot` | Views/FocusSurfaces.swift | "Updated 12 min ago · next 8:56 PM", ↻ (⌘R), open-window button. |
| `SkeletonList` / `AllClearState` | Views/FocusSurfaces.swift | First load / nothing pressing. |

### 5.1 Anatomy

```
Row (popover: all 10; window: 4–10)
┌───────────────────────────────────────────────────────────────┐
│ 4  ✦  Reply to Meera on the iOS checkout redirect       ⤴  ✓ │  ← actions on hover
│        Blocking QA sign-off for Thursday's launch.            │  ← why (1 line → 3 on hover)
│        [💬 Launch Squad] [⏱ Today] [⧗ Waiting on them]        │  ← ≤3 chips
└───────────────────────────────────────────────────────────────┘
 rank(22, trailing) · tessera(10) · 8pt gaps · 12pt h-padding · 10pt v-padding

Hero (window ranks 1–3, equal-width 3-column, min height 168)
┌─────────────────────┐
│✦ 1               ⤴ ✓│
│◆ Send Acme the Q4   │
│✦ deck               │
│◆ They asked for it  │
│✦ by Monday — the…   │
│◆ [Launch Squad][Overdue]
└─────────────────────┘
```

### 5.2 States

| State | Popover | Window | Footer |
|---|---|---|---|
| First launch, no data | `SkeletonList` (5 outlined tiles + bars, breathing) | same inside a card | "Waiting for first ranking…" (ochre diamond) |
| Loaded | 10 rows | 3 heroes + 7 rows | "Updated 12 min ago · next 8:56 PM" (teal) |
| Refreshing | keep old rows | keep old | "Re-ranking your chats…", ↻ spins (ochre) |
| Failed | keep old rows | keep old | "Bridge offline · showing 2 hours ago" (terracotta) |
| Empty result | `AllClearState` medallion: "Nothing pressing" | same | normal |
| Item done | strikethrough, tile outline, moves to bottom, why/chips hidden | leaves hero row; next open item is promoted | — |

"Done" is local only (UserDefaults set of ids). Ids the next refresh no longer returns are forgotten.

---

## 6. Data contract (the only thing the back end must provide)

`GET http://127.0.0.1:8081/focus/top10` → cached digest (fast).
`GET /focus/top10?refresh=1` → re-rank now (may take up to 90 s).
Fallback: `~/Library/Application Support/Mosaic/focus.json` with the same body (`FileFocusProvider`).

```json
{
  "generated_at": "2026-10-27T19:45:00+05:30",
  "headline": "Launch is gated on pricing copy and the Acme deck.",
  "items": [
    {
      "id": "417695aae597",
      "rank": 1,
      "title": "Send Acme the Q4 deck",
      "why": "They asked for it by Monday — the deal review depends on it.",
      "chat_name": "Launch Squad",
      "chat_jid": "120363012345678901@g.us",
      "source": "deadline",
      "urgency": "critical",
      "due": "2026-10-27T16:00:00+05:30",
      "waiting_on": "you",
      "last_activity": "2026-10-27T18:10:00+05:30"
    }
  ]
}
```

| Field | Type | Rule |
|---|---|---|
| `id` | string | **Stable across refreshes** for the same obligation (e.g. sha1 of `chat_jid + normalized topic`). Drives animations and "done" memory. |
| `rank` | 1–10 | Unique. |
| `title` | ≤ 60 chars | Imperative, starts with a verb. |
| `why` | ≤ 100 chars | Consequence or blocker, not a quote. |
| `chat_name` | string | "Note to self" when `source = self_note`. |
| `chat_jid` | string? | `…@s.whatsapp.net` enables "Open in WhatsApp". Groups have no deep link. |
| `source` | `self_note` `ask` `commitment` `deadline` `follow_up` | |
| `urgency` | `critical` `high` `normal` | At most 3 critical. |
| `due` | ISO-8601? | Omit if unknown. Never invent. |
| `waiting_on` | `you` `them` | |
| `last_activity` | ISO-8601? | |

Full sample: `Fixtures/top10.sample.json`.

### 6.1 Ranking rubric (so the UI semantics hold)

The back end is out of scope for this spec, but the UI assumes:

- Input = **non-archived** chats only, filtered to **work-related** ones (the model classifies; personal/family/banter excluded).
- **Messages the user sent to their own Me chat are the strongest signal.** Every open self-note is a candidate and is boosted one urgency level.
- Next: direct asks of the user, the user's own commitments ("I'll send it tonight"), explicit deadlines, threads waiting on someone else.
- Drop anything resolved later in the thread.
- Exactly ≤ 10 items, ranked by (deadline proximity, who's blocked, self-note boost, recency).

---

## 7. Refresh behaviour (`FocusStore`)

- On launch: fetch cached digest immediately.
- A 60 s ticker checks `now ≥ lastSuccess + 60 min`; if so, fetch. (A minute ticker, not a one-hour timer, keeps the schedule right after sleep and clock changes.)
- On `NSWorkspace.didWakeNotification`: same check.
- ⌘R / ↻: `refresh(force: true)` → `?refresh=1`.
- Never clear the list during a refresh; never stack two refreshes.
- Errors are humanized: "Bridge offline", "Gemini is slow — will retry", "Couldn't refresh".

---

## 8. Menu-bar icon

Template image: 8-point star (`Tessera` geometry), 16 pt, drawn into an `NSImage` with `isTemplate = true`. When `openCount > 0` and any item is critical + overdue, show the count next to the star (`MenuBarExtra` label `HStack { Image(nsImage:) ; Text("3") }`). Error state: `exclamationmark.triangle` as today.

---

## 9. Re-skinning existing screens (light touch)

- **Onboarding window:** background `ZelligeBackground(fade: .vignette)`; put the stage content in a `.mosaicCard()`; `StatusLine` dot → `Tessera(.diamond)` in teal/ochre/terracotta; header title in New York 22. Keep copy and logic unchanged.
- **Settings:** keep only tabs with real controls: *General* (Launch at login — wired to `Supervisor.setLoginItem`, Refresh interval: 30 min / 1 h / 2 h), *Gemini* (key status + Replace key), *WhatsApp* (connected number, Unpair → `/setup/reset`). Delete Privacy/Advanced until they have content.
- Windows: `titlebarAppearsTransparent = true`, `.fullSizeContentView`, `titleVisibility = .hidden`, so the zellige ground runs under the traffic lights.

---

## 10. Accessibility

- Every row is one VoiceOver element: "Number 4. Reply to Meera… Blocking QA… From Launch Squad. Overdue." with a custom action "Mark done".
- Colour is never the only signal: overdue has an icon + word; self-note has a chip with words.
- Increase Contrast removes the pattern entirely.
- Reduce Motion removes hover scale, stagger, reorder springs and the skeleton breathing.
- Keyboard: ⌘R refresh; Tab moves through rows; actions appear on focus as well as hover.
- Text contrast: `ink` on `plaster` ≥ 12:1; `inkSecondary` ≥ 5:1 in both themes.

---

## 11. Don'ts

- No gradients other than the pattern fade mask. No glassy blobs, no emoji as icons.
- Don't put the pattern behind text at full strength, and don't animate it.
- Don't add more than 3 chips per item or more than 10 items.
- Don't colour by chat or by person.
- Don't use hex in views; use `Mosaic.Palette`.
