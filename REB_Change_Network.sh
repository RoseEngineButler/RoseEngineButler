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
#   REB_Change_Network.sh
#
# Purpose:
#   Moves a Rose Engine Butler onto its private wired network for the
#   two-box hardware: the base box's Mesa 7i92 at 10.10.10.10, the
#   expansion box's at 10.10.10.11 and the Raspberry Pi's wired
#   connection at 10.10.10.100, with no gateway or DNS on it (the Pi's
#   internet stays on Wi-Fi). These are the addresses
#   REB_Setup/REB_Generate_Local_Ini.py loads the cards at.
#
#   A new 7i92 always answers at its factory address, 192.168.1.121,
#   so a card is set up while the Pi is still on 192.168.1.120 and with
#   only that one card connected - two cards on the same address would
#   clash. The new address is stored on the card (its EEPROM); the card
#   only uses it once its W5/W6 jumpers are moved to the setting the
#   7i92 manual calls EEPROM, which is read at power-up.
#
#   Choices (menu, or as the first argument):
#     base       set up the connected card as the base card (.10)
#     expansion  set up the connected card as the expansion card (.11)
#     pi         move the Pi's wired connection to 10.10.10.100
#     back       put the Pi's wired connection back on 192.168.1.120
#   Add --dry-run to show every command without running any of them.
#
#   Nothing is changed without asking first. Recovery for a card: put
#   W5/W6 back to their factory setting and it answers at 192.168.1.121
#   again.
#
# End User Customisation:
#   THE END USER OF THE ROSE ENGINE BUTLER SYSTEM SHOULD NOT MODIFY
#   THIS FILE.
#
#   Changes to this file are not supported by Colvin Tools nor
#   Brainwave Embedded.
#
# Version
#   1.0 - 14 October 2026
#
# Copyright (c) 2026 Colvin Tools and Brainwave Embedded.
#
# The MIT/X Consortium License applies - see LICENSE.
#######################################################################

TITLE='\033[0;34;1;47m'     # Blue on Lt Gray
KEYNOTE='\033[0;37;0;41m'   # Lt Gray on Red
CMNTTEXT='\033[0;34;1;40m'  # Blue on Black
NOCOLOR='\e[0m'

REPO_DIR="/home/reuben/linuxcnc/configs/RoseEngineButler"
FIRMWARE="$REPO_DIR/REB_Setup/MesaCard/7i92t_REB.bin"
CONNECTION="Wired Ethernet"

# A Pi where the installer was run more than once has several
# connections called "Wired Ethernet" (found 14 October 2026), and nmcli
# then changes just one of them. Use the one on eth0 now (else the
# first), by its UUID, and give it a higher autoconnect priority so the
# Pi starts with that one.
CONNECTION_UUID=$(nmcli -t -f UUID,NAME,DEVICE con show --active 2>/dev/null \
    | awk -F: -v n="$CONNECTION" '$2 == n && $3 == "eth0" {print $1; exit}')
if [ -z "$CONNECTION_UUID" ]; then
    CONNECTION_UUID=$(nmcli -t -f UUID,NAME con show 2>/dev/null \
        | awk -F: -v n="$CONNECTION" '$2 == n {print $1; exit}')
fi
FACTORY_CARD_IP="192.168.1.121"
OLD_PI_IP="192.168.1.120/24"
BASE_CARD_IP="10.10.10.10"
EXPANSION_CARD_IP="10.10.10.11"
PI_IP="10.10.10.100/24"

DRY_RUN=false
CHOICE=""
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
        base|expansion|pi|back) CHOICE="$arg" ;;
        *) echo "Unknown option: $arg (use base, expansion, pi, back, --dry-run)"; exit 1 ;;
    esac
done

say()  { echo -e "${CMNTTEXT}$1${NOCOLOR}"; }
warn() { echo -e "${KEYNOTE}$1${NOCOLOR}"; }
title() {
    echo -e "${TITLE}#######################################################################${NOCOLOR}"
    echo -e "${TITLE}$1${NOCOLOR}"
}

# Runs a command, or only shows it with --dry-run.
run() {
    if $DRY_RUN; then
        printf '    [dry run]'; printf ' %q' "$@"; printf '\n'
        return 0
    fi
    "$@"
}

# Asks a yes/no question; anything but y/yes means no.
confirm() {
    local answer
    read -r -p "$1 [y/N] " answer
    [[ "$answer" =~ ^[Yy]([Ee][Ss])?$ ]]
}

pause() {
    read -r -p "$1 Press Enter when ready (Ctrl+C to stop)... " _
}

# True if a 7i92 answers at the given address.
card_answers() {
    if $DRY_RUN; then
        echo "    [dry run] mesaflash --device 7i92t --addr $1 --readhmid  (assumed to answer)"
        return 0
    fi
    mesaflash --device 7i92t --addr "$1" --readhmid > /dev/null 2>&1
}

stop_if_linuxcnc_running() {
    if pgrep -x linuxcncsvr > /dev/null || pgrep -x milltask > /dev/null; then
        warn "LinuxCNC is running. Close it, then run this again.              "
        exit 1
    fi
}

