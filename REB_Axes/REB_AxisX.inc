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
#                                                                     #
# LinuxCNC configuration for use with a Rose Engine                   #
#                                                                     #
# File:                                                               #
#   REB_AxisX.inc                                                     #
#                                                                     #
# Purpose:                                                            #
#   This is used to setup the X axis for the configuration of         #
#   LinuxCNC.                                                         #
#                                                                     #
# End User Customisation:                                             #
#   The end user of the Rose Engine Butler system may modify this     #
#   file to accommodate their local configuration.  It is recommended #
#   that a copy of this file be saved before changes are made.        #
#                                                                     #
#   Changes to this file are not supported by Colvin Tools nor        #
#   Brainwave Embedded.                                               #
#                                                                     #
# Version                                                             #
#   1.0 - 22 July 2026, R. Colvin                                     #
#                                                                     #
# Copyright (c) 2026 Colvin Tools and Brainwave Embedded.             #
#                                                                     #
# The following MIT/X Consortium License applies to the Rose Engine   #
# Butler system. Use of this system constitutes consent to the terms  #
# outlined below.                                                     #
#                                                                     #
# Permission is hereby granted, free of charge, to any person         #
# obtaining a copy of this software and associated documentation      #
# files (the "Software"), to deal in the Software without             #
# restriction, including without limitation the rights to use, copy,  #
# modify, merge, publish, distribute, sublicense, and/or sell copies  #
# of the Software, and to permit persons to whom the Software is      #
# furnished to do so, subject to the following conditions:            #
#                                                                     #
#       The above copyright notice and this permission notice shall   #
#       be included in all copies or substantial portions of the      #
#       Software.                                                     #
#                                                                     #
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,     #
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF  #
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND               #
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS #
# BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN  #
# ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN   #
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE    #
# SOFTWARE.                                                           #
#                                                                     #
# Except as contained in this notice, the name of COPYRIGHT HOLDERS   #
# shall not be used in advertising or otherwise to promote the sale,  #
# use or other dealings in this Software without prior written        #
# authorization from COPYRIGHT HOLDERS.                               #
#######################################################################

# ********************************************************************
#    AA    XX    XX IIIIIIII  SSSSSS      YY    YY
#   AAAA    XX  XX    II     SS    SS      YY  YY
#  AA  AA    XXXX     II      SSS           YYYY
# AAAAAAAA   XXXX     II         SSS        XXXX
# AA    AA  XX  XX    II     SS    SS      XX   XX
# AA    AA XX    XX IIIIIIII  SSSSSS      XX     XX
# ********************************************************************

# ********************************************************************
# Configuration values
#                                 Home   PCB
#  Axis  Joint  Channel   Type     Seq  Plug  Comments
#  ----  -----  -------  -------  ----  ----  ------------------------
#   X      0       04    LINEAR     1    P15
# ********************************************************************

[AXIS_X]
# *******************
TYPE                 = LINEAR

# 1"/min = 0.083"/sec
MAX_VELOCITY         = 10
MAX_ACCELERATION     = 20.0

MIN_LIMIT            = -1e99
MAX_LIMIT            = 1e99

[JOINT_0]
TYPE                 = LINEAR
UNITS                = INCH

MAX_VELOCITY         = 10
MAX_ACCELERATION     = 20.0

# ********************************************************************
# STEPPER MOTOR SETTINGS
#

# Was 0.5 - lower than MAX_ACCELERATION (20.0) above, backwards from
# normal practice (stepgen limits should exceed trajectory limits with
# margin, same as STEPGEN_MAXVEL vs MAX_VELOCITY below). This let the
# trajectory planner demand more acceleration than the stepgen could
# ever deliver, producing a large following error at the start of every
# move that a P=35 loop then fought hard to correct, overshooting into
# oscillation. Raised to 1.5x MAX_ACCELERATION as a conservative
# starting point - retest live and retune from here.
STEPGEN_MAXACCEL     = 30

# Was 1.25 - with STEP_SCALE ~195900 steps/in (see RoseEngineButlerLocal
# copy) and STEPLEN+STEPSPACE = 5000ns/step, the hardware ceiling is
# 1/5000ns = 200,000 steps/sec = ~1.02 in/sec. 1.25 in/sec required
# ~244,875 steps/sec - more than hm2 could deliver, so it silently
# clipped (see the "maxvel is too big" warning) - a saturating PID
# output is a classic source of exactly the overshoot-then-slow-correct
# behavior seen live. Set with margin below the ~1.02 in/sec ceiling.
STEPGEN_MAXVEL       = 0.95

# ********************************************************************
# STANDARD VALUES
#
# These parameters are best left alone

BACKLASH             = 0.0000

MIN_LIMIT            = -1e99
MAX_LIMIT            = 1e99

MIN_FERROR           = 10
FERROR               = 100

HOME                 = 0.0
HOME_SEQUENCE        = 1

BIAS                 = 0.0
DEADBAND             = 0.00005
MAX_OUTPUT           = 10.0
OUTPUT_SCALE         = 1.000
OUTPUT_OFFSET        = 0.000

# Were P=35, I=20, D=1.2, FF1=0.0 - identical to Sp0/Sp1's P_VEL/I_VEL/
# D_VEL (a *velocity* loop), suggesting these were never independently
# tuned for X's *position* loop. With FF1=0, P+I alone had to do all the
# tracking work with nothing to lean on, causing overshoot followed by a
# slow correction (classic integral-windup signature from I=20
# accumulating error while feedforward wasn't helping it keep up). FF1
# now does most of the velocity tracking; P/I only need to clean up
# small residual error - retest live and retune from here.
P                    = 5
I                    = 1
D                    = 1.2
FF0                  = 0.0
FF1                  = 1.0
FF2                  = 0.0

# For the StepperOnline DM542T Digital Stepper Drive 
# These are 5 μs = 5,000 ns
DIRHOLD              = 5000
DIRSETUP             = 5000
# These are 2.5 μs = 2,500 ns
STEPLEN              = 2500
STEPSPACE            = 2500
# ********************************************************************
