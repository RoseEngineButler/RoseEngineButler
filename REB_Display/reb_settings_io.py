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

# Mirrors REB_main.py's/REB_Scale_Persist.py's/REB_Settings.py's/
# REB_Settings_Restore.py's/REB_Generate_Local_Ini.py's own copies (see
# this module's own header for why the read/write logic is shared here
# but small constants like this one stay duplicated per the rest of the
# codebase's convention - this one only needs to match at the value
# level, not be imported).
#
# Widened 13 September 2026 (Rich): channel_assignments used to only
# ever hold one of 8 axis letters, for channels "00".."05" - channels
# "06"/"07" were permanently, uneditably Sp0/Sp1. Now any of the 10
# possible roles (8 axis letters + Sp0 + Sp1) can be assigned to any of
# the 8 physical channels, so this dict grew two more channel keys and
# its value space grew to include "Sp0"/"Sp1". This is the shipped
# default/fallback shape (the original pre-generalization mapping,
# restoring A/C as the shipped-default "not currently wired" pair) -
# an old 6-key REBset_v1.ini merges cleanly against this in
# _merge_defaults below with zero extra migration code: the loaded
# file's 6 keys overwrite 00-05, and 06/07 simply keep this dict's
# Sp0/Sp1 default, exactly matching what those channels always were
# before this change.
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

# All ten <axis id="..."> rows the current schema has ever shipped -
# the eight assignable axis letters and the two spindles. Every one of
# these ten ids always has its own settings entry (scale/backlash/PID/
# etc.) regardless of whether it's currently assigned to a channel -
# channel_assignments (which of the 10 sits on which of the 8 physical
# channels right now) is an entirely separate concern from this list.
SPINDLE_IDS = ("Sp0", "Sp1")
AXIS_IDS = ("X", "Z", "B", "U", "V", "W", "A", "C") + SPINDLE_IDS

# The 10 valid values a channel_assignments entry can hold - the 8 axis
# letters (in AXIS_IDS' order, minus the 2 spindles) plus the 2
# spindles. Mirrors AXIS_SELECTION_LETTERS + SPINDLE_IDS in
# REB_main.py/REB_Settings.py.
CHANNEL_ROLES = tuple(a for a in AXIS_IDS if a not in SPINDLE_IDS) + SPINDLE_IDS

PID_PARAMS = ("P", "I", "D", "FF0", "FF1", "FF2")

# REB.ini's own documented generic starting PID gains (see REB.ini's
# [JOINT_n]/[SPINDLE_n] comments) - what a brand-new axis entry should
# start from.
_DEFAULT_PID = {"P": 5, "I": 1, "D": 1.2, "FF0": 0, "FF1": 1, "FF2": 0}
_DEFAULT_SPINDLE_PID_POS = {"P": 2, "I": 1, "D": 1.2, "FF0": 0, "FF1": 0, "FF2": 0}
# (Spindles' old velocity-loop "pid_vel" gains were dropped 08 October
# 2026 - that loop's output never reached the stepgen. A machine's file
# may still carry the key; nothing reads it.)

# How the advanced limits are worked out from an axis's Max Speed / Max
# Acceleration (the trajectory planner's limits, [AXIS_*]/[JOINT_n]
# MAX_VELOCITY/MAX_ACCELERATION), and the least margin each must keep
# above them. REB Settings shows these as each row's note and warns
# when a value drops below its minimum; REB_Update_Settings.py uses them
# to fill in a machine's first Max Speed / Max Acceleration.
STEPGEN_VEL_FACTOR = 1.25      # stepgen max_vel = 1.25 x max_speed
STEPGEN_VEL_MIN = 1.0          # ... and never below max_speed
STEPGEN_ACCEL_FACTOR = 2.0     # stepgen max_accel = 2 x max_acceleration
STEPGEN_ACCEL_MIN = 1.5        # ... and never below 1.5 x max_acceleration
PID_OUTPUT_FACTOR = 1.1        # pid max output = 1.1 x max_speed
PID_OUTPUT_MIN = 1.0           # ... and never below max_speed

# Step pulse time (ns) every channel uses - REB.ini's STEPLEN +
# STEPSPACE (2500 + 2500 for the DM542T). 1e9 / this is the most steps
# per second the 7i92 can send, so a Max Speed above
# that / |scale| can't actually be reached.
STEP_TIME_NS = 5000

