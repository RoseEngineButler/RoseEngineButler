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
import datetime
import json
import os
import linuxcnc
import webbrowser
import subprocess
import re
import xml.etree.ElementTree as ET
from gi.repository import Gdk
from xml.sax.saxutils import escape, unescape
from gi.repository import Gtk
from gi.repository import GLib

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

# Axis id -> HAL `pid` component instance driving that axis's PID loop
# (see the `loadrt pid names=...` line and each axis's `setp pid.<x>.*`
# block in REB.hal). Sp0/Sp1 each have two loops instead of one - a
# position/orient loop (pid.p0/pid.p1) and a velocity loop
# (pid.s0/pid.s1) - handled separately by PID_SPINDLE_LOOPS below.
PID_AXES = {
    "X": "pid.x",
    "Z": "pid.z",
    "B": "pid.b",
    "U": "pid.u",
    "V": "pid.v",
    "W": "pid.w",
}

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

SETTINGS_PATH = "/home/reuben/linuxcnc/configs/RoseEngineButlerLocal/REB_Settings_v1.ini"

# REB.ini lives in this repo (one directory up from REB_Display/), not in
# RoseEngineButlerLocal - computed from this file's own location rather than
# hardcoded like SETTINGS_PATH above, since this repo (unlike the Local
# sibling) is expected to be relocatable/clonable.
REB_INI_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "REB.ini"
)

# User-facing, explicitly named/located settings snapshots (see
# docs/settings_file.md) - separate from and in addition to the automatic,
# fixed-path REB_Settings_v1.ini above. format_version is written into
# every settings file and checked on load; bump it and add a
# _migrate_v<N>_to_v<N+1>-style function if the schema below ever changes.
#
# Extension is ".settings.ini", not the original ".rebset": a made-up
# extension like ".rebset" means nothing to an operator browsing their
# Documents folder (Rich's feedback, 30 July 2026) - ".ini" reads as an
# ordinary settings file at a glance. Not bare ".ini" though: that would
# collide with both REB_Settings_v1.ini and the separate .export.ini
# format below, making the three indistinguishable under a naive *.ini
# filter (e.g. Load Settings could show export files mixed in with full
# profiles). ".settings.ini" stays recognizable while keeping each
# format's own file-chooser filter (and a human skimming a folder)
# able to tell all three apart.
REBSET_FORMAT_VERSION = 1
REBSET_EXTENSION = ".settings.ini"
REBSET_DEFAULT_DIR = os.path.expanduser("~/Documents")

def _name_from_settings_path(path):
    '''
    Derives a display/JSON "name" from a .settings.ini file's own
    filename. NOT os.path.splitext(basename)[0] - that only strips the
    single final suffix (".ini"), leaving ".settings" stuck to the name
    for this extension specifically, since it has two dots (confirmed
    live: reloading "Chucks_LRE.settings.ini" produced the name
    "Chucks_LRE.settings", which then got baked into a
    "Chucks_LRE_settings.settings.ini" on the next Save As). Strips the
    whole known REBSET_EXTENSION suffix instead; falls back to a plain
    splitext for anything else (e.g. an old .rebset file from before the
    rename) so those still work too.
    '''
    basename = os.path.basename(path)
    if basename.endswith(REBSET_EXTENSION):
        return basename[:-len(REBSET_EXTENSION)]
    return os.path.splitext(basename)[0]

# Default name offered when there's real REB_Settings_v1.ini data but no
# .settings.ini has ever been saved yet (see _legacy_settings_available).
# Was literally "legacy" - meaningless to an operator browsing their
# Documents folder once saved as a filename (Rich's feedback, 30 July
# 2026) - so this is what they'd actually recognize as theirs.
DEFAULT_LEGACY_SETTINGS_NAME = "RoseEngineButler_Settings"

# Shipped starter profile, read from this repo (not RoseEngineButlerLocal
# or a user's ~/Documents) - see _prompt_initial_settings_load. Its scale
# values are deliberately 1 (no meaningful motion per commanded unit, on
# any machine's real step/unit calibration) rather than a plausible-looking
# number: an uncalibrated axis should fail toward "barely moves", never
# toward "moves far more than commanded".
REBSET_GENERIC_EXAMPLE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "generic_example" + REBSET_EXTENSION
)

# Per-machine record of the last .settings.ini actually opened/saved by the
# operator (not the generic_example fallback - see
# _prompt_initial_settings_load), so the next session can reload it
# automatically instead of prompting. Lives in RoseEngineButlerLocal
# alongside REB_Settings_v1.ini, same reasoning as that file: this is
# per-machine state, not something to track in the shared repo.
LAST_SETTINGS_PATH_FILE = "/home/reuben/linuxcnc/configs/RoseEngineButlerLocal/REB_Last_Settings_Path.txt"

# A full, ready-to-save .settings.ini payload, kept continuously up to date by
# _mark_settings_dirty (and the two _prompt_initial_settings_load
# fallbacks) for as long as there are unsaved changes; removed again once
# they're saved or discarded. This is what lets the exit prompt work at
# all: a GTK delete-event/destroy hook on this component's own window
# does NOT fire on real AXIS exit (confirmed live - AXIS tears embedded
# tabs down by yanking their X window out from under them, not a normal
# close negotiation), so the actual prompt has to run from a different,
# proven-reliable point in the shutdown sequence: REB_Scale_Persist.py,
# run via `loadusr -w` from REB_Shutdown.hal, which already blocks
# shutdown until it finishes. That script is a separate process with no
# access to this component's live widgets, hence staging the full
# payload here rather than just a boolean flag.
PENDING_SETTINGS_PATH = "/home/reuben/linuxcnc/configs/RoseEngineButlerLocal/REB_Pending_Settings.settings.ini"

# Axes (not spindles) that have a free-text comment field on the main
# panel, persisted to REB_Settings_v1.ini as each <axis>'s <usercomment>.
COMMENT_AXES = ("X", "Z", "U", "V", "W", "B")

