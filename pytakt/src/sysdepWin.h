/* -*- C++ -*- 
 * Realtime MIDI I/O Library for Pytakt
 *
 *  Class for operating-system dependent routines (for Windows)
 *
 *  This code was originally a part of Takt, an interpreter for the Takt music 
 *  programming language.
 */

/* Copyright (C) 2014, 2025  Satoshi Nishimura */

#ifdef __CYGWIN__
#define _SYSDEP_PTHREAD_ONLY
#include "sysdepGeneric.h"
#endif

#include <queue>

#include <windows.h>
#include <winuser.h>
#include <mmsystem.h>

extern DWORD  win32startTime;

namespace Takt {

#ifndef __CYGWIN__

struct SysDep::mutex_t {
    CRITICAL_SECTION  cs;
};

struct SysDep::cond_t {
    HANDLE  hnd;
    bool  waiting;
};

struct SysDep::thread_t {
    HANDLE  hnd;
};

inline void SysDep::mutex_init(mutex_t *mutex) {
    InitializeCriticalSection(&mutex->cs);
}

inline void SysDep::mutex_lock(mutex_t *mutex) {
    EnterCriticalSection(&mutex->cs);
}

inline void SysDep::mutex_unlock(mutex_t *mutex) {
    LeaveCriticalSection(&mutex->cs);
}

inline double SysDep::get_time() {
    return timeGetTime() - win32startTime;
}

#endif /* __CYGWIN__ */

struct SysDep::midiout_t {
    HMIDIOUT  hMidiOut;
    HANDLE   sysexDoneEvent;
    MIDIHDR  *sysexMidiHdr;  /* When this is non-NULL, a system-exclusive 
				message is being sent. */
};

struct midiin_buffer_elm {
    DWORD_PTR  timeStamp;
    bool  isShortMsg;
    union {
	DWORD  msg;   /* for short msg */
	LPMIDIHDR  midiHdr;  /* for long msg */
    };
    
    midiin_buffer_elm() {}
    midiin_buffer_elm(DWORD_PTR ts, bool ism, DWORD ms) {
	timeStamp = ts; isShortMsg = ism; msg = ms;
    }
    midiin_buffer_elm(DWORD_PTR ts, bool ism, LPMIDIHDR mh) {
	timeStamp = ts; isShortMsg = ism; midiHdr = mh;
    }
};

struct SysDep::midiin_t {
    HMIDIIN  hMidiIn;
    std::queue<midiin_buffer_elm>  inputBuffer;
    int devNum;
    double  midiStartTime;
};

inline int SysDep::midiout_get_num_devs() {
    int n = midiOutGetNumDevs();
    return n == 0 ? 0 : n + 1;  // number of devcies + MIDI MAPPER
}

inline int SysDep::midiin_get_num_devs() {
    return midiInGetNumDevs();
}

} // namespace
