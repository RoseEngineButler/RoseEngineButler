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
import json
from gi.repository import Gdk
from gi.repository import Gtk
from gi.repository import GLib
import reb_settings_io

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
# used on this machine).
AXIS_SELECTION_LETTERS = ("X", "Z", "U", "V", "W", "A", "B", "C")

# The axis letter -> Type rule: A/B/C are angular, everything else is
# linear. Was briefly an independent, per-channel operator choice via
# the Axis Selection tab's Type combo (REBset_v1.ini's "channel_types"
# field) between 3 and 4 September 2026; that feature was retired the
# same week it shipped (nothing in the current UI can ever set an
# independent type again), so this is now simply the one and only
# source of truth. Mirrors REB_Setup/REB_Generate_Local_Ini.py's and
# REB_Display/reb_settings_io.py's own copies of this same rule.
def _axis_type_for_letter(letter):
    # CURRENT_LETTER's values are lowercase (see below) and most call
    # sites pass those straight through without their own .upper() -
    # case-fold here so this stays correct regardless of caller casing.
    return "ANGULAR" if letter.upper() in ("A", "B", "C") else "LINEAR"

# Letter -> the same foreground color REB_Panel_v1.ui's original per-axis
# DRO/jog labels already use for that letter (X/U share one color, Z/W
# share another, V/B share a third - grouped by mechanical relationship,
# e.g. "U is parallel to X" per the AXIS CONVENTIONS text), extended to
# cover A/C (not present elsewhere in the panel) by following the same
# X/Z/V groupings the Axis Selection tab already applies for TYPE
# (A angular like B, but grouped with X/U's color here; C angular like B,
# grouped with Z/W's color) - used by _load_panel_axis_display to color
# the main panel's read-only "Axis Assignments" letters the same way.
AXIS_LETTER_COLOR = {
    "X": "#e5e5a5a50a0a",
    "U": "#e5e5a5a50a0a",
    "A": "#e5e5a5a50a0a",
    "V": "#a5a51d1d2d2d",
    "B": "#a5a51d1d2d2d",
    "Z": "#1a1a5f5fb4b4",
    "W": "#1a1a5f5fb4b4",
    "C": "#1a1a5f5fb4b4",
}

# Internal id -> the two jog button widget ids REB_Panel_v1.ui actually
# has for that channel (fixed forever - widgets are never renamed).
# Column 12 always sends G-code sign "-", column 13 always sends "+" -
# see JOG_NEG_HANDLER/JOG_POS_HANDLER's comment for why one factory can
# serve both naming patterns. Only B's widget ids (B_Idx_Fwd/B_Idx_Rev)
# differ from the rest's <letter>_Idx_Plus/<letter>_Idx_Minus pattern -
# note these are the WIDGET ids, not the handler method names
# (JOG_NEG_HANDLER["B"] is "B_Move_Idx_Fwd", the method the B_Idx_Fwd
# widget's "pressed" signal is wired to).
JOG_NEG_WIDGET = {
    "X": "X_Idx_Plus", "Z": "Z_Idx_Plus", "U": "U_Idx_Plus",
    "V": "V_Idx_Plus", "W": "W_Idx_Plus", "B": "B_Idx_Fwd",
}
JOG_POS_WIDGET = {
    "X": "X_Idx_Minus", "Z": "Z_Idx_Minus", "U": "U_Idx_Minus",
    "V": "V_Idx_Minus", "W": "W_Idx_Minus", "B": "B_Idx_Rev",
}

# Axis letter -> (column-12/"-" image filename, column-13/"+" image
# filename), both under REB_Display/Images/. U/V/W intentionally reuse
# their parallel axis's images (U parallel to X, V parallel to Y, W
# parallel to Z - see the AXIS CONVENTIONS text on the main panel). The
# three rotary letters (A/B/C) are inverted relative to their own
# dedicated images' nominal pos/neg naming (confirmed live) - i.e. the
# "-" button shows that letter's "pos" image and vice versa.
#
# Z fixed 22 August 2026 (Rich, confirmed live): Z's "-"/"+" images were
# swapped relative to their nominal Axis-Z{neg,pos}.png naming - the
# opposite of every other linear letter (X/U's "-" shows *neg, "+" shows
# *pos), which made Z's jog buttons visually point at each other instead
# of toward the direction each one actually jogs. W's mapping was left
# untouched (confirmed correct as-is) - it now happens to equal Z's
# corrected mapping exactly, rather than being Z's inverse as it
# appeared to be before this fix.
AXIS_JOG_IMAGE = {
    "X": ("Axis-Xneg.png", "Axis-Xpos.png"),
    "Z": ("Axis-Zpos.png", "Axis-Zneg.png"),
    "U": ("Axis-Xneg.png", "Axis-Xpos.png"),
    "V": ("Axis-Yneg.png", "Axis-Ypos.png"),
    "W": ("Axis-Zpos.png", "Axis-Zneg.png"),
    "A": ("Axis-Apos.png", "Axis-Aneg.png"),
    "B": ("Axis-Bpos.png", "Axis-Bneg.png"),
    "C": ("Axis-Cpos.png", "Axis-Cneg.png"),
}

