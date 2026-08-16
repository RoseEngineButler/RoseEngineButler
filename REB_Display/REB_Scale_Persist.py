#!/usr/bin/env python3
"""
REB_Scale_Persist.py

At LinuxCNC shutdown, reads the current stepgen position-scale value
for each Rose Engine Butler axis directly from HAL and writes it back
into REB_Settings_v1.ini, updating only the <scale> value inside each
<axis id="..."> block. The rest of the file - including its header
comment - is left untouched.

Also persists each axis's/spindle loop's live P/I/D/FF0/FF1/FF2 pid.*
gains the same way, into that axis's <pid> block (or <pid_pos>/<pid_vel>
for the two spindle loops) - see PID_AXES/PID_SPINDLE_LOOPS below. These
gains are set live from REB_Settings_v1.ini by REB_main.py's
_load_pid_settings() at Settings-tab load and by each PID spin button's
value-changed handler while running (see REB.hal for why they're no
longer set from REB.ini directly), so this is the only place that
carries a retuned gain forward into the next session - exactly mirroring
how scale already worked before PID gains were added to this file.

Also persists each axis's/spindle's live joint.N.backlash HAL
parameter into that axis's <backlash> value the same way - see
JOINT_NUMBER below. Set live from REB_Settings_v1.ini by REB_main.py's
_load_backlash_settings() at Settings-tab load and by each Backlash
spin button's value-changed handler while running (see REB.ini for why
it's no longer relied on directly at LinuxCNC startup beyond an initial
default).

Invoked from REB_Shutdown.hal:
    loadusr -w python3 REB_Display/REB_Scale_Persist.py
"""

import os
import re
import subprocess
import sys

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

