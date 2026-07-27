#! /home/reuben/linuxcnc/
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
#
# LinuxCNC configuration for use with a Rose Engine
#
# File:
#   REB_Update.sh
#
# Purpose:
#   This updates the files pulled from GitHub.
#
# End User Customisation:
#   THE END USER OF THE ROSE ENGINE BUTLER SYSTEM SHOULD NOT MODIFY
#   THIS FILE.
#
#   Changes to this file are not supported by Colvin Tools nor
#   Brainwave Embedded.
#
# Version
#   1.0 - 27 Oct 2025, R. Colvin
#   1.1 - 23 Dec 2025, R. Colvin - Changed text from "upgrade" to
#         "update".
#   1.2 - 22 January 2026, R. Colvin - Updated to run on Debian 13
#             Trixie: updated directories from
#                /home/reuben/
#             to
#                /home/reuben/
#
# Copyright (c) 2026 Colvin Tools and Brainwave Embedded.
#
# The following MIT/X Consortium License applies to the Rose Engine
# Butler system.  Use of this system constitutes consent to the terms
# outlined below.
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
# CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#
# Except as contained in this notice, the name of COPYRIGHT HOLDERS
# shall not be used in advertising or otherwise to promote the sale,
# use or other dealings in this Software without prior written
# authorization from COPYRIGHT HOLDERS.
#
# ********************************************************************
# Colours are detailed at the end of this program
#
TITLE='\033[0;34;1;47m'     # Blue on Lt Gray
KEYNOTE='\033[0;37;0;41m'   # Lt Gray on Red
CMNTTEXT='\033[0;34;1;40m'  # Blue on Black
NOCOLOR='\e[0m'
sSpaces='   '
#
# ********************************************************************
echo -e "${TITLE}#######################################################################${NOCOLOR}"
echo -e "${TITLE}#                    RRRRRR    EEEEEEEE  BBBBBBB                      #${NOCOLOR}"
echo -e "${TITLE}#                    RR   RR   EE        BB    BB                     #${NOCOLOR}"
echo -e "${TITLE}#                    RR   RR   EE        BB    BB                     #${NOCOLOR}"
echo -e "${TITLE}#                    RRRRRR    EEEEEE    BBBBBBB                      #${NOCOLOR}"
echo -e "${TITLE}#                    RR   RR   EE        BB    BB                     #${NOCOLOR}"
echo -e "${TITLE}#                    RR   RR   EE        BB    BB                     #${NOCOLOR}"
echo -e "${TITLE}#                    RR    RR  EEEEEEEE  BBBBBBB                      #${NOCOLOR}"
echo -e "${TITLE}#######################################################################${NOCOLOR}"
echo -e "${TITLE}                                                                       ${NOCOLOR}"
echo -e "${TITLE}Use of this system constitutes consent to the MIT/X Consortium License ${NOCOLOR}"
echo -e "${TITLE}as it applies to the Rose Engine Butler system.                        ${NOCOLOR}"
echo -e "${TITLE}                                                                       ${NOCOLOR}"
echo -e "${TITLE}Update the system                                                     ${NOCOLOR}"
echo -e "${TITLE}                                                                       ${NOCOLOR}"
echo -e "${TITLE}#######################################################################${NOCOLOR}"
echo -e "${TITLE}Pull latest files from GitHub                                          ${NOCOLOR}"
cd /home/reuben/linuxcnc/configs/RoseEngineButler
sudo git stash
sudo git pull
if [ $? != 0 ]; then
    echo -e "${KEYNOTE}ERROR: git pull failed.                                              ${NOCOLOR}"
    echo -e "${KEYNOTE}PROGRAM TERMINATED PREMATURELY                                       ${NOCOLOR}"
    exit $?
fi
echo -e "${TITLE}Latest files pulled from GitHub                                        ${NOCOLOR}"
echo -e "${TITLE}#######################################################################${NOCOLOR}"
echo -e "${TITLE}Update the package indexes                                             ${NOCOLOR}"
sudo apt update
if [ $? != 0 ]; then
    echo -e "${KEYNOTE}ERROR: Package update failed                                         ${NOCOLOR}"
    echo -e "${KEYNOTE}PROGRAM TERMINATED PREMATURELY                                       ${NOCOLOR}"
    exit $?
fi
echo -e "${TITLE}Latest package updates secured                                         ${NOCOLOR}"
echo -e "${TITLE}#######################################################################${NOCOLOR}"
echo -e "${TITLE}Update the system                                                      ${NOCOLOR}"
sudo apt upgrade -y
if [ $? != 0 ]; then
    echo -e "${KEYNOTE}ERROR: System upgrade failed                                         ${NOCOLOR}"
    echo -e "${KEYNOTE}PROGRAM TERMINATED PREMATURELY                                       ${NOCOLOR}"
    exit $?
fi
echo -e "${TITLE}System Updated                                                         ${NOCOLOR}"
echo -e "${TITLE}#######################################################################${NOCOLOR}"
