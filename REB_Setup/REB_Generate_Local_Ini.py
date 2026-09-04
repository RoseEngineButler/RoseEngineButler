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
#   System choices are currently persisted in
#   /home/reuben/Documents/REBset_v1.ini.
#
#   REB.ini's [TRAJ]/[DISPLAY] MAX_LINEAR_VELOCITY (and its four
#   VELOCITY_SETTINGS siblings) and [TRAJ]LINEAR_UNITS / [JOINT_n]UNITS
#   are read once by LinuxCNC at process startup, before any HAL
#   component or the GladeVCP panel's own Python (REB_main.py) ever
#   runs - so they can't be corrected from within a running session the
#   way stepgen scale/PID/backlash are (those have real HAL pins).
#   REB_main.py used to patch them directly into the tracked REB.ini, but
#   that meant a `git pull` of someone else's REB.ini change could
#   silently overwrite this machine's own jog-speed/units choice.
#
#   Run this instead, before every LinuxCNC launch (see REB_Launch.sh):
#   it always starts from the current tracked REB.ini and overlays only
#   the settings below, so upstream REB.ini edits still flow through
#   untouched and the local choice never gets committed or clobbered.
#
#   A setting is only overlaid if a persisted value actually exists in
#   REB_Settings_v1.ini - if a given Settings tab control has never been
#   touched on this machine, REB.ini's own shipped value for it is
#   carried through exactly as committed (see VELOCITY_SETTINGS/
#   _load_velocity_settings in REB_main.py, which apply that same
#   REB.ini-shipped value as their in-memory fallback for exactly this
#   reason - the two stay in sync until an operator actually changes
#   one on the Settings tab).
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


# Channel id ("00".."05", the hm2_7i92.0.stepgen.NN suffix) -> the axis
# letter REB.ini/REB.hal ship with by default. Duplicated from
# REB_Display/REB_main.py's CHANNEL_DEFAULT_LETTER (and again in
# REB_Display/REB_Scale_Persist.py) - see AXIS_STEPGEN there for why
# small maps like this are duplicated across scripts rather than
# imported (three separate processes/scripts, none of which import from
# each other).
CHANNEL_DEFAULT_LETTER = {
    "00": "W",
    "01": "Z",
    "02": "U",
    "03": "V",
    "04": "X",
    "05": "B",
}

# Channel id -> LinuxCNC joint number. Fixed regardless of axis
# assignment - only which [AXIS_<letter>] section is paired with a given
# [JOINT_n] (by COORDINATES order) ever changes, never the joint numbers
# themselves. See CLAUDE.md's axis/joint/plug map and REB_Display/
# REB_main.py's JOINT_NUMBER (keyed by letter there; keyed by channel
# here since that's what this script starts from).
CHANNEL_JOINT_NUMBER = {
    "00": 5,
    "01": 1,
    "02": 3,
    "03": 4,
    "04": 0,
    "05": 2,
}

# Y removed - not used on this machine - see REB_Display/REB_main.py's
# AXIS_SELECTION_LETTERS.
AXIS_SELECTION_LETTERS = ("X", "Z", "U", "V", "W", "A", "B", "C")


def _axis_type_for_letter(letter):
    return "ANGULAR" if letter in ("A", "B", "C") else "LINEAR"


# Channel id -> the Type _axis_type_for_letter(CHANNEL_DEFAULT_LETTER[id])
# gives - this codebase's shipped-default Type per channel. TYPE is now
# an independent, per-channel operator choice via the Axis Selection
# tab's Type combo (REBset_v1.ini's channel_types, see
# _read_channel_types below) - a channel can be any letter with either
# type, freely combined - so this is used only to detect "nothing
# changed from shipped defaults" in _overlay_axis_assignment.
DEFAULT_CHANNEL_TYPES = {
    channel_id: _axis_type_for_letter(letter)
    for channel_id, letter in CHANNEL_DEFAULT_LETTER.items()
}


def _read_channel_types(settings, assignments):
    '''
    Reads REBset_v1.ini's channel_types dict (written by the Axis
    Selection tab - REB_Display/REB_main.py's _save_channel_types),
    falling back to whatever each channel's currently-assigned letter
    (per `assignments`) would imply under the old letter-derived rule
    for any channel that's missing or unrecognized - same "absent ->
    shipped default" convention as _read_channel_assignments. Unlike
    letters, types are never duplicate-checked - two channels sharing a
    Type is perfectly valid.
    '''
    types = {
        channel_id: _axis_type_for_letter(assignments.get(channel_id, CHANNEL_DEFAULT_LETTER[channel_id]))
        for channel_id in CHANNEL_DEFAULT_LETTER
    }

    for channel_id, axis_type in settings.get("channel_types", {}).items():
        if channel_id in types and axis_type in ("LINEAR", "ANGULAR"):
            types[channel_id] = axis_type

    return types


