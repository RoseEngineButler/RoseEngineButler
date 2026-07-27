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
#   REB_Spindle1.inc                                                  #
#                                                                     #
# Purpose:                                                            #
#   This is used to setup the Spindle 1 axis (Rosette Phaser/         #
#   Multiplier) for the configuration of LinuxCNC.                    #
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
#  SSSSSS  PPPPPPP  IIIIIIII N     NN DDDDDDD  LL       EEEEEEEE  1111
# SS    SS PP    PP    II    NN    NN DD    DD LL       EE       11 11
#  SSS     PP    PP    II    NNN   NN DD    DD LL       EEEEE       11
#     SSS  PPPPPPP     II    NN NN NN DD    DD LL       EE          11
# SS    SS PP          II    NN  NNNN DD    DD LL       EE          11
#  SSSSSS  PP       IIIIIIII NN    NN DDDDDDD  LLLLLLLL EEEEEEEE 11111111
# ********************************************************************

# ********************************************************************
# Configuration values
#                                 Home 
#  Axis  Joint  Channel   Type     Seq   Comments
#  ----  -----  -------  -------  ----   ------------------------
#  Sp0     7       06      n/a     n/a 
#  Sp1     6       07      n/a     n/a

[JOINT_6]
SPINDLE              = 1
TYPE                 = ANGULAR

[SPINDLE_1]
TYPE                 = ANGULAR

MAX_VELOCITY         = 100
MAX_ACCELERATION     = 30

# STEPGEN_MAXVEL       = 3
STEPGEN_MAXVEL       = 8
# STEPGEN_MAXACCEL     = 1
STEPGEN_MAXACCEL     = 6

# ********************************************************************
# STANDARD VALUES
#
# These parameters are best left alone

BACKLASH             = 0.0000

MIN_FERROR           = 0.5
FERROR               = 5

DEADBAND             = 0.000015
MAX_OUTPUT           = 10.0

P_VEL                = 35
I_VEL                = 20
D_VEL                = 1.2
BIAS_VEL             = 0.0
FF0_VEL              = 1.0
FF1_VEL              = 0.0
FF2_VEL              = 0.0

MAX_OUTPUT_VEL       = 10.0

P_POS                = 35
I_POS                = 20
D_POS                = 1.2
BIAS_POS             = 0.0
FF0_POS              = 1.0
FF1_POS              = 0.0
FF2_POS              = 0.0

MAX_OUTPUT_POS		 = 2.0

# For the StepperOnline DM542T Digital Stepper Drive 
# These are 5 μs = 5,000 ns
DIRHOLD              = 5000
DIRSETUP             = 5000
# These are 2.5 μs = 2,500 ns
STEPLEN              = 2500
STEPSPACE            = 2500
# ********************************************************************
