# Named Settings Files (.rebset) — Design Plan

## Purpose of this document

This is a plan, not a finished feature. It records the design for letting an
operator explicitly save the Settings tab's current configuration to a file
of their choosing (via a save dialog) and reload it later (via an open
dialog), so it can be shared, backed up, or restored between sessions. It's
written up front, with decisions from Chuck (CJP) recorded inline, so Rich
and any future contributor can see why it's shaped this way before any
`.ui`/`rosetta.py` changes land.

## How settings are persisted today

Today there is exactly one settings file, at a fixed path:
`RoseEngineButlerLocal/REB_Settings_v1.ini` (actually XML despite the
extension). It holds, per axis (`X`, `Z`, `B`, `U`, `V`, `W`, `Sp0`, `Sp1`),
a `<scale>` value, and for the six linear/angular axes (not the spindles) a
free-text `<usercomment>`. It is:

- **Written** automatically at shutdown, by `REB_Display/REB_Scale_Persist.py`
  (run from `REB_Shutdown.hal`), which reads the live
  `hm2_7i92.0.stepgen.NN.position-scale` HAL pins and patches just the
  `<scale>` values into the file with a regex, leaving everything else
  untouched. Axis comments are instead saved immediately, one axis at a
  time, from `rosetta.py`'s `_save_axis_comment()` on each comment field's
  focus-out.
- **Read** automatically at Settings-tab / main-panel load, by
  `rosetta.py`'s `_load_scale_settings()` (applies `<scale>` to both the
  Settings tab's spin buttons and the live HAL pins) and
  `_load_axis_comments()` (applies `<usercomment>` to the main panel's
  comment entries).
- Single path, single implicit "current" snapshot. The user never names it,
  never chooses where it lives, and never has more than one.

This plan adds a **second, user-driven mechanism** alongside that one, not a
replacement for it: named, explicitly-saved/loaded profile files that the
operator controls the location and name of. Loading a `.rebset` file pushes
its values into the same live widgets/HAL pins that `_load_scale_settings`
already knows how to write to — so on the next shutdown,
`REB_Scale_Persist.py` naturally carries whatever was just loaded forward
into `REB_Settings_v1.ini` as the new "current" state, the same as if the
operator had retuned those values by hand. `REB_Settings_v1.ini` stays on
its current XML format and its own automatic, silent save/load — this
feature doesn't touch that path (see Decision 4 below for why).

## File format

- **Extension:** `.rebset`
- **Encoding:** JSON (replacing the ad hoc regex-patched XML used for the
  automatic file — much less fragile to parse/write correctly, and Python's
  `json` module needs no new dependency)
- **Top-level shape:**

```json
{
  "format_version": 1,
  "name": "Chuck's brass rosette setup",
  "notes": "Tighter B backlash comp for the brass box.\nRun spindle slower than usual on this one.",
  "saved_at": "2026-07-29T14:32:00",
  "axes": {
    "X":   { "scale": -196000, "comment": "" },
    "Z":   { "scale": 254427,  "comment": "" },
    "B":   { "scale": 57599,   "comment": "" },
    "U":   { "scale": 20320,   "comment": "" },
    "V":   { "scale": 20319,   "comment": "" },
    "W":   { "scale": 20320,   "comment": "" },
    "Sp0": { "scale": 57602 },
    "Sp1": { "scale": -57599 }
  }
}
```

- `axes` keys match `AXIS_STEPGEN`'s keys (already the source of truth for
  axis id ↔ stepgen channel in both `rosetta.py` and
  `REB_Scale_Persist.py`). `comment` is only meaningful for
  `COMMENT_AXES = ("X","Z","U","V","W","B")`; omit it for `Sp0`/`Sp1`.
- `name` and `notes` are the two new fields this feature adds beyond what
  today's XML file stores.

## Versioning

- `format_version` is a plain integer, starting at `1`, present at the top
  level of every `.rebset` file.
- The loader reads `format_version` first and dispatches on it. Unknown or
  newer-than-supported versions must produce a clear error dialog and abort
  the load — never guess at a schema we don't recognize.
