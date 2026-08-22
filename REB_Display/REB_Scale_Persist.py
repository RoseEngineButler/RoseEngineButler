#!/usr/bin/env python3
"""
REB_Scale_Persist.py

At LinuxCNC shutdown, reads the current stepgen position-scale value
for each Rose Engine Butler axis directly from HAL and writes it back
into REB_Settings_v1.ini, updating only that axis's "scale" value. The
rest of the file is left untouched.

Also persists each axis's/spindle loop's live P/I/D/FF0/FF1/FF2 pid.*
gains the same way, into that axis's "pid" entry (or "pid_pos"/
"pid_vel" for the two spindle loops) - see PID_AXES/PID_SPINDLE_LOOPS
below. These gains are set live from REB_Settings_v1.ini by
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

# Internal id -> HAL `pid` component instance driving that axis's PID
# loop right now (see CURRENT_LETTER above for why this can't be a
# static dict).
PID_AXES = {internal_id: "pid." + letter for internal_id, letter in CURRENT_LETTER.items()}

# Reverse of CURRENT_LETTER - mirrors REB_main.py's constant of the same
# name (see AXIS_STEPGEN above for why these are duplicated across
# scripts). Currently-assigned axis letter (uppercase) -> internal id of
# whichever physical channel is driving it right now, if any.
CURRENT_LETTER_INTERNAL_ID = {letter.upper(): internal_id for internal_id, letter in CURRENT_LETTER.items()}

# Settings-tab Axis Scaling rows with no fixed physical channel of their
# own - mirrors REB_main.py's constant of the same name. Persisted as
# "A"/"C" entries in the axes dict, independent of the six physical
# channels' own entries - see main() below.
EXTRA_SETTINGS_LETTERS = ("A", "C")
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
    settings = reb_settings_io.load_settings()
    axes = settings.setdefault("axes", {})

    for axis_id, stepgen_ch in AXIS_STEPGEN.items():
        if axis_id in CURRENT_LETTER and CURRENT_LETTER[axis_id] != axis_id.lower():
            # This channel is currently wearing a borrowed letter
            # (EXTRA_SETTINGS_LETTERS below) - the live pin reflects that
            # letter's tuning, not axis_id's own. Reading it back here
            # would stomp axis_id's own persisted scale with the
            # borrowed letter's value; leave it untouched instead - see
            # REB_main.py's _load_scale_settings for the load-side half
            # of this same fix. axis_id not in CURRENT_LETTER means
            # Sp0/Sp1 (never reassignable), which always own their own
            # live pin unconditionally.
            continue

        try:
            value = get_scale(stepgen_ch)
        except subprocess.CalledProcessError as e:
            print("Error reading scale for axis " + axis_id + ": " + e.stderr)
            continue
        except FileNotFoundError:
            print("halcmd not found - is the LinuxCNC environment sourced?")
            sys.exit(1)

        axes.setdefault(axis_id, {})["scale"] = value
        print("Saved " + axis_id + " scale = " + str(value))

    for letter in EXTRA_SETTINGS_LETTERS:
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

    for axis_id, hal_component in PID_AXES.items():
        if CURRENT_LETTER[axis_id] != axis_id.lower():
            # Same reasoning as the identical check in the scale loop
            # above - hal_component here is currently driven by a
            # borrowed letter's tuning, not axis_id's own.
            continue

        values = {}
        try:
            for param in PID_PARAMS:
                values[param] = get_pid_gain(hal_component, param)
        except subprocess.CalledProcessError as e:
            print("Error reading PID gains for axis " + axis_id + ": " + e.stderr)
            continue
        except FileNotFoundError:
            print("halcmd not found - is the LinuxCNC environment sourced?")
            sys.exit(1)

        axes.setdefault(axis_id, {}).setdefault("pid", {}).update(values)
        print("Saved " + axis_id + " PID gains = " + str(values))

    for letter in EXTRA_SETTINGS_LETTERS:
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

    for axis_id, joint_num in JOINT_NUMBER.items():
        if axis_id in CURRENT_LETTER and CURRENT_LETTER[axis_id] != axis_id.lower():
            # Same reasoning as the identical check in the scale loop
            # above (axis_id not in CURRENT_LETTER means Sp0/Sp1, which
            # always own their own live pin) - joint_num's live backlash
            # currently reflects a borrowed letter's tuning, not
            # axis_id's own.
            continue

        try:
            value = get_backlash(joint_num)
        except subprocess.CalledProcessError as e:
            print("Error reading backlash for axis " + axis_id + ": " + e.stderr)
            continue
        except FileNotFoundError:
            print("halcmd not found - is the LinuxCNC environment sourced?")
            sys.exit(1)

        axes.setdefault(axis_id, {})["backlash"] = value
        print("Saved " + axis_id + " backlash = " + str(value))

    for letter in EXTRA_SETTINGS_LETTERS:
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
