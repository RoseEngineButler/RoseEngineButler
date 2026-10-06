#!/usr/bin/env python3
#######################################################################
#                    RRRRRR    EEEEEEEE  BBBBBBB                      #
#                    RR   RR   EE        BB    BB                     #
#                    RR   RR   EE        BB    BB                     #
#                    RRRRRR    EEEEEE    BBBBBBB                      #
#                    RR   RR   EE        BB    BB                     #
#                    RR    RR  EE        BB    BB                     #
#                    RR    RR  EEEEEEEE  BBBBBBB                      #
#                                                                     #
#                         Rose Engine Butler                          #
#######################################################################
#
# LinuxCNC configuration for use with a Rose Engine
#
# File:
#   REB_Generate_Local_Ini.py
#
# Purpose:
#   Regenerates REB.local.ini (written alongside REB.ini, in this repo's
#   own directory - see below for why it can't live in
#   RoseEngineButlerLocal) from this repo's tracked REB.ini, overlaying
#   whatever local Max Jog Speed / the five VELOCITY_SETTINGS jog-speed
#   values (Default/Max/Min Angular, Default/Min Linear) / Measurement
#   System / channel-role assignment / per-axis backlash choices are
#   currently persisted in
#   /home/reuben/Documents/REBset_v1.ini. Also regenerates REB.local.hal
#   (REB_PostGUI_v1.local.hal is copied unchanged - see
#   generate_local_hal_files).
#
#   REB.ini's [TRAJ]/[DISPLAY] MAX_LINEAR_VELOCITY (and its four
#   VELOCITY_SETTINGS siblings), [TRAJ]LINEAR_UNITS/[JOINT_n]UNITS, and
#   (since 13 September 2026) [KINS]JOINTS/KINEMATICS/[TRAJ]COORDINATES/
#   SPINDLES/[DISPLAY]GEOMETRY are all read once by LinuxCNC at process
#   startup, before any HAL component or the GladeVCP panel's own Python
#   (REB_main.py) ever runs - so they can't be corrected from within a
#   running session the way stepgen scale/PID/backlash are (those have
#   real HAL pins). REB_main.py used to patch some of these directly
#   into the tracked REB.ini, but that meant a `git pull` of someone
#   else's REB.ini change could silently overwrite this machine's own
#   choice.
#
#   Run this instead, before every LinuxCNC launch (see REB_Launch.sh):
#   it always starts from the current tracked REB.ini/REB.hal and
#   overlays only the settings below, so upstream edits still flow
#   through untouched and the local choice never gets committed or
#   clobbered.
#
#   REB.local.ini MUST live next to REB.ini (this repo's own directory),
#   not in RoseEngineButlerLocal: LinuxCNC treats the directory of the
#   INI file passed on its command line as "the configuration
#   directory" and resolves every *relative* path found anywhere in that
#   config - REB.ini's own HALFILE=REB.hal and
#   POSTGUI_HALFILE=REB_Display/REB_PostGUI_v1.hal, PARAMETER_FILE=
#   sim.var, and even the relative `loadusr python3
#   REB_Display/REB_Scale_Persist.py` line inside REB_Shutdown.hal -
#   against that one directory. Generating REB.local.ini into
#   RoseEngineButlerLocal instead broke every one of those (confirmed
#   live: "CANNOT FIND FILE FOR:REB.hal" and REB_Scale_Persist.py not
#   found at shutdown). Writing it next to REB.ini keeps the
#   configuration directory exactly where every relative path already
#   expects it.
#
#   ------------------------------------------------------------------
#   Any-role/any-channel generalization (13 September 2026, Rich)
#   ------------------------------------------------------------------
#   Any of 10 roles - the 8 axis letters X,Z,U,V,W,A,B,C or the 2
#   spindles Sp0,Sp1 - can now be assigned to any of the 8 physical hm2
#   stepgen channels (00-07), with exactly 2 of the 10 left unassigned
#   at a time. This replaced the old model where only channels 00-05
#   were reassignable (among 6 axis letters only) and channels 06/07
#   were permanently, uneditably Sp0/Sp1, with A/C never wired at all.
#
#   The key simplification that makes this tractable: every one of the
#   10 roles now permanently owns its own complete HAL identity forever
#   (its own [AXIS_<letter>]/[JOINT_n] REB.ini sections, its own
#   pid.<letter> or pid.pN/pid.sN/orient.N HAL components, its own
#   ROLE_BLOCK_START/END-delimited net/setp block in REB.hal) - unlike
#   the old model, reassignment never renames anything from one role's
#   identity to another's. Only three things are recomputed fresh each
#   launch, from whichever 8 of the 10 roles are currently assigned to
#   a channel:
#     1. Which physical hm2_7i92.0.stepgen.NN channel a role's block
#        targets (and the matching hm2_7i92.0.outm.00.out-NN pin).
#     2. Which LinuxCNC joint number (0..JOINTS-1) an active axis
#        letter's block/[JOINT_n] section is renumbered to - JOINTS
#        itself is no longer a fixed 6, it ranges 6-8 depending how
#        many letters (vs. spindles) are active this launch.
#     3. Which LinuxCNC motion spindle index (0 or 1) an active
#        spindle's block is renumbered to, if fewer than both spindles
#        are active - each spindle's own component identity (pid.p0/
#        s0/orient.0 for Sp0, pid.p1/s1/orient.1 for Sp1) never changes.
#   The 2 currently-unassigned roles' entire REB.hal block is omitted
#   from the generated REB.local.hal outright (their REB.ini sections
#   stay present, just unreferenced by JOINTS/COORDINATES/SPINDLES).
#
#   REB_PostGUI_v1.hal needs NO per-launch substitution at all anymore:
#   its ENA-toggle-chain net names are letter-keyed (b-enable, x-enable,
#   ...) and spindle-keyed (sp0-enable, sp1-enable, ...), which - like
#   every other part of a role's identity - never change; only REB.hal
#   decides which physical channel a role's already-correctly-named
#   signals actually drive. It's copied to REB_PostGUI_v1.local.hal
#   unchanged, purely so POSTGUI_HALFILE can keep pointing at a
#   generated-fresh-each-launch file regardless (see _overlay_hal_files).
#
# End User Customisation:
#   THE END USER OF THE ROSE ENGINE BUTLER SYSTEM SHOULD NOT MODIFY
#   THIS FILE.
#
#   Changes to this file are not supported by Colvin Tools nor
#   Brainwave Embedded.
#
# Version
#   1.0 - 1 August 2026, Claude
#
# Copyright (c) 2026 Colvin Tools and Brainwave Embedded.
#
# The following MIT/X Consortium License applies to the Rose Engine
# Butler system. Use of this system constitutes consent to the terms
# outlined below.
#
# Permission is hereby granted, free of charge, to any person
# obtaining a copy of this software and associated documentation
# files (the "Software"), to deal in the Software without restriction,
# including without limitation the rights to use, copy, modify, merge,
# publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
#       The above copyright notice and this permission notice shall be
#       included in all copies or substantial portions of the
#       Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS
# BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
# ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# Except as contained in this notice, the name of COPYRIGHT HOLDERS
# shall not be used in advertising or otherwise to promote the sale,
# use or other dealings in this Software without prior written
# authorization from COPYRIGHT HOLDERS.
#######################################################################

