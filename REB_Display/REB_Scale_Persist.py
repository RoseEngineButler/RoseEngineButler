#!/usr/bin/env python3
"""
REB_Scale_Persist.py

At LinuxCNC shutdown, reads the current stepgen position-scale value
for each Rose Engine Butler axis directly from HAL and writes it back
into REB_Settings_v1.ini, updating only that axis's "scale" value. The
rest of the file is left untouched.

Also persists each axis's/spindle loop's live P/I/D/FF0/FF1/FF2 pid.*
gains the same way, into that axis's "pid" entry (or "pid_pos"/
"pid_vel" for the two spindle loops) - see CURRENT_LETTER_INTERNAL_ID/
PID_SPINDLE_LOOPS below. These gains are set live from REB_Settings_v1.ini by
REB_main.py's _load_pid_settings() at Settings-tab load and by each PID
spin button's value-changed handler while running (see REB.hal for why
they're no longer set from REB.ini directly), so this is the only place
that carries a retuned gain forward into the next session - exactly
mirroring how scale already worked before PID gains were added to this
file.

Also persists each axis's/spindle's live joint.N.backlash HAL
parameter into that axis's "backlash" value the same way - see
JOINT_NUMBER below. Set live from REB_Settings_v1.ini by REB_main.py's
_load_backlash_settings() at Settings-tab load and by each Backlash
spin button's value-changed handler while running (see REB.ini for why
it's no longer relied on directly at LinuxCNC startup beyond an initial
default).

Invoked from REB_Shutdown.hal:
    loadusr -w python3 REB_Display/REB_Scale_Persist.py
"""

import os
import subprocess
import sys

import reb_settings_io

# Axis id (as used in REB_Settings_v1.ini and the Settings tab spin
# buttons) -> hm2_7i92.0 stepgen channel. Verified against the actual
# "net <axis>-enable => hm2_7i92.0.stepgen.NN.enable" lines in REB.hal
# - NOT the documentation table in REB.ini, which does not match.
AXIS_STEPGEN = {
    "X":   "04",
    "Z":   "01",
    "B":   "05",
    "U":   "02",
    "V":   "03",
    "W":   "00",
    "Sp0": "06",
    "Sp1": "07",
}

# Axis id -> LinuxCNC joint number, for the live joint.N.backlash HAL
# parameter. Mirrors JOINT_NUMBER in REB_main.py (see AXIS_STEPGEN above
# for why small constants are duplicated across these two scripts
# rather than imported) - NOT the same numbering as AXIS_STEPGEN's hm2
# stepgen channel map.
JOINT_NUMBER = {
    "X":   0,
    "Z":   1,
    "B":   2,
    "U":   3,
    "V":   4,
    "W":   5,
    "Sp1": 6,
    "Sp0": 7,
}

SETTINGS_PATH = reb_settings_io.SETTINGS_PATH

# Mirrors CHANNEL_DEFAULT_LETTER/AXIS_SELECTION_LETTERS/
# _read_persisted_channel_assignments in REB_main.py (see AXIS_STEPGEN
# above for why these are duplicated across scripts rather than
# imported). Channel id -> the axis letter REB.ini/REB.hal ship with by
# default - AXIS_STEPGEN/JOINT_NUMBER's *keys* above are these same
# default/internal ids and never change even if the operator reassigns
# a channel's axis letter via the Axis Selection tab.
CHANNEL_DEFAULT_LETTER = {
    "00": "W",
    "01": "Z",
    "02": "U",
    "03": "V",
    "04": "X",
    "05": "B",
}
DEFAULT_LETTER_CHANNEL = {v: k for k, v in CHANNEL_DEFAULT_LETTER.items()}
# Y removed - not used on this machine - see REB_main.py's AXIS_SELECTION_LETTERS.
AXIS_SELECTION_LETTERS = ("X", "Z", "U", "V", "W", "A", "B", "C")

def _read_persisted_channel_assignments():
    '''
    Mirrors REB_main.py's function of the same name - reads the
    persisted channel -> axis letter map, falling back to
    CHANNEL_DEFAULT_LETTER for anything missing/unrecognized/
    duplicated. See that function's docstring for the full reasoning.
    '''
    assignments = dict(CHANNEL_DEFAULT_LETTER)
    stored = reb_settings_io.load_settings().get("channel_assignments", {})
    for channel_id, letter in stored.items():
        if channel_id in assignments and letter in AXIS_SELECTION_LETTERS:
            assignments[channel_id] = letter

    if len(set(assignments.values())) != len(assignments):
        print("Duplicate letter(s) in persisted channel_assignments - using shipped defaults")
        return dict(CHANNEL_DEFAULT_LETTER)

    return assignments

