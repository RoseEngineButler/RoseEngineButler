#!/usr/bin/env python3
"""
REB_Scale_Persist.py

At LinuxCNC shutdown, reads the current stepgen position-scale value
for each Rose Engine Butler axis directly from HAL and writes it back
into REB_Settings_v1.ini, updating only the <scale> value inside each
<axis id="..."> block. The rest of the file - including its header
comment - is left untouched.

Invoked from REB_Shutdown.hal:
    loadusr -w python3 REB_Display/REB_Scale_Persist.py
"""

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

SETTINGS_PATH = "/home/reuben/linuxcnc/configs/RoseEngineButlerLocal/REB_Settings_v1.ini"

def get_scale(stepgen_ch):
    hal_pin = "hm2_7i92.0.stepgen." + stepgen_ch + ".position-scale"
    result = subprocess.run(
        ["halcmd", "getp", hal_pin],
        check=True,
        capture_output=True,
        text=True
    )
    return result.stdout.strip()

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
            r'[\d.]+'
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

    try:
        with open(SETTINGS_PATH, "w") as f:
            f.write(xml_text)
    except OSError as e:
        print("Could not write " + SETTINGS_PATH + ": " + str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