# Export_Settings/Import_Settings (see docs/settings_file.md): a
# deliberately different, smaller mechanism from .settings.ini - a hand-picked
# subset of just what's literally on the Settings tab itself (each axis's
# Scale, plus Measurement System), not the full axis/comment/notes
# snapshot a .settings.ini carries. Plain XML (matching REB_Settings_v1.ini's
# own shape), not JSON, and no format_version - this is meant for quick,
# ad hoc sharing of a few values (e.g. "just my B-axis calibration"), not
# a versioned profile format.
EXPORT_EXTENSION = ".export.ini"

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
    # <axis>-ena-settings-allow convention in REB_PostGUI_v1.hal.
    hal_signal = axis_id.lower() + "-ena-settings-allow"
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
        flip_set_pin = axis_id.lower() + "-ena-flip.set"
        try:
            subprocess.run(["halcmd", "setp", flip_set_pin, "TRUE"], check=True, capture_output=True, text=True)
            subprocess.run(["halcmd", "setp", flip_set_pin, "FALSE"], check=True, capture_output=True, text=True)
            idx_log("Forced " + axis_id.lower() + "-ena-panel ON (override had been blocking)")
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

def _show_restart_required_popup(widget):
    dialog = Gtk.MessageDialog(
        transient_for=widget.get_toplevel(),
        flags=0,
        message_type=Gtk.MessageType.INFO,
        buttons=Gtk.ButtonsType.OK,
        text="Restart required",
    )
    dialog.format_secondary_text(
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

def _apply_measurement_system_to_ini(system):
    '''
    Patches REB.ini's [TRAJ] LINEAR_UNITS and each linear [JOINT_n]'s UNITS
    to match the chosen Measurement System. Only takes effect on the next
    LinuxCNC start (REB.ini is read once at launch) - see
    _show_restart_required_popup, shown right after this runs.

    Matches the file's existing casing convention: LINEAR_UNITS lowercase
    ("inch"/"mm"), per-joint UNITS uppercase ("INCH"/"MM") - both accepted
    case-insensitively by LinuxCNC, kept this way only for consistency with
    what was already there. JOINT_2 (B, angular) uses UNITS = DEGREE and is
    never matched by the INCH/MM pattern below, so it's left untouched.
    '''
    try:
        with open(REB_INI_PATH, "r") as f:
            text = f.read()
    except OSError as e:
        print("Could not read " + REB_INI_PATH + ": " + str(e))
        return

    if system == "Metric":
        linear_units, joint_units = "mm", "MM"
    else:
        linear_units, joint_units = "inch", "INCH"

    new_text, n1 = re.subn(
        r'(?m)^(LINEAR_UNITS\s*= )\S+',
        lambda m: m.group(1) + linear_units,
        text,
        count=1
    )
    if n1 == 0:
        print("LINEAR_UNITS line not found in " + REB_INI_PATH)

    new_text, n2 = re.subn(
        r'(?m)^(UNITS\s*= )(INCH|MM)$',
        lambda m: m.group(1) + joint_units,
        new_text
    )

    try:
        with open(REB_INI_PATH, "w") as f:
            f.write(new_text)
        print("Updated " + str(n1) + " LINEAR_UNITS line(s) and " + str(n2)
              + " UNITS line(s) in " + REB_INI_PATH)
    except OSError as e:
        print("Could not write " + REB_INI_PATH + ": " + str(e))

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

        _set_depressed(fwd, bool(hal.get_value('spindle.0.forward')))
        _set_depressed(rev, bool(hal.get_value('spindle.0.reverse')))
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

    def _load_axis_comments(self):
        '''
        Reads each axis's persisted user comment from REB_Settings_v1.ini
        and applies it to that axis's comment field on the main panel.

        Only runs in the component that actually owns these Entry
        widgets (X_Comment etc., on the main REB_Panel) - every other
        tab/panel also using REB_main.py will find that widget
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

        for axis_id in COMMENT_AXES:
            widget = self.builder.get_object(axis_id + "_Comment")
            if widget is None:
                continue

            match = re.search(
                r'<axis\s+id="' + re.escape(axis_id) + r'">\s*<scale>-?[\d.]+</scale>\s*'
                r'<usercomment>(.*?)</usercomment>',
                xml_text,
                re.DOTALL
            )
            if not match:
                print("No stored comment found for axis " + axis_id
                      + " in " + SETTINGS_PATH)
                continue

            widget.set_text(unescape(match.group(1)))

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

    def _save_axis_comment(self, axis_id, text):
        '''
        Writes a single axis's comment back into REB_Settings_v1.ini,
        updating only that axis's <usercomment> value. Called from
        each comment Entry's focus-out-event handler below.
        '''
        try:
            with open(SETTINGS_PATH, "r") as f:
                xml_text = f.read()
        except OSError as e:
            print("Could not read " + SETTINGS_PATH + ": " + str(e))
            return

        pattern = (
            r'(<axis\s+id="' + re.escape(axis_id) + r'">\s*<scale>-?[\d.]+</scale>\s*<usercomment>)'
            r'.*?'
            r'(</usercomment>)'
        )
        new_text, count = re.subn(
            pattern,
            lambda m: m.group(1) + escape(text) + m.group(2),
            xml_text,
            count=1,
            flags=re.DOTALL
        )
        if count == 0:
            print("No <usercomment> entry found for axis " + axis_id
                  + " in " + SETTINGS_PATH + " - leaving it unchanged")
            return

        try:
            with open(SETTINGS_PATH, "w") as f:
                f.write(new_text)
            print("Saved " + axis_id + " comment")
        except OSError as e:
            print("Could not write " + SETTINGS_PATH + ": " + str(e))
            return

        self._mark_settings_dirty()

    def _read_axis_comment(self, axis_id):
        '''
        Reads a single axis's current comment straight out of
        REB_Settings_v1.ini. Used by Settings_Save to gather a snapshot
        for a .settings.ini file - the Settings tab component doesn't own the
        Comment Entry widgets (those live on the main panel, a separate
        gladevcp process/widget tree - see docs/settings_file.md), so the
        shared settings file, which the main panel keeps current via
        _save_axis_comment on every focus-out, is the only common ground.
        '''
        try:
            with open(SETTINGS_PATH, "r") as f:
                xml_text = f.read()
        except OSError as e:
            print("Could not read " + SETTINGS_PATH + ": " + str(e))
            return ""

        match = re.search(
            r'<axis\s+id="' + re.escape(axis_id) + r'">\s*<scale>-?[\d.]+</scale>\s*'
            r'<usercomment>(.*?)</usercomment>',
            xml_text,
            re.DOTALL
        )
        return unescape(match.group(1)) if match else ""

    def _mark_settings_dirty(self):
        '''
        Flags that something covered by a .settings.ini snapshot (axis scales,
        comments, or notes) has changed since the last Settings_Save/
        Settings_Load, and stages a full snapshot on disk for the
        shutdown-time exit prompt to offer (see PENDING_SETTINGS_PATH).
        Suppressed while Settings_Load is itself the one poking widgets
        (self._applying_settings) - otherwise re-applying a loaded scale
        value would immediately re-dirty the settings it just loaded.
        '''
        if not self._applying_settings:
            self._settings_dirty = True
            self._write_pending_snapshot()
            self._refresh_settings_name_label()

    def _write_pending_snapshot(self):
        '''
        Writes the full current settings (scale/comment/notes/name) to
        PENDING_SETTINGS_PATH, in the same shape as a saved .settings.ini, so
        the shutdown-time prompt (a separate process - see
        PENDING_SETTINGS_PATH) has something concrete to offer saving.
        Called by _mark_settings_dirty and by _prompt_initial_settings_load's
        legacy/generic_example fallbacks, which force-dirty outside that
        normal path.
        '''
        notes_view = self.builder.get_object("Settings_Notes")
        notes = ""
        if notes_view is not None:
            buf = notes_view.get_buffer()
            notes = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)

        data = self._gather_current_settings(self._settings_name or "", notes)
        try:
            with open(PENDING_SETTINGS_PATH, "w") as f:
                json.dump(data, f, indent=2)
        except OSError as e:
            print("Could not stage pending settings snapshot: " + str(e))

    def _clear_pending_settings_snapshot(self):
        try:
            os.remove(PENDING_SETTINGS_PATH)
        except FileNotFoundError:
            pass
        except OSError as e:
            print("Could not clear pending settings snapshot: " + str(e))

    def _set_settings_name_display(self, name):
        self._settings_name = name
        self._refresh_settings_name_label()

    def _refresh_settings_name_label(self):
        '''
        Renders the Settings Name label from self._settings_name plus a
        trailing " *" whenever self._settings_dirty is True - the same
        "unsaved changes" convention as a text editor's title bar. This
        is what lets the operator notice and save proactively, while the
        GUI is still fully up and interactive, instead of relying on the
        shutdown-time prompt (which can't appear until well after the
        screen has already visually torn down - see
        docs/settings_file.md, Decision 4).
        '''
        label = self.builder.get_object("Settings_Name")
        if label is None:
            return
        text = "Settings: " + self._settings_name if self._settings_name else "Settings: (unsaved)"
        if self._settings_dirty:
            text += " *"
        label.set_text(text)

    def _set_settings_source_path_display(self, path):
        '''
        Shows the full path of wherever the current settings actually
        came from, on its own line above the toolbar (Rich's feedback,
        30 July 2026: the abbreviated Settings Name label alone lost
        track of the actual file). Broader than self._settings_path
        (which is specifically "where plain Save writes to", and is
        deliberately left None for the legacy/generic_example fallbacks
        so a plain Save can't silently overwrite REB_Settings_v1.ini or
        the shipped repo template) - this is set for those fallbacks too,
        via their own direct calls, since seeing the real source path is
        useful even when nothing's been saved as a named file yet.
        '''
        self._settings_source_path = path
        label = self.builder.get_object("Settings_File_Path")
        if label is not None:
            label.set_text("Settings File: " + path if path else "Settings File: (unsaved)")

    def _read_last_settings_path(self):
        try:
            with open(LAST_SETTINGS_PATH_FILE, "r") as f:
                path = f.read().strip()
            return path or None
        except OSError:
            return None

    def _write_last_settings_path(self, path):
        '''
        Records path as the file to silently reload next session
        (_prompt_initial_settings_load), and as this session's own
        "current file" (self._settings_path), so plain Settings_Save can
        re-save straight to it with no dialog (Settings_Save_As always
        prompts). Only called for a file the operator actually chose via
        Save/Save As or Load - never for the generic_example fallback,
        which must keep prompting (and must never be silently
        overwritten by a plain Save) until the operator saves a real
        copy of their own.
        '''
        self._settings_path = path
        self._set_settings_source_path_display(path)
        try:
            os.makedirs(os.path.dirname(LAST_SETTINGS_PATH_FILE), exist_ok=True)
            with open(LAST_SETTINGS_PATH_FILE, "w") as f:
                f.write(path)
        except OSError as e:
            print("Could not record last-used settings path: " + str(e))

    def _legacy_settings_available(self):
        '''
        True if REB_Settings_v1.ini has at least one real <axis>/<scale>
        entry - i.e. there's a pre-existing, pre-.settings.ini machine setup
        worth treating as the starting point instead of an empty
        ~/Documents picker or the generic_example placeholder. Its values
        are already live by the time this is checked: _load_scale_settings/
        _load_axis_comments already applied them earlier in __init__,
        unconditionally, regardless of anything to do with .settings.ini files -
        this only decides how _prompt_initial_settings_load should react
        to that, not whether to (re-)apply them.
        '''
        try:
            with open(SETTINGS_PATH, "r") as f:
                xml_text = f.read()
        except OSError:
            return False
        return re.search(r'<axis\s+id="[^"]+">\s*<scale>-?[\d.]+</scale>', xml_text) is not None

    def _disable_axis(self, axis_id):
        '''
        Forces one axis disabled from this component, the same way
        _axis_set_scale/Sp0_Set_Scale/Sp1_Set_Scale already force their
        own axis disabled when its scale changes - only touches it if
        it's actually enabled right now (cross-component read of
        <axis>_ENA-light, which belongs to the main panel's "gladevcp"
        component), then clears this component's own <axis>_Ena_Override
        pin (ANDed with the panel's ENA button in REB_PostGUI_v1.hal).
        Used by Settings_Load to force every axis off before a loaded
        scale value can take effect under it (docs/settings_file.md,
        Decision 3).
        '''
        status_pin = "gladevcp." + axis_id + "_ENA-light"
        try:
            result = subprocess.run(
                ["halcmd", "getp", status_pin],
                check=True,
                capture_output=True,
                text=True
            )
            is_enabled = result.stdout.strip().upper() in ("TRUE", "1")
        except subprocess.CalledProcessError as e:
            print("Error checking " + status_pin + ": " + str(e.stderr))
            return
        except FileNotFoundError:
            print("halcmd not found - is the LinuxCNC environment sourced?")
            return

        if is_enabled:
            print(axis_id + " axis is enabled - disabling for settings load")
            self.halcomp[axis_id + '_Ena_Override'] = False

    def _gather_current_settings(self, name, notes):
        axes = {}
        for axis_id in AXIS_STEPGEN:
            widget = self.builder.get_object(axis_id + "_Set_Scale")
            entry = {"scale": widget.get_value() if widget is not None else None}
            if axis_id in COMMENT_AXES:
                entry["comment"] = self._read_axis_comment(axis_id)
            axes[axis_id] = entry

        return {
            "format_version": REBSET_FORMAT_VERSION,
            "name": name,
            "notes": notes,
            "saved_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "axes": axes,
        }

    def Settings_Notes_Changed(self, buffer):
        # Wired to the Notes GtkTextView's GtkTextBuffer "changed" signal.
        # Also fires when Settings_Load sets the buffer's text
        # programmatically - _mark_settings_dirty's own
        # self._applying_settings check is what keeps that from re-dirtying
        # the settings that were just loaded.
        self._mark_settings_dirty()

#######################################################################
# Measurement_System_Changed
# Purpose:              User picked Metric or Imperial in the Settings
#                           tab's "Other" section. Updates this
#                           component's own unit-of-measure labels for
#                           immediate feedback, persists the choice to
#                           REB_Settings_v1.ini, patches REB.ini's
#                           LINEAR_UNITS/UNITS, and warns that a restart
#                           is needed for the new units to actually take
#                           effect (REB.ini is only read at LinuxCNC
#                           startup).
# Updated:              ver 1.0, 30 July 2026, Claude
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
        _apply_measurement_system_to_ini(system)
        _show_restart_required_popup(widget)

#######################################################################
# Settings_Save
# Purpose:              Saves the current Settings tab (axis scales +
#                           comments) plus the Notes field back to
#                           whichever .settings.ini file is currently active,
#                           with no dialog. Falls back to Settings_Save_As
#                           if nothing is active yet (e.g. still on the
#                           legacy/generic_example starting point - see
#                           docs/settings_file.md, Decision 5/6).
# Updated:              ver 1.0, 29 July 2026, Claude
# ---------------------------------------------------------------------
# Called from:
#   UI:                 REB_Tab_Settings_v1
#   Button:              Settings_Save  (GtkButton)
#   Signal:              GtkButton/clicked
#######################################################################
    def Settings_Save(self, widget):
        if self.builder.get_object("X_Set_Scale") is None:
            return

        if not self._settings_path:
            self.Settings_Save_As(widget)
            return

        print("=================================================")
        print("FUNCTION Settings_Save")
        self._save_to_path(widget, self._settings_path)

#######################################################################
# Settings_Save_As
# Purpose:              Always shows the file chooser, so the operator
#                           can pick a new location/filename (or
#                           overwrite an existing one) rather than
#                           re-saving over whatever's currently active.
#                           The chosen filename IS the name - shown as
#                           the Settings Name and stored in the file's
#                           own "name" field - there's no separate typed
#                           name to keep in sync (see docs/settings_file.md,
#                           Decision 2, revised).
# Updated:              ver 1.0, 29 July 2026, Claude
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

        file_filter = Gtk.FileFilter()
        file_filter.set_name("Rose Engine Butler Settings (*" + REBSET_EXTENSION + ")")
        file_filter.add_pattern("*" + REBSET_EXTENSION)
        dialog.add_filter(file_filter)

        # Suggest the current name as a starting filename, but the
        # operator can freely change it - whatever they end up with is
        # the new name, going forward.
        if self._settings_name:
            safe_name = re.sub(r'[^A-Za-z0-9 _-]', '_', self._settings_name)
            dialog.set_current_name(safe_name + REBSET_EXTENSION)

        response = dialog.run()
        path = dialog.get_filename() if response == Gtk.ResponseType.OK else None
        dialog.destroy()

        if not path:
            print("Settings_Save_As cancelled")
            return

        if not path.endswith(REBSET_EXTENSION):
            path += REBSET_EXTENSION

        self._save_to_path(widget, path)

    def _save_to_path(self, widget, path):
        '''
        Shared by Settings_Save (re-saving the active file with no
        dialog) and Settings_Save_As (always via the file chooser
        above). The name is always derived from path's filename - see
        Settings_Save_As's banner comment for why that replaced a
        separately-typed name field.
        '''
        name = _name_from_settings_path(path)

        notes_view = self.builder.get_object("Settings_Notes")
        notes_buffer = notes_view.get_buffer() if notes_view is not None else None
        notes = ""
        if notes_buffer is not None:
            notes = notes_buffer.get_text(
                notes_buffer.get_start_iter(), notes_buffer.get_end_iter(), False
            )

        data = self._gather_current_settings(name, notes)

        try:
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
        except OSError as e:
            _show_settings_error(widget, "Could not write " + path + ":\n" + str(e))
            return

        print("Saved settings '" + name + "' to " + path)
        self._set_settings_name_display(name)
        self._settings_dirty = False
        self._write_last_settings_path(path)  # also sets self._settings_path
        self._clear_pending_settings_snapshot()
        self._refresh_settings_name_label()

#######################################################################
# Settings_Load
# Purpose:              Loads a previously saved .settings.ini JSON file,
#                           applying its axis scales/comments/notes.
#                           Stops all motion and disables every axis
#                           first (docs/settings_file.md, Decision 3).
# Updated:              ver 1.0, 29 July 2026, Claude
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
            "_Open", Gtk.ResponseType.OK,
        )
        dialog.set_current_folder(REBSET_DEFAULT_DIR)

        file_filter = Gtk.FileFilter()
        file_filter.set_name("Rose Engine Butler Settings (*" + REBSET_EXTENSION + ")")
        file_filter.add_pattern("*" + REBSET_EXTENSION)
        dialog.add_filter(file_filter)

        response = dialog.run()
        path = dialog.get_filename() if response == Gtk.ResponseType.OK else None
        dialog.destroy()

        if not path:
            print("Settings_Load cancelled")
            return

        if self._load_settings_file(widget, path):
            self._write_last_settings_path(path)

    def _load_settings_file(self, widget, path):
        '''
        Parses and applies a single .settings.ini file: validates it, stops
        motion and disables every axis (Decision 3), then applies its
        scale/comment/notes/name. Shared by the Settings_Load button and
        _prompt_initial_settings_load (the startup prompt) so both go
        through identical validation. Returns True on success, False if
        the file was rejected (an error dialog has already been shown in
        that case) - callers that need to react to failure check this.
        '''
        try:
            with open(path, "r") as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            _show_settings_error(widget, "Could not read " + path + ":\n" + str(e))
            return False

        version = data.get("format_version")
        if version != REBSET_FORMAT_VERSION:
            _show_settings_error(
                widget,
                "Unsupported settings file version (" + str(version) + ") in\n" + path +
                "\nExpected version " + str(REBSET_FORMAT_VERSION) + "."
            )
            return False

        axes = data.get("axes")
        if not isinstance(axes, dict):
            _show_settings_error(widget, path + " is missing its axes data.")
            return False

        # Stop any in-progress motion and disable every axis before a
        # loaded scale value can take effect under it.
        c.abort()
        c.wait_complete()
        for axis_id in AXIS_STEPGEN:
            self._disable_axis(axis_id)

        self._applying_settings = True
        try:
            for axis_id, stepgen_ch in AXIS_STEPGEN.items():
                entry = axes.get(axis_id)
                if not isinstance(entry, dict) or "scale" not in entry:
                    print("No stored scale for axis " + axis_id + " in " + path)
                    continue

                scale = entry["scale"]

                spin = self.builder.get_object(axis_id + "_Set_Scale")
                if spin is not None:
                    spin.set_value(scale)

                hal_pin = "hm2_7i92.0.stepgen." + stepgen_ch + ".position-scale"
                try:
                    subprocess.run(
                        ["halcmd", "setp", hal_pin, str(scale)],
                        check=True,
                        capture_output=True,
                        text=True
                    )
                    print("Loaded " + hal_pin + " = " + str(scale))
                except subprocess.CalledProcessError as e:
                    print("Error setting " + hal_pin + ": " + str(e.stderr))
                except FileNotFoundError:
                    print("halcmd not found - is the LinuxCNC environment sourced?")

                if axis_id in COMMENT_AXES and "comment" in entry:
                    # Only patches REB_Settings_v1.ini - the main panel's
                    # own Comment entries are a different component's
                    # widgets (see _read_axis_comment) and will pick this
                    # up next time that component starts, the same way
                    # _load_axis_comments only runs once at startup today.
                    self._save_axis_comment(axis_id, entry["comment"])

            notes_view = self.builder.get_object("Settings_Notes")
            if notes_view is not None:
                notes_view.get_buffer().set_text(data.get("notes", "") or "")
        finally:
            self._applying_settings = False

        # The name always tracks the file's own current filename, not
        # whatever "name" happens to be baked into its JSON content - so
        # renaming a .settings.ini outside the app (or hand-editing the file)
        # can't leave a stale name on screen after reloading it.
        name = _name_from_settings_path(path)
        print("Loaded settings '" + name + "' from " + path)
        self._set_settings_name_display(name)
        self._set_settings_source_path_display(path)
        self._settings_dirty = False
        self._clear_pending_settings_snapshot()
        self._refresh_settings_name_label()
        return True

    def _prompt_initial_settings_load(self):
        '''
        Runs once, shortly after the Settings tab is up (see the
        idle_add call in __init__). Reloads the last .settings.ini the operator
        actually opened/saved (LAST_SETTINGS_PATH_FILE, in
        RoseEngineButlerLocal - per-machine state, not tracked in this
        repo) with no prompt at all, if one is on record and still
        readable.

        Failing that - no record, first-ever run with this feature - a
        machine that's been in use since before .settings.ini files existed
        still has real, good values sitting in REB_Settings_v1.ini,
        already restored into HAL/the spin buttons unconditionally
        earlier in __init__ (_load_scale_settings/_load_axis_comments)
        regardless of anything here. Recognize that instead of
        overwriting it with an empty ~/Documents picker: leave those
        values alone, but flag them dirty so the exit prompt offers to
        save them as a real, named .settings.ini - migrating them into this
        feature rather than leaving them stuck as the single anonymous
        legacy file forever.

        Only when there's neither a usable .settings.ini on record nor any
        legacy REB_Settings_v1.ini data does this fall back to showing a
        picker: pick a saved profile from ~/Documents, or fall back
        further to the generic_example profile shipped in this repo
        (REB_Display/, not RoseEngineButlerLocal) if they Cancel that too.
        Both the legacy and generic_example fallbacks are force-marked
        dirty (and stage a pending snapshot - see PENDING_SETTINGS_PATH)
        so the shutdown-time exit prompt (REB_Scale_Persist.py) offers to
        save a real copy into ~/Documents - never overwriting the shipped
        repo copy of generic_example, since Settings_Save always defaults to
        REBSET_DEFAULT_DIR. Picking a real file here, unlike either
        fallback, also updates LAST_SETTINGS_PATH_FILE, same as the Load
        button does.
        '''
        if self.builder.get_object("X_Set_Scale") is None:
            return False  # idle_add: run once regardless

        widget = self.builder.get_object("X_Set_Scale")

        last_path = self._read_last_settings_path()
        if last_path and os.path.isfile(last_path):
            if self._load_settings_file(widget, last_path):
                print("Reloaded last-used settings from " + last_path)
                return False
            print("Could not reload last-used settings (" + last_path
                  + ") - falling back to the startup picker")

        if self._legacy_settings_available():
            print("No " + REBSET_EXTENSION + " file on record - keeping the "
                  "existing " + SETTINGS_PATH + " values as the starting point")
            self._set_settings_name_display(DEFAULT_LEGACY_SETTINGS_NAME)
            self._set_settings_source_path_display(SETTINGS_PATH)
            self._settings_dirty = True
            self._write_pending_snapshot()
            self._refresh_settings_name_label()
            return False

        os.makedirs(REBSET_DEFAULT_DIR, exist_ok=True)

        dialog = Gtk.FileChooserDialog(
            title="Load Settings",
            transient_for=widget.get_toplevel(),
            action=Gtk.FileChooserAction.OPEN,
        )
        dialog.add_buttons(
            "_Cancel", Gtk.ResponseType.CANCEL,
            "_Open", Gtk.ResponseType.OK,
        )
        dialog.set_current_folder(REBSET_DEFAULT_DIR)

        file_filter = Gtk.FileFilter()
        file_filter.set_name("Rose Engine Butler Settings (*" + REBSET_EXTENSION + ")")
        file_filter.add_pattern("*" + REBSET_EXTENSION)
        dialog.add_filter(file_filter)

        instructions = Gtk.Label(
            label="No previously used settings file found. Select a saved"
                  " Rose Engine Butler settings file (" + REBSET_EXTENSION +
                  ") to load.\nCancel to start from the generic_example"
                  " starter profile instead."
        )
        instructions.set_line_wrap(True)
        instructions.set_max_width_chars(60)
        instructions.set_xalign(0)
        instructions.show()
        dialog.set_extra_widget(instructions)

        response = dialog.run()
        path = dialog.get_filename() if response == Gtk.ResponseType.OK else None
        dialog.destroy()

        if path:
            if self._load_settings_file(widget, path):
                self._write_last_settings_path(path)
        else:
            print("No settings file selected at startup - falling back to "
                  + REBSET_GENERIC_EXAMPLE_PATH)
            if self._load_settings_file(widget, REBSET_GENERIC_EXAMPLE_PATH):
                # Unlike a normal load, this isn't a file the operator
                # actually has saved anywhere themselves yet - force it
                # dirty so they're offered a chance to save their own
                # copy (to ~/Documents) once they exit or make changes.
                # _load_settings_file just cleared the pending snapshot
                # on its way to a clean return - re-stage it now that
                # dirty is being forced back on. It also already set the
                # name/path displays to REBSET_GENERIC_EXAMPLE_PATH.
                self._settings_dirty = True
                self._write_pending_snapshot()
                self._refresh_settings_name_label()

        return False  # idle_add: run once

#######################################################################
# Export_Settings
# Purpose:              Lets the operator pick a subset of what's on the
#                           Settings tab (each axis's Scale, and/or
#                           Measurement System) and export just that
#                           subset to a small .export.ini file - for
#                           quick, ad hoc sharing (e.g. "just my B-axis
#                           calibration"), distinct from a full .settings.ini
#                           snapshot. See docs/settings_file.md.
# Updated:              ver 1.0, 30 July 2026, Claude
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
        dialog.set_current_name(
            (self._settings_name or "settings") + EXPORT_EXTENSION
        )

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

        exported = []
        for axis_id in selected.get("axes", ()):
            spin = self.builder.get_object(axis_id + "_Set_Scale")
            if spin is None:
                continue
            ET.SubElement(get_axis_el(axis_id), "scale").text = str(spin.get_value())
            exported.append(axis_id + " Scale")

        for axis_id in selected.get("pid_axes", ()):
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
        Modal checklist: one row per axis's Scale, one row per axis's/
        spindle loop's PID gains (P/I/D/FF0/FF1/FF2 as a single unit -
        Sp0/Sp1 each cover both their position and velocity loops
        together, matching the coarse per-axis granularity already used
        for Scale rather than exposing every individual gain), plus
        Measurement System - all pre-checked, with Select All/None
        convenience buttons. Returns {"axes": [...ids...], "pid_axes":
        [...ids...], "measurement_system": bool} on Export, or None if
        cancelled/nothing was selected.
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

        # Two columns side by side (Scale, PID) so ~19 checkboxes stay a
        # manageable dialog height instead of one long list.
        columns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        content.pack_start(columns, False, False, 0)

        scale_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        pid_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        columns.pack_start(scale_col, False, False, 0)
        columns.pack_start(pid_col, False, False, 0)

        def section_label(text):
            label = Gtk.Label()
            label.set_markup("<b>" + text + "</b>")
            label.set_xalign(0)
            return label

        scale_col.pack_start(section_label("Axis Scales"), False, False, 0)
        checks = {}
        for axis_id in AXIS_STEPGEN:
            check = Gtk.CheckButton(label=axis_id + " Scale")
            check.set_active(True)
            scale_col.pack_start(check, False, False, 0)
            checks[axis_id] = check

        pid_col.pack_start(section_label("PID Gains"), False, False, 0)
        pid_checks = {}
        for axis_id in list(PID_AXES) + list(PID_SPINDLE_LOOPS):
            check = Gtk.CheckButton(label=axis_id + " PID")
            check.set_active(True)
            pid_col.pack_start(check, False, False, 0)
            pid_checks[axis_id] = check

        content.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 0)

        measurement_check = Gtk.CheckButton(label="Measurement System")
        measurement_check.set_active(True)
        content.pack_start(measurement_check, False, False, 0)

        all_checks = list(checks.values()) + list(pid_checks.values()) + [measurement_check]
        select_all_btn.connect("clicked", lambda b: [c.set_active(True) for c in all_checks])
        select_none_btn.connect("clicked", lambda b: [c.set_active(False) for c in all_checks])

        content.show_all()

        result = None
        while True:
            response = dialog.run()
            if response != Gtk.ResponseType.OK:
                break

            axes = [axis_id for axis_id, c in checks.items() if c.get_active()]
            pid_axes = [axis_id for axis_id, c in pid_checks.items() if c.get_active()]
            measurement_system = measurement_check.get_active()
            if not axes and not pid_axes and not measurement_system:
                _show_settings_error(widget, "Select at least one item to export.")
                continue

            result = {"axes": axes, "pid_axes": pid_axes, "measurement_system": measurement_system}
            break

        dialog.destroy()
        return result

#######################################################################
# Import_Settings
# Purpose:              Reads a .export.ini file and applies whatever
#                           subset of axis Scale/Measurement System
#                           values it contains to the current settings -
#                           everything else on the Settings tab is left
#                           untouched. Applies each value through the
#                           same widget handlers a live edit would use
#                           (<Axis>_Set_Scale/Measurement_System_Changed),
#                           so the usual per-axis safety checks (motion
#                           abort, disable-if-enabled) and dirty-tracking
#                           all apply exactly as if the operator had
#                           typed/selected each value themselves.
# Updated:              ver 1.0, 30 July 2026, Claude
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

        imported = []
        for axis_el in root.findall("axis"):
            axis_id = axis_el.get("id")
            if axis_id not in AXIS_STEPGEN:
                continue

            # Scale and PID are independent - an export may carry either,
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

    def X_Comment(self, widget):
        self._save_axis_comment("X", widget.get_text())

    def Z_Comment(self, widget):
        self._save_axis_comment("Z", widget.get_text())

    def U_Comment(self, widget):
        self._save_axis_comment("U", widget.get_text())

    def V_Comment(self, widget):
        self._save_axis_comment("V", widget.get_text())

    def W_Comment(self, widget):
        self._save_axis_comment("W", widget.get_text())

    def B_Comment(self, widget):
        self._save_axis_comment("B", widget.get_text())

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
# Updated:              ver 1.0, 21 July 2026, R. Colvin
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

        # Send an MDI command to move along the axis.
        Gcode = "G1 B" + str(self.B_Idx_Deg) + " F" + str(self.B_Feed)

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
# Updated:              ver 1.0, 21 July 2026, R. Colvin
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

        # Send an MDI command to move along the axis.
        Gcode = "G1 B-" + str(self.B_Idx_Deg) + " F" + str(self.B_Feed)

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

        self._mark_settings_dirty()

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
# Updated:              ver 1.0, 21 July 2026, R. Colvin
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
# Gcodes Called:        S, M3
#######################################################################
    def Sp0_Move_Fwd(self,widget):

        print("=================================================")
        print("FUNCTION Sp0_Move_Fwd")

        # Ensure the system is in MDI mode
        c.mode(linuxcnc.MODE_MDI)
        s.poll()
        if s.task_state != linuxcnc.MODE_MDI:
                c.mode(linuxcnc.MODE_MDI)
                c.wait_complete() # Wait for mode change to complete

        # Set the feed rates
        Sp1_Feed = self.Sp1_Pct * self.Sp0_Feed / 100

        # Send an MDI command to set the spindles' speed.
        sSp0_Feed = "S" + str(self.Sp0_Feed) + " $0"
        sSp1_Feed = "S" + str(Sp1_Feed) + " $1"

        print(sSp0_Feed)
        c.mdi(sSp0_Feed)

        print(sSp1_Feed)
        c.mdi(sSp1_Feed)

        # Send an MDI command to start spindles rotating.
        Gcode = "M3 $-1"

        print(Gcode)
        c.mdi(Gcode)

        # Wait for the command to complete
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

        sign is +1 for forward, -1 for reverse. Only called when both
        Sp0_Idx_Bool and Sp1_Idx_Bool are true (see callers).
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
# Updated:              ver 1.0, 21 July 2026, R. Colvin
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
                # sequential M19s.
                self._index_both_spindles_simultaneously(+1)
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
                target_angle = (current_angle + self.Sp0_Idx_Deg) % 360.0

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
# Sp0_Move_Idx_Rev
# Purpose:              This is used to index the Sp0 spindle in a
#                           reverse direction.
# Updated:              ver 1.0, 21 July 2026, R. Colvin
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
                self._index_both_spindles_simultaneously(-1)
                return

            # See Sp0_Move_Idx_Fwd for why the target is computed per-spindle
            # from live position, and why the checkboxes gate each M19 (only
            # one of Sp0_Idx_Bool/Sp1_Idx_Bool can be true past this point).
            if self.Sp0_Idx_Bool:
                current_angle = (hal.get_value('spindle.0-position-fb') % 1.0) * 360.0
                target_angle = (current_angle - self.Sp0_Idx_Deg) % 360.0

                # NOTE: P0 = shortest path - see matching note in Sp0_Move_Idx_Fwd.
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
# Sp0_Move_Rev
# Purpose:              This is used to start the spindles rotating in
#                           reverse.
#                       Note:  this starts both Sp0 and Sp1.
# Updated:              ver 1.0, 21 July 2026, R. Colvin
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
# Gcodes Called:        S, M4
#######################################################################
    def Sp0_Move_Rev(self,widget):

        print("=================================================")
        print("FUNCTION Sp0_Move_Rev")

        # Ensure the system is in MDI mode
        c.mode(linuxcnc.MODE_MDI)
        s.poll()
        if s.task_state != linuxcnc.MODE_MDI:
                c.mode(linuxcnc.MODE_MDI)
                c.wait_complete() # Wait for mode change to complete

        # In case the values had not already been written to the
        # Gcode S values, write them.
        Sp1_Feed = self.Sp1_Pct * self.Sp0_Feed / 100

        # Send an MDI command to set the spindles' speed.
        sSp0_Feed = "S" + str(self.Sp0_Feed) + " $0"
        sSp1_Feed = "S" + str(Sp1_Feed) + " $1"

        print(sSp0_Feed)
        c.mdi(sSp0_Feed)

        print(sSp1_Feed)
        c.mdi(sSp1_Feed)

        # Send an MDI command to start spindles rotating.
        Gcode = "M4 $-1"

        print(Gcode)
        c.mdi(Gcode)

        # Wait for the command to complete
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
        # from _load_settings_file's programmatic spin.set_value() (the
        # startup auto-reload of the last-used .rebset, via
        # _prompt_initial_settings_load) - which runs before the
        # operator has powered on/reset E-stop, when there's no
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

        self._mark_settings_dirty()

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

        self._mark_settings_dirty()

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

        # .settings.ini save/load state (Settings_Save/Settings_Load, see
        # docs/settings_file.md). _applying_settings suppresses
        # _mark_settings_dirty while Settings_Load is itself the one
        # driving widget values, so re-applying a loaded scale doesn't
        # immediately re-dirty the settings just loaded.
        self._applying_settings   = False
        self._settings_dirty      = False
        self._settings_name       = None
        self._settings_path       = None  # current file for plain Settings_Save; None -> behaves like Save As
        self._settings_source_path = None  # full path shown on Settings_File_Path - see _set_settings_source_path_display

        # Suppresses Measurement_System_Changed's save/patch/popup while
        # _load_measurement_system is itself the one driving the combo box
        # at startup (see combo.set_active there) - a startup load should
        # not re-save REB_Settings_v1.ini, re-patch REB.ini, or pop up the
        # restart notice.
        self._applying_measurement_system = False

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

        # Restore persisted per-axis user comments (REB_Settings_v1.ini)
        # into the main panel's comment fields. No-ops in every
        # component other than the main panel (gladevcp), which is the
        # only one with these widgets.
        self._load_axis_comments()

        # Restore the persisted Measurement System (REB_Settings_v1.ini)
        # into the Settings tab's combo box (if owned by this component)
        # and the unit-of-measure labels this component owns on either
        # the main panel or the Settings tab.
        self._load_measurement_system()

        # There's no stored "last loaded .settings.ini" carried across restarts
        # (only the auto-persisted REB_Settings_v1.ini values, already
        # applied above regardless of what happens here) - so every
        # session starts with nothing named. Prompt once, after the tab
        # is actually up, to pick a saved profile; deferred via idle_add
        # since __init__ runs before the toplevel is realized. Only in
        # the component that owns these widgets.
        if self.builder.get_object("X_Set_Scale") is not None:
            GLib.idle_add(self._prompt_initial_settings_load)

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

def _axis_idx_move(axis, sign):
    label = "Minus" if sign == "-" else "Plus"
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
            Gcode = "G1 " + axis + sign + str(dist) + " F" + str(feed)

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

        self._mark_settings_dirty()
    handler.__name__ = axis + "_Set_Scale"
    return handler

def _axis_set_ena(axis):
    def handler(self, widget, *args):
        _clear_ena_override(axis)
    handler.__name__ = axis + "_Set_Ena"
    return handler

for _axis in LINEAR_AXES:
    setattr(HandlerClass, _axis + "_Idx_Minus", _axis_idx_move(_axis, "-"))
    setattr(HandlerClass, _axis + "_Idx_Plus",  _axis_idx_move(_axis, "+"))
    setattr(HandlerClass, _axis + "_Set_Feed", _axis_set_feed(_axis))
    setattr(HandlerClass, _axis + "_Set_Ena", _axis_set_ena(_axis))
    setattr(HandlerClass, _axis + "_Set_Idx_Dist", _axis_set_idx_dist(_axis))
    setattr(HandlerClass, _axis + "_Set_Move_Dist", _axis_set_move_dist(_axis))
    setattr(HandlerClass, _axis + "_Set_Scale", _axis_set_scale(_axis))
del _axis

def _pid_set(hal_pin):
    '''
    Generic value-changed handler for a single P/I/D/FF0/FF1/FF2 spin
    button: pushes the new value straight to the live pid.* HAL gain
    pin. Unlike _axis_set_scale, there's no need to disable the axis
    first - a PID gain is safe to retune on the fly, it doesn't
    invalidate an in-progress move the way a scale change can.

    REB_Settings_v1.ini itself is not written here - same as scale,
    that only happens at shutdown (REB_Scale_Persist.py reading the
    live HAL pins), not on every keystroke/spin-click.
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

def get_handlers(halcomp,builder,useropts):
    '''
    this function is called by gladevcp at import time (when this module is passed with '-u <modname>.py')

    return a list of object instances whose methods should be connected as callback handlers
    any method whose name does not begin with an underscore ('_') is a  callback candidate

    the 'get_handlers' name is reserved - gladevcp expects it, so do not change
    '''
    return [HandlerClass(halcomp,builder,useropts)]

#
