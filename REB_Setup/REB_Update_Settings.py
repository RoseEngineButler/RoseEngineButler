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
# Rose Engine Butler                                                  #
#######################################################################
#                                                                     #
# File:                                                               #
#   REB_Update_Settings.py                                            #
#                                                                     #
# Purpose:                                                            #
#   Run by REB_Update.sh after the latest files have been pulled from #
#   GitHub. Adds to this machine's settings file                      #
#   (/home/reuben/Documents/REBset_v1.ini) any setting that the       #
#   shipped starting file (REB_Setup/REBset_v1.ini) has but this      #
#   machine's file doesn't - so a new feature's settings appear in    #
#   the file with sensible starting values. It never changes or       #
#   removes a value that is already there.                            #
#                                                                     #
#   This relies on REB_Setup/REBset_v1.ini always holding every       #
#   setting the programs use, with its starting value - keep it up to #
#   date whenever a new setting is added.                             #
#                                                                     #
#   Also raises any axis's saved stepgen Max Accel that is too low    #
#   for REB.ini's MAX_ACCELERATION (see raise_stepgen_accel) - the    #
#   one case where an existing value is changed.                      #
#                                                                     #
# Version                                                             #
#   1.0 - 03 October 2026                                             #
#   1.1 - 07 October 2026 - raise too-low stepgen Max Accel           #
#                                                                     #
# Copyright (c) 2026 Colvin Tools and Brainwave Embedded.             #
#                                                                     #
# The MIT/X Consortium License applies - see LICENSE.                 #
#######################################################################

import json
import os
import shutil
import sys
import time

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REB_INI_PATH = os.path.join(REPO_DIR, "REB.ini")
sys.path.insert(0, os.path.join(REPO_DIR, "REB_Display"))
import reb_settings_io

SEED_PATH = os.path.join(REPO_DIR, "REB_Setup", "REBset_v1.ini")
SETTINGS_PATH = reb_settings_io.SETTINGS_PATH

# Settings whose value is one whole choice, not a set of independent
# entries - if this machine has the key at all, it's left exactly as it
# is. Filling in single entries could break it: e.g. adding a missing
# channel from the starting file to channel_assignments can put the
# same axis on two channels, which makes every program ignore the whole
# assignment and fall back to the defaults.
WHOLE_VALUE_KEYS = ("channel_assignments", "limit_switches", "device_names")


def add_missing(user, seed, path=""):
    '''
    Copies into user every key seed has that user doesn't, recursing
    into dictionaries both have (e.g. each axis's settings), and returns
    the list of what was added. Existing values - including lists and
    WHOLE_VALUE_KEYS - are never changed.
    '''
    added = []
    for key, seed_value in seed.items():
        where = path + "/" + key if path else key
        if key not in user:
            user[key] = json.loads(json.dumps(seed_value))
            added.append(where)
        elif (isinstance(user[key], dict) and isinstance(seed_value, dict)
              and not (path == "" and key in WHOLE_VALUE_KEYS)):
            added += add_missing(user[key], seed_value, where)
    return added


# Each axis's stepgen ceiling (its saved "max_accel", which REB.hal sets
# as the stepgen's maxaccel at startup, overriding REB.ini's
# STEPGEN_MAXACCEL) must stay above the trajectory planner's limit
# (REB.ini's MAX_ACCELERATION) or the stepgen can't keep up and the axis
# trips a following error on its first quick move. REB.ini keeps a
# 1.5-2x margin; below 1.5x counts as too low.
STEPGEN_ACCEL_MIN_MARGIN = 1.5
AXIS_LETTERS = ("X", "Z", "B", "A", "C", "U", "V", "W")


