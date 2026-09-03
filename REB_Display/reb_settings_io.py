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
#   reb_settings_io.py
#
# Purpose:
#   Shared JSON read/write/legacy-XML-migration for REBset_v1.ini.
#   Imported by REB_main.py, REB_Scale_Persist.py, and REB_Setup/
#   REB_Generate_Local_Ini.py - the one place those three otherwise-
#   independent processes intentionally share code, rather than each
#   duplicating their own copy the way small constants (AXIS_STEPGEN
#   etc.) are duplicated elsewhere in this codebase - getting settings
#   read/write logic wrong three times independently is a much bigger
#   risk than duplicating a 6-entry dict three times. See CLAUDE.md.
#
#   REBset_v1.ini used to be XML manipulated entirely by hand-rolled
#   regex substitution (no real parser anywhere in the read/write path
#   except Export/Import, which used ElementTree). That fragility
#   produced two real bugs: cosmetic indentation/duplicate-tag drift
#   from inconsistent skeleton-insertion code paths, and a genuine
#   data-loss bug where one axis's live HAL state got captured into a
#   different axis's persisted block. This module replaces all of that
#   with a plain json.load/json.dump round trip - a dict either has a
#   key or it doesn't, with no risk of malformed markup.
#
#   load_settings() transparently converts a still-XML REBset_v1.ini
#   (from before this migration) to the new JSON shape the first time
#   it's read, on any machine, without operator action.
#
# End User Customisation:
#   THE END USER OF THE ROSE ENGINE BUTLER SYSTEM SHOULD NOT MODIFY
#   THIS FILE.
#
#   Changes to this file are not supported by Colvin Tools nor
#   Brainwave Embedded.
#
# Version
#   1.0 - 22 August 2026, Claude
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

import json
import os
import re
from xml.sax.saxutils import unescape

SETTINGS_PATH = "/home/reuben/Documents/REBset_v1.ini"

FORMAT_VERSION = 1

# Mirrors REB_main.py's CHANNEL_DEFAULT_LETTER/REB_Scale_Persist.py's/
# REB_Generate_Local_Ini.py's own copies (see this module's own header
# for why the read/write logic is shared here but small constants like
# this one stay duplicated per the rest of the codebase's convention -
# this one only needs to match at the value level, not be imported).
CHANNEL_DEFAULT_LETTER = {
    "00": "W",
    "01": "Z",
    "02": "U",
    "03": "V",
    "04": "X",
    "05": "B",
}

# All ten <axis id="..."> rows the current schema has ever shipped -
# the six physical channels' own default letters, the two "extra"
# reassignable-only letters (A/C - see EXTRA_SETTINGS_LETTERS in
# REB_main.py), and the two spindles.
SPINDLE_IDS = ("Sp0", "Sp1")
AXIS_IDS = ("X", "Z", "B", "U", "V", "W", "A", "C") + SPINDLE_IDS

PID_PARAMS = ("P", "I", "D", "FF0", "FF1", "FF2")

# REB.ini's own documented generic starting PID gains (see
# generic_example.settings.ini, and REB.ini's [JOINT_n]/[SPINDLE_n]
# comments) - what a brand-new axis entry should start from.
_DEFAULT_PID = {"P": 5, "I": 1, "D": 1.2, "FF0": 0, "FF1": 1, "FF2": 0}
_DEFAULT_SPINDLE_PID_POS = {"P": 2, "I": 1, "D": 1.2, "FF0": 0, "FF1": 0, "FF2": 0}
_DEFAULT_SPINDLE_PID_VEL = {"P": 35.1, "I": 20, "D": 1.2, "FF0": 1, "FF1": 0, "FF2": 0}

# REB.ini's own shipped [TRAJ]/[DISPLAY] starting values - mirrors
# REB_main.py's VELOCITY_SETTINGS defaults exactly.
VELOCITY_DEFAULTS = {
    "default_linear_velocity": 0.250000,
    "min_linear_velocity": 0.016670,
    "max_angular_velocity": 1.000000,
    "default_angular_velocity": 12.000000,
    "min_angular_velocity": 1.666667,
}


