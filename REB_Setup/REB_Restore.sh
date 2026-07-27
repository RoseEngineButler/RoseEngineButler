#! /home/cnc/linuxcnc/
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
#   Restore.sh
#
# Purpose:
#   This restores the files to their original settings.
#
# End User Customisation:
#   THE END USER OF THE ROSE ENGINE BUTLER SYSTEM SHOULD NOT MODIFY
#   THIS FILE.
#
#   Changes to this file are not supported by Colvin Tools nor
#   Brainwave Embedded.
#
# Version
#   1.0 - 26 Oct 2025, R. Colvin
#
# Copyright (c) 2025 Colvin Tools and Brainwave Embedded. 
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
echo -e "${TITLE}Restore user files.                                                    ${NOCOLOR}"
echo -e "${TITLE}                                                                       ${NOCOLOR}"
# ********************************************************************
# Restoring up files 
#   from /home/cnc/linuxcnc/configs/RoseEngineButlerLocal_Backup/
#   to   /home/cnc/linuxcnc/configs/RoseEngineButlerLocal/
echo -e "${TITLE}#######################################################################${NOCOLOR}"
echo -e "${TITLE}Restoring files                                                        ${NOCOLOR}"
echo -e "${TITLE}from /home/cnc/linuxcnc/configs/RoseEngineButlerLocal_Backup.          ${NOCOLOR}"
echo -e "${TITLE}to /home/cnc/linuxcnc/configs/RoseEngineButlerLocal.                   ${NOCOLOR}"
cd /home/cnc/linuxcnc/configs/RoseEngineButlerLocal
sudo cp -r /home/cnc/linuxcnc/configs/RoseEngineButlerLocal_Backup/*.* .
if [ $? != 0 ]; then
    echo -e "${KEYNOTE}ERROR: Copy of files from                                            ${NOCOLOR}"
    echo -e "${KEYNOTE}    /home/cnc/linuxcnc/configs/RoseEngineButlerLocal_Backup/         ${NOCOLOR}"
    echo -e "${KEYNOTE}to                                                                   ${NOCOLOR}"
    echo -e "${KEYNOTE}    /home/cnc/linuxcnc/configs/RoseEngineButlerLocal/                ${NOCOLOR}"
    echo -e "${KEYNOTE}failed.                                                              ${NOCOLOR}"
    echo -e "${KEYNOTE}PROGRAM TERMINATED PREMATURELY                                       ${NOCOLOR}"
    exit $?
fi
echo -e "${TITLE}Backup successful.                                                     ${NOCOLOR}"