def _read_channel_assignments(settings):
    '''
    Reads REBset_v1.ini's channel_assignments dict (written by the Axis
    Selection tab - REB_Display/REB_main.py's _save_channel_assignments),
    falling back to CHANNEL_DEFAULT_LETTER for any channel that's
    missing, unrecognized, or - defensively, since REBset_v1.ini's own
    header says it should not be hand-edited - duplicated onto more than
    one channel.
    '''
    assignments = dict(CHANNEL_DEFAULT_LETTER)

    for channel_id, letter in settings.get("channel_assignments", {}).items():
        if channel_id in assignments and letter in AXIS_SELECTION_LETTERS:
            assignments[channel_id] = letter

    if len(set(assignments.values())) != len(assignments):
        print("Duplicate letter(s) in persisted channel_assignments - using shipped defaults")
        return dict(CHANNEL_DEFAULT_LETTER)

    return assignments


def _set_key_in_section(text, section_name, key, value):
    '''
    Replaces `key = ...` with `key = value`, scoped to the named INI
    section only (from its `[section_name]` header up to the next line
    starting with `[`, or end of file) - so this can't touch a
    same-named key in a different section (TYPE, for instance, appears
    in every [AXIS_*] and [JOINT_n] section).
    '''
    section_pattern = re.compile(
        r'(\[' + re.escape(section_name) + r'\].*?)(?=\n\[|\Z)',
        re.DOTALL,
    )
    match = section_pattern.search(text)
    if not match:
        print("Could not find [" + section_name + "] in REB.ini")
        return text

    section_text = match.group(1)
    new_section_text, n = re.subn(
        r'(?m)^(' + re.escape(key) + r'\s*= )\S+',
        lambda m: m.group(1) + value,
        section_text,
        count=1,
    )
    if n == 0:
        print("Could not find " + key + " in [" + section_name + "]")
        return text

    return text[:match.start(1)] + new_section_text + text[match.end(1):]


