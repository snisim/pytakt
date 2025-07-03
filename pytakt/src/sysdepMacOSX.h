/* -*- C++ -*- 
 * Realtime MIDI I/O Library for Pytakt
 *
 *  Class for operating-system dependent routines (for Mac OS X)
 *
 *  This code was originally a part of Takt, an interpreter for the Takt music 
 *  programming language.
 */

/* Copyright (C) 2014, 2025  Satoshi Nishimura */

#define _SYSDEP_PTHREAD_ONLY
#include "sysdepGeneric.h"

#include <queue>
#include <vector>
#include <CoreMIDI/MIDIServices.h>
#include <CoreAudio/HostTime.h>
#include <CoreServices/CoreServices.h>
#include <AudioToolbox/AudioConverter.h>

namespace Takt {

struct SysDep::midiout_t 
{
    MIDIPortRef  outPort;
    MIDIEndpointRef  dest;
    MIDISysexSendRequest *sysexReq; /* non-NULL while sending a sysex msg */
    Byte *sysexData;
};

struct midiin_buffer_elm {
    UInt64  timeStamp;
    bool  isShortMsg;
    union {
	unsigned char  msg[3]; /* for short msg */
	std::vector<unsigned char>  *lmsg;  /* for long (sysex) msg */
    };
};

struct SysDep::midiin_t {
    int  devNum;
    MIDIPortRef  inPort;
    MIDIEndpointRef  src;
    std::queue<midiin_buffer_elm>  inputBuffer;
    std::vector<unsigned char> *sysexData; /* non-NULL while receiving a sysex msg */
    UInt64  sysexTimeStamp;
    bool deviceClosed;
};

} // namespace
