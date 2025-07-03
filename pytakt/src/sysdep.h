/* -*- C++ -*- 
 * Realtime MIDI I/O Library for Pytakt
 *
 *  Class for operating-system dependent routines
 *
 *  This code was originally a part of Takt, an interpreter for the Takt music 
 *  programming language.
 */

/* Copyright (C) 2014, 2025  Satoshi Nishimura */

#ifndef _SysDep_
#define _SysDep_

#include "_cstddefs.h"
#include <vector>
#include <string>

namespace Takt {
class SysDep {
public:
    struct mutex_t;
    struct cond_t;
    struct thread_t;

    struct midimsg_t {
	std::vector<unsigned char>  msg;  /* MIDI message */
	bool isSysEx; /* true if msg[] contains a (complete or part of) 
			 system-exclusive message */
	midimsg_t() {}
	midimsg_t(bool isSysEx) : isSysEx(isSysEx) {}
	midimsg_t(bool isSysEx, int sz) : isSysEx(isSysEx), msg(sz) {}
    };
    struct midiout_t;
    struct midiin_t;
    typedef midiout_t *midiout_handle_t;
    typedef midiin_t *midiin_handle_t;
    typedef void (*sighandler_t)(int);

public:
    /* Initialization at the program start 
       - called from the console thread */
    static void initialize(sighandler_t (*pyos_setsig)(int, sighandler_t));

    /* Set a SIGINT handler */
    static void set_signal_handler(sighandler_t handler);

    /* Resume the SIGINT handler to the one when set_signal_handler is called 
       last */ 
    static void resume_signal_handler();

    /* Create an operating-system thread 
       - returns false if failed */
    static bool create_thread(thread_t &thread, void (*func)(void *), 
			      void *arg = NULL);

    /* Wait for the completion of the created thread */
    static void join_thread(thread_t thread);

    /* Enhance scheduling priority of the current thread */
    static void raise_thread_priority();

    /* mutex operations */
    static void mutex_init(mutex_t *mutex);
    static void mutex_lock(mutex_t *mutex);
    static void mutex_unlock(mutex_t *mutex);

    /* get the current time (in milliseconds) */
    static double get_time();

    /* condition variable operations */
    static void cond_init(cond_t *cond);
    static void cond_wait(cond_t *cond, mutex_t *mutex);
    /* cond_timedwait() returns true when the timeout is reached. 
       It is important to ensure that get_time() >= the value of `abstime'
       always holds (in spite of rounding errors) when cond_timedwait()
       returns with time-out. */
    static bool cond_timedwait(cond_t *cond, mutex_t *mutex, double abstime);
    /* In cond_signal(), it is ok to assume that the number of threads 
       waiting for the signal is at most one. */
    static void cond_signal(cond_t *cond);

    /* 
     * MIDI output 
     */
    /* get the number of output devices */
    static int midiout_get_num_devs();

    /* get the name of the output device specified by devNum
       - The device number starts from 0, while device 0 means 
         the default device */
    static std::string midiout_get_dev_name(int devNum);

    /* get the device number of the default output device
       - return -1 if no devices are available */
    static int midiout_get_default_dev();

    /* open a MIDI output device 
       - returns NULL on error 
       - called from the interpreter thread */
    static midiout_handle_t midiout_open(int devNum);

    /* close a MIDI output device 
       - called from the MIDIOUT thread */
    static void midiout_close(midiout_handle_t midiOut);
    
    /* send a MIDI message to a MIDI output device 
       - called from the MIDIOUT thread */
    static void midi_send(midiout_handle_t midiOut, const midimsg_t *m);

    /* 
     * MIDI input
     */
    /* get the number of input devices */
    static int midiin_get_num_devs();

    /* get the name of the input device specified by devNum */
    static std::string midiin_get_dev_name(int devNum);

    /* get the device number of the default input device
       - return -1 if no devices are available */
    static int midiin_get_default_dev();

    /* open a MIDI input device 
       - returns NULL on error 
       - called from the interpreter thread */
    static midiin_handle_t midiin_open(int devNum);

    /* close a MIDI input device 
       - called from the console thread */
    static void midiin_close(midiin_handle_t midiIn);
    
    /* receive a MIDI message from a MIDI input device
       - should be called after device_wait() returns with MIDIIN
       - returns non-zero on error 
       - called from the MIDIIN thread */
    static int midi_recv(midiin_handle_t midiIn, 
			 midimsg_t *m, double *timeStamp);

    /* 
     * Wait for the arrival of a MIDI message
     *   - returns a code indicating the type of the event
     *   - the device number of the ready device is stored to 'devNum'
     *   - called from the MIDIIN thread
     */
    enum device_wait_rtn {
	TERMINATED,
	MIDIIN,
    };
    static device_wait_rtn device_wait(int &devNum);

    /*
     * Make device_wait() return immediately with the value TERMINATED
     *   - called by the interpreter thread 
     */
    static void terminate_device_wait();
};
}

#if (defined(_MSC_VER) || defined(__CYGWIN__)) && !defined(USE_GENERIC)
#include "sysdepWin.h"
#elif defined(__APPLE__) && !defined(USE_GENERIC)
#include "sysdepMacOSX.h"
#elif defined(__linux__) && !defined(USE_GENERIC)
#include "sysdepLinux.h"
#else
#include "sysdepGeneric.h"
#endif

#endif