# Internal id -> this session's actual current axis letter (lowercase).
# Read once at process startup (this script only ever runs once, at
# shutdown, so there's no "session" to worry about staying in sync with
# beyond this single run) - mirrors REB_main.py's CURRENT_LETTER; see
# that module's comment for why a channel's PID component name can't be
# a static "pid.<default letter>" once REB.local.hal is regenerated per
# the current assignment (REB_Setup/REB_Generate_Local_Ini.py).
_CHANNEL_ASSIGNMENTS = _read_persisted_channel_assignments()
CURRENT_LETTER = {
    internal_id: _CHANNEL_ASSIGNMENTS.get(channel_id, internal_id).lower()
    for internal_id, channel_id in DEFAULT_LETTER_CHANNEL.items()
}

# Reverse of CURRENT_LETTER - mirrors REB_main.py's constant of the same
# name (see AXIS_STEPGEN above for why these are duplicated across
# scripts). Currently-assigned axis letter (uppercase) -> internal id of
# whichever physical channel is driving it right now, if any. This is
# the sole source of truth main() uses to resolve every one of the 8
# AXIS_SELECTION_LETTERS to its live channel (see main()'s own docstring
# for the bug this fixed - PID_AXES/EXTRA_SETTINGS_LETTERS, formerly
# used for a "native vs extra letter" split, are no longer needed).
CURRENT_LETTER_INTERNAL_ID = {letter.upper(): internal_id for internal_id, letter in CURRENT_LETTER.items()}

PID_SPINDLE_LOOPS = {
    "Sp0": {"Pos": "pid.p0", "Vel": "pid.s0"},
    "Sp1": {"Pos": "pid.p1", "Vel": "pid.s1"},
}
PID_PARAM_PIN = {
    "P":   "Pgain",
    "I":   "Igain",
    "D":   "Dgain",
    "FF0": "FF0",
    "FF1": "FF1",
    "FF2": "FF2",
}
PID_PARAMS = ("P", "I", "D", "FF0", "FF1", "FF2")

def get_scale(stepgen_ch):
    hal_pin = "hm2_7i92.0.stepgen." + stepgen_ch + ".position-scale"
    result = subprocess.run(
        ["halcmd", "getp", hal_pin],
        check=True,
        capture_output=True,
        text=True
    )
    return float(result.stdout.strip())

def get_stepgen_max(stepgen_ch, param):
    hal_suffix = ".maxvel" if param == "max_vel" else ".maxaccel"
    hal_pin = "hm2_7i92.0.stepgen." + stepgen_ch + hal_suffix
    result = subprocess.run(
        ["halcmd", "getp", hal_pin],
        check=True,
        capture_output=True,
        text=True
    )
    return float(result.stdout.strip())

def get_pid_gain(hal_component, param):
    hal_pin = hal_component + "." + PID_PARAM_PIN[param]
    result = subprocess.run(
        ["halcmd", "getp", hal_pin],
        check=True,
        capture_output=True,
        text=True
    )
    return float(result.stdout.strip())

def get_backlash(joint_num):
    hal_pin = "joint." + str(joint_num) + ".backlash"
    result = subprocess.run(
        ["halcmd", "getp", hal_pin],
        check=True,
        capture_output=True,
        text=True
    )
    return float(result.stdout.strip())

