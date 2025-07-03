/* -*- C++ -*- 
 * Realtime MIDI I/O Library for Pytakt
 *
 *  Class for operating-system dependent routines (generic, without MIDI I/O)
 *
 *  This code was originally a part of Takt, an interpreter for the Takt music 
 *  programming language.
 */

/* Copyright (C) 2014, 2025  Satoshi Nishimura */

#include "sysdep.h"
#include <errno.h>
#include <signal.h>

using namespace Takt;

double sysDepStartTime;

static pthread_mutex_t waitMutex;
static pthread_cond_t waitCond;
static bool waitTerminated = false;

static pthread_t mainThread, signalThread;
static SysDep::sighandler_t sigIntHandler, originalSigIntHandler;
static SysDep::sighandler_t (*pyos_setsig)(int, SysDep::sighandler_t);

/* Since pthread_mutex_lock or pthread_cond_signal cannot be used in SIGINT 
   handler, a thread that executes sigwait() is created. */
static void* signalThreadBody(void *arg)
{
    sigset_t mask;
    sigemptyset(&mask);
    sigaddset(&mask, SIGUSR1);

    while(1) {
	int sig;
	sigwait(&mask, &sig);
	if( sigIntHandler )  sigIntHandler(SIGINT);
    }
}

static void sysdepSigIntHandler(int signum)
{
    if( pthread_equal(pthread_self(), mainThread) ) {
	pthread_kill(signalThread, SIGUSR1);
	if( originalSigIntHandler == SIG_DFL ) {
	    pyos_setsig(SIGINT, originalSigIntHandler);
	    raise(SIGINT);  // it should exit the program
	} else if( originalSigIntHandler != SIG_IGN ) {
	    originalSigIntHandler(signum);
	}
    }
}

static void emptyHandler(int signum) {}

static void initialize_generic(SysDep::sighandler_t
			       (*_pyos_setsig)(int, SysDep::sighandler_t))
{
    pthread_mutex_init(&waitMutex, NULL);
    pthread_cond_init(&waitCond, NULL);

    sysDepStartTime = 0;
    sysDepStartTime = SysDep::get_time();

    mainThread = pthread_self();
    _pyos_setsig(SIGUSR1, emptyHandler);
    pyos_setsig = _pyos_setsig;
    if( pthread_create(&signalThread, NULL, signalThreadBody, NULL) ) {
	fprintf(stderr, "midiio: pthread_create() failed\n");
    } else {
	pthread_detach(signalThread);
    }
}

void SysDep::set_signal_handler(sighandler_t handler)
{
    sigIntHandler = handler;
    originalSigIntHandler = pyos_setsig(SIGINT, sysdepSigIntHandler); 
}

void SysDep::resume_signal_handler()
{
    pyos_setsig(SIGINT, originalSigIntHandler);
}

bool
SysDep::create_thread(thread_t &thread, void (*func)(void *), void *arg)
{
    return pthread_create(&thread.t, NULL, 
			  (void *(*)(void *)) func, arg) == 0;
}

void SysDep::join_thread(SysDep::thread_t thread)
{
    pthread_join(thread.t, NULL);
}

void SysDep::raise_thread_priority()
{
#ifndef SKIP_RAISE_THREAD_PRIORITY
    struct sched_param  param;
    param.sched_priority = sched_get_priority_max(SCHED_RR);
    pthread_setschedparam(pthread_self(), SCHED_RR, &param);
#endif
}

void SysDep::cond_wait(cond_t *cond, mutex_t *mutex)
{
    if( pthread_cond_wait(&cond->c, &mutex->m) ) {
	fprintf(stderr, "midiio: pthread_cond_wait() failed\n");
    }
}

bool SysDep::cond_timedwait(cond_t *cond, mutex_t *mutex, double abstime)
{
    struct timespec ts;
    double  t = abstime + sysDepStartTime;

#ifdef TIMEDWAIT_EXTRA_DELAY
    /* In some platforms, it is better to add a small value to the timeout 
       in order to mitigate the event disorder problem between Midi-in and
       loopback devices. */
    t += TIMEDWAIT_EXTRA_DELAY;
#endif

    ts.tv_sec = t / 1e3;
#ifdef QUANTIZE_TO_MSECS
    ts.tv_nsec = (int)(t - ts.tv_sec * 1e3) * 1000000;
#else
    ts.tv_nsec = (t - ts.tv_sec * 1e3) * 1e6;
#endif
    int rtn = pthread_cond_timedwait(&cond->c, &mutex->m, &ts);
    if( rtn == ETIMEDOUT ) return true;
    if( rtn != 0 ) {
	fprintf(stderr, "midiio: pthread_cond_timedwait() failed\n");
    }
    return false;
}

#ifndef _SYSDEP_PTHREAD_ONLY

void SysDep::initialize(SysDep::sighandler_t
			(*_pyos_setsig)(int, SysDep::sighandler_t))
{
    initialize_generic(_pyos_setsig);
}

SysDep::device_wait_rtn 
SysDep::device_wait(int &devNum)
{
    pthread_mutex_lock(&waitMutex);
    while( ! waitTerminated ) {
	pthread_cond_wait(&waitCond, &waitMutex);
    }
    waitTerminated = false;
    pthread_mutex_unlock(&waitMutex);
    return TERMINATED;
}

void SysDep::terminate_device_wait()
{
    pthread_mutex_lock(&waitMutex);
    waitTerminated = true;
    pthread_mutex_unlock(&waitMutex);
    pthread_cond_signal(&waitCond);
}

#endif /* _SYSDEP_PTHREAD_ONLY */
