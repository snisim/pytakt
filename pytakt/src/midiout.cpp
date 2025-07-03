/* -*- C++ -*- 
 * Realtime MIDI I/O Library for Pytakt
 *
 *  Class for real-time MIDI output (also maintains beat-second mapping)
 *
 *  This code was originally a part of Takt, an interpreter for the Takt music 
 *  programming language.
 */

/* Copyright (C) 2014, 2025  Satoshi Nishimura */

#include "_cstddefs.h"
#include "midiout.h"
#include "midiin.h"
#include "notemap.h"
#include <queue>
#include <cmath>
using namespace Takt;
using namespace std;

static vector<SysDep::midiout_handle_t> midiOutHandles;
static SysDep::thread_t midiOutThread;
static SysDep::mutex_t midiOutMutex;
static SysDep::cond_t midiOutCond;
static bool shutdownRequest, stopRequest, tempoScaleChangeRequest;
static vector<pair<int, int> > cancelRequests;

static double currentTempo; // current tempo in BPM
static double lastTempoChangeS; // time of the last tempo change in millisecs
static double lastTempoChangeT; // time of the last tempo change in ticks
static double tempoScale = 1.0;  // current tempo scale (possibly zero)
static double requestedTempoScale;
static bool retriggerNotes = true;
static int retriggerNotesChangeReq = 0;


/* priority queue of time-stamped MIDI messages */
struct mo_queue_elm {
    int devNum; 
    double time; // time in ticks
    int count;   // wrap-around counter necessary for stable sorting
    message_t msg;
    int tk;      // track number

    mo_queue_elm(int d, double t, int _tk) : devNum(d), time(t), tk(_tk) {
	static int currentCount;
	count = currentCount++;
    }
    static bool greater(const mo_queue_elm *e1, const mo_queue_elm *e2) {
	return (e1->time == e2->time ? (e1->count - e2->count) > 0 : 
		e1->time > e2->time);
    }
};
static vector<mo_queue_elm *> moEventQueue;

static NoteMap retriggerNoteMap, cancelNoteMap;


double MidiOut::ticksToMsecs(double ticks)
{
    SysDep::mutex_lock(&midiOutMutex);
    /* returns infinity if tempo is zero */
    double msecs = (ticks - lastTempoChangeT) * 125.0
 	           / (currentTempo * tempoScale) + lastTempoChangeS;
    SysDep::mutex_unlock(&midiOutMutex);
    return msecs;
}

double MidiOut::msecsToTicks(double msecs)
{
    SysDep::mutex_lock(&midiOutMutex);
    double ticks = (msecs - lastTempoChangeS) * currentTempo * tempoScale
	           / 125.0 + lastTempoChangeT;
    SysDep::mutex_unlock(&midiOutMutex);
    return ticks;
}

double MidiOut::getCurrentTempo()
{
    return currentTempo;
}

double MidiOut::getTempoScale()
{
    return tempoScale;
}

/* MIDIOUT thread: function called from cancelNoteMap.clearAndCall */
static void cancelFunc(int devNum, int tk, int ch, int n, int count)
{
    SysDep::midimsg_t m(false, 3);
    if( n == -1 ) {
	m.msg[0] = 0xb0 + ch;
	m.msg[1] = C_SUSTAIN;
	m.msg[2] = 0;
	SysDep::midi_send(midiOutHandles[devNum], &m);
    } else {
	for( int k = 0; k < count; k++ ) {
	    m.msg[0] = 0x90 + ch;
	    m.msg[1] = n;
	    m.msg[2] = 0;
	    SysDep::midi_send(midiOutHandles[devNum], &m);
	    if( retriggerNotes ) retriggerNoteMap.pop(devNum, 0, ch, n);
	}
    }
}

/* MIDIOUT thread: send all-notes-off and sustain-off messages for each channel
   of all the opening devices and clear the event queue and note maps */
