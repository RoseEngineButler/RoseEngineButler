#!/usr/bin/env python3
"""
REB_Settings_Restore.py

At LinuxCNC startup, reads REBset_v1.ini and pushes each Rose Engine
Butler axis's persisted stepgen position-scale, maxvel/maxaccel,
P/I/D/FF0/FF1/FF2 pid.* gains, and joint.N.backlash onto the live HAL
parameters those values actually live on. This is the load-side
counterpart to REB_Display/REB_Scale_Persist.py (which does the same
job in reverse, at shutdown) - together they're what makes a value
retuned in REB_Settings survive to the next session.

Why this needs to exist as its own step: none of these are ordinary
HAL pins wired to REB.ini through the usual [JOINT_n]/[AXIS_*]
INI-substitution mechanism - they're HAL PARAMETERS on the hm2_7i92
stepgen/pid/motion components, which reset to that component's own
hard default (position-scale/maxvel/maxaccel/PID gains all come up as
0 or 1, not this machine's real values) every time hm2_7i92/pid/motion
are freshly loaded. Before 4 September 2026, the embedded AXIS Settings
tab's own startup (REB_main.py's _load_scale_settings/_load_pid_
settings/_load_backlash_settings/_load_max_vel_accel_settings) is what
pushed these values onto HAL every time LinuxCNC started - that ran
automatically because the tab was embedded in AXIS itself. Once the
Settings tab was replaced by the standalone REB_Settings program (which
must run BEFORE LinuxCNC, and is blocked from running while LinuxCNC is
running - see REB_Settings.py's _linuxcnc_is_running), nothing was left
to do this restore at a normal LinuxCNC startup at all - confirmed live
4 September 2026 (position-scale silently sitting at hm2's own default
of 1 after a restart, discovered only because a commanded move produced
far less physical travel than expected). This script is the fix.

Invoked from REB.hal, after hm2_7i92/pid/motion are all loaded:
    loadusr -w python3 REB_Display/REB_Settings_Restore.py
"""

import subprocess
import sys

import reb_settings_io

# Axis id (as used in REBset_v1.ini and the REB_Settings spin buttons)
# -> hm2_7i92.0 stepgen channel. Verified against the actual "net
# <axis>-enable => hm2_7i92.0.stepgen.NN.enable" lines in REB.hal - NOT
# the documentation table in REB.ini, which does not match. Mirrors
# REB_Scale_Persist.py's/REB_Settings.py's own copies of this same map
# (see that file's own comment for why small constants like this are
# duplicated across scripts rather than imported).
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
# parameter. NOT the same numbering as AXIS_STEPGEN's hm2 stepgen
# channel map above.
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

CHANNEL_DEFAULT_LETTER = {
    "00": "W",
    "01": "Z",
    "02": "U",
    "03": "V",
    "04": "X",
    "05": "B",
}
DEFAULT_LETTER_CHANNEL = {v: k for k, v in CHANNEL_DEFAULT_LETTER.items()}
# Y removed - not used on this machine - see REB_Settings.py's AXIS_SELECTION_LETTERS.
AXIS_SELECTION_LETTERS = ("X", "Z", "U", "V", "W", "A", "B", "C")