import os
import re
import sys

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REB_INI_PATH = os.path.join(REPO_DIR, "REB.ini")

# reb_settings_io.py lives in REB_Display/, a sibling directory to this
# script's own REB_Setup/ - not importable without this, since Python
# only puts a script's *own* directory on sys.path automatically.
sys.path.insert(0, os.path.join(REPO_DIR, "REB_Display"))
import reb_settings_io

SETTINGS_PATH = reb_settings_io.SETTINGS_PATH

# Must sit next to REB.ini (not in RoseEngineButlerLocal) - see the file
# header above for why: LinuxCNC resolves every relative path in the
# config (HALFILE, POSTGUI_HALFILE, PARAMETER_FILE, and relative paths
# inside the HAL files themselves) against the directory of whichever
# ini file was actually launched.
LOCAL_INI_PATH = os.path.join(REPO_DIR, "REB.local.ini")


# The 8 axis letters (Y removed - not used on this machine, LATHE=1) and
# the 2 spindles - the 10 possible roles a channel can be assigned.
# Duplicated from REB_Display/reb_settings_io.py's own AXIS_IDS/
# CHANNEL_ROLES (and again in REB_Display/REB_main.py/REB_Scale_Persist.py/
# REB_Settings.py/REB_Settings_Restore.py) - see AXIS_STEPGEN in those
# files for why small maps/tuples like this are duplicated across
# scripts rather than imported.
AXIS_SELECTION_LETTERS = ("X", "Z", "U", "V", "W", "A", "B", "C")
SPINDLE_IDS = ("Sp0", "Sp1")
CHANNEL_ROLES = AXIS_SELECTION_LETTERS + SPINDLE_IDS

# Channel id ("00".."07", the hm2_7i92.0.stepgen.NN suffix) -> the role
# REB.ini/REB.hal ship with by default. Mirrors reb_settings_io.py's own
# CHANNEL_DEFAULT_ROLE.
CHANNEL_DEFAULT_ROLE = {
    "00": "W",
    "01": "Z",
    "02": "U",
    "03": "V",
    "04": "X",
    "05": "B",
    "06": "Sp0",
    "07": "Sp1",
}

# Each axis letter's OWN, PERMANENT [AXIS_<letter>]/[JOINT_n] joint
# number in the tracked REB.ini template - i.e. which [JOINT_n] section
# currently holds that letter's tuning values there. Unlike the old
# (pre-13-September-2026) CHANNEL_JOINT_NUMBER, this is keyed by LETTER,
# not channel id: each letter permanently owns one AXIS_*/JOINT_n
# section pair (added A/C 13 September 2026, joint numbers 8/9 -
# placeholders only, never valid as a FINAL joint number - only 8 real
# channels/joints exist) - reassignment never renames a section, it
# only ever renumbers which JOINT_n a letter's fixed section currently
# is, via _renumber_joint_sections below, computed fresh each launch
# from how many OTHER letters are simultaneously active.
AXIS_TEMPLATE_JOINT_NUMBER = {
    "X": 0, "Z": 1, "B": 2, "U": 3, "V": 4, "W": 5, "A": 8, "C": 9,
}

# The order active letters/spindles are numbered in (0, 1, 2, ... for
# whichever of them are actually assigned to a channel this launch,
# skipping the ones that aren't). Matches AXIS_TEMPLATE_JOINT_NUMBER's
# original 6 values exactly (X=0,Z=1,B=2,U=3,V=4,W=5) so the shipped
# default assignment (only X,Z,U,V,W,B active) needs zero renumbering -
# A and C are appended last, only ever consuming a real joint number
# when actually assigned to a channel.
JOINT_NUMBER_CANONICAL_ORDER = ("X", "Z", "B", "U", "V", "W", "A", "C")
SPINDLE_NUMBER_CANONICAL_ORDER = ("Sp0", "Sp1")

# The 3 GX-12 limit jacks -> the 7i92 I/O pin each is wired to, read as
# plain GPIO (hm2_7i92.0.gpio.NNN.in - REB.hal loads the card with
# num_inms=0, so the firmware's InM pins are GPIO). Jacks 1-3 are
# Input0-2: P2 pins 3, 7, 13. Each jack takes one normally-closed
# limit switch (or both ends of an axis's travel wired in series) and
# may be left empty. What a jack protects, if anything, is the
# operator's choice on REB Settings' Axis Selection page, persisted in
# REBset_v1.ini's "limit_switches" dict: jack -> "<letter>" (both ends of
# that axis, switches in series), "<letter> min" (negative end only),
# "<letter> max" (positive end only), or "" (not used).
# Duplicated in REB_Display/REB_Settings.py's LIMIT_JACKS.
LIMIT_JACK_INPUT = {
    "1": "002",
    "2": "006",
    "3": "010",
}

# The optional E-stop button's GX-16/2 plug (normally-closed, P1 pin 21)
# -> its 7i92 I/O pin (GPIO, as above). Wired into REB.hal's estop-latch.0 only when
# REBset_v1.ini's "estop_button" is true (REB Settings' Axis Selection
# page); otherwise that latch has no fault source and behaves like a
# plain software E-stop loop.
ESTOP_BUTTON_INPUT = "031"

# The optional signal tower's GX-12/4 plug: each light/sounder is
# switched by a relay driven from one 7i92 I/O pin used as a GPIO output.
# Green (P1 pin 25) and red (P2 pin 25) are the firmware's two unassigned
# pins; the buzzer (P1 pin 13) is Input6, freed up by num_inms=0 and kept
# clear of Input3 (P2 pin 21) so more limit jacks can go next to jacks
# 1-3. Only configured as outputs when REBset_v1.ini's "signal_tower"
# is true (REB Settings, Axis Selection page).
# The end(s) of travel a limit jack can cover, by the suffix its
# limit_switches value carries ("" = both ends).
LIMIT_ENDS = {"": "both", " min": "min", " max": "max"}

SIGNAL_TOWER_OUTPUT = {
    "green": "033",
    "red": "016",
    "buzzer": "027",
}

# True for relay boards that switch ON when their input is pulled LOW.
# The 7i92's pull-ups hold every pin high whenever LinuxCNC isn't driving
# it (power-up, after exit), so active-low relays stay off then; an
# active-high board would light/sound everything at every boot.
SIGNAL_TOWER_ACTIVE_LOW = True

# How long the buzzer sounds each time the red light comes on.
SIGNAL_TOWER_BUZZER_SECONDS = 3.0

# Pulse width for tower-red-hold, the oneshot used as the red light's
# following-error latch: long enough to never time out in practice
# (about 31 years); it's cleared by turning the machine back on.
SIGNAL_TOWER_LATCH_SECONDS = 1e9


