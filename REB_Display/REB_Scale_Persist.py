#!/usr/bin/env python3
"""
REB_Scale_Persist.py

At LinuxCNC shutdown, reads the current stepgen position-scale value
for each Rose Engine Butler axis directly from HAL and writes it back
into REB_Settings_v1.ini, updating only the <scale> value inside each
<axis id="..."> block. The rest of the file - including its header
comment - is left untouched.

Also offers to save any pending named .settings.ini changes (see
docs/settings_file.md) - see prompt_save_pending_settings() below for
why that lives here rather than in rosetta.py/the Settings tab itself.

Invoked from REB_Shutdown.hal:
    loadusr -w python3 REB_Display/REB_Scale_Persist.py
"""

import json
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

SETTINGS_PATH = "/home/reuben/linuxcnc/configs/RoseEngineButlerLocal/REB_Settings_v1.ini"

# Mirrors the same-named constants in rosetta.py (see AXIS_STEPGEN above
# for why duplicating small constants across these two independent
# scripts, rather than importing between them, is this codebase's
# existing pattern for this exact split).
PENDING_SETTINGS_PATH = "/home/reuben/linuxcnc/configs/RoseEngineButlerLocal/REB_Pending_Settings.settings.ini"
LAST_SETTINGS_PATH_FILE = "/home/reuben/linuxcnc/configs/RoseEngineButlerLocal/REB_Last_Settings_Path.txt"
REBSET_DEFAULT_DIR = os.path.expanduser("~/Documents")
REBSET_EXTENSION = ".settings.ini"

def _name_from_settings_path(path):
    '''
    Mirrors rosetta.py's function of the same name - see its docstring.
    Not os.path.splitext(basename)[0]: that only strips the single final
    suffix (".ini"), leaving ".settings" stuck to the name for this
    extension specifically, since it has two dots.
    '''
    basename = os.path.basename(path)
    if basename.endswith(REBSET_EXTENSION):
        return basename[:-len(REBSET_EXTENSION)]
    return os.path.splitext(basename)[0]

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

    try:
        with open(SETTINGS_PATH, "w") as f:
            f.write(xml_text)
    except OSError as e:
        print("Could not write " + SETTINGS_PATH + ": " + str(e))
        sys.exit(1)

    prompt_save_pending_settings()


def prompt_save_pending_settings():
    '''
    If the Settings tab staged a pending .settings.ini snapshot (unsaved
    changes at the time of exit - see PENDING_SETTINGS_PATH in
    rosetta.py), ask whether to save it, then let the operator pick
    exactly where/under what name via a real Save-As file dialog -
    both so they can see where it's going to land, and so they can
    rename it right there instead of only being able to accept the
    system-picked default.

    This has to live here, not in rosetta.py/the Settings tab's own GTK
    process: a delete-event/destroy hook on that component's own window
    does not fire on a real AXIS exit (confirmed live) - AXIS tears
    embedded tabs down by yanking their X window out from under them,
    not a normal close negotiation the embedded app gets a say in. This
    script, in contrast, is already proven to run reliably and block:
    it's invoked as `loadusr -w` from REB_Shutdown.hal, which is why the
    scale-persist step above already works every time. Tkinter (not
    GTK) is used here specifically because it's a guaranteed dependency
    already (AXIS itself is Tk-based) and needs no gladevcp/GtkBuilder
    machinery for these two small dialogs.
    '''
    if not os.path.isfile(PENDING_SETTINGS_PATH):
        return

    try:
        with open(PENDING_SETTINGS_PATH, "r") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        print("Could not read " + PENDING_SETTINGS_PATH + ": " + str(e))
        return

    name = data.get("name") or "settings"

    try:
        import tkinter
        from tkinter import messagebox, filedialog
        root = tkinter.Tk()
        root.withdraw()
        # By the time this runs, AXIS's own screen has typically already
        # visually torn down (see docs/settings_file.md, Decision 4) -
        # force this to the front rather than let it appear as an easy
        # to miss window behind whatever's left on screen.
        root.attributes("-topmost", True)
        root.lift()
        root.focus_force()

        save = messagebox.askyesno(
            "Rose Engine Butler",
            "Save changes to '" + name + "' settings file before exiting?"
        )

        path = None
        if save:
            os.makedirs(REBSET_DEFAULT_DIR, exist_ok=True)
            safe_name = re.sub(r'[^A-Za-z0-9 _-]', '_', name)
            path = filedialog.asksaveasfilename(
                title="Save Settings",
                initialdir=REBSET_DEFAULT_DIR,
                initialfile=safe_name + REBSET_EXTENSION,
                defaultextension=REBSET_EXTENSION,
                filetypes=[("Rose Engine Butler Settings", "*" + REBSET_EXTENSION)],
            )

        root.destroy()
    except Exception as e:
        print("Could not show save-before-exit prompt: " + str(e))
        return

    if path:
        # The chosen filename is the name from here on - same rule
        # Settings_Save_As uses - so a rename via this dialog (or later,
        # outside the app) is reflected next time this file is loaded.
        data["name"] = _name_from_settings_path(path)
        try:
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
            with open(LAST_SETTINGS_PATH_FILE, "w") as f:
                f.write(path)
            print("Saved pending settings to " + path)
        except OSError as e:
            print("Could not save pending settings to " + path + ": " + str(e))
            return
    else:
        print("Operator chose not to save pending settings")

    # Resolved either way (saved, or explicitly declined/cancelled) -
    # don't ask again next session about the same now-settled change.
    try:
        os.remove(PENDING_SETTINGS_PATH)
    except OSError as e:
        print("Could not clear " + PENDING_SETTINGS_PATH + ": " + str(e))


if __name__ == "__main__":
    main()