def _overlay_axis_assignment(text, assignments, types):
    '''
    Rewrites REB.ini's [AXIS_<letter>] section headers, TYPE/UNITS keys,
    and [KINS]/[TRAJ]/[DISPLAY] coordinate-order keys to match the
    persisted channel -> axis letter assignment (REBset_v1.ini's
    <channel_assignments>, written by the Axis Selection tab - see
    _read_channel_assignments) and the independently persisted channel
    -> Type assignment (<channel_types> - see _read_channel_types). A
    channel's TYPE no longer follows from its letter - it's whatever
    the operator chose on the Type combo - so letter and type are each
    checked and rewritten independently below. Must run BEFORE
    _overlay_measurement_system below: a channel whose type just
    changed to/from ANGULAR needs its UNITS key set to DEGREE/a linear
    placeholder here FIRST, so that overlay's INCH/MM-only regex (which
    deliberately never touches DEGREE) can then correct the placeholder
    to the machine's actual current measurement system on the same
    pass.

    Leaves MIN_LIMIT/MAX_LIMIT/MAX_VELOCITY/MAX_ACCELERATION/
    STEPGEN_MAXVEL/STEPGEN_MAXACCEL/PID gains/backlash untouched - those
    are physical-channel tuning values the operator retunes via the
    Settings tab after physically reconfiguring hardware; this only
    fixes labeling/typing/kinematics, not motion tuning.

    Safe against channels swapping letters with each other in the sense
    that every [AXIS_*] section is located by that channel's *default*
    letter (unique per channel, and every such lookup below is scoped
    to that one already-isolated section span - never a fresh whole-
    text search by the *new* letter). That distinction matters: a
    whole-text-by-new-letter search is NOT safe mid-loop, since renaming
    one channel's section to a letter that's also some OTHER channel's
    still-unrenamed default letter briefly leaves two sections sharing
    that name - the earlier bug here (found live 4 September 2026,
    REB.ini's own [AXIS_B] left at TYPE=LINEAR after channel 00 was
    reassigned to letter B) resolved "AXIS_" + new_letter against the
    whole text *after* the rename and silently grabbed the wrong
    (unrelated, still-default) section instead of the one just renamed.
    Renaming and setting TYPE together on one isolated span, before
    splicing back, avoids that ambiguity entirely - so which channel is
    processed first still never matters, just not for the reason the
    old version of this docstring gave.
    '''
    if assignments == CHANNEL_DEFAULT_LETTER and types == DEFAULT_CHANNEL_TYPES:
        return text, None

    changes = []
    for channel_id, default_letter in CHANNEL_DEFAULT_LETTER.items():
        new_letter = assignments[channel_id]
        new_type = types[channel_id]
        default_type = DEFAULT_CHANNEL_TYPES[channel_id]
        if new_letter == default_letter and new_type == default_type:
            continue

        joint_num = CHANNEL_JOINT_NUMBER[channel_id]

        # Locate this channel's [AXIS_<default_letter>] section by its
        # DEFAULT letter (always unique/stable - see docstring), then
        # rename the header and set TYPE together within that one
        # isolated span before splicing it back into text. Doing these
        # as two separate whole-text operations (rename, then a fresh
        # _set_key_in_section("AXIS_" + new_letter, ...) lookup) is what
        # broke - see docstring.
        axis_section_pattern = re.compile(
            r'(\[AXIS_' + re.escape(default_letter) + r'\].*?)(?=\n\[|\Z)',
            re.DOTALL,
        )
        axis_match = axis_section_pattern.search(text)
        if not axis_match:
            print("Could not find [AXIS_" + default_letter + "] in REB.ini")
            continue
        axis_section_text = axis_match.group(1)

        if new_letter != default_letter:
            axis_section_text = re.sub(
                r'(?m)^\[AXIS_' + re.escape(default_letter) + r'\]',
                '[AXIS_' + new_letter + ']',
                axis_section_text,
                count=1,
            )

        axis_section_text, n = re.subn(
            r'(?m)^(TYPE\s*= )\S+',
            lambda m: m.group(1) + new_type,
            axis_section_text,
            count=1,
        )
        if n == 0:
            print("Could not find TYPE in [AXIS_" + default_letter + "]")

        text = text[:axis_match.start(1)] + axis_section_text + text[axis_match.end(1):]

        text = _set_key_in_section(text, "JOINT_" + str(joint_num), "TYPE", new_type)

        # UNITS lives only in [JOINT_n]. DEGREE if now angular; otherwise
        # a linear placeholder ("INCH") that _overlay_measurement_system
        # (run right after this function, in main()) will correct to the
        # machine's actual current measurement system - see this
        # function's own docstring.
        units = "DEGREE" if new_type == "ANGULAR" else "INCH"
        text = _set_key_in_section(text, "JOINT_" + str(joint_num), "UNITS", units)

        change = channel_id + ": "
        if new_letter != default_letter:
            change += default_letter + " -> " + new_letter
        else:
            change += default_letter + " (unchanged)"
        if new_type != default_type:
            change += ", " + default_type + " -> " + new_type
        changes.append(change)

    # Rebuild the [KINS]/[TRAJ]/[DISPLAY] coordinate-order keys: the Nth
    # letter is whichever channel is joint N (fixed - CHANNEL_JOINT_NUMBER),
    # regardless of what letter that channel is assigned today.
    letters_by_joint = [None] * len(CHANNEL_JOINT_NUMBER)
    for channel_id, joint_num in CHANNEL_JOINT_NUMBER.items():
        letters_by_joint[joint_num] = assignments[channel_id]
    coordinates = "".join(letters_by_joint)

    text, n1 = re.subn(
        r'(?m)^(KINEMATICS\s*= trivkins coordinates=)\S+',
        lambda m: m.group(1) + coordinates,
        text,
        count=1,
    )
    text, n2 = re.subn(
        r'(?m)^(COORDINATES\s*= )\S+',
        lambda m: m.group(1) + coordinates,
        text,
        count=1,
    )
    text, n3 = re.subn(
        r'(?m)^(GEOMETRY\s*= )\S+',
        lambda m: m.group(1) + coordinates,
        text,
        count=1,
    )

    return text, (changes, coordinates, n1, n2, n3)


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
    # case-insensitively by LinuxCNC. JOINT_2 (B, angular) uses
    # UNITS = DEGREE and is never matched by the INCH/MM pattern below, so
    # it's left untouched.
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
# REB.hal / REB_PostGUI_v1.hal regeneration.
#
# Unlike REB.ini's overlay above (small, independent key=value patches),
# a channel's axis letter is woven through many HAL net names and
# component-instance names across both files, so this works by direct
# text substitution of every affected token, per channel, rather than
# scoped key patches. See generate_local_hal_files' docstring for the
# overall approach and CLAUDE.md for why REB.hal itself is never edited
# (only read as a template) - Rich asked for REB.hal's net names to
# always literally match the current assignment, so unlike REB.hal's
# axis letters being purely cosmetic net-name choices with no functional
# meaning to REB.ini/kinematics, this repo's *tracked* REB.hal/
# REB_PostGUI_v1.hal remain the "no reassignment made yet" case.