def _read_channel_assignments(settings):
    '''
    Reads REBset_v1.ini's channel_assignments dict (written by the Axis
    Selection tab - REB_Display/REB_Settings.py's _save_channel_assignments),
    falling back to CHANNEL_DEFAULT_ROLE for any channel that's missing,
    unrecognized, or - defensively, since REBset_v1.ini's own header
    says it should not be hand-edited - assigned to more than one
    channel.
    '''
    assignments = dict(CHANNEL_DEFAULT_ROLE)

    for channel_id, role in settings.get("channel_assignments", {}).items():
        if channel_id in assignments and role in CHANNEL_ROLES:
            assignments[channel_id] = role

    if len(set(assignments.values())) != len(assignments):
        print("Duplicate role(s) in persisted channel_assignments - using shipped defaults")
        return dict(CHANNEL_DEFAULT_ROLE)

    return assignments


def _parse_limit_value(value):
    '''
    "X" -> ("X", "both"), "X min" -> ("X", "min"), "X max" -> ("X", "max");
    anything else (including "") -> None. Mirrors REB_Settings.py's
    _parse_limit_value.
    '''
    for suffix, end in LIMIT_ENDS.items():
        letter = value[:len(value) - len(suffix)] if suffix else value
        if value == letter + suffix and letter in AXIS_SELECTION_LETTERS:
            return letter, end
    return None


def _limit_ends_conflict(end_a, end_b):
    '''
    Two jacks on the same axis conflict unless one is min and the other
    max - "both" already covers either end.
    '''
    return not ({end_a, end_b} == {"min", "max"})


def _read_limit_jacks(settings):
    '''
    Reads REBset_v1.ini's limit_switches dict (written by REB_Settings.py's
    _save_limit_jacks) into jack -> (letter, end), for in-use jacks only.
    An absent, empty, or unrecognized entry means the jack isn't used.
    Defensively (REBset_v1.ini isn't meant to be hand-edited), a jack
    that conflicts with a lower-numbered jack on the same axis (anything
    but a min/max pair) is ignored rather than generating two sources for
    one joint limit pin.
    '''
    jacks = {}
    stored = settings.get("limit_switches", {})
    for jack in sorted(LIMIT_JACK_INPUT):
        parsed = _parse_limit_value(stored.get(jack, ""))
        if parsed is None:
            continue
        letter, end = parsed
        clash = [j for j, (l, e) in jacks.items() if l == letter and _limit_ends_conflict(e, end)]
        if clash:
            print("Limit jack " + jack + ": conflicts with limit jack " + clash[0]
                  + " on axis " + letter + " - ignoring this one")
            continue
        jacks[jack] = (letter, end)
    return jacks


def _read_estop_button(settings):
    '''
    Whether REBset_v1.ini marks the optional E-stop button as connected
    (REB_Settings.py's _save_estop_button). Absent means not connected.
    '''
    return settings.get("estop_button") is True


def _read_signal_tower(settings):
    '''
    Whether REBset_v1.ini marks the optional signal tower as connected
    (REB_Settings.py's _save_signal_tower). Absent means not connected.
    '''
    return settings.get("signal_tower") is True


