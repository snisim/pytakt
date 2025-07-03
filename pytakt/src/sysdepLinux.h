/* -*- C++ -*- 
 * Realtime MIDI I/O Library for Pytakt
 *
 *  Class for operating-system dependent routines (for Linux ALSA)
 *
 *  This code was originally a part of Takt, an interpreter for the Takt music 
 *  programming language.
 */

/* Copyright (C) 2014, 2025  Satoshi Nishimura */

#define _SYSDEP_PTHREAD_ONLY
#include "sysdepGeneric.h"

#include <queue>
#include <vector>
#include <alsa/asoundlib.h>

namespace Takt {

struct SysDep::midiout_t {
    int  devNum;
    int  port;
};

struct SysDep::midiin_t {
    int  devNum;
};

} // namespace
