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
#include "sysdepGeneric.cpp"
#include <sys/cygwin.h>
#endif

#include "sysdep.h"
#include "takterror.h"
#include <signal.h>
#include <list>
#include <vector>

using namespace Takt;
using namespace std;

#define ISYSEX_BUFFER_LENGTH  256
#define NUM_ISYSEX_BUFFERS    16

DWORD  win32startTime;
static SysDep::mutex_t ibufMutex;
static SysDep::cond_t  ibufCond;
static bool terminateRequest;
static SysDep::sighandler_t winSigIntHandler;

/* list of all midi-input handlers */
static list<SysDep::midiin_handle_t> midiInList; 

static vector<LPMIDIHDR>  midiHdrTrash;

static BOOL WINAPI win_ctrl_handler(DWORD type)
{
    if( type == CTRL_C_EVENT || type == CTRL_BREAK_EVENT ) {
        winSigIntHandler(SIGINT);
    }
    return FALSE;
}

void SysDep::initialize(SysDep::sighandler_t
			(*_pyos_setsig)(int, SysDep::sighandler_t))
{
    TIMECAPS tc;
    
#ifdef __CYGWIN__
    initialize_generic(_pyos_setsig);
#endif

    timeBeginPeriod(1);
    win32startTime = timeGetTime();

    mutex_init(&ibufMutex);
    cond_init(&ibufCond);
}

#ifndef __CYGWIN__

void SysDep::set_signal_handler(sighandler_t handler)
{
    winSigIntHandler = handler;
    SetConsoleCtrlHandler((PHANDLER_ROUTINE) win_ctrl_handler, TRUE);
}

void SysDep::resume_signal_handler()
{
    SetConsoleCtrlHandler((PHANDLER_ROUTINE) win_ctrl_handler, FALSE);
}

static DWORD WINAPI threadFunc(LPVOID argArray)
{
    LPVOID funcPtr = ((LPVOID *)argArray)[0];
    LPVOID arg = ((LPVOID *)argArray)[1];
    ((void (*)(void *)) funcPtr) (arg);
    free(argArray);
    return 0;
}

bool SysDep::create_thread(thread_t &thread, void (*func)(void *), void *arg)
{
    LPVOID *argArray = (LPVOID *) malloc(sizeof(LPVOID) * 2);
    if( !argArray )  Error::no_memory();
    argArray[0] = (LPVOID) func;
    argArray[1] = (LPVOID) arg;
    thread.hnd = CreateThread(NULL, 0, threadFunc, argArray, 0, NULL);
#ifdef SYSDEP_WIN32_DEBUG
    fprintf(stderr, "thread %p created\n", thread.hnd);
#endif
    return thread.hnd != NULL;
}

void SysDep::join_thread(thread_t thread)
{
#ifdef SYSDEP_WIN32_DEBUG
    fprintf(stderr, "thread %p join -- waiting\n", thread.hnd);
#endif
    WaitForSingleObject(thread.hnd, INFINITE);
    CloseHandle(thread.hnd);
#ifdef SYSDEP_WIN32_DEBUG
    fprintf(stderr, "thread %p join -- done.\n", thread.hnd);
#endif
}

void SysDep::raise_thread_priority()
{
    if( SetThreadPriority(GetCurrentThread(),
                          THREAD_PRIORITY_TIME_CRITICAL) == 0 ) {
        fprintf(stderr, "Warning: Win32 SetThreadPriority failed (err=%d)\n",
		GetLastError());
    }
}

void SysDep::cond_init(cond_t *cond) 
{
    /* create an auto-reset Win32 event */
    cond->hnd = CreateEvent(NULL, FALSE, FALSE, NULL);
    if( !cond->hnd ) {
	fprintf(stderr, "Win32 event creation failed\n");
	exit(1);
    }

    cond->waiting = false;
}

void SysDep::cond_wait(cond_t *cond, mutex_t *mutex) 
{
#ifdef SYSDEP_WIN32_DEBUG
    fprintf(stderr, "cond_wait(%p) -- waiting\n", cond);
#endif
    /* Since we cond_signal() is implemented with SetEvent(), 
       it is safe to make unlock and wait not atomic. */
    cond->waiting = true;
    mutex_unlock(mutex);
    DWORD result = WaitForSingleObject(cond->hnd, INFINITE);
    if( result == WAIT_FAILED ) {
	fprintf(stderr, "midiio: cond_wait() failed\n");
    }
    cond->waiting = false;
    mutex_lock(mutex);
#ifdef SYSDEP_WIN32_DEBUG
    fprintf(stderr, "cond_wait(%p) -- done.\n", cond);
#endif
}