# REB.ini's own shipped [JOINT_n]/[SPINDLE_n] STEPGEN_MAXVEL/
# STEPGEN_MAXACCEL starting values, by axis category - what a brand-new
# axis entry's "max_vel"/"max_accel" should start from. These are the
# stepgen hardware limits (live hm2_7i92.0.stepgen.NN.maxvel/maxaccel
# HAL params - see AXIS_STEPGEN in REB_main.py), not the [JOINT_n]/
# [AXIS_*] MAX_VELOCITY/MAX_ACCELERATION ini keys - those are a
# deliberately unreachable trajectory-planner ceiling that never binds
# (see CLAUDE.md), so this Settings-tab feature exposes the stepgen
# limit instead, matching REB_Generate_Local_Ini.py's docstring, which
# already calls STEPGEN_MAXVEL/STEPGEN_MAXACCEL "physical-channel
# tuning values the operator retunes via the Settings tab".
_DEFAULT_LINEAR_MAX_VEL = 0.4
_DEFAULT_LINEAR_MAX_ACCEL = 30.0
_DEFAULT_ROTARY_MAX_VEL = 100.0
_DEFAULT_ROTARY_MAX_ACCEL = 20.0
_DEFAULT_SPINDLE_MAX_VEL = 3.0
_DEFAULT_SPINDLE_MAX_ACCEL = 1.0


# Fallback only - see channel_types below. TYPE is now an independent,
# per-channel operator choice (Axis Selection tab), not derived from
# the letter; this rule is used solely to synthesize a channel_types
# default the first time a channel's type is read with nothing yet
# persisted, so a pre-existing REBset_v1.ini sees zero behavior change
# until the operator actually touches the new Type control. Mirrors
# REB_main.py's/REB_Generate_Local_Ini.py's own copies of this rule -
# see this module's header for why read/write logic is shared here but
# small constants like this one stay duplicated per the rest of the
# codebase's convention.
def _axis_type_for_letter(letter):
    return "ANGULAR" if letter in ("A", "B", "C") else "LINEAR"


def _default_channel_types(channel_assignments):
    '''
    Synthesizes a channel_types dict from channel_assignments alone,
    for a file that predates the channel_types field. Keyed off the
    *actual* assignments passed in (not the static CHANNEL_DEFAULT_
    LETTER), so a channel already reassigned away from its shipped
    letter still gets the type its current letter implied under the
    old letter-derived rule, matching pre-upgrade behavior exactly.
    '''
    return {
        channel_id: _axis_type_for_letter(
            channel_assignments.get(channel_id, CHANNEL_DEFAULT_LETTER[channel_id]))
        for channel_id in CHANNEL_DEFAULT_LETTER
    }


def _resolve_axis_type(axis_id, channel_assignments, channel_types):
    '''
    The type a Settings-tab letter slot (axis_id, e.g. "A") should use
    when seeding a never-before-seen axes[] entry: whichever channel
    currently wears that letter, per its own channel_types choice. Both
    "no channel currently wears this letter" (a parked slot, e.g. A/C
    when unplugged) and "channel wears it but has no explicit type yet"
    fall back to the old letter-derived rule.
    '''
    for channel_id, letter in channel_assignments.items():
        if letter == axis_id:
            return channel_types.get(channel_id, _axis_type_for_letter(axis_id))
    return _axis_type_for_letter(axis_id)


def _default_axis_entry(axis_id, channel_assignments, channel_types):
    if axis_id in SPINDLE_IDS:
        return {
            "scale": 1,
            "backlash": 0.0,
            "max_vel": _DEFAULT_SPINDLE_MAX_VEL,
            "max_accel": _DEFAULT_SPINDLE_MAX_ACCEL,
            "pid_pos": dict(_DEFAULT_SPINDLE_PID_POS),
            "pid_vel": dict(_DEFAULT_SPINDLE_PID_VEL),
        }
    # TYPE (and therefore default max_vel/max_accel/PID magnitude) is
    # now whatever the channel currently wearing this letter has chosen
    # via the Axis Selection tab's independent Type control - see
    # _resolve_axis_type - not a fixed "A/B/C always angular" rule.
    angular = _resolve_axis_type(axis_id, channel_assignments, channel_types) == "ANGULAR"
    return {
        "scale": 1,
        "backlash": 0.0,
        "max_vel": _DEFAULT_ROTARY_MAX_VEL if angular else _DEFAULT_LINEAR_MAX_VEL,
        "max_accel": _DEFAULT_ROTARY_MAX_ACCEL if angular else _DEFAULT_LINEAR_MAX_ACCEL,
        "usercomment": "",
        "pid": dict(_DEFAULT_PID),
    }


def default_settings():
    '''
    The shape a brand-new/missing REBset_v1.ini should start from -
    REB.ini's own documented starting values for every key, matching
    what every _load_*() fallback in REB_main.py already assumed when
    a given tag was absent from the file. Key order here is the order
    the file is written in (json.dump preserves dict insertion order).
    '''
    channel_assignments = dict(CHANNEL_DEFAULT_LETTER)
    channel_types = _default_channel_types(channel_assignments)
    settings = {
        "format_version": FORMAT_VERSION,
        "channel_assignments": channel_assignments,
        "channel_types": channel_types,
        "device_names": [],
        "measurement_system": "Imperial",
        "max_jog_speed": 1.0,
    }
    settings.update(VELOCITY_DEFAULTS)
    settings["axes"] = {
        axis_id: _default_axis_entry(axis_id, channel_assignments, channel_types)
        for axis_id in AXIS_IDS
    }
    return settings