def _signal_tower_hal(signal_tower, limit_nets, role_layout):
    '''
    Returns HAL text driving the optional signal tower's three relay
    outputs when signal_tower is True:
      - green: on while the system is doing something - the interpreter
        isn't idle (a G-code program or MDI command: Sync Move,
        Threading, axis indexing, ...), or an active spindle is running
        (spindle.N-cw/-ccw - Run Operation, M3/M4, which finish as MDI
        commands at once while the spindle keeps turning), or an active
        spindle is indexing (its orient is enabled but not yet
        is-oriented - covers both the M19 single-spindle path, which
        leaves orient enabled afterwards to hold position, and the
        Sp0+Sp1 path through Sp<n>-idx-active). OR'd by tower-green-or;
        the NOTs are logic NANDs with both inputs on the same signal,
        since not/and2 are already loaded elsewhere under fixed names.
      - red: on after any active joint exceeds its following error, until
        the machine is turned back on (F2), and while any in-use limit
        jack is tripped (limit_nets, from _limit_jack_hal). LinuxCNC does
        NOT hold joint.N.f-errored - it clears as the machine turns off,
        within a servo cycle or so (found live 05 Oct 2026: red never
        lit) - and a limit trip can be just as brief (the switch closes
        again once the axis stops; found live the same day: the buzzer
        sounded but red didn't stay lit). So following errors and limit
        trips (OR'd by tower-fault-or) trigger tower-red-hold, a oneshot
        with a practically endless pulse that acts as a latch, reset by
        tower-on-edge's short pulse when machine-is-on rises (F2 - both
        faults turn the machine off). tower-red-or then ORs the latch
        with the live limit nets, so a switch still open after F2 keeps
        red lit until the axis is moved off it.
      - buzzer: a SIGNAL_TOWER_BUZZER_SECONDS pulse from a oneshot each
        time red rises.
    With the tower off the pins are left as inputs, so nothing drives
    the relays. Pin levels follow SIGNAL_TOWER_ACTIVE_LOW.
    '''
    lines = [
        "",
        "# ********************************************************************",
        "# Signal tower - generated by REB_Generate_Local_Ini.py from",
        "# REBset_v1.ini's signal_tower (REB Settings, Axis Selection page).",
        "# ********************************************************************",
    ]
    if not signal_tower:
        lines.append("# (signal tower not connected)")
        return "\n".join(lines) + "\n"

    joints = sorted(role_layout.joint_number.values())
    red_inputs = ["tower-red-held"] + sorted(limit_nets)
    logic = [("tower-fault-or", "0x2%02x" % (len(joints) + len(limit_nets)))]
    if len(red_inputs) > 1:
        logic.append(("tower-red-or", "0x2%02x" % len(red_inputs)))

    # Green: not idle, or any active spindle running or indexing. Each
    # spindle's nets carry its LinuxCNC spindle number this launch
    # (spindle.<n>-cw ...); its orient-done net keeps its role's name.
    oriented_net = {"Sp0": "orient-done", "Sp1": "orient.1-done"}
    green_inputs = ["tower-not-idle"]
    spindle_lines = []
    logic.append(("tower-not-idle-nand", "0x802"))
    for role, n in sorted(role_layout.spindle_number.items(), key=lambda kv: kv[1]):
        tag = "tower-sp%d" % n
        logic.append((tag + "-not-oriented", "0x802"))
        logic.append((tag + "-indexing", "0x102"))
        spindle_lines += [
            ("net " + oriented_net[role]).ljust(41) + "=> %s-not-oriented.in-00" % tag,
            ("net " + oriented_net[role]).ljust(41) + "=> %s-not-oriented.in-01" % tag,
            ("net %s-not-oriented" % tag).ljust(40) + "<=  %s-not-oriented.nand" % tag,
            ("net %s-not-oriented" % tag).ljust(41) + "=> %s-indexing.in-00" % tag,
            ("net spindle.%d-pos-mode-enable" % n).ljust(41) + "=> %s-indexing.in-01" % tag,
            ("net %s-indexing" % tag).ljust(40) + "<=  %s-indexing.and" % tag,
        ]
        green_inputs += ["spindle.%d-cw" % n, "spindle.%d-ccw" % n, tag + "-indexing"]
    if len(green_inputs) > 1:
        logic.append(("tower-green-or", "0x2%02x" % len(green_inputs)))
    # Buzzer: the fault siren OR'd with REB_main.py's attention beeps
    # (gladevcp.tower-beep, netted to in-01 by _tower_beep_postgui_hal,
    # since that pin only exists once the GUI is up).
    logic.append(("tower-buzzer-or", "0x202"))

    lines += [
        "loadrt logic names=%s personality=%s" % (",".join(n for n, _ in logic), ",".join(p for _, p in logic)),
        "loadrt oneshot names=tower-buzz,tower-red-hold,tower-on-edge",
    ]
    for name in [n for n, _ in logic] + ["tower-red-hold", "tower-on-edge", "tower-buzz"]:
        lines.append(("addf " + name).ljust(44) + "servo-thread")
    lines += [
        "setp tower-buzz.width".ljust(44) + str(SIGNAL_TOWER_BUZZER_SECONDS),
        "# Practically endless pulse = a latch, cleared by tower-red-reset.",
        "setp tower-red-hold.width".ljust(44) + str(SIGNAL_TOWER_LATCH_SECONDS),
        "setp tower-on-edge.width".ljust(44) + "0.05",
        "",
    ]
    for i, j in enumerate(joints):
        net = "net tower-ferror-%d" % j
        lines.append(net.ljust(40) + "<=  joint.%d.f-errored" % j)
        lines.append(net.ljust(41) + "=> tower-fault-or.in-%02d" % i)
    for i, net in enumerate(sorted(limit_nets), start=len(joints)):
        lines.append(("net " + net).ljust(41) + "=> tower-fault-or.in-%02d" % i)
    lines += [
        "net tower-fault".ljust(40) + "<=  tower-fault-or.or",
        "net tower-fault".ljust(41) + "=> tower-red-hold.in",
        "net machine-is-on".ljust(41) + "=> tower-on-edge.in",
        "net tower-red-reset".ljust(40) + "<=  tower-on-edge.out",
        "net tower-red-reset".ljust(41) + "=> tower-red-hold.reset",
        "net tower-red-held".ljust(40) + "<=  tower-red-hold.out",
    ]
    lines += [
        "",
        "net tower-green-idle".ljust(40) + "<=  halui.program.is-idle",
        "net tower-green-idle".ljust(41) + "=> tower-not-idle-nand.in-00",
        "net tower-green-idle".ljust(41) + "=> tower-not-idle-nand.in-01",
        "net tower-not-idle".ljust(40) + "<=  tower-not-idle-nand.nand",
    ] + spindle_lines
    if len(green_inputs) > 1:
        for i, net in enumerate(green_inputs):
            lines.append(("net " + net).ljust(41) + "=> tower-green-or.in-%02d" % i)
        lines.append("net tower-green".ljust(40) + "<=  tower-green-or.or")
        green_net = "tower-green"
    else:
        green_net = "tower-not-idle"   # no spindles assigned
    lines.append(("net " + green_net).ljust(41) + "=> hm2_7i92.0.gpio." + SIGNAL_TOWER_OUTPUT["green"] + ".out")
    if len(red_inputs) > 1:
        for i, net in enumerate(red_inputs):
            lines.append(("net " + net).ljust(41) + "=> tower-red-or.in-%02d" % i)
        red_source = "tower-red-or.or"
    else:
        red_source = None   # no limit jacks: the latch alone is red
    lines.append("")
    if red_source:
        lines.append("net tower-red".ljust(40) + "<=  " + red_source)
        red_net = "tower-red"
    else:
        red_net = "tower-red-held"
    lines += [
        ("net " + red_net).ljust(41) + "=> hm2_7i92.0.gpio." + SIGNAL_TOWER_OUTPUT["red"] + ".out",
        ("net " + red_net).ljust(41) + "=> tower-buzz.in",
        "net tower-siren".ljust(40) + "<=  tower-buzz.out",
        "net tower-siren".ljust(41) + "=> tower-buzzer-or.in-00",
        "net tower-buzzer".ljust(40) + "<=  tower-buzzer-or.or",
        "net tower-buzzer".ljust(41) + "=> hm2_7i92.0.gpio." + SIGNAL_TOWER_OUTPUT["buzzer"] + ".out",
        "",
    ]
    out_true_means_on = {"green": True, "red": True, "buzzer": True}
    for color in ("green", "red", "buzzer"):
        pin = "hm2_7i92.0.gpio." + SIGNAL_TOWER_OUTPUT[color]
        # Active-low: ON must drive the pin low, so invert exactly when
        # .out is true for ON. Active-high: the opposite.
        invert = out_true_means_on[color] == SIGNAL_TOWER_ACTIVE_LOW
        lines.append(("setp " + pin + ".is_output").ljust(44) + "1")
        lines.append(("setp " + pin + ".invert_output").ljust(44) + ("1" if invert else "0"))
    return "\n".join(lines) + "\n"


def _tower_beep_postgui_hal(signal_tower):
    '''
    Returns HAL text, appended to REB_PostGUI_v1.local.hal, netting the
    main panel's attention-beep pin (REB_main.py's _load_sounds) into
    the buzzer's OR gate - post-GUI because gladevcp's pins don't exist
    until the panel has loaded. Empty with the tower off, since
    tower-buzzer-or then doesn't exist.
    '''
    if not signal_tower:
        return ""
    return "\n".join([
        "",
        "# ********************************************************************",
        "# Signal tower attention beeps - generated by REB_Generate_Local_Ini.py",
        "# (REBset_v1.ini's signal_tower is true).",
        "# ********************************************************************",
        "net tower-beep".ljust(40) + "<=  gladevcp.tower-beep",
        "net tower-beep".ljust(41) + "=> tower-buzzer-or.in-01",
    ]) + "\n"


def _limit_jack_hal(limit_jacks, role_layout):
    '''
    Returns (HAL text, summary list, limit net names) wiring each in-use
    limit jack's 7i92 input straight to its axis's joint limit pin(s):
    "min" -> joint.N.neg-lim-sw-in (net <letter>-limit-min), "max" ->
    joint.N.pos-lim-sw-in (<letter>-limit-max), "both" -> both pins
    (<letter>-limit-sw, the switches at each end wired in series). REB.hal
    doesn't touch those pins at all, so a joint with no jack keeps them
    false. Separate min/max jacks let LinuxCNC tell which end tripped, so
    the operator can jog away from it without Override Limits. A jack
    whose axis isn't assigned to any channel this launch is skipped.

    Uses the GPIO's .in (not .in_not): a normally-closed switch to ground
    holds the input low; a tripped switch or broken wire lets the 7i92's
    pull-up take it high, which reads as a limit hit.
    '''
    lines = [
        "",
        "# ********************************************************************",
        "# Limit switch jacks - generated by REB_Generate_Local_Ini.py from",
        "# REBset_v1.ini's limit_switches (REB Settings, Axis Selection page).",
        "# ********************************************************************",
    ]
    summary = []
    nets = []
    for jack in sorted(limit_jacks):
        letter, end = limit_jacks[jack]
        if letter not in role_layout.channel_of:
            print("Limit jack " + jack + ": axis " + letter
                  + " isn't assigned to a channel - jack ignored this launch")
            continue
        joint = "joint." + str(role_layout.joint_number[letter])
        net = letter.lower() + ("-limit-sw" if end == "both" else "-limit-" + end)
        pins = {"min": ["neg-lim-sw-in"], "max": ["pos-lim-sw-in"],
                "both": ["neg-lim-sw-in", "pos-lim-sw-in"]}[end]
        lines.append(("net " + net).ljust(40) + "<=  hm2_7i92.0.gpio." + LIMIT_JACK_INPUT[jack] + ".in")
        for pin in pins:
            lines.append(("net " + net).ljust(41) + "=> " + joint + "." + pin)
        summary.append("jack " + jack + " -> " + letter + ("" if end == "both" else " " + end))
        nets.append(net)
    if not summary:
        lines.append("# (no limit jacks in use)")
    return "\n".join(lines) + "\n", summary, nets