HAL_PATH = os.path.join(REPO_DIR, "REB.hal")
LOCAL_HAL_PATH = os.path.join(REPO_DIR, "REB.local.hal")
POSTGUI_HAL_PATH = os.path.join(REPO_DIR, "REB_Display", "REB_PostGUI_v1.hal")
LOCAL_POSTGUI_HAL_PATH = os.path.join(REPO_DIR, "REB_Display", "REB_PostGUI_v1.local.hal")

# Every fixed suffix, across both REB.hal and REB_PostGUI_v1.hal, that a
# HAL net name or component-instance name embedding an axis letter as
# its LEADING character can end in - the letter starts the token, one of
# these strings ends it (verified against every actual net/addf/loadrt
# line in both files - not the header comment tables, which are
# decorative and not regenerated, matching the "trust the net lines, not
# the ASCII-art tables" precedent CLAUDE.md already documents for these
# files).
_AXIS_TOKEN_SUFFIXES = (
    "-enable", "-home-sw", "-index-enable", "-is-homed", "-neg-limit",
    "-output", "-pos-cmd", "-pos-fb", "-pos-limit", "-vel-cmd",
    "-ena-flip", "-ena-not", "-ena-and", "-estop-and", "-ena-btn",
    "-ena-panel-inv", "-ena-panel-allow", "-ena-settings-allow",
    "-ena-panel",
)


def _bounded(pattern_body, suffix_boundary=True):
    '''
    Wraps a regex fragment with boundary guards so it only matches a
    genuine standalone HAL token, never a substring embedded in a longer
    identifier. This matters concretely: without the prefix guard,
    searching for the literal text "x-enable" would wrongly match inside
    "...index-enable" too (the word "index" ends in "x", immediately
    followed by "-enable" - a real collision, hit on every REB.hal
    regeneration where channel 4 is still assigned its default letter X,
    since every axis's own "<letter>-index-enable" net exists in the
    file). suffix_boundary=False is for the one token shape where the
    letter sits in the middle of a longer word (jog-<letter>-analog/neg/
    pos) rather than at the end.
    '''
    prefix = r'(?<![\w.-])'
    suffix = r'(?![\w-])' if suffix_boundary else ''
    return prefix + pattern_body + suffix


def _rename_hal_axis_tokens(text, old_letter, new_letter):
    '''
    Renames every HAL net/component-instance token in REB.hal or
    REB_PostGUI_v1.hal that embeds an axis letter, from old_letter to
    new_letter. Deliberately does NOT touch:
    - hm2_7i92.0.outm.00.out-NN / stepgen.NN.* (channel-number based,
      never letter-based)
    - [JOINT_n] ini key references inside setp lines (joint-number
      based)
    - gladevcp.*/REBCnfg.* pin names in REB_PostGUI_v1.hal (tied to the
      fixed internal id forever - see CHANNEL_DEFAULT_LETTER in
      REB_Display/REB_main.py, and the comment above the call site in
      generate_local_hal_files)
    - the `loadrt pid names=...` / `loadrt flipflop|not|and2 names=...`
      lines - these ARE renamed, by the same substitution as everything
      else below (the boundary-safe regex correctly matches a
      comma-separated "pid.x," entry too, since "," isn't excluded by
      the suffix guard), not by any special-cased whole-line rebuild
    - decorative ASCII-art banners and the per-axis documentation
      comment table (cosmetic only, left showing the shipped default
      letter - not read by LinuxCNC, and regenerating them reliably via
      regex isn't worth the risk for a cosmetic-only outcome)

    old_letter/new_letter are single uppercase letters; every token
    shape below uses the lowercase HAL-identifier convention.
    '''
    old = old_letter.lower()
    new = new_letter.lower()

    text = re.sub(_bounded(r'pid\.' + re.escape(old)), 'pid.' + new, text)
    text = re.sub(_bounded(r'halui\.axis\.' + re.escape(old)), 'halui.axis.' + new, text)
    text = re.sub(_bounded(r'axis-select-' + re.escape(old)), 'axis-select-' + new, text)
    text = re.sub(_bounded(r'jog-' + re.escape(old) + '-', suffix_boundary=False), 'jog-' + new + '-', text)

    for suffix in _AXIS_TOKEN_SUFFIXES:
        text = re.sub(_bounded(re.escape(old) + re.escape(suffix)), new + suffix, text)

    return text