static void doStopAll()
{
    SysDep::midimsg_t  midimsg(false, 3);

    for( int i = 0; i < midiOutHandles.size(); i++ ) {
	if( midiOutHandles[i] ) {
	    cancelNoteMap.clearAndCall(i, ALL_TRACKS, cancelFunc);
	    for( int ch = 0; ch < 16; ch++ ) {
		midimsg.msg[0] = 0xb0 + ch;
		midimsg.msg[1] = C_ALL_NOTES_OFF;
		midimsg.msg[2] = 0;
		SysDep::midi_send(midiOutHandles[i], &midimsg);
		midimsg.msg[1] = C_SUSTAIN;
		SysDep::midi_send(midiOutHandles[i], &midimsg);
		midimsg.msg[1] = C_ALL_SOUND_OFF;
		SysDep::midi_send(midiOutHandles[i], &midimsg);
	    }
	}
    }

    /* clear the event queue and the note map */
    for( int i = 0; i < moEventQueue.size(); i++ ) {
	delete moEventQueue[i];
    }
    moEventQueue.clear();
    retriggerNoteMap.clear();
    cancelNoteMap.clear();
}

/* MIDIOUT thread: cancel messages for particular devNum and tk */
static void doCancelMessages(int devNum, int tk)
{
    /* move the events deleted to the end part of moEventQueue */
    int i = 0, j = (int)moEventQueue.size() - 1;
    for(;;) {
	while( i <= j && !(moEventQueue[i]->devNum == devNum &&
			  (tk == ALL_TRACKS || moEventQueue[i]->tk == tk)) ) {
	    i++;
	}
	while( i <= j && (moEventQueue[j]->devNum == devNum &&
			 (tk == ALL_TRACKS || moEventQueue[j]->tk == tk)) ) {
	    j--;
	}
	if( i > j )  break;
	mo_queue_elm* tmp = moEventQueue[j];
	moEventQueue[j] = moEventQueue[i];
	moEventQueue[i] = tmp;
    }
    for( int k = i; k < moEventQueue.size(); k++ )  delete moEventQueue[k];
    moEventQueue.resize(i);
    make_heap(moEventQueue.begin(), moEventQueue.end(), mo_queue_elm::greater);

    if( devNum >= 0 && devNum < midiOutHandles.size() && 
	midiOutHandles[devNum] ) {
	cancelNoteMap.clearAndCall(devNum, tk, cancelFunc);
    }
}

/* MIDIOUT thread: send a MIDI message with optional retrigger processing */
static void midiOutSendMessage(int devNum, int tk, const SysDep::midimsg_t &m)
{
    int ch = m.msg[0] & 0xf;
    bool no_output = false;

    if( ((m.msg[0] & 0xf0) == 0x90 && m.msg[2] == 0) ||
	(m.msg[0] & 0xf0) == 0x80 ) { // note-off
	if( retriggerNotes &&
	    retriggerNoteMap.pop(devNum, 0, ch, m.msg[1]) >= 1 ) {
	    no_output = true;
	}
	cancelNoteMap.pop(devNum, tk, ch, m.msg[1]);
    } else if( (m.msg[0] & 0xf0) == 0x90 ) { // note-on 
	if( retriggerNotes &&
	    retriggerNoteMap.push(devNum, 0, ch, m.msg[1]) >= 1 ) {
	    SysDep::midimsg_t m_off = m;
	    m_off.msg[2] = 0;
	    SysDep::midi_send(midiOutHandles[devNum], &m_off);
	}
	cancelNoteMap.push(devNum, tk, ch, m.msg[1]);
    } else if( (m.msg[0] & 0xf0) == 0xb0 &&
	       (m.msg[1] == C_ALL_NOTES_OFF || m.msg[1] == C_ALL_SOUND_OFF) ) {
	if( retriggerNotes ) 
	    retriggerNoteMap.clear(devNum, 0, ch);
	/* cancelNoteMapの方はクリアしない。これは、all-notes-offを感知しない
	   シンセがあった場合に、cancelでnote-offが送られないと困るから */
    } else if( (m.msg[0] & 0xf0) == 0xb0 && m.msg[1] == C_SUSTAIN ) {
	if( m.msg[2] == 0 )
	    cancelNoteMap.pop(devNum, tk, ch, -1);
	else
	    cancelNoteMap.set(devNum, tk, ch, -1, 1);
    }
    
    if( !no_output ) SysDep::midi_send(midiOutHandles[devNum], &m);
}

