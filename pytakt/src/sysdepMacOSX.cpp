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
#include "sysdepGeneric.cpp"
#include "takterror.h"
#include <list>

using namespace std;

static UInt64  startHostTime;
static UInt64  startHostTimeInNanos;
static MIDIClientRef  midiClient;
static bool clientCreated;
static SysDep::mutex_t ibufMutex;
static SysDep::cond_t  ibufCond;
static bool terminateRequest;

static list<SysDep::midiin_t *> midiInList;  /* list of all midiin_t's */

#define  CTRL_ALL_NOTES_OFF   123
#define  CTRL_SUSTAIN   64

void SysDep::initialize(SysDep::sighandler_t
			(*signal_func)(int, SysDep::sighandler_t))
{
    initialize_generic(signal_func);

    mutex_init(&ibufMutex);
    cond_init(&ibufCond);

    startHostTime = AudioGetCurrentHostTime();
    startHostTimeInNanos = AudioConvertHostTimeToNanos(startHostTime);
}

/*
 * MIDI output
 */

/* wait for the completion of the previous SysEx message and free the buffer */
static void wait_for_sysex_done(SysDep::midiout_t *midiOut)
{
    if( midiOut->sysexReq != NULL ) {
	/* poll until the previous transmission is completed */
	while( !midiOut->sysexReq->complete ) {
	    usleep(1000); /* 1ms corresponds to the time for transmitting 
			     3 bytes through the MIDI cable */
	}

	/* free sysex buffer */
	free(midiOut->sysexData);
	free(midiOut->sysexReq);
	midiOut->sysexReq = NULL;
    }
}

int SysDep::midiout_get_num_devs() 
{
    return MIDIGetNumberOfDestinations();
}

