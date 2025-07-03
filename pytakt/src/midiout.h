/* -*- C++ -*- 
 * Realtime MIDI I/O Library for Pytakt
 *
 *  Class for real-time MIDI output (also maintains beat-second mapping)
 *
 *  This code was originally a part of Takt, an interpreter for the Takt music 
 *  programming language.
 */

/* Copyright (C) 2014, 2025  Satoshi Nishimura */

#ifndef _Takt_MidiOut_
#define _Takt_MidiOut_

#include "sysdep.h"
#include "defs.h"

namespace Takt {
class MidiOut {
public:
    /* initialization 
       - create MIDIOUT thread for time management and MIDI output */
    static void startup();

    /* open the midi-output device specified by devNum. 
       - if the device is already open, nothing is done
       - returns true when the device open error is detected */
    static bool openDevice(int devNum);

    static void closeDevice(int devNum);
    static bool isOpenedDevice(int devNum);

    /* put a message in the message queue 
       - devNum can be DEV_DUMMY or DEV_LOOPBACK
       - returns true when the device is not opened or message is invalid */
    static bool queueMessage(int devNum, double ticks, int tk,
			     const message_t& msg);

    /* cancel messages in the message queue
       - every message where its track number matches tk is deleted.
       - If tk is ALL_TRACKS, it matches any track.
       - note-off messages are sent to sounding notes.
       - sustain-off messages are sent to holding pedals. */
    static void cancelMessages(int devNum, int tk);
    
    /* shutdown - kill MIDIOUT thread */
    static void shutdown();

    /* stop all the sounding notes */
    static void stopAll();

    /* time conversion */
    static double ticksToMsecs(double ticks);
    static double msecsToTicks(double msecs);
    static double getCurrentTempo();
    static double getCurrentTime() { return msecsToTicks(SysDep::get_time()); }
    static void setTempoScale(double scale);
    static double getTempoScale();

    /* set note-retrigger mode (implies stopAll) */
    static void setRetrigger(bool enable);
};
}

#endif