SETTINGS_PATH = "/home/reuben/Documents/REBset_v1.ini"

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
    persisted channel -> axis letter map from SETTINGS_PATH, falling
    back to CHANNEL_DEFAULT_LETTER for anything missing/unrecognized/
    duplicated. See that function's docstring for the full reasoning.
    '''
    assignments = dict(CHANNEL_DEFAULT_LETTER)
    try:
        with open(SETTINGS_PATH, "r") as f:
            xml_text = f.read()
    except OSError as e:
        print("Could not read " + SETTINGS_PATH + ": " + str(e))
        return assignments

    match = re.search(r'<channel_assignments>(.*?)</channel_assignments>', xml_text, re.DOTALL)
    if not match:
        return assignments

    for channel_id, letter in re.findall(r'<channel id="(\d\d)">([A-Z])</channel>', match.group(1)):
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
    return result.stdout.strip()

def get_pid_gain(hal_component, param):
    hal_pin = hal_component + "." + PID_PARAM_PIN[param]
    result = subprocess.run(
        ["halcmd", "getp", hal_pin],
        check=True,
        capture_output=True,
        text=True
    )
    return result.stdout.strip()

def get_backlash(joint_num):
    hal_pin = "joint." + str(joint_num) + ".backlash"
    result = subprocess.run(
        ["halcmd", "getp", hal_pin],
        check=True,
        capture_output=True,
        text=True
    )
    return result.stdout.strip()

def set_single_value(xml_text, axis_id, tag, value):
    '''
    Patches a single flat <tag>value</tag> element (e.g. <backlash>)
    inside a specific axis's <axis id="..."> block, leaving everything
    else in the file - including any other element on that same axis -
    untouched. Same two-step "find the axis block, then find the tag
    within it" approach as set_pid_block above (more robust than
    assuming a fixed element order within <axis>, unlike the scale
    patch in main() below). Returns (new_xml_text, ok).
    '''
    axis_match = re.search(
        r'<axis\s+id="' + re.escape(axis_id) + r'">.*?</axis>',
        xml_text, re.DOTALL
    )
    if not axis_match:
        print("No <axis id=\"" + axis_id + "\"> entry found in "
              + SETTINGS_PATH + " - leaving it unchanged")
        return xml_text, False

    axis_block = axis_match.group(0)
    new_axis_block, count = re.subn(
        r'(<' + tag + r'>)-?[\d.]+(</' + tag + r'>)',
        r'\g<1>' + value + r'\g<2>',
        axis_block, count=1
    )
    if count == 0:
        print("No <" + tag + "> entry found for axis " + axis_id
              + " in " + SETTINGS_PATH + " - leaving it unchanged")
        return xml_text, False

    new_xml_text = xml_text[:axis_match.start()] + new_axis_block + xml_text[axis_match.end():]
    return new_xml_text, True

def set_pid_block(xml_text, axis_id, block_tag, values):
    '''
    Patches P/I/D/FF0/FF1/FF2 values into a specific axis's <pid> (or
    <pid_pos>/<pid_vel>) block, leaving everything else in the file -
    including any other block on that same axis - untouched. Returns
    (new_xml_text, ok).
    '''
    axis_match = re.search(
        r'<axis\s+id="' + re.escape(axis_id) + r'">.*?</axis>',
        xml_text, re.DOTALL
    )
    if not axis_match:
        print("No <axis id=\"" + axis_id + "\"> entry found in "
              + SETTINGS_PATH + " - leaving it unchanged")
        return xml_text, False

    axis_block = axis_match.group(0)
    block_match = re.search(
        r'<' + block_tag + r'>.*?</' + block_tag + r'>',
        axis_block, re.DOTALL
    )
    if not block_match:
        print("No <" + block_tag + "> entry found for axis " + axis_id
              + " in " + SETTINGS_PATH + " - leaving it unchanged")
        return xml_text, False

    pid_block = block_match.group(0)
    for param, value in values.items():
        pid_block, count = re.subn(
            r'(<' + param + r'>)-?[\d.]+(</' + param + r'>)',
            r'\g<1>' + value + r'\g<2>',
            pid_block, count=1
        )
        if count == 0:
            print("No <" + param + "> entry found in axis " + axis_id + "'s <"
                  + block_tag + "> block in " + SETTINGS_PATH + " - leaving it unchanged")
            return xml_text, False

    new_axis_block = axis_block[:block_match.start()] + pid_block + axis_block[block_match.end():]
    new_xml_text = xml_text[:axis_match.start()] + new_axis_block + xml_text[axis_match.end():]
    return new_xml_text, True

def main():
    try:
        with open(SETTINGS_PATH, "r") as f:
            xml_text = f.read()
    except OSError as e:
        print("Could not read " + SETTINGS_PATH + ": " + str(e))
        sys.exit(1)

    for axis_id, stepgen_ch in AXIS_STEPGEN.items():
        try:
            value = get_scale(stepgen_ch)
        except subprocess.CalledProcessError as e:
            print("Error reading scale for axis " + axis_id + ": " + e.stderr)
            continue
        except FileNotFoundError:
            print("halcmd not found - is the LinuxCNC environment sourced?")
            sys.exit(1)

        pattern = (
            r'(<axis\s+id="' + re.escape(axis_id) + r'">\s*<scale>)'
            r'-?[\d.]+'
            r'(</scale>)'
        )
        new_text, count = re.subn(
            pattern, r'\g<1>' + value + r'\g<2>', xml_text, count=1
        )
        if count == 0:
            print("No <axis id=\"" + axis_id + "\"> entry found in "
                  + SETTINGS_PATH + " - leaving it unchanged")
            continue

        xml_text = new_text
        print("Saved " + axis_id + " scale = " + value)

    for axis_id, hal_component in PID_AXES.items():
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

        xml_text, ok = set_pid_block(xml_text, axis_id, "pid", values)
        if ok:
            print("Saved " + axis_id + " PID gains = " + str(values))

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

            xml_text, ok = set_pid_block(xml_text, spindle_id, block_tag, values)
            if ok:
                print("Saved " + spindle_id + " " + suffix + " PID gains = " + str(values))

    for axis_id, joint_num in JOINT_NUMBER.items():
        try:
            value = get_backlash(joint_num)
        except subprocess.CalledProcessError as e:
            print("Error reading backlash for axis " + axis_id + ": " + e.stderr)
            continue
        except FileNotFoundError:
            print("halcmd not found - is the LinuxCNC environment sourced?")
            sys.exit(1)

        xml_text, ok = set_single_value(xml_text, axis_id, "backlash", value)
        if ok:
            print("Saved " + axis_id + " backlash = " + value)

    try:
        with open(SETTINGS_PATH, "w") as f:
            f.write(xml_text)
    except OSError as e:
        print("Could not write " + SETTINGS_PATH + ": " + str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