- When the schema needs to change, bump `format_version` and add a small
  `_migrate_v1_to_v2()`-style function rather than branching the whole
  loader on version number inline. Keep migrations additive/one-directional
  (old → new); we don't need to support saving older versions back out.

## UI changes (`REB_Display/REB_Tab_Settings_v1.ui`)

The Settings tab's main content already lives inside a `GtkScrolledWindow`
(Rich's fix). New controls need to be placed **outside** that scrolled
region — anything inside it can be scrolled out of view, which is fine for
the long list of per-axis rows but wrong for controls that should always be
reachable.

- **Save Settings** / **Save Settings As...** / **Load Settings...**
  buttons, in a small `GtkBox` above the scrolled window.
- **Settings Name** — a read-only label above the scrolled window showing
  the currently active file's name (e.g. `Settings: Chucks_LRE`). **The
  name is always the current file's filename (minus `.rebset`), not a
  separately-typed field** — see Decision 2 (revised) below.
- **Notes** — a `GtkTextView` (multi-line free text, ~3 rows tall) inside
  its own small fixed-height `GtkScrolledWindow`, so long notes scroll
  within their own box rather than growing the tab. Placed above or below
  the main scrolled grid — exact position is cosmetic, TBD when this is
  built.

## Save flow

**Decision 2, revised.** The original design had the operator type a
separate "Name" field in the Save dialog, independent of the chosen
filename. Live testing showed this was confusing: renaming a `.rebset`
file (even from inside a later Save As) didn't change what was displayed,
because the display was reading the *file's embedded* `name` field, not
its actual current filename. Fixed by dropping the separate name field
entirely - **the filename is the name, everywhere**, always derived via
`os.path.splitext(os.path.basename(path))[0]` at both save and load time.
The JSON's own `name` field is still written (kept in sync with the
filename at save time, useful for a human reading the raw file) but is no
longer authoritative for what's displayed - the actual current path is.

This also motivated splitting Save into two buttons, matching ordinary
desktop-app conventions:

- **Save Settings** (`Settings_Save`): if a file is already active this
  session (`self._settings_path` is set - i.e. something was already
  loaded or saved this session), write straight back to it with **no
  dialog**. If nothing is active yet (still on the `legacy`/
  `generic_example` starting point - Decisions 5/6), this just delegates
  to Save As, since there's nowhere to "save back to".
- **Save Settings As...** (`Settings_Save_As`): always shows a
  `GtkFileChooserDialog` (`action=SAVE`), `*.rebset` filter, `~/Documents`
  default starting folder (Decision 1), current name pre-filled as a
  filename suggestion. Whatever filename the operator confirms with
  becomes the new name (and the new `self._settings_path`) going forward.

