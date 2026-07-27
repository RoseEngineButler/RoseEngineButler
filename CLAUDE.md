# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A LinuxCNC configuration (not a compiled software project) for the "Rose Engine Butler" — a control system for ornamental turning lathes (rose engines), built by Colvin Tools / Brainwave Embedded. It uses a Raspberry Pi 5 + Mesa 7i92 (`hm2_eth`) FPGA card driving 8 stepper joints via StepperOnline DM542T drives. Details: https://RoseEngineButler.com.

There is no build/compile/test step. "Testing" a change means loading the config in LinuxCNC (`linuxcnc REB.ini`) on the actual machine (or a sim) and observing axis/spindle behavior — most of this is real-time motion control tuning, not something that can be verified by static inspection alone.

## Repo vs. local machine state — read this before editing

This repo (`RoseEngineButler`) is the **shared/distributable** config. A sibling directory, `RoseEngineButlerLocal` (NOT part of this git repo, lives at `/home/reuben/linuxcnc/configs/RoseEngineButlerLocal`), holds **per-machine local state** that REB.ini/REB.hal reference by absolute path:

- `RoseEngineButlerLocal/REB_Custom/REB_Custom.hal` — end-user HAL customizations (`[HAL]HALFILE` in REB.ini)
- `RoseEngineButlerLocal/REB_Custom/REB_Tool.tbl` — the tool table (`[EMCIO]TOOL_TABLE`)
- `RoseEngineButlerLocal/REB_Settings_v1.ini` — persisted per-axis stepgen scale values (an XML file despite the `.ini` extension), written by `REB_Display/REB_Scale_Persist.py` on shutdown and read back by `REB_Display/hitcounter.py` at Settings-tab load

The repo also ships its own `REB_Custom/REB_Custom.hal` and `REB_Custom/REB_Tool.tbl` as templates/fallback copies — don't confuse the two when tracing which file is actually loaded at runtime (check the absolute paths in REB.ini's `[HAL]` and `[EMCIO]` sections).

`sim.var` / `sim.var.bak` and `REB_Display/__pycache__/` appearing in `git status` are runtime artifacts, not tracked source — don't commit them.

## Architecture

**Load order or a LinuxCNC session** (see `REB.ini`):
1. `REB.ini` — the master config: `[EMC]`/`[DISPLAY]`/`[KINS]`/`[TRAJ]` sections plus one `[AXIS_*]`/`[JOINT_n]` section per axis and one `[SPINDLE_n]` per spindle. All axis tuning (PID gains, STEPGEN_MAXVEL/MAXACCEL, step timing) lives here now — the old per-axis `REB_Axes/*.inc` files were merged into REB.ini's `[JOINT_n]`/`[SPINDLE_n]` sections (see git history) and no longer exist.
2. `REB.hal` — loads realtime components (`hostmot2`, `hm2_eth`, `pid`, `orient`, `sum2`) and wires each joint's stepgen ↔ PID ↔ HAL pins. **Not meant to be user-edited.**
3. `RoseEngineButlerLocal/REB_Custom/REB_Custom.hal` — user HAL additions, loaded after REB.hal.
4. `REB_Display/REB_PostGUI.hal` — runs after the GUI loads; wires the gladevcp panel's per-axis ENA buttons through a flipflop-based toggle, ANDed with a Settings-tab override pin (`REBCnfg.<Axis>_Ena_Override`), into each axis's actual enable net.
5. `REB_Shutdown.hal` — runs `REB_Display/REB_Scale_Persist.py` to persist live stepgen position-scale values back into `RoseEngineButlerLocal/REB_Settings_v1.ini`.

**Axis/joint/plug map** (also documented as a table at the top of REB.hal and REB.ini): X=joint0, Z=joint1, B=joint2 (angular), U=joint3, V=joint4, W=joint5 (no PID — open-loop stepgen only), Sp0=joint7, Sp1=joint6. `Y`/`A`/`C` are unused (`LATHE=1`, no back tool post). Kinematics is `trivkins coordinates=XZBUVW`.

**`AXIS_STEPGEN` axis-id → stepgen-channel map** is duplicated in both `REB_Display/hitcounter.py` and `REB_Display/REB_Scale_Persist.py` — it's the source of truth for which `hm2_7i92.0.stepgen.NN` a given axis letter maps to, verified against the actual `net <axis>-enable => hm2_7i92.0.stepgen.NN.enable` lines in REB.hal (the channel numbers in REB.ini's/REB.hal's comment-block tables are documentation only and have been known to disagree with the real wiring — trust the `net` lines, not the ASCII-art tables, when in doubt). If you change stepgen channel wiring in REB.hal, update this map in both Python files.

**GUI layer** (`REB_Display/`): AXIS (`DISPLAY = axis`) with a GladeVCP side panel (`REB_Panel_v2.ui`) and three embedded tabs (Help, Settings, License), all driven by the single handler script `hitcounter.py` (loaded once per gladevcp instance via `-u REB_Display/hitcounter.py`). Each `.ui` file's Python object IDs (e.g. `REBCnfg.X_Ena_Override`) are what HAL nets in REB_PostGUI.hal connect to — cross-reference the `.ui` files and REB_PostGUI.hal together when tracing a panel control end-to-end. `REB_Display/ZZ_Unused/` holds superseded `.ui` files kept for reference; don't wire new HAL against them.

**Tuning comments**: many `[JOINT_n]` blocks in REB.ini carry long inline comments explaining *why* a PID/STEPGEN value was changed (e.g. STEPGEN_MAXACCEL vs MAX_ACCELERATION ordering, FF1 vs P/I windup). When adjusting tuning values, preserve or update these comments rather than deleting them — they record hardware-derived ceilings (step timing → max steps/sec) that aren't otherwise obvious from the number alone.

**`REB_Spindle.hal`** is a standalone reference/example file (vismach sim spindle wiring with `pid`/`orient`/`mux2`/`near`/`edge`) — it is not loaded by REB.ini (`HALFILE = REB_Spindle.hal` is commented out) and should be treated as inactive documentation, not live config.

**`REB_Setup/`** contains shell installers (`REB_Install.sh`, `REB_Install_Trixie.sh` for Debian Trixie, `REB_Update.sh`, `REB_Backup.sh`, `REB_Restore.sh`) that provision a fresh Pi, plus `MesaCard/` (the 7i92 firmware `.bin`/pin file and VHDL source) and `Images/` (boot splash/wallpaper assets). These scripts are meant to run on the target machine, not in a dev sandbox.