/* MIDIOUT thread: main routine */
static void midiOutThreadBody(void *arg)
{
    SysDep::raise_thread_priority();

    SysDep::mutex_lock(&midiOutMutex);
    for(;;) {
	/* wait until the time of the queue's top comes, or a signal is 
	   sent by the main thread */
	bool tmout = false;
	double msecs, ticks;
	if( moEventQueue.empty() ) {
	    SysDep::cond_wait(&midiOutCond, &midiOutMutex);
	} else {
	    double tempo = currentTempo * tempoScale;
	    if( tempo <= 0 ) {
		SysDep::cond_wait(&midiOutCond, &midiOutMutex);
	    } else {
		ticks = moEventQueue[0]->time;
		if( isinf(ticks) && ticks > 0 ) {
		    SysDep::cond_wait(&midiOutCond, &midiOutMutex);
		} else {
		    if( isinf(ticks) )  ticks = 0;
		    msecs = (ticks - lastTempoChangeT) * 125 / tempo
      		        + lastTempoChangeS;
		    tmout = SysDep::cond_timedwait(&midiOutCond, &midiOutMutex,
						   msecs);
		}
	    }
	}

	if( shutdownRequest ) break;
	if( tempoScaleChangeRequest ) {
	    msecs = SysDep::get_time();
	    lastTempoChangeT = (msecs - lastTempoChangeS) * currentTempo
		               * tempoScale / 125 + lastTempoChangeT;
	    lastTempoChangeS = msecs;
	    tempoScale = requestedTempoScale;
	    tempoScaleChangeRequest = false;
	} 
	if( stopRequest ) {
	    doStopAll();
	    stopRequest = false;
	    if( retriggerNotesChangeReq ) {
		retriggerNotes = retriggerNotesChangeReq - 1;
		retriggerNotesChangeReq = 0;
	    }
	}
	if( !cancelRequests.empty() ) {
	    for( vector<pair<int, int> >::iterator i = cancelRequests.begin();
		 i != cancelRequests.end(); i++ ) {
		doCancelMessages(i->first, i->second);
	    }
	    cancelRequests.clear();
	}
	if( !tmout ) continue; // new event with earlier time stamp is arrived
	
	/* pop the event at the queue's top and output it to MIDI I/F */
	while( !moEventQueue.empty() && moEventQueue[0]->time <= ticks ) {
	    mo_queue_elm *qtop = moEventQueue[0];
	    if( qtop->devNum == DEV_LOOPBACK ) {
		MidiIn::enqueue(qtop->devNum, qtop->time, qtop->tk, qtop->msg);
	    } else if( qtop->msg[0] != 0xff ) {
		if( qtop->devNum >= 0 && midiOutHandles[qtop->devNum] ) {
		    SysDep::midimsg_t m;
		    if( qtop->msg[0] == 0xf0 ) {
			m.msg.assign(qtop->msg.begin() + 1, qtop->msg.end());
			m.isSysEx = true; 
		    } else {
			m.msg = qtop->msg;
			m.isSysEx = false;
		    }
		    midiOutSendMessage(qtop->devNum, qtop->tk, m);
		}
	    } else if( qtop->msg.size() >= 5 && qtop->msg[1] == M_TEMPO ) {
		/* tempo event */
		lastTempoChangeS = msecs;
		lastTempoChangeT = ticks;
		int usecsPerBeat = ((qtop->msg[2] << 16) + 
				    (qtop->msg[3] << 8) + qtop->msg[4]);
		currentTempo = 6e7 / usecsPerBeat;
	    } /* ignore other meta-events */

	    pop_heap(moEventQueue.begin(), moEventQueue.end(), 
		     mo_queue_elm::greater);
	    delete moEventQueue.back();
	    moEventQueue.pop_back();
	}
    }

    /* shutdown - close all devices */
    for( int i = 0; i < midiOutHandles.size(); i++ ) {
	if( midiOutHandles[i] ) {
	    SysDep::midiout_close(midiOutHandles[i]);
	    midiOutHandles[i] = NULL;
	}
    }
    SysDep::mutex_unlock(&midiOutMutex);
}

void MidiOut::startup() 
{
    SysDep::mutex_init(&midiOutMutex);
    SysDep::cond_init(&midiOutCond);

    currentTempo = 125.0; // 125 beats per minute (1 tick = 1 msec)
    lastTempoChangeS = 0; 
    lastTempoChangeT = 0;

    if( ! SysDep::create_thread(midiOutThread, midiOutThreadBody) ) {
	fprintf(stderr, "MIDI-output thread creation failed\n");
	exit(1);
    }
}