Both funnel into a shared `_save_to_path(widget, path)`: derive `name`
from `path`, read the current live values the same way
`_load_scale_settings` already knows how to (Settings tab spin buttons
for `scale`, main panel comment entries for `comment`) plus the Notes
`GtkTextView`'s contents, build the dict shown above, `json.dump(...,
indent=2)` it to `path`, update the Settings Name display, clear the
unsaved-changes flag, and record `path` as both the last-used file
(Decision 5) and this session's active file.

## Load flow

1. Operator clicks **Load Settings...**.
2. Show a `GtkFileChooserDialog` (`action=OPEN`), same `*.rebset` filter and
   default folder as Save.
3. On confirm: `json.load()` the file.
   - Malformed JSON, missing `format_version`, or an unsupported version →
     `Gtk.MessageDialog` error (same pattern already used for the "No
     spindle is enabled" warning near the top of `rosetta.py`), abort,
     leave everything currently on screen/in HAL untouched.
4. **Stop motion and disable every axis before applying anything**
   (Decision 3):
   - `c.abort()` then `c.wait_complete()` — same call already used by
     `_axis_set_scale` to cancel any in-progress move before a scale
     change lands, just applied unconditionally here rather than only for
     the one axis being changed.
   - For every axis in `AXIS_STEPGEN` (`X, Z, B, U, V, W, Sp0, Sp1`): check
     `gladevcp.<axis>_ENA-light`, and if enabled, set
     `self.halcomp[<axis>_Ena_Override] = False`. This is the exact
     disable mechanism `_axis_set_scale`/`Sp0_Set_Scale`/`Sp1_Set_Scale`
     already use for their own axis — worth extracting into one shared
     `_disable_axis(self, axis)` helper that all four call sites use
     instead of four copies of the same block.
5. Apply each axis's `scale` to that axis's `Set_Scale` spin button **and**
   the live `hm2_7i92.0.stepgen.NN.position-scale` HAL pin via `halcmd
   setp` — exactly what `_load_scale_settings` already does at startup.
6. Apply each axis's `comment` to that axis's Comment entry on the main
   panel, as `_load_axis_comments` already does.
7. Set the Notes `GtkTextView` from the loaded `notes`. The Settings Name
   display is set from the **loaded file's own filename** (not its
   embedded `name` field - see Decision 2, revised, under Save flow), and
   that path becomes this session's active file (`self._settings_path`),
   so a subsequent plain **Save Settings** writes straight back to it.
   Clear the unsaved-changes flag.
8. Nothing is written back to `REB_Settings_v1.ini` as part of loading —
   that file still only updates at the next shutdown, via the existing
   `REB_Scale_Persist.py` path, which will naturally pick up whatever was
   just loaded as the new "current" values.

## Startup behavior: reload the last-used file, or fall back (Decision 5)

By default, the Settings tab should silently reopen whatever `.rebset` the
operator last opened or saved — not the automatic, unnamed
`REB_Settings_v1.ini` snapshot, which persists on its own regardless, but
the *named* profile. The startup picker (below) should only ever appear
when there's genuinely nothing to reopen.

- **Where "last used" is recorded:** `RoseEngineButlerLocal/
  REB_Last_Settings_Path.txt` (`LAST_SETTINGS_PATH_FILE`) — a one-line
  plain-text file holding the absolute path of the last `.rebset` the
  operator actually chose via Save or the Load button (or picked from the
  startup dialog itself). It lives in `RoseEngineButlerLocal`, not this
  repo, on the same reasoning as `REB_Settings_v1.ini`: this is
  per-machine state, not something to check in. Plain text rather than
  JSON since it only ever holds a single path — nothing to structure.
  Written by `Settings_Save`, by `Settings_Load`, and by the startup
  picker's own "picked a file" branch — **never** written when falling
  back to the `generic_example` profile below, since that fallback isn't
  something the operator actually chose.
- **`_prompt_initial_settings_load`** (deferred via `GLib.idle_add`, since
  `__init__` runs before the toplevel window is realized) first reads
  `LAST_SETTINGS_PATH_FILE`. If it names a file that still exists, that
  file is loaded straight through the same `_load_settings_file` helper
  `Settings_Load` uses — no dialog, no prompt, nothing on screen.
- **No `.rebset` on record → check for legacy values first.** A machine
  that's been in use since before this feature existed still has real,
  good values sitting in `REB_Settings_v1.ini` — and those are already
  live by this point regardless (`_load_scale_settings`/
  `_load_axis_comments` apply them unconditionally, earlier in
  `__init__`, with no dependency on `.rebset` files at all). Rather than
  bury that under an empty `~/Documents` picker, `_legacy_settings_available()`
  checks whether `REB_Settings_v1.ini` has at least one real
  `<axis>`/`<scale>` entry; if so, those already-applied values are left
  exactly as they are (nothing is re-loaded/re-applied), the Settings Name
  display is set to `legacy`, and the settings are force-marked dirty —
  same reasoning as the `generic_example` case below — so the exit prompt
  (Decision 4) offers to save them as a real, named `.rebset`, migrating
  them into this feature instead of leaving them stuck as the single
  anonymous legacy file forever.
- **The picker** (shown only once neither a last-used `.rebset` nor any
  legacy `REB_Settings_v1.ini` data is available): the same
  Load dialog as the **Load Settings** button, with an extra instructional
  label explaining the choice — pick a saved `.rebset` from `~/Documents`,
  or Cancel to fall back to a starter profile.
  - **Picks a file:** loaded exactly like a normal `Settings_Load`
    (Decision-3's motion-stop/disable-all safety applies here too), and
    that path is now recorded as the new "last used" one.
  - **Cancels:** load `REB_Display/generic_example.rebset` — a small
    starter `.rebset` **shipped in this repo** (not `RoseEngineButlerLocal`,
    not `~/Documents`) whose `name` field is literally `"generic_example"`,
    so the Settings Name display picks it up with no special-casing in the
    code. Every axis's `scale` in that shipped file is `1` — deliberately
    not a plausible-looking calibration number: an uncalibrated axis
    should fail toward "barely moves" (scale far too low), never toward
    "moves far more than commanded" (scale far too high). Loading it still
    goes through the same stop-motion/disable-all-axes step as any other
    load, so this is safe even though the values themselves are
    placeholders. After loading, the settings are force-marked dirty
    (overriding the normal load behavior of clearing that flag) so the
    existing exit prompt (Decision 4) offers to save a real copy — into
    `~/Documents`, never back over the shipped repo copy, and **not**
    recorded as "last used" until the operator actually saves it
    themselves.
- **Settings_Save's Name field** is pre-filled from whatever's currently
  active (a reloaded profile, or `generic_example`) so re-saving or
  renaming it is one click instead of retyping — still just a starting
  suggestion, not a constraint; the operator can change it to anything
  before saving.

## Unsaved-changes tracking & exit prompt (Decision 4)

If the operator has changed any scale, comment, or note since the last
save/load, exiting should ask whether to save those changes to a
`.rebset` file first — the same "unsaved changes" pattern as a text
editor, layered on top of (not replacing) the existing silent
`REB_Settings_v1.ini` auto-persist, which keeps happening regardless.

**Known limitation, confirmed live:** the shutdown prompt (below) can't
appear until well after AXIS's own screen has visually torn down -
seeing the axes/DRO disappear and only then a save popup appear is
disorienting, but there's no earlier hook available (same underlying
constraint as the superseded `delete-event` attempt: AXIS's own
quit-handling isn't something this repo controls, and the HAL shutdown
script is inherently a late-stage mechanism). Two mitigations, rather
than a real fix for the ordering itself:
- The Settings Name label now appends `" *"` whenever
  `self._settings_dirty` is `True` (`_refresh_settings_name_label()`),
  the same convention as a text editor's title bar, so the operator can
  notice and save proactively while the GUI is still fully up -
  ideally making the jarring post-teardown prompt something they rarely
  see because they've already saved.
- The Tkinter root window in `REB_Scale_Persist.py` forces itself to the
  front (`-topmost`, `lift()`, `focus_force()`) so on the occasions it
  does appear, it's not easy to miss behind whatever's left on screen.

**First attempt (superseded, kept here for the record):** the original
design hooked `delete-event` on the Settings tab's own top-level
`GtkWindow`, the same technique `_set_busy_cursor` uses for
`get_toplevel()`. **Confirmed live not to work.** AXIS embeds gladevcp
tabs via XEmbed into its own Tk frame; on real exit it tears that down by
destroying the embedded window out from under the child process (visible
in the LinuxCNC log as `GdkWindow ... unexpectedly destroyed` for every
embedded gladevcp process at once), not through a normal
WM-close/delete-event negotiation. There is no supported way for an
embedded tab's own Python handler to intercept or veto AXIS's own
top-level window closing - two separate toolkits (Tk for AXIS, GTK for
the embedded panel), no shared control flow. The hook simply never fired.

**Actual design:** move the prompt to the one point in the shutdown
sequence already proven to run reliably and block - `REB_Shutdown.hal`'s
`loadusr -w python3 REB_Display/REB_Scale_Persist.py` step, the same one
that already successfully persists scale values every time. `-w` means
LinuxCNC's shutdown genuinely waits for this script to exit, so it's free
to pop a blocking dialog.

- **Dirty flag:** `self._settings_dirty`, set `True` by the existing
  per-widget change handlers (`_axis_set_scale`, `Sp0_Set_Scale`,
  `Sp1_Set_Scale`, `_save_axis_comment`, and the Notes `GtkTextView`'s
  `changed` handler) via `_mark_settings_dirty()`, and by the legacy/
  generic_example startup fallbacks. Cleared on a successful Save or Load.
- **Pending snapshot:** since `REB_Scale_Persist.py` runs in a completely
  separate process with no access to the Settings tab's live widgets,
  `_mark_settings_dirty()` (and the two fallbacks) also write a complete,
  ready-to-save `.rebset`-shaped payload to
  `RoseEngineButlerLocal/REB_Pending_Settings.rebset`
  (`PENDING_SETTINGS_PATH`) every time something changes. Removed again
  by `_clear_pending_settings_snapshot()` whenever Save or Load succeeds.
- **The shutdown prompt** (`prompt_save_pending_settings()` in
  `REB_Scale_Persist.py`, called at the end of `main()`, after the
  existing scale-persist step): if `REB_Pending_Settings.rebset` exists,
  show a Tkinter (not GTK - no gladevcp/GtkBuilder machinery needed for
  one yes/no box, and Tk is already a guaranteed dependency since AXIS
  itself is Tk-based) `askyesno` "Save changes to '<name>' before
  exiting?". Yes: writes it to `~/Documents/<name>.rebset` (name
  sanitized for use as a filename) and updates
  `LAST_SETTINGS_PATH_FILE`, so it's what silently reloads next session.
  Either way, the pending-snapshot file is removed once answered, so the
  operator isn't asked again about a change they already resolved.
- **Not yet live-tested either** - same caveat as the first attempt, just
  with a mechanism grounded in something already proven to work
  (`REB_Scale_Persist.py`'s existing, reliable execution) rather than a
  GTK signal that turned out not to apply to this embedding model. Worth
  specifically confirming: the prompt actually appears on screen (DISPLAY/
  X access should still be live at this point, but hasn't been checked),
  and it doesn't get cut off by some other timeout in the shutdown
  sequence.

## Implementation touch points

- `REB_Display/REB_Tab_Settings_v1.ui` — Save/Save As/Load buttons, Name
  display, Notes `GtkTextView` + its own `GtkScrolledWindow`, with
  `Settings_Save` / `Settings_Save_As` / `Settings_Load` signal handlers
  (naming matches the existing `<Widget>_<Action>` convention).
- `REB_Display/generic_example.rebset` — the shipped starter profile
  (Decision 5), tracked in this repo like any other config asset.
- `REB_Display/rosetta.py`:
  - `Settings_Save(self, widget)` (no dialog if a file's already active,
    otherwise delegates to Save As) / `Settings_Save_As(self, widget)`
    (always shows the file chooser) / `Settings_Load(self, widget)`
    handlers, funneling into shared `_save_to_path(self, widget, path)`
    and `_load_settings_file(self, widget, path)` helpers - the latter
    also shared with `_prompt_initial_settings_load` (Decision 5).
  - `REBSET_FORMAT_VERSION = 1`, `REBSET_DEFAULT_DIR =
    os.path.expanduser("~/Documents")`, `REBSET_GENERIC_EXAMPLE_PATH`
    (resolved relative to `rosetta.py`'s own location, so it always finds
    the copy shipped alongside it regardless of where the repo is
    checked out), and `LAST_SETTINGS_PATH_FILE` (fixed
    `RoseEngineButlerLocal` path, same convention as `SETTINGS_PATH`).
  - `_read_last_settings_path()` / `_write_last_settings_path(path)`
    helpers around `LAST_SETTINGS_PATH_FILE` - the latter also sets
    `self._settings_path`, this session's "current file" for plain Save.
  - A shared `_disable_axis(self, axis)` helper (see Load flow step 4),
    factored out of the near-identical block already duplicated in
    `_axis_set_scale`, `Sp0_Set_Scale`, and `Sp1_Set_Scale`.
  - `self._settings_dirty` flag, `PENDING_SETTINGS_PATH` constant, and
    `_write_pending_snapshot()` / `_clear_pending_settings_snapshot()`
    (see Decision 4 - the actual exit prompt itself lives in
    `REB_Scale_Persist.py`, not here).
  - Both new handlers need the same "only run in the component that owns
    these widgets" guard already used by `_load_scale_settings` /
    `_load_axis_comments` (`if self.builder.get_object(...) is None:
    return`), since `rosetta.py` is loaded once per gladevcp instance
    across several tabs/panels.
  - Worth factoring a shared `_gather_axis_settings()` /
    `_apply_axis_settings(data)` pair that both the new `.rebset` path and
    the existing `_load_scale_settings`/`_load_axis_comments`/
    `_save_axis_comment` trio can call, instead of a third independent
    walk over `AXIS_STEPGEN`/`COMMENT_AXES`. Nice-to-have cleanup, not
    required to ship v1.
- `REB_Display/REB_Scale_Persist.py` — extended with
  `prompt_save_pending_settings()`, called at the end of `main()` after
  the existing scale-persist loop. Duplicates `PENDING_SETTINGS_PATH`,
  `LAST_SETTINGS_PATH_FILE`, `REBSET_DEFAULT_DIR`, `REBSET_EXTENSION`
  from `rosetta.py` rather than importing between them - same reasoning
  as `AXIS_STEPGEN` already being duplicated across both files. Its
  prompt is two Tkinter dialogs in sequence: `askyesno` ("Save changes to
  '<name>' settings file before exiting?"), then, if yes,
  `filedialog.asksaveasfilename` so the operator sees exactly where it's
  going and can rename it there - the same "filename is the name" rule
  as `Settings_Save_As` applies to whatever they pick.
- No changes needed to `REB.hal`, `REB.ini`, or anything realtime — this is
  entirely GladeVCP/Python UI and file I/O.

## Decisions (CJP)

1. **Default save/open folder:** `~/Documents`.
2. **Where `name` comes from (revised after live testing):** originally a
   separately-typed required field. Changed to always be derived from the
   file's actual filename instead, both at save time and at load time -
   see "Save flow" for why (a typed name that could drift from the
   filename left the display showing a stale name after a rename).
3. **Load safety:** loading a `.rebset` must stop all motion in progress
   and disable all axes before applying the loaded values.
4. **Exit behavior:** if settings have changed since the last save/load,
   ask the operator whether to save before exiting.
5. **Default to reloading the last-used file:** the startup picker should
   only appear if there's no last-used `.rebset` on record. Record that
   path in `RoseEngineButlerLocal` (`REB_Last_Settings_Path.txt`). When the
   picker does appear, it carries enough instructions to be useful on its
   own; if the operator cancels it instead of picking a file, load a
   `generic_example` starter profile — read from this repo
   (`REB_Display/generic_example.rebset`), not `RoseEngineButlerLocal` —
   which then gets offered for saving into `~/Documents` on exit (via the
   existing Decision-4 prompt), and is not itself recorded as "last used"
   until the operator actually saves their own copy.
6. **Check for legacy settings before the picker:** on a machine with good
   values already sitting in `REB_Settings_v1.ini` from before this feature
   existed, don't bury that under an empty `~/Documents` picker on first
   run — recognize it (`_legacy_settings_available()`), leave it as the
   already-applied starting point, and flag it dirty so the operator is
   offered a chance to save it as a real, named `.rebset`.
7. **Save vs. Save As, and the shutdown prompt shows a file selector:**
   plain Save silently re-saves the active file with no dialog; Save As
   always prompts for a location/filename. The shutdown-time "save before
   exiting?" prompt (Decision 4) follows the same pattern - Yes brings up
   a real file selector (coaching the operator where it's about to be
   stored) rather than silently writing to a computed default path, and
   they can rename it right there.

## Testing plan

Per this repo's `CLAUDE.md`, this can only be verified live in LinuxCNC (real
machine or sim) — no compiled/static test can substitute. Once built,
exercise:

- Save As with a normal filename, change several scale values and a
  comment, Load the file back, confirm spin buttons, live HAL scale pins,
  comments, name, and notes all restore correctly.
- After a Save As, change a value and click plain **Save Settings**:
  confirm it writes straight back to the same file with no dialog.
  Freshly after Cancelling out of the startup picker (still on
  `generic_example`, nothing active), click plain **Save Settings** and
  confirm it behaves like Save As (shows the dialog) instead of trying to
  save nowhere.
- Save As with a filename that has no `.rebset` extension, or contains
  spaces, and confirm it still produces a valid, reloadable file.
- Save As, then rename the resulting file on disk (outside the app, e.g.
  via a file manager) and reload it via **Load Settings...**: confirm the
  Settings Name display shows the *new* filename, not whatever name was
  originally baked into the file's JSON.
- Load a file with a missing/garbled `format_version`, and a plain
  non-JSON text file renamed to `.rebset`, and confirm both produce an
  error dialog instead of a crash or silently-wrong values.
- With an axis enabled and/or a move in progress, Load a `.rebset` and
  confirm motion actually stops and every axis actually disables before
  any scale value changes.
- Change a scale value, then exit LinuxCNC without saving, and confirm
  the Tkinter "Save changes to '<name>' settings file before exiting?"
  prompt actually appears on screen during shutdown; confirm Yes brings
  up a real Save-As-style file selector defaulted to `~/Documents`
  (rather than silently writing somewhere), that renaming there is
  respected, and that it updates the last-used path; confirm No discards
  it cleanly; confirm Cancelling out of the file selector itself is also
  treated as "don't save" rather than erroring; confirm no prompt appears
  on a plain exit when nothing has changed since the last save/load.
- After answering that prompt either way, confirm
  `REB_Pending_Settings.rebset` is gone (so the next session isn't asked
  about the same already-resolved change again).
- Change a scale value and confirm the Settings Name label immediately
  picks up a trailing `*` (no exit needed); Save (or Save As) and confirm
  the `*` clears again.
- Confirm the Save/Save As/Load buttons and Name display stay visible
  while scrolled to the bottom of the axis grid.
- With no `REB_Last_Settings_Path.txt` **but** a real `REB_Settings_v1.ini`
  already populated (the actual first-time-test scenario on a live
  machine): confirm no dialog appears, the already-good scale/comment
  values stay exactly as restored, the Name display reads `legacy`, and
  the settings are already flagged dirty (exiting immediately offers to
  save). Save it, restart again, and confirm that saved copy — not
  `legacy` — is what silently reloads next time.
- With no `RoseEngineButlerLocal/REB_Last_Settings_Path.txt` present
  **and** an empty/missing `REB_Settings_v1.ini` (true first-ever run),
  confirm the startup picker appears: pick a real `.rebset` and confirm it
  loads exactly like the Load button would, and confirm that path is now
  recorded.
- Restart with a valid recorded last-used path: confirm the Settings tab
  comes up with that profile already loaded and **no dialog appears at
  all**.
- Restart with `REB_Last_Settings_Path.txt` pointing at a file that no
  longer exists (delete/rename it first): confirm this falls back to the
  startup picker rather than erroring out silently.
- Save As a file, then restart: confirm that save is what gets silently
  reloaded next time (Save/Save As update the recorded path, not just
  Load).
- No recorded last-used path, Cancel the startup picker: confirm all axes
  end up disabled with `scale = 1`, the Name display reads
  `generic_example`, and the settings are already flagged dirty (e.g.
  exiting immediately triggers the save prompt with no other changes
  made). Restart again without saving first: confirm the picker appears
  again rather than silently reloading `generic_example` a second time.
- From that `generic_example` state, exit and choose Save: confirm the
  Save dialog's Name field is pre-filled with `generic_example` and the
  suggested filename is `generic_example.rebset`, and confirm the file
  lands in `~/Documents`, not overwriting
  `REB_Display/generic_example.rebset` in the repo. Confirm a subsequent
  restart now silently reloads that saved copy.