def _estop_button_hal(estop_button):
    '''
    Returns HAL text wiring the optional E-stop button's 7i92 input into
    REB.hal's estop-latch.0 fault-in when estop_button is True. GPIO
    .in, same reasoning as _limit_jack_hal: a normally-closed button
    to ground holds it low; pressed, broken, or unplugged reads high,
    which latches E-stop.
    '''
    lines = [
        "",
        "# ********************************************************************",
        "# E-stop button - generated by REB_Generate_Local_Ini.py from",
        "# REBset_v1.ini's estop_button (REB Settings, Axis Selection page).",
        "# ********************************************************************",
    ]
    if estop_button:
        lines.append("net estop-button".ljust(40) + "<=  hm2_7i92.0.gpio." + ESTOP_BUTTON_INPUT + ".in")
        lines.append("net estop-button".ljust(41) + "=> estop-latch.0.fault-in")
    else:
        lines.append("# (E-stop button not connected - software E-stop only)")
    return "\n".join(lines) + "\n"


class RoleLayout(object):
    '''
    Everything derived from one launch's channel_assignments: which of
    the 10 roles are active (assigned to some channel) vs. not, which
    channel each active role targets, and - for active roles only -
    which joint number (axis letters) or spindle index (spindles) that
    role's HAL block should be renumbered to.
    '''
    def __init__(self, assignments):
        self.channel_of = {}
        for channel_id, role in assignments.items():
            self.channel_of[role] = channel_id

        active_letters = [l for l in JOINT_NUMBER_CANONICAL_ORDER if l in self.channel_of]
        active_spindles = [s for s in SPINDLE_NUMBER_CANONICAL_ORDER if s in self.channel_of]

        self.joint_number = {letter: i for i, letter in enumerate(active_letters)}
        self.spindle_number = {spindle_id: i for i, spindle_id in enumerate(active_spindles)}
        self.active_letters = active_letters
        self.active_spindles = active_spindles
        self.inactive_roles = [r for r in CHANNEL_ROLES if r not in self.channel_of]


# ----------------------------------------------------------------------
# REB.ini overlay: renumber each active letter's [JOINT_n] section and
# rewrite the [KINS]/[TRAJ]/[DISPLAY] joint/spindle-count and
# coordinate-order keys to match. TYPE/UNITS never need touching here -
# unlike the old model, a section is never relabeled to a different
# letter (each letter permanently owns its own AXIS_*/JOINT_n section),
# so a letter's TYPE (fixed: A/B/C angular, else linear) never changes.

def _renumber_joint_sections(text, joint_number):
    '''
    Renumbers every axis letter's [JOINT_n] section header to
    joint_number[letter] (only for letters actually assigned to a
    channel this launch - joint_number's keys). Every OTHER letter
    (not currently assigned to any channel) is parked at a safe
    sentinel number (90, 91, ...) that can never collide with a real
    0-7 target - harmless, since an unparked/inactive letter's section
    is never referenced by JOINTS/COORDINATES anyway.

    Safe against any permutation of letters exchanging joint numbers
    with each other (e.g. two channels swapping which letter they hold,
    each of which now needs the OTHER's old joint number) via the same
    two-phase-through-a-placeholder technique this repo already uses
    for exactly this kind of swap-safety concern elsewhere (see
    REB_Setup/REB_Generate_Local_Ini.py's git history / CLAUDE.md): each
    changed section is first renamed to a per-letter placeholder that
    can never collide with any real or another letter's target number,
    and only once every section has been safely relabeled are the
    placeholders resolved to their final numbers.

    Returns (text, targets) where targets is letter -> final joint
    number (including parked/inactive letters, for the caller's own
    bookkeeping/prints).
    '''
    # Phase 1: locate every letter's current [JOINT_<template>] section
    # span against the pristine, unmodified text.
    spans = {}
    for letter, template_num in AXIS_TEMPLATE_JOINT_NUMBER.items():
        pattern = re.compile(
            r'(?m)(^\[JOINT_' + str(template_num) + r'\].*?)(?=\n\[|\Z)',
            re.DOTALL,
        )
        match = pattern.search(text)
        if match:
            spans[letter] = (match.start(1), match.end(1), match.group(1))
        else:
            print("Could not find [JOINT_" + str(template_num) + "] (" + letter + ") in REB.ini")

    # Every letter's final target number: active letters get their
    # computed joint number. An inactive letter keeps its own template
    # number unchanged UNLESS that number is also some active letter's
    # target (a real collision - two [JOINT_n] sections can't share a
    # number) - only then is it parked at a safe sentinel (90, 91, ...)
    # instead. This is what makes the shipped default assignment need
    # zero renumbering at all: none of A/C's template numbers (8, 9)
    # ever collide with an active letter's target (always 0-7).
    targets = dict(joint_number)
    active_target_values = set(targets.values())
    sentinel = 90
    for letter, template_num in AXIS_TEMPLATE_JOINT_NUMBER.items():
        if letter in targets:
            continue
        if template_num in active_target_values:
            targets[letter] = sentinel
            sentinel += 1
        else:
            targets[letter] = template_num

    # Phase 2: rename each changed section's header to a per-letter
    # placeholder, splicing back from the end of the document backwards
    # so no edit shifts another still-pending edit's recorded position.
    edits = []
    for letter, (start, end, section_text) in spans.items():
        template_num = AXIS_TEMPLATE_JOINT_NUMBER[letter]
        target_num = targets[letter]
        if target_num == template_num:
            continue
        new_text = re.sub(
            r'(?m)^\[JOINT_' + str(template_num) + r'\]',
            '[JOINT_PLACEHOLDER_' + letter + ']',
            section_text,
            count=1,
        )
        edits.append((start, end, new_text))

    for start, end, new_text in sorted(edits, key=lambda e: e[0], reverse=True):
        text = text[:start] + new_text + text[end:]

    # Phase 3: placeholder -> final number. A plain literal replace is
    # safe here - each placeholder string is unique per letter and
    # cannot appear anywhere else in the file.
    for letter, template_num in AXIS_TEMPLATE_JOINT_NUMBER.items():
        target_num = targets[letter]
        if target_num != template_num:
            text = text.replace(
                '[JOINT_PLACEHOLDER_' + letter + ']',
                '[JOINT_' + str(target_num) + ']',
            )

    return text, targets


