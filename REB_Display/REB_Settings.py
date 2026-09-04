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
#   REB_Settings.py
#
# Purpose:  Standalone external configurator for Rose Engine Butler.
#   Replaces the Settings tab that used to be embedded inside
#   LinuxCNC's AXIS GUI via gladevcp - this is a plain, independently
#   launched GTK program (see REB_Settings.sh) that loads
#   REB_Settings_v1.ui directly, with no HAL component of its own.
#   Every live HAL read/write goes through `halcmd getp/setp/gets/sets`
#   subprocess calls, so this program works whether or not LinuxCNC
#   happens to be running at the time (the halcmd calls simply fail
#   harmlessly if it isn't).
#
# End User Customisation:
#   THE END USER OF THE ROSE ENGINE BUTLER SYSTEM SHOULD NOT MODIFY
#   THIS FILE.
#
#   Changes to this file are not supported by Colvin Tools nor
#   Brainwave Embedded.
#
# Version
#   1.0 - 4 September 2026, Claude
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
import time
import subprocess
import shutil
import re
import json
import webbrowser
import contextlib
import linuxcnc
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gdk
from gi.repository import Gtk

@contextlib.contextmanager
def _suppress_fd2():
    '''
    Silences writes to OS file descriptor 2 (stderr) for the duration
    of the `with` block - needed because gladevcp.hal_widgets (imported
    below) and linuxcnc.stat().poll() (see _linuxcnc_is_running further
    down) both print harmless diagnostic noise ("tool_mmap_user(): tool
    mmap not available" / "poll(): continuing without tool mmap data")
    straight to the raw fd from C code, which a plain Python-level
    contextlib.redirect_stderr can't catch (it only reassigns sys.
    stderr's object reference, not the underlying OS fd the C code
    writes to - confirmed by testing both approaches live 4 September
    2026). This also happens to swallow gladevcp's own "Logging to:
    ..." console line, since Python's logging.StreamHandler writes
    through sys.stderr, which is itself backed by this same fd absent
    a full reassignment.

    Scoped narrowly to each specific call site (the gladevcp import,
    and _linuxcnc_is_running's poll()) rather than left in place
    permanently, since it would just as easily hide a real error
    printed to stderr during whatever's wrapped in `with` - fine for a
    known-noisy, already-handled call, not something to reach for
    generally.
    '''
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    saved_fd = os.dup(2)
    os.dup2(devnull_fd, 2)
    try:
        yield
    finally:
        os.dup2(saved_fd, 2)
        os.close(saved_fd)
        os.close(devnull_fd)

# Registers the HAL_SpinButton GObject type (REB_Settings_v1.ui's only
# custom widget class) so Gtk.Builder can resolve it - without this
# import, add_from_file() below fails immediately with "invalid object
# type 'HAL_SpinButton'". Confirmed this is sufficient on its own (no
# live HAL component/hal.component() needed at class-registration time)
# - gladevcp.hal_widgets' HAL_SpinButton only touches HAL when actually
# wired to a component, which this standalone program never does; every
# live HAL read/write here already goes through halcmd instead (see
# module docstring above).
with _suppress_fd2():
    import gladevcp.hal_widgets
import reb_settings_io

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
UI_FILE = os.path.join(SCRIPT_DIR, "REB_Settings_v1.ui")

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

# Reverse of CHANNEL_DEFAULT_LETTER - internal id -> channel id.
DEFAULT_LETTER_CHANNEL = {v: k for k, v in CHANNEL_DEFAULT_LETTER.items()}

# The 8 letters selectable on the Axis Selection tab (Y removed - not
# used on this machine).
AXIS_SELECTION_LETTERS = ("X", "Z", "U", "V", "W", "A", "B", "C")

# Axis type (Linear/Angular) is always derived from the letter, forever
# - unlike the embedded Settings tab this replaces (which briefly had
# an independent per-channel Type combo, 3-4 September 2026), Rich
# asked for that reverted for this program: X/Z/U/V/W are always
# Linear, A/B/C are always Angular, with no separate Type choice for
# the operator to make. There is therefore no "channel_types"
# persistence in this file at all - CURRENT_TYPE below is computed
# directly from CURRENT_LETTER instead of read from REBset_v1.ini.
def _axis_type_for_letter(letter):
    return "ANGULAR" if letter.upper() in ("A", "B", "C") else "LINEAR"

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
    _load_measurement_system.
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

# Axis id (as used in REBset_v1.ini and the Settings widgets) -> hm2_7i92.0
# stepgen channel. Verified against the actual "net <axis>-enable =>
# hm2_7i92.0.stepgen.NN.enable" lines in REB.hal - NOT the documentation
# table in REB.ini, which does not match. This key is the internal id
# (see CHANNEL_DEFAULT_LETTER above) - it never changes even if the
# operator reassigns this channel's axis letter.
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
# parameter (motion's own per-joint backlash compensation). NOT the
# same numbering as AXIS_STEPGEN's hm2 stepgen channel map above -
# joint numbers come from [KINS]JOINTS/trivkins ordering, not hm2
# wiring.
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
# running LinuxCNC session's assignment can't change without a restart
# anyway (a "restart required" popup is shown on every change), so
# re-reading it later would only ever see the same value or one that
# doesn't match what's actually wired into HAL right now.
_CHANNEL_ASSIGNMENTS_AT_STARTUP = _read_persisted_channel_assignments()

# Internal id -> this session's actual current axis letter (lowercase).
# Needed anywhere a HAL net/component name in REB.local.hal/
# REB_PostGUI_v1.local.hal embeds the assigned letter (PID_AXES below).
# Does NOT apply to gladevcp.* pin names or any widget id - those stay
# the internal id forever, see CHANNEL_DEFAULT_LETTER above.
CURRENT_LETTER = {
    internal_id: _CHANNEL_ASSIGNMENTS_AT_STARTUP.get(channel_id, internal_id).lower()
    for internal_id, channel_id in DEFAULT_LETTER_CHANNEL.items()
}

# Internal id -> this session's actual current Type ("LINEAR"/"ANGULAR"),
# derived directly from CURRENT_LETTER - see _axis_type_for_letter above
# for why this is a plain computation rather than something read from
# REBset_v1.ini.
CURRENT_TYPE = {
    internal_id: _axis_type_for_letter(letter)
    for internal_id, letter in CURRENT_LETTER.items()
}

# Internal id -> HAL `pid` component instance driving that axis's PID
# loop right now (see CURRENT_LETTER above for why this can't be a
# static dict, and PID_SPINDLE_LOOPS below for Sp0/Sp1's own loops).
PID_AXES = {internal_id: "pid." + letter for internal_id, letter in CURRENT_LETTER.items()}

# Reverse of CURRENT_LETTER: currently-assigned axis letter (uppercase)
# -> internal id of whichever physical channel is driving it right now,
# if any - used to resolve EXTRA_SETTINGS_LETTERS' live HAL pin below.
CURRENT_LETTER_INTERNAL_ID = {letter.upper(): internal_id for internal_id, letter in CURRENT_LETTER.items()}

# Settings widget rows with no fixed physical channel of their own (see
# CHANNEL_DEFAULT_LETTER) - lets the operator pre-configure/retain a
# Scale value for an A/C attachment even while it isn't currently
# plugged into any channel. Persisted in REBset_v1.ini as
# <axis id="A">/<axis id="C"> blocks, independent of the six physical
# channels' own blocks.
EXTRA_SETTINGS_LETTERS = ("A", "C")

# Spindle id -> {"Pos": position-loop component, "Vel": velocity-loop
# component}. The suffix ("Pos"/"Vel") matches the Settings widget id
# suffix (e.g. Sp0_Set_P_Pos, Sp0_Set_P_Vel) and the REBset_v1.ini block
# tag ("pid_pos"/"pid_vel").
PID_SPINDLE_LOOPS = {
    "Sp0": {"Pos": "pid.p0", "Vel": "pid.s0"},
    "Sp1": {"Pos": "pid.p1", "Vel": "pid.s1"},
}

# Settings widget field name -> HAL pid component pin name.
PID_PARAM_PIN = {
    "P":   "Pgain",
    "I":   "Igain",
    "D":   "Dgain",
    "FF0": "FF0",
    "FF1": "FF1",
    "FF2": "FF2",
}
PID_PARAMS = ("P", "I", "D", "FF0", "FF1", "FF2")

# Default directory Export/Import's file choosers start in.
REBSET_DEFAULT_DIR = os.path.expanduser("~/Documents")

# Axes (not spindles) that have a free-text comment field on the main
# panel, persisted to REBset_v1.ini as each <axis>'s <usercomment>.
# REB_Settings has no comment field of its own (that widget lives on
# the main panel, a separate program) but still needs this list to
# default the Export dialog's Device combos and to apply an imported/
# loaded comment value to REBset_v1.ini on the main panel's behalf.
COMMENT_AXES = ("X", "Z", "U", "V", "W", "B")

# Leading entry (index 0) in every device-name GtkComboBoxText - the
# Export Settings dialog's per-axis Device combos - standing in for
# "nothing chosen yet" instead of a blank-looking row. Never treated as
# a real device name - see _combo_selected_device.
DEVICE_COMBO_PLACEHOLDER = "(nothing selected yet)"

# Sp0/Sp1 have no main-panel comment field (see COMMENT_AXES) to default
# the Export Settings dialog's Device combo from, unlike X/Z/U/V/W/B -
# these are the ones Rich actually has, so use them as each spindle's
# default there instead of falling back to DEVICE_COMBO_PLACEHOLDER.
SPINDLE_DEFAULT_DEVICE_NAME = {
    "Sp0": "Spindle (Sp0)",
    "Sp1": "Rosette Phaser/Multiplier (Sp1)",
}

