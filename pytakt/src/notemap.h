/* -*- C++ -*- 
 * Realtime MIDI I/O Library for Pytakt
 *
 *  Class for maps for finding the currently-active note-on events
 *
 *  This code was originally a part of Takt, an interpreter for the Takt music 
 *  programming language.
 */

/* Copyright (C) 2014, 2025  Satoshi Nishimura */

#ifndef _NoteMap_
#define _NoteMap_

#include "defs.h"
#include <map>

namespace Takt {
class NoteMap {
    struct key_type {
	int  devNum;
	int  tk;  /* track number */
	int  ch;  /* MIDI channel number (0-15) */
	int  n;   /* MIDI note number (-1 for pedal) */
	key_type(int _devNum, int _tk, int _ch, int _n)
	    : devNum(_devNum), tk(_tk), ch(_ch), n(_n) {}
    };
    struct lessp {
	bool operator()(const key_type &m1, const key_type &m2) const {
	    return( m1.devNum < m2.devNum ||
		    (m1.devNum == m2.devNum &&
		     (m1.tk < m2.tk ||
		      (m1.tk == m2.tk && 
		       (m1.ch < m2.ch ||
			(m1.ch == m2.ch && m1.n < m2.n))))) );
	}
    };
    /* the value of the map is note-on pile count */
    typedef std::map<key_type, int, lessp> note_map;
    note_map  noteMap;

public:
    int push(int devNum, int tk, int ch, int n) {
	key_type  key(devNum, tk, ch, n);
	return noteMap.insert(note_map::value_type(key, 0)).first->second++;
    }

    void set(int devNum, int tk, int ch, int n, int count) {
	key_type  key(devNum, tk, ch, n);
	noteMap.insert(note_map::value_type(key, count));
    }

    int pop(int devNum, int tk, int ch, int n) {
	key_type  key(devNum, tk, ch, n);
	note_map::iterator  i;
	int count = 0;
	if( (i = noteMap.find(key)) != noteMap.end() ) {
	    count = --i->second;
	    if( count == 0 ) noteMap.erase(i);
	}
	return count;
    }

    void clear() {
	noteMap.clear();
    }

    void clear(int devNum, int tk, int ch) {
	note_map::iterator p1 = noteMap.end(), p2 = noteMap.end();
	for( note_map::iterator i = noteMap.begin(); i != noteMap.end(); i++ ){
	    if( (*i).first.devNum == devNum && (*i).first.tk == tk &&
		(*i).first.ch == ch ) {
		if( p1 == noteMap.end() ) p1 = i;
	    } else {
		if( p1 != noteMap.end() && p2 == noteMap.end() ) p2 = i;
	    }
	}
	noteMap.erase(p1, p2);
    }

    /* For each entry with devNum and tk, call a function and delete it */
    void clearAndCall(int devNum, int tk,
		      void (*func)(int, int, int, int, int)) {
	note_map::iterator p1 = noteMap.end(), p2 = noteMap.end();
	for( note_map::iterator i = noteMap.begin(); i != noteMap.end(); i++ ){
	    if( (*i).first.devNum == devNum &&
		(tk == ALL_TRACKS || (*i).first.tk == tk) ) {
		func(devNum, tk, (*i).first.ch, (*i).first.n, (*i).second);
		if( p1 == noteMap.end() ) p1 = i;
	    } else {
		if( p1 != noteMap.end() && p2 == noteMap.end() ) p2 = i;
	    }
	}
	noteMap.erase(p1, p2);
    }
};
}

#endif
