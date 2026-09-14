#!/usr/bin/env python3
"""
REB_Scale_Persist.py

At LinuxCNC shutdown, reads the current stepgen position-scale value
for each Rose Engine Butler axis directly from HAL and writes it back
into REB_Settings_v1.ini, updating only that axis's "scale" value. The
rest of the file is left untouched.

Also persists each axis's/spindle loop's live P/I/D/FF0/FF1/FF2 pid.*
gains the same way, into that axis's "pid" entry (or "pid_pos"/
"pid_vel" for the two spindle loops) - see PID_SPINDLE_LOOPS below.
These gains are set live from REB_Settings_v1.ini by REB_main.py's
_load_pid_settings() at Settings-tab load and by each PID spin
button's value-changed handler while running (see REB.hal for why
they're no longer set from REB.ini directly), so this is the only place
that carries a retuned gain forward into the next session - exactly
mirroring how scale already worked before PID gains were added to this
file.

Also persists each axis LETTER's live joint.N.backlash HAL parameter
into that axis's "backlash" value the same way. Set live from
REB_Settings_v1.ini by REB_main.py's _load_backlash_settings() at
Settings-tab load and by each Backlash spin button's value-changed
handler while running (see REB.ini for why it's no longer relied on
directly at LinuxCNC startup beyond an initial default). Spindles no
longer have a joint number at all (see this file's own header note in
REB_Settings_Restore.py) so their backlash is no longer persisted here
either - nothing would ever restore it.

Invoked from REB_Shutdown.hal:
    loadusr -w python3 REB_Display/REB_Scale_Persist.py

------------------------------------------------------------------
Any-role/any-channel generalization (13 September 2026, Rich)
------------------------------------------------------------------
Any of 10 roles (8 axis letters or 2 spindles) can now be assigned to
any of the 8 physical channels - see CLAUDE.md and REB_Setup/
REB_Generate_Local_Ini.py, whose RoleLayout this script's own
RoleLayout mirrors (duplicated rather than imported, per this
codebase's usual convention for small maps/logic shared only at the
value level across independent scripts). Sp0/Sp1 and the 8 axis
letters are now restored/persisted through the exact same single loop
over CHANNEL_ROLES, resolved via RoleLayout.channel_of - no more
separate "spindles are always present" special case, matching how
REB_Settings_Restore.py's load-side counterpart was fixed at the same
time.
"""

import os
import subprocess
import sys

import reb_settings_io

# The 8 axis letters (Y removed - not used on this machine, LATHE=1)
# and the 2 spindles - the 10 possible roles a channel can be assigned.
AXIS_SELECTION_LETTERS = ("X", "Z", "U", "V", "W", "A", "B", "C")
SPINDLE_IDS = ("Sp0", "Sp1")
CHANNEL_ROLES = AXIS_SELECTION_LETTERS + SPINDLE_IDS

# Channel id ("00".."07") -> the role REB.ini/REB.hal ship with by
# default. Mirrors reb_settings_io.py's own CHANNEL_DEFAULT_ROLE.
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

# Canonical joint-numbering order for active axis letters - mirrors
# REB_Setup/REB_Generate_Local_Ini.py's JOINT_NUMBER_CANONICAL_ORDER
# exactly (must match, since this script needs to read back the joint
# number that script's REB.local.ini generation already assigned for
# this session).
JOINT_NUMBER_CANONICAL_ORDER = ("X", "Z", "B", "U", "V", "W", "A", "C")

SETTINGS_PATH = reb_settings_io.SETTINGS_PATH


def _read_channel_assignments():
    '''
    Reads the persisted channel -> role map, falling back to
    CHANNEL_DEFAULT_ROLE for anything missing, unrecognized, or -
    defensively, since REBset_v1.ini's own header says it should not be
    hand-edited - assigned to more than one channel. Mirrors
    REB_Generate_Local_Ini.py's/REB_main.py's/REB_Settings.py's/
    REB_Settings_Restore.py's own copies of this same function.
    '''
    assignments = dict(CHANNEL_DEFAULT_ROLE)
    stored = reb_settings_io.load_settings().get("channel_assignments", {})
    for channel_id, role in stored.items():
        if channel_id in assignments and role in CHANNEL_ROLES:
            assignments[channel_id] = role

    if len(set(assignments.values())) != len(assignments):
        print("Duplicate role(s) in persisted channel_assignments - using shipped defaults")
        return dict(CHANNEL_DEFAULT_ROLE)

    return assignments


