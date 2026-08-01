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
#   REB_Generate_Local_Ini.py
#
# Purpose:
#   Regenerates REB.local.ini (written alongside REB.ini, in this repo's
#   own directory - see below for why it can't live in
#   RoseEngineButlerLocal) from this repo's tracked REB.ini, overlaying
#   whatever local Max Jog Speed / Measurement System choices are
#   currently persisted in RoseEngineButlerLocal/REB_Settings_v1.ini.
#
#   REB.ini's [TRAJ]/[DISPLAY] MAX_LINEAR_VELOCITY and [TRAJ]LINEAR_UNITS
#   / [JOINT_n]UNITS are read once by LinuxCNC at process startup, before
#   any HAL component or the GladeVCP panel's own Python (REB_main.py)
#   ever runs - so they can't be corrected from within a running session
#   the way stepgen scale/PID gains are (those have real HAL pins).
#   REB_main.py used to patch them directly into the tracked REB.ini, but
#   that meant a `git pull` of someone else's REB.ini change could
#   silently overwrite this machine's own jog-speed/units choice.
#
#   Run this instead, before every LinuxCNC launch (see REB_Launch.sh):
#   it always starts from the current tracked REB.ini and overlays only
#   the two settings below, so upstream REB.ini edits still flow through
#   untouched and the local choice never gets committed or clobbered.
#
#   A setting is only overlaid if a persisted value actually exists in
#   REB_Settings_v1.ini - if the Settings tab's Max Jog Speed /
#   Measurement System controls have never been touched on this machine,
#   REB.ini's own shipped values are carried through exactly as
#   committed.
#
#   REB.local.ini MUST live next to REB.ini (this repo's own directory),
#   not in RoseEngineButlerLocal: LinuxCNC treats the directory of the
#   INI file passed on its command line as "the configuration
#   directory" and resolves every *relative* path found anywhere in that
#   config - REB.ini's own HALFILE=REB.hal and
#   POSTGUI_HALFILE=REB_Display/REB_PostGUI_v1.hal, PARAMETER_FILE=
#   sim.var, and even the relative `loadusr python3
#   REB_Display/REB_Scale_Persist.py` line inside REB_Shutdown.hal -
#   against that one directory. Generating REB.local.ini into
#   RoseEngineButlerLocal instead broke every one of those (confirmed
#   live: "CANNOT FIND FILE FOR:REB.hal" and REB_Scale_Persist.py not
#   found at shutdown). Writing it next to REB.ini keeps the
#   configuration directory exactly where every relative path already
#   expects it.
#
# End User Customisation:
#   THE END USER OF THE ROSE ENGINE BUTLER SYSTEM SHOULD NOT MODIFY
#   THIS FILE.
#
#   Changes to this file are not supported by Colvin Tools nor
#   Brainwave Embedded.
#
# Version
#   1.0 - 1 August 2026, Claude
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

import os
import re
import sys

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REB_INI_PATH = os.path.join(REPO_DIR, "REB.ini")

SETTINGS_PATH = "/home/reuben/linuxcnc/configs/RoseEngineButlerLocal/REB_Settings_v1.ini"

# Must sit next to REB.ini (not in RoseEngineButlerLocal) - see the file
# header above for why: LinuxCNC resolves every relative path in the
# config (HALFILE, POSTGUI_HALFILE, PARAMETER_FILE, and relative paths
# inside the HAL files themselves) against the directory of whichever
# ini file was actually launched.
LOCAL_INI_PATH = os.path.join(REPO_DIR, "REB.local.ini")


def _read_settings_xml():
    try:
        with open(SETTINGS_PATH, "r") as f:
            return f.read()
    except OSError:
        # No persisted settings yet on this machine - fall through with
        # every overlay below finding nothing to match, so REB.ini's own
        # shipped values pass through unchanged.
        return ""


def _overlay_max_jog_speed(text, xml_text):
    match = re.search(r'<max_jog_speed>([0-9.eE+-]+)</max_jog_speed>', xml_text)
    if not match:
        return text, None

    value_text = "%.4f" % float(match.group(1))
    text, n = re.subn(
        r'(?m)^(MAX_LINEAR_VELOCITY\s*= )\S+',
        lambda m: m.group(1) + value_text,
        text,
    )
    return text, (value_text, n)


def _overlay_measurement_system(text, xml_text):
    match = re.search(r'<measurement_system>(Metric|Imperial)</measurement_system>', xml_text)
    if not match:
        return text, None

    if match.group(1) == "Metric":
        linear_units, joint_units = "mm", "MM"
    else:
        linear_units, joint_units = "inch", "INCH"

    # Matches REB.ini's existing casing convention: LINEAR_UNITS lowercase
    # ("inch"/"mm"), per-joint UNITS uppercase ("INCH"/"MM") - both accepted
    # case-insensitively by LinuxCNC. JOINT_2 (B, angular) uses
    # UNITS = DEGREE and is never matched by the INCH/MM pattern below, so
    # it's left untouched.
    text, n1 = re.subn(
        r'(?m)^(LINEAR_UNITS\s*= )\S+',
        lambda m: m.group(1) + linear_units,
        text,
        count=1,
    )
    text, n2 = re.subn(
        r'(?m)^(UNITS\s*= )(INCH|MM)$',
        lambda m: m.group(1) + joint_units,
        text,
    )
    return text, (match.group(1), n1, n2)


def main():
    try:
        with open(REB_INI_PATH, "r") as f:
            text = f.read()
    except OSError as e:
        print("Could not read " + REB_INI_PATH + ": " + str(e))
        sys.exit(1)

    xml_text = _read_settings_xml()

    text, jog_result = _overlay_max_jog_speed(text, xml_text)
    if jog_result:
        value_text, n = jog_result
        print("Overlaid MAX_LINEAR_VELOCITY = " + value_text + " (" + str(n) + " line(s))")

    text, units_result = _overlay_measurement_system(text, xml_text)
    if units_result:
        system, n1, n2 = units_result
        print("Overlaid " + system + " units (" + str(n1) + " LINEAR_UNITS, "
              + str(n2) + " UNITS line(s))")

    try:
        with open(LOCAL_INI_PATH, "w") as f:
            f.write(text)
    except OSError as e:
        print("Could not write " + LOCAL_INI_PATH + ": " + str(e))
        sys.exit(1)

    print("Wrote " + LOCAL_INI_PATH)


if __name__ == "__main__":
    main()