def _verify_hal_generation(hal_text, postgui_text, assignments):
    '''
    Verifies the regenerated files by tracing the one definitive,
    channel-NUMBER-anchored net line for each of the 6 channels (the
    stepgen channel number in these lines is never renamed, so it's a
    fixed anchor letters can be checked against).

    Deliberately NOT "no leftover old-letter token anywhere in the
    file" - that check is WRONG whenever two channels swap letters with
    each other: a later channel's legitimate newly-written letter can
    equal an earlier channel's default letter (e.g. channel 5 newly
    assigned X right after channel 4 stops being X), which a leftover-
    token search can't tell apart from an actual missed rename. Anchoring
    on the stepgen channel number instead sidesteps that ambiguity
    entirely - it doesn't matter what order channels were processed in,
    only whether the right letter ended up on the right channel number.

    Returns a list of problem descriptions (empty list = all good).
    '''
    problems = []

    loadrt_pid_match = re.search(r'(?m)^loadrt pid names=.*$', hal_text)
    loadrt_pid_line = loadrt_pid_match.group(0) if loadrt_pid_match else ""

    for channel_id, letter in assignments.items():
        letter = letter.lower()
        default_letter = CHANNEL_DEFAULT_LETTER[channel_id].lower()

        if not re.search(
            r'net ' + re.escape(letter) + r'-enable\s*=>\s*hm2_7i92\.0\.stepgen\.'
            + re.escape(channel_id) + r'\.enable',
            hal_text,
        ):
            problems.append(
                "REB.local.hal: no 'net " + letter + "-enable => hm2_7i92.0."
                "stepgen." + channel_id + ".enable' line found (channel "
                + channel_id + " should be assigned " + letter.upper() + ")"
            )

        # Channel 00 (W) is open-loop - no PID enable net or loadrt pid
        # entry for it (see REB.hal's W block) - see CLAUDE.md/the Axis
        # Selection tab's own tooltip for this hardware asymmetry.
        if channel_id != "00":
            if not re.search(
                r'net ' + re.escape(letter) + r'-enable\s*=>\s*pid\.' + re.escape(letter) + r'\.enable',
                hal_text,
            ):
                problems.append(
                    "REB.local.hal: no 'net " + letter + "-enable => pid."
                    + letter + ".enable' line found"
                )
            if not re.search(r'(?<![\w.-])pid\.' + re.escape(letter) + r'(?![\w-])', loadrt_pid_line):
                problems.append(
                    "REB.local.hal: pid." + letter + " missing from the "
                    "loadrt pid names= line"
                )

        if not re.search(
            r'net ' + re.escape(letter) + r'-enable\s*<=\s*' + re.escape(letter) + r'-estop-and\.out',
            postgui_text,
        ):
            problems.append(
                "REB_PostGUI_v1.local.hal: no 'net " + letter + "-enable <= "
                + letter + "-estop-and.out' line found"
            )

        # The gladevcp status-light pin is tied to the fixed internal id
        # forever (REB_Panel_v1.ui's widget id never changes) - it must
        # stay at default_letter even though the net feeding it is now
        # named after the current letter. Getting this backwards (or
        # renaming it) would silently break the main panel's ENA light
        # for this channel.
        if not re.search(
            r'net ' + re.escape(letter) + r'-enable\s*=>\s*gladevcp\.'
            + re.escape(default_letter.upper()) + r'_ENA-light',
            postgui_text,
        ):
            problems.append(
                "REB_PostGUI_v1.local.hal: no 'net " + letter + "-enable => "
                "gladevcp." + default_letter.upper() + "_ENA-light' line found "
                "(the gladevcp pin must stay named after the internal id, "
                + default_letter.upper() + ", not the assigned letter)"
            )

    return problems


