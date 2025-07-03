/* -*- C++ -*-
 * Realtime MIDI I/O Library for Pytakt
 *
 *  Class for MIDI input (device input manager)
 *
 *  This code was originally a part of Takt, an interpreter for the Takt music 
 *  programming language.
 */

/* Copyright (C) 2014, 2025  Satoshi Nishimura */

#include "_cstddefs.h"
#include "midiin.h"
#include "midiout.h"
#include <vector>
#include <deque>

using namespace Takt;
using namespace std;

static vector<SysDep::midiin_handle_t> midiInHandles;
static SysDep::thread_t midiInThread;
static SysDep::cond_t midiInCond;
static SysDep::mutex_t midiInMutex;
bool  receiving = false;

/* FIFO queue of time-stamped MIDI messages */
struct mi_queue_elm {
    int devNum; 
    double time; // time in ticks
    message_t msg;
    int tk;      // track number

    mi_queue_elm(int devNum, double time, const message_t& msg, int tk)
	: devNum(devNum), time(time), msg(msg), tk(tk) {}
};
static deque<mi_queue_elm *> miEventQueue;

static void midiInThreadBody(void *arg)
{
    for(;;) {
	int devNum;
	SysDep::device_wait_rtn dwrtn = SysDep::device_wait(devNum);
	if( dwrtn == SysDep::MIDIIN ) {
	    SysDep::midimsg_t midimsg;
	    double tstamp;
	    if( SysDep::midi_recv(midiInHandles[devNum],
				  &midimsg, &tstamp) == 0 ) {
		double ticks = MidiOut::msecsToTicks(tstamp);
		if( midimsg.isSysEx )
		    midimsg.msg.insert(midimsg.msg.begin(), 0xf0);
		MidiIn::enqueue(devNum, ticks, 0, midimsg.msg);
	    } else {
		//fprintf(stderr, "Error while receiving MIDI messages\n");
	    }
	} else { // dwrtn == SysDep::TERMINATED
	    break;
	}
    }
}

void MidiIn::startup()
{
    SysDep::cond_init(&midiInCond);
    SysDep::mutex_init(&midiInMutex);

    if( ! SysDep::create_thread(midiInThread, midiInThreadBody) ) {
	fprintf(stderr, "MIDI-input thread creation failed\n");
	exit(1);
    }
}

bool MidiIn::openDevice(int devNum)
{
    if( devNum < 0 ) return false;
    if( devNum >= SysDep::midiin_get_num_devs() )  return true;

    bool err = false;
    SysDep::mutex_lock(&midiInMutex);
    if( midiInHandles.size() <= devNum ) { 
	midiInHandles.resize(devNum + 1, NULL);
    }
    if( !midiInHandles[devNum] ) {
	if( ! (midiInHandles[devNum] = SysDep::midiin_open(devNum)) ) {
	    err = true;
	}
    }
    SysDep::mutex_unlock(&midiInMutex);
    return err;
}

void MidiIn::closeDevice(int devNum)
{
    if( devNum < 0 ) return;
    SysDep::mutex_lock(&midiInMutex);
    if( devNum < midiInHandles.size() && midiInHandles[devNum] ) {
	SysDep::midiin_close(midiInHandles[devNum]);
	midiInHandles[devNum] = NULL;
    }

    /* remove messages in miEventQueue */
    deque<mi_queue_elm *> queueCopy = miEventQueue;
    miEventQueue.clear();
    for( deque<mi_queue_elm *>::iterator i = queueCopy.begin();
	 i != queueCopy.end(); i++ ) {
	if( (*i)->devNum != devNum ) miEventQueue.push_back(*i);
	else delete (*i);
    }
    SysDep::mutex_unlock(&midiInMutex);
}

bool MidiIn::isOpenedDevice(int devNum)
{
    if( devNum < 0 ) return true;
    SysDep::mutex_lock(&midiInMutex);
    bool result = devNum < midiInHandles.size() && midiInHandles[devNum];
    SysDep::mutex_unlock(&midiInMutex);
    return result;
}

static void midiInSigIntHandler(int signum)
{
    MidiIn::interrupt();
}

bool MidiIn::receiveReady()
{
    bool rtn;
    SysDep::mutex_lock(&midiInMutex);
    rtn = !miEventQueue.empty();
    SysDep::mutex_unlock(&midiInMutex);
    return rtn;
}

void MidiIn::receiveMessage(int &devNum, double &ticks, int &tk, message_t& msg)
{
    SysDep::set_signal_handler(midiInSigIntHandler);
    SysDep::mutex_lock(&midiInMutex);
    receiving = true;
    while( miEventQueue.empty() && receiving ) {
	SysDep::cond_wait(&midiInCond, &midiInMutex);
    } 
    if( receiving ) {
	receiving = false;
	devNum = miEventQueue.front()->devNum;
	ticks = miEventQueue.front()->time;
	tk = miEventQueue.front()->tk;
	msg = miEventQueue.front()->msg;
	delete miEventQueue.front();
	miEventQueue.pop_front();
    } else {
	/* interrupted while receiving */
	devNum = DEV_DUMMY;
	ticks = 0;
	tk = 0;
	msg.clear();
    }
    SysDep::mutex_unlock(&midiInMutex);
    SysDep::resume_signal_handler();
}

void MidiIn::enqueue(int devNum, double ticks, int tk, const message_t& msg)
{
    mi_queue_elm *q = new mi_queue_elm(devNum, ticks, msg, tk);
    SysDep::mutex_lock(&midiInMutex);
    miEventQueue.push_back(q);
    SysDep::cond_signal(&midiInCond);
    SysDep::mutex_unlock(&midiInMutex);
}

void MidiIn::interrupt() 
{
    SysDep::mutex_lock(&midiInMutex);
    for( int i = 0; i < miEventQueue.size(); i++ ) {
	delete miEventQueue[i];
    }
    miEventQueue.clear();
    receiving = false;
    SysDep::cond_signal(&midiInCond);
    SysDep::mutex_unlock(&midiInMutex);
}

void MidiIn::shutdown()
{
    for( int i = 0; i < midiInHandles.size(); i++ ) {
	if( midiInHandles[i] ) {
	    SysDep::midiin_close(midiInHandles[i]);
	}
    }
    SysDep::terminate_device_wait();
    SysDep::join_thread(midiInThread);
}
