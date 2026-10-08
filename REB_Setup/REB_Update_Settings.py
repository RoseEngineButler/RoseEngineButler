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
#   Also gives each axis its own Max Speed / Max Acceleration / PID   #
#   Max Output (and each spindle its Indexing Max Output) the first   #
#   time, worked out from REB.ini and the machine's own stepgen       #
#   values (see fill_speed_limits) - raising a stepgen Max Vel / Max  #
#   Accel only if it's now too low, the one case where an existing    #
#   value is changed.                                                 #
#                                                                     #
# Version                                                             #
#   1.0 - 03 October 2026                                             #
#   1.1 - 07 October 2026 - raise too-low stepgen Max Accel           #
#   1.2 - 08 October 2026 - fill in each axis's speed limits, which   #
#         moved from REB.ini to REB Settings (replaces 1.1's rule)    #
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
AXIS_LETTERS = ("X", "Z", "B", "A", "C", "U", "V", "W")


def read_axis_planner(path=REB_INI_PATH):
    '''
    Returns {letter: (MAX_VELOCITY, MAX_ACCELERATION)} from each
    [AXIS_<letter>] section of REB.ini - the starting point for an axis
    that has no Max Speed / Max Acceleration of its own yet.
    '''
    found = {}
    letter = None
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if line.startswith("["):
                letter = line[6:-1] if line.startswith("[AXIS_") and line[6:-1] in AXIS_LETTERS else None
                if letter:
                    found[letter] = {}
                continue
            if letter is None or "=" not in line or line.startswith("#"):
                continue
            key, value = (part.strip() for part in line.split("=", 1))
            if key in ("MAX_VELOCITY", "MAX_ACCELERATION") and key not in found[letter]:
                try:
                    found[letter][key] = float(value)
                except ValueError:
                    pass
    return {k: (v["MAX_VELOCITY"], v["MAX_ACCELERATION"])
            for k, v in found.items() if len(v) == 2}


def fill_speed_limits(user, planner):
    '''
    Gives every axis that doesn't have one yet its Max Speed, Max
    Acceleration and PID Max Output, and every spindle its Indexing Max
    Output (reb_settings_io.fill_missing_limits). Must run before
    add_missing, so these come from this machine's own values rather
    than the starting file's. Returns a list of what was set or raised.
    '''
    changed = []
    system = user.get("measurement_system", "Imperial")
    for axis_id, entry in sorted(user.get("axes", {}).items()):
        if not isinstance(entry, dict):
            continue
        if axis_id in reb_settings_io.SPINDLE_IDS:
            notes = reb_settings_io.fill_missing_limits(axis_id, entry)
        elif axis_id in planner:
            notes = reb_settings_io.fill_missing_limits(axis_id, entry, planner[axis_id], system)
        else:
            continue
        changed += [axis_id + " " + note for note in notes]
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

    try:
        raised = fill_speed_limits(user, read_axis_planner())
    except OSError as e:
        print("WARNING: could not read " + REB_INI_PATH + " (" + str(e) + ") - speed limits not filled in.")
        raised = []
    added = add_missing(user, seed)
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
        print("Set up %d speed limit value(s) (now in REB Settings):" % len(raised))
        for what in raised:
            print("    " + what)
    print("Previous settings file saved as " + backup)
    return 0


if __name__ == "__main__":
    sys.exit(main())