def _merge_defaults(loaded):
    '''
    Defensive against a hand-edited or partially-corrupted file (its
    own header says it shouldn't be touched directly, but nothing stops
    it) - fills in any top-level or per-axis key missing from `loaded`
    with default_settings()'s value, rather than letting a KeyError
    surface deep in caller code later. Same "absent -> shipped default"
    convention the old per-tag regex fallbacks already used.

    channel_assignments and channel_types are resolved explicitly,
    before axes, because a never-before-seen axes[] entry's default
    max_vel/max_accel/PID depends on both (see _default_axis_entry) -
    a file with real channel_assignments but no channel_types yet (pre-
    upgrade) gets one synthesized from its *loaded* assignments, not
    the shipped-default ones, so upgrading never changes behavior for
    a channel already reassigned away from its default letter.
    '''
    merged = default_settings()

    if "channel_assignments" in loaded and isinstance(loaded["channel_assignments"], dict):
        merged["channel_assignments"].update(loaded["channel_assignments"])

    if "channel_types" in loaded and isinstance(loaded["channel_types"], dict):
        merged["channel_types"].update(loaded["channel_types"])
    else:
        merged["channel_types"] = _default_channel_types(merged["channel_assignments"])

    merged["axes"] = {
        axis_id: _default_axis_entry(axis_id, merged["channel_assignments"], merged["channel_types"])
        for axis_id in AXIS_IDS
    }

    for key, value in loaded.items():
        if key in ("channel_assignments", "channel_types"):
            continue
        if key == "axes" and isinstance(value, dict):
            for axis_id, axis_value in value.items():
                if axis_id in merged["axes"] and isinstance(axis_value, dict):
                    merged["axes"][axis_id].update(axis_value)
                else:
                    merged["axes"][axis_id] = axis_value
        else:
            merged[key] = value
    return merged


def save_settings(data, path=SETTINGS_PATH):
    '''
    Writes data as JSON to path, atomically: write to a temp file in the
    same directory, then os.replace() over the real path. os.replace is
    a single filesystem rename, so a reader can never observe a
    half-written file - cheap insurance against a Pi losing power
    mid-write, which the old direct open(path, "w") had no protection
    against at all.
    '''
    tmp_path = path + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(tmp_path, path)


def _xml_tag(text, tag, default=None, cast=str):
    match = re.search(r'<' + tag + r'>(.*?)</' + tag + r'>', text, re.DOTALL)
    if not match:
        return default
    try:
        return cast(match.group(1).strip())
    except ValueError:
        return default


