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
| Speed limits in REB Settings | 08 October 2026 | Max Speed / Max Acceleration / PID Max Output from REB Settings reach LinuxCNC; `REB_Update.sh` fills them in correctly on an existing machine. On the tuning page: each group shows four rows, a warnings line and a closed "Advanced settings" twistie with a note beside every row, nothing cut off; no warnings on a normal machine; changing C's Max Speed carries Stepgen Max Vel and PID Max Output along; linear Max Speed stops at 1.0 in/s; Restore Defaults resets an axis's advanced values. The window itself was never opened before commit (no GTK on the Mac). |
| C top speed 30°/s | 07 October 2026 | A 360° G0 rewind of C takes about 12 s (was 36 s). Then time a full run of Roy's Pumping5Sides program - estimated about 46 minutes (was about 4 hours). |
| Threading tab | 24 September 2026 | C turns the right way for a right-hand thread, and outside threading feeds in toward -X. |
| EtherLab key refresh in `REB_Update.sh` | 08 October 2026 | Tested on its own (current key, stale key, server unreachable), not yet as part of a full update run. |
| Back Up to USB | 06 October 2026 | Insert a stick, run a backup, then check the dated `REB_Backup/` folder and `backup_log.txt` on another computer, and that the stick ejects with "Safe to remove". Also add the MenuLibre menu and desktop entries - Command `/home/reuben/linuxcnc/configs/RoseEngineButler/REB_Backup.sh`, Icon `REB_Setup/Images/REB_Backup.png`. |
| REB.ini / REB.hal cleanup | 06 October 2026 | LinuxCNC starts with no HAL errors, an axis jogs and moves, and an Sp0 M19 index works. Probably already exercised by the 08 October spindle and speed-limit testing - tick it off if so. |
| File menu in REB Settings | 07 October 2026 | Ctrl+S / Shift+Ctrl+S / Ctrl+O / Ctrl+Q do the same as the buttons, including a half-typed value being saved. |

## Open items and follow-ups

| Item | Since | Notes |
|---|---|---|
| Spindles on the second machine | 08 October 2026 | Sp0/Sp1 don't run there. They work on the prototype, so this is that machine's wiring - check its cables, plugs and drives first. |
| Limit jack pin map | 28 September 2026 | `LIMIT_JACK_INPUT` (jacks 1/2/3 -> I/O 002/006/010) is a placeholder until the PCB wiring is final. Space is left on the Axis Selection page for a Limit Jack 4. |
| Tell Roy about the C speed-up | 07 October 2026 | Close LinuxCNC, run the update **twice** in a row before starting LinuxCNC again, and check the output shows C's new limits. |
| Roy's program: skip the C rewinds | 07 October 2026 | Optional, Roy's call: resetting C's coordinate to 0 after each pass instead of rapiding back 360° would save the rewind time entirely. |
| Warn when running with an axis not enabled | 07 October 2026 | Idea: a program started with an axis's ENA off ends in a "following error"; a plain "C is not enabled" warning before the run would be clearer. Not started. |
| Sp0 won't reverse on one box | 06 October 2026 | Run Operation Rev and index Rev both turned Sp0 forward; Sp1 reversed fine. Not caused by the 06 October cleanup (Sp0's speed path is unchanged). Suspected hardware: Sp0 DIR is P1 pin 11 (I/O 026), right next to the tower buzzer on P1 pin 13 (I/O 027) - a bridge would pin DIR whenever the tower is enabled. Checks: retest on the known-good prototype; `halcmd show sig spindle.0-vel-cmd-final` in Fwd and Rev (sign should flip); untick Signal Tower and retry; swap Sp0/Sp1 channels or plugs. May be the same box as "Spindles on the second machine". |
| Indexing direction for large angles | 06 October 2026 | `orient.0`/`orient.1` mode is hardwired to 0 (shortest path), so an index of 180° or more can turn the opposite way from the button pressed. Decide whether to make Fwd/Rev always turn the requested way. |
| User Manual pages for Backup, Sounds and Signal Tower | 07 October 2026 | PmWiki pages Main.BackUpToUSB, Main.Sounds and Main.SignalTower were drafted on the Mac but never committed, and the folder they were in is gone - confirm they were pasted into the wiki, or ask Claude to redraft them. Also: upload `REB_Backup.png` to `UserManual/Images/`, add the pages to the sidebar, and confirm the menu entry is named "Back Up to USB". The Signal Tower page says towers must be PNP / common-negative (NPN won't work with the standard cabling) - confirm. The Sounds page predates the fault siren on the speaker and needs that added. |
| User Manual: tuning page | 08 October 2026 | Update for the new Max Speed / Max Acceleration rows, the Advanced settings twisties, the row notes and Restore Defaults, once the screen has been seen on the Pi. |
| Restore from USB | 06 October 2026 | Idea, not started: a matching program to copy a dated backup back onto the Pi. Check how it should fit with the existing `REB_Display/REB_Settings_Restore.py` first. |
| REB.ini: possibly redundant keys | 06 October 2026 | Left in during the cleanup because how AXIS uses them wasn't certain: `[FILTER]` (opens .png/.gif/.jpg and .py files through image-to-gcode - remove if never used), `[DISPLAY]MIN_VELOCITY` and the un-numbered `MAX_SPINDLE_OVERRIDE`/`MIN_SPINDLE_OVERRIDE`. |
| Old spindle `pid_vel` blocks in settings files | 08 October 2026 | Machines' REBset_v1.ini still hold an inert `pid_vel` block from the removed spindle velocity PID. Harmless; could be removed by `REB_Update_Settings.py` some day. |
| Leftover repo copy on the Mac | 06 October 2026 | `~/Documents/GitHub/RoseEngineButler` is a stale duplicate (with one unpushed commit, now also in the real repo). Safe to delete; the working copy is iCloud Drive > Shared iCloud > Rich > GitHub > RoseEngineButler. |

## Done

Most recent first.

| Item | Settled | How |
|---|---|---|
| Items from the Mac session's list | 11 October 2026 | Copied into this file. |
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