bool SysDep::cond_timedwait(cond_t *cond, mutex_t *mutex, double abstime) 
{
#ifdef SYSDEP_WIN32_DEBUG
    fprintf(stderr, "cond_timedwait(%p, %f) -- waiting\n", cond, abstime);
#endif
    cond->waiting = true;
    mutex_unlock(mutex);
    int  timeout = (int)abstime - (timeGetTime() - win32startTime);

#ifdef TIMEDWAIT_EXTRA_DELAY
    timeout += TIMEDWAIT_EXTRA_DELAY;
#endif

    if( timeout < 0 )  timeout = 0;
    DWORD result = WaitForSingleObject(cond->hnd, (DWORD) timeout);
    cond->waiting = false;
    mutex_lock(mutex);
#ifdef SYSDEP_WIN32_DEBUG
    fprintf(stderr, "cond_timedwait(%p, %f) -- done.\n", cond, abstime);
#endif
    if( result == WAIT_TIMEOUT ) return true;
    if( result == WAIT_FAILED ) {
	fprintf(stderr, "midiio: cond_timedwait() failed\n");
    }
    return false;
}

void SysDep::cond_signal(cond_t *cond) 
{
#ifdef SYSDEP_WIN32_DEBUG
    fprintf(stderr, "cond_signal(%p) (waiting=%d)\n", cond, cond->waiting);
#endif
    if( cond->waiting ) {
	/* When SetEvent() is called twice during the execution of
	   WaitForSingleObject(), it seems that the second event is queued,
	   i.e., the next call of WaitForSingleObject() returns immediately.
	   To avoid calling SetEvent() more than once, we clear 'waiting'. */
	cond->waiting = false;
	SetEvent(cond->hnd);
    }
}

#endif /* __CYGWIN__ */

/*
 * MIDI output
 */

/* Wait until the previously-queued system-exclusive message is transmitted, 
   and free the buffer for it */
static void wait_for_sysex_done(SysDep::midiout_handle_t midiOut)
{
    if( midiOut->sysexMidiHdr != NULL ) {
	WaitForSingleObject(midiOut->sysexDoneEvent, INFINITE);

	/* free sysex buffer */
	midiOutUnprepareHeader(midiOut->hMidiOut,
			       midiOut->sysexMidiHdr, sizeof(MIDIHDR));
	free(midiOut->sysexMidiHdr->lpData);
	free(midiOut->sysexMidiHdr);
	midiOut->sysexMidiHdr = NULL;
    }
}

static void CALLBACK midiOutHandler(HMIDIOUT hmo, UINT wMsg, 
				    DWORD_PTR dwInstance,
				    DWORD_PTR dwParam1, DWORD_PTR dwParam2)
{
    if( wMsg == MOM_DONE ) {
	SetEvent(((SysDep::midiout_handle_t) dwInstance)->sysexDoneEvent);
    }
}

static string devNameString(LPSTR p) { return p; }
static string devNameString(LPCWSTR p) { 
    char buf[128];
    if( WideCharToMultiByte(CP_UTF8, 0, p, -1, 
			    buf, sizeof(buf), NULL, NULL) == 0 ) {
	return "*String Conversion Error*";
    }
    return buf;
}

string SysDep::midiout_get_dev_name(int devNum)
{
    MIDIOUTCAPS  mc;
    if( midiOutGetDevCaps(devNum == 0 ? MIDI_MAPPER : devNum-1,
			  &mc, sizeof(mc)) == MMSYSERR_NOERROR ) {
	return devNameString(mc.szPname);
    } else {
	return "*Invalid device*";
    }
}

int SysDep::midiout_get_default_dev()
{
    return midiout_get_num_devs() > 0 ? 0 : -1;
}

SysDep::midiout_handle_t SysDep::midiout_open(int devNum)
{
    midiout_handle_t  midiOut;

    if( devNum < 0 || devNum >= midiout_get_num_devs() ) {
	return NULL;
    }

    midiOut = new midiout_t();

    if( midiOutOpen(&midiOut->hMidiOut, 
		    devNum == 0 ? MIDI_MAPPER : devNum-1,
		    (DWORD_PTR)midiOutHandler, 
		    (DWORD_PTR)midiOut, CALLBACK_FUNCTION) != MMSYSERR_NOERROR ) {
	delete midiOut;
	return NULL;
    }

    if( !(midiOut->sysexDoneEvent = CreateEvent(NULL, FALSE, FALSE, NULL)) ) {
	midiOutClose(midiOut->hMidiOut);
	delete midiOut;
	return NULL;
    }

    midiOut->sysexMidiHdr = NULL;

    return midiOut;
}