def _overlay_role_assignment(text, role_layout):
    '''
    Renumbers REB.ini's [JOINT_n] sections (see _renumber_joint_sections)
    and rewrites [KINS]JOINTS/KINEMATICS coordinates=, [TRAJ]COORDINATES/
    SPINDLES, and [DISPLAY]GEOMETRY to match role_layout - the current
    channel_assignments, resolved into which axis letters/spindles are
    active and which joint/spindle number each active one now has (see
    RoleLayout). Returns (text, summary) where summary is None if
    nothing needed changing (the shipped default assignment needs no
    renumbering at all - see JOINT_NUMBER_CANONICAL_ORDER).
    '''
    text, targets = _renumber_joint_sections(text, role_layout.joint_number)
    changed = any(
        targets[letter] != AXIS_TEMPLATE_JOINT_NUMBER[letter]
        for letter in AXIS_TEMPLATE_JOINT_NUMBER
    )

    coordinates = "".join(role_layout.active_letters)
    joints = len(role_layout.active_letters)
    # Never 0, even with neither Sp0 nor Sp1 assigned: LinuxCNC 2.9's
    # milltask refuses [TRAJ]SPINDLES = 0 ("emcTrajSetSpindles failing:
    # spindles=0") and never finishes starting. With no spindle role
    # active, spindle.0 just exists unconnected - REB.local.hal leaves
    # out both spindle blocks regardless.
    spindles = max(1, len(role_layout.active_spindles))

    text, n1 = re.subn(
        r'(?m)^(JOINTS\s*= )\S+',
        lambda m: m.group(1) + str(joints),
        text,
        count=1,
    )
    text, n2 = re.subn(
        r'(?m)^(KINEMATICS\s*= trivkins coordinates=)\S+',
        lambda m: m.group(1) + coordinates,
        text,
        count=1,
    )
    text, n3 = re.subn(
        r'(?m)^(COORDINATES\s*= )\S+',
        lambda m: m.group(1) + coordinates,
        text,
        count=1,
    )
    text, n4 = re.subn(
        r'(?m)^(SPINDLES\s*= )\S+',
        lambda m: m.group(1) + str(spindles),
        text,
        count=1,
    )
    text, n5 = re.subn(
        r'(?m)^(GEOMETRY\s*= )\S+',
        lambda m: m.group(1) + coordinates,
        text,
        count=1,
    )

    if not changed and joints == 6 and spindles == 2 and coordinates == "XZBUVW":
        return text, None

    summary = (
        "coordinates=" + coordinates + " (JOINTS=" + str(joints) + ", "
        + str(n1) + " JOINTS/" + str(n2) + " KINEMATICS/" + str(n3)
        + " COORDINATES/" + str(n5) + " GEOMETRY line(s)), SPINDLES="
        + str(spindles) + " (" + str(n4) + " line(s)), joint numbers: "
        + ", ".join(letter + "=" + str(targets[letter]) for letter in AXIS_TEMPLATE_JOINT_NUMBER
                     if letter in role_layout.joint_number)
    )
    return text, summary


def _overlay_max_jog_speed(text, settings):
    # settings is always fully populated (reb_settings_io.load_settings()
    # fills in any absent key from default_settings(), which mirrors
    # REB.ini's own shipped starting value here) - so this always
    # overlays, unlike the old per-tag XML presence check. A machine
    # that has never saved any REBset_v1.ini setting at all still gets
    # REB.ini's own value here (defaults match); one that has saved
    # anything gets whatever's actually persisted, customized or not -
    # see reb_settings_io.py's module docstring for why REBset_v1.ini
    # is a full snapshot rather than a set of independently-optional
    # keys once anything has ever been saved to it.
    value_text = "%.4f" % float(settings["max_jog_speed"])
    text, n = re.subn(
        r'(?m)^(MAX_LINEAR_VELOCITY\s*= )\S+',
        lambda m: m.group(1) + value_text,
        text,
    )
    return text, (value_text, n)


# REB_Settings_v1.ini tag -> REB.ini key, for the five jog-speed values
# the Settings tab's General tab makes user-editable alongside Max Jog
# Speed above. Mirrors VELOCITY_SETTINGS in REB_main.py (see AXIS_STEPGEN
# there for why small constants like this are duplicated across scripts
# rather than imported). Each key is overlaid everywhere it appears in
# REB.ini - both [DISPLAY] (jog slider) and [TRAJ] (trajectory-planner
# ceiling) for the three keys present in both sections - same as
# MAX_LINEAR_VELOCITY above, per an explicit decision to unify them
# under one operator-facing control rather than leave two different
# values behind one label.
VELOCITY_SETTINGS = {
    "default_linear_velocity":  "DEFAULT_LINEAR_VELOCITY",
    "min_linear_velocity":      "MIN_LINEAR_VELOCITY",
    "max_angular_velocity":     "MAX_ANGULAR_VELOCITY",
    "default_angular_velocity": "DEFAULT_ANGULAR_VELOCITY",
    "min_angular_velocity":     "MIN_ANGULAR_VELOCITY",
}


def _overlay_velocity_setting(text, settings, settings_key, ini_key):
    value_text = "%.6f" % float(settings[settings_key])
    text, n = re.subn(
        r'(?m)^(' + ini_key + r'\s*= )\S+',
        lambda m: m.group(1) + value_text,
        text,
    )
    return text, (value_text, n)


def _overlay_measurement_system(text, settings):
    system = settings.get("measurement_system", "Imperial")
    if system not in ("Metric", "Imperial"):
        system = "Imperial"

    if system == "Metric":
        linear_units, joint_units = "mm", "MM"
    else:
        linear_units, joint_units = "inch", "INCH"

    # Matches REB.ini's existing casing convention: LINEAR_UNITS lowercase
    # ("inch"/"mm"), per-joint UNITS uppercase ("INCH"/"MM") - both accepted
    # case-insensitively by LinuxCNC. Angular [JOINT_n] sections use
    # UNITS = DEGREE and are never matched by the INCH/MM pattern below,
    # so they're left untouched.
    text, n1 = re.subn(
        r'(?m)^(LINEAR_UNITS\s*= )\S+',
        lambda m: m.group(1) + linear_units,
        text,
        count=1,
    )
    text, n2 = re.subn(
        r'(?m)^(UNITS\s*= )(INCH|MM)$',
        lambda m: m.group(1) + joint_units,
        text,
    )
    return text, (system, n1, n2)


