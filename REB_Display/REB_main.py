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
#   REB_main.py
#
# Purpose:  This is used to handle buttons used in panels developed
#   for Rose Engine Butler's use on LinuxCNC.
#
# End User Customisation:
#   THE END USER OF THE ROSE ENGINE BUTLER SYSTEM SHOULD NOT MODIFY
#   THIS FILE.
#
#   Changes to this file are not supported by Colvin Tools nor
#   Brainwave Embedded.
#
# Version
#   1.0 - 21 July 2026, R. Colvin
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

import hal
import hal_glib
import glib
import time
import os
import linuxcnc
import webbrowser
import subprocess
import shutil
import re
import xml.etree.ElementTree as ET
from gi.repository import Gdk
from xml.sax.saxutils import escape, unescape
from gi.repository import Gtk
from gi.repository import GLib

SETTINGS_PATH = "/home/reuben/Documents/REBset_v1.ini"

# Channel id ("00".."05", matching the hm2_7i92.0.stepgen.NN suffix - see
# AXIS_STEPGEN below) -> the axis letter REB.ini/REB.hal ship with by
# default. This is the seed value for a channel's <channel_assignments>
# entry in REBset_v1.ini when the operator has never touched the Axis
# Selection tab - same "absent -> shipped default" convention as every
# other REBset_v1.ini-backed setting (see _load_measurement_system).
# Internal ids (AXIS_STEPGEN/JOINT_NUMBER/PID_AXES keys, Settings-tab
# widget-id prefixes) always stay these default letters, regardless of
# what the operator later assigns a channel to - see CLAUDE.md.
CHANNEL_DEFAULT_LETTER = {
    "00": "W",
    "01": "Z",
    "02": "U",
    "03": "V",
    "04": "X",
    "05": "B",
}

# Reverse of CHANNEL_DEFAULT_LETTER - internal id -> channel id. Used to
# resolve an internal id's *current* assigned letter (see _compute_pid_axes
# below and _clear_ena_override).
DEFAULT_LETTER_CHANNEL = {v: k for k, v in CHANNEL_DEFAULT_LETTER.items()}

# The 8 letters selectable on the Axis Selection tab (Y removed - not
# used on this machine). A/B/C are angular, the rest linear - see
# _axis_type_for_letter and REB_Setup/REB_Generate_Local_Ini.py's
# _overlay_axis_assignment.
AXIS_SELECTION_LETTERS = ("X", "Z", "U", "V", "W", "A", "B", "C")

def _axis_type_for_letter(letter):
    return "ANGULAR" if letter in ("A", "B", "C") else "LINEAR"

def _save_channel_assignments(assignments):
    '''
    Persists the Axis Selection tab's channel -> axis letter choices into
    REBset_v1.ini as a <channel_assignments><channel id="00">W</channel>...
    block, replacing the whole block each time - same reasoning as
    _save_device_names (simpler than patching individual <channel> entries,
    and the block is small enough a full rewrite costs nothing). assignments
    is a dict of channel id ("00".."05") -> letter; any channel missing from
    it falls back to CHANNEL_DEFAULT_LETTER.
    '''
    try:
        with open(SETTINGS_PATH, "r") as f:
            xml_text = f.read()
    except OSError as e:
        print("Could not read " + SETTINGS_PATH + ": " + str(e))
        return

    lines = ["    <channel_assignments>"]
    for channel_id in sorted(CHANNEL_DEFAULT_LETTER):
        letter = assignments.get(channel_id, CHANNEL_DEFAULT_LETTER[channel_id])
        lines.append('        <channel id="' + channel_id + '">' + letter + '</channel>')
    lines.append("    </channel_assignments>")
    block = "\n".join(lines)

    # [ \t]* eats any pre-existing indentation on the <channel_assignments>
    # line itself - see _save_device_names for why.
    pattern = re.compile(r'[ \t]*<channel_assignments>.*?</channel_assignments>', re.DOTALL)
    if pattern.search(xml_text):
        new_text, count = pattern.subn(lambda m: block, xml_text, count=1)
    else:
        new_text, count = re.subn(
            r'(<settings>)',
            lambda m: m.group(1) + "\n" + block,
            xml_text,
            count=1
        )

    if count == 0:
        print("Could not find a place to store <channel_assignments> in " + SETTINGS_PATH)
        return

    try:
        with open(SETTINGS_PATH, "w") as f:
            f.write(new_text)
        print("Saved channel assignments: " + str(assignments))
    except OSError as e:
        print("Could not write " + SETTINGS_PATH + ": " + str(e))