# Type -> numeric range/precision/default profile for a channel's Feed
# and Idx (jog-increment) adjustments. "feed" is (lower, upper, step,
# digits, default_value). Angular feed range is +/-6000 deg/min (100
# deg/sec, Rich's requested working max speed - 27 August 2026) with a
# 360 deg/min default value (Rich, 3 September 2026); linear stays
# +/-10 in-or-mm/min with a 1 default, matching every linear channel's
# original shipped value. Idx has no default_value entry - its initial
# value (0) is fine for both types, only Feed's misleadingly-low static
# "1" default (REB_Panel_v1.ui) needed fixing here. Applied by
# _load_panel_axis_controls so a reassigned channel's controls behave
# correctly for its new type, not its old one - this is the actual
# runtime source of truth for these ranges; REB_Panel_v1.ui's own
# GtkAdjustment lower/upper/value properties are overwritten by this
# profile the moment the main panel component loads, so they matter
# only until then.
TYPE_ADJUSTMENT_PROFILE = {
    "LINEAR":  {"feed": (-10, 10, 0.01, 3, 1), "idx": (25, 0.01, 3)},
    "ANGULAR": {"feed": (-6000, 6000, 0.01, 3, 360), "idx": (720, 0.10, 2)},
}

def _save_channel_assignments(assignments):
    '''
    Persists the Axis Selection tab's channel -> axis letter choices into
    REBset_v1.ini's "channel_assignments" dict. assignments is a dict of
    channel id ("00".."05") -> letter; any channel missing from it falls
    back to CHANNEL_DEFAULT_LETTER.
    '''
    settings = reb_settings_io.load_settings()
    settings["channel_assignments"] = {
        channel_id: assignments.get(channel_id, CHANNEL_DEFAULT_LETTER[channel_id])
        for channel_id in sorted(CHANNEL_DEFAULT_LETTER)
    }
    reb_settings_io.save_settings(settings)
    print("Saved channel assignments: " + str(settings["channel_assignments"]))

def _read_persisted_channel_assignments():
    '''
    Reads the persisted channel -> axis letter map, falling back to
    CHANNEL_DEFAULT_LETTER for any channel whose entry is missing or
    unrecognized - same "absent -> shipped default" convention as
    _load_measurement_system. Used by the Settings tab to populate the 6
    Axis Selection combos at startup, by CURRENT_LETTER below (module
    load time), and duplicated (rather than imported - see AXIS_STEPGEN
    below for why) in REB_Scale_Persist.py and REB_Setup/
    REB_Generate_Local_Ini.py.
    '''
    assignments = dict(CHANNEL_DEFAULT_LETTER)
    stored = reb_settings_io.load_settings().get("channel_assignments", {})
    for channel_id, letter in stored.items():
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

# Internal id -> this session's actual current Type ("LINEAR"/
# "ANGULAR"), derived purely from CURRENT_LETTER via
# _axis_type_for_letter - the live source of truth everywhere TYPE
# matters at runtime (feed/idx adjustment ranges, deg-vs-inch unit
# labels, jog-increment G-code amount). Was briefly computed from an
# independent per-channel Type choice (REBset_v1.ini's "channel_types",
# read via the now-deleted _read_persisted_channel_types) between 3 and
# 4 September 2026; that feature was retired the same week it shipped,
# reverting this to its original letter-derived form.
CURRENT_TYPE = {
    internal_id: _axis_type_for_letter(letter)
    for internal_id, letter in CURRENT_LETTER.items()
}

# Internal id -> HAL `pid` component instance driving that axis's PID
# loop right now (see CURRENT_LETTER above for why this can't be a
# static dict, and PID_SPINDLE_LOOPS below for Sp0/Sp1's own loops).

# Reverse of CURRENT_LETTER: currently-assigned axis letter (uppercase)
# -> internal id of whichever physical channel is driving it right now,
# if any - used to resolve EXTRA_SETTINGS_LETTERS' live HAL pin below.
CURRENT_LETTER_INTERNAL_ID = {letter.upper(): internal_id for internal_id, letter in CURRENT_LETTER.items()}

# Settings-tab Axis Scaling rows with no fixed physical channel of their
# own (see CHANNEL_DEFAULT_LETTER) - added so an operator can
# pre-configure/retain a Scale value for an A/C attachment even while it
# isn't currently plugged into any channel ("no need for this page to
# only show the 'selected axes'"). Persisted in REBset_v1.ini as
# <axis id="A">/<axis id="C"> blocks, independent of the six physical
# channels' own blocks - see _load_scale_settings and
# _axis_set_scale_letter below, and REB_Scale_Persist.py's mirror of
# this same constant.