def _read_persisted_channel_assignments():
    '''
    Mirrors REB_Settings.py's/REB_Scale_Persist.py's function of the
    same name - reads the persisted channel -> axis letter map, falling
    back to CHANNEL_DEFAULT_LETTER for anything missing/unrecognized/
    duplicated.
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
# startup, so there's no "session" to worry about staying in sync with
# beyond this single run) - mirrors REB_Scale_Persist.py's CURRENT_LETTER.
_CHANNEL_ASSIGNMENTS = _read_persisted_channel_assignments()
CURRENT_LETTER = {
    internal_id: _CHANNEL_ASSIGNMENTS.get(channel_id, internal_id).lower()
    for internal_id, channel_id in DEFAULT_LETTER_CHANNEL.items()
}
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


def _setp(hal_pin, value):
    subprocess.run(
        ["halcmd", "setp", hal_pin, str(value)],
        check=True,
        capture_output=True,
        text=True
    )


def set_scale(stepgen_ch, value):
    _setp("hm2_7i92.0.stepgen." + stepgen_ch + ".position-scale", value)


def set_stepgen_max(stepgen_ch, param, value):
    hal_suffix = ".maxvel" if param == "max_vel" else ".maxaccel"
    _setp("hm2_7i92.0.stepgen." + stepgen_ch + hal_suffix, value)


def set_pid_gain(hal_component, param, value):
    _setp(hal_component + "." + PID_PARAM_PIN[param], value)


def set_backlash(joint_num, value):
    _setp("joint." + str(joint_num) + ".backlash", value)


def main():
    '''
    Restores exactly what REB_Scale_Persist.py's main() persists, in the
    same order, keyed the same way: Sp0/Sp1 unconditionally by their own
    fixed internal id, then all 8 AXIS_SELECTION_LETTERS resolved
    through CURRENT_LETTER_INTERNAL_ID (skipping any letter not
    currently assigned to a channel - nothing live to push it onto).
    '''
    settings = reb_settings_io.load_settings()
    axes = settings.get("axes", {})

    def restore_scale(axis_id, stepgen_ch):
        axis_entry = axes.get(axis_id)
        if axis_entry is None or "scale" not in axis_entry:
            print("No stored scale found for axis " + axis_id)
            return
        value = float(axis_entry["scale"])
        try:
            set_scale(stepgen_ch, value)
            print("Restored " + axis_id + " scale = " + str(value))
        except subprocess.CalledProcessError as e:
            print("Error restoring scale for axis " + axis_id + ": " + e.stderr)
        except FileNotFoundError:
            print("halcmd not found - is the LinuxCNC environment sourced?")
            sys.exit(1)

    def restore_stepgen_max(axis_id, stepgen_ch):
        axis_entry = axes.get(axis_id)
        if axis_entry is None:
            return
        for param in ("max_vel", "max_accel"):
            if param not in axis_entry:
                print("No stored " + param + " found for axis " + axis_id)
                continue
            value = float(axis_entry[param])
            try:
                set_stepgen_max(stepgen_ch, param, value)
                print("Restored " + axis_id + " " + param + " = " + str(value))
            except subprocess.CalledProcessError as e:
                print("Error restoring " + param + " for axis " + axis_id + ": " + e.stderr)
            except FileNotFoundError:
                print("halcmd not found - is the LinuxCNC environment sourced?")
                sys.exit(1)

    def restore_backlash(axis_id, joint_num):
        axis_entry = axes.get(axis_id)
        if axis_entry is None or "backlash" not in axis_entry:
            print("No stored backlash found for axis " + axis_id)
            return
        value = float(axis_entry["backlash"])
        try:
            set_backlash(joint_num, value)
            print("Restored " + axis_id + " backlash = " + str(value))
        except subprocess.CalledProcessError as e:
            print("Error restoring backlash for axis " + axis_id + ": " + e.stderr)
        except FileNotFoundError:
            print("halcmd not found - is the LinuxCNC environment sourced?")
            sys.exit(1)

    def restore_pid(axis_id, block_tag, hal_component):
        axis_entry = axes.get(axis_id)
        if axis_entry is None:
            return
        pid_block = axis_entry.get(block_tag)
        if pid_block is None:
            print("No \"" + block_tag + "\" entry found for axis " + axis_id)
            return
        for param in PID_PARAMS:
            if param not in pid_block:
                print("No stored " + param + " found for " + axis_id + " " + block_tag)
                continue
            value = float(pid_block[param])
            try:
                set_pid_gain(hal_component, param, value)
            except subprocess.CalledProcessError as e:
                print("Error restoring " + param + " for " + axis_id + " " + block_tag + ": " + e.stderr)
            except FileNotFoundError:
                print("halcmd not found - is the LinuxCNC environment sourced?")
                sys.exit(1)
        print("Restored " + axis_id + " " + block_tag + " PID gains = " + str(pid_block))

    for axis_id in ("Sp0", "Sp1"):
        restore_scale(axis_id, AXIS_STEPGEN[axis_id])
        restore_stepgen_max(axis_id, AXIS_STEPGEN[axis_id])
        restore_backlash(axis_id, JOINT_NUMBER[axis_id])

    for letter in AXIS_SELECTION_LETTERS:
        internal_id = CURRENT_LETTER_INTERNAL_ID.get(letter)
        if internal_id is None:
            # Not currently assigned to any channel this session -
            # nothing live to push it onto.
            continue
        restore_scale(letter, AXIS_STEPGEN[internal_id])
        restore_stepgen_max(letter, AXIS_STEPGEN[internal_id])
        restore_backlash(letter, JOINT_NUMBER[internal_id])
        restore_pid(letter, "pid", "pid." + letter.lower())

    for spindle_id, loops in PID_SPINDLE_LOOPS.items():
        for suffix, hal_component in loops.items():
            block_tag = "pid_pos" if suffix == "Pos" else "pid_vel"
            restore_pid(spindle_id, block_tag, hal_component)


if __name__ == "__main__":
    main()
