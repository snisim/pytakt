# coding:utf-8
"""
This module defines classes that perform conversions to and from pretty_midi.
libraries.
"""
"""
このモジュールには、pretty_midiへの変換、およびそれからの変換を行うクラスが
定義されています。
"""
# Copyright (C) 2025  Satoshi Nishimura

import pretty_midi
import warnings
import itertools
from pytakt.score import EventList, EventStream, Tracks
from pytakt.event import NoteEvent, CtrlEvent, MetaEvent, TimeSignatureEvent, \
    KeySignatureEvent, TempoEvent
from pytakt.constants import M_TEXT, M_TRACKNAME, M_LYRIC, TICKS_PER_QUARTER, \
    C_PROG, C_BEND
from pytakt.pitch import Pitch, Key
from pytakt.timemap import KeySignatureMap
from pytakt.utils import int_preferred


class TaktToPrettyMIDI:
    def create_note(self, ev):
        pmnote = pretty_midi.Note(ev.v, ev._get_n(),
                                  ev.t/1000, (ev.t + ev.L)/1000)
        for k, v in ev.__dict__.items():
            if not hasattr(pmnote, k):
                setattr(pmnote, k, v)
        return pmnote

    def add_tempo_change(self, tick_scales, ev):
        ts = 60.0 / (ev.value * TICKS_PER_QUARTER)
        if ev.t == 0:
            tick_scales[0] = (0, ts)
        else:
            _, last_ts = tick_scales[-1]
            if ts != last_ts:
                tick_scales.append((ev.t, ts))

    def get_instrument(self, prog, ch, is_note):
        if (prog, ch) in self.instruments:
            return self.instruments[(prog, ch)]
        # pre_inst contain PB or CC events before a program change (or None)
        pre_inst = self.instruments.get(ch)
        if is_note:
            inst = pretty_midi.Instrument(prog, ch == 10)
            if pre_inst:
                inst.control_changes = pre_inst.control_changes
                inst.pitch_bends = pre_inst.pitch_bends
            self.instruments[(prog, ch)] = inst
            return inst
        else:
            if not pre_inst:
                pre_inst = pretty_midi.Instrument(None)
                self.instruments[ch] = pre_inst
            return pre_inst

    def check_track0(self, ev):
        if ev.tk != 0:
            warnings.warn("Tempo, time-signature, and key-signature events "
                          "not contained in the first track will be ignored.")
            return False
        return True

    def convert_to_pretty_midi(self, score,
                               render, limit) -> pretty_midi.PrettyMIDI:
        if isinstance(score, EventStream) and score.is_consumed():
            raise Exception('convert_to_pretty_midi: '
                            'Input stream has already been consumed')

        evlist = EventList(score, limit=limit).PairNoteEvents()
        if render:
            evlist = evlist.Render()
        evlist_msec = evlist.ToMilliseconds()
        pmscore = pretty_midi.PrettyMIDI(resolution=TICKS_PER_QUARTER)

        # convert tempo events
        pmscore._tick_scales = [(0, 60.0 / (125.0 * TICKS_PER_QUARTER))]
        for ev in evlist.Filter(TempoEvent):
            if self.check_track0(ev):
                self.add_tempo_change(pmscore._tick_scales, ev)

        # convert other meta events
        for ev in evlist_msec.Filter(MetaEvent):
            if isinstance(ev, KeySignatureEvent):
                if self.check_track0(ev):
                    key_num = pretty_midi.key_name_to_key_number(
                            ev.value.tostr())
                    pmscore.key_signature_changes.append(
                        pretty_midi.KeySignature(key_num, ev.t/1000))
            elif isinstance(ev, TimeSignatureEvent):
                if self.check_track0(ev):
                    pmscore.time_signature_changes.append(
                        pretty_midi.TimeSignature(ev.numerator(),
                                                  ev.denominator(), ev.t/1000))
            elif ev.mtype == M_LYRIC:
                pmscore.lyrics.append(pretty_midi.Lyric(ev.value, ev.t/1000))
            elif ev.mtype == M_TEXT:
                pmscore.text_events.append(pretty_midi.Text(ev.value,
                                                            ev.t/1000))

        # convert note & control-change events
        tracks = evlist_msec.ToTracks()
        for track_number, track_evlist in enumerate(tracks):
            self.instruments = {}  # dict: (prog_num, ch) => Instrument
            track_name = ''
            current_prog = [0 for _ in range(17)]  # 17 because ch is base-1
            prev_time = -1
            notes_buf = []

            # When there is a program change after a note with the same time,
            # the program number should apply to the note. For this reason,
            # note output is delayed.
            def output_notes():
                for ev in notes_buf:
                    inst = self.get_instrument(current_prog[ev.ch], ev.ch, 1)
                    inst.notes.append(self.create_note(ev))
                notes_buf.clear()

            for ev in track_evlist:
                if ev.t != prev_time:
                    output_notes()
                if isinstance(ev, NoteEvent):
                    notes_buf.append(ev)
                elif ev.is_program_change():
                    current_prog[ev.ch] = ev._get_ctrl_val(1, 128) - 1
                elif ev.is_pitch_bend():
                    inst = self.get_instrument(current_prog[ev.ch], ev.ch, 0)
                    inst.pitch_bends.append(
                        pretty_midi.PitchBend(ev._get_ctrl_val(-8192, 8191),
                                              ev.t/1000))
                elif isinstance(ev, CtrlEvent) and 0 <= ev.ctrlnum < 128:
                    inst = self.get_instrument(current_prog[ev.ch], ev.ch, 0)
                    inst.control_changes.append(
                        pretty_midi.ControlChange(ev.ctrlnum,
                                                  ev._get_ctrl_val(0, 127),
                                                  ev.t/1000))
                elif isinstance(ev, MetaEvent) and ev.mtype == M_TRACKNAME:
                    track_name = ev.value
                prev_time = ev.t

            output_notes()
            for inst in self.instruments.values():
                if inst.program is not None:
                    inst.name = track_name
                    pmscore.instruments.append(inst)

        return pmscore


