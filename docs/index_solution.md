# Sp0 Spindle Indexing (M19 Orient) — Root Cause History & Fix Rationale

## Purpose of this document

The Indexing panel's Sp0 "Fwd"/"Rev" buttons are supposed to rotate the Sp0
spindle by a fixed step (default 90°) and stop, so the operator can use the
spindle like a dividing head. When this was first tested, pressing the
buttons did nothing at all. Getting it to work correctly required fixing a
chain of unrelated problems spanning HAL wiring, PID tuning, and the
Python button handlers. This document records *why* each change was made,
in the order the problems were found, so the next engineer touching this
code understands the reasoning instead of just seeing a diff.

Problems 1–8 below were found and fixed against **Sp0 only**. Problem 9
covers building the equivalent chain for **Sp1** afterward, by mirroring
the Sp0 fixes. Problem 10 covers the bugs found once Sp1 was actually
live-tested on hardware, plus two Indexing-panel bugs (checkbox state,
Deg/Div toggle) that surfaced during that same testing session.

## How indexing works, mechanically

Pressing Fwd/Rev sends an `M19` ("Orient Spindle") MDI command for spindle
0. `M19` is LinuxCNC's built-in spindle-orientation primitive: given a
target angle (`R`), it drives the spindle to that angle and reports
success/failure. On this machine that drive is implemented with two HAL
components:

- `orient.0` — given the spindle's current position and a target angle,
  computes a target *position* (`orient.0.command`) that accounts for
  which way around the circle to go.
- `pid.p0` — a position PID loop that turns "target position minus actual
  position" into a velocity command for the Sp0 stepper (`hm2_7i92.0.stepgen.06`).

Sp0 is an **open-loop stepper**, not a servo with an encoder. The position
"feedback" used by both `orient.0` and `pid.p0` is
`hm2_7i92.0.stepgen.06.position-fb` — the stepgen's own internal count of
the steps it has commanded, not an independently measured position. This
is the normal, correct way to close an orientation loop on an open-loop
stepper (assuming no stalls), and was not something we needed to change.

## Problem 1: the orient PID output was never connected to the motor

**Symptom:** M19 did nothing — the spindle simply did not move.

