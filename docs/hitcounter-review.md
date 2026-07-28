# Code Review: `REB_Display/hitcounter.py`

**Date:** 2026-07-26
**Scope:** General structural review, not a bug hunt. Requested after a session
of live bug-fixing on the indexing panel, ENA override handling, and X/Z axis
tuning, to capture what a senior Python reviewer would flag about the file's
overall shape.

**Status (2026-07-28):** Issue 1 has a concrete implementation plan.
Scope is X/Z/U/V/W only — B and Sp0/Sp1 are intentionally excluded (see
Issue 1 below for why). While designing it, two live bugs also surfaced
and are being fixed as part of the same work: `REB_Panel_v2.ui` has
`V_Idx_Minus` wired to the `W_Idx_Minus` handler (wrong axis) and
`W_Idx_Minus`/`W_Idx_Plus` swapped with each other; and only X currently
has the `c.abort()` safety-stop-before-rescale and button-depress UI
feedback that all five axes are being standardized on.

## Summary

The file is 3,259 lines, one class (`HandlerClass`), 72 methods, plus a
handful of module-level helper functions. The *behavior* is solid at this
point (extensively live-tested this session), but the *structure* has grown
the way debugging sessions grow: reasonable for how it got here, but it would
fight back hard if extended to a 9th axis or handed to someone else cold.

## Strengths

- The instinct to extract shared helpers is there when it mattered -
  `_set_depressed`, `_clear_ena_override`, `_set_busy_cursor`, `idx_log` are
  all reasonable, single-purpose functions pulled out to module level rather
  than inlined everywhere.
- The banner-comment convention (Purpose / Called from / Data / Gcodes above
  every method) is unusually disciplined for this kind of machine-control
  codebase.
- Cross-process HAL boundaries (`self.halcomp` vs. another component's pins)
  are correctly understood and documented where it matters (e.g.
  `_clear_ena_override`'s comment about why a component can't write another
  component's pin directly) - a subtle thing to get right.

## Issue 1: One class, one file, doing everything for 8 axes by copy-paste

```
grep -c "^    def " → 72 methods, all on one HandlerClass
```

Every axis (`X`, `Z`, `U`, `V`, `W`, plus `B`/`Sp0`/`Sp1` with minor
variations) has its own near-identical `Idx_Minus`, `Idx_Plus`, `Set_Feed`,
`Set_Idx_Dist`, `Set_Move_Dist`, `Set_Scale`, `Set_Ena`. That's roughly 35
methods that are the same handful of patterns with `self.X_...` swapped for
`self.Z_...`. Concretely, `X_Set_Scale` / `Z_Set_Scale` / `U_Set_Scale` /
`V_Set_Scale` / `W_Set_Scale` are the same ~25-line function five times,
differing only in the axis letter and stepgen channel number.

This isn't just a style complaint - it's why the accel/PID misconfiguration
found on X existed identically on all five linear axes, and had to be
manually re-verified and reapplied four more times instead of being fixed
once in one place. The same investigation also found `Set_Ena` (all 8
axes/spindles) may be entirely unreachable from the UI - no `.ui` file
wires a `<signal>` to it - which the plan verifies live before deciding
whether to delete or keep it.

**Fix (planned):** generate real bound methods via `setattr` on
`HandlerClass` itself at module-load time, one factory function per
pattern (`_axis_idx_move`, `_axis_set_feed`, `_axis_set_scale`, etc.)
looped over `LINEAR_AXES = ("X", "Z", "U", "V", "W")`, using the existing
`AXIS_STEPGEN` mapping for stepgen channels. A bare `__getattr__`
dispatcher was considered and ruled out: GladeVCP discovers handlers via
`dir(instance)` fed into `builder.connect_signals()`, and `dir()` doesn't
enumerate names produced only through `__getattr__` - a button wired to
a `__getattr__`-only name would silently stop working with no error.
Class-level `setattr` produces real, `dir()`-visible, individually
named methods (`handler.__name__` set explicitly), avoiding that trap.
`B`/`Sp0`/`Sp1` are excluded from this collapse: `B` has Deg/Div-toggle
logic with no linear-axis equivalent, and `Sp0`/`Sp1` indexing is a
different mechanism entirely (M19 absolute-angle orient vs. relative G1
moves) - forcing them into the same dispatch would obscure real
differences rather than removing duplication.

## Issue 2: Logging is in a transitional, inconsistent state

```
print(  → 238 occurrences
idx_log( → 48 occurrences
```

Most of the file still uses bare `print()`, which goes nowhere visible when
the panel launches with `Terminal=false` (confirmed directly this session -
this exact gap was the source of real confusion while debugging the
indexing checkboxes). `idx_log` was added specifically for that debugging
and only got retrofitted into the code paths being actively chased at the
time. The other ~200 `print()` calls are just as invisible right now.

**Suggested fix:** either finish the `idx_log` conversion everywhere, or
replace the whole ad-hoc scheme with Python's `logging` module (file handler
+ rotation), which solves "where did my print go" permanently instead of one
call site at a time.

## Issue 3: Shelling out to `halcmd` per-call is fragile and slow

```
subprocess.run → 21 call sites, all building
    ["halcmd", "getp"/"setp"/"sets", ...] and parsing text stdout
```

Each call spawns a new process (tens of ms), and correctness depends on
parsing halcmd's text output (e.g.
`result.stdout.strip().upper() in ("TRUE", "1")`) rather than a typed API.
`hal.get_value()` is already used elsewhere in the same file for same-process
reads and works directly. The cross-component pin-name mixups hit this
session (`setp` vs `sets`, `getp` vs `gets`, wrong-component pin target) are
the direct symptom of this being string-plumbing rather than a real API
boundary.

**Suggested fix:** if this cross-component communication pattern has to
stay (GladeVCP's process-per-tab model may require it), wrap it in one small
`_hal_signal(name)` / `_set_hal_signal(name, value)` pair that centralizes
the `getp`-vs-`gets` distinction, instead of leaving each call site to get it
right independently.

## Smaller items

- `__init__` is ~120 lines, almost entirely repetitive
  `self.X_Feed = 1.0` / `self.X_Idx_Dist = 0.0` / ... declarations per axis -
  same duplication problem as Issue 1, same fix (a per-axis dict or small
  state object would replace ~80 of those lines).
- The `self.builder.get_object(widget_id) is None: return` guard (used to
  make one shared module work across the 4 different GladeVCP processes -
  main panel, Settings, Help, Ts&Cs tabs) is a real, working technique, but
  it means every such method silently no-ops in 3 of 4 processes with no log
  trail. Worth a top-of-file comment explaining this is intentional
  multi-process shared-module architecture, since it isn't obvious from any
  single method in isolation.
- No tests at all - understandable for something this hardware-coupled, but
  the pure-logic bits (the angle math in `Sp0_Move_Idx_Fwd`/`Rev`, the
  Deg/Div conversion) are unit-testable in isolation without a running
  LinuxCNC, and are exactly the kind of thing that broke silently this
  session (the Deg/Div double-fire bug) in a way a two-line test would have
  caught immediately.

## Priority, if picking one thing

The axis duplication (Issue 1) is the one worth spending real time on - it's
the direct cause of needing this session's PID fix applied five times by
hand, and it will bite again the next time a bug is found on one axis and
needs porting to the rest. The logging and halcmd-wrapping items are
lower-stakes cleanup that mostly pay off in "the next debugging session goes
faster," not in correctness today.