class PrettyMIDIToTakt:
    def conv_to_ticks(self, seconds):
        return int_preferred(self.pmscore.time_to_tick(seconds) *
                             self.reso_scale)

    def convert_note(self, pmnote, tk, ch):
        on_time = self.conv_to_ticks(pmnote.start)
        off_time = self.conv_to_ticks(pmnote.end)
        pitch = Pitch(pmnote.pitch, key=self.ksigmap.key_at(on_time))
        ev = NoteEvent(on_time, pitch, off_time - on_time,
                       pmnote.velocity, tk=tk, ch=ch)
        for k, v in pmnote.__dict__.items():
            if k not in ('start', 'end', 'pitch', 'velocity') and \
               not hasattr(ev, k):
                setattr(ev, k, v)
        return ev

    def convert_to_takt(self, pmscore) -> Tracks:
        self.pmscore = pmscore
        self.reso_scale = TICKS_PER_QUARTER / pmscore.resolution
        score = Tracks()
        track0 = EventList()
        # convert tempo events
        for (ticks, tick_scale) in pmscore._tick_scales:
            track0.add(TempoEvent(int_preferred(ticks * self.reso_scale),
                                  60 / (tick_scale * pmscore.resolution)))
        # convert time-signature events
        if not any(ts.time == 0 for ts in pmscore.time_signature_changes):
            track0.add(TimeSignatureEvent(0, 4, 4))  # default 4/4 timesig
        for ts in pmscore.time_signature_changes:
            track0.add(TimeSignatureEvent(self.conv_to_ticks(ts.time),
                                          ts.numerator, ts.denominator))
        # convert key-signature events
        for ks in pmscore.key_signature_changes:
            key = Key.from_tonic(ks.key_number % 12, ks.key_number >= 12)
            track0.add(KeySignatureEvent(self.conv_to_ticks(ks.time), key))
        # convert lyrics events
        for lyric in pmscore.lyrics:
            track0.add(MetaEvent(self.conv_to_ticks(lyric.time),
                                 M_LYRIC, lyric.text, tk=0))
        # Add text events
        for text in pmscore.text_events:
            track0.add(MetaEvent(self.conv_to_ticks(text.time),
                                 M_TEXT, text.text, tk=0))
        # append the conductor track to the score
        track0.sort()
        score.append(track0)

        self.ksigmap = KeySignatureMap(track0)
        channels = itertools.cycle([ch for ch in range(1, 17) if ch != 10])
        for n, inst in enumerate(pmscore.instruments):
            evlist = EventList()
            if inst.name:
                evlist.add(MetaEvent(0, M_TRACKNAME, inst.name, tk=n+1))
            # # If full compatibility with PrettyMIDI.write is needed, take
            # # the following (but may need more channels)
            # channel = next(channels)
            # if inst.is_drum:
            #     channel = 10
            channel = 10 if inst.is_drum else next(channels)
            evlist.add(CtrlEvent(0, C_PROG, inst.program + 1,
                                 tk=n+1, ch=channel))
            # convert pitch-bend events
            for bend in inst.pitch_bends:
                evlist.add(CtrlEvent(self.conv_to_ticks(bend.time), C_BEND,
                                     bend.pitch, tk=n+1, ch=channel))
            # convert control-change events.
            #  Sort only by the control number (because sorting also by the
            #  value may change the synthesizer's behavior).
            for ctrl_change in sorted(inst.control_changes,
                                      key=lambda x: x.number):
                evlist.add(CtrlEvent(self.conv_to_ticks(ctrl_change.time),
                                     ctrl_change.number,
                                     ctrl_change.value, tk=n+1, ch=channel))
            # convert notes
            for note in sorted(inst.notes, key=lambda x: x.pitch):
                evlist.add(self.convert_note(note, n+1, channel))
            # append a track to the score
            evlist.sort()
            score.append(evlist)

        return score