# Fastest any linear axis may be set to move: 1 inch/sec (Rich, 08
# October 2026), in machine units - 25.4 mm/sec when the Measurement
# System is Metric.
LINEAR_MAX_SPEED_CAP_INCH = 1.0


def linear_speed_cap(measurement_system):
    return LINEAR_MAX_SPEED_CAP_INCH * (25.4 if measurement_system == "Metric" else 1.0)


def step_rate_speed_ceiling(scale):
    '''Fastest speed (units/sec) the step timing allows at this scale,
    or None for a zero scale.'''
    try:
        scale = abs(float(scale))
    except (TypeError, ValueError):
        return None
    if scale == 0:
        return None
    return 1e9 / STEP_TIME_NS / scale

# REB.ini's own shipped [TRAJ]/[DISPLAY] starting values - mirrors
# REB_main.py's VELOCITY_SETTINGS defaults exactly.
VELOCITY_DEFAULTS = {
    "default_linear_velocity": 0.250000,
    "min_linear_velocity": 0.016670,
    "max_angular_velocity": 10.000000,
    "default_angular_velocity": 5.833333,
    "min_angular_velocity": 1.666667,
}


# A spindle's stepgen limits (its Max Vel / Max Accel in REB Settings -
# spindles have no planner limits of their own). An axis's stepgen
# max_vel/max_accel are worked out from its Max Speed / Max
# Acceleration instead - see default_limits.
_DEFAULT_SPINDLE_MAX_VEL = 3.0
_DEFAULT_SPINDLE_MAX_ACCEL = 1.0

# Planner limits ("max_speed"/"max_acceleration") per letter - REB.ini's
# shipped [AXIS_*] values, except linear Max Speed, which REB.ini sets
# far above what the stepgen allows (10 in/s) and is the stepgen's own
# default here instead. C is set up for rosette programs of many tiny
# moves (see REB.ini's [AXIS_C]).
_DEFAULT_MAX_SPEED = {"C": 30.0}
_DEFAULT_MAX_ACCELERATION = {"C": 320.0}
_DEFAULT_LINEAR_MAX_SPEED = 0.3
_DEFAULT_LINEAR_MAX_ACCELERATION = 20.0
_DEFAULT_ROTARY_MAX_SPEED = 10.0
_DEFAULT_ROTARY_MAX_ACCELERATION = 10.0
# Spindle indexing (M19) position loop's output cap - REB.ini's
# [SPINDLE_n]MAX_OUTPUT_POS.
_DEFAULT_INDEX_MAX_OUTPUT = 1.0


def default_limits(axis_id):
    '''
    An axis's calculated starting limits: {"max_speed", "max_acceleration",
    "max_vel", "max_accel", "pid_max_output"} - or, for a spindle,
    {"max_vel", "max_accel", "index_max_output"}. Also what REB Settings'
    Restore Defaults puts back.
    '''
    if axis_id in SPINDLE_IDS:
        return {"max_vel": _DEFAULT_SPINDLE_MAX_VEL,
                "max_accel": _DEFAULT_SPINDLE_MAX_ACCEL,
                "index_max_output": _DEFAULT_INDEX_MAX_OUTPUT}
    angular = _axis_type_for_letter(axis_id) == "ANGULAR"
    speed = _DEFAULT_MAX_SPEED.get(
        axis_id, _DEFAULT_ROTARY_MAX_SPEED if angular else _DEFAULT_LINEAR_MAX_SPEED)
    accel = _DEFAULT_MAX_ACCELERATION.get(
        axis_id, _DEFAULT_ROTARY_MAX_ACCELERATION if angular else _DEFAULT_LINEAR_MAX_ACCELERATION)
    return {"max_speed": speed,
            "max_acceleration": accel,
            "max_vel": round(speed * STEPGEN_VEL_FACTOR, 6),
            "max_accel": round(accel * STEPGEN_ACCEL_FACTOR, 6),
            "pid_max_output": round(speed * PID_OUTPUT_FACTOR, 6)}


def default_pid(axis_id):
    '''An axis's standard PID gains (a spindle's indexing loop's for Sp0/Sp1).'''
    return dict(_DEFAULT_SPINDLE_PID_POS if axis_id in SPINDLE_IDS else _DEFAULT_PID)


