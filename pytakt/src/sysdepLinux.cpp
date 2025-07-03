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
#include "sysdepGeneric.cpp"
#include "takterror.h"

using namespace std;

static SysDep::mutex_t  seqMutex;
static snd_seq_t  *seq;
static int myClientID;
static int inputQueueID;
static int inputPortID;
static snd_seq_event_t *inputEvent;

struct dev_info {
    snd_seq_addr_t  addr;
    string name;
    dev_info(const snd_seq_addr_t &a, const string &s) : addr(a), name(s) {}
};
vector<dev_info> inputDevices, outputDevices;


static void findAllDevices() 
{
    snd_seq_client_info_t *cinfo;
    snd_seq_client_info_alloca(&cinfo);
    snd_seq_client_info_set_client(cinfo, -1);
    snd_seq_port_info_t *pinfo;
    snd_seq_port_info_alloca(&pinfo);

    while( snd_seq_query_next_client(seq, cinfo) >= 0 ) {
	int cid = snd_seq_client_info_get_client(cinfo);
	if( cid == myClientID )  continue;
        snd_seq_port_info_set_client(pinfo, cid);
	snd_seq_port_info_set_port(pinfo, -1);
	while( snd_seq_query_next_port(seq, pinfo) >= 0 ) {
	    int pid = snd_seq_port_info_get_port(pinfo);
	    int ptype = snd_seq_port_info_get_type(pinfo);
	    int cap = snd_seq_port_info_get_capability(pinfo);
	    if( (ptype & SND_SEQ_PORT_TYPE_MIDI_GENERIC) &&
		(cap & (SND_SEQ_PORT_CAP_SUBS_READ|
			SND_SEQ_PORT_CAP_SUBS_WRITE)) ) {
		char buf[64];
		sprintf(buf, "%d:%d ", cid, pid);
		string name = buf;
		const char *cname = snd_seq_client_info_get_name(cinfo);
		const char *pname = snd_seq_port_info_get_name(pinfo);
		/* supply the client name only if the port name is not
		   originally prefixed by the client name */
		if( strncmp(cname, pname, strlen(cname)) != 0 ) {
		    name += '(';
		    name += cname;
		    name += ") ";
		}
		name += pname;
		if( cap & SND_SEQ_PORT_CAP_SUBS_READ ) {
		    inputDevices.push_back(
			dev_info(*snd_seq_port_info_get_addr(pinfo), name));
		}
		if( cap & SND_SEQ_PORT_CAP_SUBS_WRITE ) {
		    outputDevices.push_back(
			dev_info(*snd_seq_port_info_get_addr(pinfo), name));
		}
	    }
	}
    }
}

static void snd_lib_error_silent(const char *, int, const char *, int, const char *, ...) {}

void SysDep::initialize(SysDep::sighandler_t
			(*_pyos_setsig)(int, SysDep::sighandler_t))
{
    initialize_generic(_pyos_setsig);

    mutex_init(&seqMutex);

    snd_lib_error_set_handler(snd_lib_error_silent);
    if( snd_seq_open(&seq, "default", SND_SEQ_OPEN_DUPLEX, 0) < 0 ) {
	snd_lib_error_set_handler(NULL);
	//fprintf(stderr, "Could not open the ALSA sequencer\n");
	seq = NULL;
    } else {
	snd_lib_error_set_handler(NULL);
	snd_seq_set_client_name(seq, "Takt");
	myClientID = snd_seq_client_id(seq);
	
	findAllDevices();
	
	inputQueueID = snd_seq_alloc_queue(seq);
	snd_seq_start_queue(seq, inputQueueID, NULL);
	snd_seq_drain_output(seq);

	/* reinitialize sysDepStartTime, because we want to minimize the
	   deference between the queue's time and get_time() */
	struct timeval  tm;
	gettimeofday(&tm, NULL);
	sysDepStartTime = tm.tv_sec * 1e3 + tm.tv_usec / 1e3;
    }

    if( seq ) {
	inputPortID = snd_seq_create_simple_port(seq, "Takt input",
					 SND_SEQ_PORT_CAP_WRITE,
					 SND_SEQ_PORT_TYPE_MIDI_GENERIC | 
					 SND_SEQ_PORT_TYPE_SOFTWARE | 
					 SND_SEQ_PORT_TYPE_APPLICATION);
	if( inputPortID ) {
	    fprintf(stderr, "Could not create the ALSA input port\n");
	    exit(1);
	}
    }
}