# Spindle id -> {"Pos": position-loop component, "Vel": velocity-loop
# component}. The suffix ("Pos"/"Vel") matches the Settings tab widget
# id suffix (e.g. Sp0_Set_P_Pos, Sp0_Set_P_Vel) and the REB_Settings_v1.ini
# block tag ("pid_pos"/"pid_vel").

# Settings tab field name -> HAL pid component pin name. Order matches
# the P/I/D/FF0/FF1/FF2 column order in REB_Tab_Settings_v1.ui's
# "Stepper Motor Settings" grid.

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
    # netted *_Ena_Override pin (see REB_PostGUI_v1.hal) is written from
    # the standalone REB_Settings program, a different process (before
    # 4 September 2026 this was the embedded Settings tab's own
    # component, "REBCnfg" - now retired). Cross the process boundary
    # via halcmd instead, the same way REB_Settings's own Scale handlers
    # already do in the other direction for *_ENA-light.
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



def _read_persisted_device_names():
    '''
    Reads the persisted device-name list straight from SETTINGS_PATH
    (REBset_v1.ini's "device_names" list) - the on-disk counterpart to
    HandlerClass._read_device_names, which reads the live Settings tab's
    Device_Names GtkTextView instead. Used wherever a component needs
    this list but doesn't own that widget - e.g. the main panel
    populating each axis's Comment combo box at startup, since the main
    panel and Settings tab are separate gladevcp processes with no live
    IPC between them (see CLAUDE.md). Returns [] if the file can't be
    read or has no device_names list.
    '''
    return list(reb_settings_io.load_settings().get("device_names", []))

def _read_persisted_axis_comment(axis_id, settings):
    '''
    Extracts one axis's persisted usercomment value out of an
    already-loaded settings dict. Shared by _load_axis_comments (main
    panel, restoring its own Device combos at startup) and
    _run_export_selection_dialog (Settings tab, defaulting each axis's
    Export dialog Device combo to whatever's currently set on the main
    panel) - REBset_v1.ini's usercomment is the only channel between
    those two separate gladevcp processes (see CLAUDE.md). Returns ""
    if the axis or its usercomment isn't found.
    '''
    return settings.get("axes", {}).get(axis_id, {}).get("usercomment", "")

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
# Also carries the three reb-axis-* label color classes used by
# _load_panel_axis_controls to recolor a channel row's letter label to
# match its currently assigned letter (AXIS_LETTER_COLOR's three
# distinct colors, converted from GTK's 16-bit-per-channel #RRRRGGGGBBBB
# hex to CSS's 8-bit #RRGGBB - e.g. #e5e5a5a50a0a -> #e5a50a). A plain
# label.set_markup() with a <span foreground="..."> was tried first and
# didn't work here: REB_Panel_v1.ui's <letter>_Letter labels each have
# their OWN static per-widget Pango <attributes> block (font-desc/
# weight/foreground, straight from the original hand-authored panel).
# That's a separate, widget-level Pango attribute list applied by
# GtkLabel itself, layered ON TOP OF CSS when rendering - it can (and
# here, did - confirmed live: the text updated correctly, the color
# didn't) win over a CSS or markup-supplied foreground for the same
# text. _load_panel_axis_controls clears that static attribute list
# (set_attributes(None)) before applying this CSS class, so there's
# nothing left to win over it - font-weight/family/size are restated
# here in CSS so the label doesn't lose its original bold styling once
# the Pango attributes carrying it are cleared. Contrast
# _load_panel_axis_display's Panel_Channel_0N_Axis labels, which have
# no such static foreground of their own, so set_markup() works fine
# there without any of this.
_DEPRESS_CSS = b"""
button.reb-depressed,
button.reb-depressed:hover,
button.reb-depressed:focus,
button.reb-depressed:active {
    background-color: shade(@theme_bg_color, 0.6);
    background-image: none;
    box-shadow: inset 2px 2px 4px rgba(0,0,0,0.6), inset -1px -1px 2px rgba(255,255,255,0.15);
}
label.reb-axis-yellow,
label.reb-axis-red,
label.reb-axis-blue {
    font-family: "DejaVu Serif";
    font-weight: bold;
    /* Matches Sp0/Sp1's untouched font-desc="DejaVu Serif Bold 12" -
       that "12" is POINTS (Pango's default unit in a font-desc string),
       not pixels: CSS "12px" is only ~9pt at 96dpi, visibly smaller -
       "pt" is the unit that actually matches. */
    font-size: 12pt;
}
label.reb-axis-yellow { color: #e5a50a; }
label.reb-axis-red    { color: #a51d2d; }
label.reb-axis-blue   { color: #1a5fb4; }
"""

