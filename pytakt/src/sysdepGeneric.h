/* -*- C++ -*- 
 * Realtime MIDI I/O Library for Pytakt
 *
 *  Class for operating-system dependent routines (generic, without MIDI I/O)
 *
 *  This code was originally a part of Takt, an interpreter for the Takt music 
 *  programming language.
 */

/* Copyright (C) 2014, 2025  Satoshi Nishimura */

#include <sys/types.h>
#include <sys/time.h>
#include <pthread.h>

extern double sysDepStartTime;

namespace Takt {

struct SysDep::mutex_t {
    pthread_mutex_t  m;
};

struct SysDep::cond_t {
    pthread_cond_t  c;
};

struct SysDep::thread_t {
    pthread_t  t;
};

inline void SysDep::mutex_init(mutex_t *mutex) {
    pthread_mutex_init(&mutex->m, NULL);
}

inline void SysDep::mutex_lock(mutex_t *mutex) {
    pthread_mutex_lock(&mutex->m);
}

inline void SysDep::mutex_unlock(mutex_t *mutex) {
    pthread_mutex_unlock(&mutex->m);
}

inline double SysDep::get_time() {
    struct timeval  tm;
    gettimeofday(&tm, NULL);
#ifdef QUANTIZE_TO_MSECS
    return (tm.tv_sec * 1e3 + (tm.tv_usec / 1000)) - sysDepStartTime;
#else
    return (tm.tv_sec * 1e3 + tm.tv_usec * 1e-3) - sysDepStartTime;
#endif
}

inline void SysDep::cond_init(cond_t *cond) {
    pthread_cond_init(&cond->c, NULL);
}

inline void SysDep::cond_signal(cond_t *cond) {
    pthread_cond_signal(&cond->c);
}

#ifndef _SYSDEP_PTHREAD_ONLY

/* No MIDI I/F */
struct SysDep::midiout_t {};
struct SysDep::midiin_t {};

inline int SysDep::midiout_get_num_devs() { return 0; }
inline std::string SysDep::midiout_get_dev_name(int devNum) { return ""; }
inline int SysDep::midiout_get_default_dev() { return -1; }
inline SysDep::midiout_handle_t SysDep::midiout_open(int devNum) { 
    return NULL; 
}
inline void SysDep::midiout_close(midiout_handle_t midiOut) {}
inline void SysDep::midi_send(midiout_handle_t midiOut, const midimsg_t *m) {}

inline int SysDep::midiin_get_num_devs() { return 0; }
inline std::string SysDep::midiin_get_dev_name(int devNum) { return ""; }
inline int SysDep::midiin_get_default_dev() { return -1; }
inline SysDep::midiin_handle_t SysDep::midiin_open(int devNum) {
    return NULL;
}
inline void SysDep::midiin_close(midiin_handle_t midiIn) {}
inline int SysDep::midi_recv(midiin_handle_t midiIn, 
		             midimsg_t *m, double *timeStamp) { return 1; }

#endif /* _SYSDEP_PTHREAD_ONLY */

} // namespace