string SysDep::midiout_get_dev_name(int devNum) 
{
    CFStringRef name = NULL;
    MIDIEndpointRef  dest = MIDIGetDestination(devNum);
    if( dest && MIDIObjectGetStringProperty(dest, kMIDIPropertyDisplayName, 
					    &name) == noErr ) {
	char buf[1024];
	CFStringGetCString(name, buf, 1024, kCFStringEncodingUTF8);
	return buf;	
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
    midiout_t  *midiOut;

    if( devNum < 0 || devNum >= midiout_get_num_devs() ) {
        return NULL;
    }

    if( !clientCreated ) {
	MIDIClientCreate(CFSTR("Takt"), NULL, NULL, &midiClient);
	clientCreated = true;
    }

    midiOut = new midiout_t();

    if( (midiOut->dest = MIDIGetDestination(devNum)) == 0 ) {
	delete midiOut;
	return NULL;
    }
    if( MIDIOutputPortCreate(midiClient, CFSTR("Takt output"),
			     &midiOut->outPort) != noErr ) {
	delete midiOut;
	return NULL;
    }

    midiOut->sysexReq = NULL;

    return midiOut;
}

void SysDep::midiout_close(midiout_handle_t midiOut)
{
    MIDIFlushOutput(midiOut->dest);  /* no effect? */
    wait_for_sysex_done(midiOut);

    /* Send all-note-off and no-sustain messages for all the channels */
    MIDIPacketList lst;
    MIDIPacket *p;
    unsigned char  data[6];
    for( int ch = 0; ch < 16; ch++ ) {
	p = MIDIPacketListInit(&lst);
	data[0] = 0xb0 + ch;
	data[1] = CTRL_ALL_NOTES_OFF;
	data[2] = 0;
	data[3] = 0xb0 + ch;
	data[4] = CTRL_SUSTAIN;
	data[5] = 0;
	p = MIDIPacketListAdd(&lst, sizeof(lst), p, 0, 6, data);
	MIDISend(midiOut->outPort, midiOut->dest, &lst);
    }

    MIDIPortDispose(midiOut->outPort);
    delete midiOut;
}

void SysDep::midi_send(midiout_handle_t midiOut, const midimsg_t *m)
{
    wait_for_sysex_done(midiOut);

    if( ! m->isSysEx ) {
	MIDIPacketList lst;
	MIDIPacket *p;
	Byte mbuf[3];
	int len = ((m->msg[0] & 0xf0) == 0xc0 ||(m->msg[0] & 0xf0) == 0xd0 ? 
		   2 : 3);
	for( int i = 0; i < len; i++ ) mbuf[i] = m->msg[i];
	p = MIDIPacketListInit(&lst);
	p = MIDIPacketListAdd(&lst, sizeof(lst), p, 0, len, mbuf);
	MIDISend(midiOut->outPort, midiOut->dest, &lst);
    } else {
	/* allocate sysex buffer */
	MIDISysexSendRequest *req;
	Byte *dp;
	if( !(req = (MIDISysexSendRequest *) 
	      malloc(sizeof(MIDISysexSendRequest))) )
	    Error::no_memory();
	if( !(dp = (Byte *) malloc(m->msg.size())) )
	    Error::no_memory();
	for( int i = 0; i < m->msg.size(); i++ ) dp[i] = m->msg[i];
	req->destination = midiOut->dest;
	req->data = dp;
	req->bytesToSend = m->msg.size();
	req->complete = 0;
	req->completionProc = NULL;
	req->completionRefCon = NULL;
	midiOut->sysexReq = req;
	midiOut->sysexData = dp;
	MIDISendSysex(req);
    }
}

/*
 * MIDI input
 */

int SysDep::midiin_get_num_devs() 
{
    return MIDIGetNumberOfSources();
}

string SysDep::midiin_get_dev_name(int devNum) 
{
    CFStringRef name = NULL;
    MIDIEndpointRef  src = MIDIGetSource(devNum);
    if( src && MIDIObjectGetStringProperty(src, kMIDIPropertyDisplayName, 
					    &name) == noErr ) {
	char buf[1024];
	CFStringGetCString(name, buf, 1024, kCFStringEncodingUTF8);
	return buf;	
    } else {
	return "*Invalid device*";
    }
}

int SysDep::midiin_get_default_dev()
{
    return midiin_get_num_devs() > 0 ? 0 : -1;
}

static void midiInReadProc(const MIDIPacketList *packetList,
			   void *readProcRefCon, void *srcConnRefCon)
{
    SysDep::midiin_t  *midiIn = (SysDep::midiin_t *) readProcRefCon;
    midiin_buffer_elm  elm;

    const MIDIPacket *packet = &packetList->packet[0];
    for( int i = 0; i < packetList->numPackets; i++ ) {
	int  k = 0;

	while( k < packet->length ) {
	    bool msgComplete = false;
	    if( midiIn->sysexData != NULL ) {
		int d = packet->data[k++];
		if( d < 0x80 ) { /* sysex data byte */
		    midiIn->sysexData->push_back(d);
		} else if( d < 0xf8 ) { /* end of exclusive */
		    if( d != 0xf7 ) { k--; } /* abnormal termination */
		    midiIn->sysexData->push_back(0xf7);
		    elm.timeStamp = midiIn->sysexTimeStamp;
		    elm.isShortMsg = false;
		    elm.lmsg = midiIn->sysexData;
		    msgComplete = true;
		    midiIn->sysexData = NULL;
		} else {
		    /* ignore real-time messages embeded in a sysex message */
		}
	    } else {
		int st = packet->data[k++];
		if( st == 0xf0 ) {
		    /* a new exclusive message */
		    midiIn->sysexTimeStamp = packet->timeStamp;
		    midiIn->sysexData = new vector<unsigned char>;
		    midiIn->sysexData->push_back(st);
		} else if( st < 0xf0 ) {
		    /* short MIDI message */
		    elm.timeStamp = packet->timeStamp;
		    elm.isShortMsg = true;
		    elm.msg[0] = st;
		    elm.msg[1] = packet->data[k++];
		    if( (st & 0xf0) != 0xc0 && (st & 0xf0) != 0xd0 ) {
			elm.msg[2] = packet->data[k++];
		    }
		    msgComplete = true;
		} else {
		    /* ignore system messages */
		    if( st == 0xf2 )  k += 2;
		    else if( st == 0xf3 )  k += 1;
		}
	    }
	    if( msgComplete ) {
		/* Message from IAC may have a far past timestamp (usually 0)
		   meaning "immediate output". 
		   Such a timestamp must be corrected. */
		//if( U64Compare(elm.timeStamp, startHostTime) < 0 ) {
		if( elm.timeStamp < startHostTime ) {
		    elm.timeStamp = AudioGetCurrentHostTime();
		}
		SysDep::mutex_lock(&ibufMutex);
		midiIn->inputBuffer.push(elm);
		SysDep::mutex_unlock(&ibufMutex);
		SysDep::cond_signal(&ibufCond);
	    }
	}
	
	packet = MIDIPacketNext(packet);
    }
}
    
SysDep::midiin_handle_t SysDep::midiin_open(int devNum)
{
    midiin_t  *midiIn;

    if( devNum < 0 || devNum >= midiin_get_num_devs() ) {
        return NULL;
    }

    if( !clientCreated ) {
	MIDIClientCreate(CFSTR("Takt"), NULL, NULL, &midiClient);
	clientCreated = true;
    }

    midiIn = new midiin_t();

    if( (midiIn->src = MIDIGetSource(devNum)) == 0 ) {
	delete midiIn;
	return NULL;
    }
    if( MIDIInputPortCreate(midiClient, CFSTR("Takt input"), 
			    midiInReadProc, (void *) midiIn,
			    &midiIn->inPort) != noErr ) {
	delete midiIn;
	return NULL;
    }
    MIDIPortConnectSource(midiIn->inPort, midiIn->src, NULL);

    midiIn->devNum = devNum;
    midiIn->sysexData = NULL;
    midiIn->deviceClosed = false;

    SysDep::mutex_lock(&ibufMutex);
    midiInList.push_back(midiIn);
    SysDep::mutex_unlock(&ibufMutex);

    return midiIn;
}

void SysDep::midiin_close(midiin_handle_t midiIn)
{
    MIDIPortDisconnectSource(midiIn->inPort, midiIn->src);
    MIDIPortDispose(midiIn->inPort);

    SysDep::mutex_lock(&ibufMutex);
    midiInList.remove(midiIn);
    SysDep::mutex_unlock(&ibufMutex);

    if( midiIn->sysexData != NULL )  delete midiIn->sysexData;
    midiIn->deviceClosed = true;  
    /* We do not free midiIn for avoiding problems 
       when midi_recv() is accidentally called after close. */
}

int SysDep::midi_recv(midiin_handle_t midiIn, midimsg_t *m, double *timeStamp)
{
    midiin_buffer_elm  elm;

    if( midiIn->deviceClosed )  return 1;  // error: alread closed

    mutex_lock(&ibufMutex);
    if( midiIn->inputBuffer.empty() ) {
	mutex_unlock(&ibufMutex);
	return 1;  // error: buffer is empty
    }
    elm = midiIn->inputBuffer.front();
    midiIn->inputBuffer.pop();
    mutex_unlock(&ibufMutex);

    //*timeStamp = UInt64ToLongDouble(
    //	U64Subtract(AudioConvertHostTimeToNanos(elm.timeStamp),
    //		    startHostTimeInNanos)) / 1e6;
    *timeStamp = (AudioConvertHostTimeToNanos(elm.timeStamp) -
		  startHostTimeInNanos) / 1e6;

    if( elm.isShortMsg ) {
	m->msg.resize(3);
	m->msg[0] = elm.msg[0];
	m->msg[1] = elm.msg[1];
	m->msg[2] = elm.msg[2];
	m->isSysEx = false;
    } else {
	m->msg = *elm.lmsg;
	m->isSysEx = true;
	delete elm.lmsg;
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
	for( list<midiin_t *>::const_iterator i = midiInList.begin(); 
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
}