# Letter -> which of the 3 CSS classes above matches AXIS_LETTER_COLOR's
# grouping for that letter (X/U/A yellow, V/B red, Z/W/C blue) - see
# _DEPRESS_CSS's comment for why this exists as CSS rather than reusing
# AXIS_LETTER_COLOR's hex values directly via set_markup().
AXIS_LETTER_COLOR_CLASS = {
    "X": "reb-axis-yellow", "U": "reb-axis-yellow", "A": "reb-axis-yellow",
    "V": "reb-axis-red", "B": "reb-axis-red",
    "Z": "reb-axis-blue", "W": "reb-axis-blue", "C": "reb-axis-blue",
}
_AXIS_LETTER_COLOR_CLASSES = ("reb-axis-yellow", "reb-axis-red", "reb-axis-blue")

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

        settings = reb_settings_io.load_settings()
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

                stored = _read_persisted_axis_comment(axis_id, settings)
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









    def _load_panel_axis_display(self):
        '''
        Reads the persisted channel -> axis letter assignment and
        populates the main panel's own read-only "Axis Assignments"
        display (Panel_Channel_0N_Axis/_Type - REB_Panel_v1.ui), if
        this component owns those widgets. Unlike the Axis Selection
        tab's combos, these are plain labels with no signal handlers -
        purely informational; the Settings tab is the only place the
        assignment can actually be changed. Populated once at this
        component's own startup, same as everything else keyed off
        REBset_v1.ini - a change made on the Settings tab only takes
        effect (here and everywhere else) after a restart anyway, at
        which point this process reloads fresh too. No-ops outside the
        main panel component.
        '''
        if self.builder.get_object("Panel_Channel_00_Axis") is None:
            return

        assignments = _read_persisted_channel_assignments()
        types = {channel_id: _axis_type_for_letter(letter) for channel_id, letter in assignments.items()}
        for channel_id, letter in assignments.items():
            axis_label = self.builder.get_object("Panel_Channel_" + channel_id + "_Axis")
            if axis_label is not None:
                color = AXIS_LETTER_COLOR.get(letter)
                if color is not None:
                    # set_markup takes over the label's whole attribute
                    # list, so the big/bold styling REB_Panel_v1.ui gives
                    # this label has to be restated here too, not just
                    # the color - otherwise it would revert to plain text
                    # the moment this runs.
                    axis_label.set_markup(
                        '<span foreground="' + color + '" font_desc="DejaVu Serif 24" weight="bold">'
                        + letter + '</span>'
                    )
                else:
                    axis_label.set_text(letter)

            type_label = self.builder.get_object("Panel_Channel_" + channel_id + "_Type")
            if type_label is not None:
                type_label.set_text(types[channel_id].capitalize())

    def _load_panel_axis_controls(self):
        '''
        Configures each of the 6 channel rows' *interactive* controls to
        match its CURRENTLY assigned letter and type (CURRENT_LETTER/
        CURRENT_TYPE), if this component owns the main panel's
        widgets - the working counterpart to _load_panel_axis_display's
        read-only table above. For each channel: sets the col-0 letter
        label's text/color (AXIS_LETTER_COLOR, same styling approach as
        _load_panel_axis_display); swaps both jog buttons' icon to the
        one matching the assigned letter specifically, not just its type
        (AXIS_JOG_IMAGE - a linear channel reassigned from X to V still
        needs V's icon, not X's, since the icon encodes physical +/-
        direction); reconfigures the Feed/Idx adjustments' numeric range,
        precision, and (Feed only) default value to the assigned type's
        profile (TYPE_ADJUSTMENT_PROFILE); and shows whichever of the two
        column-11 widgets matches the type (deg/div radio pair if
        angular, the static unit label if linear) while hiding the
        other. Unit-label *text* (Feed_UOM/IdxDist_UOM/Scale_UOM) is
        handled separately by _apply_measurement_system_labels, called
        from _load_measurement_system right after this in __init__ -
        that function already needs the same per-channel type check for
        its own purpose (Metric/Imperial only means something for a
        linear channel), so it owns all three unit-label texts rather
        than splitting that responsibility across two methods.

        Populated once at this component's own startup, same as
        _load_panel_axis_display - a reassignment made on the Settings
        tab only takes effect after a restart anyway, at which point
        this process reloads fresh too. No-ops outside the main panel
        component.
        '''
        if self.builder.get_object("X_ENA") is None:
            return

        images_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Images")

        for axis in CHANNEL_DEFAULT_LETTER.values():
            letter = CURRENT_LETTER[axis].upper()
            angular = CURRENT_TYPE[axis] == "ANGULAR"

            letter_label = self.builder.get_object(axis + "_Letter")
            if letter_label is not None:
                letter_label.set_text(letter)
                # Clear the static per-widget Pango attributes REB_Panel_v1.ui
                # gives this label (font-desc/weight/foreground) - see
                # _DEPRESS_CSS's comment for why those would otherwise
                # win over the CSS color class applied below.
                letter_label.set_attributes(None)
                ctx = letter_label.get_style_context()
                for css_class in _AXIS_LETTER_COLOR_CLASSES:
                    ctx.remove_class(css_class)
                css_class = AXIS_LETTER_COLOR_CLASS.get(letter)
                if css_class is not None:
                    ctx.add_class(css_class)

            neg_file, pos_file = AXIS_JOG_IMAGE.get(letter, AXIS_JOG_IMAGE["X"])
            neg_button = self.builder.get_object(JOG_NEG_WIDGET[axis])
            if neg_button is not None:
                neg_button.set_image(Gtk.Image.new_from_file(os.path.join(images_dir, neg_file)))
            pos_button = self.builder.get_object(JOG_POS_WIDGET[axis])
            if pos_button is not None:
                pos_button.set_image(Gtk.Image.new_from_file(os.path.join(images_dir, pos_file)))

            profile = TYPE_ADJUSTMENT_PROFILE["ANGULAR" if angular else "LINEAR"]

            feed_adj = self.builder.get_object(axis + "_Feed_Rate")
            if feed_adj is not None:
                feed_lower, feed_upper, feed_step, _, feed_default = profile["feed"]
                feed_adj.set_lower(feed_lower)
                feed_adj.set_upper(feed_upper)
                feed_adj.set_step_increment(feed_step)
                feed_adj.set_value(feed_default)
            feed_spin = self.builder.get_object(axis + "_Feed")
            if feed_spin is not None:
                feed_spin.set_digits(profile["feed"][3])

            idx_adj = self.builder.get_object(axis + "_Idx_Dis")
            if idx_adj is not None:
                idx_upper, idx_step, _ = profile["idx"]
                idx_adj.set_upper(idx_upper)
                idx_adj.set_step_increment(idx_step)
            idx_spin = self.builder.get_object(axis + "_Idx_Dist")
            if idx_spin is not None:
                idx_spin.set_digits(profile["idx"][2])

            degdiv_box = self.builder.get_object(axis + "_Idx_DegDiv_Box")
            if degdiv_box is not None:
                degdiv_box.set_visible(angular)
            unit_label = self.builder.get_object(axis + "_IdxDist_UOM")
            if unit_label is not None:
                unit_label.set_visible(not angular)



    def _save_axis_comment(self, axis_id, text):
        '''
        Writes a single axis's comment back into REB_Settings_v1.ini's
        usercomment value for that axis. Called from each comment
        Entry's focus-out-event handler below.
        '''
        settings = reb_settings_io.load_settings()
        settings.setdefault("axes", {}).setdefault(axis_id, {})["usercomment"] = text
        reb_settings_io.save_settings(settings)
        print("Saved " + axis_id + " comment")