def read_axis_accels(path=REB_INI_PATH):
    '''
    Returns {letter: (MAX_ACCELERATION, STEPGEN_MAXACCEL)} from REB.ini:
    MAX_ACCELERATION from [AXIS_<letter>], STEPGEN_MAXACCEL from the
    [JOINT_n] section that follows it (REB.ini always puts an axis's
    joint section straight after its axis section).
    '''
    found = {}
    letter = None
    in_joint = False
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if line.startswith("["):
                if line.startswith("[AXIS_") and line[6:-1] in AXIS_LETTERS:
                    letter, in_joint = line[6:-1], False
                    found[letter] = [None, None]
                elif line.startswith("[JOINT_") and letter is not None and not in_joint:
                    in_joint = True
                else:
                    letter = None
                continue
            if letter is None or "=" not in line or line.startswith("#"):
                continue
            key, value = (part.strip() for part in line.split("=", 1))
            try:
                number = float(value)
            except ValueError:
                continue
            if key == "MAX_ACCELERATION" and not in_joint and found[letter][0] is None:
                found[letter][0] = number
            elif key == "STEPGEN_MAXACCEL" and in_joint and found[letter][1] is None:
                found[letter][1] = number
    return {k: tuple(v) for k, v in found.items() if None not in v}


def raise_stepgen_accel(user, accels):
    '''
    Raises each axis's saved stepgen max_accel that is below
    STEPGEN_ACCEL_MIN_MARGIN x REB.ini's MAX_ACCELERATION to REB.ini's
    own STEPGEN_MAXACCEL (or to the minimum, if that's higher). Returns
    a list of what was changed. Values already high enough - including
    ones tuned above REB.ini's - are left alone.
    '''
    changed = []
    for letter, (planner, stepgen) in sorted(accels.items()):
        entry = user.get("axes", {}).get(letter)
        if not isinstance(entry, dict) or not isinstance(entry.get("max_accel"), (int, float)):
            continue
        minimum = planner * STEPGEN_ACCEL_MIN_MARGIN
        if entry["max_accel"] < minimum:
            new = max(stepgen, minimum)
            changed.append("%s Max Accel %g -> %g (REB.ini plans %s at up to %g)"
                           % (letter, entry["max_accel"], new, letter, planner))
            entry["max_accel"] = new
    return changed


def main():
    print("Checking " + SETTINGS_PATH + " for new settings")

    try:
        with open(SEED_PATH, "r") as f:
            seed = json.load(f)
    except (OSError, ValueError) as e:
        print("ERROR: could not read " + SEED_PATH + ": " + str(e))
        return 1

    if not os.path.exists(SETTINGS_PATH):
        os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
        shutil.copyfile(SEED_PATH, SETTINGS_PATH)
        print("No settings file yet - copied the starting settings into place.")
        return 0

    with open(SETTINGS_PATH, "r") as f:
        raw = f.read()
    if raw.lstrip().startswith(("<?xml", "<settings")):
        # Old XML format: let the normal reader convert it (it backs up
        # the original first and writes the JSON version), then carry on.
        reb_settings_io.load_settings()
        with open(SETTINGS_PATH, "r") as f:
            raw = f.read()
    try:
        user = json.loads(raw)
    except ValueError as e:
        # Never replace a file we can't read - it may hold the only copy
        # of this machine's calibration.
        print("ERROR: " + SETTINGS_PATH + " could not be read (" + str(e) + ") - left unchanged.")
        return 1
    if not isinstance(user, dict):
        print("ERROR: " + SETTINGS_PATH + " is not a settings file - left unchanged.")
        return 1

    added = add_missing(user, seed)
    try:
        raised = raise_stepgen_accel(user, read_axis_accels())
    except OSError as e:
        print("WARNING: could not read " + REB_INI_PATH + " (" + str(e) + ") - Max Accel not checked.")
        raised = []
    if not added and not raised:
        print("Settings file is up to date - nothing to add.")
        return 0

    backup = SETTINGS_PATH + ".bak-" + time.strftime("%Y%m%d-%H%M%S")
    shutil.copy2(SETTINGS_PATH, backup)
    reb_settings_io.save_settings(user, SETTINGS_PATH)
    if added:
        print("Added %d new setting(s), using the starting values:" % len(added))
        for where in added:
            print("    " + where)
    if raised:
        print("Raised %d stepgen Max Accel value(s) to suit REB.ini:" % len(raised))
        for what in raised:
            print("    " + what)
    print("Previous settings file saved as " + backup)
    return 0


if __name__ == "__main__":
    sys.exit(main())