void SysDep::midiout_close(midiout_handle_t midiOut)
{
    midiOutReset(midiOut->hMidiOut);
    wait_for_sysex_done(midiOut);
    midiOutClose(midiOut->hMidiOut);
    CloseHandle(midiOut->sysexDoneEvent);
    delete midiOut;
}

void SysDep::midi_send(midiout_handle_t midiOut, const midimsg_t *m)
{
    wait_for_sysex_done(midiOut);

    if( !m->isSysEx ) {
	DWORD d = m->msg[0] | (m->msg[1] << 8);
	if( m->msg.size() >= 2 )  d |= m->msg[2] << 16;
	midiOutShortMsg(midiOut->hMidiOut, d);
    } else {
	MIDIHDR  *mhp;
	
	/* allocate sysex buffer */
	if( !(mhp = (MIDIHDR *) malloc(sizeof(MIDIHDR))) )
	    Error::no_memory();
	if( !(mhp->lpData = (LPSTR) malloc(m->msg.size())) )
	    Error::no_memory();
	for( int i = 0; i < m->msg.size(); i++ ) mhp->lpData[i] = m->msg[i];
	mhp->dwBufferLength = (DWORD)m->msg.size();
	mhp->dwFlags = 0;
	midiOutPrepareHeader(midiOut->hMidiOut, mhp, sizeof(MIDIHDR));
	midiOut->sysexMidiHdr = mhp;
	midiOutLongMsg(midiOut->hMidiOut, mhp, sizeof(MIDIHDR));
    }
}

/*
 * MIDI input
 */
static void CALLBACK midiInHandler(HMIDIIN hmi, UINT wMsg, 
				   DWORD_PTR dwInstance,
				   DWORD_PTR dwParam1, DWORD_PTR timeStamp)
{
    SysDep::midiin_handle_t midiIn = (SysDep::midiin_handle_t) dwInstance;
    LPMIDIHDR  mhp = (LPMIDIHDR) dwParam1;

    switch(wMsg) {
    case MIM_DATA:
	if( (dwParam1 & 0xff) < 0xf0 ) {  /* ignore system messages */
	    SysDep::mutex_lock(&ibufMutex);
	    midiIn->inputBuffer.push(midiin_buffer_elm(timeStamp, 
						       true, (DWORD)dwParam1));
	    SysDep::mutex_unlock(&ibufMutex);
	    SysDep::cond_signal(&ibufCond);
	}
	break;

    case MIM_LONGDATA:
	if( mhp->dwBytesRecorded == 0 ) {
	    /* buffer thrown by midiInReset() in midiin_close() */
	    SysDep::mutex_lock(&ibufMutex);
	    midiHdrTrash.push_back(mhp);
	    SysDep::mutex_unlock(&ibufMutex);
	} else {
	    SysDep::mutex_lock(&ibufMutex);
	    midiIn->inputBuffer.push(midiin_buffer_elm(timeStamp, false, mhp));
	    SysDep::mutex_unlock(&ibufMutex);
	    SysDep::cond_signal(&ibufCond);
	}
	break;

    case MIM_OPEN:
    case MIM_CLOSE:
    case MIM_MOREDATA:
    case MIM_ERROR:
    case MIM_LONGERROR:
	/* ignore it */
	break;
    }
} 

string SysDep::midiin_get_dev_name(int devNum)
{
    MIDIINCAPS  mc;
    if( midiInGetDevCaps(devNum, &mc, sizeof(mc)) == MMSYSERR_NOERROR ) {
	return devNameString(mc.szPname);
    } else {
	return "*Invalid device*";
    }
}

int SysDep::midiin_get_default_dev()
{
    return midiin_get_num_devs() > 0 ? 0 : -1;
}