#######################################################################
# Measurement_System_Changed
# Purpose:              User picked Metric or Imperial in the Settings
#                           tab's "Other" section. Updates this
#                           component's own unit-of-measure labels for
#                           immediate feedback, persists the choice to
#                           REBset_v1.ini, and warns that a restart
#                           is needed for the new units to actually take
#                           effect. REB.ini itself is never patched here
#                           any more - REB_Launch.sh overlays
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


#######################################################################
# Max_Jog_Speed_Changed
# Purpose:              User changed the Max Jog Speed on the Settings
#                           tab's "General" section. Persists the value
#                           to REBset_v1.ini and warns that a
#                           restart is needed. REB.ini itself is never
#                           patched here any more - REB_Launch.sh
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

# B's jog/feed/index/scale/ena handlers used to be hand-written here
# (B_Move_Idx_Fwd/Rev, B_Set_Idx_Feed, B_Set_Idx_Dist, B_Set_Idx_DegDiv,
# B_Set_Move_Dist, B_Set_Scale, B_Set_Ena) - they're now generated by the
# same type-aware factories as every other channel (see "Generated
# per-channel handlers" below, JOG_NEG_HANDLER/JOG_POS_HANDLER/
# FEED_HANDLER for the handful of B-specific widget-id names those
# factories still have to honor).

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





        # Same suppression as above, for _load_axis_comments driving each
        # axis's comment combo box at startup.
        self._applying_axis_comments = False



        _install_depress_css()

        # Independent pins this component owns, used to force each
        # axis disabled from this tab regardless of what the main
        # panel's own enable button is doing. Each defaults to "allow
        # enabled". ANDed with the panel button per-axis in
        # REB_PostGUI_v1.hal - only this component's own copy
        # ("gladevcp.<Axis>_Ena_Override") is actually netted; every
        # other component (Help, License) creates the same pin
        # harmlessly unused.
        #
        # HAL_IO, not HAL_OUT: this component's own Set_Scale handlers
        # clear an axis to False, but re-arming it happens from the main
        # panel's ENA button - a different process - via
        # the external REB_Settings program clears an axis to False
        # before a scale change (a different process, via
        # `halcmd sets <letter>-ena-settings-allow FALSE` - the signal,
        # not this pin directly, once netted) - re-arming happens back
        # in THIS component's own _clear_ena_override, below, when the
        # panel's ENA button is pressed again. See
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




        # Restore the persisted channel -> axis letter assignment
        # (REBset_v1.ini) into the main panel's own read-only display
        # (if owned by this component).
        self._load_panel_axis_display()

        # Reconfigure the main panel's 6 channel rows (letter label,
        # jog icons, adjustment ranges, column-11 widget visibility) to
        # match each channel's current type/letter (if owned by this
        # component).
        self._load_panel_axis_controls()



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

        # Per-channel state for all 6 reassignable channels (internal ids
        # X/Z/U/V/W/B - CHANNEL_DEFAULT_LETTER's values), read/written by
        # the generated Idx_Fwd/Idx_Rev/Set_Feed/etc. methods below via
        # getattr/setattr. Defaults are picked from this SESSION's actual
        # current type (CURRENT_TYPE), not the internal id's own
        # historical type - a channel reassigned to Angular needs
        # angular-shaped defaults even though its internal id is, say,
        # "X". Idx_Deg/Idx_DegDiv are harmless to set on a currently-
        # linear channel - they simply go unused until (if ever) that
        # channel becomes angular after a future restart, the same
        # moment this whole block re-runs with fresh CURRENT_TYPE values
        # anyway. Sp0/Sp1 keep their own hand-written state above -
        # genuinely different shape (Idx_Bool checkboxes, no Move_Dist).
        for axis in CHANNEL_DEFAULT_LETTER.values():
            if CURRENT_TYPE[axis] == "ANGULAR":
                setattr(self, axis + "_Feed", TYPE_ADJUSTMENT_PROFILE["ANGULAR"]["feed"][4])
                setattr(self, axis + "_Idx_Dist", 90.0)
                setattr(self, axis + "_Idx_Deg", 90.0)
            else:
                setattr(self, axis + "_Feed", TYPE_ADJUSTMENT_PROFILE["LINEAR"]["feed"][4])
                setattr(self, axis + "_Idx_Dist", 0.0)
                setattr(self, axis + "_Idx_Deg", 0.0)
            setattr(self, axis + "_Idx_DegDiv", "Deg")
            setattr(self, axis + "_Idx_Qty", 0)
            setattr(self, axis + "_Move_Dist", 0.0)

