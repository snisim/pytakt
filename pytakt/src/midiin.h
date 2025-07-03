/* -*- C++ -*-
 * Realtime MIDI I/O Library for Pytakt
 *
 *  Class for MIDI input (device input manager)
 *
 *  This code was originally a part of Takt, an interpreter for the Takt music 
 *  programming language.
 */

/* Copyright (C) 2014, 2025  Satoshi Nishimura */

#ifndef _Takt_MidiIn_
#define _Takt_MidiIn_

#include "sysdep.h"
#include "defs.h"

namespace Takt {
class MidiIn { 
public:
    /* initialization - create MIDIIN thread */ 
    static void startup();

    /* open a MIDI-input evice if it has not been opened yet
       - returns true when the device open error is detected */
    static bool openDevice(int devNum);

    static void closeDevice(int devNum);
    static bool isOpenedDevice(int devNum);

    /* test if there is a message in the queue - called from MAIN thread */
    static bool receiveReady();

    /* receive a message from the message queue - called from MAIN thread */
    static void receiveMessage(int &devNum, double &ticks, int &tk,
			       message_t& msg);

    /* put a message in the input queue */
    static void enqueue(int devNum, double ticks, int tk, const message_t& msg);

    /* clear all pending input messages and make receiveMessage return with
       an empty message */
    static void interrupt();

    /* shutdown - kill MIDIIN thread */
    static void shutdown();
};
}

#endif