/*
 * MIDI output
 */

int SysDep::midiout_get_num_devs() 
{
    return outputDevices.size();
}

string SysDep::midiout_get_dev_name(int devNum) 
{
    if( devNum < 0 || devNum >= midiout_get_num_devs() ) {
	return "*Invalid device*";
    } else {
	return outputDevices[devNum].name;
    }
}

int SysDep::midiout_get_default_dev()
{
    for( int i = 0; i < outputDevices.size(); i++ ) {
	if( outputDevices[i].name.find("Through Port") == string::npos )
	    return i;
    }
    return -1;
}    
    
SysDep::midiout_handle_t SysDep::midiout_open(int devNum)
{
    midiout_t  *midiOut;

    if( devNum < 0 || devNum >= midiout_get_num_devs() ) {
        return NULL;
    }

    mutex_lock(&seqMutex);
    int oport = snd_seq_create_simple_port(seq, "Takt output",
					   SND_SEQ_PORT_CAP_READ | 
					   SND_SEQ_PORT_CAP_SUBS_READ,
					   SND_SEQ_PORT_TYPE_MIDI_GENERIC | 
					   SND_SEQ_PORT_TYPE_SOFTWARE | 
					   SND_SEQ_PORT_TYPE_APPLICATION);
    mutex_unlock(&seqMutex);
    if( oport < 0 )  return NULL;

    snd_seq_port_subscribe_t *subs;
    snd_seq_port_subscribe_alloca(&subs);
    snd_seq_addr_t sender;
    sender.client = myClientID;
    sender.port = oport;
    snd_seq_port_subscribe_set_sender(subs, &sender);
    snd_seq_port_subscribe_set_dest(subs, &outputDevices[devNum].addr);
    mutex_lock(&seqMutex);
    int result = snd_seq_subscribe_port(seq, subs);
    mutex_unlock(&seqMutex);
    if( result < 0 )  return NULL;

    midiOut = new midiout_t();
    midiOut->devNum = devNum;
    midiOut->port = oport;
    return midiOut;
}

void SysDep::midiout_close(midiout_handle_t midiOut)
{
    snd_seq_port_subscribe_t *subs;
    snd_seq_port_subscribe_alloca(&subs);
    snd_seq_addr_t sender;
    sender.client = myClientID;
    sender.port = midiOut->port;
    snd_seq_port_subscribe_set_sender(subs, &sender);
    snd_seq_port_subscribe_set_dest(subs, &outputDevices[midiOut->devNum].addr);
    mutex_lock(&seqMutex);
    snd_seq_unsubscribe_port(seq, subs);
    snd_seq_delete_port(seq, midiOut->port);
    mutex_unlock(&seqMutex);
    delete midiOut;
}

void SysDep::midi_send(midiout_handle_t midiOut, const midimsg_t *m)
{
    snd_seq_event_t ev;
    snd_seq_ev_clear(&ev);
    snd_seq_ev_set_source(&ev, midiOut->port);
    snd_seq_ev_set_subs(&ev);
    snd_seq_ev_set_direct(&ev);

    if( ! m->isSysEx ) {
	switch( m->msg[0] & 0xf0 ) {
	case 0x80:
	    snd_seq_ev_set_noteoff(&ev, m->msg[0] & 0xf, m->msg[1], m->msg[2]);
	    break;
	case 0x90:
	    snd_seq_ev_set_noteon(&ev, m->msg[0] & 0xf, m->msg[1], m->msg[2]);
	    break;
	case 0xa0:
	    snd_seq_ev_set_keypress(&ev, m->msg[0] & 0xf, m->msg[1], m->msg[2]);
	    break;
	case 0xb0:
	    snd_seq_ev_set_controller(&ev, m->msg[0] & 0xf,
				      m->msg[1], m->msg[2]);
	    break;
	case 0xc0:
	    snd_seq_ev_set_pgmchange(&ev, m->msg[0] & 0xf, m->msg[1]);
	    break;
	case 0xd0:
	    snd_seq_ev_set_chanpress(&ev, m->msg[0] & 0xf, m->msg[1]);
	    break;
	case 0xe0:
	    snd_seq_ev_set_pitchbend(&ev, m->msg[0] & 0xf, 
				     m->msg[1] + (m->msg[2] << 7) - 8192);
	    break;
	default:
	    /* ignore system msgs */
	    return;
	}
    } else {
	snd_seq_ev_set_sysex(&ev, m->msg.size(), (void*)&m->msg[0]);
    }

    mutex_lock(&seqMutex);
    snd_seq_event_output(seq, &ev);
    snd_seq_drain_output(seq);
    mutex_unlock(&seqMutex);
}