# ------------------------------------------------------------------
# Generated per-channel handlers, for all 6 reassignable channels
# (X/Z/U/V/W/B - CHANNEL_DEFAULT_LETTER's values).
#
# Collapses the near-identical Idx_Fwd/Idx_Rev/Set_Feed/Set_Idx_Dist/
# Set_Idx_DegDiv/Set_Move_Dist/Set_Scale methods - which used to be
# hand-written once per axis (see docs/hitcounter-review.md, Issue 1),
# then generated for the 5 linear axes only, with B kept separately
# hand-written (different shape: Idx_Deg/Idx_DegDiv derivation, no
# equivalent in the linear factories) - into one factory function per
# pattern, looped over all 6 channels and bound onto HandlerClass via
# setattr. This has to produce real, named methods rather than a
# __getattr__ dispatcher: GladeVCP discovers handlers via dir(instance)
# fed into builder.connect_signals(), and dir() does not enumerate names
# that only exist through __getattr__ - such a button would silently
# stop working with no error anywhere.
#
# Channels are no longer permanently linear or angular - which shape a
# given channel's controls behave as is decided at CALL TIME by
# CURRENT_TYPE[axis], since the operator can independently set any
# channel's letter and Type via the Axis Selection tab (taking effect
# on next restart, same as everywhere else this matters). Widget
# ids themselves are NEVER renamed - REB_Panel_v1.ui's buttons still
# have the ids they've always had; only B's jog buttons/Feed widget use
# a different naming pattern than the rest (JOG_NEG_HANDLER/
# JOG_POS_HANDLER/FEED_HANDLER below), a historical quirk from B being
# hand-written for so long, not something worth renaming widgets over.
#
# Set_Ena IS generated here (revised 2026-07-28): initially thought dead
# (no .ui file wires a <signal> to any <Axis>_Set_Ena), but that's because
# the ENA buttons were redesigned from HAL_Button (which used a "pressed"
# signal) to HAL_LightButton, which only emits "clicked" - the signal
# wiring was never carried over, silently orphaning
# _clear_ena_override()'s fix for the "press ENA and nothing happens,
# need a confusing second press" bug (see that function's own comments).
# The real fix is reconnecting REB_Panel_v1.ui's <Axis>_ENA widgets'
# "clicked" signal to <Axis>_Set_Ena, not deleting the method.

# Column-12/column-13 jog button handler names actually wired in
# REB_Panel_v1.ui, per channel. These are fixed forever (widgets are
# never renamed) - only B differs from the "<letter>_Idx_Minus"/
# "<letter>_Idx_Plus" pattern the rest use (B_Move_Idx_Fwd/Rev, a
# leftover from before this handler was generated generically). Despite
# the different naming, column 12 always sends G-code sign "-" and
# column 13 always sends "+" for every channel, linear or angular alike
# (empirically verified independently for both X's Idx_Minus/Idx_Plus
# and B's Move_Idx_Fwd/Rev - see the loop below) - that's what lets one
# factory serve both naming patterns.
JOG_NEG_HANDLER = {  # column 12, gcode sign "-"
    "X": "X_Idx_Plus", "Z": "Z_Idx_Plus", "U": "U_Idx_Plus",
    "V": "V_Idx_Plus", "W": "W_Idx_Plus", "B": "B_Move_Idx_Fwd",
}
JOG_POS_HANDLER = {  # column 13, gcode sign "+"
    "X": "X_Idx_Minus", "Z": "Z_Idx_Minus", "U": "U_Idx_Minus",
    "V": "V_Idx_Minus", "W": "W_Idx_Minus", "B": "B_Move_Idx_Rev",
}
FEED_HANDLER = {
    "X": "X_Set_Feed", "Z": "Z_Set_Feed", "U": "U_Set_Feed",
    "V": "V_Set_Feed", "W": "W_Set_Feed", "B": "B_Set_Idx_Feed",
}