# test code
if __name__ == '__main__':
    import sys
    import os
    import argparse
    from pytakt import readsmf
    from pytakt.score import DEFAULT_LIMIT
    from pytakt.constants import M_EOT

    def print_pmscore(p, f=sys.stdout):
        print(f'<PrettyMIDI: resolution={p.resolution}>', file=f)
        for tick, tick_scale in p._tick_scales:
            tick /= p.resolution
            tick_scale *= p.resolution
            print(f'tick_scale: {tick:f} {tick_scale:f}', file=f)
        for ks in p.key_signature_changes:
            print(f'key_signature: key_number={ks.key_number} \
time={ks.time:.4f}', file=f)
        for ts in p.time_signature_changes:
            print(f'time_signature: {ts.numerator}/{ts.denominator} \
time={ts.time:.4f}', file=f)
        for e in p.lyrics:
            print(f'lyrics: {e.text!r} time={e.time:.4f}', file=f)
        for e in p.text_events:
            print(f'text: {e.text!r} time={e.time:.4f}', file=f)
        for i in p.instruments:
            # Absorb the difference in the order of events
            i.notes.sort(key=lambda x: (x.start, x.end, x.pitch, x.velocity))
            i.pitch_bends.sort(key=lambda x: (x.time, x.pitch))
            i.control_changes.sort(key=lambda x: (x.time, x.number, x.value))
            print(i, file=f)
            for pb in i.pitch_bends:
                print(f'PitchBend: pitch={pb.pitch} time={pb.time:.4f}',
                      file=f)
            for cc in i.control_changes:
                print(f'ControlChange: number={cc.number} value={cc.value} \
time={cc.time:.4f}', file=f)
            for nt in i.notes:
                print(f'Note: start={nt.start:.4f} end={nt.end:.4f} \
pitch={nt.pitch} velocity={nt.velocity}', file=f)

    def round_tempo_values(score):
        for ev in score.stream():
            if isinstance(ev, TempoEvent):
                ev.value = round(ev.value, 5)

    parser = argparse.ArgumentParser()
    parser.add_argument('MIDIFILE')
    args = parser.parse_args()

    # Note: There might be some differences due to numerical errors, the order
    # of control change events, the method of calculating the score duration,
    # or the different treatment of overlapping notes.

    # Compare a pretty_midi score converted from Pytakt and that directly read
    # from the MIDI file.
    score = readsmf(args.MIDIFILE)
    score = score.Reject('L==0')  # pretty_midi excludes zero-duration notes
    pmscore1 = TaktToPrettyMIDI().convert_to_pretty_midi(score, DEFAULT_LIMIT)
    pmscore2 = pretty_midi.PrettyMIDI(args.MIDIFILE)
    with open('/tmp/pmscore1.txt', 'w') as f:
        print_pmscore(pmscore1, f)
    with open('/tmp/pmscore2.txt', 'w') as f:
        print_pmscore(pmscore2, f)
    print("******** Test 1: Pytakt => pretty_midi ********")
    cmd = 'diff /tmp/pmscore1.txt /tmp/pmscore2.txt'
    print(cmd)
    if os.system(cmd) == 0:
        print('Succeeded')

    # Compare a Pytakt score converted from pretty_midi and that read by
    # Pytakt from a MIDI file that is written by pretty_midi.
    score1 = PrettyMIDIToTakt().convert_to_takt(pmscore2)
    # Add a small value to each time scale to make the tempo events in
    # test_pmconv.mid have the same values as the original MIDI file.
    pmscore2._tick_scales = [(t, ts + 0.5 / (6e7 / 60) / pmscore2.resolution)
                             for (t, ts) in pmscore2._tick_scales]
    pmscore2.write('/tmp/test_pmconv.mid')
    score2 = readsmf('/tmp/test_pmconv.mid')
    score2 = score2.Reject('mtype==M_EOT')
    for track in score2:
        track.duration -= 1
    del score2.smf_format
    del score2.smf_resolution
    round_tempo_values(score1)
    round_tempo_values(score2)
    with open('/tmp/score1.txt', 'w') as f:
        print(score1, file=f)
    with open('/tmp/score2.txt', 'w') as f:
        print(score2, file=f)
    print("******** Test 2: pretty_midi => Pytakt ********")
    cmd = 'diff /tmp/score1.txt /tmp/score2.txt'
    print(cmd)
    if os.system(cmd) == 0:
        print('Succeeded')

    # Check that a pretty_midi score first converted to Pytakt and then
    # converted back to pretty_midi is equivalent to the original.
    pmscore2 = pretty_midi.PrettyMIDI(args.MIDIFILE)
    score3 = PrettyMIDIToTakt().convert_to_takt(pmscore2)
    pmscore3 = TaktToPrettyMIDI().convert_to_pretty_midi(score3, DEFAULT_LIMIT)
    with open('/tmp/pmscore3.txt', 'w') as f:
        print_pmscore(pmscore2, f)
    print("******** Test 3: Pytakt => pretty_midi => Pytakt ********")
    cmd = 'diff /tmp/pmscore2.txt /tmp/pmscore3.txt'
    print(cmd)
    if os.system(cmd) == 0:
        print('Succeeded')