/*
 * MIDI input
 */

int SysDep::midiin_get_num_devs() 
{
    return inputDevices.size();
}

string SysDep::midiin_get_dev_name(int devNum) 
{
    if( devNum < 0 || devNum >= midiin_get_num_devs() ) {
	return "*Invalid device*";
    } else {
	return inputDevices[devNum].name;
    }
}
    
int SysDep::midiin_get_default_dev()
{
    for( int i = 0; i < inputDevices.size(); i++ ) {
	if( inputDevices[i].name.find("Through Port") == string::npos )
	    return i;
    }
    return -1;
}    
    
SysDep::midiin_handle_t SysDep::midiin_open(int devNum)
{
    midiin_t  *midiIn;

    if( devNum < 0 || devNum >= midiin_get_num_devs() ) {
        return NULL;
    }

    snd_seq_port_subscribe_t *subs;
    snd_seq_port_subscribe_alloca(&subs);
    snd_seq_addr_t dest;
    dest.client = myClientID;
    dest.port = inputPortID;
    snd_seq_port_subscribe_set_sender(subs, &inputDevices[devNum].addr);
    snd_seq_port_subscribe_set_dest(subs, &dest);
    snd_seq_port_subscribe_set_queue(subs, inputQueueID);
    snd_seq_port_subscribe_set_time_update(subs, true);
    snd_seq_port_subscribe_set_time_real(subs, true);
    mutex_lock(&seqMutex);
    int result = snd_seq_subscribe_port(seq, subs);
    mutex_unlock(&seqMutex);
    if( result < 0 )  return NULL;

    midiIn = new midiin_t();
    midiIn->devNum = devNum;
    return midiIn;
}

void SysDep::midiin_close(midiin_handle_t midiIn)
{
    snd_seq_port_subscribe_t *subs;
    snd_seq_port_subscribe_alloca(&subs);
    snd_seq_addr_t dest;
    dest.client = myClientID;
    dest.port = inputPortID;
    snd_seq_port_subscribe_set_sender(subs, &inputDevices[midiIn->devNum].addr);
    snd_seq_port_subscribe_set_dest(subs, &dest);
    mutex_lock(&seqMutex);
    snd_seq_unsubscribe_port(seq, subs);
    mutex_unlock(&seqMutex);

    delete midiIn;
}