# --- set up one card --------------------------------------------------
set_up_card() {   # $1 = new address, $2 = "base" or "expansion"
    local new_ip="$1" which="$2"
    title "Set up the $which card ($new_ip)"
    stop_if_linuxcnc_running

    if ! ip -4 addr show | grep -q "inet 192\.168\.1\."; then
        warn "The Pi's wired connection isn't on 192.168.1.x, so it can't reach a"
        warn "card at its factory address. Choose 'back' first, then run this again."
        exit 1
    fi

    say "Connect ONLY the card being set up (unplug any other card), with its"
    say "W5/W6 jumpers at the factory setting, and power it on."
    pause ""

    say "Checking the card answers at $FACTORY_CARD_IP..."
    if ! card_answers "$FACTORY_CARD_IP"; then
        warn "No card answered at $FACTORY_CARD_IP - nothing was changed.        "
        warn "Check the cable, the card's power and its W5/W6 jumpers.          "
        exit 1
    fi
    say "Card found."

    if confirm "Write the Rose Engine Butler firmware to it (needed on a new card)?"; then
        run mesaflash --device 7i92t --addr "$FACTORY_CARD_IP" --write "$FIRMWARE" --reload
        if [ $? != 0 ]; then
            warn "Writing the firmware failed - the card's address was not changed."
            exit 1
        fi
    fi

    if ! confirm "Store $new_ip as this card's address?"; then
        say "Address not changed."
        exit 0
    fi
    run mesaflash --device 7i92t --addr "$FACTORY_CARD_IP" --set ip="$new_ip"
    if [ $? != 0 ]; then
        warn "Storing the address failed - the card still answers at $FACTORY_CARD_IP."
        exit 1
    fi

    say "Address stored. Now:"
    say "  1. Power the card off."
    say "  2. Move its W5/W6 jumpers to the setting the 7i92 manual calls EEPROM."
    say "  3. Power it back on. It will answer at $new_ip."
    say "To undo: jumpers back to the factory setting = $FACTORY_CARD_IP again."
    pause ""

    if confirm "Move the Pi's wired connection to 10.10.10.100 now and check the card?"; then
        move_pi
    else
        say "Pi left on 192.168.1.x - choose 'pi' once every card is set up."
    fi
}

# --- move the Pi ------------------------------------------------------
move_pi() {
    title "Move the Pi's wired connection to ${PI_IP%/*}"
    stop_if_linuxcnc_running
    run nmcli con mod "$CONNECTION_UUID" ipv4.method manual ipv4.addresses "$PI_IP" ipv4.gateway "" ipv4.dns "" connection.autoconnect-priority 10
    if [ $? != 0 ]; then
        warn "Changing the '$CONNECTION' connection failed - nothing else was changed."
        exit 1
    fi
    run nmcli con up "$CONNECTION_UUID"
    sleep 2
    for card_ip in "$BASE_CARD_IP" "$EXPANSION_CARD_IP"; do
        if card_answers "$card_ip"; then
            say "Card at $card_ip answers."
        else
            say "No card at $card_ip (fine if that card isn't set up or connected)."
        fi
    done
}

# --- put the Pi back --------------------------------------------------
move_pi_back() {
    title "Put the Pi's wired connection back on ${OLD_PI_IP%/*}"
    stop_if_linuxcnc_running
    say "Use this to reach a card at its factory address, or to run software"
    say "from before the two-box change. A card already moved to 10.10.10.x"
    say "also needs its W5/W6 jumpers back at the factory setting."
    confirm "Continue?" || exit 0
    run nmcli con mod "$CONNECTION_UUID" ipv4.method manual ipv4.addresses "$OLD_PI_IP" ipv4.gateway "" ipv4.dns "" connection.autoconnect-priority 10
    run nmcli con up "$CONNECTION_UUID"
    sleep 2
    if card_answers "$FACTORY_CARD_IP"; then
        say "Card at $FACTORY_CARD_IP answers."
    else
        say "No card at $FACTORY_CARD_IP yet."
    fi
}

# --- main -------------------------------------------------------------
$DRY_RUN && warn "DRY RUN - commands are shown, not run.                              "
if [ -z "$CHOICE" ]; then
    title "Rose Engine Butler - network setup"
    echo "  1) Set up a card as the base card       ($BASE_CARD_IP)"
    echo "  2) Set up a card as the expansion card  ($EXPANSION_CARD_IP)"
    echo "  3) Move the Pi's wired connection to    ${PI_IP%/*}"
    echo "  4) Put the Pi back on                   ${OLD_PI_IP%/*}"
    read -r -p "Choose 1-4: " pick
    case "$pick" in
        1) CHOICE=base ;; 2) CHOICE=expansion ;; 3) CHOICE=pi ;; 4) CHOICE=back ;;
        *) echo "Nothing chosen."; exit 0 ;;
    esac
fi
case "$CHOICE" in
    base)      set_up_card "$BASE_CARD_IP" base ;;
    expansion) set_up_card "$EXPANSION_CARD_IP" expansion ;;
    pi)        move_pi ;;
    back)      move_pi_back ;;
esac
title "Done"