def generate_local_hal_files(assignments):
    '''
    Regenerates REB.local.hal and REB_Display/REB_PostGUI_v1.local.hal
    from the tracked REB.hal/REB_PostGUI_v1.hal, renaming every HAL net/
    component-instance token that embeds an axis letter to match the
    current channel assignment. Always writes both files, even with no
    reassignment made (an unchanged copy) - see _overlay_hal_files,
    which always points REB.local.ini's HALFILE/POSTGUI_HALFILE at these
    generated files regardless, so behavior doesn't depend on whether
    the operator has ever touched the Axis Selection tab.

    Renames through a per-channel placeholder rather than default_letter
    -> new_letter directly, so channels swapping letters with each other
    (or any larger reassignment cycle) can't have one channel's freshly-
    written new tokens wrongly re-matched and re-renamed by a later
    channel's own rename pass - see the inline comment where the
    placeholder is built for the full reasoning.

    Returns True on success (both files written). Returns False, writing
    NEITHER file, if _verify_hal_generation finds a problem - refuses to
    leave a broken, half-generated .local.hal for LinuxCNC to load in
    that case; the caller should treat False as fatal.
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

    changed_channels = [
        (channel_id, default_letter, assignments[channel_id])
        for channel_id, default_letter in CHANNEL_DEFAULT_LETTER.items()
        if assignments[channel_id] != default_letter
    ]

    # Two-phase rename through a per-channel placeholder rather than
    # renaming default_letter -> new_letter directly in one pass: with
    # two (or more) channels swapping letters with each other, a direct
    # rename is NOT safe the way _overlay_axis_assignment's section-
    # header rename is - here, letter tokens are free-floating text
    # scattered across many lines, not anchored to one unique bracketed
    # header each. If channel 4 (X) is renamed to B first, its brand new
    # "b-enable" text is then indistinguishable from channel 5's own
    # original "b-enable" text - channel 5's subsequent "rename every
    # default-B token to X" pass would wrongly re-rename channel 4's
    # freshly-written tokens too, corrupting them. Routing every channel
    # through a placeholder that can never collide with a real single-
    # letter axis token (or with another channel's placeholder) makes
    # this safe for any permutation, not just simple two-way swaps.
    for channel_id, default_letter, new_letter in changed_channels:
        placeholder = "zzch" + channel_id
        hal_text = _rename_hal_axis_tokens(hal_text, default_letter, placeholder)
        postgui_text = _rename_hal_axis_tokens(postgui_text, default_letter, placeholder)
    for channel_id, default_letter, new_letter in changed_channels:
        placeholder = "zzch" + channel_id
        hal_text = _rename_hal_axis_tokens(hal_text, placeholder, new_letter)
        postgui_text = _rename_hal_axis_tokens(postgui_text, placeholder, new_letter)

    problems = _verify_hal_generation(hal_text, postgui_text, assignments)
    if problems:
        print("REFUSING to write REB.local.hal/REB_PostGUI_v1.local.hal - "
              "generation verification failed:")
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

    if changed_channels:
        print("Regenerated REB.local.hal / REB_PostGUI_v1.local.hal for: "
              + ", ".join(c + " (" + d + " -> " + n + ")" for c, d, n in changed_channels))
    print("Wrote " + LOCAL_HAL_PATH + " and " + LOCAL_POSTGUI_HAL_PATH)
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
    types = _read_channel_types(settings, assignments)

    # Regenerate REB.local.hal/REB_PostGUI_v1.local.hal FIRST and abort
    # immediately if it fails (see generate_local_hal_files) - if the
    # realtime wiring can't be regenerated safely, don't write a
    # REB.local.ini that would point at it (or at a stale previous
    # .local.hal left over from a different assignment) anyway.
    if not generate_local_hal_files(assignments):
        sys.exit(1)

    text, hal_files_result = _overlay_hal_files(text)
    n1, n2 = hal_files_result
    print("Overlaid HALFILE (" + str(n1) + ") / POSTGUI_HALFILE (" + str(n2)
          + " line(s)) -> generated .local.hal files")

    # Must run before _overlay_measurement_system below - see
    # _overlay_axis_assignment's docstring for why.
    text, axis_result = _overlay_axis_assignment(text, assignments, types)
    if axis_result:
        changes, coordinates, n1, n2, n3 = axis_result
        print("Overlaid axis assignment: " + ", ".join(changes))
        print("Overlaid coordinates = " + coordinates + " (" + str(n1) + " KINEMATICS, "
              + str(n2) + " COORDINATES, " + str(n3) + " GEOMETRY line(s))")

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