int SysDep::midi_recv(midiin_handle_t midiIn /* not used */,
		      midimsg_t *m, double *timeStamp)
{
    if( !inputEvent ) {
	return 1;  // error: buffer is empty
    }
    
    snd_seq_event_t *ev = inputEvent;

    *timeStamp = ev->time.time.tv_sec * 1e3 + ev->time.time.tv_nsec / 1e6;
    m->isSysEx = false;

    switch(ev->type) {
    case SND_SEQ_EVENT_NOTEOFF:
	m->msg.resize(3);
	m->msg[0] = 0x80 | (ev->data.note.channel & 0xf);
	m->msg[1] = ev->data.note.note;
	m->msg[2] = ev->data.note.velocity;
	break;
    case SND_SEQ_EVENT_NOTEON:
	m->msg.resize(3);
	m->msg[0] = 0x90 | (ev->data.note.channel & 0xf);
	m->msg[1] = ev->data.note.note;
	m->msg[2] = ev->data.note.velocity;
	break;
    case SND_SEQ_EVENT_KEYPRESS:
	m->msg.resize(3);
	m->msg[0] = 0xa0 | (ev->data.note.channel & 0xf);
	m->msg[1] = ev->data.note.note;
	m->msg[2] = ev->data.note.velocity;
	break;
    case SND_SEQ_EVENT_CONTROLLER:
	m->msg.resize(3);
	m->msg[0] = 0xb0 | (ev->data.control.channel & 0xf);
	m->msg[1] = ev->data.control.param;
	m->msg[2] = ev->data.control.value;
	break;
    case SND_SEQ_EVENT_PGMCHANGE:
	m->msg.resize(2);
	m->msg[0] = 0xc0 | (ev->data.control.channel & 0xf);
	m->msg[1] = ev->data.control.value;
	break;
    case SND_SEQ_EVENT_CHANPRESS:
	m->msg.resize(2);
	m->msg[0] = 0xd0 | (ev->data.control.channel & 0xf);
	m->msg[1] = ev->data.control.value;
	break;
    case SND_SEQ_EVENT_PITCHBEND:
	m->msg.resize(3);
	m->msg[0] = 0xe0 | (ev->data.control.channel & 0xf);
	m->msg[1] = (ev->data.control.value + 8192) & 0x7f;
	m->msg[2] = ((ev->data.control.value + 8192) >> 7) & 0x7f;
	break;
    case SND_SEQ_EVENT_SYSEX:
	m->msg.resize(ev->data.ext.len);
	m->isSysEx = true;
	memcpy(&m->msg[0], ev->data.ext.ptr, ev->data.ext.len);
	break;
    default:
	return 1;  // error: unknown event type
    }

    inputEvent = NULL;
    return 0;
}

/*
 * device wait
 */
SysDep::device_wait_rtn
SysDep::device_wait(int &devNum)
{
    snd_seq_event_t *ev;

    if( !seq ) return TERMINATED;

    for( int retry = 0; retry < 100; retry++ ) {
	int result = 0;
	mutex_lock(&seqMutex);
	if( snd_seq_event_input_pending(seq, 0) <= 0 ) {
	    while( result == 0 ) {
		int nfds = snd_seq_poll_descriptors_count(seq, POLLIN);
		struct pollfd *fds = (pollfd *) alloca(nfds * sizeof(pollfd));
		snd_seq_poll_descriptors(seq, fds, nfds, POLLIN);
		mutex_unlock(&seqMutex);
		result = poll(fds, nfds, -1);
		mutex_lock(&seqMutex);
		if( result > 0 ) {
		    unsigned short revents = 0;
		    if( snd_seq_poll_descriptors_revents(seq, fds, nfds, 
							 &revents) < 0 ) {
			result = -1;
		    } else {
			if( !(revents & POLLIN) )  result = 0;
		    }
		}
	    }
	}
	if( result >= 0 ) {
	    result = snd_seq_event_input(seq, &ev);
	}
	mutex_unlock(&seqMutex);

	if( result < 0 ) {
	    fprintf(stderr, "Failed in receiving event from MIDI input device (buffer overrun?)\n");
	    continue;
	}

	if( ev->source.client == myClientID ) {
	    return TERMINATED;
	} else {
	    for( int i = 0; i < inputDevices.size(); i++ ) {
		if( ev->source.client == inputDevices[i].addr.client &&
		    ev->source.port == inputDevices[i].addr.port ) {
		    devNum = i;
		    inputEvent = ev;
		    return MIDIIN;
		}
	    }
	    fprintf(stderr, "Event received from unregistered MIDI-input source\n");
	}
    }

    return TERMINATED;  /* error */
}

void SysDep::terminate_device_wait()
{
    if( !seq ) return;

    snd_seq_event_t ev;
    snd_seq_ev_clear(&ev);
    ev.dest.client = myClientID;
    ev.dest.port = inputPortID;
    snd_seq_ev_set_direct(&ev);

    mutex_lock(&seqMutex);
    snd_seq_event_output(seq, &ev);
    snd_seq_drain_output(seq);
    mutex_unlock(&seqMutex);
}