def _overlay_backlash(text, settings, role_layout):
    '''
    Writes each active axis letter's persisted backlash (REBset_v1.ini
    axes.<letter>.backlash) into its own [JOINT_n]BACKLASH, n being this
    launch's joint number for that letter - so must run after
    _overlay_role_assignment has renumbered the [JOINT_n] sections.

    This is the only way a persisted backlash reaches LinuxCNC at
    startup: LinuxCNC 2.9 has no joint.N.backlash HAL parameter to set
    after the fact (its only live handle is inihal's ini.N.backlash pin,
    which REB_Settings.py's Backlash fields set while running, and which
    doesn't exist yet when REB.hal loads). Spindles have no [JOINT_n]
    and no backlash compensation of their own, so they're skipped.
    Returns (text, list of "letter=value" applied).
    '''
    axes = settings.get("axes", {})
    applied = []
    for letter, joint_num in role_layout.joint_number.items():
        try:
            value = float(axes.get(letter, {})["backlash"])
        except (KeyError, TypeError, ValueError):
            continue
        header = "[JOINT_" + str(joint_num) + "]"
        start = text.find("\n" + header + "\n")
        if start < 0:
            continue
        end = text.find("\n[", start + 1)
        if end < 0:
            end = len(text)
        section, n = re.subn(
            r'(?m)^(BACKLASH\s*= )\S+',
            lambda m: m.group(1) + "%.6f" % value,
            text[start:end],
            count=1,
        )
        if n:
            text = text[:start] + section + text[end:]
            applied.append(letter + "=" + "%g" % value)
    return text, applied


# ----------------------------------------------------------------------
# REB.hal regeneration. REB_PostGUI_v1.hal needs no per-launch
# substitution at all (see this file's own header) and is simply copied
# unchanged to REB_PostGUI_v1.local.hal.
#
# Every one of the 10 roles owns a permanent, self-contained
# "# ROLE_BLOCK_START: <role>" ... "# ROLE_BLOCK_END: <role>"-delimited
# region in REB.hal (added 13 September 2026 alongside the AXIS_A/
# AXIS_C blocks - see REB.hal itself). Regeneration is then just:
# for each of the 8 currently-active roles, retarget its own isolated
# block's channel number (and joint/spindle number) and keep it; for
# the 2 currently-inactive roles, omit their block entirely. Because
# each role's substitutions are performed on an ISOLATED slice of text
# (not the whole file), there is no risk of one role's rename
# accidentally touching another's tokens - unlike the old (pre-13-
# September-2026) letter-token-renaming approach, which had to share
# a fixed pool of 6 channel slots among letters and therefore needed a
# two-phase placeholder-swap to stay safe against arbitrary
# permutations. That whole mechanism (AXIS_STEPGEN-style letter-token
# renaming across the whole file) is retired along with it.

HAL_PATH = os.path.join(REPO_DIR, "REB.hal")
LOCAL_HAL_PATH = os.path.join(REPO_DIR, "REB.local.hal")
POSTGUI_HAL_PATH = os.path.join(REPO_DIR, "REB_Display", "REB_PostGUI_v1.hal")
LOCAL_POSTGUI_HAL_PATH = os.path.join(REPO_DIR, "REB_Display", "REB_PostGUI_v1.local.hal")


def _extract_role_blocks(hal_text):
    '''
    Returns role -> (start, end) character spans (marker lines
    included) for every "# ROLE_BLOCK_START: <role>" ... "# ROLE_BLOCK_END:
    <role>" region in hal_text.
    '''
    blocks = {}
    for match in re.finditer(r'(?m)^# ROLE_BLOCK_START: (\S+)\n', hal_text):
        role = match.group(1)
        start = match.start()
        end_marker = "# ROLE_BLOCK_END: " + role + "\n"
        end_index = hal_text.index(end_marker, match.end())
        blocks[role] = (start, end_index + len(end_marker))
    return blocks


def _retarget_channel(block_text, role, channel_id, problems):
    '''
    Common to every role (axis letter or spindle): repoints its
    hm2_7i92.0.stepgen.NN.*/outm.00.out-NN references at channel_id.
    Every role's block has exactly one distinct old channel number
    embedded this way (verified below) - safe to blanket-replace within
    this isolated block text.
    '''
    match = re.search(r'hm2_7i92\.0\.stepgen\.(\d\d)\.', block_text)
    if not match:
        problems.append(role + "'s block has no hm2_7i92.0.stepgen.NN. reference to retarget")
        return block_text
    old_channel = match.group(1)
    if old_channel != channel_id:
        block_text = block_text.replace("stepgen." + old_channel + ".", "stepgen." + channel_id + ".")
        block_text = re.sub(r'out-' + old_channel + r'(?![\w-])', "out-" + channel_id, block_text)
    return block_text


def _retarget_axis_block(block_text, letter, channel_id, joint_num, problems):
    block_text = _retarget_channel(block_text, letter, channel_id, problems)

    match = re.search(r'\[JOINT_(\d+)\]', block_text)
    if not match:
        problems.append(letter + "'s block has no [JOINT_n] reference to retarget")
        return block_text
    old_joint = match.group(1)
    new_joint = str(joint_num)
    if old_joint != new_joint:
        block_text = re.sub(r'\[JOINT_' + old_joint + r'\]', '[JOINT_' + new_joint + ']', block_text)
        block_text = re.sub(r'joint\.' + old_joint + r'\.', 'joint.' + new_joint + '.', block_text)
    return block_text


def _retarget_spindle_block(block_text, spindle_id, channel_id, spindle_num, problems):
    block_text = _retarget_channel(block_text, spindle_id, channel_id, problems)

    match = re.search(r'spindle\.(\d)[.\-]', block_text)
    if not match:
        problems.append(spindle_id + "'s block has no spindle.N reference to retarget")
        return block_text
    old_index = match.group(1)
    new_index = str(spindle_num)
    if old_index != new_index:
        block_text = re.sub(
            r'spindle\.' + old_index + r'([.\-])',
            'spindle.' + new_index + r'\1',
            block_text,
        )
    return block_text