# Export_Settings/Import_Settings: a hand-picked subset of just what's
# literally on the Settings widgets (each axis's Scale/Backlash/Max
# Vel/Max Accel/PID, plus Measurement System), for quick, ad hoc
# sharing of a few values (e.g. "just my B-axis calibration") rather
# than a full profile. Plain JSON (matching REBset_v1.ini's own shape).
EXPORT_EXTENSION = ".REBset_v1.ini"

# Establish connection to command and status channels - needed for the
# M5-before-scale-change safety behavior in Sp0_Set_Scale/Sp1_Set_Scale/
# _axis_set_scale_letter below and the motion-abort in the latter. This
# is the one piece of LinuxCNC access that has no halcmd-subprocess
# equivalent - everything else in this file shells out to halcmd
# instead of importing hal/hal_glib, but the command/status channel can
# only be reached via `import linuxcnc`.
c = linuxcnc.command()
s = linuxcnc.stat()

def _linuxcnc_is_running():
    '''
    The intended workflow is: run REB_Settings first, then start
    LinuxCNC - not the other way around, and not concurrently. Every
    _load_* method below pushes the values it reads from REBset_v1.ini
    onto live HAL pins via halcmd, which only exist while LinuxCNC is
    running; running this program while LinuxCNC is up floods the
    console with harmless-but-alarming "parameter or pin not found"
    lines for every single pin (confirmed live 4 September 2026 with
    LinuxCNC not running). Rather than let that noise stand in for a
    real answer, check up front and tell the operator to close LinuxCNC
    first.

    s.poll() is documented to raise linuxcnc.error ("emcStatusBuffer
    invalid") when there's no running LinuxCNC session to connect to,
    and does exactly that in isolation - but confirmed live, once
    gladevcp.hal_widgets has been imported (needed above so Gtk.Builder
    can resolve HAL_SpinButton), the same failure instead surfaces as a
    bare SystemError ("returned NULL without setting an exception") -
    apparently some interaction between GTK/GLib's signal handling and
    NML's own alarm()-based timeout, not something to rely on staying
    exactly linuxcnc.error. There's no legitimate reason for poll() to
    raise anything at all when a session genuinely is running, so treat
    ANY exception here as "not running" rather than chase every exact
    exception type this interaction might produce.
    '''
    try:
        with _suppress_fd2():
            s.poll()
        return True
    except Exception:
        return False

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
    REBset_v1.ini, the same silent, automatic settings file
    _load_scale_settings/_load_axis_comments already read/write.
    '''
    settings = reb_settings_io.load_settings()
    settings["measurement_system"] = system
    reb_settings_io.save_settings(settings)
    print("Saved measurement_system = " + system)

def _save_device_names(names):
    '''
    Persists the maintained device-name list (the Other page's Device
    Names box - one name per line) into REBset_v1.ini's "device_names"
    list, replacing it wholesale each time rather than tracking
    adds/removes/reorders across saves.
    '''
    settings = reb_settings_io.load_settings()
    settings["device_names"] = list(names)
    reb_settings_io.save_settings(settings)
    print("Saved " + str(len(names)) + " device name(s)")

def _read_persisted_device_names():
    '''
    Reads the persisted device-name list straight from SETTINGS_PATH.
    Returns [] if the file can't be read or has no device_names list.
    '''
    return list(reb_settings_io.load_settings().get("device_names", []))

def _read_persisted_axis_comment(axis_id, settings):
    '''
    Extracts one axis's persisted usercomment value out of an
    already-loaded settings dict. Used by _run_export_selection_dialog
    to default each axis's Export dialog Device combo to whatever's
    currently set on the main panel - REBset_v1.ini's usercomment is
    the only channel between this program and the main panel, which is
    a separate process with no live IPC. Returns "" if the axis or its
    usercomment isn't found.
    '''
    return settings.get("axes", {}).get(axis_id, {}).get("usercomment", "")

def _combo_selected_device(combo):
    '''
    Returns the real selected value of a device-name GtkComboBoxText
    (empty string if the leading DEVICE_COMBO_PLACEHOLDER entry - index
    0 - is what's active), rather than combo.get_active_text() directly,
    which would return the placeholder's own display text.
    '''
    return combo.get_active_text() if combo.get_active() > 0 else ""

def _save_max_jog_speed(value):
    '''
    Persists the Max Jog Speed choice into REBset_v1.ini, the same
    silent, automatic settings file _save_measurement_system already
    writes measurement_system into.
    '''
    settings = reb_settings_io.load_settings()
    settings["max_jog_speed"] = round(value, 4)
    reb_settings_io.save_settings(settings)
    print("Saved max_jog_speed = " + str(settings["max_jog_speed"]))

# Settings widget id -> (REBset_v1.ini tag, fallback default matching
# REB.ini's own shipped value). Each of these patches ALL occurrences of
# its ini key, both [DISPLAY] (jog slider) and [TRAJ] (trajectory-planner
# ceiling), since REB.ini ships the same value in both places for these
# keys - see REB_Setup/REB_Generate_Local_Ini.py for the overlay side.
VELOCITY_SETTINGS = {
    "Default_Linear_Velocity":  ("default_linear_velocity",  0.250000),
    "Min_Linear_Velocity":      ("min_linear_velocity",      0.016670),
    "Max_Angular_Velocity":     ("max_angular_velocity",     1.000000),
    "Default_Angular_Velocity": ("default_angular_velocity", 12.000000),
    "Min_Angular_Velocity":     ("min_angular_velocity",     1.666667),
}

def _save_velocity_setting(tag, value):
    '''
    Persists one of VELOCITY_SETTINGS' values into REBset_v1.ini -
    generic version of _save_max_jog_speed above, parameterized by key
    name since these five all follow the exact same shape.
    '''
    settings = reb_settings_io.load_settings()
    settings[tag] = round(value, 6)
    reb_settings_io.save_settings(settings)
    print("Saved " + tag + " = " + str(settings[tag]))

def _stepgen_step_rate_ceiling(stepgen_ch):
    '''
    Returns the hardware step-rate ceiling (steps/sec) for the given
    stepgen channel, derived from its live steplen/stepspace HAL params
    (nanoseconds, set from [JOINT_n]STEPLEN/STEPSPACE in REB.hal at
    startup and not editable from this UI) via
    1 / (STEPLEN + STEPSPACE) - the same formula worked by hand in
    REB.ini's STEPGEN_MAXVEL comments. Returns None if steplen+stepspace
    sum to zero, or if either can't be read (e.g. LinuxCNC isn't
    running).

    Reads both params via `halcmd getp` rather than the Python hal
    module's hal.get_value() (what REB_main.py's version of this
    function uses) - this program has no HAL component of its own and
    deliberately avoids `import hal` entirely, so every live HAL read
    goes through the same halcmd-subprocess pattern used everywhere
    else in this file.
    '''
    try:
        steplen_result = subprocess.run(
            ["halcmd", "getp", "hm2_7i92.0.stepgen." + stepgen_ch + ".steplen"],
            check=True, capture_output=True, text=True
        )
        stepspace_result = subprocess.run(
            ["halcmd", "getp", "hm2_7i92.0.stepgen." + stepgen_ch + ".stepspace"],
            check=True, capture_output=True, text=True
        )
        steplen = float(steplen_result.stdout.strip())
        stepspace = float(stepspace_result.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
        return None
    total_ns = steplen + stepspace
    if total_ns <= 0:
        return None
    return 1e9 / total_ns

def _warn_if_max_vel_exceeds_ceiling(self, widget, axis, stepgen_ch, scale, max_vel_widget):
    '''
    Warns and clamps when scale (steps/unit, just-committed) and the
    Max Vel spin button's current value together would ask the stepgen
    for more steps/sec than its steplen+stepspace timing can produce.
    LinuxCNC doesn't error in this case, it silently clips the
    stepgen's actual speed at the hardware ceiling - rather than leave
    the field showing a value the hardware can't actually honor, this
    pushes the calculated safe maximum back into max_vel_widget, which
    (via its own "value-changed" signal, already wired to
    _axis_set_max/_axis_set_max_letter) sends the corrected value to
    the live HAL maxvel pin the same way a manual edit would - no
    separate HAL write needed here. Only called for Max Vel, not Max
    Accel - there's no equivalent stepgen step-rate limit tied to
    acceleration.
    '''
    if scale == 0:
        return
    ceiling = _stepgen_step_rate_ceiling(stepgen_ch)
    if ceiling is None:
        return
    max_vel = max_vel_widget.get_value()
    if abs(scale) * max_vel <= ceiling:
        return

    # Round down (not to nearest) so the clamped value can't itself
    # still exceed the ceiling after rounding - the set_value() below
    # reenters this same check via max_vel_widget's own "value-changed"
    # signal, and a second popup there would be confusing.
    digits = max_vel_widget.get_digits()
    factor = 10 ** digits
    safe_max_vel = int((ceiling / abs(scale)) * factor) / factor

    # REB_Settings_v1.ini's Axis and Stepper Motor Tuning page shows one
    # representative Max Vel UOM label per table (LinearAxes_Max_Vel_UOM/
    # RotaryAxes_Max_Vel_UOM/Spindle_Max_Vel_UOM), not one per letter/
    # axis id the way the embedded Settings tab this replaces did (e.g.
    # "X_Max_Vel_UOM") - see _apply_measurement_system_labels' docstring
    # for the same consolidation. Map axis to the right table's label.
    if axis in ("Sp0", "Sp1"):
        uom_widget_id = "Spindle_Max_Vel_UOM"
    elif _axis_type_for_letter(axis) == "ANGULAR":
        uom_widget_id = "RotaryAxes_Max_Vel_UOM"
    else:
        uom_widget_id = "LinearAxes_Max_Vel_UOM"
    uom_widget = self.builder.get_object(uom_widget_id)
    uom = uom_widget.get_label().replace("\n", " ") if uom_widget is not None else "units/sec"
    dialog = Gtk.MessageDialog(
        transient_for=widget.get_toplevel(),
        flags=0,
        message_type=Gtk.MessageType.WARNING,
        buttons=Gtk.ButtonsType.OK,
        text=axis + ": Max Velocity was too high for this Scale",
    )
    dialog.format_secondary_text(
        "At a Scale of {:g}, the stepgen hardware can drive at most {:.4f} {} "
        "(step-rate ceiling {:.0f} steps/sec, from STEPLEN+STEPSPACE). "
        "Max Velocity has been reduced from {:g} {} to {:.4f} {} to match."
        .format(abs(scale), safe_max_vel, uom, ceiling, max_vel, uom, safe_max_vel, uom)
    )
    dialog.run()
    dialog.destroy()

    max_vel_widget.set_value(safe_max_vel)


class HandlerClass:
    '''
    Handler methods/state for the standalone REB_Settings program.
    Not gladevcp-launched - a single instance is created directly by
    main() below against one Gtk.Builder that owns every widget in
    REB_Settings_v1.ui, so (unlike REB_main.py, which this was
    extracted from) the "does this component own this widget" guards
    inherited from several methods below are always trivially true
    here. They're kept anyway rather than stripped out, since they're
    harmless and keep this code close to its REB_main.py original for
    anyone comparing the two later.
    '''

    def scroll_entries(self, widget, event):
        '''
        Lets the mouse scroll wheel scroll the viewport instead of the
        scroll being captured by a child widget such as a spin button
        under the cursor.
        '''
        adj = widget.get_property("vadjustment")
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
        and never lets it reach the viewport at all. Wired onto every
        spin button/combo box individually (see
        _install_viewport_scroll_redirect) so scrolling still works
        when the cursor happens to be over one of the many spin
        buttons/combos this program is mostly made of.
        '''
        viewport = widget.get_ancestor(Gtk.Viewport)
        if viewport is None:
            return False
        return self.scroll_entries(viewport, event)

    def _install_viewport_scroll_redirect(self, container):
        '''
        Recursively wires _redirect_scroll_to_viewport onto every spin
        button/combo box under container. Called once from __init__ on
        the outer scrollable viewport.
        '''
        for child in container.get_children():
            if isinstance(child, (Gtk.SpinButton, Gtk.ComboBox)):
                child.connect("scroll-event", self._redirect_scroll_to_viewport)
            if isinstance(child, Gtk.Container):
                self._install_viewport_scroll_redirect(child)

    def _load_scale_settings(self):
        '''
        Reads persisted axis scale values from REBset_v1.ini and
        applies them to the Settings spin buttons and the real stepgen
        position-scale HAL pins.

        Sp0/Sp1 (never reassignable - no letter concept applies) always
        own their own live pin unconditionally. The 6 reassignable
        channels are instead handled uniformly by LETTER (not internal
        id) below, resolving the live channel through
        CURRENT_LETTER_INTERNAL_ID for all 8 AXIS_SELECTION_LETTERS.
        '''
        if self.builder.get_object("X_Set_Scale") is None:
            return

        settings = reb_settings_io.load_settings()
        axes = settings.get("axes", {})

        for axis_id in ("Sp0", "Sp1"):
            axis_entry = axes.get(axis_id)
            if axis_entry is None or "scale" not in axis_entry:
                print("No stored scale found for axis " + axis_id
                      + " in " + SETTINGS_PATH)
                continue

            value = float(axis_entry["scale"])

            widget = self.builder.get_object(axis_id + "_Set_Scale")
            if widget is not None:
                widget.set_value(value)

            hal_pin = "hm2_7i92.0.stepgen." + AXIS_STEPGEN[axis_id] + ".position-scale"
            if self._linuxcnc_running:
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

        # All 8 letters (X,Z,U,V,W,A,B,C): letter-keyed - always load the
        # persisted value into the spin button, but only push it live if
        # this letter is currently assigned to a channel this session
        # (CURRENT_LETTER_INTERNAL_ID).
        for letter in AXIS_SELECTION_LETTERS:
            axis_entry = axes.get(letter)
            if axis_entry is None or "scale" not in axis_entry:
                print("No stored scale found for axis " + letter
                      + " in " + SETTINGS_PATH)
                continue

            value = float(axis_entry["scale"])

            widget = self.builder.get_object(letter + "_Set_Scale")
            if widget is not None:
                widget.set_value(value)

            internal_id = CURRENT_LETTER_INTERNAL_ID.get(letter)
            if internal_id is None:
                # Not currently assigned to any channel - nothing live
                # to push to, the value just sits in the spin button/
                # file for whenever this letter is assigned.
                continue

            hal_pin = "hm2_7i92.0.stepgen." + AXIS_STEPGEN[internal_id] + ".position-scale"
            if self._linuxcnc_running:
                try:
                    subprocess.run(
                        ["halcmd", "setp", hal_pin, str(value)],
                        check=True,
                        capture_output=True,
                        text=True
                    )
                    print("Restored " + hal_pin + " = " + str(value) + " (" + letter + ")")
                except subprocess.CalledProcessError as e:
                    print("Error restoring " + hal_pin + ": " + e.stderr)
                except FileNotFoundError:
                    print("halcmd not found - is the LinuxCNC environment sourced?")

    def _load_max_vel_accel_settings(self):
        '''
        Reads persisted axis/spindle "max_vel"/"max_accel" values from
        REBset_v1.ini and applies them to the Max Vel/Max Accel spin
        buttons and the real stepgen maxvel/maxaccel HAL params
        (hm2_7i92.0.stepgen.NN.maxvel/.maxaccel) - mirrors
        _load_scale_settings above exactly, just pushing two values per
        axis instead of one. These are the stepgen hardware limits, not
        [JOINT_n]MAX_VELOCITY/MAX_ACCELERATION - see reb_settings_io.py's
        _default_axis_entry for why.
        '''
        if self.builder.get_object("X_Set_Max_Vel") is None:
            return

        settings = reb_settings_io.load_settings()
        axes = settings.get("axes", {})

        def restore(axis_id, stepgen_ch, axis_entry, label_suffix=""):
            for key, widget_suffix, hal_suffix in (
                ("max_vel", "_Set_Max_Vel", ".maxvel"),
                ("max_accel", "_Set_Max_Accel", ".maxaccel"),
            ):
                if key not in axis_entry:
                    print("No stored " + key + " found for axis " + axis_id
                          + " in " + SETTINGS_PATH)
                    continue

                value = float(axis_entry[key])

                widget = self.builder.get_object(axis_id + widget_suffix)
                if widget is not None:
                    widget.set_value(value)

                if stepgen_ch is None or not self._linuxcnc_running:
                    continue

                hal_pin = "hm2_7i92.0.stepgen." + stepgen_ch + hal_suffix
                try:
                    subprocess.run(
                        ["halcmd", "setp", hal_pin, str(value)],
                        check=True,
                        capture_output=True,
                        text=True
                    )
                    print("Restored " + hal_pin + " = " + str(value) + label_suffix)
                except subprocess.CalledProcessError as e:
                    print("Error restoring " + hal_pin + ": " + e.stderr)
                except FileNotFoundError:
                    print("halcmd not found - is the LinuxCNC environment sourced?")

        for axis_id in ("Sp0", "Sp1"):
            axis_entry = axes.get(axis_id)
            if axis_entry is None:
                continue
            restore(axis_id, AXIS_STEPGEN[axis_id], axis_entry)

        # All 8 letters (X,Z,U,V,W,A,B,C): letter-keyed, same pattern as
        # _load_scale_settings.
        for letter in AXIS_SELECTION_LETTERS:
            axis_entry = axes.get(letter)
            if axis_entry is None:
                continue
            internal_id = CURRENT_LETTER_INTERNAL_ID.get(letter)
            stepgen_ch = AXIS_STEPGEN[internal_id] if internal_id is not None else None
            restore(letter, stepgen_ch, axis_entry, " (" + letter + ")")

    def _load_pid_settings(self):
        '''
        Reads persisted P/I/D/FF0/FF1/FF2 gains from REBset_v1.ini
        (each axis's <pid> block, or <pid_pos>/<pid_vel> for the two
        spindle loops) and applies them to the PID spin buttons and the
        live pid.* HAL gain pins - mirrors _load_scale_settings above
        for the axis stepgen scales (same per-letter resolution via
        CURRENT_LETTER_INTERNAL_ID for all 8 AXIS_SELECTION_LETTERS).
        REB_Scale_Persist.py is what writes these back into
        REBset_v1.ini at shutdown, the same as it already does for
        scale.
        '''
        if self.builder.get_object("X_Set_P") is None:
            return

        settings = reb_settings_io.load_settings()
        axes = settings.get("axes", {})

        def apply(axis_id, block_tag, hal_component, widget_id_for_param, push_live=True):
            '''
            widget_id_for_param(param) builds the Settings widget id for
            a given P/I/D/FF0/FF1/FF2 param - axes and spindle loops put
            their disambiguating suffix in different places (X_Set_P vs
            Sp0_Set_P_Pos), so the caller supplies this rather than
            apply() assuming one fixed naming shape.

            push_live=False (used for EXTRA_SETTINGS_LETTERS when not
            currently assigned to a channel - see below) still sets the
            widget from file but skips the halcmd push, since
            hal_component names a pid.* instance that doesn't currently
            exist rather than one that's merely stale.
            '''
            axis_entry = axes.get(axis_id)
            if axis_entry is None:
                print("No axis \"" + axis_id + "\" entry found in " + SETTINGS_PATH)
                return

            pid_block = axis_entry.get(block_tag)
            if pid_block is None:
                print("No \"" + block_tag + "\" entry found for axis " + axis_id
                      + " in " + SETTINGS_PATH)
                return

            for param in PID_PARAMS:
                widget_id = widget_id_for_param(param)

                if param not in pid_block:
                    print("No stored " + param + " found for " + widget_id
                          + " in " + SETTINGS_PATH)
                    continue

                value = pid_block[param]
                widget = self.builder.get_object(widget_id)
                if widget is not None:
                    widget.set_value(float(value))

                if not push_live:
                    continue

                hal_pin = hal_component + "." + PID_PARAM_PIN[param]
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

        for spindle_id, loops in PID_SPINDLE_LOOPS.items():
            for suffix, component in loops.items():
                block_tag = "pid_pos" if suffix == "Pos" else "pid_vel"
                apply(spindle_id, block_tag, component,
                      lambda param, spindle_id=spindle_id, suffix=suffix:
                          spindle_id + "_Set_" + param + "_" + suffix,
                      push_live=self._linuxcnc_running)

        # All 8 letters (X,Z,U,V,W,A,B,C): letter-keyed, no fixed channel
        # of their own - the live pid.<letter> component is named after
        # the letter itself (REB_Generate_Local_Ini.py renames each
        # channel's pid component to match its current assignment), so
        # it only exists at all while this letter is currently assigned
        # to a channel (CURRENT_LETTER_INTERNAL_ID).
        for letter in AXIS_SELECTION_LETTERS:
            apply(letter, "pid", "pid." + letter.lower(),
                  lambda param, letter=letter: letter + "_Set_" + param,
                  push_live=self._linuxcnc_running and letter in CURRENT_LETTER_INTERNAL_ID)

    def _load_backlash_settings(self):
        '''
        Reads persisted axis/spindle backlash values from REBset_v1.ini
        (each axis's <backlash> element) and applies them to the
        Backlash spin buttons and the live joint.N.backlash HAL
        parameters - mirrors _load_scale_settings above (same
        per-letter resolution via CURRENT_LETTER_INTERNAL_ID for all 8
        AXIS_SELECTION_LETTERS). REB_Scale_Persist.py is what writes
        these back into REBset_v1.ini at shutdown, the same as it
        already does for scale and PID gains.
        '''
        if self.builder.get_object("X_Set_Backlash") is None:
            return

        settings = reb_settings_io.load_settings()
        axes = settings.get("axes", {})

        for axis_id in ("Sp0", "Sp1"):
            axis_entry = axes.get(axis_id)
            if axis_entry is None or "backlash" not in axis_entry:
                print("No stored backlash found for axis " + axis_id
                      + " in " + SETTINGS_PATH)
                continue

            value = float(axis_entry["backlash"])

            widget = self.builder.get_object(axis_id + "_Set_Backlash")
            if widget is not None:
                widget.set_value(value)

            hal_pin = "joint." + str(JOINT_NUMBER[axis_id]) + ".backlash"
            if self._linuxcnc_running:
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

        # All 8 letters (X,Z,U,V,W,A,B,C): letter-keyed, no fixed joint
        # number of their own - always load the persisted value into the
        # spin button, but only push it live if this letter is currently
        # assigned to a channel this session (CURRENT_LETTER_INTERNAL_ID),
        # same pattern as _load_scale_settings.
        for letter in AXIS_SELECTION_LETTERS:
            axis_entry = axes.get(letter)
            if axis_entry is None or "backlash" not in axis_entry:
                print("No stored backlash found for axis " + letter
                      + " in " + SETTINGS_PATH)
                continue

            value = float(axis_entry["backlash"])

            widget = self.builder.get_object(letter + "_Set_Backlash")
            if widget is not None:
                widget.set_value(value)

            internal_id = CURRENT_LETTER_INTERNAL_ID.get(letter)
            if internal_id is None or not self._linuxcnc_running:
                continue

            hal_pin = "joint." + str(JOINT_NUMBER[internal_id]) + ".backlash"
            try:
                subprocess.run(
                    ["halcmd", "setp", hal_pin, str(value)],
                    check=True,
                    capture_output=True,
                    text=True
                )
                print("Restored " + hal_pin + " = " + str(value) + " (" + letter + ")")
            except subprocess.CalledProcessError as e:
                print("Error restoring " + hal_pin + ": " + e.stderr)
            except FileNotFoundError:
                print("halcmd not found - is the LinuxCNC environment sourced?")

    def _apply_measurement_system_labels(self, system):
        '''
        Sets the Scale/Max Vel/Max Accel unit-of-measure labels for the
        Linear Axes table (X/Z/U/V/W) to match the given system
        ("Metric" or "Imperial").

        Adapted from REB_main.py's version of this method for
        REB_Settings_v1.ui's consolidated UOM labels: the embedded
        Settings tab this replaces had one Scale/Max_Vel/Max_Accel_UOM
        label PER LETTER (needed because a channel's type used to be
        independently reassignable there); this program's Axis and
        Stepper Motor Tuning page instead shows one representative UOM
        label per table (LinearAxes_*_UOM/RotaryAxes_*_UOM/
        Spindle_*_UOM), since letter always determines type here (see
        _axis_type_for_letter) - a channel can no longer be reassigned
        away from its permanent type, so only the Linear table's three
        labels ever need to change; degrees (Rotary/Angular) and
        revolutions (Spindles) aren't metric or imperial, and those two
        tables' .ui-file-static text is already correct forever. The
        original method also set the main panel's Feed_UOM/IdxDist_UOM
        labels - this program has no main panel widgets, so that part
        is dropped entirely rather than ported as a permanent no-op.
        '''
        if system == "Metric":
            scale_uom, vel_uom, accel_uom = "pulses\n/ mm", "mm\n/ sec", "mm\n/ sec²"
        else:
            scale_uom, vel_uom, accel_uom = "pulses\n/ in", "in\n/ sec", "in\n/ sec²"

        scale_label = self.builder.get_object("LinearAxes_Scale_UOM")
        if scale_label is not None:
            scale_label.set_text(scale_uom)

        vel_label = self.builder.get_object("LinearAxes_Max_Vel_UOM")
        if vel_label is not None:
            vel_label.set_text(vel_uom)

        accel_label = self.builder.get_object("LinearAxes_Max_Accel_UOM")
        if accel_label is not None:
            accel_label.set_text(accel_uom)

    def _load_measurement_system(self):
        '''
        Reads the persisted Measurement System ("Metric"/"Imperial", default
        "Imperial" if absent - matching REB.ini's shipped inch/INCH default)
        from REBset_v1.ini, applies it to the Measurement_System combo box
        and the Linear Axes table's unit-of-measure labels.
        '''
        settings = reb_settings_io.load_settings()
        system = settings.get("measurement_system", "Imperial")
        if system not in ("Metric", "Imperial"):
            system = "Imperial"

        combo = self.builder.get_object("Measurement_System")
        if combo is not None:
            self._applying_measurement_system = True
            combo.set_active(0 if system == "Metric" else 1)
            self._applying_measurement_system = False

        self._apply_measurement_system_labels(system)

    def _load_device_names(self):
        '''
        Reads the persisted device-name list (REBset_v1.ini's
        <device_names> block) and applies it to the Other page's Device
        Names GtkTextView, one name per line - mirrors
        _load_measurement_system above.
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
        dropped.
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
        letter. Every letter is always offered here - any channel is
        freely selectable to any letter, with duplicates flagged live
        instead (see _update_duplicate_warnings) and only actually
        blocked from being persisted, not from being picked in the
        first place.

        Called both by _load_channel_assignments (startup) and by
        Channel_0N_Axis_Changed itself (every time one combo's choice
        changes).
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

    def _update_duplicate_warnings(self):
        '''
        Flags every channel whose currently-selected letter is also
        selected by at least one other channel, by setting its
        Channel_0N_Warning label to a red "Duplicate!" notice (cleared
        for channels with no conflict). A duplicate can be picked
        freely, it's just flagged immediately rather than rejected.
        Channel_0N_Axis_Changed uses this method's return value to
        decide whether the assignment is safe to persist - actually
        saving/showing the restart notice is refused for as long as any
        duplicate remains, resuming automatically on whichever change
        clears it.

        Returns True if at least one duplicate exists (False, and every
        warning cleared, if the assignment is fully valid).
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
        Axis Selection tab's six letter combos.

        Adapted from REB_main.py's version of this method: the embedded
        Settings tab this replaces also read/populated a per-channel
        Type combo here (<channel_types>) - that combo doesn't exist in
        this program's UI at all (type is always derived from the
        letter - see _axis_type_for_letter), so that half is dropped
        entirely rather than ported as a no-op.
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
        shipped [TRAJ]/[DISPLAY] MAX_LINEAR_VELOCITY) from REBset_v1.ini
        and applies it to the Max Jog Speed spin button.
        '''
        settings = reb_settings_io.load_settings()
        value = float(settings.get("max_jog_speed", 1.0))

        spin = self.builder.get_object("Max_Jog_Speed")
        if spin is not None:
            self._applying_max_jog_speed = True
            spin.set_value(value)
            self._applying_max_jog_speed = False

    def _load_velocity_settings(self):
        '''
        Reads each of VELOCITY_SETTINGS' persisted values from
        REBset_v1.ini (default to REB.ini's own shipped value if never
        persisted) and applies them to their spin buttons - mirrors
        _load_max_jog_speed above, generalized to all five at once
        under one shared guard flag (they're only ever loaded together,
        so one flag covering the whole batch is enough).
        '''
        settings = reb_settings_io.load_settings()

        self._applying_velocity_settings = True
        try:
            for widget_id, (tag, default) in VELOCITY_SETTINGS.items():
                value = float(settings.get(tag, default))

                spin = self.builder.get_object(widget_id)
                if spin is not None:
                    spin.set_value(value)
        finally:
            self._applying_velocity_settings = False

    def _save_axis_comment(self, axis_id, text):
        '''
        Writes a single axis's comment back into REBset_v1.ini's
        usercomment value for that axis. The main panel (a separate
        program) is what actually displays this field - REB_Settings
        can only patch the file, not the live widget - so the main
        panel only picks up the new text at its own next startup.
        '''
        settings = reb_settings_io.load_settings()
        settings.setdefault("axes", {}).setdefault(axis_id, {})["usercomment"] = text
        reb_settings_io.save_settings(settings)
        print("Saved " + axis_id + " comment")

    def _read_pid_gains(self, widget_id_for_param):
        '''
        Reads P/I/D/FF0/FF1/FF2 from one axis's/spindle loop's own
        widgets into a plain {param: value} dict, for embedding
        directly in a settings-file JSON "pid"/"pid_pos"/"pid_vel"
        entry.
        '''
        values = {}
        for param in PID_PARAMS:
            widget = self.builder.get_object(widget_id_for_param(param))
            if widget is not None:
                values[param] = widget.get_value()
        return values

    def Settings_Notes_Changed(self, buffer):
        # Wired to the Notes GtkTextView's GtkTextBuffer "changed"
        # signal. The Notes field is free-text scratch space only -
        # nothing persists it.
        pass

    def Open_User_Manual(self, widget):
        # Opens the Rose Engine Butler User Manual's Axis Configuration
        # File page in the default web browser.
        url = "https://roseenginebutler.com/UserManual/index.php?n=Main.AxisConfigurationFile"
        webbrowser.open(url)
        print("Opening website " + url)

    def OpenPidTuningReference(self, widget):
        # Opens LinuxCNC's own documentation for the pid HAL component
        # (the control loop these P/I/D/FF values tune) in a browser.
        url = "https://linuxcnc.org/docs/html/man/man9/pid.9.html"
        webbrowser.open(url)
        print("Opening website " + url)

    def OpenPidControllerWikipedia(self, widget):
        # Opens Wikipedia's PID controller article - general background
        # on P/I/D/FF terms, separate from LinuxCNC's own pid-component
        # reference above.
        url = "https://en.wikipedia.org/wiki/PID_controller"
        webbrowser.open(url)
        print("Opening website " + url)

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

    def Settings_Save(self, widget):
        if self.builder.get_object("X_Set_Scale") is None:
            return

        print("=================================================")
        print("FUNCTION Settings_Save")
        self._write_rebset_snapshot()

    def _write_rebset_snapshot(self):
        '''
        Writes this program's live Scale/Backlash/Max Vel/Max Accel/PID
        widget values into REBset_v1.ini's per-axis entries. Reads the
        whole file once, patches every axis's dict entry in memory,
        then writes it back once - unlike the shutdown path
        (REB_Scale_Persist.py), which patches and writes incrementally
        since it goes through separate halcmd calls per value.
        '''
        settings = reb_settings_io.load_settings()
        axes = settings.setdefault("axes", {})

        for axis_id in list(AXIS_STEPGEN) + list(EXTRA_SETTINGS_LETTERS):
            axis_entry = axes.setdefault(axis_id, {})

            scale_widget = self.builder.get_object(axis_id + "_Set_Scale")
            if scale_widget is not None:
                axis_entry["scale"] = scale_widget.get_value()

            backlash_widget = self.builder.get_object(axis_id + "_Set_Backlash")
            if backlash_widget is not None:
                axis_entry["backlash"] = backlash_widget.get_value()

            max_vel_widget = self.builder.get_object(axis_id + "_Set_Max_Vel")
            if max_vel_widget is not None:
                axis_entry["max_vel"] = max_vel_widget.get_value()

            max_accel_widget = self.builder.get_object(axis_id + "_Set_Max_Accel")
            if max_accel_widget is not None:
                axis_entry["max_accel"] = max_accel_widget.get_value()

            if axis_id in PID_AXES or axis_id in EXTRA_SETTINGS_LETTERS:
                values = self._read_pid_gains(lambda param, axis_id=axis_id: axis_id + "_Set_" + param)
                if values:
                    axis_entry.setdefault("pid", {}).update(values)
            elif axis_id in PID_SPINDLE_LOOPS:
                for suffix, block_tag in (("Pos", "pid_pos"), ("Vel", "pid_vel")):
                    values = self._read_pid_gains(
                        lambda param, axis_id=axis_id, suffix=suffix: axis_id + "_Set_" + param + "_" + suffix
                    )
                    if values:
                        axis_entry.setdefault(block_tag, {}).update(values)

        reb_settings_io.save_settings(settings)
        print("Saved live scale/backlash/max vel/max accel/PID values to " + SETTINGS_PATH)

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
        # confusing the two.
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
            with open(path, "r") as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            _show_settings_error(widget, "Could not read " + path + ":\n" + str(e))
            return

        if not isinstance(data, dict) or "axes" not in data:
            _show_settings_error(widget, path + " is not a Rose Engine Butler settings file.")
            return

        self._apply_settings_root(widget, data, path, "usercomment")

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
            # More than one different device name was selected - no
            # single name to build the file's default name from, so
            # fall back to today's date instead of refusing to export.
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

        data = {"axes": {}}

        def get_axis_entry(axis_id):
            return data["axes"].setdefault(axis_id, {})

        # Each selected axis exports Scale, Backlash, Max Vel/Max Accel,
        # and PID together as one unit - see _run_export_selection_dialog
        # for why these no longer get independent checkboxes.
        exported = []
        for axis_id in selected.get("axes", ()):
            spin = self.builder.get_object(axis_id + "_Set_Scale")
            if spin is not None:
                get_axis_entry(axis_id)["scale"] = spin.get_value()
                exported.append(axis_id + " Scale")

            backlash_spin = self.builder.get_object(axis_id + "_Set_Backlash")
            if backlash_spin is not None:
                get_axis_entry(axis_id)["backlash"] = backlash_spin.get_value()
                exported.append(axis_id + " Backlash")

            max_vel_spin = self.builder.get_object(axis_id + "_Set_Max_Vel")
            if max_vel_spin is not None:
                get_axis_entry(axis_id)["max_vel"] = max_vel_spin.get_value()
                exported.append(axis_id + " Max Vel")

            max_accel_spin = self.builder.get_object(axis_id + "_Set_Max_Accel")
            if max_accel_spin is not None:
                get_axis_entry(axis_id)["max_accel"] = max_accel_spin.get_value()
                exported.append(axis_id + " Max Accel")

            if axis_id in PID_AXES or axis_id in EXTRA_SETTINGS_LETTERS:
                self._export_pid_block(get_axis_entry(axis_id), "pid",
                                        lambda param, axis_id=axis_id: axis_id + "_Set_" + param)
                exported.append(axis_id + " PID")
            elif axis_id in PID_SPINDLE_LOOPS:
                for suffix in ("Pos", "Vel"):
                    block_tag = "pid_pos" if suffix == "Pos" else "pid_vel"
                    self._export_pid_block(
                        get_axis_entry(axis_id), block_tag,
                        lambda param, axis_id=axis_id, suffix=suffix: axis_id + "_Set_" + param + "_" + suffix
                    )
                exported.append(axis_id + " PID")

        for axis_id, comment in selected.get("comments", {}).items():
            get_axis_entry(axis_id)["comment"] = comment
            exported.append(axis_id + " Comment (" + comment + ")")

        if selected.get("measurement_system"):
            combo = self.builder.get_object("Measurement_System")
            system = combo.get_active_text() if combo is not None else None
            if system:
                data["measurement_system"] = system
                exported.append("Measurement System")

        try:
            reb_settings_io.save_settings(data, path)
        except OSError as e:
            _show_settings_error(widget, "Could not write " + path + ":\n" + str(e))
            return

        print("Exported " + ", ".join(exported) + " to " + path)

    def _export_pid_block(self, axis_entry, block_tag, widget_id_for_param):
        '''
        Reads P/I/D/FF0/FF1/FF2 from this axis's/spindle loop's own
        widgets into a "pid"/"pid_pos"/"pid_vel" dict on axis_entry -
        the same shape REBset_v1.ini already uses, so a value
        round-trips through Import_Settings/_load_pid_settings
        identically either way.
        '''
        block = {}
        for param in PID_PARAMS:
            widget = self.builder.get_object(widget_id_for_param(param))
            if widget is None:
                continue
            block[param] = widget.get_value()
        if block:
            axis_entry[block_tag] = block

    def _run_export_selection_dialog(self, widget):
        '''
        Modal checklist: one row per axis, each with a single checkbox
        covering that axis's Scale, Backlash, Max Vel/Max Accel, and PID
        together, plus a Device dropdown (populated from the Other
        page's maintained Device Names list) to optionally label that
        axis's export with which physical device it belongs to.

        Each Device combo defaults to whatever's currently set on the
        main panel's own comment field for that axis (X/Z/U/V/W/B - see
        COMMENT_AXES), via _read_persisted_axis_comment against
        SETTINGS_PATH - the main panel is a separate program from this
        one, so its live widget isn't reachable directly. Sp0/Sp1 have
        no such field, so they default to SPINDLE_DEFAULT_DEVICE_NAME
        instead.

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
        comments_settings = reb_settings_io.load_settings()

        axis_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        content.pack_start(axis_col, False, False, 0)

        # Sized so the "Device" header lines up with the combo boxes
        # below it, not just with wherever the widest axis checkbox
        # happens to end.
        axis_label_group = Gtk.SizeGroup(mode=Gtk.SizeGroupMode.HORIZONTAL)

        axis_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        axis_label = section_label("Axis")
        axis_label_group.add_widget(axis_label)
        axis_header.pack_start(axis_label, False, False, 0)
        axis_header.pack_start(section_label("Device"), False, False, 0)
        axis_col.pack_start(axis_header, False, False, 0)

        checks = {}
        comment_combos = {}
        for axis_id in list(AXIS_STEPGEN) + list(EXTRA_SETTINGS_LETTERS):
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

            stored = (_read_persisted_axis_comment(axis_id, comments_settings)
                      or SPINDLE_DEFAULT_DEVICE_NAME.get(axis_id, ""))
            try:
                combo.set_active(device_names.index(stored) + 1 if stored else 0)
            except ValueError:
                combo.set_active(0)

            combo.set_tooltip_text(
                "Optional: label this axis's export with one of the "
                "device names maintained on the Other page."
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
            with open(path, "r") as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            _show_settings_error(widget, "Could not read " + path + ":\n" + str(e))
            return

        if not isinstance(data, dict) or "axes" not in data:
            _show_settings_error(widget, path + " is not a Rose Engine Butler export file.")
            return

        self._apply_settings_root(widget, data, path, "comment")

    def _apply_settings_root(self, widget, data, path, comment_key):
        '''
        Applies whatever subset of axis Scale/Backlash/Max Vel/Max
        Accel/PID/comment/Measurement System values a parsed settings
        dict contains to the live widgets, then reports what changed.
        Shared by Import_Settings (small "comment"-keyed
        Export_Settings subset files) and Settings_Load (full
        "usercomment"-keyed REBset_v1.ini-shaped snapshots) -
        comment_key is the only thing that differs between those two
        file shapes. Each value is applied through its own widget
        handler (<Axis>_Set_Scale/<Axis>_Set_Backlash/
        Measurement_System_Changed) rather than written to disk
        directly - it keeps the usual per-axis safety checks (motion
        abort, disable-if-enabled) in the loop exactly as if the
        operator had typed/selected each value themselves.
        '''
        imported = []
        comment_imported = False
        for axis_id, axis_entry in data.get("axes", {}).items():
            if axis_id not in AXIS_STEPGEN and axis_id not in EXTRA_SETTINGS_LETTERS:
                continue
            if not isinstance(axis_entry, dict):
                continue

            # Scale and PID are independent - a file may carry either,
            # both, or neither for a given axis, so check each on its own
            # rather than skipping the whole axis entry when one is
            # absent.
            if "scale" in axis_entry:
                spin = self.builder.get_object(axis_id + "_Set_Scale")
                if spin is not None:
                    try:
                        scale = float(axis_entry["scale"])
                    except (TypeError, ValueError):
                        print("Skipping " + axis_id + " scale - not a number: " + str(axis_entry["scale"]))
                        scale = None
                    if scale is not None:
                        spin.set_value(scale)  # fires <Axis>_Set_Scale: abort/disable-if-enabled/halcmd setp
                        imported.append(axis_id + " Scale")

            if "backlash" in axis_entry:
                spin = self.builder.get_object(axis_id + "_Set_Backlash")
                if spin is not None:
                    try:
                        backlash = float(axis_entry["backlash"])
                    except (TypeError, ValueError):
                        print("Skipping " + axis_id + " backlash - not a number: " + str(axis_entry["backlash"]))
                        backlash = None
                    if backlash is not None:
                        spin.set_value(backlash)  # fires <Axis>_Set_Backlash: halcmd setp
                        imported.append(axis_id + " Backlash")

            if "max_vel" in axis_entry:
                spin = self.builder.get_object(axis_id + "_Set_Max_Vel")
                if spin is not None:
                    try:
                        max_vel = float(axis_entry["max_vel"])
                    except (TypeError, ValueError):
                        print("Skipping " + axis_id + " max_vel - not a number: " + str(axis_entry["max_vel"]))
                        max_vel = None
                    if max_vel is not None:
                        spin.set_value(max_vel)  # fires <Axis>_Set_Max_Vel: halcmd setp
                        imported.append(axis_id + " Max Vel")

            if "max_accel" in axis_entry:
                spin = self.builder.get_object(axis_id + "_Set_Max_Accel")
                if spin is not None:
                    try:
                        max_accel = float(axis_entry["max_accel"])
                    except (TypeError, ValueError):
                        print("Skipping " + axis_id + " max_accel - not a number: " + str(axis_entry["max_accel"]))
                        max_accel = None
                    if max_accel is not None:
                        spin.set_value(max_accel)  # fires <Axis>_Set_Max_Accel: halcmd setp
                        imported.append(axis_id + " Max Accel")

            # Comment (device name): only COMMENT_AXES have a live
            # comment field to apply it to (Sp0/Sp1 don't - the main
            # panel has no spindle comment entries), so a file's comment
            # for a spindle is informational-only and doesn't round-trip
            # back into anything here. _save_axis_comment only patches
            # REBset_v1.ini on disk - it can't reach into the main
            # panel's own Comment widget, a separate program with no
            # live IPC to this one. The panel only picks up the new text
            # at its own next startup - hence comment_imported below.
            comment_value = axis_entry.get(comment_key)
            if comment_value is not None and axis_id in COMMENT_AXES:
                self._save_axis_comment(axis_id, comment_value)
                imported.append(axis_id + " Comment")
                comment_imported = True

            pid_applied = False
            if axis_id in PID_AXES or axis_id in EXTRA_SETTINGS_LETTERS:
                pid_applied = self._import_pid_block(
                    axis_entry, "pid", lambda param, axis_id=axis_id: axis_id + "_Set_" + param
                )
            elif axis_id in PID_SPINDLE_LOOPS:
                for suffix in ("Pos", "Vel"):
                    block_tag = "pid_pos" if suffix == "Pos" else "pid_vel"
                    if self._import_pid_block(
                        axis_entry, block_tag,
                        lambda param, axis_id=axis_id, suffix=suffix: axis_id + "_Set_" + param + "_" + suffix
                    ):
                        pid_applied = True
            if pid_applied:
                imported.append(axis_id + " PID")

        measurement_system = data.get("measurement_system")
        if measurement_system in ("Metric", "Imperial"):
            combo = self.builder.get_object("Measurement_System")
            if combo is not None:
                combo.set_active(0 if measurement_system == "Metric" else 1)  # fires Measurement_System_Changed
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

    def _import_pid_block(self, axis_entry, block_tag, widget_id_for_param):
        '''
        Mirror of _export_pid_block: reads a "pid"/"pid_pos"/"pid_vel"
        dict (if present) and applies each P/I/D/FF0/FF1/FF2 value it
        contains to that param's own widget via set_value() - fires the
        same _pid_set handler a live edit would (pushes straight to the
        live pid.* HAL gain pin). Returns True if anything was actually
        applied.
        '''
        block = axis_entry.get(block_tag)
        if not isinstance(block, dict):
            return False

        applied = False
        for param in PID_PARAMS:
            if param not in block:
                continue

            widget = self.builder.get_object(widget_id_for_param(param))
            if widget is None:
                continue

            try:
                value = float(block[param])
            except (TypeError, ValueError):
                print("Skipping " + widget_id_for_param(param) + " - not a number: " + str(block[param]))
                continue

            widget.set_value(value)
            applied = True

        return applied

    def Sp0_Set_Scale(self, widget):
        '''
        Value-changed handler for Sp0's Scale spin button. Sp0 is never
        reassignable (no letter concept applies), so its stepgen
        channel (04) and ENA-light/override signal name ("sp0") are
        fixed constants here rather than resolved through
        CURRENT_LETTER_INTERNAL_ID the way the 8 letter-labeled Scale
        handlers (_axis_set_scale_letter) do.
        '''
        print("=================================================")
        print("FUNCTION Sp0_Set_Scale")

        # Stop any Run Operation spindle rotation (M3/M4) before this
        # scale change lands - a large change to position-scale while
        # the spindle is actively spinning under S-word/M3/M4 control
        # could otherwise cause a runaway once the new scale takes
        # effect.
        #
        # Only if the machine is actually ON: this handler also fires
        # from _load_scale_settings's programmatic spin.set_value() (the
        # startup auto-restore from REBset_v1.ini), which runs before
        # the operator has powered on/reset E-stop, when there's no
        # spinning spindle to stop anyway.
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
        # the axis, set the sp0-ena-settings-allow signal FALSE (see
        # _axis_set_scale_letter's docstring for why "sets" on the
        # signal, not "setp" on the pin - REB_PostGUI_v1.hal nets that
        # signal from gladevcp.Sp0_Ena_Override).
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
                try:
                    subprocess.run(
                        ["halcmd", "sets", "sp0-ena-settings-allow", "FALSE"],
                        check=True,
                        capture_output=True,
                        text=True
                    )
                    print("Set sp0-ena-settings-allow = FALSE")
                except subprocess.CalledProcessError as e:
                    print("Error setting sp0-ena-settings-allow: " + e.stderr)
                except FileNotFoundError:
                    print("halcmd not found - is the LinuxCNC environment sourced?")
            else:
                print("Sp0 axis is already disabled")
        except subprocess.CalledProcessError as e:
            print("Error checking " + status_pin + ": " + e.stderr)
        except FileNotFoundError:
            print("halcmd not found - is the LinuxCNC environment sourced?")

        hal_pin = "hm2_7i92.0.stepgen.06.position-scale"
        cmd = ["halcmd", "setp", hal_pin, str(Sp0_Scale)]

        try:
            subprocess.run(
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

    def Sp1_Set_Scale(self, widget):
        '''
        Value-changed handler for Sp1's Scale spin button - mirrors
        Sp0_Set_Scale above exactly, for stepgen channel 07 and the
        sp1-ena-settings-allow signal.
        '''
        print("=================================================")
        print("FUNCTION Sp1_Set_Scale")

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
                try:
                    subprocess.run(
                        ["halcmd", "sets", "sp1-ena-settings-allow", "FALSE"],
                        check=True,
                        capture_output=True,
                        text=True
                    )
                    print("Set sp1-ena-settings-allow = FALSE")
                except subprocess.CalledProcessError as e:
                    print("Error setting sp1-ena-settings-allow: " + e.stderr)
                except FileNotFoundError:
                    print("halcmd not found - is the LinuxCNC environment sourced?")
            else:
                print("Sp1 axis is already disabled")
        except subprocess.CalledProcessError as e:
            print("Error checking " + status_pin + ": " + e.stderr)
        except FileNotFoundError:
            print("halcmd not found - is the LinuxCNC environment sourced?")

        hal_pin = "hm2_7i92.0.stepgen.07.position-scale"
        cmd = ["halcmd", "setp", hal_pin, str(Sp1_Scale)]

        try:
            subprocess.run(
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

    def __init__(self, builder):
        self.builder = builder

        # main() only ever constructs HandlerClass after confirming
        # LinuxCNC is NOT running (see _linuxcnc_is_running/main's
        # blocking dialog) - so this is always False in practice, but
        # every _load_* method below still checks it explicitly rather
        # than assuming, so they degrade the same way if HandlerClass
        # is ever constructed some other way (as this session's own
        # verification scripts already do). Without this gate, each
        # _load_* method below would attempt a `halcmd setp` for every
        # single axis/spindle/PID-gain pin and print an individual
        # "parameter or pin not found" error for each one when nothing
        # is running to own those pins (confirmed live 4 September
        # 2026, ~90 such lines from one normal startup) - computing
        # this once and skipping the doomed attempts entirely, with one
        # informational line instead, is far less alarming for what is
        # in fact the expected, intended way to run this program.
        self._linuxcnc_running = _linuxcnc_is_running()
        if not self._linuxcnc_running:
            print("LinuxCNC is not running - settings loaded from REBset_v1.ini only; live HAL pins were not touched.")

        # Suppresses Measurement_System_Changed's save/patch/popup while
        # _load_measurement_system is itself the one driving the combo box
        # at startup (see combo.set_active there) - a startup load should
        # not re-save REBset_v1.ini or pop up the restart notice.
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

        # Same suppression as above, for _load_channel_assignments (and
        # Channel_0N_Axis_Changed's own re-filtering rebuild - see
        # _rebuild_all_channel_combo_items) driving the six Axis Selection
        # combos.
        self._applying_channel_assignments = False

        # Restore persisted axis scale values (REBset_v1.ini) into the
        # spin buttons and the real stepgen scale pins.
        self._load_scale_settings()

        # Restore persisted P/I/D/FF0/FF1/FF2 gains (REBset_v1.ini) into
        # the PID spin buttons and the live pid.* HAL gain pins.
        self._load_pid_settings()

        # Restore persisted backlash values (REBset_v1.ini) into the
        # Backlash spin buttons and the live joint.N.backlash HAL
        # parameters.
        self._load_backlash_settings()

        # Restore persisted Max Vel/Max Accel values (REBset_v1.ini)
        # into the spin buttons and the live stepgen maxvel/maxaccel
        # HAL params.
        self._load_max_vel_accel_settings()

        # Restore the persisted Measurement System (REBset_v1.ini) into
        # the Measurement_System combo box and the Linear Axes table's
        # unit-of-measure labels.
        self._load_measurement_system()

        # Restore the persisted device-name list (REBset_v1.ini) into
        # the Other page's Device Names text box.
        self._load_device_names()

        # Restore the persisted channel -> axis letter assignment
        # (REBset_v1.ini) into the Axis Selection tab's six combos.
        self._load_channel_assignments()

        # Restore the persisted Max Jog Speed (REBset_v1.ini) into the
        # Max Jog Speed spin button.
        self._load_max_jog_speed()

        # Restore the five persisted VELOCITY_SETTINGS values
        # (REBset_v1.ini) into the jog-speed spin buttons.
        self._load_velocity_settings()

        # Let the mouse wheel scroll the page even when the cursor is
        # over one of its many spin buttons/combo boxes, rather than only
        # working over the shrinking gaps between them - see
        # _redirect_scroll_to_viewport.
        viewport = self.builder.get_object("viewport1")
        if viewport is not None:
            self._install_viewport_scroll_redirect(viewport)


# ------------------------------------------------------------------
# Generated per-channel handlers, for all 8 selectable letters
# (AXIS_SELECTION_LETTERS) and the two fixed spindles (Sp0/Sp1).
#
# Widgets are bound per LETTER, not per internal id, for Scale/Backlash/
# Max Vel/Max Accel/PID: the widget labeled e.g. "B" must always mean
# "whichever channel currently wears letter B," not "channel 05,
# forever" - see _axis_set_scale_letter's docstring for the live bug
# this fixes (found live 3 September 2026, in REB_main.py, before this
# program existed).
#
# This has to produce real, named methods rather than a __getattr__
# dispatcher: GtkBuilder discovers handlers via dir(instance) fed into
# builder.connect_signals(), and dir() does not enumerate names that
# only exist through __getattr__.

def _axis_set_scale_letter(letter):
    '''
    Value-changed handler for one of the 8 letter-labeled Scale spin
    buttons (<letter>_Set_Scale, letter in AXIS_SELECTION_LETTERS). The
    live stepgen pin (and the ENA override used to disable the axis
    first) are resolved through CURRENT_LETTER_INTERNAL_ID/AXIS_STEPGEN
    at call time, rather than a closure-captured constant. If this
    letter isn't currently assigned to any channel, the value is simply
    kept (and persisted at shutdown by REB_Scale_Persist.py) with no
    live HAL write to make.

    scale is rounded to 3 decimal places, matching this widget's own
    "digits" property in the .ui file.

    The axis-disable step uses `halcmd sets <letter>-ena-settings-allow
    FALSE` rather than a direct pin write - this program has no HAL
    component of its own, so it can't do the embedded Settings tab's
    old `self.halcomp[...] = False` trick (that only worked because the
    writer WAS the netted component, REBCnfg). Since 4 September 2026,
    REB_PostGUI_v1.hal nets that "allow" signal from the main panel's
    own always-running HAL component ("gladevcp.<Axis>_Ena_Override")
    instead - a real component this program can influence, cross-
    process, the same way the main panel's own _clear_ena_override
    already does in the other direction (`halcmd sets ... TRUE`). Once
    a pin is netted to a signal, halcmd can't "setp" the pin directly
    ("pin is connected to a signal") - the signal itself has to be set
    instead, via "halcmd sets".
    '''
    def handler(self, widget):
        print("=================================================")
        print("FUNCTION " + letter + "_Set_Scale")

        internal_id = CURRENT_LETTER_INTERNAL_ID.get(letter)
        if internal_id is None:
            print(letter + " is not currently assigned to a channel - value kept, no live HAL write")
            return

        c.abort()
        c.wait_complete()

        scale = round(widget.get_value(), 3)
        hal_pin = "hm2_7i92.0.stepgen." + AXIS_STEPGEN[internal_id] + ".position-scale"
        status_pin = "gladevcp." + internal_id + "_ENA-light"

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
                print(internal_id + " axis is enabled - disabling")
                ena_signal = CURRENT_LETTER.get(internal_id, internal_id.lower()) + "-ena-settings-allow"
                try:
                    subprocess.run(
                        ["halcmd", "sets", ena_signal, "FALSE"],
                        check=True,
                        capture_output=True,
                        text=True
                    )
                    print("Set " + ena_signal + " = FALSE")
                except subprocess.CalledProcessError as e:
                    print("Error setting " + ena_signal + ": " + e.stderr)
                except FileNotFoundError:
                    print("halcmd not found - is the LinuxCNC environment sourced?")
            else:
                print(internal_id + " axis is already disabled")
        except subprocess.CalledProcessError as e:
            print("Error checking " + status_pin + ": " + e.stderr)
        except FileNotFoundError:
            print("halcmd not found - is the LinuxCNC environment sourced?")

        cmd = ["halcmd", "setp", hal_pin, str(scale)]
        try:
            subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True
            )
            print("Set " + hal_pin + " = " + str(scale) + " (" + letter + ")")
        except subprocess.CalledProcessError as e:
            print("Error setting " + hal_pin + ": " + e.stderr)
        except FileNotFoundError:
            print("halcmd not found - is the LinuxCNC environment sourced?")

        max_vel_widget = self.builder.get_object(letter + "_Set_Max_Vel")
        if max_vel_widget is not None:
            _warn_if_max_vel_exceeds_ceiling(
                self, widget, letter, AXIS_STEPGEN[internal_id], scale, max_vel_widget)
    handler.__name__ = letter + "_Set_Scale"
    return handler

for _letter in AXIS_SELECTION_LETTERS:
    setattr(HandlerClass, _letter + "_Set_Scale", _axis_set_scale_letter(_letter))
del _letter

def _axis_set_backlash(axis):
    '''
    Value-changed handler for Sp0_Set_Backlash/Sp1_Set_Backlash only -
    the spindles are never reassignable (no letter concept applies), so
    their own JOINT_NUMBER entry is always correct with no letter
    resolution needed. The six reassignable channels are instead bound
    to _axis_set_backlash_letter below, uniformly for all 8 letters.

    Unlike _axis_set_scale_letter, there's no need to disable the axis
    first - a backlash change is safe to make on the fly, it doesn't
    invalidate an in-progress move the way a scale change can.
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

for _axis_id in ("Sp0", "Sp1"):
    setattr(HandlerClass, _axis_id + "_Set_Backlash", _axis_set_backlash(_axis_id))
del _axis_id

def _axis_set_backlash_letter(letter):
    '''
    Value-changed handler for one of the 8 letter-labeled Backlash spin
    buttons (<letter>_Set_Backlash, letter in AXIS_SELECTION_LETTERS).
    letter has no fixed joint number of its own, so the live
    joint.N.backlash pin is resolved through CURRENT_LETTER_INTERNAL_ID/
    JOINT_NUMBER at call time.
    '''
    def handler(self, widget):
        internal_id = CURRENT_LETTER_INTERNAL_ID.get(letter)
        if internal_id is None:
            print(letter + " is not currently assigned to a channel - value kept, no live HAL write")
            return

        hal_pin = "joint." + str(JOINT_NUMBER[internal_id]) + ".backlash"
        value = widget.get_value()
        try:
            subprocess.run(
                ["halcmd", "setp", hal_pin, str(value)],
                check=True,
                capture_output=True,
                text=True
            )
            print("Set " + hal_pin + " = " + str(value) + " (" + letter + ")")
        except subprocess.CalledProcessError as e:
            print("Error setting " + hal_pin + ": " + e.stderr)
        except FileNotFoundError:
            print("halcmd not found - is the LinuxCNC environment sourced?")
    handler.__name__ = letter + "_Set_Backlash"
    return handler

for _letter in AXIS_SELECTION_LETTERS:
    setattr(HandlerClass, _letter + "_Set_Backlash", _axis_set_backlash_letter(_letter))
del _letter

def _axis_set_max(axis, param):
    '''
    Value-changed handler for Sp0/Sp1's Max Vel/Max Accel spin buttons
    only - the spindles are never reassignable, so AXIS_STEPGEN[axis]
    is always correct with no letter resolution needed. The six
    reassignable channels are instead bound to _axis_set_max_letter
    below, uniformly for all 8 letters.

    Pushes the new value straight to the live
    hm2_7i92.0.stepgen.NN.maxvel/.maxaccel HAL param. param is "Vel" or
    "Accel". Like backlash (and unlike scale), no need to disable the
    axis first.
    '''
    hal_suffix = ".maxvel" if param == "Vel" else ".maxaccel"
    hal_pin = "hm2_7i92.0.stepgen." + AXIS_STEPGEN[axis] + hal_suffix
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

        if param == "Vel":
            scale_widget = self.builder.get_object(axis + "_Set_Scale")
            if scale_widget is not None:
                _warn_if_max_vel_exceeds_ceiling(
                    self, widget, axis, AXIS_STEPGEN[axis], scale_widget.get_value(), widget)
    handler.__name__ = axis + "_Set_Max_" + param
    return handler

for _axis in ("Sp0", "Sp1"):
    setattr(HandlerClass, _axis + "_Set_Max_Vel", _axis_set_max(_axis, "Vel"))
    setattr(HandlerClass, _axis + "_Set_Max_Accel", _axis_set_max(_axis, "Accel"))
del _axis

def _axis_set_max_letter(letter, param):
    '''
    Value-changed handler for one of the 8 letter-labeled Max Vel/Max
    Accel spin buttons (<letter>_Set_Max_Vel/_Accel, letter in
    AXIS_SELECTION_LETTERS). letter has no fixed channel of its own, so
    the live stepgen pin is resolved through CURRENT_LETTER_INTERNAL_ID/
    AXIS_STEPGEN at call time, same as _axis_set_scale_letter/
    _axis_set_backlash_letter.
    '''
    hal_suffix = ".maxvel" if param == "Vel" else ".maxaccel"
    def handler(self, widget):
        internal_id = CURRENT_LETTER_INTERNAL_ID.get(letter)
        if internal_id is None:
            print(letter + " is not currently assigned to a channel - value kept, no live HAL write")
            return

        hal_pin = "hm2_7i92.0.stepgen." + AXIS_STEPGEN[internal_id] + hal_suffix
        value = widget.get_value()
        try:
            subprocess.run(
                ["halcmd", "setp", hal_pin, str(value)],
                check=True,
                capture_output=True,
                text=True
            )
            print("Set " + hal_pin + " = " + str(value) + " (" + letter + ")")
        except subprocess.CalledProcessError as e:
            print("Error setting " + hal_pin + ": " + e.stderr)
        except FileNotFoundError:
            print("halcmd not found - is the LinuxCNC environment sourced?")

        if param == "Vel":
            scale_widget = self.builder.get_object(letter + "_Set_Scale")
            if scale_widget is not None:
                _warn_if_max_vel_exceeds_ceiling(
                    self, widget, letter, AXIS_STEPGEN[internal_id], scale_widget.get_value(), widget)
    handler.__name__ = letter + "_Set_Max_" + param
    return handler

for _letter in AXIS_SELECTION_LETTERS:
    setattr(HandlerClass, _letter + "_Set_Max_Vel", _axis_set_max_letter(_letter, "Vel"))
    setattr(HandlerClass, _letter + "_Set_Max_Accel", _axis_set_max_letter(_letter, "Accel"))
del _letter

def _channel_axis_changed(channel_id):
    '''
    Generic "changed" handler for one Axis Selection letter combo.
    Records the new choice and refreshes every combo
    (_rebuild_all_channel_combo_items) - every letter is always
    selectable, duplicates are no longer prevented at the dropdown.
    Instead, _update_duplicate_warnings flags every channel currently
    sharing a letter; as long as any duplicate remains, this handler
    deliberately does NOT persist the assignment or show the restart
    notice - both only happen once the whole assignment is duplicate-
    free, at which point they fire on that clearing change.
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
    pin. Unlike _axis_set_scale_letter, there's no need to disable the
    axis first - a PID gain is safe to retune on the fly, it doesn't
    invalidate an in-progress move the way a scale change can. Used
    only for Sp0/Sp1's fixed pid components (pid.p0/pid.s0/pid.p1/
    pid.s1) - the six reassignable channels are instead bound via
    _pid_set_letter below.
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

def _pid_set_letter(letter, param):
    '''
    Value-changed handler for one of the 8 letter-labeled PID spin
    buttons (<letter>_Set_<param>, letter in AXIS_SELECTION_LETTERS).
    The live pid.* component here is named after the LETTER ITSELF
    (REB_Generate_Local_Ini.py renames each channel's pid component to
    match its current assignment), so no channel indirection is needed
    to build the pin name, only a check that some channel is actually
    using this letter right now (CURRENT_LETTER_INTERNAL_ID), since the
    component doesn't exist at all otherwise - same gating
    _axis_set_scale_letter/_axis_set_backlash_letter use.
    '''
    hal_pin = "pid." + letter.lower() + "." + PID_PARAM_PIN[param]
    def handler(self, widget):
        if letter not in CURRENT_LETTER_INTERNAL_ID:
            print(letter + " is not currently assigned to a channel - value kept, no live HAL write")
            return
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
    handler.__name__ = letter + "_Set_" + param
    return handler

for _letter in AXIS_SELECTION_LETTERS:
    for _param in PID_PARAMS:
        setattr(HandlerClass, _letter + "_Set_" + _param, _pid_set_letter(_letter, _param))
del _letter, _param

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
    buttons: persists to REBset_v1.ini and warns that a restart is
    needed, same as Max_Jog_Speed_Changed - these are read once by
    LinuxCNC at process startup, not live HAL pins, so there's no
    halcmd setp to also do here.
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


def main():
    if _linuxcnc_is_running():
        dialog = Gtk.MessageDialog(
            transient_for=None,
            flags=0,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text="LinuxCNC is currently running",
        )
        dialog.format_secondary_text(
            "REB Settings must be run before starting LinuxCNC, not while "
            "it's running. Please exit LinuxCNC first, then run REB "
            "Settings again."
        )
        dialog.run()
        dialog.destroy()
        return

    builder = Gtk.Builder()
    builder.add_from_file(UI_FILE)
    handler = HandlerClass(builder)
    builder.connect_signals(handler)
    window = builder.get_object("window1")
    window.connect("destroy", Gtk.main_quit)
    window.set_title("REB Settings")
    # window1/scrolledwindow1 no longer propagate their content's
    # natural size upward (see scrolledwindow1's propagate-natural-
    # width/height in REB_Settings_v1.ui - needed so content actually
    # fills a maximized window instead of clamping to a cramped natural
    # size, the old embedded-tab-era behavior). The tradeoff: nothing
    # now gives this window a sensible size on its own at startup - it
    # opens tiny (confirmed live 4 September 2026) unless explicitly
    # told to maximize, so do that here rather than relying on content
    # size to imply a window size.
    window.maximize()
    window.show_all()
    Gtk.main()

if __name__ == "__main__":
    main()