def main():
    '''
    Fixed 3 September 2026: every read-back below is now keyed by
    LETTER (all 8 AXIS_SELECTION_LETTERS, resolved through
    CURRENT_LETTER_INTERNAL_ID), not by internal id with a "borrowed
    letter, skip" exception for EXTRA_SETTINGS_LETTERS only. The old
    split meant a channel wearing a borrowed *native* letter (e.g.
    channel 00 reassigned to letter B, native to channel 05) was
    invisible to BOTH the internal-id loop (skipped, since channel 00's
    own internal id "W" no longer matches its current letter) AND the
    EXTRA_SETTINGS_LETTERS loop (B isn't A or C) - so its live scale/
    max_vel/max_accel/PID/backlash were silently never persisted at
    all. Sp0/Sp1 (never reassignable) are still handled separately,
    unconditionally, by their own fixed internal id - see REB_main.py's
    _load_scale_settings for the load-side half of this same fix.
    '''
    settings = reb_settings_io.load_settings()
    axes = settings.setdefault("axes", {})

    for axis_id in ("Sp0", "Sp1"):
        try:
            value = get_scale(AXIS_STEPGEN[axis_id])
        except subprocess.CalledProcessError as e:
            print("Error reading scale for axis " + axis_id + ": " + e.stderr)
            continue
        except FileNotFoundError:
            print("halcmd not found - is the LinuxCNC environment sourced?")
            sys.exit(1)

        axes.setdefault(axis_id, {})["scale"] = value
        print("Saved " + axis_id + " scale = " + str(value))

    for letter in AXIS_SELECTION_LETTERS:
        internal_id = CURRENT_LETTER_INTERNAL_ID.get(letter)
        if internal_id is None:
            # Not currently assigned to any channel this session -
            # nothing live to read, leave its persisted value untouched.
            continue

        try:
            value = get_scale(AXIS_STEPGEN[internal_id])
        except subprocess.CalledProcessError as e:
            print("Error reading scale for axis " + letter + ": " + e.stderr)
            continue
        except FileNotFoundError:
            print("halcmd not found - is the LinuxCNC environment sourced?")
            sys.exit(1)

        axes.setdefault(letter, {})["scale"] = value
        print("Saved " + letter + " scale = " + str(value))

    for axis_id in ("Sp0", "Sp1"):
        for param in ("max_vel", "max_accel"):
            try:
                value = get_stepgen_max(AXIS_STEPGEN[axis_id], param)
            except subprocess.CalledProcessError as e:
                print("Error reading " + param + " for axis " + axis_id + ": " + e.stderr)
                continue
            except FileNotFoundError:
                print("halcmd not found - is the LinuxCNC environment sourced?")
                sys.exit(1)

            axes.setdefault(axis_id, {})[param] = value
            print("Saved " + axis_id + " " + param + " = " + str(value))

    for letter in AXIS_SELECTION_LETTERS:
        internal_id = CURRENT_LETTER_INTERNAL_ID.get(letter)
        if internal_id is None:
            continue

        for param in ("max_vel", "max_accel"):
            try:
                value = get_stepgen_max(AXIS_STEPGEN[internal_id], param)
            except subprocess.CalledProcessError as e:
                print("Error reading " + param + " for axis " + letter + ": " + e.stderr)
                continue
            except FileNotFoundError:
                print("halcmd not found - is the LinuxCNC environment sourced?")
                sys.exit(1)

            axes.setdefault(letter, {})[param] = value
            print("Saved " + letter + " " + param + " = " + str(value))

    for letter in AXIS_SELECTION_LETTERS:
        internal_id = CURRENT_LETTER_INTERNAL_ID.get(letter)
        if internal_id is None:
            continue

        values = {}
        try:
            for param in PID_PARAMS:
                values[param] = get_pid_gain("pid." + letter.lower(), param)
        except subprocess.CalledProcessError as e:
            print("Error reading PID gains for axis " + letter + ": " + e.stderr)
            continue
        except FileNotFoundError:
            print("halcmd not found - is the LinuxCNC environment sourced?")
            sys.exit(1)

        axes.setdefault(letter, {}).setdefault("pid", {}).update(values)
        print("Saved " + letter + " PID gains = " + str(values))

    for spindle_id, loops in PID_SPINDLE_LOOPS.items():
        for suffix, hal_component in loops.items():
            block_tag = "pid_pos" if suffix == "Pos" else "pid_vel"
            values = {}
            try:
                for param in PID_PARAMS:
                    values[param] = get_pid_gain(hal_component, param)
            except subprocess.CalledProcessError as e:
                print("Error reading " + suffix + " PID gains for " + spindle_id
                      + ": " + e.stderr)
                continue
            except FileNotFoundError:
                print("halcmd not found - is the LinuxCNC environment sourced?")
                sys.exit(1)

            axes.setdefault(spindle_id, {}).setdefault(block_tag, {}).update(values)
            print("Saved " + spindle_id + " " + suffix + " PID gains = " + str(values))

    for axis_id in ("Sp0", "Sp1"):
        try:
            value = get_backlash(JOINT_NUMBER[axis_id])
        except subprocess.CalledProcessError as e:
            print("Error reading backlash for axis " + axis_id + ": " + e.stderr)
            continue
        except FileNotFoundError:
            print("halcmd not found - is the LinuxCNC environment sourced?")
            sys.exit(1)

        axes.setdefault(axis_id, {})["backlash"] = value
        print("Saved " + axis_id + " backlash = " + str(value))

    for letter in AXIS_SELECTION_LETTERS:
        internal_id = CURRENT_LETTER_INTERNAL_ID.get(letter)
        if internal_id is None:
            continue

        try:
            value = get_backlash(JOINT_NUMBER[internal_id])
        except subprocess.CalledProcessError as e:
            print("Error reading backlash for axis " + letter + ": " + e.stderr)
            continue
        except FileNotFoundError:
            print("halcmd not found - is the LinuxCNC environment sourced?")
            sys.exit(1)

        axes.setdefault(letter, {})["backlash"] = value
        print("Saved " + letter + " backlash = " + str(value))

    try:
        reb_settings_io.save_settings(settings)
    except OSError as e:
        print("Could not write " + SETTINGS_PATH + ": " + str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
