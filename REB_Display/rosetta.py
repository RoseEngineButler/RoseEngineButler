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
#   rosetta.py
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
import linuxcnc
import webbrowser
import subprocess
import re
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

SETTINGS_PATH = "/home/reuben/linuxcnc/configs/RoseEngineButlerLocal/REB_Settings_v1.ini"

# Axes (not spindles) that have a free-text comment field on the main
# panel, persisted to REB_Settings_v1.ini as each <axis>'s <usercomment>.
COMMENT_AXES = ("X", "Z", "U", "V", "W", "B")

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
    # netted *_Ena_Override pin (see REB_PostGUI.hal) lives on the
    # Settings tab's component ("REBCnfg"), a different process. Writing
    # to self.halcomp there would only touch this component's own,
    # unconnected pin of the same name - a no-op. Cross the process
    # boundary via halcmd instead, the same way Sp0_Set_Scale already
    # does in the other direction for *_ENA-light.
    #
    # Once a pin is netted to a signal, halcmd can't "setp" the pin
    # directly ("pin is connected to a signal") - the signal itself has
    # to be set instead, via "halcmd sets". The signal name follows the
    # <axis>-ena-settings-allow convention in REB_PostGUI.hal.
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
        # own toggle bit (REB_PostGUI.hal) via the ordinary clk input -
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
        also using rosetta.py will find that widget missing and
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

    def _load_axis_comments(self):
        '''
        Reads each axis's persisted user comment from REB_Settings_v1.ini
        and applies it to that axis's comment field on the main panel.

        Only runs in the component that actually owns these Entry
        widgets (X_Comment etc., on the main REB_Panel) - every other
        tab/panel also using rosetta.py will find that widget
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
        # (ANDed with the panel button in REB_PostGUI.hal) instead of
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
#                           REB_PostGUI.hal for the flip-flop that
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

            # M19 orients to an absolute angle, not a relative step, so compute
            # the next target from each spindle's own actual current angle
            # rather than sending Sp0_Idx_Deg itself as R each time (which
            # would just re-target the same fixed angle on every press). The
            # Sp0/Sp1 checkboxes on the Indexing panel gate which spindle(s)
            # actually get an M19 - a spindle with no orient HAL chain (or one
            # the operator hasn't enabled) is simply skipped rather than
            # sent a command that can only time out.
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
                # Let Sp0's orient fully resolve before Sp1's M19 is even sent -
                # queuing both back-to-back with a single wait_complete() at the
                # end let Sp0's move interfere with Sp1's (see conversation: with
                # both checkboxes on, only Sp0 actually moved).
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

            # See Sp0_Move_Idx_Fwd for why the target is computed per-spindle
            # from live position, and why the checkboxes gate each M19.
            if self.Sp0_Idx_Bool:
                current_angle = (hal.get_value('spindle.0-position-fb') % 1.0) * 360.0
                target_angle = (current_angle - self.Sp0_Idx_Deg) % 360.0

                # NOTE: P0 = shortest path - see matching note in Sp0_Move_Idx_Fwd.
                GcodeStr3 = "M19 R" + str(target_angle) + " Q20 P0 $0"
                idx_log(GcodeStr3)
                c.mdi(GcodeStr3)
                # See matching note in Sp0_Move_Idx_Fwd - let Sp0 fully resolve
                # before Sp1's M19 is sent.
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
        s.poll()
        if s.task_state != linuxcnc.MODE_MDI:
                c.mode(linuxcnc.MODE_MDI)
                c.wait_complete()
        c.mdi("M5")
        c.wait_complete()

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
        # before the scale change lands.
        s.poll()
        if s.task_state != linuxcnc.MODE_MDI:
                c.mode(linuxcnc.MODE_MDI)
                c.wait_complete()
        c.mdi("M5")
        c.wait_complete()

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

        _install_depress_css()

        # Independent pins this component owns, used to force each
        # axis disabled from this tab regardless of what the main
        # panel's own enable button is doing. Each defaults to "allow
        # enabled". ANDed with the panel button per-axis in
        # REB_PostGUI.hal (REBCnfg.<Axis>_Ena_Override).
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

        # Restore persisted axis scale values (REB_Settings_v1.ini)
        # into the Settings tab's spin buttons and the real stepgen
        # scale pins. No-ops in every component other than the
        # Settings tab (REBHlp), which is the only one with these
        # widgets.
        self._load_scale_settings()

        # Restore persisted per-axis user comments (REB_Settings_v1.ini)
        # into the main panel's comment fields. No-ops in every
        # component other than the main panel (gladevcp), which is the
        # only one with these widgets.
        self._load_axis_comments()

        # Input pin fed from the existing "machine-is-on" HAL signal
        # (net machine-is-on => gladevcp.machine-is-on in
        # REB_PostGUI.hal). Grays out the whole main panel grid
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

        self.Sp1_Idx_Bool   = False     # Index this spindle? See Sp0_Idx_Bool - the checkbox renders unchecked at launch regardless of the .ui default.
        self.Sp1_Idx_Dist   = 90.0      # Sp1 index degrees
        self.Sp1_Idx_Qty    = 0         # Sp1 axis index counter
        self.Sp1_Pct        = 100.0     # Sp1 speed percentage of Sp0 speed

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
# comments). The real fix is reconnecting REB_Panel_v2.ui's <Axis>_ENA
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
        # (ANDed with the panel button in REB_PostGUI.hal) instead of
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
    setattr(HandlerClass, _axis + "_Idx_Minus", _axis_idx_move(_axis, "-"))
    setattr(HandlerClass, _axis + "_Idx_Plus",  _axis_idx_move(_axis, "+"))
    setattr(HandlerClass, _axis + "_Set_Feed", _axis_set_feed(_axis))
    setattr(HandlerClass, _axis + "_Set_Ena", _axis_set_ena(_axis))
    setattr(HandlerClass, _axis + "_Set_Idx_Dist", _axis_set_idx_dist(_axis))
    setattr(HandlerClass, _axis + "_Set_Move_Dist", _axis_set_move_dist(_axis))
    setattr(HandlerClass, _axis + "_Set_Scale", _axis_set_scale(_axis))
del _axis

def get_handlers(halcomp,builder,useropts):
    '''
    this function is called by gladevcp at import time (when this module is passed with '-u <modname>.py')

    return a list of object instances whose methods should be connected as callback handlers
    any method whose name does not begin with an underscore ('_') is a  callback candidate

    the 'get_handlers' name is reserved - gladevcp expects it, so do not change
    '''
    return [HandlerClass(halcomp,builder,useropts)]

#
