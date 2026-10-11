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
| Fault siren on the speaker | 07 October 2026 | A following error or limit trip plays `REB_Fault.wav` on the monitor speaker, with and without a signal tower. Also that Fault Siren = Off / Speaker silences the tower buzzer for faults. |
| Done / Pause beeps | 06 October 2026 | 3 beeps when a program finishes normally, 2 at M0/M1/M60, none on an abort. The finish detection (`stat.motion_line` vs the program's last move) is a guess - the console prints each run's end values to check it. |
| Speed limits in REB Settings | 08 October 2026 | Max Speed / Max Acceleration / PID Max Output from REB Settings reach LinuxCNC; `REB_Update.sh` fills them in correctly on an existing machine. On the tuning page: each group shows four rows, a warnings line and a closed "Advanced settings" twistie with a note beside every row, nothing cut off; no warnings on a normal machine; changing C's Max Speed carries Stepgen Max Vel and PID Max Output along; linear Max Speed stops at 1.0 in/s; Restore Defaults resets an axis's advanced values. The window itself was never opened before commit (no GTK on the Mac). |
| C top speed 30°/s | 07 October 2026 | A 360° G0 rewind of C takes about 12 s (was 36 s). Then time a full run of Roy's Pumping5Sides program - estimated about 46 minutes (was about 4 hours). |
| Threading tab | 24 September 2026 | C turns the right way for a right-hand thread, and outside threading feeds in toward -X. |
| EtherLab key refresh in `REB_Update.sh` | 08 October 2026 | Tested on its own (current key, stale key, server unreachable), not yet as part of a full update run. |
| Back Up to USB | 06 October 2026 | Insert a stick, run a backup, then check the dated `REB_Backup/` folder and `backup_log.txt` on another computer, and that the stick ejects with "Safe to remove". Also add the MenuLibre menu and desktop entries - Command `/home/reuben/linuxcnc/configs/RoseEngineButler/REB_Backup.sh`, Icon `REB_Setup/Images/REB_Backup.png`. |
| REB.ini / REB.hal cleanup | 06 October 2026 | LinuxCNC starts with no HAL errors, an axis jogs and moves, and an Sp0 M19 index works. Probably already exercised by the 08 October spindle and speed-limit testing - tick it off if so. |
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
| Sp0 won't reverse on one box | 06 October 2026 | Run Operation Rev and index Rev both turned Sp0 forward; Sp1 reversed fine. Not caused by the 06 October cleanup (Sp0's speed path is unchanged). Suspected hardware: Sp0 DIR is P1 pin 11 (I/O 026), right next to the tower buzzer on P1 pin 13 (I/O 027) - a bridge would pin DIR whenever the tower is enabled. Checks: retest on the known-good prototype; `halcmd show sig spindle.0-vel-cmd-final` in Fwd and Rev (sign should flip); untick Signal Tower and retry; swap Sp0/Sp1 channels or plugs. May be the same box as "Spindles on the second machine". |
| Indexing direction for large angles | 06 October 2026 | `orient.0`/`orient.1` mode is hardwired to 0 (shortest path), so an index of 180° or more can turn the opposite way from the button pressed. Decide whether to make Fwd/Rev always turn the requested way. |
| User Manual pages for Backup, Sounds and Signal Tower | 07 October 2026 | PmWiki pages Main.BackUpToUSB, Main.Sounds and Main.SignalTower were drafted on the Mac but never committed, and the folder they were in is gone - confirm they were pasted into the wiki, or ask Claude to redraft them. Also: upload `REB_Backup.png` to `UserManual/Images/`, add the pages to the sidebar, and confirm the menu entry is named "Back Up to USB". The Signal Tower page says towers must be PNP / common-negative (NPN won't work with the standard cabling) - confirm. The Sounds page predates the fault siren on the speaker and needs that added. |
| User Manual: tuning page | 08 October 2026 | Update for the new Max Speed / Max Acceleration rows, the Advanced settings twisties, the row notes and Restore Defaults, once the screen has been seen on the Pi. |
| Restore from USB | 06 October 2026 | Idea, not started: a matching program to copy a dated backup back onto the Pi. Check how it should fit with the existing `REB_Display/REB_Settings_Restore.py` first. |
| REB.ini: possibly redundant keys | 06 October 2026 | Left in during the cleanup because how AXIS uses them wasn't certain: `[FILTER]` (opens .png/.gif/.jpg and .py files through image-to-gcode - remove if never used), `[DISPLAY]MIN_VELOCITY` and the un-numbered `MAX_SPINDLE_OVERRIDE`/`MIN_SPINDLE_OVERRIDE`. |
| Old keys in settings files | 08 October 2026 | Machines' REBset_v1.ini may still hold an inert `pid_vel` block from the removed spindle velocity PID, and (since 11 October 2026) a `signal_tower_active_low` value from the removed relay-polarity checkbox. Nothing reads either; harmless. Could be removed by `REB_Update_Settings.py` some day. |
| Leftover repo copy on the Mac | 06 October 2026 | `~/Documents/GitHub/RoseEngineButler` is a stale duplicate (with one unpushed commit, now also in the real repo). Safe to delete; the working copy is iCloud Drive > Shared iCloud > Rich > GitHub > RoseEngineButler. |

## Planning

Ideas and designs not yet being built. Nothing here has code yet.

### Two-box hardware: base box + expansion box (since 11 October 2026)

Rich and Chuck's plan to split the hardware into two chassis: a **base
box** with the Raspberry Pi, an Ethernet switch, one Mesa 7i92TH and 6
DM542T channels, and an optional **expansion box** with a second 7i92TH
and 4 more channels - 10 in all, one for each of the 10 roles (8 axis
letters and 2 spindles). The two cards talk to the Pi through the switch.

Decided so far:

- **Development boxes:** the current 8-channel boxes are development
  units. They'll be replaced, or simply treated as a base box with
  channels 00-05 and their other two plugs ignored - so only one
  software design is needed.
- **Base box I/O stays:** limit jacks 1-3, the E-stop button and the
  signal tower stay in the base box. The expansion box may add **limit
  jacks 4-6**, read from the second card.
- **Channel labels:** base box 00 / 02 / 04 on the top row and 01 / 03 /
  05 on the bottom. Expansion box either 00-03 again or **06 / 08 over
  07 / 09** - Claude recommends 06-09, so every channel number names one
  plug on the whole machine (in the settings file, on the Axis Selection
  page and when talking to a customer), continuing the base box's
  even-top / odd-bottom pattern. Also recommended: wire each plug to the
  step generator with the same number, so labels and software agree
  (today's boxes don't - "Position 1" is Channel 02).
- **No fixed roles:** any role on any channel, as now.

Open questions:

- **Mesa (Rich has asked their tech contact):** is two 7i92s through an
  unmanaged switch at a 1 ms servo period on a Pi 5 a setup they've seen
  work; any switch they recommend; and firmware - a 6-channel base card
  and a 4-channel expansion card with the inputs/outputs wanted (custom
  pin files like today's `PIN_REB_34`, or something stock).
- **Bench test:** if Mesa agrees, borrow a card from a development box:
  two cards, the switch and a few drives, run for a long time watching
  for `hm2_eth` read errors and following errors. Order another card
  after.

Points to settle in the design:

- The second card needs its own IP address (today's card uses the
  jumper default, 192.168.1.121), set once with `mesaflash` before the
  box ships.
- Keep the switch private - nothing else (router, internet, file
  sharing) on that network, or the 1 ms timing suffers. The Pi's
  internet stays on Wi-Fi.
- Either card's watchdog (it stops that card's steps if it loses
  contact) should count as an E-stop fault, so a pulled cable can't leave
  half the machine running.
- Alternative considered: one 7i92 with new firmware running all ten
  channels, with step/direction signals cabled to the expansion box.
  Cheaper and easier on timing, but long signal cables pick up noise and
  it uses up the card's spare pins; the two-card design is more modular.

Software work once the design is fixed (not started):

1. Channels 00-09 across two cards (`hm2_7i92.0` for 00-05,
   `hm2_7i92.1` for 06-09). The channel table is repeated in
   `REB_Settings.py`, `REB_main.py`, `REB_Scale_Persist.py` and
   `REB_Generate_Local_Ini.py`; the generator builds the HAL from it.
2. An "Expansion box connected" setting (like Signal Tower's): off = one
   card and 6 channels, on = both cards and 10.
3. REB Settings' Axis Selection page laid out as the two boxes, with the
   expansion group greyed out when it isn't connected.
4. Limit jacks 4-6 on the second card, shown only with the expansion box.
5. Either card losing contact = E-stop.
6. The update step converting existing settings files' channel IDs.
7. New firmware/pin files for both cards.

## Done

Most recent first.

| Item | Settled | How |
|---|---|---|
| Signal tower relay polarity setting | 11 October 2026 | Dropped: the relays are on Chuck's REB circuit board, and home-built systems must follow the same active-low standard. The "Relays switch on when low" checkbox is gone; `SIGNAL_TOWER_ACTIVE_LOW` is fixed. |
| Startup splash drawing and fallback | 11 October 2026 | Verified by Rich: with X and Z assigned the preview shows "REB" over "ROSE ENGINE BUTLER", right way up, no error; X only, Z only, and neither all fall back to the empty splash; pressing Run with it loaded and the axes enabled moves nothing. |
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
