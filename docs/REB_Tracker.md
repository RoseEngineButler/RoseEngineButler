# Rose Engine Butler Tracker

The one list of open, untested and recently settled items for the Rose
Engine Butler. It lives in the repo so every Claude Code session (the Pi
and the Mac) and everyone working on REB sees the same list after a
`git pull`. Claude sessions keep their own per-machine notes, which the
other machine can't see - anything that matters goes here instead.

How to use it:

- Add an item when something is built but not yet run on a machine, a
  problem is found, or a follow-up is agreed. Give it a date.
- When an item is settled, move it to **Done** with the date and how it
  was settled (tested on which machine, fixed in which commit, dropped).
- Dates use a two-digit day: 08 October 2026.

Last reviewed: 11 October 2026.

## Untested on a machine

Built and committed, but not yet seen working on real hardware.

| Item | Since | What to check |
|---|---|---|
| E-stop button | 28 September 2026 | Pressing it (and unplugging it) latches E-stop; release then F1 resets. Needs "Connected" ticked in REB Settings. |
| NO limit switches | 08 October 2026 | With Limit Switch Type set to Normally open, a tripped NO switch stops the axis (reads the jack's GPIO `.in_not`). NC is already verified - see Done. |
| Active-high signal tower relays | 08 October 2026 | With "Relays switch on when low" unticked, the lights and buzzer follow the right states on an active-high relay board. Active-low (the default) is already verified. |
| Fault siren on the speaker | 07 October 2026 | A following error or limit trip plays `REB_Fault.wav` on the monitor speaker, with and without a signal tower. Also that Fault Siren = Off / Speaker silences the tower buzzer for faults. |
| Done / Pause beeps | 06 October 2026 | 3 beeps when a program finishes normally, 2 at M0/M1/M60, none on an abort. The finish detection (`stat.motion_line` vs the program's last move) is a guess - the console prints each run's end values to check it. |
| Speed limits in REB Settings | 08 October 2026 | Max Speed / Max Acceleration / PID Max Output from REB Settings reach LinuxCNC; `REB_Update.sh` fills them in correctly on an existing machine. |
| C top speed 30°/s | 07 October 2026 | A 360° G0 rewind of C takes about 12 s (was 36 s). Then time a full run of Roy's Pumping5Sides program - estimated about 46 minutes (was about 4 hours). |
| Threading tab | 24 September 2026 | C turns the right way for a right-hand thread, and outside threading feeds in toward -X. |
| EtherLab key refresh in `REB_Update.sh` | 08 October 2026 | Tested on its own (current key, stale key, server unreachable), not yet as part of a full update run. |
| Index counters on the Indexing tab | 11 October 2026 | Each axis row and the spindle row show a count left of Distance: +1 per Fwd index, -1 per Rev (it can go negative). Resets to 0 at startup, on a distance or deg/div change, and on a double-click of the number. Check the count follows the on-screen Rev/Fwd columns, the spindle count works with Sp0, Sp1 and both, and the Distance column didn't get wider. Rich may switch the reset to a single click after trying it. |
| Notes in REBset_v1.ini | 11 October 2026 | After an update (run twice on Chuck's and Roy's machines), `~/Documents/REBset_v1.ini` starts with the "Rose Engine Butler settings" notes and ends with the copyright, and the other settings/export files there have their notes too (not the `.bak-` backups); LinuxCNC and REB Settings still start, and Load Settings reads both a "Save All Settings As..." copy and a Save Subset export. |
| File menu in REB Settings | 07 October 2026 | Ctrl+S / Shift+Ctrl+S / Ctrl+O / Ctrl+Q do the same as the buttons, including a half-typed value being saved. |

## Open items and follow-ups

| Item | Since | Notes |
|---|---|---|
| Spindles on the second machine | 08 October 2026 | Sp0/Sp1 don't run there. They work on the prototype, so this is that machine's wiring - check its cables, plugs and drives first. |
| Limit jack pin map | 28 September 2026 | `LIMIT_JACK_INPUT` (jacks 1/2/3 -> I/O 002/006/010) is a placeholder until the PCB wiring is final. Space is left on the Axis Selection page for a Limit Jack 4. |
| Tell Roy about the C speed-up | 07 October 2026 | Close LinuxCNC, run the update **twice** in a row before starting LinuxCNC again, and check the output shows C's new limits. |
| Roy's program: skip the C rewinds | 07 October 2026 | Optional, Roy's call: resetting C's coordinate to 0 after each pass instead of rapiding back 360° would save the rewind time entirely. |
| Warn when running with an axis not enabled | 07 October 2026 | Idea: a program started with an axis's ENA off ends in a "following error"; a plain "C is not enabled" warning before the run would be clearer. Not started. |
| Items from the Mac session's list | 11 October 2026 | The Claude session on the Mac kept its own list of untested items. Copy anything still open into this file. |

## Done

Most recent first.

| Item | Settled | How |
|---|---|---|
| Startup splash drawing and fallback | 11 October 2026 | Verified by Rich: with X and Z assigned the preview shows "REB" over "ROSE ENGINE BUTLER", right way up, no error; X only, Z only, and neither all fall back to the empty splash; pressing Run with it loaded and the axes enabled moves nothing. |
| Sp0 / Sp1 running | 08 October 2026 | Verified by Rich on the prototype. |
| EtherLab "signing key is bad / expired" from apt update | 08 October 2026 | Key refreshed on the Pi; `REB_Update.sh` now refreshes it automatically (06549a8). |
| Update asking for the SSH key passphrase | 08 October 2026 | The Pi's `~/.ssh/config` uses the passphrase-free key for GitHub. Per-machine setting, not in the repo. |
| User Manual anchor for "How Limit Switches Work" | 08 October 2026 | Rich renamed it to `[[#LimitSwitches]]`. |
| Seed linear stepgen speed below the planner's | 08 October 2026 | Resolved by the speed-limits change (4835dbc): the seed plans X/Z at 0.167 in/s, below the 0.208 in/s stepgen ceiling. |
| Jog speed capping programs (C held at 10°/s) | 08 October 2026 | `[TRAJ]` caps now come from the fastest axis, not the jog setting (4835dbc). |
| Roy's program taking about 4 hours | 07 October 2026 | C acceleration 10 -> 320°/s². One-zone test 88 s -> 15.84 s, ran clean (0e860ae). Full-run time still to measure - see C top speed above. |
| Help tab making the window too wide | 05 October 2026 | Smaller title banner (e93eb18). |
| Signal tower red and green lights | 05 October 2026 | Verified on the prototype after the latch and spindle-activity fixes (e74f9c5). |
| NC limit switches | 05 October 2026 | Verified stopping motion on the prototype; red latches on a trip. |
| Mesa ground / +5V pins | 02 October 2026 | Settled by Rich on the support wiki's Mesa pin mapping page. |