def _axis_idx_move(axis, handler_name, gcode_sign):
    '''
    handler_name is the exact method name GladeVCP dispatches to (see
    JOG_NEG_HANDLER/JOG_POS_HANDLER - varies per channel, not derived
    from axis here); gcode_sign ("+"/"-") is the actual sign sent in the
    G-code, and also which way the Idx_Qty counter moves (matches B's
    old Fwd=+1/Rev=-1 behavior, now applied to every channel instead of
    just B). Whether this move uses Idx_Dist (linear) or the derived
    Idx_Deg (angular) is decided at call time from the channel's current
    type - see the module comment above.
    '''
    def handler(self, widget):
        print("=================================================")
        print("FUNCTION " + handler_name)

        # Depress the button for the duration of the move (see
        # _set_depressed for why this isn't a HAL_ToggleButton).
        _set_depressed(widget, True)
        try:
            s.poll()
            if s.task_state != linuxcnc.MODE_MDI:
                c.mode(linuxcnc.MODE_MDI)
                c.wait_complete()

            angular = CURRENT_TYPE[axis] == "ANGULAR"
            amount = getattr(self, axis + "_Idx_Deg") if angular else getattr(self, axis + "_Idx_Dist")
            feed = getattr(self, axis + "_Feed")
            # The G-code axis word must be the CURRENTLY assigned letter
            # for this channel (CURRENT_LETTER), not the fixed internal
            # id "axis" - LinuxCNC only recognizes whatever letter is
            # actually in [TRAJ]COORDINATES right now (see REB_Setup/
            # REB_Generate_Local_Ini.py's _overlay_axis_assignment). All
            # other uses of "axis" in this function (attribute names,
            # handler naming) correctly stay the internal id.
            gcode_axis = CURRENT_LETTER.get(axis, axis.lower()).upper()
            Gcode = "G1 " + gcode_axis + gcode_sign + str(amount) + " F" + str(feed)

            print(Gcode)
            c.mdi(Gcode)
            c.wait_complete()

            qty_delta = 1 if gcode_sign == "-" else -1
            setattr(self, axis + "_Idx_Qty", getattr(self, axis + "_Idx_Qty") + qty_delta)
            print(axis + "_Idx_Qty = " + str(getattr(self, axis + "_Idx_Qty")))
        finally:
            _set_depressed(widget, False)
    handler.__name__ = handler_name
    return handler

def _axis_set_feed(axis, handler_name):
    def handler(self, widget):
        print("=================================================")
        print("FUNCTION " + handler_name)
        setattr(self, axis + "_Feed", round(widget.get_value(), 1))
        print(axis + "_Feed = " + str(getattr(self, axis + "_Feed")))
    handler.__name__ = handler_name
    return handler

def _axis_set_idx_dist(axis):
    '''
    Linear channels: Idx_Dist is used directly. Angular channels: Idx_Dist
    is the raw user entry, which - depending on the channel's Idx_DegDiv
    mode ("Deg" vs "Div", toggled by _axis_set_idx_degdiv below) - gets
    derived into Idx_Deg, the value _axis_idx_move actually sends in
    G-code (matches B's old hand-written derivation, now available to
    any channel currently angular).
    '''
    def handler(self, widget):
        print("=================================================")
        print("FUNCTION " + axis + "_Set_Idx_Dist")
        value = widget.get_value()
        setattr(self, axis + "_Idx_Dist", value)
        if CURRENT_TYPE[axis] == "ANGULAR":
            if getattr(self, axis + "_Idx_DegDiv") == "Deg":
                setattr(self, axis + "_Idx_Deg", round(value, 1))
            else:
                setattr(self, axis + "_Idx_Deg", round(360 / value, 1))
            print(axis + "_Idx_DegDiv = " + getattr(self, axis + "_Idx_DegDiv"))
            print(axis + "_Idx_Deg = " + str(getattr(self, axis + "_Idx_Deg")) + " deg")
        else:
            print(axis + "_Idx_Dist = " + str(value))
    handler.__name__ = axis + "_Set_Idx_Dist"
    return handler

