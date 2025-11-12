#
# Detecting chords in the MIDI input stream
#
from pytakt import *
from pytakt.midiio import *

open_input_device()
loopback_event = LoopBackEvent(0, 'detect_chord')
chord_buffer = []  # A buffer for storing pitches in the chord
while True:
    ev = recv_event()
    if isinstance(ev, NoteOnEvent):
        if not chord_buffer:  # For the first note in the chord
            # The second argument below specifies the timestamp.
            queue_event(loopback_event, ev.t + 50)
        chord_buffer.append(ev.n)
    elif ev is loopback_event:
        if len(chord_buffer) >= 2:
            chord = Chord.from_chroma_profile(
                chroma_profile(chord_buffer), bass=min(chord_buffer))
            print(chord_buffer, chord.name())
        chord_buffer.clear()
