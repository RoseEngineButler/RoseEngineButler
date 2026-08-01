#!/bin/bash
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
#   REB_Launch.sh
#
# Purpose:
#   Desktop-launcher entry point for a LinuxCNC session. Regenerates
#   REB.local.ini (written next to REB.ini, in this repo's own
#   directory - see REB_Generate_Local_Ini.py's header for why it can't
#   live in RoseEngineButlerLocal instead) from the tracked REB.ini,
#   overlaying this machine's persisted Max Jog Speed / Measurement
#   System, and starts LinuxCNC against that generated file instead of
#   the tracked REB.ini directly. This keeps REB.ini itself untouched so
#   a `git pull` never clobbers a machine-local setting.
#
#   Point the desktop launcher's Exec= at this script instead of at
#   `linuxcnc REB.ini` directly.
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

set -e

REPO_DIR="/home/reuben/linuxcnc/configs/RoseEngineButler"
LOCAL_INI="$REPO_DIR/REB.local.ini"

python3 "$REPO_DIR/REB_Setup/REB_Generate_Local_Ini.py"
exec linuxcnc "$LOCAL_INI"
