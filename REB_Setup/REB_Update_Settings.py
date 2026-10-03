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
# Version                                                             #
#   1.0 - 03 October 2026                                             #
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
    if not added:
        print("Settings file is up to date - nothing to add.")
        return 0

    backup = SETTINGS_PATH + ".bak-" + time.strftime("%Y%m%d-%H%M%S")
    shutil.copy2(SETTINGS_PATH, backup)
    reb_settings_io.save_settings(user, SETTINGS_PATH)
    print("Added %d new setting(s), using the starting values:" % len(added))
    for where in added:
        print("    " + where)
    print("Previous settings file saved as " + backup)
    return 0


if __name__ == "__main__":
    sys.exit(main())