bool MidiOut::openDevice(int devNum)
{
    if( devNum < 0 ) return false;
    if( devNum >= SysDep::midiout_get_num_devs() ) return true;

    bool err = false;
    SysDep::mutex_lock(&midiOutMutex);
    if( midiOutHandles.size() <= devNum ) { 
	midiOutHandles.resize(devNum + 1, NULL);
    }
    if( !midiOutHandles[devNum] ) {
	if( ! (midiOutHandles[devNum] = SysDep::midiout_open(devNum)) ) {
	    err = true;
	}
    }
    SysDep::mutex_unlock(&midiOutMutex);
    return err;
}

void MidiOut::closeDevice(int devNum)
{
    if( devNum < 0 ) return;
    SysDep::mutex_lock(&midiOutMutex);
    if( devNum < midiOutHandles.size() && midiOutHandles[devNum] ) {
	SysDep::midiout_close(midiOutHandles[devNum]);
	midiOutHandles[devNum] = NULL;
    }
    SysDep::mutex_unlock(&midiOutMutex);
}

bool MidiOut::isOpenedDevice(int devNum)
{
    if( devNum < 0 ) return true;
    SysDep::mutex_lock(&midiOutMutex);
    bool result = devNum < midiOutHandles.size() && midiOutHandles[devNum];
    SysDep::mutex_unlock(&midiOutMutex);
    return result;
}

void MidiOut::shutdown() 
{
    SysDep::mutex_lock(&midiOutMutex);
    shutdownRequest = true;
    SysDep::cond_signal(&midiOutCond);
    SysDep::mutex_unlock(&midiOutMutex);
    SysDep::join_thread(midiOutThread);
}

void MidiOut::stopAll() 
{
    SysDep::mutex_lock(&midiOutMutex);
    stopRequest = true;
    SysDep::cond_signal(&midiOutCond);
    SysDep::mutex_unlock(&midiOutMutex);
}

void MidiOut::setTempoScale(double scale)
{
    SysDep::mutex_lock(&midiOutMutex);
    tempoScaleChangeRequest = true;
    requestedTempoScale = scale < 0 ? 0 : scale;
    SysDep::cond_signal(&midiOutCond);
    SysDep::mutex_unlock(&midiOutMutex);
}

static void enqueue(mo_queue_elm *q) 
{
    /* To reduce overheads, a signal is sent to the MIDIOUT thread 
       only if the event time at the top of the queue is changed. */
    bool timeChanged = false;
    double orgTime;

    SysDep::mutex_lock(&midiOutMutex);

    if( moEventQueue.empty() ) timeChanged = true;
    else orgTime = moEventQueue[0]->time;
    moEventQueue.push_back(q);
    push_heap(moEventQueue.begin(), moEventQueue.end(), mo_queue_elm::greater);
    if( !timeChanged && orgTime != moEventQueue[0]->time ) timeChanged = true;

    if( timeChanged ) SysDep::cond_signal(&midiOutCond);
    SysDep::mutex_unlock(&midiOutMutex);
}

bool MidiOut::queueMessage(int devNum, double ticks, int tk,
			   const message_t& msg)
{
    if( msg.size() < 1 ) return true;
    if( devNum >= 0 ) {
	SysDep::mutex_lock(&midiOutMutex);
	bool err = devNum >= midiOutHandles.size() || !midiOutHandles[devNum];
	SysDep::mutex_unlock(&midiOutMutex);
	if( err ) return true;
    }
    mo_queue_elm *q = new mo_queue_elm(devNum, ticks, tk);
    q->msg = msg;
    enqueue(q);
    return false;
}

void MidiOut::cancelMessages(int devNum, int tk)
{
    SysDep::mutex_lock(&midiOutMutex);
    cancelRequests.push_back(pair<int, int>(devNum, tk));
    SysDep::cond_signal(&midiOutCond);
    SysDep::mutex_unlock(&midiOutMutex);
}

void MidiOut::setRetrigger(bool enable)
{
    SysDep::mutex_lock(&midiOutMutex);
    stopRequest = true;
    retriggerNotesChangeReq = enable + 1;
    SysDep::cond_signal(&midiOutCond);
    SysDep::mutex_unlock(&midiOutMutex);
}