**Cause:** `pid.p0.output` (the orient position loop's computed velocity)
fed into a `sum2` block (`sum2.0`) whose output (`spindle.0-output`) had
**no consumer anywhere** in any loaded `.hal` file. Worse, `sum2.0`'s
update function was never added to any HAL thread (`addf sum2.0` was
missing), so it never even executed. Meanwhile, the signal that actually
drove the stepper's `velocity-cmd` pin was wired directly to
`spindle.0.speed-out-rps` — the normal S-word spindle-speed output, which
LinuxCNC drives to 0 while in orient mode. So during an M19 move, the
orient PID computed a correct velocity command, and it went nowhere.

**Fix:** Added a `mux2` HAL component (`REB.hal`, loaded at line 104,
added to `servo-thread` at line 680) that switches
`hm2_7i92.0.stepgen.06.velocity-cmd` between two sources:

- `mux2.0.in0` = `spindle.0-vel-cmd-rps` (normal S-word speed — unchanged
  from before, zero risk to ordinary spindle rotation)
- `mux2.0.in1` = `spindle.0-output-pos` (the orient position PID output)
- `mux2.0.sel` = `spindle.0-pos-mode-enable` (true only while an M19 is
  actually in progress)

See `REB.hal` lines 725, 739, 752–757. This is a minimal, additive fix:
it doesn't touch the existing normal-rotation path at all, it just adds
the missing final link for orient mode. The old `pid.s0`/`sum2.0` chain
(velocity loop blended with position loop) is left in place but unused —
it was never functional in the first place (missing `addf`, and
`pid.s0.feedback` is also unconnected) and rebuilding it wasn't necessary
once `mux2` provided a working path.

## Problem 2: the position PID was never tuned (found via oscillation)

**Symptom:** With the wiring fixed, the spindle now moved — but wildly
overshot the target and oscillated for several revolutions before settling
back near the start and reporting a timeout.

**Cause:** `pid.p0`'s gain (`P_POS` in `REB_Axes/REB_Spindle0.inc`) was
`1000.0` — a placeholder that had never been exercised, since nothing was
driving the motor before Problem 1 was fixed. With a gain that high, the
loop output saturates at `MAX_OUTPUT_POS` (velocity limit) for almost any
nonzero error, i.e. it behaves like bang-bang control. Given the stepper's
acceleration limit (`STEPGEN_MAXACCEL`), the loop couldn't decelerate in
time and blew straight through the target every time, reversing and
repeating — a classic limit cycle.

**Fix:** For a P-only velocity-mode loop against an acceleration-limited
actuator, overshoot is avoided when
`P_POS ≤ 2 × STEPGEN_MAXACCEL / MAX_OUTPUT_POS`. We tuned `P_POS` down
through this constraint, settling at `1.0` (with `MAX_OUTPUT_POS = 1.0`,
`STEPGEN_MAXACCEL = 1`), which gives a comfortable margin below the
no-overshoot ceiling of 2.0 while still converging in a few seconds.

## Problem 3: FF0 was wrongly nonzero on a position loop

**Symptom:** After fixing the P gain, a move would run continuously for
the entire timeout window in one direction (about as many revolutions as
seconds elapsed) instead of stopping anywhere near the target.

**Cause:** `REB_Axes/REB_Spindle0.inc` had `FF0_POS = 1.0`. Per the HAL
`pid` component's own documentation, `FF0` multiplies the **raw commanded
position**, not the error — and `orient.0.command` is an absolute,
ever-accumulating position (whole revolutions + fractional target), not a
small delta. With `FF0=1.0`, that large absolute number got added directly
into the velocity output, saturating it in one direction regardless of the
actual position error. The `pid` man page is explicit that `FF0` "should
usually be left at zero" for position loops.

**Fix:** `FF0_POS = 0.0` in `REB_Axes/REB_Spindle0.inc`.

## Problem 4: the target angle was never wired in (always targeted 0°)

**Symptom:** After fixing gain and FF0, moves converged cleanly (no more
oscillation or runaway) — but landed at seemingly random angles unrelated
to the commanded `R` value, and still timed out.

**Cause:** `spindle.0.orient-angle` — the HAL pin that receives the `R`
value from the M19 command — was never connected to anything.
`REB.hal` had `net orient.0-angle => orient.0.angle` (a destination only,
no source), so `orient.0.angle` was permanently stuck at its default of
`0`. Every M19, regardless of the `R` you sent, was actually orienting to
0° (relative to the stepper's accumulated revolution count since
power-on).

**Fix:** `net orient.0-angle <= spindle.0.orient-angle` added in
`REB.hal` (line 687), completing the net so the commanded angle actually
reaches `orient.0`.

## Problem 5: forced CW/CCW mode was empirically backwards vs. the docs

**Cause:** `M19`'s `P` word selects direction mode (`orient.0.mode`):
`0` = shortest path, `1`/`2` = force clockwise/counterclockwise. The
LinuxCNC docs available on this system don't fully spell out which of
`P1`/`P2` maps to which, and live HAL tracing (watching `orient.0.mode`
while issuing known commands) showed the *opposite* of the naive
assumption: sending `P1` produced `orient.0.mode = 2`, and vice versa.

**Fix (temporary, later superseded — see Problem 7):** swapped the
literal `P1`/`P2` sent by `Sp0_Move_Idx_Fwd` / `Sp0_Move_Idx_Rev` in
`REB_Display/rosetta.py` so Fwd produced the intended clockwise motion.

## Problem 6: `M19 R<angle>` is an absolute target, not a relative step

**Symptom:** After all of the above, direction was right and a single
move worked — but pressing the *other* button right afterward (e.g. Rev
right after Fwd) produced a huge, unexpected move.

**Cause:** `M19 R<angle>` orients to an **absolute** angle (0–360°), not
"rotate by `<angle>` from here." The original code always sent the fixed
step size (`self.Sp0_Idx_Deg`, e.g. `90`) as `R` on every press. So
pressing Fwd always meant "go to absolute 90°," and pressing Rev
immediately afterward — while already sitting at ~90° — also meant "go to
absolute 90°," just via the opposite forced direction. Since the "short
way" was blocked by the direction constraint, it had to travel almost a
full revolution to reach the same spot from the other side.

**Fix:** `Sp0_Move_Idx_Fwd` and `Sp0_Move_Idx_Rev`
(`REB_Display/rosetta.py`, functions starting at lines 798 and 867)
now read the spindle's **actual current angle live from HAL**
(`hal.get_value('spindle.0-position-fb')`, converted from revolutions to
degrees) and compute the target as `current ± Sp0_Idx_Deg`, wrapped to
0–360°, before sending it as `R`. This makes each press a genuine
incremental step from wherever the spindle physically is — self-correcting
every time, rather than drifting via a separately-tracked software
counter.

## Problem 7: forced direction reliably took the long way around

**Symptom:** Even with the correct incremental target angle, and the
direction mapping from Problem 5 in place, moves would reliably travel
~270° instead of the intended ~90° — always arriving at the *correct*
destination, just by the long route.

**Diagnosis:** Live HAL tracing of several consecutive moves showed the
position before/after each move always landed on the mathematically
correct target angle, but via a ~270° sweep instead of the direct ~90°
one — consistently, in both directions. Forcing a specific CW/CCW
approach (`P1`/`P2`) does not reliably combine with our live-computed,
wrapped target angle to pick the short arc — it isn't a simple "always CW"
or "always CCW" in practice, and there was no indication it was reliably
serving any backlash-consistency purpose either.

**Fix:** Both handlers now send `P0` (shortest path) instead of a forced
direction. This guarantees the direct route to the same (already correct)
destination every time. This also incidentally fixed most of the
remaining marginal timeouts, since a ~90° move converges roughly 3x faster
than a ~270° one.

## Problem 8: a phantom Sp1 command caused a timeout ~20s after every move

**Symptom:** Everything above converged correctly and quickly, but a
"TIMED OUT" error would still appear about 20 seconds after the operator
stopped pressing buttons.

**Cause:** Both handlers sent **two** M19 commands per press: one for
spindle `$0` (Sp0, fully wired per the fixes above) and one for spindle
`$1` (Sp1). At the time, **Sp1 had no `orient` HAL wiring at all**. The
`$1` M19 could never report `is-oriented`, so it always ran for the full
timeout window and then failed, one command behind the real (successful)
Sp0 move.

**Fix (temporary, later superseded — see Problem 9):** Removed the `$1`
M19 call from both handlers (`REB_Display/rosetta.py`). Once Sp1's own
`orient`/`pid` chain was built out, the `$1` call was reinstated —
properly gated this time, per Problem 9.

## Where to adjust accuracy ⭐

**This is the answer to "how close does it get."** The relevant setting
is `orient.0.tolerance` — how many degrees of error is acceptable before
`M19` reports the spindle as successfully oriented.

This pin was previously **hardcoded at the HAL component's default of
0.5°** and wasn't connected to anything configurable. It is now wired to
an ini value:

- **`REB.hal`, line 786:**
  `setp orient.0.tolerance  [SPINDLE_0]ORIENT_TOLERANCE`
- **`REB_Axes/REB_Spindle0.inc`, line 132:**
  `ORIENT_TOLERANCE = 0.1`   *(degrees)*

To change the required accuracy, edit `ORIENT_TOLERANCE` in
`REB_Axes/REB_Spindle0.inc` and restart LinuxCNC (ini/`.inc` files are only
read at startup, via the `#INCLUDE` directive in `REB.ini`). **Two copies
of this file exist — see "A note on which files were edited" below — make
sure you're editing the one that's actually loaded on the machine you're
tuning.**

**Tradeoff to keep in mind:** tightening this value makes each move take
slightly longer to converge (the position loop has to settle further
before declaring success), and if it's set tighter than the loop can
realistically achieve, moves will always time out instead of succeeding.
The gain `P_POS = 1.0` in the same file gives roughly a 1-second time
constant, so a typical 90° move should comfortably reach 0.1° in well
under the 20-second timeout (`Q20`, set in the `M19` strings in
`rosetta.py`). If a tighter tolerance is ever needed, `P_POS` can be
raised further — the no-overshoot ceiling is
`P_POS ≤ 2 × STEPGEN_MAXACCEL / MAX_OUTPUT_POS` (currently `2.0`; see
Problem 2) — or a small `I_POS` can be added to eliminate any residual
steady-state error a pure-P loop leaves behind.

## Problem 9: building out the Sp1 chain, and respecting the Sp0/Sp1 checkboxes

**Goal:** apply the same wiring and tuning fixes to Sp1 that Problems 1–4
established for Sp0, so both spindles can be indexed, and make the
Indexing panel's Sp0/Sp1 checkboxes actually control which spindle(s)
move (they never did).

**HAL wiring (`REB.hal`):** mirrors Problem 1 and Problem 4 exactly, for
spindle 1 / `hm2_7i92.0.stepgen.07`:

- `loadrt orient` → `loadrt orient count=2` and `loadrt mux2` →
  `loadrt mux2 count=2`, to get `orient.1` and `mux2.1`.
- `pid.p1` added to the `loadrt pid names=...` list.
- `addf orient.1`, `addf pid.p1.do-pid-calcs`, `addf mux2.1` added to
  `servo-thread`.
- `orient.1-angle <= spindle.1.orient-angle` (the Problem 4 fix, built in
  from the start this time rather than discovered missing).
- `mux2.1` gates `hm2_7i92.0.stepgen.07.velocity-cmd` between normal
  spindle speed and `pid.p1`'s orient output, selected by
  `spindle.1-pos-mode-enable` — the same pattern as `mux2.0`.
- Fixed a latent Problem-4-style bug found while wiring this up: the
  existing `net spindle.1-revs => spindle.1.revs` had **no source at
  all** (spindle 1's revolution counter was permanently stuck at 0, same
  class of bug as the original `orient.0-angle`). Replaced by properly
  feeding it from `spindle.1-position-fb`, alongside `orient.1.position`
  and `pid.p1.feedback`.

As with Sp0, the pre-existing `pid.s1` velocity-loop chain (`spindle.1-output
<= pid.s1.output`, itself already a dead end — no consumer) was left alone;
`mux2.1` bypasses it the same way `mux2.0` bypasses `pid.s0`.

**Gains (`REB_Axes/REB_Spindle1.inc`, both the git-managed prototype and
the loaded `RoseEngineButlerLocal` copy):** applied the same *pattern* of
fixes as Problems 2–3, using the same starting numbers validated on Sp0
— `P_POS = 1.0`, `FF0_POS = 0.0`, `MAX_OUTPUT_POS = 1.0`, and a new
`ORIENT_TOLERANCE = 0.1`. `orient.1.tolerance` is wired to it in `REB.hal`
the same way as `orient.0.tolerance`. **These numbers are carried over
from Sp0 by analogy, not independently derived or live-tested on Sp1** —
see the caveat below.

**The checkbox bug:** `Sp0_Move_Idx_Fwd`/`Sp0_Move_Idx_Rev` never checked
`self.Sp0_Idx_Bool` / `self.Sp1_Idx_Bool` at all — the Sp0/Sp1 checkboxes
on the Indexing panel visibly existed but did nothing; both spindles
(before Problem 8) or just Sp0 (after Problem 8) always moved regardless
of which boxes were checked. Compounding this, the Python defaults for
those two variables were `False`, while the corresponding GTK checkboxes
(`Sp0_Set_Idx_OnOff`/`Sp1_Set_Idx_OnOff` in `REB_Panel_v2.ui`) default to
**checked** (`active=True`) — so even if the checkboxes had been wired up
naively, a freshly-started GUI would show both boxes checked while the
underlying state said "don't index," until each box was toggled once.

**Fix:** Both handlers now build and send the `$0` M19 only if
`self.Sp0_Idx_Bool` is true, and the `$1` M19 only if `self.Sp1_Idx_Bool`
is true — each computed from that spindle's *own* live position
(`spindle.0-position-fb` / `spindle.1-position-fb` respectively; they can
be at completely different absolute angles).

**Status: since superseded.** Sp1 has since been live-tested on real
hardware — see Problem 10, which also corrects the checkbox-default claim
originally made here (only `Sp0_Idx_Bool`'s default actually changed to
`True`; `Sp1_Idx_Bool` stayed `False`, for reasons explained there).

## Problem 10: bugs found live-testing Sp1 on hardware

**Context:** this is the first time Sp1's chain (built in Problem 9) was
actually commanded to orient on the real machine. It converged correctly
— no oscillation, runaway, or wrong-destination behavior, so the gains
carried over by analogy in Problem 9 held up as-is with no retuning.
Live testing did surface four Python-side bugs, unrelated to the HAL/PID
work, all fixed in the same session in
`REB_Display/rosetta.py`.

**Bug A — index checkboxes drifted out of sync with the display.**
`Sp0_Set_Idx_OnOff`/`Sp1_Set_Idx_OnOff` blindly flipped their own
`self.SpN_Idx_Bool` flag every time the handler ran, on the assumption
the GTK `toggled` signal fires exactly once per click. It doesn't
reliably, so the tracked flag could silently end up opposite of what the
checkbox visually showed. **Fix:** both handlers now read the checkbox's
actual state directly (`widget.get_active()`) instead of flipping a
separately-tracked bool.

This also forced a correction to the Problem 9 checkbox-default fix:
`Sp0_Idx_Bool`'s `__init__` default was changed `False` → `True`, but
live testing showed the `Sp0_Set_Idx_OnOff` checkbox *does* reliably
render checked from the `.ui` file's `active="True"` alone, while the
`Sp1_Set_Idx_OnOff` checkbox does **not** — it renders unchecked
regardless of the `.ui` default. So `Sp1_Idx_Bool`'s default was left at
`False` (matching what the box actually shows at launch), not changed to
`True` as Problem 9 originally described. A `_set_checkbox_active()`
helper, deferred via `GLib.idle_add()` so it runs after gladevcp's own
startup sequence has settled (setting it directly during `__init__` was
tried and didn't stick), now force-syncs both checkboxes to their
`self.SpN_Idx_Bool` defaults once the panel is interactive.

**Bug B — Sp0 and Sp1 M19s sent back-to-back interfered with each other.**
With both checkboxes on, the `$0` and `$1` M19 commands were both queued
via `c.mdi()` before a single trailing `c.wait_complete()` — and only Sp0
actually moved. **Fix:** each M19 now gets its own `c.wait_complete()`
immediately after it's sent, so Sp1's move doesn't start until Sp0's has
fully resolved.

**Bug C — Deg/Div toggle silently canceled itself out.**
`Sp0_Set_Idx_bW_Deg`/`Sp0_Set_Idx_bW_Div` are a GTK radio-button pair
sharing one `toggled` handler (`Sp0_Set_Idx_DegDiv`). Clicking either
button fires that handler **twice** — once for the button becoming
active, once for its sibling becoming inactive. The handler
unconditionally toggled `self.Sp0_Idx_DegDiv` between `"Deg"`/`"Div"` on
every call, so one click flipped it there and back — Div mode could
never actually engage. **Fix:** the handler now checks
`widget.get_active()` and ignores the "going inactive" call, and sets
the mode directly from which button fired (`Gtk.Buildable.get_name(widget)
== "Sp0_Set_Idx_bW_Div"`) rather than toggling blindly. Separately,
`Sp0_Set_Idx_Dist` (the distance spinner) previously only recomputed
`self.Sp0_Idx_Deg` inside the mode-toggle handler, so changing the
distance while already in Div mode had no effect on the actual move size
until the mode was toggled again — it now recomputes `Sp0_Idx_Deg` itself
whenever the distance changes.

**Smaller fixes made alongside the above:**
- A busy ("wait") cursor is now shown for the duration of the blocking
  `c.wait_complete()` calls in both index handlers, so the UI doesn't
  look hung during a multi-second M19 move.
- Pressing Fwd/Rev with neither Sp0 nor Sp1 checked now shows a "No
  spindle is enabled" popup and aborts, instead of silently doing
  nothing.
- The temporary `idx_log()` helper (file-backed logging, added because
  `print()` goes nowhere when the panel launches with `Terminal=false`)
  was extended to cover the index/DegDiv/OnOff handlers touched here,
  alongside the two functions it already covered.

**Net result:** Sp0 and Sp1 can now both be tested independently or
together via their checkboxes, with correct per-spindle sequencing, a
working Deg/Div mode toggle, and UI feedback during moves. The
"watch closely, e-stop within reach" caution from Problem 9 applied
during this testing and can be considered satisfied for Sp1's core
orient/PID chain; it was the surrounding Python state-handling that had
bugs, not the HAL wiring or gains from Problem 9.

## A note on which files were edited

`REB_Axes/REB_Spindle0.inc` exists in **two places**, and they are not
kept in sync automatically:

- `RoseEngineButler/REB_Axes/REB_Spindle0.inc` — the **git-managed
  prototype**, tracked in version control.
- `RoseEngineButlerLocal/REB_Axes/REB_Spindle0.inc` — the **local,
  untracked copy that is actually `#INCLUDE`d and loaded at runtime**
  (see `REB.ini`). All live testing and tuning in this document was done
  against this copy.

Before this work, the two copies had already diverged in ways unrelated
to indexing: `RoseEngineButlerLocal`'s copy has a different Sp0 stepgen
channel (`06` vs the prototype's `05`), different velocity/acceleration
limits (`MAX_VELOCITY`, `STEPGEN_MAXVEL`, `STEPGEN_MAXACCEL`), a
`SCALE`/`STEP_SCALE`/`ENCODER_SCALE` block the prototype doesn't have,
and different `P_VEL`/`I_VEL`/`D_VEL`/`I_POS`/`D_POS` values.

**Only the four values this work actually changed were ported into the
prototype** — `P_POS`, `FF0_POS`, `MAX_OUTPUT_POS`, and the new
`ORIENT_TOLERANCE` key — so the fixes described above aren't lost the
next time someone provisions a machine from the tracked prototype.
Everything else listed above (channel, velocity/accel limits, the scale
block, the untouched gain values) was **deliberately left as-is** in the
prototype; it was never part of this indexing fix and reconciling it was
out of scope. If those other differences are unintentional drift rather
than an intentional newer revision, that still needs a separate look.

`REB_Axes/REB_Spindle1.inc` has the identical two-copy split, with the
same kind of pre-existing divergence (`STEPGEN_MAXVEL`/`STEPGEN_MAXACCEL`,
the `SCALE` block, `P_VEL`/`I_VEL`/`D_VEL`) between the prototype and
`RoseEngineButlerLocal`. The Problem 9 gain values were applied to both
copies the same way as Sp0's.

One consequence worth flagging: the no-overshoot ceiling in Problem 2
(`P_POS ≤ 2 × STEPGEN_MAXACCEL / MAX_OUTPUT_POS`) evaluates differently
in each file, because `STEPGEN_MAXACCEL` differs (`1` in
`RoseEngineButlerLocal`, `6` in the prototype). `P_POS = 1.0` was tuned
and live-validated against the `RoseEngineButlerLocal` ceiling of `2.0`.
In the prototype, the same `P_POS = 1.0` sits well under its (untested)
ceiling of `12.0` — safe, but more conservative than necessary, and not
itself validated on real hardware. Whoever next builds a machine from the
prototype should expect indexing to work but possibly converge more
slowly than what was observed during this session, and may want to retune
`P_POS` upward against that file's own limits.

## Files touched by this work

- `REB.hal` (git-managed) — for Sp0: `mux2.0` component (load, thread,
  wiring), the missing `orient.0-angle` source net, `orient.0.tolerance`
  setp. For Sp1 (Problem 9): `orient`/`mux2` bumped to `count=2`, `pid.p1`
  added, `orient.1`/`pid.p1.do-pid-calcs`/`mux2.1` added to
  `servo-thread`, the full `orient.1`/`pid.p1`/`mux2.1` wiring, and the
  `spindle.1-revs` dangling-net fix.
- `REB_Axes/REB_Spindle0.inc`, **both copies** (see "A note on which
  files were edited") — `P_POS`, `MAX_OUTPUT_POS`, `FF0_POS`,
  `ORIENT_TOLERANCE`.
- `REB_Axes/REB_Spindle1.inc`, **both copies** — same four keys, same
  pattern, added in Problem 9.
- `REB_Display/rosetta.py` (git-managed) — `Sp0_Move_Idx_Fwd` /
  `Sp0_Move_Idx_Rev`: incremental (not absolute) per-spindle target-angle
  computation, shortest-path (`P0`) direction, the Sp0/Sp1 checkbox gating
  and matching `__init__` default fix from Problem 9, and a fix to a
  pre-existing bug where `Sp0_Move_Idx_Rev` referenced an undefined
  variable and never actually sent its `$1` command (unrelated to the
  indexing behavior itself, but discovered and fixed along the way).
  Problem 10 (Sp1 hardware live-testing) added: per-M19
  `c.wait_complete()` sequencing, `widget.get_active()`-based checkbox
  state reading in `Sp0_Set_Idx_OnOff`/`Sp1_Set_Idx_OnOff`, the
  `_set_checkbox_active()`/`GLib.idle_add()` startup-sync fix, the
  `Sp0_Set_Idx_DegDiv` double-fire fix and `Sp0_Set_Idx_Dist` recompute
  fix, `_set_busy_cursor()`, `_show_no_spindle_enabled_popup()`, and
  extending `idx_log()` into the touched handlers.