def _read_persisted_channel_assignments():
    '''
    Reads the persisted channel -> axis letter map straight from
    SETTINGS_PATH, falling back to CHANNEL_DEFAULT_LETTER for any channel
    whose <channel> entry is missing or unrecognized - same "absent ->
    shipped default" convention as _load_measurement_system. Used by the
    Settings tab to populate the 6 Axis Selection combos at startup, by
    _compute_pid_axes below (module load time), and duplicated (rather
    than imported - see AXIS_STEPGEN below for why) in
    REB_Scale_Persist.py and REB_Setup/REB_Generate_Local_Ini.py.
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

    # Defensive against a hand-edited or corrupted file (REBset_v1.ini's
    # own header says "should not be modified directly"): if the same
    # letter somehow ended up on two channels, ignore the persisted data
    # entirely rather than regenerating REB.ini/REB.hal with a duplicate
    # axis letter.
    if len(set(assignments.values())) != len(assignments):
        print("Duplicate letter(s) in persisted channel_assignments - using shipped defaults")
        return dict(CHANNEL_DEFAULT_LETTER)

    return assignments

# Axis id (as used in REB_Settings_v1.ini and the Settings tab spin
# buttons) -> hm2_7i92.0 stepgen channel. Verified against the actual
# "net <axis>-enable => hm2_7i92.0.stepgen.NN.enable" lines in REB.hal
# - NOT the documentation table in REB.ini, which does not match. This
# key is the internal id (see CHANNEL_DEFAULT_LETTER above) - it never
# changes even if the operator reassigns this channel's axis letter.
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
# parameter (motion's own per-joint backlash compensation - see
# REB.ini's [JOINT_n] sections and the axis/joint map in CLAUDE.md).
# NOT the same numbering as AXIS_STEPGEN's hm2 stepgen channel map
# above - joint numbers come from [KINS]JOINTS/trivkins ordering, not
# hm2 wiring.
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

# This session's channel -> axis letter assignment, as persisted at the
# time REB_Generate_Local_Ini.py generated REB.local.hal/REB.local.ini for
# this LinuxCNC launch (see CLAUDE.md). Read once at module import: a
# running session's assignment can't change without a restart anyway (the
# Axis Selection tab shows the same "restart required" popup Measurement
# System/Max Jog Speed already use), so re-reading it later would only
# ever see the same value or a value that doesn't match what's actually
# wired into this session's HAL - re-reading live would be worse, not
# better.
_CHANNEL_ASSIGNMENTS_AT_STARTUP = _read_persisted_channel_assignments()

# Internal id -> this session's actual current axis letter (lowercase).
# Needed anywhere a HAL net/component name in REB.local.hal/
# REB_PostGUI_v1.local.hal embeds the assigned letter (PID_AXES below;
# _clear_ena_override's <letter>-ena-settings-allow/<letter>-ena-flip.set)
# - those two files are regenerated per assignment (see REB_Setup/
# REB_Generate_Local_Ini.py), so e.g. channel 4's PID component is only
# literally "pid.x" while channel 4 is still assigned to X; if the
# operator reassigns it to "A" the live component becomes "pid.a", and a
# halcmd call built from a stale "pid.x" would fail ("no such pin").
# Does NOT apply to gladevcp.*/REBCnfg.* pin names or any Settings-tab/
# main-panel widget id - those stay the internal id forever, see
# CHANNEL_DEFAULT_LETTER above. Sp0/Sp1 aren't reassignable (channels
# 06/07, out of scope for the Axis Selection tab) so they're absent here;
# callers needing a spindle's pid component use PID_SPINDLE_LOOPS instead.
CURRENT_LETTER = {
    internal_id: _CHANNEL_ASSIGNMENTS_AT_STARTUP.get(channel_id, internal_id).lower()
    for internal_id, channel_id in DEFAULT_LETTER_CHANNEL.items()
}

# Internal id -> HAL `pid` component instance driving that axis's PID
# loop right now (see CURRENT_LETTER above for why this can't be a
# static dict, and PID_SPINDLE_LOOPS below for Sp0/Sp1's own loops).
PID_AXES = {internal_id: "pid." + letter for internal_id, letter in CURRENT_LETTER.items()}

# Spindle id -> {"Pos": position-loop component, "Vel": velocity-loop
# component}. The suffix ("Pos"/"Vel") matches the Settings tab widget
# id suffix (e.g. Sp0_Set_P_Pos, Sp0_Set_P_Vel) and the REB_Settings_v1.ini
# block tag ("pid_pos"/"pid_vel").
PID_SPINDLE_LOOPS = {
    "Sp0": {"Pos": "pid.p0", "Vel": "pid.s0"},
    "Sp1": {"Pos": "pid.p1", "Vel": "pid.s1"},
}

# Settings tab field name -> HAL pid component pin name. Order matches
# the P/I/D/FF0/FF1/FF2 column order in REB_Tab_Settings_v1.ui's
# "Stepper Motor Settings" grid.
PID_PARAM_PIN = {
    "P":   "Pgain",
    "I":   "Igain",
    "D":   "Dgain",
    "FF0": "FF0",
    "FF1": "FF1",
    "FF2": "FF2",
}
PID_PARAMS = ("P", "I", "D", "FF0", "FF1", "FF2")

# Max time (seconds) to wait for both Sp0 and Sp1 to report oriented in
# Sp0_Move_Idx_Fwd/Rev's simultaneous-index path (see
# _index_both_spindles_simultaneously) - matches the "Q20" timeout
# already used for the single-spindle M19 path elsewhere in this file.
SIMULTANEOUS_INDEX_TIMEOUT = 20.0

# Default directory Export/Import's file choosers start in.
REBSET_DEFAULT_DIR = os.path.expanduser("~/Documents")

# Axes (not spindles) that have a free-text comment field on the main
# panel, persisted to REB_Settings_v1.ini as each <axis>'s <usercomment>.
COMMENT_AXES = ("X", "Z", "U", "V", "W", "B")

# Leading entry (index 0) in every device-name GtkComboBoxText - the main
# panel's per-axis Comment/Device combos and the Export Settings dialog's
# per-axis Device combos alike - standing in for "nothing chosen yet"
# instead of a blank-looking row. Never treated as a real device name -
# see _combo_selected_device.
DEVICE_COMBO_PLACEHOLDER = "(nothing selected yet)"

# Sp0/Sp1 have no main-panel comment field (see COMMENT_AXES) to default
# the Export Settings dialog's Device combo from, unlike X/Z/U/V/W/B -
# these are the ones Rich actually has, so use them as each spindle's
# default there instead of falling back to DEVICE_COMBO_PLACEHOLDER.
# Only applied if the name is still present in the maintained Device
# Names list at export time - see _run_export_selection_dialog.
SPINDLE_DEFAULT_DEVICE_NAME = {
    "Sp0": "Spindle (Sp0)",
    "Sp1": "Rosette Phaser/Multiplier (Sp1)",
}

# Export_Settings/Import_Settings (see docs/settings_file.md): a
# hand-picked subset of just what's literally on the Settings tab itself
# (each axis's Scale, plus Measurement System), for quick, ad hoc sharing
# of a few values (e.g. "just my B-axis calibration") rather than a full
# profile. Plain XML (matching REB_Settings_v1.ini's own shape). The
# filename itself defaults to "<comment>.REBset_v1.ini", where <comment>
# is the single device name the operator picked in the export selection
# dialog - or, when the selected axes' Device combos name more than one
# distinct device, today's date instead (see Export_Settings) - not
# related to SETTINGS_PATH, which is always the fixed "REBset_v1.ini"
# name with no comment prefix.
EXPORT_EXTENSION = ".REBset_v1.ini"

# Establish connection to command and status channels
c = linuxcnc.command()
s = linuxcnc.stat()

# Temporary diagnostic log for the Sp0/Sp1 indexing checkbox investigation.
# The panel is normally launched with Terminal=false (see the desktop
# launcher), so print() output has nowhere visible to go - this mirrors the
# relevant prints to a file so they can be watched during live testing.
IDX_LOG_PATH = "/home/reuben/linuxcnc/configs/RoseEngineButler/REB_Display/idx_debug.log"

def idx_log(msg):
    print(msg)
    try:
        with open(IDX_LOG_PATH, "a") as f:
            f.write(time.strftime("%H:%M:%S") + " " + msg + "\n")
            f.flush()
    except Exception:
        pass

def _clear_ena_override(axis_id):
    # The *_Set_Ena handlers fire from whichever component owns that
    # axis's ENA button (the main panel, "gladevcp") - but the real,
    # netted *_Ena_Override pin (see REB_PostGUI_v1.hal) lives on the
    # Settings tab's component ("REBCnfg"), a different process. Writing
    # to self.halcomp there would only touch this component's own,
    # unconnected pin of the same name - a no-op. Cross the process
    # boundary via halcmd instead, the same way Sp0_Set_Scale already
    # does in the other direction for *_ENA-light.
    #
    # Once a pin is netted to a signal, halcmd can't "setp" the pin
    # directly ("pin is connected to a signal") - the signal itself has
    # to be set instead, via "halcmd sets". The signal name follows the
    # <letter>-ena-settings-allow convention in REB_PostGUI_v1.hal, where
    # <letter> is the CURRENT axis letter assigned to axis_id's channel
    # (CURRENT_LETTER) - not axis_id itself, which is the fixed internal
    # id and may no longer match the live net name if this channel has
    # been reassigned (see CURRENT_LETTER's own comment). Sp0/Sp1 aren't
    # in CURRENT_LETTER (not reassignable), so they fall back to
    # axis_id.lower(), same as before this feature existed.
    current_letter = CURRENT_LETTER.get(axis_id, axis_id.lower())
    hal_signal = current_letter + "-ena-settings-allow"
    idx_log("_clear_ena_override(" + axis_id + ") -> " + hal_signal)

    # Was the override actually blocking anything? Only true right after
    # a scale change (Set_Scale) forced it False. If it's already True,
    # this ENA press is routine day-to-day toggling and must be left
    # alone below - forcing the panel bit in that case would turn
    # "click to disable" into a no-op.
    was_blocked = False
    try:
        result = subprocess.run(["halcmd", "gets", hal_signal], check=True, capture_output=True, text=True)
        was_blocked = result.stdout.strip().upper() not in ("TRUE", "1")
    except subprocess.CalledProcessError as e:
        idx_log("Error reading " + hal_signal + ": " + str(e.stderr))
    except FileNotFoundError:
        idx_log("halcmd not found - is the LinuxCNC environment sourced?")

    try:
        subprocess.run(["halcmd", "sets", hal_signal, "TRUE"], check=True, capture_output=True, text=True)
        idx_log("Set " + hal_signal + " = TRUE")
    except subprocess.CalledProcessError as e:
        idx_log("Error setting " + hal_signal + ": " + str(e.stderr))
    except FileNotFoundError:
        idx_log("halcmd not found - is the LinuxCNC environment sourced?")

    if was_blocked:
        # The same ENA press that got us here also clocks the flipflop's
        # own toggle bit (REB_PostGUI_v1.hal) via the ordinary clk input -
        # since that bit never moved while the override was blocking
        # things, this click would otherwise flip a previously-on panel
        # state OFF, undoing the very re-enable just requested (this is
        # exactly the "press ENA and nothing happens, need a confusing
        # second press" behavior from live testing). Force the panel bit
        # on deterministically via the flipflop's own set/reset override
        # pins instead of leaving it to toggle-parity guesswork.
        flip_set_pin = current_letter + "-ena-flip.set"
        try:
            subprocess.run(["halcmd", "setp", flip_set_pin, "TRUE"], check=True, capture_output=True, text=True)
            subprocess.run(["halcmd", "setp", flip_set_pin, "FALSE"], check=True, capture_output=True, text=True)
            idx_log("Forced " + current_letter + "-ena-panel ON (override had been blocking)")
        except subprocess.CalledProcessError as e:
            idx_log("Error pulsing " + flip_set_pin + ": " + str(e.stderr))
        except FileNotFoundError:
            idx_log("halcmd not found - is the LinuxCNC environment sourced?")

def _show_no_spindle_enabled_popup(widget):
    dialog = Gtk.MessageDialog(
        transient_for=widget.get_toplevel(),
        flags=0,
        message_type=Gtk.MessageType.WARNING,
        buttons=Gtk.ButtonsType.OK,
        text="No spindle is enabled",
    )
    dialog.run()
    dialog.destroy()

def _show_settings_error(widget, message):
    dialog = Gtk.MessageDialog(
        transient_for=widget.get_toplevel(),
        flags=0,
        message_type=Gtk.MessageType.ERROR,
        buttons=Gtk.ButtonsType.OK,
        text=message,
    )
    dialog.run()
    dialog.destroy()

def _show_restart_required_popup(widget, detail=None):
    dialog = Gtk.MessageDialog(
        transient_for=widget.get_toplevel(),
        flags=0,
        message_type=Gtk.MessageType.INFO,
        buttons=Gtk.ButtonsType.OK,
        text="Restart required",
    )
    dialog.format_secondary_text(
        detail if detail is not None else
        "The Measurement System change will not take effect until you exit "
        "and restart LinuxCNC."
    )
    dialog.run()
    dialog.destroy()

def _save_measurement_system(system):
    '''
    Persists the Measurement System choice ("Metric"/"Imperial") into
    REB_Settings_v1.ini, the same silent, automatic settings file that
    _load_scale_settings/_load_axis_comments already read/write - see
    docs/settings_file.md for why this file (rather than a .settings.ini) is
    the right home for machine-level state like this.
    '''
    try:
        with open(SETTINGS_PATH, "r") as f:
            xml_text = f.read()
    except OSError as e:
        print("Could not read " + SETTINGS_PATH + ": " + str(e))
        return

    if re.search(r'<measurement_system>(Metric|Imperial)</measurement_system>', xml_text):
        new_text, count = re.subn(
            r'<measurement_system>(Metric|Imperial)</measurement_system>',
            "<measurement_system>" + system + "</measurement_system>",
            xml_text,
            count=1
        )
    else:
        new_text, count = re.subn(
            r'(<settings>)',
            r'\1\n    <measurement_system>' + system + '</measurement_system>',
            xml_text,
            count=1
        )

    if count == 0:
        print("Could not find a place to store <measurement_system> in " + SETTINGS_PATH)
        return

    try:
        with open(SETTINGS_PATH, "w") as f:
            f.write(new_text)
        print("Saved measurement_system = " + system)
    except OSError as e:
        print("Could not write " + SETTINGS_PATH + ": " + str(e))

def _save_device_names(names):
    '''
    Persists the maintained device-name list (General tab's Device
    Names box - one name per line, e.g. "Spindle (Sp0)", "Rosette
    Phaser/Multiplier (Sp1)", "Retractor") into REBset_v1.ini as a
    <device_names><name>...</name>...</device_names> block, replacing
    the whole block each time rather than patching individual <name>
    entries - simpler than tracking adds/removes/reorders across saves,
    and the block is small enough that a full rewrite costs nothing.
    escape()/unescape() (already imported for axis comments) keep any
    stray XML-special characters in a name (&, <, >) from corrupting
    the file.
    '''
    try:
        with open(SETTINGS_PATH, "r") as f:
            xml_text = f.read()
    except OSError as e:
        print("Could not read " + SETTINGS_PATH + ": " + str(e))
        return

    lines = ["    <device_names>"]
    for name in names:
        lines.append("        <name>" + escape(name) + "</name>")
    lines.append("    </device_names>")
    block = "\n".join(lines)

    # [ \t]* eats any pre-existing indentation on the <device_names> line
    # itself - otherwise each rewrite stacks the block's own 4-space
    # indent onto whatever whitespace was already sitting there,
    # growing a little further out every time this runs.
    pattern = re.compile(r'[ \t]*<device_names>.*?</device_names>', re.DOTALL)
    if pattern.search(xml_text):
        new_text, count = pattern.subn(lambda m: block, xml_text, count=1)
    else:
        new_text, count = re.subn(
            r'(<settings>)',
            lambda m: m.group(1) + "\n" + block,
            xml_text,
            count=1
        )

    if count == 0:
        print("Could not find a place to store <device_names> in " + SETTINGS_PATH)
        return

    try:
        with open(SETTINGS_PATH, "w") as f:
            f.write(new_text)
        print("Saved " + str(len(names)) + " device name(s)")
    except OSError as e:
        print("Could not write " + SETTINGS_PATH + ": " + str(e))

def _read_persisted_device_names():
    '''
    Reads the persisted device-name list straight from SETTINGS_PATH
    (REBset_v1.ini's <device_names> block) - the on-disk counterpart to
    HandlerClass._read_device_names, which reads the live Settings tab's
    Device_Names GtkTextView instead. Used wherever a component needs
    this list but doesn't own that widget - e.g. the main panel
    populating each axis's Comment combo box at startup, since the main
    panel and Settings tab are separate gladevcp processes with no live
    IPC between them (see CLAUDE.md). Returns [] if the file can't be
    read or has no <device_names> block.
    '''
    try:
        with open(SETTINGS_PATH, "r") as f:
            xml_text = f.read()
    except OSError as e:
        print("Could not read " + SETTINGS_PATH + ": " + str(e))
        return []

    match = re.search(r'<device_names>(.*?)</device_names>', xml_text, re.DOTALL)
    if not match:
        return []
    return [unescape(n) for n in re.findall(r'<name>(.*?)</name>', match.group(1), re.DOTALL)]

def _read_persisted_axis_comment(axis_id, xml_text):
    '''
    Extracts one axis's persisted <usercomment> value out of an
    already-read SETTINGS_PATH xml_text. Shared by _load_axis_comments
    (main panel, restoring its own Device combos at startup) and
    _run_export_selection_dialog (Settings tab, defaulting each axis's
    Export dialog Device combo to whatever's currently set on the main
    panel) - REBset_v1.ini's <usercomment> is the only channel between
    those two separate gladevcp processes (see CLAUDE.md). Returns ""
    if the axis or its <usercomment> isn't found.
    '''
    match = re.search(
        r'<axis\s+id="' + re.escape(axis_id) + r'">\s*<scale>-?[\d.]+</scale>\s*'
        r'<usercomment>(.*?)</usercomment>',
        xml_text,
        re.DOTALL
    )
    return unescape(match.group(1)) if match else ""

def _combo_selected_device(combo):
    '''
    Returns the real selected value of a device-name GtkComboBoxText
    (empty string if the leading DEVICE_COMBO_PLACEHOLDER entry - index
    0 - is what's active), rather than combo.get_active_text() directly,
    which would return the placeholder's own display text. Index-based
    rather than a string comparison against DEVICE_COMBO_PLACEHOLDER so
    this keeps working even if that text is ever changed - index 0 is
    always the placeholder, in both places these combos get built
    (_load_axis_comments, _run_export_selection_dialog).
    '''
    return combo.get_active_text() if combo.get_active() > 0 else ""

def _save_max_jog_speed(value):
    '''
    Persists the Max Jog Speed choice into REB_Settings_v1.ini, the same
    silent, automatic settings file _save_measurement_system already
    writes <measurement_system> into.
    '''
    try:
        with open(SETTINGS_PATH, "r") as f:
            xml_text = f.read()
    except OSError as e:
        print("Could not read " + SETTINGS_PATH + ": " + str(e))
        return

    value_text = "%.4f" % value

    if re.search(r'<max_jog_speed>[0-9.eE+-]+</max_jog_speed>', xml_text):
        new_text, count = re.subn(
            r'<max_jog_speed>[0-9.eE+-]+</max_jog_speed>',
            "<max_jog_speed>" + value_text + "</max_jog_speed>",
            xml_text,
            count=1
        )
    else:
        new_text, count = re.subn(
            r'(<settings>)',
            r'\1\n    <max_jog_speed>' + value_text + '</max_jog_speed>',
            xml_text,
            count=1
        )

    if count == 0:
        print("Could not find a place to store <max_jog_speed> in " + SETTINGS_PATH)
        return

    try:
        with open(SETTINGS_PATH, "w") as f:
            f.write(new_text)
        print("Saved max_jog_speed = " + value_text)
    except OSError as e:
        print("Could not write " + SETTINGS_PATH + ": " + str(e))

# Settings tab jog-speed-grid widget id -> (REB_Settings_v1.ini tag,
# fallback default matching REB.ini's own shipped value). Mirrors
# MAX_LINEAR_VELOCITY/<max_jog_speed> above, generalized to the other
# [DISPLAY]/[TRAJ] jog-speed values (see REB_Setup/REB_Generate_Local_Ini.py
# for the overlay side - like Max Jog Speed, each of these patches ALL
# occurrences of its ini key, both [DISPLAY] (jog slider) and [TRAJ]
# (trajectory-planner ceiling), since REB.ini ships the same value in
# both places for these keys - unlike MAX_ANGULAR_VELOCITY historically,
# where [TRAJ] carried a much larger, effectively-unlimited value; this
# was a deliberate choice to unify them under one operator-facing
# control rather than leave two different meanings behind one label).
VELOCITY_SETTINGS = {
    "Default_Linear_Velocity":  ("default_linear_velocity",  0.250000),
    "Min_Linear_Velocity":      ("min_linear_velocity",      0.016670),
    "Max_Angular_Velocity":     ("max_angular_velocity",     1.000000),
    "Default_Angular_Velocity": ("default_angular_velocity", 12.000000),
    "Min_Angular_Velocity":     ("min_angular_velocity",     1.666667),
}

def _save_velocity_setting(tag, value):
    '''
    Persists one of VELOCITY_SETTINGS' values into REB_Settings_v1.ini -
    generic version of _save_max_jog_speed above, parameterized by tag
    name since these five all follow the exact same shape.
    '''
    try:
        with open(SETTINGS_PATH, "r") as f:
            xml_text = f.read()
    except OSError as e:
        print("Could not read " + SETTINGS_PATH + ": " + str(e))
        return

    value_text = "%.6f" % value

    if re.search(r'<' + tag + r'>[0-9.eE+-]+</' + tag + r'>', xml_text):
        new_text, count = re.subn(
            r'<' + tag + r'>[0-9.eE+-]+</' + tag + r'>',
            "<" + tag + ">" + value_text + "</" + tag + ">",
            xml_text,
            count=1
        )
    else:
        new_text, count = re.subn(
            r'(<settings>)',
            r'\1\n    <' + tag + '>' + value_text + '</' + tag + '>',
            xml_text,
            count=1
        )

    if count == 0:
        print("Could not find a place to store <" + tag + "> in " + SETTINGS_PATH)
        return

    try:
        with open(SETTINGS_PATH, "w") as f:
            f.write(new_text)
        print("Saved " + tag + " = " + value_text)
    except OSError as e:
        print("Could not write " + SETTINGS_PATH + ": " + str(e))

# The indexing Fwd/Rev handlers block on c.wait_complete() for as long as
# each M19 takes to converge (or time out), which otherwise leaves the UI
# looking unresponsive with no feedback that anything is happening.
def _set_busy_cursor(widget, busy):
    win = widget.get_toplevel().get_window()
    if win is None:
        return
    win.set_cursor(Gdk.Cursor.new_from_name(win.get_display(), "wait") if busy else None)
    # Force the cursor change to actually paint before the blocking MDI
    # calls take over the main loop.
    while Gtk.events_pending():
        Gtk.main_iteration()

# Used to show a plain HAL_Button as depressed/darkened while a move or
# an operation is active (X_Idx_Minus/Plus, Sp0_Move_Fwd/Rev).
# Deliberately NOT done via HAL_ToggleButton.set_active(): a real
# GtkToggleButton also flips its own active state on click or on the
# theme's native (and here, barely visible) "checked" rendering, and
# for the blocking X_Idx_Minus/Plus case specifically, the
# release-driven auto-flip happens right after our own code sets it
# back to False - undoing it and leaving the button stuck depressed
# (confirmed live). A custom CSS class on a plain, non-toggle button has
# no such built-in behavior to fight - only this code ever touches it,
# and the darkened background makes the state obvious regardless of
# theme.
_DEPRESS_CSS = b"""
button.reb-depressed,
button.reb-depressed:hover,
button.reb-depressed:focus,
button.reb-depressed:active {
    background-color: shade(@theme_bg_color, 0.6);
    background-image: none;
    box-shadow: inset 2px 2px 4px rgba(0,0,0,0.6), inset -1px -1px 2px rgba(255,255,255,0.15);
}
"""

def _install_depress_css():
    try:
        provider = Gtk.CssProvider()
        provider.load_from_data(_DEPRESS_CSS)
        screen = Gdk.Screen.get_default()
        Gtk.StyleContext.add_provider_for_screen(
            screen,
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        idx_log("_install_depress_css OK, screen=" + str(screen))
    except Exception as e:
        idx_log("_install_depress_css FAILED: " + str(e))

def _set_depressed(widget, depressed):
    ctx = widget.get_style_context()
    was_depressed = ctx.has_class("reb-depressed")
    if depressed:
        ctx.add_class("reb-depressed")
    else:
        ctx.remove_class("reb-depressed")
    # Only log actual transitions - the Run Operation poll calls this
    # every 100ms regardless of whether anything changed, which was
    # flooding idx_debug.log and triggering the monitor's own rate
    # limiting.
    if was_depressed != depressed:
        idx_log("_set_depressed(" + Gtk.Buildable.get_name(widget) + ", " + str(depressed)
                + ") classes=" + str(ctx.list_classes()))
    # Force the style change to actually paint now, the same reason
    # _set_busy_cursor does this - callers that bracket a blocking MDI
    # call (X_Idx_Minus/Plus) would otherwise freeze the main loop
    # before GTK gets a chance to repaint the new class, so the darkened
    # look barely shows (confirmed live: "hardly noticeable"). Periodic
    # callers (the Run Operation poll) don't strictly need this - they
    # get repainted on the next idle cycle regardless - but it's
    # harmless there too.
    while Gtk.events_pending():
        Gtk.main_iteration()

class HandlerClass:
    '''
    class with gladevcp callback handlers
    '''

    def on_button_press(self,widget,data=None):
        '''
        a callback method
        parameters are:
            the generating object instance, likte a GtkButton instance
            user data passed if any - this is currently unused but
            the convention should be retained just in case
        '''
        print ("on_button_press called")
        self.nhits += 1
        self.builder.get_object('hits').set_label("Hits: %d" % (self.nhits))

    def scroll_entries(self,widget,event):
        '''
        Lets the mouse scroll wheel scroll the viewport (e.g. on the
        Usage tab) instead of the scroll being captured by a child
        widget such as a spin button under the cursor.
        '''
        adj = widget.get_vadjustment()
        if adj is None:
            return False

        increment = adj.get_step_increment()
        lower = adj.get_lower()
        upper = adj.get_upper() - adj.get_page_size()

        if event.direction == Gdk.ScrollDirection.UP:
            adj.set_value(max(lower, adj.get_value() - increment))
            return True
        elif event.direction == Gdk.ScrollDirection.DOWN:
            adj.set_value(min(upper, adj.get_value() + increment))
            return True
        elif event.direction == Gdk.ScrollDirection.SMOOTH:
            valid, dx, dy = event.get_scroll_deltas()
            if valid:
                new_value = adj.get_value() + (dy * increment)
                adj.set_value(max(lower, min(upper, new_value)))
            return True

        return False

    def _redirect_scroll_to_viewport(self, widget, event):
        '''
        scroll_entries above only fires for "windowless" widgets (Labels,
        empty grid cells) - anything with its own GdkWindow, like a
        GtkSpinButton or GtkComboBox, receives a scroll-event directly
        and never lets it reach the viewport at all, since GTK delivers
        the event straight to the most specific window under the
        pointer rather than bubbling it up through the container
        hierarchy. That widget's own built-in class handler then runs
        its default scroll behavior (increment/decrement a spin button,
        change a combo box's selection) instead.

        With the Settings tab's grid now almost entirely full of spin
        buttons (Scale + PID gains), that left almost no surface left to
        actually scroll the page from - hence wiring this onto every
        spin button/combo box individually (see
        _install_viewport_scroll_redirect) rather than relying on
        scroll_entries alone. A broader attempt at wiring *every* widget
        in the subtree (labels, grids, boxes) was tried and made things
        worse - it broke scrolling over spin buttons too, for reasons
        not fully understood - so this deliberately stays scoped to just
        the input widgets. Settled behavior: scrolling works over spin
        buttons/combo boxes; it does not work over the surrounding
        labels/empty grid space.
        '''
        viewport = widget.get_ancestor(Gtk.Viewport)
        if viewport is None:
            return False
        return self.scroll_entries(viewport, event)

    def _install_viewport_scroll_redirect(self, container):
        '''
        Recursively wires _redirect_scroll_to_viewport onto every spin
        button/combo box under container (see that method's docstring
        for why). Called once from __init__ on the Settings tab's own
        scrollable viewport - harmless/no-op everywhere else, since
        every other tab/panel's viewport (if it has one at all) has far
        fewer, more sparsely-packed input widgets and get_children()
        simply returns less to walk.
        '''
        for child in container.get_children():
            if isinstance(child, (Gtk.SpinButton, Gtk.ComboBox)):
                child.connect("scroll-event", self._redirect_scroll_to_viewport)
            if isinstance(child, Gtk.Container):
                self._install_viewport_scroll_redirect(child)

    def _set_checkbox_active(self, widget_id, active):
        '''
        Forces a checkbox to the given state. Only the main panel
        component has these widgets - every other tab/panel finds
        the widget missing and no-ops.

        Deferred via GLib.idle_add (see __init__) rather than set
        directly during __init__: the checkbox doesn't reliably end up
        checked from the .ui file's active="True" alone once the panel
        is actually interactive (confirmed live), so this runs after
        gladevcp's own startup sequence has settled instead of risking
        being overwritten by whatever resets it otherwise.
        '''
        widget = self.builder.get_object(widget_id)
        if widget is not None:
            widget.set_active(active)
        return False

    def _sync_run_operation_buttons(self):
        '''
        Keeps the Run Operation tab's Fwd/Rev buttons visually depressed/
        darkened for as long as the spindle is actually running in that
        direction, reading the real HAL state (spindle.0.forward /
        spindle.0.reverse) rather than just whatever the last click did -
        so the button reflects reality even if a move ends some other
        way (e.g. M5 from elsewhere, a fault, etc). Runs on a timer
        rather than once, since gladevcp has no built-in live binding
        for an arbitrary read-only HAL pin like this (unlike HAL_LED,
        which is built for exactly this but doesn't give a "look
        pressed" visual).

        Fwd is tied to spindle.0.reverse and Rev to spindle.0.forward -
        backwards-looking, but intentional: Sp0_Move_Fwd/Sp0_Move_Rev
        send M4/M3 respectively (see those functions' docstrings for why
        - an empirically-verified swap fixing an unexplained direction
        flip), so spindle.0.reverse is what actually goes TRUE while Fwd
        is spinning. This mirrors that same swap so the highlighted
        button still matches the one physically pressed.

        Uses _set_depressed (a plain HAL_Button plus a CSS class), not
        HAL_ToggleButton.set_active() - the theme's native "checked"
        look for a toggle button wasn't visibly different enough to
        read as "pressed" (confirmed live: hover-highlight only, no
        visible change on click).

        Only the main panel component has these widgets; every other
        tab/panel finds them missing and this becomes a no-op (but the
        timer itself, once started, keeps calling it - see __init__).
        '''
        fwd = self.builder.get_object('Sp0_Move_Fwd')
        rev = self.builder.get_object('Sp0_Move_Rev')
        if fwd is None or rev is None:
            return False

        _set_depressed(fwd, bool(hal.get_value('spindle.0.reverse')))
        _set_depressed(rev, bool(hal.get_value('spindle.0.forward')))
        return True

    def _load_scale_settings(self):
        '''
        Reads persisted axis scale values from REB_Settings_v1.ini
        (an XML file living alongside this script) and applies them
        to the Settings tab's spin buttons and the real stepgen
        position-scale HAL pins.

        Only runs in the component that actually owns the Settings
        tab's spin buttons (X_Set_Scale etc.) - every other tab/panel
        also using REB_main.py will find that widget missing and
        return immediately.
        '''
        if self.builder.get_object("X_Set_Scale") is None:
            return

        try:
            with open(SETTINGS_PATH, "r") as f:
                xml_text = f.read()
        except OSError as e:
            print("Could not read " + SETTINGS_PATH + ": " + str(e))
            return

        for axis_id, stepgen_ch in AXIS_STEPGEN.items():
            match = re.search(
                r'<axis\s+id="' + re.escape(axis_id) + r'">\s*<scale>(-?[\d.]+)</scale>',
                xml_text
            )
            if not match:
                print("No stored scale found for axis " + axis_id
                      + " in " + SETTINGS_PATH)
                continue

            value = float(match.group(1))

            widget = self.builder.get_object(axis_id + "_Set_Scale")
            if widget is not None:
                widget.set_value(value)

            hal_pin = "hm2_7i92.0.stepgen." + stepgen_ch + ".position-scale"
            try:
                subprocess.run(
                    ["halcmd", "setp", hal_pin, str(value)],
                    check=True,
                    capture_output=True,
                    text=True
                )
                print("Restored " + hal_pin + " = " + str(value))
            except subprocess.CalledProcessError as e:
                print("Error restoring " + hal_pin + ": " + e.stderr)
            except FileNotFoundError:
                print("halcmd not found - is the LinuxCNC environment sourced?")

    def _load_pid_settings(self):
        '''
        Reads persisted P/I/D/FF0/FF1/FF2 gains from REB_Settings_v1.ini
        (each axis's <pid> block, or <pid_pos>/<pid_vel> for the two
        spindle loops) and applies them to the Settings tab's PID spin
        buttons and the live pid.* HAL gain pins - mirrors
        _load_scale_settings above for the axis stepgen scales.
        REB_Scale_Persist.py is what writes these back into
        REB_Settings_v1.ini at shutdown, the same as it already does
        for scale.

        Only runs in the component that actually owns the Settings
        tab's PID spin buttons (X_Set_P etc.) - every other tab/panel
        also using REB_main.py will find that widget missing and
        return immediately.
        '''
        if self.builder.get_object("X_Set_P") is None:
            return

        try:
            with open(SETTINGS_PATH, "r") as f:
                xml_text = f.read()
        except OSError as e:
            print("Could not read " + SETTINGS_PATH + ": " + str(e))
            return

        def apply(axis_id, block_tag, hal_component, widget_id_for_param):
            '''
            widget_id_for_param(param) builds the Settings tab widget id
            for a given P/I/D/FF0/FF1/FF2 param - axes and spindle loops
            put their disambiguating suffix in different places
            (X_Set_P vs Sp0_Set_P_Pos), so the caller supplies this
            rather than apply() assuming one fixed naming shape.
            '''
            axis_match = re.search(
                r'<axis\s+id="' + re.escape(axis_id) + r'">(.*?)</axis>',
                xml_text, re.DOTALL
            )
            if not axis_match:
                print("No <axis id=\"" + axis_id + "\"> entry found in " + SETTINGS_PATH)
                return

            block_match = re.search(
                r'<' + block_tag + r'>(.*?)</' + block_tag + r'>',
                axis_match.group(1), re.DOTALL
            )
            if not block_match:
                print("No <" + block_tag + "> entry found for axis " + axis_id
                      + " in " + SETTINGS_PATH)
                return

            for param in PID_PARAMS:
                widget_id = widget_id_for_param(param)

                param_match = re.search(
                    r'<' + param + r'>(-?[\d.]+)</' + param + r'>',
                    block_match.group(1)
                )
                if not param_match:
                    print("No stored " + param + " found for " + widget_id
                          + " in " + SETTINGS_PATH)
                    continue

                value = param_match.group(1)
                widget = self.builder.get_object(widget_id)
                if widget is not None:
                    widget.set_value(float(value))

                hal_pin = hal_component + "." + PID_PARAM_PIN[param]
                try:
                    subprocess.run(
                        ["halcmd", "setp", hal_pin, value],
                        check=True,
                        capture_output=True,
                        text=True
                    )
                    print("Restored " + hal_pin + " = " + value)
                except subprocess.CalledProcessError as e:
                    print("Error restoring " + hal_pin + ": " + e.stderr)
                except FileNotFoundError:
                    print("halcmd not found - is the LinuxCNC environment sourced?")

        for axis_id, component in PID_AXES.items():
            apply(axis_id, "pid", component,
                  lambda param, axis_id=axis_id: axis_id + "_Set_" + param)

        for spindle_id, loops in PID_SPINDLE_LOOPS.items():
            for suffix, component in loops.items():
                block_tag = "pid_pos" if suffix == "Pos" else "pid_vel"
                apply(spindle_id, block_tag, component,
                      lambda param, spindle_id=spindle_id, suffix=suffix:
                          spindle_id + "_Set_" + param + "_" + suffix)

    def _load_backlash_settings(self):
        '''
        Reads persisted axis/spindle backlash values from
        REB_Settings_v1.ini (each axis's <backlash> element) and applies
        them to the Settings tab's Backlash spin buttons and the live
        joint.N.backlash HAL parameters - mirrors _load_scale_settings
        above. REB_Scale_Persist.py is what writes these back into
        REB_Settings_v1.ini at shutdown, the same as it already does for
        scale and PID gains.

        Only runs in the component that actually owns the Settings tab's
        Backlash spin buttons (X_Set_Backlash etc.) - every other tab/
        panel also using REB_main.py will find that widget missing and
        return immediately.
        '''
        if self.builder.get_object("X_Set_Backlash") is None:
            return

        try:
            with open(SETTINGS_PATH, "r") as f:
                xml_text = f.read()
        except OSError as e:
            print("Could not read " + SETTINGS_PATH + ": " + str(e))
            return

        for axis_id, joint_num in JOINT_NUMBER.items():
            axis_match = re.search(
                r'<axis\s+id="' + re.escape(axis_id) + r'">(.*?)</axis>',
                xml_text, re.DOTALL
            )
            if not axis_match:
                print("No <axis id=\"" + axis_id + "\"> entry found in " + SETTINGS_PATH)
                continue

            match = re.search(r'<backlash>(-?[\d.]+)</backlash>', axis_match.group(1))
            if not match:
                print("No stored backlash found for axis " + axis_id
                      + " in " + SETTINGS_PATH)
                continue

            value = float(match.group(1))

            widget = self.builder.get_object(axis_id + "_Set_Backlash")
            if widget is not None:
                widget.set_value(value)

            hal_pin = "joint." + str(joint_num) + ".backlash"
            try:
                subprocess.run(
                    ["halcmd", "setp", hal_pin, str(value)],
                    check=True,
                    capture_output=True,
                    text=True
                )
                print("Restored " + hal_pin + " = " + str(value))
            except subprocess.CalledProcessError as e:
                print("Error restoring " + hal_pin + ": " + e.stderr)
            except FileNotFoundError:
                print("halcmd not found - is the LinuxCNC environment sourced?")

    def _load_axis_comments(self):
        '''
        Populates each axis's comment combo box (X_Comment etc., on the
        main REB_Panel) with the persisted device-name list
        (_read_persisted_device_names - the on-disk counterpart to the
        General tab's live Device Names widget, which this component
        doesn't have access to, being a separate gladevcp process - see
        CLAUDE.md) plus a leading DEVICE_COMBO_PLACEHOLDER entry for
        "nothing chosen yet", then selects whichever entry matches that
        axis's persisted
        comment from REB_Settings_v1.ini. This is what constrains a
        comment to one of the maintained device names rather than free
        text - GtkComboBoxText (no entry) only ever offers what's been
        appended to it.

        Guarded by _applying_axis_comments so combo.set_active() below
        doesn't trigger X_Comment/etc.'s own "changed" handler and
        immediately re-save the value being loaded (same pattern as
        _load_measurement_system's _applying_measurement_system).

        Only runs in the component that actually owns these widgets -
        every other tab/panel also using REB_main.py will find them
        missing and return immediately.
        '''
        if self.builder.get_object("X_Comment") is None:
            return

        try:
            with open(SETTINGS_PATH, "r") as f:
                xml_text = f.read()
        except OSError as e:
            print("Could not read " + SETTINGS_PATH + ": " + str(e))
            return

        device_names = _read_persisted_device_names()

        self._applying_axis_comments = True
        try:
            for axis_id in COMMENT_AXES:
                widget = self.builder.get_object(axis_id + "_Comment")
                if widget is None:
                    continue

                widget.remove_all()
                widget.append_text(DEVICE_COMBO_PLACEHOLDER)
                for name in device_names:
                    widget.append_text(name)

                stored = _read_persisted_axis_comment(axis_id, xml_text)
                if not stored:
                    print("No stored comment found for axis " + axis_id
                          + " in " + SETTINGS_PATH)

                try:
                    widget.set_active(device_names.index(stored) + 1 if stored else 0)
                except ValueError:
                    # Stored comment doesn't match any current device
                    # name (e.g. free text from before this became a
                    # constrained dropdown, or the device-name list
                    # changed since it was picked) - fall back to the
                    # placeholder entry rather than silently keeping an
                    # invalid value selected.
                    print(axis_id + " comment \"" + stored
                          + "\" doesn't match any device name - leaving blank")
                    widget.set_active(0)
        finally:
            self._applying_axis_comments = False

    def _autosave_axis_comments(self):
        '''
        Polling backstop for the comment combo boxes - see the
        GLib.timeout_add call in __init__ for why this exists alongside
        (not instead of) X_Comment/Z_Comment/etc.'s "changed" signal.

        Only the main panel component has these widgets; every other
        tab/panel finds them missing and returning False here cancels
        the timer entirely (same pattern as _sync_run_operation_buttons).
        '''
        if self.builder.get_object("X_Comment") is None:
            return False

        for axis_id in COMMENT_AXES:
            widget = self.builder.get_object(axis_id + "_Comment")
            if widget is None:
                continue

            text = _combo_selected_device(widget)
            if text != self._last_saved_axis_comment.get(axis_id):
                self._save_axis_comment(axis_id, text)
                self._last_saved_axis_comment[axis_id] = text

        return True

    def _apply_measurement_system_labels(self, system):
        '''
        Sets the feed-rate/indexing-distance unit labels on the main panel
        (X/Z/U/V/W's "in / min" and "in" labels) and the scale unit labels
        on the Settings tab (X/Z/U/V/W's "pulses / in" labels) to match
        the given system ("Metric" or "Imperial"). Whichever labels this
        component doesn't own (builder.get_object returns None) are
        silently skipped - same no-op-in-the-wrong-component pattern as
        _load_scale_settings/_load_axis_comments.
        '''
        if system == "Metric":
            feed_uom, dist_uom, scale_uom = "mm / min", "mm", "pulses / mm"
        else:
            feed_uom, dist_uom, scale_uom = "in / min", "in", "pulses / in"

        for axis_id in LINEAR_AXES:
            feed_label = self.builder.get_object(axis_id + "_Feed_UOM")
            if feed_label is not None:
                feed_label.set_text(feed_uom)

            dist_label = self.builder.get_object(axis_id + "_IdxDist_UOM")
            if dist_label is not None:
                dist_label.set_text(dist_uom)

            scale_label = self.builder.get_object(axis_id + "_Scale_UOM")
            if scale_label is not None:
                scale_label.set_text(scale_uom)

    def _load_measurement_system(self):
        '''
        Reads the persisted Measurement System ("Metric"/"Imperial", default
        "Imperial" if absent - matching REB.ini's shipped inch/INCH default)
        from REB_Settings_v1.ini, applies it to the Settings tab's combo box
        (if this component owns it) and to whichever unit-of-measure labels
        this component owns (see _apply_measurement_system_labels).
        '''
        system = "Imperial"
        try:
            with open(SETTINGS_PATH, "r") as f:
                xml_text = f.read()
            match = re.search(r'<measurement_system>(Metric|Imperial)</measurement_system>', xml_text)
            if match:
                system = match.group(1)
        except OSError as e:
            print("Could not read " + SETTINGS_PATH + ": " + str(e))

        combo = self.builder.get_object("Measurement_System")
        if combo is not None:
            self._applying_measurement_system = True
            combo.set_active(0 if system == "Metric" else 1)
            self._applying_measurement_system = False

        self._apply_measurement_system_labels(system)

    def _load_device_names(self):
        '''
        Reads the persisted device-name list (REBset_v1.ini's
        <device_names> block) and applies it to the General tab's
        Device Names GtkTextView, one name per line - mirrors
        _load_measurement_system above. No-ops outside the component
        that owns that widget.
        '''
        view = self.builder.get_object("Device_Names")
        if view is None:
            return

        names = _read_persisted_device_names()

        self._applying_device_names = True
        view.get_buffer().set_text("\n".join(names))
        self._applying_device_names = False

    def _read_device_names(self):
        '''
        Reads the maintained device-name list straight from the live
        Device Names widget (kept in sync with REBset_v1.ini by
        Device_Names_Changed on every edit) rather than re-reading the
        file - used by _run_export_selection_dialog to populate each
        axis's comment dropdown. Blank/whitespace-only lines are
        dropped. Returns [] if this component doesn't own the widget.
        '''
        view = self.builder.get_object("Device_Names")
        if view is None:
            return []
        buf = view.get_buffer()
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
        return [line.strip() for line in text.splitlines() if line.strip()]

    def _rebuild_all_channel_combo_items(self):
        '''
        Populates every Channel_0N_Axis combo with the full letter pool
        (AXIS_SELECTION_LETTERS) and reselects that combo's own current
        letter. Every letter is always offered here - this used to
        filter out whatever letter another channel already held
        (uniqueness by construction), but Rich asked for that removed:
        any channel should be freely selectable to any letter, with
        duplicates flagged live instead (see _update_duplicate_warnings)
        and only actually blocked from being persisted, not from being
        picked in the first place.

        Called both by _load_channel_assignments (startup) and by
        Channel_0N_Axis_Changed itself (every time one combo's choice
        changes). Also refreshes each row's Type label (Channel_0N_Type)
        to match its combo's current letter - Type is a property of
        whichever letter is assigned right now, not of the channel, so
        it has to be recomputed here rather than set once. No-ops
        outside the component that owns these widgets.
        '''
        if self.builder.get_object("Channel_00_Axis") is None:
            return

        for channel_id in CHANNEL_DEFAULT_LETTER:
            combo = self.builder.get_object("Channel_" + channel_id + "_Axis")
            if combo is None:
                continue

            current = self._channel_assignments[channel_id]

            combo.remove_all()
            for letter in AXIS_SELECTION_LETTERS:
                combo.append_text(letter)
            combo.set_active(AXIS_SELECTION_LETTERS.index(current))

            type_label = self.builder.get_object("Channel_" + channel_id + "_Type")
            if type_label is not None:
                type_label.set_text(_axis_type_for_letter(current).capitalize())

    def _update_duplicate_warnings(self):
        '''
        Flags every channel whose currently-selected letter is also
        selected by at least one other channel, by setting its
        Channel_0N_Warning label to a red "Duplicate!" notice (cleared
        for channels with no conflict). This is the live feedback that
        replaced uniqueness-by-construction (see
        _rebuild_all_channel_combo_items) - a duplicate can now be
        picked freely, it's just flagged immediately rather than
        rejected. Channel_0N_Axis_Changed uses this method's return
        value to decide whether the assignment is safe to persist -
        actually saving/showing the restart notice is refused for as
        long as any duplicate remains, resuming automatically on
        whichever change clears it.

        Returns True if at least one duplicate exists (False, and every
        warning cleared, if the assignment is fully valid). No-ops
        (returns False) outside the component that owns these widgets.
        '''
        if self.builder.get_object("Channel_00_Axis") is None:
            return False

        letter_counts = {}
        for letter in self._channel_assignments.values():
            letter_counts[letter] = letter_counts.get(letter, 0) + 1

        any_duplicate = False
        for channel_id, letter in self._channel_assignments.items():
            warning = self.builder.get_object("Channel_" + channel_id + "_Warning")
            if warning is None:
                continue
            if letter_counts[letter] > 1:
                warning.set_markup('<span foreground="red" weight="bold">Duplicate!</span>')
                any_duplicate = True
            else:
                warning.set_text("")

        return any_duplicate

    def _load_channel_assignments(self):
        '''
        Reads the persisted channel -> axis letter assignment
        (REBset_v1.ini's <channel_assignments> block) and populates the
        Axis Selection tab's six combos, if this component owns them.
        No-ops outside that component, same pattern as
        _load_measurement_system.
        '''
        if self.builder.get_object("Channel_00_Axis") is None:
            return

        self._channel_assignments = _read_persisted_channel_assignments()

        self._applying_channel_assignments = True
        self._rebuild_all_channel_combo_items()
        self._applying_channel_assignments = False

        # _read_persisted_channel_assignments already falls back to the
        # shipped defaults rather than ever returning a duplicate, so
        # this should always clear every warning - called anyway so the
        # tab's own state stays consistent if that ever changes.
        self._update_duplicate_warnings()

    def _load_max_jog_speed(self):
        '''
        Reads the persisted Max Jog Speed (default 1.0, matching REB.ini's
        shipped [TRAJ]/[DISPLAY] MAX_LINEAR_VELOCITY) from
        REB_Settings_v1.ini and applies it to the Settings tab's spin
        button, if this component owns it - same no-op-in-the-wrong-
        component pattern as _load_measurement_system.
        '''
        value = 1.0
        try:
            with open(SETTINGS_PATH, "r") as f:
                xml_text = f.read()
            match = re.search(r'<max_jog_speed>([0-9.eE+-]+)</max_jog_speed>', xml_text)
            if match:
                value = float(match.group(1))
        except OSError as e:
            print("Could not read " + SETTINGS_PATH + ": " + str(e))

        spin = self.builder.get_object("Max_Jog_Speed")
        if spin is not None:
            self._applying_max_jog_speed = True
            spin.set_value(value)
            self._applying_max_jog_speed = False

    def _load_velocity_settings(self):
        '''
        Reads each of VELOCITY_SETTINGS' persisted values from
        REB_Settings_v1.ini (default to REB.ini's own shipped value if
        never persisted) and applies them to their Settings tab spin
        buttons, if this component owns them - mirrors
        _load_max_jog_speed above, generalized to all five at once under
        one shared guard flag (they're only ever loaded together, so one
        flag covering the whole batch is enough - no risk of one load
        call falsely suppressing a genuine edit to a different widget).
        '''
        try:
            with open(SETTINGS_PATH, "r") as f:
                xml_text = f.read()
        except OSError as e:
            print("Could not read " + SETTINGS_PATH + ": " + str(e))
            xml_text = ""

        self._applying_velocity_settings = True
        try:
            for widget_id, (tag, default) in VELOCITY_SETTINGS.items():
                value = default
                match = re.search(r'<' + tag + r'>([0-9.eE+-]+)</' + tag + r'>', xml_text)
                if match:
                    value = float(match.group(1))

                spin = self.builder.get_object(widget_id)
                if spin is not None:
                    spin.set_value(value)
        finally:
            self._applying_velocity_settings = False

    def _save_axis_comment(self, axis_id, text):
        '''
        Writes a single axis's comment back into REB_Settings_v1.ini,
        updating that axis's <usercomment> value - or inserting one
        right after its <scale> element if this axis doesn't have one
        yet. Every existing REB_Settings_v1.ini predates <usercomment>
        entirely (confirmed live: none of X/Z/B/U/V/W had one), so
        without this fallback every comment save was a silent no-op
        forever - there was nothing already there to update. Called
        from each comment Entry's focus-out-event handler below.
        '''
        try:
            with open(SETTINGS_PATH, "r") as f:
                xml_text = f.read()
        except OSError as e:
            print("Could not read " + SETTINGS_PATH + ": " + str(e))
            return

        escaped = escape(text)

        update_pattern = (
            r'(<axis\s+id="' + re.escape(axis_id) + r'">\s*<scale>-?[\d.]+</scale>\s*<usercomment>)'
            r'.*?'
            r'(</usercomment>)'
        )
        new_text, count = re.subn(
            update_pattern,
            lambda m: m.group(1) + escaped + m.group(2),
            xml_text,
            count=1,
            flags=re.DOTALL
        )

        if count == 0:
            insert_pattern = (
                r'<axis\s+id="' + re.escape(axis_id) + r'">\s*<scale>-?[\d.]+</scale>'
            )
            new_text, count = re.subn(
                insert_pattern,
                lambda m: m.group(0) + "\n        <usercomment>" + escaped + "</usercomment>",
                xml_text,
                count=1
            )

        if count == 0:
            print("No <axis id=\"" + axis_id + "\"> entry found in "
                  + SETTINGS_PATH + " - leaving it unchanged")
            return

        try:
            with open(SETTINGS_PATH, "w") as f:
                f.write(new_text)
            print("Saved " + axis_id + " comment")
        except OSError as e:
            print("Could not write " + SETTINGS_PATH + ": " + str(e))
            return

    def _read_pid_gains(self, widget_id_for_param):
        '''
        Reads P/I/D/FF0/FF1/FF2 from one axis's/spindle loop's own
        Settings tab widgets into a plain {param: value} dict, for
        embedding directly in a .settings.ini JSON "pid"/"pid_pos"/
        "pid_vel" entry - the JSON counterpart to _export_pid_block's XML
        sub-element (kept separate rather than shared, since one builds
        an ElementTree element and this builds a dict). Missing widgets
        are skipped; returns {} if none of this axis's PID widgets exist
        in this component.
        '''
        values = {}
        for param in PID_PARAMS:
            widget = self.builder.get_object(widget_id_for_param(param))
            if widget is not None:
                values[param] = widget.get_value()
        return values

    def Settings_Notes_Changed(self, buffer):
        # Wired to the Notes GtkTextView's GtkTextBuffer "changed" signal.
        # The Notes field is free-text scratch space only - nothing
        # persists it (the .settings.ini profile mechanism that used to
        # save it has been removed; REBset_v1.ini has no notes field).
        pass

#######################################################################
# Measurement_System_Changed
# Purpose:              User picked Metric or Imperial in the Settings
#                           tab's "Other" section. Updates this
#                           component's own unit-of-measure labels for
#                           immediate feedback, persists the choice to
#                           REBset_v1.ini, and warns that a restart
#                           is needed for the new units to actually take
#                           effect. REB.ini itself is never patched here
#                           any more - REB_Setup/REB_Launch.sh overlays
#                           this persisted choice onto a fresh copy of
#                           REB.ini (REB.local.ini, written next to
#                           REB.ini in this repo's own directory - see
#                           REB_Generate_Local_Ini.py for why it can't
#                           live in RoseEngineButlerLocal) on every
#                           LinuxCNC launch, so a `git pull` of REB.ini
#                           can never clobber it (see
#                           REB_Setup/REB_Generate_Local_Ini.py).
# Updated:              ver 1.1, 1 August 2026, Claude
# ---------------------------------------------------------------------
# Called from:
#   UI:                 REB_Tab_Settings_v1
#   Widget:              Measurement_System  (GtkComboBoxText)
#   Signal:              GtkComboBoxText/changed
#######################################################################
    def Measurement_System_Changed(self, widget):
        if self._applying_measurement_system:
            return

        system = widget.get_active_text()
        if system not in ("Metric", "Imperial"):
            return

        self._apply_measurement_system_labels(system)
        _save_measurement_system(system)
        _show_restart_required_popup(widget)

    def Device_Names_Changed(self, buffer):
        # Wired to the Device Names GtkTextView's GtkTextBuffer
        # "changed" signal - mirrors Measurement_System_Changed's
        # save-immediately pattern. Suppressed while _load_device_names
        # is itself the one driving the buffer text at startup.
        if self._applying_device_names:
            return
        text = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False)
        names = [line.strip() for line in text.splitlines() if line.strip()]
        _save_device_names(names)

#######################################################################
# Max_Jog_Speed_Changed
# Purpose:              User changed the Max Jog Speed on the Settings
#                           tab's "General" section. Persists the value
#                           to REBset_v1.ini and warns that a
#                           restart is needed. REB.ini itself is never
#                           patched here any more - REB_Setup/REB_Launch.sh
#                           overlays this persisted value onto a fresh
#                           copy of REB.ini (REB.local.ini, written next
#                           to REB.ini in this repo's own directory - see
#                           REB_Generate_Local_Ini.py for why it can't
#                           live in RoseEngineButlerLocal) on every
#                           LinuxCNC launch, so a `git pull` of REB.ini
#                           can never clobber it (see
#                           REB_Setup/REB_Generate_Local_Ini.py).
# Updated:              ver 1.1, 1 August 2026, Claude
# ---------------------------------------------------------------------
# Called from:
#   UI:                 REB_Tab_Settings_v1
#   Widget:              Max_Jog_Speed  (GtkSpinButton)
#   Signal:              GtkSpinButton/value-changed
#######################################################################
    def Max_Jog_Speed_Changed(self, widget):
        if self._applying_max_jog_speed:
            return

        value = widget.get_value()
        _save_max_jog_speed(value)
        _show_restart_required_popup(
            widget,
            "The Max Jog Speed change will not take effect until you exit "
            "and restart LinuxCNC."
        )

#######################################################################
# Open_User_Manual
# Purpose:              Opens the Rose Engine Butler User Manual's Axis
#                           Configuration File page in the default web
#                           browser.
# Updated:              ver 1.0, 6 August 2026, Claude
# ---------------------------------------------------------------------
# Called from:
#   UI:                 REB_Tab_Settings_v1
#   Button:              Open User Manual  (HAL_Button)
#   Signal:              GtkButton/pressed
#######################################################################
    def Open_User_Manual(self, widget):

        print("=================================================")
        print("FUNCTION Open_User_Manual")

        url = "https://roseenginebutler.com/UserManual/index.php?n=Main.AxisConfigurationFile"
        webbrowser.open(url)

        Prt1 = "Opening website " + url
        print(Prt1)

#######################################################################
# Settings_Save
# Purpose:              Writes the live scale/backlash/PID values -
#                           read straight from this tab's own widgets,
#                           which already mirror the live HAL pins via
#                           their own value-changed handlers - into
#                           SETTINGS_PATH (/home/reuben/Documents/
#                           REBset_v1.ini), in the same XML shape
#                           REB_Scale_Persist.py already writes there at
#                           shutdown. This is an on-demand trigger of
#                           that same patch -
#                           Measurement System/Max Jog Speed/the five
#                           VELOCITY_SETTINGS values aren't touched here
#                           since each of those already writes itself
#                           into SETTINGS_PATH immediately on change.
# Updated:              ver 2.0, 2 August 2026, Claude
# ---------------------------------------------------------------------
# Called from:
#   UI:                 REB_Tab_Settings_v1
#   Button:              Settings_Save  (GtkButton)
#   Signal:              GtkButton/clicked
#######################################################################
    def Settings_Save(self, widget):
        if self.builder.get_object("X_Set_Scale") is None:
            return

        print("=================================================")
        print("FUNCTION Settings_Save")
        self._write_rebset_snapshot()

    def _patch_pid_block(self, text, block_tag, values):
        '''
        Patches P/I/D/FF0/FF1/FF2 values into a <pid>/<pid_pos>/
        <pid_vel> sub-element within text (an already-extracted <axis>
        block), leaving everything else untouched. Mirrors
        REB_Scale_Persist.py's set_pid_block, but operating on values
        already read from this component's own widgets rather than via
        halcmd getp (this component IS the live process, no subprocess
        round-trip needed). Returns the patched text unchanged if the
        block isn't found.
        '''
        block_match = re.search(r'<' + block_tag + r'>.*?</' + block_tag + r'>', text, re.DOTALL)
        if not block_match:
            return text

        block = block_match.group(0)
        for param, value in values.items():
            block = re.sub(
                r'(<' + param + r'>)-?[\d.]+(</' + param + r'>)',
                lambda m: m.group(1) + str(value) + m.group(2),
                block, count=1
            )
        return text[:block_match.start()] + block + text[block_match.end():]

    def _write_rebset_snapshot(self):
        '''
        Writes this tab's live Scale/Backlash/PID widget values into
        SETTINGS_PATH's <axis> blocks - see Settings_Save above for why
        Measurement System/Max Jog Speed/VELOCITY_SETTINGS aren't
        touched here. Reads the whole file once, patches every axis in
        memory, then writes it back once - unlike the shutdown path
        (REB_Scale_Persist.py), which patches and writes incrementally
        since it goes through separate halcmd calls per value.
        '''
        try:
            with open(SETTINGS_PATH, "r") as f:
                xml_text = f.read()
        except OSError as e:
            print("Could not read " + SETTINGS_PATH + ": " + str(e))
            return

        for axis_id in AXIS_STEPGEN:
            axis_match = re.search(
                r'<axis\s+id="' + re.escape(axis_id) + r'">.*?</axis>',
                xml_text, re.DOTALL
            )
            if not axis_match:
                print("No <axis id=\"" + axis_id + "\"> entry found in " + SETTINGS_PATH)
                continue

            axis_block = axis_match.group(0)

            scale_widget = self.builder.get_object(axis_id + "_Set_Scale")
            if scale_widget is not None:
                axis_block = re.sub(
                    r'(<scale>)-?[\d.]+(</scale>)',
                    lambda m: m.group(1) + str(scale_widget.get_value()) + m.group(2),
                    axis_block, count=1
                )

            backlash_widget = self.builder.get_object(axis_id + "_Set_Backlash")
            if backlash_widget is not None:
                axis_block = re.sub(
                    r'(<backlash>)-?[\d.]+(</backlash>)',
                    lambda m: m.group(1) + str(backlash_widget.get_value()) + m.group(2),
                    axis_block, count=1
                )

            if axis_id in PID_AXES:
                values = self._read_pid_gains(lambda param, axis_id=axis_id: axis_id + "_Set_" + param)
                axis_block = self._patch_pid_block(axis_block, "pid", values)
            elif axis_id in PID_SPINDLE_LOOPS:
                for suffix, block_tag in (("Pos", "pid_pos"), ("Vel", "pid_vel")):
                    values = self._read_pid_gains(
                        lambda param, axis_id=axis_id, suffix=suffix: axis_id + "_Set_" + param + "_" + suffix
                    )
                    axis_block = self._patch_pid_block(axis_block, block_tag, values)

            xml_text = xml_text[:axis_match.start()] + axis_block + xml_text[axis_match.end():]

        try:
            with open(SETTINGS_PATH, "w") as f:
                f.write(xml_text)
            print("Saved live scale/backlash/PID values to " + SETTINGS_PATH)
        except OSError as e:
            print("Could not write " + SETTINGS_PATH + ": " + str(e))

#######################################################################
# Settings_Save_As
# Purpose:              Same live-value snapshot as Settings_Save, but
#                           written to a file the operator picks instead
#                           of always overwriting SETTINGS_PATH - e.g.
#                           for a dated backup before a retune (hence the
#                           dialog's default filename of today's date,
#                           not SETTINGS_PATH's own name - see below).
#                           Refreshes SETTINGS_PATH first (via
#                           _write_rebset_snapshot, the same call
#                           Settings_Save makes) so the copy reflects the
#                           current live values, then copies that file
#                           byte-for-byte to the chosen path. This does
#                           not change which file Settings_Save/
#                           Settings_Load use afterward - unlike the
#                           retired named-.settings.ini mechanism, there is
#                           no "current file" to switch to.
# Updated:              ver 1.1, 8 August 2026, Claude
# ---------------------------------------------------------------------
# Called from:
#   UI:                 REB_Tab_Settings_v1
#   Button:              Settings_Save_As  (GtkButton)
#   Signal:              GtkButton/clicked
#######################################################################
    def Settings_Save_As(self, widget):
        if self.builder.get_object("X_Set_Scale") is None:
            return

        print("=================================================")
        print("FUNCTION Settings_Save_As")

        self._write_rebset_snapshot()

        os.makedirs(REBSET_DEFAULT_DIR, exist_ok=True)

        dialog = Gtk.FileChooserDialog(
            title="Save Settings As",
            transient_for=widget.get_toplevel(),
            action=Gtk.FileChooserAction.SAVE,
        )
        dialog.add_buttons(
            "_Cancel", Gtk.ResponseType.CANCEL,
            "_Save", Gtk.ResponseType.OK,
        )
        dialog.set_current_folder(REBSET_DEFAULT_DIR)
        dialog.set_do_overwrite_confirmation(True)
        # Today's date, not SETTINGS_PATH's own fixed "REBset_v1.ini"
        # name - this is a copy going somewhere else, so defaulting to
        # the exact name of the file it's copied from just invites
        # confusing the two; a dated name reads as "a snapshot from
        # this day" and is still just a default the operator can
        # rename on this same dialog.
        dialog.set_current_name(time.strftime("%Y-%m-%d") + ".REBset_v1.ini")

        file_filter = Gtk.FileFilter()
        file_filter.set_name("Rose Engine Butler Settings (*.ini)")
        file_filter.add_pattern("*.ini")
        dialog.add_filter(file_filter)

        response = dialog.run()
        path = dialog.get_filename() if response == Gtk.ResponseType.OK else None
        dialog.destroy()

        if not path:
            print("Settings_Save_As cancelled")
            return

        if not path.endswith(".ini"):
            path += ".ini"

        try:
            shutil.copyfile(SETTINGS_PATH, path)
        except OSError as e:
            _show_settings_error(widget, "Could not write " + path + ":\n" + str(e))
            return

        print("Saved a copy of " + SETTINGS_PATH + " to " + path)

#######################################################################
# Settings_Load
# Purpose:              Lets the operator pick a REBset_v1.ini-shaped
#                           settings file (SETTINGS_PATH itself, or a
#                           Settings_Save_As backup of it) and applies
#                           whatever axis Scale/Backlash/PID/comment and
#                           Measurement System values it contains to the
#                           live widgets, via the same _apply_settings_root
#                           helper Import_Settings uses - see that
#                           function for why each value goes through its
#                           own widget handler rather than being written
#                           to disk directly, and for the comment-restart
#                           caveat. Differs from Import_Settings only in
#                           the file it expects (a full snapshot, using
#                           <usercomment> - see docs/settings_file.md -
#                           rather than Export's smaller <comment>-tagged
#                           subset) and in not restricting to a hand-picked
#                           subset of axes.
# Updated:              ver 1.0, 8 August 2026, Claude
# ---------------------------------------------------------------------
# Called from:
#   UI:                 REB_Tab_Settings_v1
#   Button:              Settings_Load  (GtkButton)
#   Signal:              GtkButton/clicked
#######################################################################
    def Settings_Load(self, widget):
        if self.builder.get_object("X_Set_Scale") is None:
            return

        print("=================================================")
        print("FUNCTION Settings_Load")

        os.makedirs(REBSET_DEFAULT_DIR, exist_ok=True)

        dialog = Gtk.FileChooserDialog(
            title="Load Settings",
            transient_for=widget.get_toplevel(),
            action=Gtk.FileChooserAction.OPEN,
        )
        dialog.add_buttons(
            "_Cancel", Gtk.ResponseType.CANCEL,
            "_Load", Gtk.ResponseType.OK,
        )
        dialog.set_current_folder(REBSET_DEFAULT_DIR)

        file_filter = Gtk.FileFilter()
        file_filter.set_name("Rose Engine Butler Settings (*.ini)")
        file_filter.add_pattern("*.ini")
        dialog.add_filter(file_filter)

        response = dialog.run()
        path = dialog.get_filename() if response == Gtk.ResponseType.OK else None
        dialog.destroy()

        if not path:
            print("Settings_Load cancelled")
            return

        try:
            root = ET.parse(path).getroot()
        except (OSError, ET.ParseError) as e:
            _show_settings_error(widget, "Could not read " + path + ":\n" + str(e))
            return

        if root.tag != "settings":
            _show_settings_error(widget, path + " is not a Rose Engine Butler settings file.")
            return

        self._apply_settings_root(widget, root, path, "usercomment")


#######################################################################
# Export_Settings
# Purpose:              Lets the operator pick which axes to export (each
#                           selected axis's Scale, Backlash, and Stepper
#                           Motor Tuning/PID all go together as one unit -
#                           see _run_export_selection_dialog), and/or
#                           Measurement System, and export just that
#                           subset to a small <comment>.REBset_v1.ini
#                           file, named after the single device name
#                           comment picked for the export - or today's
#                           date if the selected axes name more than one
#                           distinct device - for quick, ad hoc sharing
#                           (e.g. "just my B-axis calibration"), distinct
#                           from the full REBset_v1.ini snapshot. See
#                           docs/settings_file.md.
# Updated:              ver 1.3, 8 August 2026, Claude
# ---------------------------------------------------------------------
# Called from:
#   UI:                 REB_Tab_Settings_v1
#   Button:              Export_Settings  (GtkButton)
#   Signal:              GtkButton/clicked
#######################################################################
    def Export_Settings(self, widget):
        if self.builder.get_object("X_Set_Scale") is None:
            return

        print("=================================================")
        print("FUNCTION Export_Settings")

        selected = self._run_export_selection_dialog(widget)
        if not selected:
            print("Export_Settings cancelled")
            return

        comments = set(selected.get("comments", {}).values())
        if not comments:
            _show_settings_error(
                widget,
                "Pick a device name for at least one exported axis - it's "
                "used to name the exported file."
            )
            return
        if len(comments) == 1:
            file_name = re.sub(r'[\\/]', '-', comments.pop()) + EXPORT_EXTENSION
        else:
            # More than one different device name was selected (e.g.
            # exporting several axes belonging to different physical
            # devices at once) - no single name to build the file's
            # default name from, so fall back to today's date instead of
            # refusing to export. Still just a default: the operator can
            # rename it on the save dialog that comes up next.
            file_name = time.strftime("%Y-%m-%d") + EXPORT_EXTENSION

        os.makedirs(REBSET_DEFAULT_DIR, exist_ok=True)

        dialog = Gtk.FileChooserDialog(
            title="Export Settings",
            transient_for=widget.get_toplevel(),
            action=Gtk.FileChooserAction.SAVE,
        )
        dialog.add_buttons(
            "_Cancel", Gtk.ResponseType.CANCEL,
            "_Export", Gtk.ResponseType.OK,
        )
        dialog.set_current_folder(REBSET_DEFAULT_DIR)
        dialog.set_do_overwrite_confirmation(True)
        dialog.set_current_name(file_name)

        file_filter = Gtk.FileFilter()
        file_filter.set_name("Rose Engine Butler Export (*" + EXPORT_EXTENSION + ")")
        file_filter.add_pattern("*" + EXPORT_EXTENSION)
        dialog.add_filter(file_filter)

        response = dialog.run()
        path = dialog.get_filename() if response == Gtk.ResponseType.OK else None
        dialog.destroy()

        if not path:
            print("Export_Settings cancelled")
            return

        if not path.endswith(EXPORT_EXTENSION):
            path += EXPORT_EXTENSION

        root = ET.Element("settings")
        axis_els = {}

        def get_axis_el(axis_id):
            if axis_id not in axis_els:
                axis_els[axis_id] = ET.SubElement(root, "axis", {"id": axis_id})
            return axis_els[axis_id]

        # Each selected axis exports Scale, Backlash, and Stepper Motor
        # Tuning/PID together as one unit - see _run_export_selection_dialog
        # for why these three no longer get independent checkboxes.
        exported = []
        for axis_id in selected.get("axes", ()):
            spin = self.builder.get_object(axis_id + "_Set_Scale")
            if spin is not None:
                ET.SubElement(get_axis_el(axis_id), "scale").text = str(spin.get_value())
                exported.append(axis_id + " Scale")

            backlash_spin = self.builder.get_object(axis_id + "_Set_Backlash")
            if backlash_spin is not None:
                ET.SubElement(get_axis_el(axis_id), "backlash").text = str(backlash_spin.get_value())
                exported.append(axis_id + " Backlash")

            if axis_id in PID_AXES:
                self._export_pid_block(get_axis_el(axis_id), axis_id, "pid",
                                        lambda param, axis_id=axis_id: axis_id + "_Set_" + param)
                exported.append(axis_id + " PID")
            elif axis_id in PID_SPINDLE_LOOPS:
                for suffix in ("Pos", "Vel"):
                    block_tag = "pid_pos" if suffix == "Pos" else "pid_vel"
                    self._export_pid_block(
                        get_axis_el(axis_id), axis_id, block_tag,
                        lambda param, axis_id=axis_id, suffix=suffix: axis_id + "_Set_" + param + "_" + suffix
                    )
                exported.append(axis_id + " PID")

        for axis_id, comment in selected.get("comments", {}).items():
            ET.SubElement(get_axis_el(axis_id), "comment").text = comment
            exported.append(axis_id + " Comment (" + comment + ")")

        if selected.get("measurement_system"):
            combo = self.builder.get_object("Measurement_System")
            system = combo.get_active_text() if combo is not None else None
            if system:
                ET.SubElement(root, "measurement_system").text = system
                exported.append("Measurement System")

        ET.indent(root, space="    ")

        try:
            ET.ElementTree(root).write(path, encoding="UTF-8", xml_declaration=True)
        except OSError as e:
            _show_settings_error(widget, "Could not write " + path + ":\n" + str(e))
            return

        print("Exported " + ", ".join(exported) + " to " + path)

    def _export_pid_block(self, axis_el, axis_id, block_tag, widget_id_for_param):
        '''
        Reads P/I/D/FF0/FF1/FF2 from this axis's/spindle loop's own
        Settings tab widgets and writes them into a <pid>/<pid_pos>/
        <pid_vel> sub-element of axis_el - the same block shape
        REB_Settings_v1.ini already uses, so a value round-trips through
        Import_Settings/_load_pid_settings identically either way. Missing
        widgets are skipped rather than erroring - matches the tolerant,
        "just skip what isn't there" pattern the rest of Export/Import
        already uses.
        '''
        block_el = None
        for param in PID_PARAMS:
            widget = self.builder.get_object(widget_id_for_param(param))
            if widget is None:
                continue
            if block_el is None:
                block_el = ET.SubElement(axis_el, block_tag)
            ET.SubElement(block_el, param).text = str(widget.get_value())

    def _run_export_selection_dialog(self, widget):
        '''
        Modal checklist: one row per axis, each with a single checkbox
        covering that axis's Scale, Backlash, and Stepper Motor Tuning/
        PID together (P/I/D/FF0/FF1/FF2 - Sp0/Sp1 each cover both their
        position and velocity loops as part of the same unit), plus a
        Device dropdown (populated from the General tab's maintained
        Device Names list) to optionally label that axis's export with
        which physical device it belongs to (e.g. "Rosette Phaser/
        Multiplier (Sp1)") - axis-to-device isn't fixed, so this is a
        per-export choice rather than something inferred from the axis
        id. Two entries per axis, nothing more - these three used to be
        independent checkboxes in separate columns, which was more
        precision than this dialog needs; a device's Scale/Backlash/
        tuning are always exported or skipped together in practice.
        Measurement System stays a separate, independent checkbox below
        the axis list. All pre-checked, with Select All/None convenience
        buttons.

        Each Device combo defaults to whatever's currently set on the
        main panel's own comment field for that axis (X/Z/U/V/W/B - see
        COMMENT_AXES), via _read_persisted_axis_comment against
        SETTINGS_PATH - the main panel is a separate gladevcp process
        from this one, so its live widget isn't reachable directly (see
        CLAUDE.md), but its own "changed" handler saves every edit
        straight to REBset_v1.ini's <usercomment>, which is what's read
        here instead. Sp0/Sp1 have no such field, so they default to
        SPINDLE_DEFAULT_DEVICE_NAME instead. Either way, falls back to
        the placeholder if that value doesn't match any currently
        maintained device name, same as _load_axis_comments does for the
        main panel's own combos.

        Returns {"axes": [...ids...], "comments":
        {axis_id: name, ...}, "measurement_system": bool} on Export, or
        None if cancelled/nothing was selected.
        '''
        dialog = Gtk.Dialog(
            title="Export Settings - Choose What to Include",
            transient_for=widget.get_toplevel(),
            modal=True,
        )
        dialog.add_buttons(
            "_Cancel", Gtk.ResponseType.CANCEL,
            "_Export", Gtk.ResponseType.OK,
        )

        content = dialog.get_content_area()
        content.set_border_width(8)
        content.set_spacing(6)

        select_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        select_all_btn = Gtk.Button(label="Select All")
        select_none_btn = Gtk.Button(label="Select None")
        select_row.pack_start(select_all_btn, False, False, 0)
        select_row.pack_start(select_none_btn, False, False, 0)
        content.pack_start(select_row, False, False, 0)

        content.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 0)

        def section_label(text):
            label = Gtk.Label()
            label.set_markup("<b>" + text + "</b>")
            label.set_xalign(0)
            return label

        device_names = self._read_device_names()

        try:
            with open(SETTINGS_PATH, "r") as f:
                comments_xml_text = f.read()
        except OSError as e:
            print("Could not read " + SETTINGS_PATH + ": " + str(e))
            comments_xml_text = ""

        axis_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        content.pack_start(axis_col, False, False, 0)

        # Sized so the "Device" header lines up with the combo boxes
        # below it, not just with wherever the widest axis checkbox
        # happens to end - axis labels are different widths (e.g. "X"
        # vs. "Sp0"), so without this the combos (and this header) would
        # drift depending on which axis's row is widest.
        axis_label_group = Gtk.SizeGroup(mode=Gtk.SizeGroupMode.HORIZONTAL)

        axis_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        axis_label = section_label("Axis")
        axis_label_group.add_widget(axis_label)
        axis_header.pack_start(axis_label, False, False, 0)
        axis_header.pack_start(section_label("Device"), False, False, 0)
        axis_col.pack_start(axis_header, False, False, 0)

        checks = {}
        comment_combos = {}
        for axis_id in AXIS_STEPGEN:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            check = Gtk.CheckButton(label=axis_id)
            check.set_active(True)
            check.set_tooltip_text(
                "Exports this axis's Scale, Backlash, and Stepper Motor "
                "Tuning together."
            )
            axis_label_group.add_widget(check)
            row.pack_start(check, False, False, 0)

            combo = Gtk.ComboBoxText()
            combo.append_text(DEVICE_COMBO_PLACEHOLDER)
            for name in device_names:
                combo.append_text(name)

            stored = (_read_persisted_axis_comment(axis_id, comments_xml_text)
                      or SPINDLE_DEFAULT_DEVICE_NAME.get(axis_id, ""))
            try:
                combo.set_active(device_names.index(stored) + 1 if stored else 0)
            except ValueError:
                # Doesn't match any currently maintained device name -
                # see _load_axis_comments' matching fallback.
                combo.set_active(0)

            combo.set_tooltip_text(
                "Optional: label this axis's export with one of the "
                "device names maintained on the General tab."
            )
            row.pack_start(combo, False, False, 0)

            axis_col.pack_start(row, False, False, 0)
            checks[axis_id] = check
            comment_combos[axis_id] = combo

        content.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 0)

        measurement_check = Gtk.CheckButton(label="Measurement System")
        measurement_check.set_active(True)
        content.pack_start(measurement_check, False, False, 0)

        device_note = Gtk.Label()
        device_note.set_markup(
            "<i>You must select a device for any axis data you wish to "
            "save. You can change that name on the file save screen "
            "which pops up next.</i>"
        )
        device_note.set_xalign(0)
        device_note.set_line_wrap(True)
        device_note.set_max_width_chars(60)
        content.pack_start(device_note, False, False, 0)

        all_checks = list(checks.values()) + [measurement_check]
        select_all_btn.connect("clicked", lambda b: [c.set_active(True) for c in all_checks])
        select_none_btn.connect("clicked", lambda b: [c.set_active(False) for c in all_checks])

        content.show_all()

        result = None
        while True:
            response = dialog.run()
            if response != Gtk.ResponseType.OK:
                break

            axes = [axis_id for axis_id, c in checks.items() if c.get_active()]
            comments = {
                axis_id: text
                for axis_id, combo in comment_combos.items()
                for text in [_combo_selected_device(combo)]
                if text
            }
            measurement_system = measurement_check.get_active()
            if not axes and not comments and not measurement_system:
                _show_settings_error(widget, "Select at least one item to export.")
                continue

            result = {
                "axes": axes,
                "comments": comments,
                "measurement_system": measurement_system,
            }
            break

        dialog.destroy()
        return result

#######################################################################
# Import_Settings
# Purpose:              Reads a <comment>.REBset_v1.ini export file and
#                           applies whatever
#                           subset of axis Scale/Backlash/PID/
#                           Measurement System values it contains to the
#                           current settings - everything else on the
#                           Settings tab is left untouched. Applies each
#                           value through the same widget handlers a
#                           live edit would use (<Axis>_Set_Scale/
#                           <Axis>_Set_Backlash/Measurement_System_Changed),
#                           so the usual per-axis safety checks (motion
#                           abort, disable-if-enabled) and dirty-tracking
#                           all apply exactly as if the operator had
#                           typed/selected each value themselves. The
#                           actual per-axis apply loop lives in
#                           _apply_settings_root, shared with Settings_Load.
# Updated:              ver 1.2, 8 August 2026, Claude
# ---------------------------------------------------------------------
# Called from:
#   UI:                 REB_Tab_Settings_v1
#   Button:              Import_Settings  (GtkButton)
#   Signal:              GtkButton/clicked
#######################################################################
    def Import_Settings(self, widget):
        if self.builder.get_object("X_Set_Scale") is None:
            return

        print("=================================================")
        print("FUNCTION Import_Settings")

        os.makedirs(REBSET_DEFAULT_DIR, exist_ok=True)

        dialog = Gtk.FileChooserDialog(
            title="Import Settings",
            transient_for=widget.get_toplevel(),
            action=Gtk.FileChooserAction.OPEN,
        )
        dialog.add_buttons(
            "_Cancel", Gtk.ResponseType.CANCEL,
            "_Import", Gtk.ResponseType.OK,
        )
        dialog.set_current_folder(REBSET_DEFAULT_DIR)

        file_filter = Gtk.FileFilter()
        file_filter.set_name("Rose Engine Butler Export (*" + EXPORT_EXTENSION + ")")
        file_filter.add_pattern("*" + EXPORT_EXTENSION)
        dialog.add_filter(file_filter)

        response = dialog.run()
        path = dialog.get_filename() if response == Gtk.ResponseType.OK else None
        dialog.destroy()

        if not path:
            print("Import_Settings cancelled")
            return

        try:
            root = ET.parse(path).getroot()
        except (OSError, ET.ParseError) as e:
            _show_settings_error(widget, "Could not read " + path + ":\n" + str(e))
            return

        if root.tag != "settings":
            _show_settings_error(widget, path + " is not a Rose Engine Butler export file.")
            return

        self._apply_settings_root(widget, root, path, "comment")

    def _apply_settings_root(self, widget, root, path, comment_tag):
        '''
        Applies whatever subset of axis Scale/Backlash/PID/comment/
        Measurement System values a parsed <settings> root contains to
        the live Settings-tab widgets, then reports what changed. Shared
        by Import_Settings (small <comment>-tagged Export_Settings
        subset files) and Settings_Load (full <usercomment>-tagged
        REBset_v1.ini-shaped snapshots) - comment_tag is the only thing
        that differs between those two file shapes; everything else
        (scale/backlash/pid/measurement_system element names) is common
        to both. See Import_Settings's old docstring history for why
        each value is applied through its own widget handler
        (<Axis>_Set_Scale/<Axis>_Set_Backlash/Measurement_System_Changed)
        rather than written to disk directly - it keeps the usual
        per-axis safety checks (motion abort, disable-if-enabled) in the
        loop exactly as if the operator had typed/selected each value
        themselves.
        '''
        imported = []
        comment_imported = False
        for axis_el in root.findall("axis"):
            axis_id = axis_el.get("id")
            if axis_id not in AXIS_STEPGEN:
                continue

            # Scale and PID are independent - a file may carry either,
            # both, or neither for a given axis, so check each on its own
            # rather than skipping the whole <axis> element when one is
            # absent.
            scale_el = axis_el.find("scale")
            if scale_el is not None and scale_el.text is not None:
                spin = self.builder.get_object(axis_id + "_Set_Scale")
                if spin is not None:
                    try:
                        scale = float(scale_el.text.strip())
                    except ValueError:
                        print("Skipping " + axis_id + " scale - not a number: " + scale_el.text)
                        scale = None
                    if scale is not None:
                        spin.set_value(scale)  # fires <Axis>_Set_Scale: abort/disable-if-enabled/halcmd setp/mark dirty
                        imported.append(axis_id + " Scale")

            backlash_el = axis_el.find("backlash")
            if backlash_el is not None and backlash_el.text is not None:
                spin = self.builder.get_object(axis_id + "_Set_Backlash")
                if spin is not None:
                    try:
                        backlash = float(backlash_el.text.strip())
                    except ValueError:
                        print("Skipping " + axis_id + " backlash - not a number: " + backlash_el.text)
                        backlash = None
                    if backlash is not None:
                        spin.set_value(backlash)  # fires <Axis>_Set_Backlash: halcmd setp/mark dirty
                        imported.append(axis_id + " Backlash")

            # Comment (device name - see Export_Settings/the General
            # tab's Device Names list): only COMMENT_AXES have a live
            # comment field to apply it to (Sp0/Sp1 don't - the main
            # panel has no spindle comment entries), so a file's comment
            # for a spindle is informational-only and doesn't round-trip
            # back into anything here. _save_axis_comment only patches
            # REBset_v1.ini on disk - it can't reach into the
            # X_Comment/etc. Entry widget itself, because that widget
            # lives on REB_Panel_v1.ui, a separate `loadusr gladevcp`
            # process from this Settings-tab one (see EMBED_TAB_COMMAND
            # in REB.ini) - not just a different builder in the same
            # process. There is no live IPC between them for this, so the
            # panel only picks up the new text from _load_axis_comments()
            # at its own next startup - hence comment_imported below.
            comment_el = axis_el.find(comment_tag)
            if comment_el is not None and comment_el.text is not None and axis_id in COMMENT_AXES:
                self._save_axis_comment(axis_id, comment_el.text)
                imported.append(axis_id + " Comment")
                comment_imported = True

            pid_applied = False
            if axis_id in PID_AXES:
                pid_applied = self._import_pid_block(
                    axis_el, "pid", lambda param, axis_id=axis_id: axis_id + "_Set_" + param
                )
            elif axis_id in PID_SPINDLE_LOOPS:
                for suffix in ("Pos", "Vel"):
                    block_tag = "pid_pos" if suffix == "Pos" else "pid_vel"
                    if self._import_pid_block(
                        axis_el, block_tag,
                        lambda param, axis_id=axis_id, suffix=suffix: axis_id + "_Set_" + param + "_" + suffix
                    ):
                        pid_applied = True
            if pid_applied:
                imported.append(axis_id + " PID")

        measurement_el = root.find("measurement_system")
        if measurement_el is not None and measurement_el.text in ("Metric", "Imperial"):
            combo = self.builder.get_object("Measurement_System")
            if combo is not None:
                combo.set_active(0 if measurement_el.text == "Metric" else 1)  # fires Measurement_System_Changed
                imported.append("Measurement System")

        if imported:
            print("Imported " + ", ".join(imported) + " from " + path)
            dialog = Gtk.MessageDialog(
                transient_for=widget.get_toplevel(),
                flags=0,
                message_type=Gtk.MessageType.INFO,
                buttons=Gtk.ButtonsType.OK,
                text="Imported: " + ", ".join(imported),
            )
            if comment_imported:
                dialog.format_secondary_text(
                    "The imported comment(s) are saved, but the main "
                    "panel's Comment field runs as a separate program and "
                    "won't show the new text until you restart LinuxCNC."
                )
            dialog.run()
            dialog.destroy()
        else:
            _show_settings_error(widget, "Nothing recognizable to import in " + path)

    def _import_pid_block(self, axis_el, block_tag, widget_id_for_param):
        '''
        Mirror of _export_pid_block: reads a <pid>/<pid_pos>/<pid_vel>
        sub-element (if present) and applies each P/I/D/FF0/FF1/FF2 value
        it contains to that param's own Settings tab widget via
        set_value() - fires the same _pid_set handler a live edit would
        (pushes straight to the live pid.* HAL gain pin; see that
        function's docstring for why it doesn't need the abort/disable
        dance scale changes do, and doesn't mark .settings.ini dirty -
        PID gains aren't part of that format's schema). Returns True if
        anything was actually applied.
        '''
        block_el = axis_el.find(block_tag)
        if block_el is None:
            return False

        applied = False
        for param in PID_PARAMS:
            param_el = block_el.find(param)
            if param_el is None or param_el.text is None:
                continue

            widget = self.builder.get_object(widget_id_for_param(param))
            if widget is None:
                continue

            try:
                value = float(param_el.text.strip())
            except ValueError:
                print("Skipping " + widget_id_for_param(param) + " - not a number: " + param_el.text)
                continue

            widget.set_value(value)
            applied = True

        return applied

    def _on_machine_is_on_changed(self, hal_pin, data=None):
        '''
        Grays out the main panel's whole grid of axis/spindle controls
        whenever the machine is not powered on, so nothing on it can be
        operated until the operator powers the machine on. GTK
        propagates insensitivity to every child of a container, so
        toggling this one grid is enough for the whole panel.

        No-op in every component other than the main panel (MainGrid),
        which is the only one with this widget.
        '''
        grid = self.builder.get_object("MainGrid")
        if grid is None:
            return
        grid.set_sensitive(bool(hal_pin.get()))

    # Each of these is wired to its GtkComboBoxText's "changed" signal
    # (see REB_Panel_v1.ui) - fired the instant the operator picks a
    # different entry, and also by combo.set_active() in
    # _load_axis_comments itself, which is why each checks
    # _applying_axis_comments first: without that guard, loading the
    # persisted comment at startup would immediately re-save the exact
    # value just read (same pattern as Measurement_System_Changed).
    # _combo_selected_device() (not get_active_text() directly) reads
    # back "" when the leading DEVICE_COMBO_PLACEHOLDER entry is active,
    # rather than saving that placeholder text itself as the comment.
    def X_Comment(self, widget):
        if self._applying_axis_comments:
            return
        self._save_axis_comment("X", _combo_selected_device(widget))

    def Z_Comment(self, widget):
        if self._applying_axis_comments:
            return
        self._save_axis_comment("Z", _combo_selected_device(widget))

    def U_Comment(self, widget):
        if self._applying_axis_comments:
            return
        self._save_axis_comment("U", _combo_selected_device(widget))

    def V_Comment(self, widget):
        if self._applying_axis_comments:
            return
        self._save_axis_comment("V", _combo_selected_device(widget))

    def W_Comment(self, widget):
        if self._applying_axis_comments:
            return
        self._save_axis_comment("W", _combo_selected_device(widget))

    def B_Comment(self, widget):
        if self._applying_axis_comments:
            return
        self._save_axis_comment("B", _combo_selected_device(widget))

# ********************************************************************
#    AA    XX    XX IIIIIIII  SSSSSS      BBBBBBB
#   AAAA    XX  XX    II     SS    SS     BB    BB
#  AA  AA    XXXX     II      SSS         BBBBBBB
# AAAAAAAA   XXXX     II         SSS      BB    BB
# AA    AA  XX  XX    II     SS    SS     BB    BB
# AA    AA XX    XX IIIIIIII  SSSSSS      BBBBBBB
# ********************************************************************

#######################################################################
# B_Move_Idx_Fwd
# Purpose:              This is used to run the B axis forward using
#                       the G0 Gcode.
#                       Note:  sends "B-" (negative), not "B" (positive),
#                           despite being the Fwd handler - empirically-
#                           verified swap, matching the same fix applied
#                           to the spindles and the X/Z/U/V/W Idx_Minus/
#                           Idx_Plus handlers (see Sp0_Move_Fwd's
#                           docstring for that investigation). B's icons
#                           are unaffected/still correct - only the
#                           Gcode sign changes.
# Updated:              ver 1.1, 8 August 2026, Claude
# ---------------------------------------------------------------------
# Called from:
#   UI:                 REB_Panel
#   Button:             B_Move_Idx_Fwd  (Hal_Button)
#   Signal:             GtkButton/pressed
# ---------------------------------------------------------------------
# Data
#   Read from UI:       B_Feed - Feed rate set by user
#   Program Variables
#       Referenced:     (none)
#       Set:            B_Idx_Qty - the quantity of indexes so far.
#                           Forward increases this value.
#   Written to UI:      B_Idx_Qty - the quantity of indexes so far.
#                           Forward increases this value.
# ---------------------------------------------------------------------
# Gcodes Called:    (none)
#######################################################################
    def B_Move_Idx_Fwd(self,widget):

        print("=================================================")
        print("FUNCTION B_Move_Idx_Fwd")

        # Ensure the system is in MDI mode
        s.poll()
        if s.task_state != linuxcnc.MODE_MDI:
                c.mode(linuxcnc.MODE_MDI)
                c.wait_complete() # Wait for mode change to complete

        # Send an MDI command to move along the axis. The G-code axis
        # word must be the CURRENTLY assigned letter for this channel
        # (CURRENT_LETTER), not the hardcoded "B" - see _axis_idx_move's
        # gcode_axis comment for why.
        Gcode = "G1 " + CURRENT_LETTER["B"].upper() + "-" + str(self.B_Idx_Deg) + " F" + str(self.B_Feed)

        print(Gcode)
        c.mdi(Gcode)

        # Wait for the command to complete
        c.wait_complete()

        # increment the count and write out to the UI
        self.B_Idx_Qty = self.B_Idx_Qty + 1
        Prt1 = "B_Idx_Qty = " + str(self.B_Idx_Qty)
        print(Prt1)

        # B_Idx_Qtystr = str(self.B_Idx_Qty)
        # widget.set_label(B_Idx_Qty, B_Idx_Qtystr)

#######################################################################
# B_Move_Idx_Rev
# Purpose:              This is used to run the B axis in reverse using
#                       the G0 Gcode.
#                       Note:  sends "B" (positive), not "B-" (negative),
#                           despite being the Rev handler - see
#                           B_Move_Idx_Fwd's docstring for the same
#                           empirically-verified swap applied here.
# Updated:              ver 1.1, 8 August 2026, Claude
# ---------------------------------------------------------------------
# Called from:
#   UI:                 REB_Panel
#   Button:             B_Move_Idx_Rev  (Hal_Button)
#   Signal:             GtkButton/pressed
# ---------------------------------------------------------------------
# Data
#   Read from UI:       B_Feed - Feed rate set by user
#   Program Variables
#       Referenced:     (none)
#       Set:            B_Idx_Qty - the quantity of indexes so far. Reverse
#                           decreases this value.
#   Written to UI:      B_Idx_Qty - the quantity of indexes so far. Reverse
#                           decreases this value.
# ---------------------------------------------------------------------
# Gcodes Called:        (none)
#######################################################################
    def B_Move_Idx_Rev(self,widget):

        print("=================================================")
        print("FUNCTION B_Move_Idx_Rev")

        # Ensure the system is in MDI mode
        s.poll()
        if s.task_state != linuxcnc.MODE_MDI:
                c.mode(linuxcnc.MODE_MDI)
                c.wait_complete() # Wait for mode change to complete

        # Send an MDI command to move along the axis. See B_Move_Idx_Fwd
        # for why the G-code axis word comes from CURRENT_LETTER.
        Gcode = "G1 " + CURRENT_LETTER["B"].upper() + str(self.B_Idx_Deg) + " F" + str(self.B_Feed)

        print(Gcode)
        c.mdi(Gcode)

        self.B_Idx_Qty = self.B_Idx_Qty - 1
        Prt1 = "B_Idx_Qty = " + str(self.B_Idx_Qty)
        print(Prt1)

        # Wait for the command to complete
        c.wait_complete()

#######################################################################
# Sp0_Set_Idx_DegDiv
# Purpose:              This is used to set the rotational distance
#                       measurement for the Sp0 & Sp1 spindles.
#                       If degrees, set to divisions; 
#                       if divisions, set to degrees.
# Updated:              ver 1.0, 21 July 2026, R. Colvin
# ---------------------------------------------------------------------
# Called from:
#   UI:                 REB_Panel
#   Button:             Sp0_Set_Idx_bW_Deg  (HAL_RadioButton)
#   Signal:             GtkToggledButton/toggled
# ---------------------------------------------------------------------
# Data
#   Read from UI:       (none)
#   Program Variables
#       Referenced:     self.Sp0_Idx_Dist - distance field data
#       Set:            self.Sp0_Idx_Deg - degrees to index
#                       self.Sp0_Idx_DegDiv - type of distance
#                           measurement (Deg or Div)
#   Written to UI:      (none)
# ---------------------------------------------------------------------
# Gcodes Called:        (none)
#######################################################################
    def B_Set_Idx_DegDiv(self,widget):

        print("=================================================")
        print("FUNCTION B_Set_Idx_DegDiv")

        if self.B_Idx_DegDiv == "Deg":
                        self.B_Idx_DegDiv = "Div"
                        self.B_Idx_Deg = round(360 / self.B_Idx_Dist, 1)
        else:
                        self.B_Idx_DegDiv = "Deg"
                        self.B_Idx_Deg = round(self.B_Idx_Dist, 1)

        Prt1 = "B_Idx_Deg = " + str(self.B_Idx_Deg)
        print(Prt1)

        Prt2 = "self.B_Idx_DegDiv = " + self.B_Idx_DegDiv
        print(Prt2)

#######################################################################
# B_Set_Move_Dist
# Purpose:              This is used to set the movement distance for
#                           the B axis.
# Updated:              ver 1.0, 21 July 2026, R. Colvin
# ---------------------------------------------------------------------
# Called from:
#   UI:                 REB_Panel
#   Button:             B_Move_Dist (on setting the value)
#   Signal:             GtkSpinButton/value-changed
# ---------------------------------------------------------------------
# Data
#   Read from UI:       B_Move_Dist
#   Program Variables
#       Referenced:     (none)
#       Set:            self.B_Move_Dist
#   Written to UI:      (none)
# ---------------------------------------------------------------------
# Gcodes Called:        (none)
#######################################################################
    def B_Set_Move_Dist(self,widget):

        print("=================================================")
        print("FUNCTION B_Set_Move_Dist")

        self.B_Move_Dist = widget.get_value()

        print("B_Move_Dist = " + str(self.B_Move_Dist))

#######################################################################
# B_Set_Scale
# Purpose:              This is used to set the scale distance for the
#                           B axis.
# Updated:              ver 1.0, 21 July 2026, R. Colvin
# ---------------------------------------------------------------------
# Called from:
#   UI:                 REB_Tab_Settings
#   Button:             B_Set_Scale (on setting the value)
#   Signal:             HAL_SpinButton/value-changed
# ---------------------------------------------------------------------
# Data
#   Read from UI:       (none)
#   Program Variables
#       Referenced:     (none)
#       Set:            (none)
#   Written to UI:      (none)
# ---------------------------------------------------------------------
# Gcodes Called:        (none)
# ---------------------------------------------------------------------
# HAL Commands:         halcmd setp hm2_7i92.0.stepgen.04.position-scale
#                              (value)
#######################################################################
    def B_Set_Scale(self,widget):

        print("=================================================")
        print("FUNCTION B_Set_Scale")

        B_Scale = round(widget.get_value(), 3)

        # B_ENA-light belongs to the main panel's HAL component
        # ("gladevcp"); read it cross-component via halcmd. To disable
        # the axis, drive this component's own B_Ena_Override pin
        # (ANDed with the panel button in REB_PostGUI_v1.hal) instead of
        # trying to write another component's pin directly.
        status_pin = "gladevcp.B_ENA-light"

        try:
            result = subprocess.run(
                ["halcmd", "getp", status_pin],
                check=True,
                capture_output=True,
                text=True
            )
            is_enabled = result.stdout.strip().upper() in ("TRUE", "1")
            print(status_pin + " = " + result.stdout.strip())

            if is_enabled:
                print("B axis is enabled - disabling")
                self.halcomp['B_Ena_Override'] = False
            else:
                print("B axis is already disabled")
        except subprocess.CalledProcessError as e:
            print("Error checking " + status_pin + ": " + e.stderr)
        except FileNotFoundError:
            print("halcmd not found - is the LinuxCNC environment sourced?")

        # Send the new scale to the X axis stepgen via halcmd.
        hal_pin = "hm2_7i92.0.stepgen.05.position-scale"
        cmd = ["halcmd", "setp", hal_pin, str(B_Scale)]

        try:
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True
            )
            print("Set " + hal_pin + " = " + str(B_Scale))
        except subprocess.CalledProcessError as e:
            print("Error setting " + hal_pin + ": " + e.stderr)
        except FileNotFoundError:
            print("halcmd not found - is the LinuxCNC environment sourced?")

#######################################################################
# B_Set_Ena
# Purpose:              Clears this axis's Ena_Override veto whenever
#                           the ENA button is pressed, so an axis that
#                           was force-disabled by a scale change
#                           (B_Set_Scale) can be re-enabled by the
#                           operator afterward. Does not touch the
#                           panel's own toggle state - see
#                           REB_PostGUI_v1.hal for the flip-flop that
#                           tracks that.
# ---------------------------------------------------------------------
# Called from:
#   UI:                 REB_Panel
#   Button:             B_ENA
#   Signal:             GtkButton/pressed
#######################################################################
    def B_Set_Ena(self,widget,*args):
        _clear_ena_override('B')

#######################################################################
# B_Set_Idx_Dist
# Purpose:              This is used to set the rotational distance
#                       (degrees or divisions of a circle) for the B
#                       axis.
# Updated:              ver 1.0, 21 July 2026, R. Colvin
# ---------------------------------------------------------------------
# Called from:
#   UI:                 REB_Panel
#   Button:             B_Set_Idx_Dist  (HAL_SpinButton)
#   Signal:             GtkSpinButton/value-changed
# ---------------------------------------------------------------------
# Data
#   Read from UI:       B_Idx_Dist
#   Program Variables
#       Referenced:     B_Idx_Dist - Distance set by user
#       Set:            B_Idx_Deg - Degrees to index during movement
#                       B_Idx_DegDiv - type of distance measurement
#                           (Deg or Div)
#   Written to UI:      (none)
# ---------------------------------------------------------------------
# Gcodes Called:        (none)
#######################################################################
    def B_Set_Idx_Dist(self,widget):

        print("=================================================")
        print("FUNCTION B_Set_Idx_Dist")

        self.B_Idx_Dist = widget.get_value()

        if self.B_Idx_DegDiv == "Deg":
                self.B_Idx_Deg = round(self.B_Idx_Dist, 1)
        else:
                self.B_Idx_Deg = round(360 / self.B_Idx_Dist, 1)

        Prt1 = "B_Idx_DegDiv = " + self.B_Idx_DegDiv
        print(Prt1)
        Prt2 = "B_Idx_Deg = " + str(self.B_Idx_Deg) + " deg"
        print(Prt2)

#######################################################################
# B_Set_Idx_Feed
# Purpose:              This is used to set the movement speed for the
#                       B axis.
# Updated:              ver 1.0, 21 July 2026, R. Colvin
# ---------------------------------------------------------------------
# Called from:
#   UI:                 REB_Panel
#   Button:             B_Feed
#   Signal:             GtkSpinButton/value-changed
# ---------------------------------------------------------------------
# Data
#   Read from UI:       B_Feed - Feed rate set by user
#   Program Variables
#       Referenced:
#       Set:            B_Feed
#   Written to UI:      (none)
# ---------------------------------------------------------------------
# Gcodes Called:        (none)
#######################################################################
    def B_Set_Idx_Feed(self,widget):

        print("=================================================")
        print("FUNCTION B_Set_Idx_Feed")

        self.B_Feed = widget.get_value()

        Prt1 = "B_Feed = " + str(self.B_Feed)
        print(Prt1)


# ********************************************************************
#    AA     LL       LL              AA    XX    XX EEEEEEEE  SSSSSS 
#   AAAA    LL       L              AAAA    XX  XX  EE       SSS   SS
#  AA  AA   LL       LL            AA  AA    XXXX   EE        SSS 
# AAAAAAAA  LL       LL           AAAAAAAA   XXXX   EEEEE        SSS 
# AA    AA  LL       LL           AA    AA  XX  XX  EE       SS    SS
# AA    AA  LLLLLLLL LLLLLLLL     AA    AA XX    XX EEEEEEEE  SSSSSS  
# ********************************************************************

#######################################################################
# OpenRoseEngineButlerWebsite
# Purpose:              This is used to open the Rose Engine Butler
#                       website.
# Updated:              ver 1.0, 6 August 2026, Claude
# ---------------------------------------------------------------------
# Called from:
#   UI:                 REB_Panel_v1
#   Button:             Open Library  (HAL_Button)
#   Signal:             GtkButton/pressed
# ---------------------------------------------------------------------
# Data
#   Read from UI:       (none)
#   Program Variables
#       Referenced:     (none)
#       Set:            (none)
#   Written to UI:      (none)
# ---------------------------------------------------------------------
# Gcodes Called:        (none)
#######################################################################
    def OpenRoseEngineButlerWebsite(self,widget):

        print("=================================================")
        print("FUNCTION OpenRoseEngineButlerWebsite")

        url = "https://roseenginebutler.com/"
        webbrowser.open(url)

        Prt1 = "Opening website " + url
        print(Prt1)

#######################################################################
# OpenGcodeLibrary
# Purpose:              This is used to open the Rose Engine Butler
#                       Gcode library web page.
# Updated:              ver 1.0, 21 July 2026, R. Colvin
# ---------------------------------------------------------------------
# Called from:
#   UI:                 REB_Tab_Help
#   Button:             Gcode_Library
#   Signal:             GtkButton/pressed
# ---------------------------------------------------------------------
# Data
#   Read from UI:       (none)
#   Program Variables
#       Referenced:     (none)
#       Set:            (none)
#   Written to UI:      (none)
# ---------------------------------------------------------------------
# Gcodes Called:        (none)
#######################################################################
    def OpenGcodeLibrary(self,widget):

        print("=================================================")
        print("FUNCTION OpenGcodeLibrary")

        url = "https://gcode.RoseEngineButler.com"
        webbrowser.open(url)

        Prt1 = "Opening website " + url
        print(Prt1)

#######################################################################
# OpenGcodeQuickReference
# Purpose:              This is used to open the LinuxCNC Gcode Quick
#                       Reference.
# Updated:              ver 1.0, 21 July 2026, R. Colvin
# ---------------------------------------------------------------------
# Called from:
#   UI:                 REB_Tab_Help
#   Button:             Gcode_QuickRef
#   Signal:             GtkButton/pressed
# ---------------------------------------------------------------------
# Data
#   Read from UI:       (none)
#   Program Variables
#       Referenced:     (none)
#       Set:            (none)
#   Written to UI:      (none)
# ---------------------------------------------------------------------
# Gcodes Called:        (none)
#######################################################################
    def OpenGcodeQuickReference(self,widget):

        print("=================================================")
        print("FUNCTION OpenGcodeQuickReference")

        url = "https://linuxcnc.org/docs/html/gcode.html"
        webbrowser.open(url)

        Prt1 = "Opening website " + url
        print(Prt1)

#######################################################################
# OpenPidTuningReference
# Purpose:              Opens LinuxCNC's own documentation for the pid
#                           HAL component (the control loop the Stepper
#                           Motor Tuning tab's P/I/D/FF0/FF1/FF2 spin
#                           buttons drive) in a web browser - the same
#                           content as the locally-installed `man pid`
#                           page, which is also where the per-widget
#                           tooltip text on that tab was sourced from.
# Updated:              ver 1.0, 1 August 2026, Claude
# ---------------------------------------------------------------------
# Called from:
#   UI:                 REB_Tab_Settings_v1
#   Button:              PID_Tuning_Reference  (GtkButton)
#   Signal:              GtkButton/clicked
#######################################################################
    def OpenPidTuningReference(self,widget):

        print("=================================================")
        print("FUNCTION OpenPidTuningReference")

        url = "https://linuxcnc.org/docs/html/man/man9/pid.9.html"
        webbrowser.open(url)

        Prt1 = "Opening website " + url
        print(Prt1)

#######################################################################
# OpenPidControllerWikipedia
# Purpose:              Opens Wikipedia's PID controller article -
#                           general background on what a PID controller
#                           is, separate from LinuxCNC's own
#                           pid-HAL-component-specific reference
#                           (OpenPidTuningReference above).
# Updated:              ver 1.0, 1 August 2026, Claude
# ---------------------------------------------------------------------
# Called from:
#   UI:                 REB_Tab_Settings_v1
#   Button:              PID_Controller_Wikipedia  (GtkButton)
#   Signal:              GtkButton/clicked
#######################################################################
    def OpenPidControllerWikipedia(self,widget):

        print("=================================================")
        print("FUNCTION OpenPidControllerWikipedia")

        url = "https://en.wikipedia.org/wiki/PID_controller"
        webbrowser.open(url)

        Prt1 = "Opening website " + url
        print(Prt1)

#######################################################################
# OpenLibrary
# Purpose:              This is used to open the Rose Engine Butler
#                       web page.
# Updated:              ver 1.0, 21 July 2026, R. Colvin
# ---------------------------------------------------------------------
# Called from:
#   UI:                 REB_Panel
#                       REB_Tab_Help
#                       REB_Tab_Settings
#   Button:             Library
#   Signal:             GtkButton/pressed
# ---------------------------------------------------------------------
# Data
#   Read from UI:       (none)
#   Program Variables
#       Referenced:     (none)
#       Set:            (none)
#   Written to UI:      (none)
# ---------------------------------------------------------------------
# Gcodes Called:        (none)
#######################################################################
    def OpenLibrary(self,widget):

        print("=================================================")
        print("FUNCTION OpenLibrary")

        url = "https://www.RoseEngineButler.com"
        webbrowser.open(url)

        Prt1 = "Opening website " + url
        print(Prt1)

#######################################################################
# OpenOTHandyBook
# Purpose:              This is used to open the Ornamental Turner's
#                       Handy Book
# Updated:              ver 1.0, 21 July 2026, R. Colvin
# ---------------------------------------------------------------------
# Called from:
#   UI:                 REB_Tab_Help
#   Button:             OT_HandyBook
#   Signal:             GtkButton/pressed
# ---------------------------------------------------------------------
# Data
#   Read from UI:       REB_Help
#   Program Variables
#       Referenced:     (none)
#       Set:            (none)
#   Written to UI:      (none)
# ---------------------------------------------------------------------
# Gcodes Called:        (none)
#######################################################################
    def OpenOTHandyBook(self,widget):

        print("=================================================")
        print("FUNCTION OpenOTHandyBook")

        url = "https://mdfre2.colvintools.com/Documents/OTHB.pdf"
        webbrowser.open(url)

        Prt1 = "Opening website " + url
        print(Prt1)

#######################################################################
# OpenUserForum
# Purpose:              This is used to open the Rose Engine Butler
#                       forum web page.
# Updated:              ver 1.0, 21 July 2026, R. Colvin
# ---------------------------------------------------------------------
# Called from:
#   UI:                 REB_Tab_Help
#   Button:             User_Forum
#   Signal:             GtkButton/pressed
# ---------------------------------------------------------------------
# Data
#   Read from UI:       REB_Help
#   Program Variables
#       Referenced:     (none)
#       Set:            (none)
#   Written to UI:      (none)
# ---------------------------------------------------------------------
# Gcodes Called:        (none)
#######################################################################
    def OpenUserForum(self,widget):

        print("=================================================")
        print("FUNCTION OpenUserForum")

        url = "https://RoseEngineButler.com/Forum"
        webbrowser.open(url)

        Prt1 = "Opening website " + url
        print(Prt1)

#######################################################################
# OpenUserManual
# Purpose:              This is used to open the Rose Engine Butler
#                       user manual web page.
# Updated:              ver 1.0, 21 July 2026, R. Colvin
# ---------------------------------------------------------------------
# Called from:
#   UI:                 REB_Tab_Help
#   Button:             User_Manual
#   Signal:             GtkButton/pressed
# ---------------------------------------------------------------------
# Data
#   Read from UI:       (none)
#   Program Variables
#       Referenced:     (none)
#       Set:            (none)
#   Written to UI:      (none)
# ---------------------------------------------------------------------
# Gcodes Called:        (none)
#######################################################################
    def OpenUserManual(self,widget):

        print("=================================================")
        print("FUNCTION OpenUserManual")

        url = "https://manual.RoseEngineButler.com"
        webbrowser.open(url)

        Prt1 = "Opening website " + url
        print(Prt1)

# ********************************************************************
#  SSSSSS  PPPPPPP  IIIIIIII N     NN DDDDDDD  LL       EEEEEEEE   0000
# SS    SS PP    PP    II    NN    NN DD    DD LL       EE        00  00
#  SSS     PP    PP    II    NNN   NN DD    DD LL       EEEEE    00    00
#     SSS  PPPPPPP     II    NN NN NN DD    DD LL       EE       00    00
# SS    SS PP          II    NN  NNNN DD    DD LL       EE        00  00
#  SSSSSS  PP       IIIIIIII NN    NN DDDDDDD  LLLLLLLL EEEEEEEE   0000
# ********************************************************************

#######################################################################
# Sp0_Move_Fwd
# Purpose:              This is used to start the spindles rotating
#                           forward.
#                       Note:  this starts both Sp0 and Sp1.
#                       Note:  sends M4, not M3 - see the Gcode0/Gcode1
#                           comment below. This is an intentional,
#                           empirically-verified swap, not a typo.
# Updated:              ver 1.2, 8 August 2026, Claude
# ---------------------------------------------------------------------
# Called from:
#   UI:                 REB_Panel
#   Button:             Sp0_Move_Fwd  (Hal_Button)
#   Signal:             GtkButton/pressed
# ---------------------------------------------------------------------
# Data
#   Read from UI:       (none)
#   Program Variables
#       Referenced:     self.Sp0_Feed
#                       self.Sp1_Pct
#       Set:            (none)
#   Written to UI:      (none)
# ---------------------------------------------------------------------
# Gcodes Called:        M4 (S combined on the same line - see below)
#######################################################################
    def Sp0_Move_Fwd(self,widget):

        print("=================================================")
        print("FUNCTION Sp0_Move_Fwd")

        # Ensure the system is in MDI mode - only switch if not already
        # there (matches _axis_idx_move/B_Move_Idx_Fwd/Sp0_Move_Idx_Fwd
        # etc.). This used to call c.mode(MODE_MDI) unconditionally on
        # every press, even when already in MDI mode from the previous
        # one - a redundant mode-switch no other handler in this file
        # does, and one a human typing directly into the AXIS MDI box
        # never triggers either. Re-entering MDI mode while already in
        # it is exactly the kind of thing that can carry an internal
        # abort/reset side effect in LinuxCNC's task controller, and was
        # removed as a suspect once the wait_complete()-between-mdi-calls
        # fix (see Gcode0/Gcode1 below) alone didn't resolve the spindle
        # 0 direction flip found via live halcmd pin tracing.
        s.poll()
        if s.task_state != linuxcnc.MODE_MDI:
                c.mode(linuxcnc.MODE_MDI)
                c.wait_complete() # Wait for mode change to complete

        # Set the feed rates
        Sp1_Feed = self.Sp1_Pct * self.Sp0_Feed / 100

        # Sends M4, not M3, despite this being the Fwd handler - an
        # empirical workaround, not a mistake. Live halcmd pin tracing
        # (spindle.0.forward/reverse/speed-out, which are motion-controller
        # output pins REB.hal/this file cannot influence) proved that
        # M3 $0 S<speed>, sent via this component's c.mdi(), reliably
        # commands spindle.0.reverse=TRUE / speed-out negative - i.e.
        # actual reverse rotation - while the byte-identical line typed
        # into the AXIS MDI box by hand, in the same live session,
        # reliably commands forward. Ruled out along the way: the S
        # value's sign (always positive), the "$-1"/all-spindles form
        # (replaced with per-spindle $0/$1 addressing), missing
        # wait_complete() between the two spindles' mdi() calls (fixed -
        # each now waits before the next is sent), and a redundant
        # unconditional c.mode(MODE_MDI) call this used to make on every
        # press (removed - now matches every other MDI-issuing handler's
        # conditional-only mode switch). None of those changed the
        # outcome, and manually replaying this exact two-line sequence
        # by hand did not reproduce the flip either - so whatever
        # actually causes it remains unexplained. Sending M4 here (and
        # M3 in Sp0_Move_Rev) is the pragmatic fix: it makes the physical
        # rotation match the button pressed, at the cost of the M-code
        # sent no longer matching the function name/button label.
        Gcode0 = "M4 $0 S" + str(self.Sp0_Feed)
        Gcode1 = "M4 $1 S" + str(Sp1_Feed)

        print(Gcode0)
        c.mdi(Gcode0)
        c.wait_complete()

        print(Gcode1)
        c.mdi(Gcode1)
        c.wait_complete()

    def _index_both_spindles_simultaneously(self, sign):
        '''
        Indexes Sp0 and Sp1 together, in the same servo-thread cycle,
        by driving orient.0/orient.1's target angle and trigger bit
        directly through the Sp0-idx-angle/Sp1-idx-angle and
        Sp0-idx-active/Sp1-idx-active HAL pins (see REB.hal's Sp0/Sp1
        blocks: mux2.2/mux2.3 select this angle over the M19-driven
        one, or2.0/or2.1 OR this active bit into the same enable chain
        M19 already used) - entirely bypassing M19/MDI, unlike the
        single-spindle path in Sp0_Move_Idx_Fwd/Rev.

        This exists because that M19 path is fundamentally sequential -
        LinuxCNC's M19 blocks the (single-threaded) interpreter until
        that spindle reports oriented, so a second M19 for the other
        spindle cannot even begin until the first returns. Queuing both
        back-to-back with only one final wait_complete() was tried and
        dropped Sp1's move entirely (see Sp0_Move_Idx_Fwd's git history).
        orient.0 and orient.1 are fully independent realtime components
        with their own PID loop each (pid.p0/pid.p1), so once both
        Active bits are set - each individual halcmd-style pin write
        only microseconds apart - both land well within the same or
        adjacent servo-thread cycle and both spindles move at once.

        sign is +1 for Sp0_Move_Idx_Rev (the Fwd/Rev handlers pass a
        swapped sign - see their docstrings), -1 for Sp0_Move_Idx_Fwd.
        Only called when both Sp0_Idx_Bool and Sp1_Idx_Bool are true
        (see callers).
        '''
        current_angle_0 = (hal.get_value('spindle.0-position-fb') % 1.0) * 360.0
        target_angle_0 = (current_angle_0 + sign * self.Sp0_Idx_Deg) % 360.0

        current_angle_1 = (hal.get_value('spindle.1-position-fb') % 1.0) * 360.0
        target_angle_1 = (current_angle_1 + sign * self.Sp0_Idx_Deg) % 360.0

        idx_log("Simultaneous index: Sp0 target=" + str(target_angle_0)
                + "  Sp1 target=" + str(target_angle_1))

        # Set both target angles first - orient.N samples position/angle
        # on Active's rising edge (see REB.hal comments) - then trigger
        # both together.
        self.halcomp['Sp0-idx-angle'] = target_angle_0
        self.halcomp['Sp1-idx-angle'] = target_angle_1
        self.halcomp['Sp0-idx-active'] = True
        self.halcomp['Sp1-idx-active'] = True

        try:
            deadline = time.time() + SIMULTANEOUS_INDEX_TIMEOUT
            sp0_done = False
            sp1_done = False
            while time.time() < deadline:
                if not sp0_done and hal.get_value('orient.0.is-oriented'):
                    sp0_done = True
                    idx_log("Sp0 oriented")
                if not sp1_done and hal.get_value('orient.1.is-oriented'):
                    sp1_done = True
                    idx_log("Sp1 oriented")
                if sp0_done and sp1_done:
                    break
                # Keep the GUI responsive while polling - same reason
                # _set_busy_cursor/_set_depressed force a repaint before
                # a blocking call takes over the main loop.
                while Gtk.events_pending():
                    Gtk.main_iteration()
                time.sleep(0.02)
            else:
                idx_log("Simultaneous index TIMED OUT - Sp0 oriented=" + str(sp0_done)
                        + " Sp1 oriented=" + str(sp1_done))
        finally:
            # Clear the trigger bits regardless of outcome - orient.N
            # only reacts to the next rising edge, so leaving Active
            # stuck True would just be a no-op until cleared and
            # re-raised anyway, but clearing it now keeps HAL state
            # consistent with "idle" for the next press.
            self.halcomp['Sp0-idx-active'] = False
            self.halcomp['Sp1-idx-active'] = False

#######################################################################
# Sp0_Move_Idx_Fwd
# Purpose:              This is used to index the Sp0 spindle in a
#                           forward direction.
#                       Note:  indexes toward a lower angle (sign -1),
#                           not higher, despite being the Fwd handler -
#                           see Sp0_Move_Fwd's docstring for the same
#                           empirically-verified swap applied here.
# Updated:              ver 1.1, 8 August 2026, Claude
# ---------------------------------------------------------------------
# Called from:
#   UI:                 REB_Panel
#   Button:             Sp0_Idx_Fwd
#   Signal:             GtkButton/pressed
# ---------------------------------------------------------------------
# Data
#   Read from UI:       (none)
#   Program Variables
#       Referenced:     self.Sp0_Idx_Deg
#                       self.Sp1_Pct
#       Set:            (none)
#   Written to UI:      B_Idx_Qty - the quantity of indexes so far.
#                           Forward increases this value.
# ---------------------------------------------------------------------
# Gcodes Called:        M19
#######################################################################
    def Sp0_Move_Idx_Fwd(self,widget):

        idx_log("=================================================")
        idx_log("FUNCTION Sp0_Move_Idx_Fwd")
        idx_log("Sp0_Idx_Bool = " + str(self.Sp0_Idx_Bool) + "  Sp1_Idx_Bool = " + str(self.Sp1_Idx_Bool))

        if not self.Sp0_Idx_Bool and not self.Sp1_Idx_Bool:
            idx_log("No spindle enabled - aborting move")
            _show_no_spindle_enabled_popup(widget)
            return

        _set_busy_cursor(widget, True)
        try:
            # Ensure the system is in MDI mode
            s.poll()
            if s.task_state != linuxcnc.MODE_MDI:
                    c.mode(linuxcnc.MODE_MDI)
                    c.wait_complete() # Wait for mode change to complete

            # Set spindle rotational speeds
            GcodeStr1 = "S0 " + str(self.Sp0_Feed)
            idx_log(GcodeStr1)

            Sp1_Feed = self.Sp0_Feed * self.Sp1_Pct / 100
            GcodeStr2 = "S1 " + str(Sp1_Feed)
            idx_log(GcodeStr2)

            c.mdi(GcodeStr1)
            c.mdi(GcodeStr2)

            if self.Sp0_Idx_Bool and self.Sp1_Idx_Bool:
                # Both selected - drive both spindles' orient chains
                # directly and simultaneously (see
                # _index_both_spindles_simultaneously) instead of two
                # sequential M19s. sign is -1, not +1 - see this
                # function's docstring.
                self._index_both_spindles_simultaneously(-1)
                return

            # M19 orients to an absolute angle, not a relative step, so compute
            # the next target from each spindle's own actual current angle
            # rather than sending Sp0_Idx_Deg itself as R each time (which
            # would just re-target the same fixed angle on every press). Only
            # one of Sp0_Idx_Bool/Sp1_Idx_Bool can be true here (the both-true
            # case already returned above), so exactly one of the two blocks
            # below runs - a spindle the operator hasn't enabled is simply
            # skipped rather than sent a command that can only time out.
            if self.Sp0_Idx_Bool:
                current_angle = (hal.get_value('spindle.0-position-fb') % 1.0) * 360.0
                target_angle = (current_angle - self.Sp0_Idx_Deg) % 360.0

                # NOTE: P0 = shortest path. Forcing a specific CW/CCW direction
                # (P1/P2) was tried and empirically always took the long ~270
                # deg way around to reach the same (correct) target angle -
                # see the live HAL trace analysis in conversation. P0 takes
                # the direct ~90 deg route to the same destination.
                GcodeStr3 = "M19 R" + str(target_angle) + " Q20 P0 $0"
                idx_log(GcodeStr3)
                c.mdi(GcodeStr3)
                c.wait_complete()
            else:
                idx_log("Sp0 M19 skipped (Sp0_Idx_Bool is False)")

            if self.Sp1_Idx_Bool:
                current_angle_1 = (hal.get_value('spindle.1-position-fb') % 1.0) * 360.0
                target_angle_1 = (current_angle_1 - self.Sp0_Idx_Deg) % 360.0

                GcodeStr4 = "M19 R" + str(target_angle_1) + " Q20 P0 $1"
                idx_log(GcodeStr4)
                c.mdi(GcodeStr4)
                c.wait_complete()
            else:
                idx_log("Sp1 M19 skipped (Sp1_Idx_Bool is False)")
        finally:
            _set_busy_cursor(widget, False)

#######################################################################
# Sp0_Move_Idx_Rev
# Purpose:              This is used to index the Sp0 spindle in a
#                           reverse direction.
#                       Note:  indexes toward a higher angle (sign +1),
#                           not lower, despite being the Rev handler -
#                           see Sp0_Move_Idx_Fwd/Sp0_Move_Fwd's
#                           docstrings for the same empirically-verified
#                           swap applied here.
# Updated:              ver 1.1, 8 August 2026, Claude
# ---------------------------------------------------------------------
# Called from:
#   UI:                 REB_Panel
#   Button:             Sp0_Idx_Rev
#   Signal:             GtkButton/pressed
# ---------------------------------------------------------------------
# Data
#   Read from UI:       (none)
#   Program Variables
#       Referenced:     self.Sp0_Idx_Deg
#                       self.Sp1_Pct
#       Set:            (none)
#   Written to UI:      B_Idx_Qty - the quantity of indexes so far.
#                           Forward increases this value.
# ---------------------------------------------------------------------
# Gcodes Called:        M19
#######################################################################
    def Sp0_Move_Idx_Rev(self,widget):

        idx_log("=================================================")
        idx_log("FUNCTION Sp0_Move_Idx_Rev")
        idx_log("Sp0_Idx_Bool = " + str(self.Sp0_Idx_Bool) + "  Sp1_Idx_Bool = " + str(self.Sp1_Idx_Bool))

        if not self.Sp0_Idx_Bool and not self.Sp1_Idx_Bool:
            idx_log("No spindle enabled - aborting move")
            _show_no_spindle_enabled_popup(widget)
            return

        _set_busy_cursor(widget, True)
        try:
            # Ensure the system is in MDI mode
            s.poll()
            if s.task_state != linuxcnc.MODE_MDI:
                    c.mode(linuxcnc.MODE_MDI)
                    c.wait_complete() # Wait for mode change to complete

            # Set spindle rotational speeds
            GcodeStr1 = "S0 " + str(self.Sp0_Feed)
            idx_log(GcodeStr1)

            Sp1_Feed = self.Sp0_Feed * self.Sp1_Pct / 100
            GcodeStr2 = "S1 " + str(Sp1_Feed)
            idx_log(GcodeStr2)

            c.mdi(GcodeStr1)
            c.mdi(GcodeStr2)

            if self.Sp0_Idx_Bool and self.Sp1_Idx_Bool:
                # Both selected - see matching branch in Sp0_Move_Idx_Fwd.
                # sign is +1, not -1 - see this function's docstring.
                self._index_both_spindles_simultaneously(+1)
                return

            # See Sp0_Move_Idx_Fwd for why the target is computed per-spindle
            # from live position, and why the checkboxes gate each M19 (only
            # one of Sp0_Idx_Bool/Sp1_Idx_Bool can be true past this point).
            if self.Sp0_Idx_Bool:
                current_angle = (hal.get_value('spindle.0-position-fb') % 1.0) * 360.0
                target_angle = (current_angle + self.Sp0_Idx_Deg) % 360.0

                # NOTE: P0 = shortest path - see matching note in Sp0_Move_Idx_Fwd.
                GcodeStr3 = "M19 R" + str(target_angle) + " Q20 P0 $0"
                idx_log(GcodeStr3)
                c.mdi(GcodeStr3)
                c.wait_complete()
            else:
                idx_log("Sp0 M19 skipped (Sp0_Idx_Bool is False)")

            if self.Sp1_Idx_Bool:
                current_angle_1 = (hal.get_value('spindle.1-position-fb') % 1.0) * 360.0
                target_angle_1 = (current_angle_1 + self.Sp0_Idx_Deg) % 360.0

                GcodeStr4 = "M19 R" + str(target_angle_1) + " Q20 P0 $1"
                idx_log(GcodeStr4)
                c.mdi(GcodeStr4)
                c.wait_complete()
            else:
                idx_log("Sp1 M19 skipped (Sp1_Idx_Bool is False)")
        finally:
            _set_busy_cursor(widget, False)

#######################################################################
# Sp0_Move_Rev
# Purpose:              This is used to start the spindles rotating in
#                           reverse.
#                       Note:  this starts both Sp0 and Sp1.
#                       Note:  sends M3, not M4 - see the Gcode0/Gcode1
#                           comment below (and Sp0_Move_Fwd's). This is
#                           an intentional, empirically-verified swap,
#                           not a typo.
# Updated:              ver 1.2, 8 August 2026, Claude
# ---------------------------------------------------------------------
# Called from:
#   UI:                 REB_Panel
#   Button:             Sp0_Move_Rev  (Hal_Button)
#   Signal:             GtkButton/pressed
# ---------------------------------------------------------------------
# Data
#   Read from UI:       (none)
#   Program Variables
#       Referenced:     self.Sp0_Feed
#                       self.Sp1_Pct
#       Set:            (none)
#   Written to UI:      (none)
# ---------------------------------------------------------------------
# Gcodes Called:        M3 (S combined on the same line - see below)
#######################################################################
    def Sp0_Move_Rev(self,widget):

        print("=================================================")
        print("FUNCTION Sp0_Move_Rev")

        # Ensure the system is in MDI mode - only switch if not already
        # there. See Sp0_Move_Fwd for why the previous unconditional
        # c.mode(MODE_MDI) call was removed.
        s.poll()
        if s.task_state != linuxcnc.MODE_MDI:
                c.mode(linuxcnc.MODE_MDI)
                c.wait_complete() # Wait for mode change to complete

        # In case the values had not already been written to the
        # Gcode S values, write them.
        Sp1_Feed = self.Sp1_Pct * self.Sp0_Feed / 100

        # Sends M3, not M4, despite this being the Rev handler - see the
        # Gcode0/Gcode1 comment in Sp0_Move_Fwd for the full explanation
        # (live pin tracing showed M4 here reliably commanding forward
        # rotation instead of reverse, with no root cause found after
        # ruling out S sign, "$-1" addressing, missing wait_complete()
        # between the two spindles' mdi() calls, and a redundant
        # unconditional mode switch). This is the matching pragmatic swap.
        Gcode0 = "M3 $0 S" + str(self.Sp0_Feed)
        Gcode1 = "M3 $1 S" + str(Sp1_Feed)

        print(Gcode0)
        c.mdi(Gcode0)
        c.wait_complete()

        print(Gcode1)
        c.mdi(Gcode1)
        c.wait_complete()

#######################################################################
# Move_Stop
# Purpose:              This is used to stop any movement.
# Updated:              ver 1.0, 21 July 2026, R. Colvin
# ---------------------------------------------------------------------
# Called from:
#   UI:                 REB_Panel
#   Buttons:            Sp0_Move_Stop  (Hal_Button)
#   Signal:             GtkButton/pressed
# ---------------------------------------------------------------------
# Data
#   Read from UI:       REB_Panel
#   Program Variables
#       Referenced:     (none)
#       Set:            (none)
#   Written to UI:      (none)
# ---------------------------------------------------------------------
# Gcodes Called:        M5
#######################################################################
    def Move_Stop(self,widget):

        print("=================================================")
        print("FUNCTION Move_Stop")

        # Ensure the system is in MDI mode
        s.poll()
        if s.task_state != linuxcnc.MODE_MDI:
                c.mode(linuxcnc.MODE_MDI)
                c.wait_complete() # Wait for mode change to complete

        # Send an MDI command to stop the spindles from rotating.
        Gcode = "M5"

        print(Gcode)
        c.mdi(Gcode)

        c.mdi("M5")

        # Wait for the command to complete
        c.wait_complete()

#######################################################################
# Sp0_Set_Feed
# Purpose:              This is used to set the base feed rate for the
#                           spindle (Sp0) & the rosette phaser
#                           multiplier (Sp1).  (Sp1 gets multiplied
#                           by the value of Sp1Pct
# Updated:              ver 1.0, 21 July 2026, R. Colvin
# ---------------------------------------------------------------------
# Called from:
#   UI:                 REB_Panel
#   Button:             Sp0_Set_Feed  (Hal_SpinButton)
#   Signal:             GtkSpinButton/value-changed
# ---------------------------------------------------------------------
# Data
#   Read from UI:       Sp0_Feed from Sp0_Spd on the UI
#   Program Variables
#       Referenced:     (none)
#       Set:            self.Sp0_Feed - the speed for the spindle
#                           (Sp0)
#   Written to UI:      (none)
# ---------------------------------------------------------------------
# Gcodes Called:        S
#######################################################################
    def Sp0_Set_Feed(self,widget):

        print("=================================================")
        print("FUNCTION Sp0_Set_Feed")

        self.Sp0_Feed = round(widget.get_value(), 1)
        print("self.Sp0_Feed = " + str(self.Sp0_Feed))

        # The spinbutton's arrows auto-repeat while held, firing
        # value-changed on every tick. c.mdi()/c.wait_complete() below
        # block the GTK main loop (same issue noted in _set_busy_cursor
        # and _axis_set_scale above), so sending them on every tick was
        # freezing the whole panel - including the spinbutton's own
        # on-screen digits - for as long as the button stayed held.
        # Debounce: only actually dispatch once the value has settled for
        # 150ms, so GTK is free to repaint between ticks.
        if self.Sp0_Feed_debounce_id is not None:
            GLib.source_remove(self.Sp0_Feed_debounce_id)
        self.Sp0_Feed_debounce_id = GLib.timeout_add(150, self._Sp0_Send_Feed)

    def _Sp0_Send_Feed(self):

        self.Sp0_Feed_debounce_id = None

        Sp1_Feed = round(self.Sp0_Feed * self.Sp1_Pct / 100, 2)

        Gcode0 = "S" + str(self.Sp0_Feed) + " $0"
        Gcode1 = "S" + str(Sp1_Feed) + " $1"

        # Ensure the system is in MDI mode
        s.poll()
        if s.task_state != linuxcnc.MODE_MDI:
                c.mode(linuxcnc.MODE_MDI)
                c.wait_complete() # Wait for mode change to complete

        # Send an MDI commands to set the spindle speeds.
        print(Gcode0)
        c.mdi(Gcode0)

        print(Gcode1)
        c.mdi(Gcode1)

        # Wait for the command to complete
        c.wait_complete()

        return False  # one-shot timeout, not a repeating GLib source

#######################################################################
# Sp0_Set_Idx_bW_DegDiv
# Purpose:              This is used to set the rotational distance
#                       measurement for the Sp0 & Sp1 spindles.
#                       If degrees, set to divisions; 
#                       if divisions, set to degrees.
# Updated:              ver 1.0, 21 July 2026, R. Colvin
# ---------------------------------------------------------------------
# Called from:
#   UI:                 REB_Panel
#   Button:             Sp0_Set_Idx_Deg  (HAL_RadioButton)
#                       Sp0_Set_Idx_Div  (HAL_RadioButton)
#   Signal:             GtkToggledButton/toggled
# ---------------------------------------------------------------------
# Data
#   Read from UI:       (none)
#   Program Variables
#       Referenced:     self.Sp0_Idx_Dist - distance field data
#       Set:            self.Sp0_Idx_Deg - degrees to index
#                       self.Sp0_Idx_DegDiv - type of distance
#                           measurement (Deg or Div)
#   Written to UI:      (none)
# ---------------------------------------------------------------------
# Gcodes Called:        (none)
#######################################################################
    def Sp0_Set_Idx_DegDiv(self,widget):

        idx_log("=================================================")
        idx_log("FUNCTION Sp0_Set_Idx_DegDiv")

        # Sp0_Set_Idx_bW_Deg and Sp0_Set_Idx_bW_Div are a GTK radio pair
        # sharing this one "toggled" handler - clicking either one fires
        # this handler TWICE (once for the button going active, once for
        # its paired sibling going inactive). Blindly flipping our own
        # mode flag on every call meant one click flipped it there and
        # back, net no-op - Div mode could never actually engage. Reading
        # the widget directly and ignoring the "going inactive" call fixes
        # it the same way the Sp0/Sp1 index checkboxes were fixed earlier.
        if not widget.get_active():
            idx_log("Sp0_Set_Idx_DegDiv ignored (widget going inactive)")
            return

        self.Sp0_Idx_DegDiv = "Div" if Gtk.Buildable.get_name(widget) == "Sp0_Set_Idx_bW_Div" else "Deg"

        if self.Sp0_Idx_DegDiv == "Div":
            self.Sp0_Idx_Deg = round(360 / self.Sp0_Idx_Dist, 1)
        else:
            self.Sp0_Idx_Deg = round(self.Sp0_Idx_Dist, 1)

        idx_log("Sp0_Idx_DegDiv = " + self.Sp0_Idx_DegDiv)
        idx_log("Sp0_Idx_Deg = " + str(self.Sp0_Idx_Deg))

#######################################################################
# Sp0_Set_Idx_Dist
# Purpose:              This is used to set the distance that and index
#                           operation moves the spindles(s).  This is
#                           used with self.Sp0_Idx_DegDiv to set the
#                           actual movement distance.
# Updated:              ver 1.0, 21 July 2026, R. Colvin
# ---------------------------------------------------------------------
# Called from:
#   UI:                 REB_Panel
#   Button:             Sp0_Set_Idx_Dist  (Hal_SpinButton)
#   Signal:             GtkSpinButton/value-changed
# ---------------------------------------------------------------------
# Data
#   Read from UI:       (none)
#   Program Variables
#       Referenced:     (none)
#       Set:            self.Sp0_Idx_Dist
#   Written to UI:      (none)
# ---------------------------------------------------------------------
# Gcodes Called:        (none)
#######################################################################
    def Sp0_Set_Idx_Dist(self,widget):

        idx_log("=================================================")
        idx_log("FUNCTION Sp0_Set_Idx_Dist")

        self.Sp0_Idx_Dist = round(widget.get_value(), 1)
        idx_log("self.Sp0_Idx_Dist = " + str(self.Sp0_Idx_Dist))

        # Sp0_Idx_Deg is what every M19 move actually uses, and it must
        # track the current Deg/Div mode here too - previously it was only
        # recalculated inside Sp0_Set_Idx_DegDiv (the mode toggle), so
        # changing the distance value while already in Div mode had no
        # effect on the actual move size until the mode was toggled again.
        if self.Sp0_Idx_DegDiv == "Div":
            self.Sp0_Idx_Deg = round(360 / self.Sp0_Idx_Dist, 1)
        else:
            self.Sp0_Idx_Deg = round(self.Sp0_Idx_Dist, 1)
        idx_log("self.Sp0_Idx_Deg = " + str(self.Sp0_Idx_Deg))

#######################################################################
# Sp0_Set_Idx_OnOff
# Purpose:              This is used to set the use of Sp1 indexing
#                           on or off.
# Updated:              ver 1.0, 21 July 2026, R. Colvin
# ---------------------------------------------------------------------
# Called from:
#   UI:                 REB_Panel
#   Button:             Sp0_Set_Idx_OnOff
#   Signal:             GtkToggleButton/toggled
# ---------------------------------------------------------------------
# Data
#   Read from UI:       (none)
#   Program Variables
#       Referenced:     (none)
#       Set:            self.Sp0_Idx_Bool
#   Written to UI:      (none)
# ---------------------------------------------------------------------
# Gcodes Called:        (none)
#######################################################################
    def Sp0_Set_Idx_OnOff(self,widget):

        idx_log("=================================================")
        idx_log("FUNCTION Sp0_Set_Idx_OnOff")

        # Read the checkbox's actual state rather than blindly flipping our
        # own flag - the "toggled" signal isn't guaranteed to fire exactly
        # once per user click, so blindly flipping let this drift out of
        # sync with what the checkbox visually shows.
        self.Sp0_Idx_Bool = widget.get_active()
        idx_log("Sp0_Idx_Bool = " + str(self.Sp0_Idx_Bool))

#######################################################################
# Sp0_Set_Scale
# Purpose:              This is used to set the scale distance for the
#                           Sp0 Spindle.
# Updated:              ver 1.0, 21 July 2026, R. Colvin
# ---------------------------------------------------------------------
# Called from:
#   UI:                 REB_Tab_Settings
#   Button:             Sp0_Set_Scale (on setting the value)
#   Signal:             HAL_SpinButton/value-changed
# ---------------------------------------------------------------------
# Data
#   Read from UI:       (none)
#   Program Variables
#       Referenced:     (none)
#       Set:            (none)
#   Written to UI:      (none)
# ---------------------------------------------------------------------
# Gcodes Called:        (none)
# ---------------------------------------------------------------------
# HAL Commands:         halcmd setp hm2_7i92.0.stepgen.04.position-scale
#                              (value)
#######################################################################
    def Sp0_Set_Scale(self,widget):

        print("=================================================")
        print("FUNCTION Sp0_Set_Scale")

        # Stop any Run Operation spindle rotation (M3/M4) before this
        # scale change lands - a large change to position-scale while
        # the spindle is actively spinning under S-word/M3/M4 control
        # could otherwise cause a runaway once the new scale takes
        # effect (see conversation).
        #
        # Only if the machine is actually ON: this handler also fires
        # from _load_scale_settings's programmatic spin.set_value() (the
        # startup auto-restore from REBset_v1.ini), which runs before
        # the operator has powered on/reset E-stop, when there's no
        # spinning spindle to stop anyway. Sending M5 unconditionally
        # there popped an "EMC_TASK_PLAN_EXECUTE cannot be executed
        # until the machine is out of E-stop and turned on" error dialog
        # at every startup.
        s.poll()
        if s.task_state == linuxcnc.STATE_ON:
            if s.task_state != linuxcnc.MODE_MDI:
                    c.mode(linuxcnc.MODE_MDI)
                    c.wait_complete()
            c.mdi("M5")
            c.wait_complete()
        else:
            print("Sp0_Set_Scale: machine not ON - skipping M5 (nothing to stop)")

        Sp0_Scale = round(widget.get_value(), 1)

        # Sp0_ENA-light belongs to the main panel's HAL component
        # ("gladevcp"); read it cross-component via halcmd. To disable
        # the axis, drive this component's own Sp0_Ena_Override pin
        # (ANDed with the panel button in RESp0_PostGUI.hal) instead of
        # trying to write another component's pin directly.
        status_pin = "gladevcp.Sp0_ENA-light"

        try:
            result = subprocess.run(
                ["halcmd", "getp", status_pin],
                check=True,
                capture_output=True,
                text=True
            )
            is_enabled = result.stdout.strip().upper() in ("TRUE", "1")
            print(status_pin + " = " + result.stdout.strip())

            if is_enabled:
                print("Sp0 axis is enabled - disabling")
                self.halcomp['Sp0_Ena_Override'] = False
            else:
                print("Sp0 axis is already disabled")
        except subprocess.CalledProcessError as e:
            print("Error checking " + status_pin + ": " + e.stderr)
        except FileNotFoundError:
            print("halcmd not found - is the LinuxCNC environment sourced?")

        # Send the new scale to the X axis stepgen via halcmd.
        hal_pin = "hm2_7i92.0.stepgen.06.position-scale"
        cmd = ["halcmd", "setp", hal_pin, str(Sp0_Scale)]

        try:
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True
            )
            print("Set " + hal_pin + " = " + str(Sp0_Scale))
        except subprocess.CalledProcessError as e:
            print("Error setting " + hal_pin + ": " + e.stderr)
        except FileNotFoundError:
            print("halcmd not found - is the LinuxCNC environment sourced?")

#######################################################################
# Sp0_Set_Ena
# Purpose:              See B_Set_Ena - same pattern, for Sp0.
#######################################################################
    def Sp0_Set_Ena(self,widget,*args):
        _clear_ena_override('Sp0')

# ********************************************************************
#  SSSSSS  PPPPPPP  IIIIIIII N     NN DDDDDDD  LL       EEEEEEEE  1111
# SS    SS PP    PP    II    NN    NN DD    DD LL       EE       11 11
#  SSS     PP    PP    II    NNN   NN DD    DD LL       EEEEE       11
#     SSS  PPPPPPP     II    NN NN NN DD    DD LL       EE          11
# SS    SS PP          II    NN  NNNN DD    DD LL       EE          11
#  SSSSSS  PP       IIIIIIII NN    NN DDDDDDD  LLLLLLLL EEEEEEEE 11111111
# ********************************************************************

#######################################################################
# Sp1_Set_Idx_Dist
# Purpose:              This is used to set the rotational distance
#                           (degrees) for the Sp1 spindle (the
#                           rosette phaser/multiplier).
# Updated:              ver 1.0, 21 July 2026, R. Colvin
# ---------------------------------------------------------------------
# Called from:
#   UI:                 REB_Panel
#   Button:             Sp1_Idx (on setting the value)
#   Signal:             GtkSpinButton/value-changed
# ---------------------------------------------------------------------
# Data
#   Read from UI:       Sp1_Idx
#   Program Variables
#       Referenced:     (none)
#       Set:            self.Sp1_Idx_Dist
#   Written to UI:      (none)
# ---------------------------------------------------------------------
# Gcodes Called:        (none)
#######################################################################
    def Sp1_Set_Idx_Dist(self,widget):

        print("=================================================")
        print("FUNCTION Sp1_Set_Idx_Dist")

        self.Sp1_Idx_Dist = widget.get_value()

#######################################################################
# Sp1_Set_Idx_OnOff
# Purpose:              This is used to set the use of Sp1 indexing
#                           on or off.
# Updated:              ver 1.0, 21 July 2026, R. Colvin
# ---------------------------------------------------------------------
# Called from:
#   UI:                 REB_Panel
#   Button:             Sp1_Set_Idx_OnOff
#   Signal:             GtkToggleButton/toggled
# ---------------------------------------------------------------------
# Data
#   Read from UI:       (none)
#   Program Variables
#       Referenced:     (none)
#       Set:            self.Sp1_Idx_Bool
#   Written to UI:      (none)
# ---------------------------------------------------------------------
# Gcodes Called:        (none)
#######################################################################
    def Sp1_Set_Idx_OnOff(self,widget):

        idx_log("=================================================")
        idx_log("FUNCTION Sp1_Set_Idx_OnOff")

        # See Sp0_Set_Idx_OnOff for why this reads the widget directly
        # instead of flipping a separately-tracked flag.
        self.Sp1_Idx_Bool = widget.get_active()
        idx_log("Sp1_Idx_Bool = " + str(self.Sp1_Idx_Bool))

#######################################################################
# Sp1_Set_Move_Pct
# Purpose:              This is used to set the speed for the rosette
#                           phaser / multiplier (Sp0) as a percentage
#                           of the spindle speed.
# Updated:              ver 1.0, 21 July 2026, R. Colvin
# ---------------------------------------------------------------------
# Called from:
#   UI:                 REB_Panel
#   Button:             Sp1_Set_Move_Pct  (Hal_SpinButton)
#   Signal:             GtkSpinButton/value-changed
# ---------------------------------------------------------------------
# Data
#   Read from UI:       (none)
#   Program Variables
#       Referenced:     (none)
#       Set:            self.Sp1_Pct
#   Written to UI:      (none)
# ---------------------------------------------------------------------
# Gcodes Called:        S
#######################################################################
    def Sp1_Set_Move_Pct(self,widget):

        print("=================================================")
        print("FUNCTION Sp1_Set_Move_Pct")

        self.Sp1_Pct = round(widget.get_value(), 2)
        print("self.Sp1_Pct = " + str(self.Sp1_Pct))

        # Same freeze as Sp0_Set_Feed (see that handler's comment): the
        # spinbutton arrows auto-repeat while held, and dispatching the
        # blocking c.mdi()/c.wait_complete() pair on every tick stalls the
        # GTK main loop long enough that the on-screen value looks stuck.
        # Debounce the actual dispatch instead.
        if self.Sp1_Pct_debounce_id is not None:
            GLib.source_remove(self.Sp1_Pct_debounce_id)
        self.Sp1_Pct_debounce_id = GLib.timeout_add(150, self._Sp1_Send_Pct)

    def _Sp1_Send_Pct(self):

        self.Sp1_Pct_debounce_id = None

        Sp1_Feed = round(self.Sp0_Feed * self.Sp1_Pct / 100, 2)
        Gcode1 = "S" + str(Sp1_Feed) + " $1"

        print("self.Sp0_Feed = " + str(self.Sp0_Feed))
        print("self.Sp1_Pct = " + str(self.Sp1_Pct))
        print("Sp1_Feed = " + str(Sp1_Feed))

        # Ensure the system is in MDI mode
        s.poll()
        if s.task_state != linuxcnc.MODE_MDI:
                c.mode(linuxcnc.MODE_MDI)
                c.wait_complete() # Wait for mode change to complete

        # Send an MDI command to set the spindle speed.
        print(Gcode1)
        c.mdi(Gcode1)

        # Wait for the command to complete
        c.wait_complete()

        return False  # one-shot timeout, not a repeating GLib source

#######################################################################
# Sp1_Set_Scale
# Purpose:              This is used to set the scale distance for the
#                           Sp1 Spindle.
# Updated:              ver 1.0, 21 July 2026, R. Colvin
# ---------------------------------------------------------------------
# Called from:
#   UI:                 REB_Tab_Settings
#   Button:             Sp1_Set_Scale (on setting the value)
#   Signal:             HAL_SpinButton/value-changed
# ---------------------------------------------------------------------
# Data
#   Read from UI:       (none)
#   Program Variables
#       Referenced:     (none)
#       Set:            (none)
#   Written to UI:      (none)
# ---------------------------------------------------------------------
# Gcodes Called:        (none)
# ---------------------------------------------------------------------
# HAL Commands:         halcmd setp hm2_7i92.0.stepgen.04.position-scale
#                              (value)
#######################################################################
    def Sp1_Set_Scale(self,widget):

        print("=================================================")
        print("FUNCTION Sp1_Set_Scale")

        # See Sp0_Set_Scale for why this stops Run Operation rotation
        # before the scale change lands, and why it's skipped when the
        # machine isn't ON (the startup auto-reload path).
        s.poll()
        if s.task_state == linuxcnc.STATE_ON:
            if s.task_state != linuxcnc.MODE_MDI:
                    c.mode(linuxcnc.MODE_MDI)
                    c.wait_complete()
            c.mdi("M5")
            c.wait_complete()
        else:
            print("Sp1_Set_Scale: machine not ON - skipping M5 (nothing to stop)")

        Sp1_Scale = round(widget.get_value(), 1)

        # Sp1_ENA-light belongs to the main panel's HAL component
        # ("gladevcp"); read it cross-component via halcmd. To disable
        # the axis, drive this component's own Sp1_Ena_Override pin
        # (ANDed with the panel button in RESp1_PostGUI.hal) instead of
        # trying to write another component's pin directly.
        status_pin = "gladevcp.Sp1_ENA-light"

        try:
            result = subprocess.run(
                ["halcmd", "getp", status_pin],
                check=True,
                capture_output=True,
                text=True
            )
            is_enabled = result.stdout.strip().upper() in ("TRUE", "1")
            print(status_pin + " = " + result.stdout.strip())

            if is_enabled:
                print("Sp1 axis is enabled - disabling")
                self.halcomp['Sp1_Ena_Override'] = False
            else:
                print("Sp1 axis is already disabled")
        except subprocess.CalledProcessError as e:
            print("Error checking " + status_pin + ": " + e.stderr)
        except FileNotFoundError:
            print("halcmd not found - is the LinuxCNC environment sourced?")

        # Send the new scale to the X axis stepgen via halcmd.
        hal_pin = "hm2_7i92.0.stepgen.07.position-scale"
        cmd = ["halcmd", "setp", hal_pin, str(Sp1_Scale)]

        try:
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True
            )
            print("Set " + hal_pin + " = " + str(Sp1_Scale))
        except subprocess.CalledProcessError as e:
            print("Error setting " + hal_pin + ": " + e.stderr)
        except FileNotFoundError:
            print("halcmd not found - is the LinuxCNC environment sourced?")

#######################################################################
# Sp1_Set_Ena
# Purpose:              See B_Set_Ena - same pattern, for Sp1.
#######################################################################
    def Sp1_Set_Ena(self,widget,*args):
        _clear_ena_override('Sp1')


#######################################################################
# __init__
# Purpose:              This is used to initialize everything.
# Updated:              ver 1.0, 21 July 2026, R. Colvin
#######################################################################
    def __init__(self, halcomp,builder,useropts):
        '''
        Handler classes are instantiated in the following state:
        - the widget tree is created, but not yet realized (no toplevel window.show() executed yet)
        - the halcomp HAL component is set up and the widhget tree's HAL pins have already been added to it
        - it is safe to add more hal pins because halcomp.ready() has not yet been called at this point.

        after all handlers are instantiated in command line and get_handlers() order, callbacks will be
        connected with connect_signals()/signal_autoconnect()

        The builder may be either of libglade or GtkBuilder type depending on the glade file format.
        '''

        self.halcomp        = halcomp
        self.builder        = builder
        self.nhits          = 0

        # Suppresses Measurement_System_Changed's save/patch/popup while
        # _load_measurement_system is itself the one driving the combo box
        # at startup (see combo.set_active there) - a startup load should
        # not re-save REB_Settings_v1.ini, re-patch REB.ini, or pop up the
        # restart notice.
        self._applying_measurement_system = False

        # Same suppression as _applying_measurement_system above, for
        # _load_device_names driving the Device Names text buffer at
        # startup.
        self._applying_device_names = False

        # Same suppression as _applying_measurement_system above, for
        # _load_max_jog_speed driving the Max Jog Speed spin button at
        # startup.
        self._applying_max_jog_speed = False

        # Same suppression as above, for _load_velocity_settings driving
        # the five VELOCITY_SETTINGS spin buttons at startup.
        self._applying_velocity_settings = False

        # Same suppression as above, for _load_axis_comments driving each
        # axis's comment combo box at startup.
        self._applying_axis_comments = False

        # Same suppression as above, for _load_channel_assignments (and
        # Channel_0N_Axis_Changed's own re-filtering rebuild - see
        # _rebuild_all_channel_combo_items) driving the six Axis Selection
        # combos.
        self._applying_channel_assignments = False

        _install_depress_css()

        # Independent pins this component owns, used to force each
        # axis disabled from this tab regardless of what the main
        # panel's own enable button is doing. Each defaults to "allow
        # enabled". ANDed with the panel button per-axis in
        # REB_PostGUI_v1.hal (REBCnfg.<Axis>_Ena_Override).
        #
        # HAL_IO, not HAL_OUT: this component's own Set_Scale handlers
        # clear an axis to False, but re-arming it happens from the main
        # panel's ENA button - a different process - via
        # `halcmd setp REBCnfg.<Axis>_Ena_Override TRUE` (see
        # _clear_ena_override). An OUT pin can only ever be driven by
        # its owning component; halcmd setp on one fails outright
        # ("pin is not writable"). IO allows the legitimate external
        # write while this component's own self.halcomp[...] = value
        # writes still work exactly the same as before.
        #
        # Per the GladeVCP docs, an output pin must be created via
        # hal_glib.GPin(halcomp.newpin(...)) - not a bare newpin() -
        # for writes through halcomp[name] = value to actually take
        # effect. The GPin objects are kept on self so they aren't
        # garbage-collected.
        self._ena_override_pins = {}
        for axis_id in AXIS_STEPGEN:
            pin_name = axis_id + "_Ena_Override"
            self._ena_override_pins[axis_id] = hal_glib.GPin(
                self.halcomp.newpin(pin_name, hal.HAL_BIT, hal.HAL_IO)
            )
            self.halcomp[pin_name] = True

        # Sp0-idx-angle/Sp1-idx-angle (float) and Sp0-idx-active/
        # Sp1-idx-active (bit) - drive orient.0/orient.1 directly,
        # bypassing M19/MDI, so Sp0_Move_Idx_Fwd/Rev can trigger both
        # spindles in the same servo cycle when both are selected for
        # indexing (see REB.hal's Sp0/Sp1 blocks: mux2.2/mux2.3 pick
        # this angle over the M19-driven one, or2.0/or2.1 OR this
        # active bit into the same enable chain M19 already used).
        # HAL_OUT (not IO): only this component (the main panel,
        # "gladevcp" - the only one with the Idx Fwd/Rev buttons) ever
        # drives these, so plain GPin output pins are enough - see
        # _ena_override_pins above for why GPin specifically (required
        # for halcomp[name] = value writes to take effect).
        self._sp_idx_pins = {}
        if self.builder.get_object("Sp0_Idx_Fwd") is not None:
            for spindle_id in ("Sp0", "Sp1"):
                angle_pin = spindle_id + "-idx-angle"
                active_pin = spindle_id + "-idx-active"
                self._sp_idx_pins[spindle_id + "_Angle"] = hal_glib.GPin(
                    self.halcomp.newpin(angle_pin, hal.HAL_FLOAT, hal.HAL_OUT)
                )
                self._sp_idx_pins[spindle_id + "_Active"] = hal_glib.GPin(
                    self.halcomp.newpin(active_pin, hal.HAL_BIT, hal.HAL_OUT)
                )
                self.halcomp[active_pin] = False

        # Restore persisted axis scale values (REB_Settings_v1.ini)
        # into the Settings tab's spin buttons and the real stepgen
        # scale pins. No-ops in every component other than the
        # Settings tab (REBHlp), which is the only one with these
        # widgets.
        self._load_scale_settings()

        # Restore persisted P/I/D/FF0/FF1/FF2 gains (REB_Settings_v1.ini)
        # into the Settings tab's PID spin buttons and the live pid.*
        # HAL gain pins. No-ops in every component other than the
        # Settings tab (REBCnfg), which is the only one with these
        # widgets.
        self._load_pid_settings()

        # Restore persisted backlash values (REB_Settings_v1.ini) into
        # the Settings tab's Backlash spin buttons and the live
        # joint.N.backlash HAL parameters. No-ops in every component
        # other than the Settings tab (REBCnfg), which is the only one
        # with these widgets.
        self._load_backlash_settings()

        # Restore persisted per-axis user comments (REB_Settings_v1.ini)
        # into the main panel's comment fields. No-ops in every
        # component other than the main panel (gladevcp), which is the
        # only one with these widgets.
        self._load_axis_comments()

        # Baseline for _autosave_axis_comments below - what's on screen
        # right after the load above already matches REB_Settings_v1.ini,
        # so there's nothing to flush until an operator actually changes
        # a field.
        self._last_saved_axis_comment = {
            axis_id: _combo_selected_device(widget)
            for axis_id in COMMENT_AXES
            for widget in [self.builder.get_object(axis_id + "_Comment")]
            if widget is not None
        }

        # Backstop for X_Comment/Z_Comment/etc.'s "changed" signal -
        # cheap insurance alongside it, on the same reasoning as the old
        # Entry-based "activate"/"focus-out-event" backstop this
        # replaced (a GtkComboBoxText's "changed" signal is a plain
        # same-process GTK signal with none of that focus-out-event's
        # cross-process reliability concerns, but polling every second
        # and only writing a field that actually changed since the last
        # flush costs nothing while idle). See _autosave_axis_comments.
        GLib.timeout_add(1000, self._autosave_axis_comments)

        # Restore the persisted Measurement System (REB_Settings_v1.ini)
        # into the Settings tab's combo box (if owned by this component)
        # and the unit-of-measure labels this component owns on either
        # the main panel or the Settings tab.
        self._load_measurement_system()

        # Restore the persisted device-name list (REBset_v1.ini) into
        # the General tab's Device Names text box (if owned by this
        # component).
        self._load_device_names()

        # Restore the persisted channel -> axis letter assignment
        # (REBset_v1.ini) into the Axis Selection tab's six combos (if
        # owned by this component).
        self._load_channel_assignments()

        # Restore the persisted Max Jog Speed (REB_Settings_v1.ini) into
        # the Settings tab's spin button (if owned by this component).
        self._load_max_jog_speed()

        # Restore the five persisted VELOCITY_SETTINGS values
        # (REB_Settings_v1.ini) into the Settings tab's jog-speed spin
        # buttons (if owned by this component).
        self._load_velocity_settings()

        # Let the mouse wheel scroll the page even when the cursor is
        # over one of its many spin buttons/combo boxes, rather than only
        # working over the shrinking gaps between them - see
        # _redirect_scroll_to_viewport. No-op wherever there's no
        # "viewport1" (every tab/panel other than the ones that embed a
        # GtkScrolledWindow).
        viewport = self.builder.get_object("viewport1")
        if viewport is not None:
            self._install_viewport_scroll_redirect(viewport)

        # Input pin fed from the existing "machine-is-on" HAL signal
        # (net machine-is-on => gladevcp.machine-is-on in
        # REB_PostGUI_v1.hal). Grays out the whole main panel grid
        # whenever the machine is not powered on. GPin.update() treats
        # any pin's first read after creation as a change (self._prev
        # starts as None), so this fires once automatically shortly
        # after startup even if the machine is already on - no need to
        # sync it manually here.
        self._machine_is_on_pin = hal_glib.GPin(
            self.halcomp.newpin("machine-is-on", hal.HAL_BIT, hal.HAL_IN)
        )
        self._machine_is_on_pin.connect('value-changed', self._on_machine_is_on_changed)

        ###############################################################
        # Global Program Variables - declare and set initial value.
        ###############################################################

        self.B_Feed         = 10.0      # B axis feed rate
        self.B_Idx_Deg      = 90.0      # B axis index degrees
        self.B_Idx_DegDiv   = "Deg"     # B axis index by degrees or divisions
        self.B_Idx_Dist     = 90.0      # B axis index distance
        self.B_Idx_Qty      = 0         # B axis index counter
        self.B_Move_Dist    = 0.0       # B axis move distance

        self.Sp0_Feed       = 1.0       # Sp0 Speed
        self.Sp0_Idx_Bool   = True      # Index this spindle? Default enabled at startup. The checkbox itself doesn't reliably render checked from the .ui file's active="True" alone (confirmed live) - _set_checkbox_active below forces it to match once the panel is up.
        self.Sp0_Idx_DegDiv = "Deg"     # Sp0 & Sp1 spindles: index by degrees or divisions
        self.Sp0_Idx_Deg    = 90.0      # Sp0 index degrees
        self.Sp0_Idx_Dist   = 90.0      # B axis index distance
        self.Sp0_Idx_Qty    = 0         # Sp0 axis index counter
        self.Sp0_Feed_debounce_id = None  # pending GLib timeout for Sp0_Set_Feed, see that handler

        self.Sp1_Idx_Bool   = False     # Index this spindle? See Sp0_Idx_Bool - the checkbox renders unchecked at launch regardless of the .ui default.
        self.Sp1_Idx_Dist   = 90.0      # Sp1 index degrees
        self.Sp1_Idx_Qty    = 0         # Sp1 axis index counter
        self.Sp1_Pct        = 100.0     # Sp1 speed percentage of Sp0 speed
        self.Sp1_Pct_debounce_id = None  # pending GLib timeout for Sp1_Set_Move_Pct, see that handler

        # Match the on-screen checkboxes to the defaults above (see
        # _set_checkbox_active for why this is deferred rather than done
        # here directly).
        GLib.idle_add(self._set_checkbox_active, 'Sp0_Set_Idx_OnOff', self.Sp0_Idx_Bool)
        GLib.idle_add(self._set_checkbox_active, 'Sp1_Set_Idx_OnOff', self.Sp1_Idx_Bool)

        # Keep the Run Operation tab's Fwd/Rev buttons showing pressed
        # for as long as the spindle is actually running that direction
        # (see _sync_run_operation_buttons). No-ops itself out after one
        # call in every component other than the main panel.
        GLib.timeout_add(100, self._sync_run_operation_buttons)

        # Per-axis state for the five linear axes (LINEAR_AXES, defined
        # below with the generated Idx_Minus/Set_Feed/etc. methods that
        # read/write these same attributes via getattr/setattr). B and
        # Sp0/Sp1 keep their own hand-written state above - not the same
        # shape (DegDiv fields, Idx_Bool checkboxes, no Move_Dist, etc.).
        for axis in LINEAR_AXES:
            setattr(self, axis + "_Feed", 1.0)
            setattr(self, axis + "_Idx_Dist", 0.0)
            setattr(self, axis + "_Idx_Qty", 0)
            setattr(self, axis + "_Move_Dist", 0.0)

# ------------------------------------------------------------------
# Generated per-axis handlers (linear axes: X, Z, U, V, W).
#
# Collapses the near-identical Idx_Minus/Idx_Plus/Set_Feed/Set_Idx_Dist/
# Set_Move_Dist/Set_Scale methods that used to be hand-written once per
# axis (see docs/hitcounter-review.md, Issue 1) into one factory function
# per pattern, looped over the axes and bound onto HandlerClass via
# setattr. This has to produce real, named methods rather than a
# __getattr__ dispatcher: GladeVCP discovers handlers via dir(instance)
# fed into builder.connect_signals(), and dir() does not enumerate names
# that only exist through __getattr__ - such a button would silently
# stop working with no error anywhere.
#
# All five linear axes migrated (X, Z, then U/V/W batched together once
# Z proved the new-behavior pattern live - see the refactor plan). B and
# Sp0/Sp1 stay hand-written above/below - different mechanisms entirely,
# not just axis-letter variations of this same pattern.
#
# Set_Ena IS generated here (revised 2026-07-28): initially thought dead
# (no .ui file wires a <signal> to any <Axis>_Set_Ena), but that's because
# the ENA buttons were redesigned from HAL_Button (which used a "pressed"
# signal - see B_Set_Ena's banner comment) to HAL_LightButton, which only
# emits "clicked" - the signal wiring was never carried over, silently
# orphaning _clear_ena_override()'s fix for the "press ENA and nothing
# happens, need a confusing second press" bug (see that function's own
# comments). The real fix is reconnecting REB_Panel_v1.ui's <Axis>_ENA
# widgets' "clicked" signal to <Axis>_Set_Ena, not deleting the method.

LINEAR_AXES = ("X", "Z", "U", "V", "W")  # all five linear axes migrated

def _axis_idx_move(axis, label, gcode_sign):
    '''
    label ("Minus"/"Plus") names the handler/button/print output;
    gcode_sign ("+"/"-") is the actual sign sent in the G-code. These
    are deliberately NOT tied together 1:1 below - see the LINEAR_AXES
    loop's comment for why (empirically-verified direction swap,
    mirroring the same fix applied to Sp0_Move_Fwd/Rev and
    Sp0_Move_Idx_Fwd/Rev). Keeping label driving the printed FUNCTION
    name and handler.__name__ means the console trace still matches
    whichever button was physically pressed.
    '''
    def handler(self, widget):
        print("=================================================")
        print("FUNCTION " + axis + "_Idx_" + label)

        # Depress the button for the duration of the move (see
        # _set_depressed for why this isn't a HAL_ToggleButton).
        _set_depressed(widget, True)
        try:
            s.poll()
            if s.task_state != linuxcnc.MODE_MDI:
                c.mode(linuxcnc.MODE_MDI)
                c.wait_complete()

            dist = getattr(self, axis + "_Idx_Dist")
            feed = getattr(self, axis + "_Feed")
            # The G-code axis word must be the CURRENTLY assigned letter
            # for this channel (CURRENT_LETTER), not the fixed internal
            # id "axis" - LinuxCNC only recognizes whatever letter is
            # actually in [TRAJ]COORDINATES right now (see REB_Setup/
            # REB_Generate_Local_Ini.py's _overlay_axis_assignment). All
            # other uses of "axis" in this function (attribute names,
            # handler naming) correctly stay the internal id.
            gcode_axis = CURRENT_LETTER.get(axis, axis.lower()).upper()
            Gcode = "G1 " + gcode_axis + gcode_sign + str(dist) + " F" + str(feed)

            print(Gcode)
            c.mdi(Gcode)
            c.wait_complete()
        finally:
            _set_depressed(widget, False)
    handler.__name__ = axis + "_Idx_" + label
    return handler

def _axis_set_feed(axis):
    def handler(self, widget):
        print("=================================================")
        print("FUNCTION " + axis + "_Set_Feed")
        setattr(self, axis + "_Feed", round(widget.get_value(), 1))
        print(axis + "_Set_Feed =")
        print(getattr(self, axis + "_Feed"))
    handler.__name__ = axis + "_Set_Feed"
    return handler

def _axis_set_idx_dist(axis):
    def handler(self, widget):
        print("=================================================")
        print("FUNCTION " + axis + "_Set_Idx_Dist")
        setattr(self, axis + "_Idx_Dist", widget.get_value())
        print(axis + "_Idx_Dist =")
        print(getattr(self, axis + "_Idx_Dist"))
    handler.__name__ = axis + "_Set_Idx_Dist"
    return handler

def _axis_set_move_dist(axis):
    def handler(self, widget):
        print("=================================================")
        print("FUNCTION " + axis + "_Set_Move_Dist")
        setattr(self, axis + "_Move_Dist", widget.get_value())
        print(axis + "_Move_Dist = " + str(getattr(self, axis + "_Move_Dist")))
    handler.__name__ = axis + "_Set_Move_Dist"
    return handler

def _axis_set_scale(axis):
    stepgen_ch = AXIS_STEPGEN[axis]
    hal_pin = "hm2_7i92.0.stepgen." + stepgen_ch + ".position-scale"
    status_pin = "gladevcp." + axis + "_ENA-light"
    def handler(self, widget):
        print("=================================================")
        print("FUNCTION " + axis + "_Set_Scale")

        # Cancel any in-progress move (e.g. <Axis>_Idx_Plus/Minus) before
        # this scale change lands - a large change to position-scale
        # while a coordinated move is still executing could otherwise
        # leave the physical axis somewhere unexpected once the new
        # scale takes effect (same class of risk as the Run Operation
        # spindle case - see conversation). This guards an independently
        # running G-code program or another MDI source, not this same
        # click handler's own MDI call - that can't be concurrent, since
        # c.mdi()/c.wait_complete() block the GTK loop this click needs
        # to be processed by.
        c.abort()
        c.wait_complete()

        scale = round(widget.get_value(), 1)

        # <Axis>_ENA-light belongs to the main panel's HAL component
        # ("gladevcp"); read it cross-component via halcmd. To disable
        # the axis, drive this component's own <Axis>_Ena_Override pin
        # (ANDed with the panel button in REB_PostGUI_v1.hal) instead of
        # trying to write another component's pin directly.
        try:
            result = subprocess.run(
                ["halcmd", "getp", status_pin],
                check=True,
                capture_output=True,
                text=True
            )
            is_enabled = result.stdout.strip().upper() in ("TRUE", "1")
            print(status_pin + " = " + result.stdout.strip())

            if is_enabled:
                print(axis + " axis is enabled - disabling")
                self.halcomp[axis + '_Ena_Override'] = False
            else:
                print(axis + " axis is already disabled")
        except subprocess.CalledProcessError as e:
            print("Error checking " + status_pin + ": " + e.stderr)
        except FileNotFoundError:
            print("halcmd not found - is the LinuxCNC environment sourced?")

        # Send the new scale to the axis's stepgen via halcmd.
        cmd = ["halcmd", "setp", hal_pin, str(scale)]
        try:
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True
            )
            print("Set " + hal_pin + " = " + str(scale))
        except subprocess.CalledProcessError as e:
            print("Error setting " + hal_pin + ": " + e.stderr)
        except FileNotFoundError:
            print("halcmd not found - is the LinuxCNC environment sourced?")
    handler.__name__ = axis + "_Set_Scale"
    return handler

def _axis_set_ena(axis):
    def handler(self, widget, *args):
        _clear_ena_override(axis)
    handler.__name__ = axis + "_Set_Ena"
    return handler

for _axis in LINEAR_AXES:
    # Idx_Minus sends "+" and Idx_Plus sends "-" - swapped relative to
    # each button's own name, but NOT relative to its icon (X/U/V/Z/W's
    # Idx_Minus/Idx_Plus icons are confirmed correct - see the earlier
    # pixbuf revert). Empirically-verified fix: live testing showed all
    # five linear axes moving the physically wrong way relative to their
    # (correct) icons, the same class of bug already found and fixed for
    # the spindles' Fwd/Rev and Idx_Fwd/Idx_Rev via live halcmd pin
    # tracing - see Sp0_Move_Fwd's docstring for that investigation.
    setattr(HandlerClass, _axis + "_Idx_Minus", _axis_idx_move(_axis, "Minus", "+"))
    setattr(HandlerClass, _axis + "_Idx_Plus",  _axis_idx_move(_axis, "Plus",  "-"))
    setattr(HandlerClass, _axis + "_Set_Feed", _axis_set_feed(_axis))
    setattr(HandlerClass, _axis + "_Set_Ena", _axis_set_ena(_axis))
    setattr(HandlerClass, _axis + "_Set_Idx_Dist", _axis_set_idx_dist(_axis))
    setattr(HandlerClass, _axis + "_Set_Move_Dist", _axis_set_move_dist(_axis))
    setattr(HandlerClass, _axis + "_Set_Scale", _axis_set_scale(_axis))
del _axis

def _axis_set_backlash(axis):
    '''
    Generic value-changed handler for a single axis's/spindle's
    Backlash spin button: pushes the new value straight to the live
    joint.N.backlash HAL parameter (motion's own per-joint backlash
    compensation - see JOINT_NUMBER above). Unlike _axis_set_scale,
    there's no need to disable the axis first - same reasoning as
    _pid_set below: a backlash change is safe to make on the fly, it
    doesn't invalidate an in-progress move the way a scale change can.

    REB_Settings_v1.ini itself is not written here - same as scale/PID,
    that only happens at shutdown (REB_Scale_Persist.py reading the
    live HAL pins), not on every keystroke/spin-click.
    '''
    hal_pin = "joint." + str(JOINT_NUMBER[axis]) + ".backlash"
    def handler(self, widget):
        value = widget.get_value()
        try:
            subprocess.run(
                ["halcmd", "setp", hal_pin, str(value)],
                check=True,
                capture_output=True,
                text=True
            )
            print("Set " + hal_pin + " = " + str(value))
        except subprocess.CalledProcessError as e:
            print("Error setting " + hal_pin + ": " + e.stderr)
        except FileNotFoundError:
            print("halcmd not found - is the LinuxCNC environment sourced?")
    handler.__name__ = axis + "_Set_Backlash"
    return handler

for _axis_id in JOINT_NUMBER:
    setattr(HandlerClass, _axis_id + "_Set_Backlash", _axis_set_backlash(_axis_id))
del _axis_id

def _channel_axis_changed(channel_id):
    '''
    Generic "changed" handler for one Axis Selection combo. Records the
    new choice and refreshes every combo/Type label
    (_rebuild_all_channel_combo_items) - every letter is always
    selectable now, duplicates are no longer prevented at the dropdown.
    Instead, _update_duplicate_warnings flags every channel currently
    sharing a letter; as long as any duplicate remains, this handler
    deliberately does NOT persist the assignment or show the restart
    notice - both only happen once the whole assignment is duplicate-
    free, at which point they fire on that clearing change, matching
    Measurement_System_Changed's save-immediately/apply-on-restart
    pattern (since [TRAJ]COORDINATES/[AXIS_*]TYPE are read once at
    LinuxCNC startup the same way LINEAR_UNITS is - see REB_Setup/
    REB_Generate_Local_Ini.py).
    '''
    def handler(self, widget):
        if self._applying_channel_assignments:
            return

        letter = widget.get_active_text()
        if letter not in AXIS_SELECTION_LETTERS:
            return

        self._channel_assignments[channel_id] = letter

        self._applying_channel_assignments = True
        self._rebuild_all_channel_combo_items()
        self._applying_channel_assignments = False

        if self._update_duplicate_warnings():
            return

        _save_channel_assignments(self._channel_assignments)
        _show_restart_required_popup(
            widget,
            "The axis assignment change will not take effect until you "
            "exit and restart LinuxCNC. Make sure the physical motor "
            "cable for this channel actually matches the letter you just "
            "assigned before restarting."
        )
    handler.__name__ = "Channel_" + channel_id + "_Axis_Changed"
    return handler

for _channel_id in CHANNEL_DEFAULT_LETTER:
    setattr(HandlerClass, "Channel_" + _channel_id + "_Axis_Changed", _channel_axis_changed(_channel_id))
del _channel_id

def _pid_set(hal_pin):
    '''
    Generic value-changed handler for a single P/I/D/FF0/FF1/FF2 spin
    button: pushes the new value straight to the live pid.* HAL gain
    pin. Unlike _axis_set_scale, there's no need to disable the axis
    first - a PID gain is safe to retune on the fly, it doesn't
    invalidate an in-progress move the way a scale change can.

    REB_Settings_v1.ini itself is not written here - same as scale,
    that only happens when the operator clicks Save Settings, or
    automatically at shutdown (REB_Scale_Persist.py reading the live
    HAL pins), not on every keystroke/spin-click.
    '''
    def handler(self, widget):
        value = widget.get_value()
        try:
            subprocess.run(
                ["halcmd", "setp", hal_pin, str(value)],
                check=True,
                capture_output=True,
                text=True
            )
            print("Set " + hal_pin + " = " + str(value))
        except subprocess.CalledProcessError as e:
            print("Error setting " + hal_pin + ": " + e.stderr)
        except FileNotFoundError:
            print("halcmd not found - is the LinuxCNC environment sourced?")
    return handler

for _axis_id, _component in PID_AXES.items():
    for _param in PID_PARAMS:
        _widget_id = _axis_id + "_Set_" + _param
        _handler = _pid_set(_component + "." + PID_PARAM_PIN[_param])
        _handler.__name__ = _widget_id
        setattr(HandlerClass, _widget_id, _handler)
del _axis_id, _component, _param, _widget_id, _handler

for _spindle_id, _loops in PID_SPINDLE_LOOPS.items():
    for _suffix, _component in _loops.items():
        for _param in PID_PARAMS:
            _widget_id = _spindle_id + "_Set_" + _param + "_" + _suffix
            _handler = _pid_set(_component + "." + PID_PARAM_PIN[_param])
            _handler.__name__ = _widget_id
            setattr(HandlerClass, _widget_id, _handler)
del _spindle_id, _loops, _suffix, _component, _param, _widget_id, _handler

def _velocity_setting_changed(tag):
    '''
    Generic value-changed handler for one of VELOCITY_SETTINGS' spin
    buttons: persists to REB_Settings_v1.ini and warns that a restart is
    needed, same as Max_Jog_Speed_Changed - these are read once by
    LinuxCNC at process startup (see REB_Setup/REB_Generate_Local_Ini.py),
    not live HAL pins, so there's no halcmd setp to also do here.
    '''
    def handler(self, widget):
        if self._applying_velocity_settings:
            return
        value = widget.get_value()
        _save_velocity_setting(tag, value)
        _show_restart_required_popup(
            widget,
            "This change will not take effect until you exit and restart LinuxCNC."
        )
    return handler

for _widget_id, (_tag, _default) in VELOCITY_SETTINGS.items():
    _handler = _velocity_setting_changed(_tag)
    _handler.__name__ = _widget_id + "_Changed"
    setattr(HandlerClass, _widget_id + "_Changed", _handler)
del _widget_id, _tag, _default, _handler

def get_handlers(halcomp,builder,useropts):
    '''
    this function is called by gladevcp at import time (when this module is passed with '-u <modname>.py')

    return a list of object instances whose methods should be connected as callback handlers
    any method whose name does not begin with an underscore ('_') is a  callback candidate

    the 'get_handlers' name is reserved - gladevcp expects it, so do not change
    '''
    return [HandlerClass(halcomp,builder,useropts)]

#
