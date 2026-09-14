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
#   System / channel-role assignment choices are currently persisted in
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
    spindles = len(role_layout.active_spindles)

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


def generate_local_hal_files(role_layout):
    '''
    Regenerates REB.local.hal from the tracked REB.hal: for each of the
    8 currently-active roles, retargets its own isolated
    ROLE_BLOCK-delimited region's channel number (and joint number for
    an axis letter, or spindle index for a spindle) and keeps it; the 2
    currently-inactive roles' entire block is omitted. Copies
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
    if role_layout.inactive_roles:
        print("Not currently assigned to any channel: " + ", ".join(role_layout.inactive_roles))
    print("Wrote " + LOCAL_HAL_PATH + " and " + LOCAL_POSTGUI_HAL_PATH + " (unchanged copy)")
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
    if not generate_local_hal_files(role_layout):
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