LIMIT_KEYS = ("max_speed", "max_acceleration", "pid_max_output", "index_max_output")


def fill_missing_limits(axis_id, entry, planner=None, measurement_system="Imperial"):
    '''
    Fills in a machine's missing Max Speed / Max Acceleration / PID Max
    Output (axes) or Indexing Max Output (spindles) without changing how
    fast the axis can actually move. Returns a list of what was set.

    Before 08 October 2026 these lived in REB.ini, where linear Max
    Speed was 10 in/s but the stepgen's own max_vel (often 0.167 in/s)
    was what really limited the axis - so Max Speed starts at the lower
    of the two.

    planner=None (just reading a file): Max Acceleration is also held to
    what the saved stepgen max_accel allows, so nothing is asked of the
    stepgen that it can't do. planner=(MAX_VELOCITY, MAX_ACCELERATION)
    from REB.ini (REB_Update_Settings.py): Max Acceleration is REB.ini's,
    and the stepgen max_vel/max_accel are raised if they're now too low
    - the one place existing values change.
    '''
    changes = []
    if axis_id in SPINDLE_IDS:
        if "index_max_output" not in entry:
            # REB.ini's MAX_OUTPUT_POS, but no more than the spindle's own
            # Max Vel - the stepgen held it to that anyway.
            try:
                stepgen_vel = float(entry.get("max_vel", _DEFAULT_SPINDLE_MAX_VEL))
            except (TypeError, ValueError):
                stepgen_vel = _DEFAULT_SPINDLE_MAX_VEL
            entry["index_max_output"] = round(min(_DEFAULT_INDEX_MAX_OUTPUT, stepgen_vel), 6)
            changes.append("index_max_output = %g" % entry["index_max_output"])
        return changes

    defaults = default_limits(axis_id)
    speed_default, accel_default = planner if planner else (defaults["max_speed"], defaults["max_acceleration"])
    try:
        stepgen_vel = float(entry.get("max_vel", defaults["max_vel"]))
        stepgen_accel = float(entry.get("max_accel", defaults["max_accel"]))
    except (TypeError, ValueError):
        stepgen_vel, stepgen_accel = defaults["max_vel"], defaults["max_accel"]

    if "max_speed" not in entry:
        speed = min(speed_default, stepgen_vel)
        if _axis_type_for_letter(axis_id) == "LINEAR":
            speed = min(speed, linear_speed_cap(measurement_system))
        entry["max_speed"] = round(speed, 6)
        changes.append("max_speed = %g" % entry["max_speed"])
        if planner:
            wanted = entry["max_speed"] * STEPGEN_VEL_FACTOR
            ceiling = step_rate_speed_ceiling(entry.get("scale"))
            if ceiling is not None:
                wanted = min(wanted, ceiling)
            if wanted > stepgen_vel:
                entry["max_vel"] = round(wanted, 6)
                changes.append("max_vel %g -> %g" % (stepgen_vel, entry["max_vel"]))

    if "max_acceleration" not in entry:
        if planner:
            entry["max_acceleration"] = accel_default
            if stepgen_accel < accel_default * STEPGEN_ACCEL_MIN:
                entry["max_accel"] = round(accel_default * STEPGEN_ACCEL_FACTOR, 6)
                changes.append("max_accel %g -> %g" % (stepgen_accel, entry["max_accel"]))
        else:
            entry["max_acceleration"] = round(min(accel_default, stepgen_accel / STEPGEN_ACCEL_MIN), 6)
        changes.append("max_acceleration = %g" % entry["max_acceleration"])

    if "pid_max_output" not in entry:
        entry["pid_max_output"] = round(entry["max_speed"] * PID_OUTPUT_FACTOR, 6)
        changes.append("pid_max_output = %g" % entry["pid_max_output"])
    return changes