def _parse_legacy_xml(xml_text):
    '''
    Converts REBset_v1.ini's old hand-rolled-regex XML shape into the
    current dict shape. This is read-only, legacy-support code - it
    exists so _migrate_legacy_xml can run exactly once per machine (the
    very next save produces plain JSON) and is intentionally the only
    place in the whole codebase that still knows this old format.
    '''
    settings = default_settings()

    settings["measurement_system"] = _xml_tag(
        xml_text, "measurement_system", settings["measurement_system"])
    settings["max_jog_speed"] = _xml_tag(
        xml_text, "max_jog_speed", settings["max_jog_speed"], float)
    for key in VELOCITY_DEFAULTS:
        settings[key] = _xml_tag(xml_text, key, settings[key], float)

    assignments_block = _xml_tag(xml_text, "channel_assignments", "")
    if assignments_block:
        assignments = dict(CHANNEL_DEFAULT_LETTER)
        for channel_id, letter in re.findall(
                r'<channel id="(\d\d)">([A-Z])</channel>', assignments_block):
            if channel_id in assignments:
                assignments[channel_id] = letter
        if len(set(assignments.values())) == len(assignments):
            settings["channel_assignments"] = assignments
        else:
            print("Duplicate letter(s) in legacy channel_assignments - using shipped defaults")

    # The legacy XML format predates channel_types entirely - synthesize
    # it from whatever channel_assignments was just resolved above (not
    # the shipped default), and rebuild the axes[] skeleton so a never-
    # before-seen letter's default max_vel/max_accel/PID reflect it,
    # before the per-axis XML overlay loop below fills in real values.
    settings["channel_types"] = _default_channel_types(settings["channel_assignments"])
    settings["axes"] = {
        axis_id: _default_axis_entry(axis_id, settings["channel_assignments"], settings["channel_types"])
        for axis_id in AXIS_IDS
    }

    names_block = _xml_tag(xml_text, "device_names", "")
    if names_block:
        settings["device_names"] = [
            unescape(name) for name in
            re.findall(r'<name>(.*?)</name>', names_block, re.DOTALL)
        ]

    for axis_id in AXIS_IDS:
        axis_match = re.search(
            r'<axis\s+id="' + re.escape(axis_id) + r'">(.*?)</axis>',
            xml_text, re.DOTALL
        )
        if not axis_match:
            continue
        axis_block = axis_match.group(1)
        axis_entry = settings["axes"][axis_id]

        scale = _xml_tag(axis_block, "scale", None, float)
        if scale is not None:
            axis_entry["scale"] = scale

        backlash = _xml_tag(axis_block, "backlash", None, float)
        if backlash is not None:
            axis_entry["backlash"] = backlash

        if axis_id in SPINDLE_IDS:
            for block_tag in ("pid_pos", "pid_vel"):
                block_match = re.search(
                    r'<' + block_tag + r'>(.*?)</' + block_tag + r'>',
                    axis_block, re.DOTALL
                )
                if not block_match:
                    continue
                for param in PID_PARAMS:
                    value = _xml_tag(block_match.group(1), param, None, float)
                    if value is not None:
                        axis_entry[block_tag][param] = value
        else:
            comment_match = re.search(r'<usercomment>(.*?)</usercomment>', axis_block, re.DOTALL)
            if comment_match:
                axis_entry["usercomment"] = unescape(comment_match.group(1))

            pid_match = re.search(r'<pid>(.*?)</pid>', axis_block, re.DOTALL)
            if pid_match:
                for param in PID_PARAMS:
                    value = _xml_tag(pid_match.group(1), param, None, float)
                    if value is not None:
                        axis_entry["pid"][param] = value

    return settings


def _migrate_legacy_xml(xml_text, path):
    '''
    One-time conversion, triggered automatically the first time
    load_settings() finds XML content instead of JSON - on this
    machine or any other still running the pre-migration format. Backs
    up the untouched original first (only if no backup exists yet - a
    second machine/process racing this same conversion at the same
    startup must never overwrite an already-made backup with a second,
    possibly-different read of the same file), then writes the
    converted JSON only after confirming it round-trips through
    json.load successfully - REBset_v1.ini has already been lost to a
    bad write twice this week, so this path deliberately never lets a
    failed conversion touch the real file.
    '''
    backup_path = path + ".xml-backup"
    if not os.path.exists(backup_path):
        try:
            with open(backup_path, "w") as f:
                f.write(xml_text)
            print("Backed up legacy XML settings to " + backup_path)
        except OSError as e:
            print("Could not write legacy XML backup " + backup_path + ": " + str(e))

    settings = _parse_legacy_xml(xml_text)

    tmp_path = path + ".tmp"
    try:
        with open(tmp_path, "w") as f:
            json.dump(settings, f, indent=2)
            f.write("\n")
        with open(tmp_path, "r") as f:
            round_tripped = json.load(f)
        if "axes" not in round_tripped or "channel_assignments" not in round_tripped:
            raise ValueError("converted JSON is missing expected top-level keys")
        os.replace(tmp_path, path)
        print("Migrated " + path + " from legacy XML to JSON (format_version "
              + str(FORMAT_VERSION) + ") - original backed up to " + backup_path)
    except (OSError, ValueError) as e:
        print("Legacy XML->JSON migration of " + path + " failed, leaving the "
              "original file untouched: " + str(e))
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    return settings


def load_settings(path=SETTINGS_PATH):
    '''
    Reads path and returns its settings dict - default_settings() if
    the file doesn't exist yet, a legacy-XML one-time conversion (see
    _migrate_legacy_xml) if it's still in the pre-migration format, or
    the parsed JSON (merged over default_settings() to fill in any
    missing key - see _merge_defaults) otherwise.
    '''
    try:
        with open(path, "r") as f:
            raw = f.read()
    except OSError:
        return default_settings()

    stripped = raw.lstrip()
    if stripped.startswith("<?xml") or stripped.startswith("<settings"):
        return _migrate_legacy_xml(raw, path)

    try:
        loaded = json.loads(raw)
    except ValueError as e:
        print("Could not parse " + path + " as JSON: " + str(e))
        return default_settings()

    if not isinstance(loaded, dict):
        print(path + " did not contain a JSON object - using shipped defaults")
        return default_settings()

    return _merge_defaults(loaded)