def generate_local_hal_files(role_layout, limit_jacks=None, estop_button=False,
                             signal_tower=False):
    '''
    Regenerates REB.local.hal from the tracked REB.hal: for each of the
    8 currently-active roles, retargets its own isolated
    ROLE_BLOCK-delimited region's channel number (and joint number for
    an axis letter, or spindle index for a spindle) and keeps it; the 2
    currently-inactive roles' entire block is omitted. Then appends the
    in-use limit jacks', E-stop button's and signal tower's wiring
    (_limit_jack_hal/_estop_button_hal/_signal_tower_hal). Copies
    REB_PostGUI_v1.hal to REB_PostGUI_v1.local.hal unchanged (see this
    file's own header for why no substitution is needed there).

    Always writes both files, even with the shipped default assignment
    (an unchanged copy) - see _overlay_hal_files, which always points
    REB.local.ini's HALFILE/POSTGUI_HALFILE at these generated files
    regardless, so behavior doesn't depend on whether the operator has
    ever touched the Axis Selection tab.

    Returns True on success (both files written). Returns False,
    writing NEITHER file, if any problem is found while retargeting -
    refuses to leave a broken, half-generated .local.hal for LinuxCNC to
    load in that case; the caller should treat False as fatal.
    '''
    try:
        with open(HAL_PATH, "r") as f:
            hal_text = f.read()
    except OSError as e:
        print("Could not read " + HAL_PATH + ": " + str(e))
        return False

    try:
        with open(POSTGUI_HAL_PATH, "r") as f:
            postgui_text = f.read()
    except OSError as e:
        print("Could not read " + POSTGUI_HAL_PATH + ": " + str(e))
        return False

    blocks = _extract_role_blocks(hal_text)
    problems = []
    for role in CHANNEL_ROLES:
        if role not in blocks:
            problems.append("REB.hal: no ROLE_BLOCK_START/END markers found for " + role)
    if problems:
        print("REFUSING to write REB.local.hal - template problem(s):")
        for problem in problems:
            print("  " + problem)
        return False

    ordered_blocks = sorted(blocks.items(), key=lambda kv: kv[1][0])
    pieces = []
    cursor = 0
    retargeted = []
    for role, (start, end) in ordered_blocks:
        pieces.append(hal_text[cursor:start])
        if role in role_layout.channel_of:
            channel_id = role_layout.channel_of[role]
            block_text = hal_text[start:end]
            if role in AXIS_SELECTION_LETTERS:
                block_text = _retarget_axis_block(
                    block_text, role, channel_id, role_layout.joint_number[role], problems)
            else:
                block_text = _retarget_spindle_block(
                    block_text, role, channel_id, role_layout.spindle_number[role], problems)
            pieces.append(block_text)
            retargeted.append(role + " -> channel " + channel_id)
        # else: role is inactive this launch - omit its block entirely.
        cursor = end
    pieces.append(hal_text[cursor:])
    hal_text = "".join(pieces)

    # Goes just before REB.hal's closing "NOTHING FOLLOWS" banner, if
    # present, so that banner still ends the file.
    limit_text, limit_summary, limit_nets = _limit_jack_hal(limit_jacks or {}, role_layout)
    limit_text += _estop_button_hal(estop_button)
    limit_text += _signal_tower_hal(signal_tower, limit_nets, role_layout)
    end_banner = hal_text.rfind("\n# *********************** NOTHING FOLLOWS")
    if end_banner == -1:
        hal_text += limit_text
    else:
        hal_text = hal_text[:end_banner] + limit_text + hal_text[end_banner:]
    postgui_text += _tower_beep_postgui_hal(signal_tower)

    if problems:
        print("REFUSING to write REB.local.hal - generation problem(s):")
        for problem in problems:
            print("  " + problem)
        return False

    try:
        with open(LOCAL_HAL_PATH, "w") as f:
            f.write(hal_text)
        with open(LOCAL_POSTGUI_HAL_PATH, "w") as f:
            f.write(postgui_text)
    except OSError as e:
        print("Could not write generated .local.hal file: " + str(e))
        return False

    print("Regenerated REB.local.hal: " + ", ".join(retargeted))
    print("Limit jacks: " + (", ".join(limit_summary) or "none in use"))
    print("E-stop button: " + ("connected" if estop_button else "not connected"))
    print("Signal tower: " + ("connected" if signal_tower else "not connected"))
    if role_layout.inactive_roles:
        print("Not currently assigned to any channel: " + ", ".join(role_layout.inactive_roles))
    print("Wrote " + LOCAL_HAL_PATH + " and " + LOCAL_POSTGUI_HAL_PATH +
          (" (copy plus tower beep net)" if signal_tower else " (unchanged copy)"))
    return True


def _overlay_hal_files(text):
    '''
    Points REB.local.ini's HALFILE/POSTGUI_HALFILE at the freshly
    generated REB.local.hal/REB_PostGUI_v1.local.hal (written by
    generate_local_hal_files, which must run first - see main()) instead
    of the tracked REB.hal/REB_PostGUI_v1.hal - always, even with no
    reassignment made, so REB.local.ini's behavior doesn't depend on
    whether the operator has ever touched the Axis Selection tab. Only
    touches the one active `HALFILE = REB.hal` line (REB.ini also has a
    second, different `HALFILE = REB_Custom/REB_Custom.hal` line, and a
    commented-out `# HALFILE = REB_Spindle.hal` line - neither matches
    this pattern's exact anchored value).
    '''
    text, n1 = re.subn(
        r'(?m)^(HALFILE\s*= )REB\.hal$',
        r'\1REB.local.hal',
        text,
        count=1,
    )
    text, n2 = re.subn(
        r'(?m)^(POSTGUI_HALFILE\s*= )REB_Display/REB_PostGUI_v1\.hal$',
        r'\1REB_Display/REB_PostGUI_v1.local.hal',
        text,
        count=1,
    )
    return text, (n1, n2)


def main():
    try:
        with open(REB_INI_PATH, "r") as f:
            text = f.read()
    except OSError as e:
        print("Could not read " + REB_INI_PATH + ": " + str(e))
        sys.exit(1)

    settings = reb_settings_io.load_settings()
    assignments = _read_channel_assignments(settings)
    role_layout = RoleLayout(assignments)

    # Regenerate REB.local.hal/REB_PostGUI_v1.local.hal FIRST and abort
    # immediately if it fails (see generate_local_hal_files) - if the
    # realtime wiring can't be regenerated safely, don't write a
    # REB.local.ini that would point at it (or at a stale previous
    # .local.hal left over from a different assignment) anyway.
    if not generate_local_hal_files(role_layout, _read_limit_jacks(settings),
                                    _read_estop_button(settings),
                                    _read_signal_tower(settings)):
        sys.exit(1)

    text, hal_files_result = _overlay_hal_files(text)
    n1, n2 = hal_files_result
    print("Overlaid HALFILE (" + str(n1) + ") / POSTGUI_HALFILE (" + str(n2)
          + " line(s)) -> generated .local.hal files")

    # Must run before _overlay_measurement_system below - see
    # _overlay_measurement_system's docstring: an angular [JOINT_n]
    # section's UNITS=DEGREE is set in the tracked REB.ini already and
    # is never touched by either overlay, so ordering only matters
    # insofar as _overlay_role_assignment must run before anything else
    # that assumes JOINTS/COORDINATES already reflect this launch.
    text, role_summary = _overlay_role_assignment(text, role_layout)
    if role_summary:
        print("Overlaid role assignment: " + role_summary)

    text, backlash_applied = _overlay_backlash(text, settings, role_layout)
    print("Overlaid BACKLASH: " + (", ".join(backlash_applied) or "none"))

    text, jog_result = _overlay_max_jog_speed(text, settings)
    if jog_result:
        value_text, n = jog_result
        print("Overlaid MAX_LINEAR_VELOCITY = " + value_text + " (" + str(n) + " line(s))")

    for settings_key, ini_key in VELOCITY_SETTINGS.items():
        text, result = _overlay_velocity_setting(text, settings, settings_key, ini_key)
        if result:
            value_text, n = result
            print("Overlaid " + ini_key + " = " + value_text + " (" + str(n) + " line(s))")

    text, units_result = _overlay_measurement_system(text, settings)
    if units_result:
        system, n1, n2 = units_result
        print("Overlaid " + system + " units (" + str(n1) + " LINEAR_UNITS, "
              + str(n2) + " UNITS line(s))")

    try:
        with open(LOCAL_INI_PATH, "w") as f:
            f.write(text)
    except OSError as e:
        print("Could not write " + LOCAL_INI_PATH + ": " + str(e))
        sys.exit(1)

    print("Wrote " + LOCAL_INI_PATH)


if __name__ == "__main__":
    main()