def _axis_set_idx_degdiv(axis):
    '''
    Toggles a currently-angular channel's jog-increment entry between
    meaning degrees directly ("Deg") and meaning "N divisions of a full
    circle" ("Div", i.e. 360/N degrees) - wired to the deg/div
    HAL_RadioButton pair every channel's row now has (previously only
    B's row did). Matches B's old hand-written B_Set_Idx_DegDiv exactly;
    only reachable in practice on a currently-angular channel, since
    that's the only case _load_panel_axis_controls makes this pair
    visible - harmless to register for every channel regardless.
    '''
    def handler(self, widget):
        print("=================================================")
        print("FUNCTION " + axis + "_Set_Idx_DegDiv")
        if getattr(self, axis + "_Idx_DegDiv") == "Deg":
            setattr(self, axis + "_Idx_DegDiv", "Div")
            setattr(self, axis + "_Idx_Deg", round(360 / getattr(self, axis + "_Idx_Dist"), 1))
        else:
            setattr(self, axis + "_Idx_DegDiv", "Deg")
            setattr(self, axis + "_Idx_Deg", round(getattr(self, axis + "_Idx_Dist"), 1))
        print(axis + "_Idx_Deg = " + str(getattr(self, axis + "_Idx_Deg")))
        print(axis + "_Idx_DegDiv = " + getattr(self, axis + "_Idx_DegDiv"))
    handler.__name__ = axis + "_Set_Idx_DegDiv"
    return handler

def _axis_set_move_dist(axis):
    def handler(self, widget):
        print("=================================================")
        print("FUNCTION " + axis + "_Set_Move_Dist")
        setattr(self, axis + "_Move_Dist", widget.get_value())
        print(axis + "_Move_Dist = " + str(getattr(self, axis + "_Move_Dist")))
    handler.__name__ = axis + "_Set_Move_Dist"
    return handler



def _axis_set_ena(axis):
    def handler(self, widget, *args):
        _clear_ena_override(axis)
    handler.__name__ = axis + "_Set_Ena"
    return handler

for _axis in CHANNEL_DEFAULT_LETTER.values():
    # Column 12 sends gcode sign "-", column 13 sends "+" - empirically
    # verified independently for X/U/V/Z/W's Idx_Minus/Idx_Plus (live
    # testing showed all five linear axes moving the physically wrong
    # way relative to their correct icons - the same class of bug
    # already found and fixed for the spindles' Fwd/Rev and Idx_Fwd/
    # Idx_Rev via live halcmd pin tracing, see Sp0_Move_Fwd's docstring)
    # and for B's Move_Idx_Fwd/Rev (see that method's old banner comment,
    # now folded into _axis_idx_move above) - see JOG_NEG_HANDLER/
    # JOG_POS_HANDLER for why this holds regardless of the handler name.
    setattr(HandlerClass, JOG_NEG_HANDLER[_axis], _axis_idx_move(_axis, JOG_NEG_HANDLER[_axis], "-"))
    setattr(HandlerClass, JOG_POS_HANDLER[_axis], _axis_idx_move(_axis, JOG_POS_HANDLER[_axis], "+"))
    setattr(HandlerClass, FEED_HANDLER[_axis], _axis_set_feed(_axis, FEED_HANDLER[_axis]))
    setattr(HandlerClass, _axis + "_Set_Ena", _axis_set_ena(_axis))
    setattr(HandlerClass, _axis + "_Set_Idx_Dist", _axis_set_idx_dist(_axis))
    setattr(HandlerClass, _axis + "_Set_Idx_DegDiv", _axis_set_idx_degdiv(_axis))
    setattr(HandlerClass, _axis + "_Set_Move_Dist", _axis_set_move_dist(_axis))
    # No _Set_Scale binding here - Scale is bound per LETTER, not per
    # internal id, in the unified AXIS_SELECTION_LETTERS loop below (see
    # _axis_set_scale_letter's docstring for why: the widget labeled
    # e.g. "B" must always mean "whichever channel currently wears
    # letter B," not "channel 05, forever" - a real bug found live 3
    # September 2026 when channel 00 was reassigned to letter B and its
    # Scale edits were silently landing on channel 05's stepgen instead).
del _axis
















# No PID_AXES-based binding loop here for the 6 reassignable channels
# (X/Z/B/U/V/W widgets) - PID is instead bound per LETTER, uniformly
# for all 8 letters, via _pid_set_letter below (same fix as Scale/Max
# Vel/Backlash - see _axis_set_scale_letter's docstring). PID_AXES
# itself is kept and still used elsewhere (e.g. the Export/Save-
# Settings snapshot's "is this a reassignable axis id" membership
# check) - just no longer as a live-HAL-pin source here.






def get_handlers(halcomp,builder,useropts):
    '''
    this function is called by gladevcp at import time (when this module is passed with '-u <modname>.py')

    return a list of object instances whose methods should be connected as callback handlers
    any method whose name does not begin with an underscore ('_') is a  callback candidate

    the 'get_handlers' name is reserved - gladevcp expects it, so do not change
    '''
    return [HandlerClass(halcomp,builder,useropts)]

#