SysDep::midiin_handle_t SysDep::midiin_open(int devNum)
{
    midiin_handle_t  midiIn;

    if( devNum < 0 || devNum >= midiin_get_num_devs() ) {
	return NULL;
    }

    midiIn = new midiin_t();
    midiIn->devNum = devNum;

    /* Because some MIDI drivers receive MIDI messages before the driver is 
       opened and keep them in the queue, we need to clear the queue. */
    midiInOpen(&midiIn->hMidiIn, devNum, 0, 0, CALLBACK_NULL);
    midiInStart(midiIn->hMidiIn);
    midiInReset(midiIn->hMidiIn);
    midiInClose(midiIn->hMidiIn);

    if( midiInOpen(&midiIn->hMidiIn, devNum, (DWORD_PTR)midiInHandler, 
		    (DWORD_PTR)midiIn, CALLBACK_FUNCTION) != MMSYSERR_NOERROR ) {
	delete midiIn;
	return NULL;
    }

    /* register buffers for receiving sysex messages */
    for( int i = 0; i < NUM_ISYSEX_BUFFERS; i++ ) {
	MIDIHDR *mhp;
	
	if( !(mhp = (MIDIHDR *) malloc(sizeof(MIDIHDR))) ||
	    !(mhp->lpData = (LPSTR) malloc(ISYSEX_BUFFER_LENGTH)) ) {
	    Error::no_memory();
	}

	mhp->dwBufferLength = ISYSEX_BUFFER_LENGTH;
	mhp->dwFlags = 0;
	mhp->dwBytesRecorded = 0; /* just for sure */
	midiInPrepareHeader(midiIn->hMidiIn, mhp, sizeof(MIDIHDR));
	midiInAddBuffer(midiIn->hMidiIn, mhp, sizeof(MIDIHDR));
    }

    midiIn->midiStartTime = SysDep::get_time();
    midiInStart(midiIn->hMidiIn);

    mutex_lock(&ibufMutex);
    midiInList.push_back(midiIn);
    mutex_unlock(&ibufMutex);

    return midiIn;
}

void SysDep::midiin_close(midiin_handle_t midiIn)
{
    midiInStop(midiIn->hMidiIn);
    midiInReset(midiIn->hMidiIn); /* move all the registred sysex buffers
				     to Trash */

    SysDep::mutex_lock(&ibufMutex);
    vector<LPMIDIHDR>::iterator i;
    for( i = midiHdrTrash.begin(); i != midiHdrTrash.end(); i++ ) {
	midiInUnprepareHeader(midiIn->hMidiIn, *i, sizeof(MIDIHDR));
	free((char *) (*i)->lpData);
	free((char *) *i);
    }
    midiHdrTrash.clear();
    midiInList.remove(midiIn);
    SysDep::mutex_unlock(&ibufMutex);

    midiInClose(midiIn->hMidiIn);
    delete midiIn;
}

int SysDep::midi_recv(midiin_handle_t midiIn, midimsg_t *m, double *timeStamp)
{
    midiin_buffer_elm  elm;

    mutex_lock(&ibufMutex);
    if( midiIn->inputBuffer.empty() ) {
	mutex_unlock(&ibufMutex);
	return 1; // error (no messages exist in the input buffer)
    }
    elm = midiIn->inputBuffer.front();
    midiIn->inputBuffer.pop();
    mutex_unlock(&ibufMutex);

    *timeStamp = (DWORD)elm.timeStamp + midiIn->midiStartTime;

    if( elm.isShortMsg ) {
	m->msg.resize(3);
	m->msg[0] = elm.msg & 0xff;
	m->msg[1] = (elm.msg >> 8) & 0xff;
	m->msg[2] = (elm.msg >> 16) & 0xff;
	m->isSysEx = false;
    } else {
	LPMIDIHDR  mhp = elm.midiHdr;
	int  len = mhp->dwBytesRecorded;

	m->msg.resize(len);
	for( int i = 0; i < len; i++ ) m->msg[i] = mhp->lpData[i];
	m->isSysEx = true;

	/* recycle the system exclusive buffer */
	midiInUnprepareHeader(midiIn->hMidiIn, mhp, sizeof(MIDIHDR));
	mhp->dwFlags = 0;
	mhp->dwBytesRecorded = 0; /* Without this, new messages are
				     concatenated to the previous message.*/
	midiInPrepareHeader(midiIn->hMidiIn, mhp, sizeof(MIDIHDR));
	midiInAddBuffer(midiIn->hMidiIn, mhp, sizeof(MIDIHDR));
    }

    return 0;
}

/*
 * device wait
 */
SysDep::device_wait_rtn
SysDep::device_wait(int &devNum)
{
    mutex_lock(&ibufMutex);
    for(;;) {
	for( list<midiin_handle_t>::const_iterator i = midiInList.begin(); 
	     i != midiInList.end(); i++ ) {
	    if( (*i)->inputBuffer.size() > 0 ) {
		mutex_unlock(&ibufMutex);
		devNum = (*i)->devNum;
		return MIDIIN;
	    }
	}

	if( terminateRequest ) {
	    terminateRequest = false;
	    mutex_unlock(&ibufMutex);
	    return TERMINATED;
	}
	
	cond_wait(&ibufCond, &ibufMutex);
    }
}

void SysDep::terminate_device_wait()
{
    mutex_lock(&ibufMutex);
    terminateRequest = true;
    mutex_unlock(&ibufMutex);
    SysDep::cond_signal(&ibufCond);

    timeEndPeriod(1);
}