# The axis letter -> Type rule. TYPE was briefly an independent,
# per-channel operator choice via the Axis Selection tab's Type combo
# (REBset_v1.ini's "channel_types" field) between 3 and 4 September
# 2026; that feature was retired the same week it shipped (nothing in
# the current UI can ever set an independent type again), so this is
# now simply the one and only source of truth: A/B/C are angular,
# everything else is linear. Mirrors REB_main.py's/
# REB_Generate_Local_Ini.py's own copies of this rule - see this
# module's header for why read/write logic is shared here but small
# constants like this one stay duplicated per the rest of the
# codebase's convention.
def _axis_type_for_letter(letter):
    return "ANGULAR" if letter in ("A", "B", "C") else "LINEAR"


def _default_axis_entry(axis_id):
    if axis_id in SPINDLE_IDS:
        entry = {"scale": 1, "backlash": 0.0}
        entry.update(default_limits(axis_id))
        entry["pid_pos"] = default_pid(axis_id)
        return entry
    entry = {"scale": 1, "backlash": 0.0}
    entry.update(default_limits(axis_id))
    entry["usercomment"] = ""
    entry["pid"] = default_pid(axis_id)
    return entry


def default_settings():
    '''
    The shape a brand-new/missing REBset_v1.ini should start from -
    REB.ini's own documented starting values for every key, matching
    what every _load_*() fallback in REB_main.py already assumed when
    a given tag was absent from the file. Key order here is the order
    the file is written in (json.dump preserves dict insertion order).
    '''
    channel_assignments = dict(CHANNEL_DEFAULT_ROLE)
    settings = {
        "format_version": FORMAT_VERSION,
        "channel_assignments": channel_assignments,
        "device_names": [],
        "measurement_system": "Imperial",
        "max_jog_speed": 1.0,
    }
    settings.update(VELOCITY_DEFAULTS)
    settings["axes"] = {
        axis_id: _default_axis_entry(axis_id)
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

    channel_assignments is resolved explicitly, before axes, because a
    never-before-seen axes[] entry needs the real letter to derive its
    default TYPE (see _default_axis_entry).

    A loaded file's stale "channel_types" key (written only briefly, 3-4
    September 2026, by a feature since retired) is intentionally left
    alone here rather than merged in or deleted - it's just inert dead
    data now, nothing reads it.
    '''
    merged = default_settings()

    if "channel_assignments" in loaded and isinstance(loaded["channel_assignments"], dict):
        merged["channel_assignments"].update(loaded["channel_assignments"])

    merged["axes"] = {
        axis_id: _default_axis_entry(axis_id)
        for axis_id in AXIS_IDS
    }

    for key, value in loaded.items():
        if key == "channel_assignments":
            continue
        if key == "axes" and isinstance(value, dict):
            for axis_id, axis_value in value.items():
                if axis_id in merged["axes"] and isinstance(axis_value, dict):
                    entry = merged["axes"][axis_id]
                    # A saved axis without the 08 October 2026 limits
                    # gets them worked out from its own stepgen values,
                    # not the shipped defaults - see fill_missing_limits.
                    for limit_key in LIMIT_KEYS:
                        if limit_key not in axis_value:
                            entry.pop(limit_key, None)
                    entry.update(axis_value)
                    fill_missing_limits(axis_id, entry, measurement_system=loaded.get(
                        "measurement_system", "Imperial"))
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
        # No legacy XML file ever had a spindle in channel_assignments
        # (that's the whole point of the 13 September 2026 widening -
        # see CHANNEL_DEFAULT_ROLE above) or a channel id beyond "05",
        # but the value pattern is widened to \w+ (was [A-Z], one char
        # only) and validated against CHANNEL_ROLES rather than assumed
        # single-letter, so this stays correct if it's ever fed a
        # channel_assignments block written by a newer version of this
        # same schema.
        assignments = dict(CHANNEL_DEFAULT_ROLE)
        for channel_id, role in re.findall(
                r'<channel id="(\d\d)">(\w+)</channel>', assignments_block):
            if channel_id in assignments and role in CHANNEL_ROLES:
                assignments[channel_id] = role
        if len(set(assignments.values())) == len(assignments):
            settings["channel_assignments"] = assignments
        else:
            print("Duplicate letter(s) in legacy channel_assignments - using shipped defaults")

    # Rebuild the axes[] skeleton (default max_vel/max_accel/PID, which
    # depend on TYPE - see _default_axis_entry) before the per-axis XML
    # overlay loop below fills in real values.
    settings["axes"] = {
        axis_id: _default_axis_entry(axis_id)
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