class RoleLayout(object):
    '''
    Mirrors REB_Setup/REB_Generate_Local_Ini.py's own RoleLayout - which
    of the 10 roles are active (assigned to some channel) this session,
    which channel each one is on, and which joint number an active axis
    letter's joint.N now is (see JOINT_NUMBER_CANONICAL_ORDER).
    '''
    def __init__(self, assignments):
        self.channel_of = {}
        for channel_id, role in assignments.items():
            self.channel_of[role] = channel_id

        active_letters = [l for l in JOINT_NUMBER_CANONICAL_ORDER if l in self.channel_of]
        self.joint_number = {letter: i for i, letter in enumerate(active_letters)}


_ROLE_LAYOUT = RoleLayout(_read_channel_assignments())

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
    settings = reb_settings_io.load_settings()
    axes = settings.setdefault("axes", {})

    for role in CHANNEL_ROLES:
        channel_id = _ROLE_LAYOUT.channel_of.get(role)
        if channel_id is None:
            # Not currently assigned to any channel this session -
            # nothing live to read, leave its persisted value untouched.
            continue

        try:
            value = get_scale(channel_id)
        except subprocess.CalledProcessError as e:
            print("Error reading scale for axis " + role + ": " + e.stderr)
        except FileNotFoundError:
            print("halcmd not found - is the LinuxCNC environment sourced?")
            sys.exit(1)
        else:
            axes.setdefault(role, {})["scale"] = value
            print("Saved " + role + " scale = " + str(value))

        for param in ("max_vel", "max_accel"):
            try:
                value = get_stepgen_max(channel_id, param)
            except subprocess.CalledProcessError as e:
                print("Error reading " + param + " for axis " + role + ": " + e.stderr)
                continue
            except FileNotFoundError:
                print("halcmd not found - is the LinuxCNC environment sourced?")
                sys.exit(1)
            axes.setdefault(role, {})[param] = value
            print("Saved " + role + " " + param + " = " + str(value))

        if role in AXIS_SELECTION_LETTERS:
            values = {}
            try:
                for param in PID_PARAMS:
                    values[param] = get_pid_gain("pid." + role.lower(), param)
            except subprocess.CalledProcessError as e:
                print("Error reading PID gains for axis " + role + ": " + e.stderr)
            except FileNotFoundError:
                print("halcmd not found - is the LinuxCNC environment sourced?")
                sys.exit(1)
            else:
                axes.setdefault(role, {}).setdefault("pid", {}).update(values)
                print("Saved " + role + " PID gains = " + str(values))

            try:
                value = get_backlash(_ROLE_LAYOUT.joint_number[role])
            except subprocess.CalledProcessError as e:
                print("Error reading backlash for axis " + role + ": " + e.stderr)
            except FileNotFoundError:
                print("halcmd not found - is the LinuxCNC environment sourced?")
                sys.exit(1)
            else:
                axes.setdefault(role, {})["backlash"] = value
                print("Saved " + role + " backlash = " + str(value))
        else:
            for suffix, hal_component in PID_SPINDLE_LOOPS[role].items():
                block_tag = "pid_pos" if suffix == "Pos" else "pid_vel"
                values = {}
                try:
                    for param in PID_PARAMS:
                        values[param] = get_pid_gain(hal_component, param)
                except subprocess.CalledProcessError as e:
                    print("Error reading " + suffix + " PID gains for " + role
                          + ": " + e.stderr)
                    continue
                except FileNotFoundError:
                    print("halcmd not found - is the LinuxCNC environment sourced?")
                    sys.exit(1)
                axes.setdefault(role, {}).setdefault(block_tag, {}).update(values)
                print("Saved " + role + " " + suffix + " PID gains = " + str(values))

    try:
        reb_settings_io.save_settings(settings)
    except OSError as e:
        print("Could not write " + SETTINGS_PATH + ": " + str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
