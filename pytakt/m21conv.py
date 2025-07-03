# coding:utf-8
"""
This module defines classes that perform conversions to and from music21.
"""
"""
このモジュールには、music21への変換、および music21からの変換を行うクラスが
定義されています。
"""
# Copyright (C) 2025  Satoshi Nishimura

import music21
import numbers
import heapq
import warnings
import math
from fractions import Fraction
from pytakt.score import Score, EventList, EventStream, Tracks
from pytakt.event import NoteEvent, CtrlEvent, MetaEvent, TimeSignatureEvent, \
    KeySignatureEvent, TempoEvent, XmlEvent
from pytakt.pitch import Pitch, Key
from pytakt.constants import TICKS_PER_QUARTER, EPSILON, \
    M_TEXT, M_COPYRIGHT, M_TEMPO, M_TRACKNAME, M_INSTNAME, M_MARK, BEGIN, END
from pytakt.timemap import TimeSignatureMap
from pytakt.utils import Ticks, int_preferred, TaktWarning
from pytakt.chord import Chord
from typing import List, Tuple, Optional, Iterator, Union


NOTATIONS = {
    '.': (music21.articulations.Staccato, {}),
    'staccato': (music21.articulations.Staccato, {}),
    '>': (music21.articulations.Accent, {}),
    'accent': (music21.articulations.Accent, {}),
    '^': (music21.articulations.StrongAccent, {}),
    'strong-accent': (music21.articulations.StrongAccent, {}),
    '-': (music21.articulations.Tenuto, {}),
    'tenuto': (music21.articulations.Tenuto, {}),
    '-.': (music21.articulations.DetachedLegato, {}),
    'detached-legato': (music21.articulations.DetachedLegato, {}),
    'staccatissimo': (music21.articulations.Staccatissimo, {}),
    'spiccato': (music21.articulations.Spiccato, {}),
    'breath-mark': (music21.articulations.BreathMark, {}),
    'stress': (music21.articulations.Stress, {}),
    'unstress': (music21.articulations.Unstress, {}),
    'up-bow': (music21.articulations.UpBow, {}),
    'down-bow': (music21.articulations.DownBow, {}),
    'open-string': (music21.articulations.OpenString, {}),
    'harmonic': (music21.articulations.StringHarmonic, {}),
    'stopped': (music21.articulations.Stopped, {}),
    '1': (music21.articulations.Fingering, {'fingerNumber': 1}),
    '2': (music21.articulations.Fingering, {'fingerNumber': 2}),
    '3': (music21.articulations.Fingering, {'fingerNumber': 3}),
    '4': (music21.articulations.Fingering, {'fingerNumber': 4}),
    '5': (music21.articulations.Fingering, {'fingerNumber': 5}),
    'fermata': (music21.expressions.Fermata, {'type': 'upright'}),
    'inverted-fermata': (music21.expressions.Fermata, {'type': 'inverted'}),
    'trill': (music21.expressions.Trill, {}),
    'turn': (music21.expressions.Turn, {}),
    'inverted-turn': (music21.expressions.InvertedTurn, {}),
    'mordent': (music21.expressions.Mordent, {}),
    'inverted-mordent': (music21.expressions.InvertedMordent, {}),
}


CLASS_TO_NOTATIONS = {}
for sym, (cls, props) in NOTATIONS.items():
    CLASS_TO_NOTATIONS.setdefault(cls, []).append((props, sym))


class TaktToMusic21:
    TUPLET_DIVISORS = [3, 5, 7, 11, 13]
    TRIPLET_TIME_TOLERANCE = 0.1  # 0.25
    NOTE_ON_MATCH_REWARD = 1.0
    INEXACT_NOTE_ON_MATCH_REWARD = 0.75
    TUPLET_BEATLEN_REWARD = 0.6
    TUPLET_MIDNOTE_PENALTY = 0.5  # 1.0
    MATCH_QUALITY_THRESHOLD = 0.3
    NOTEOFF_QUANT_FACTOR = 2

    def gen_pitch(self, n):
        if not isinstance(n, numbers.Real):
            raise Exception("event with ill-typed note number")
        if isinstance(n, Pitch) and n >= 12:
            return music21.pitch.Pitch(n.tostr(sfn='#-'))
        else:
            return music21.pitch.Pitch(ps=n)

    def gen_duration(self, ticks, tupdiv=None):
        if isinstance(ticks, list):
            d = None
            for i, elm in enumerate(ticks):
                if i == 0:
                    d = self.gen_duration(elm, tupdiv)
                else:
                    d.addDurationTuple(self.gen_duration(elm, tupdiv))
            return d
        if ticks == 'grace:eighth':
            d = music21.duration.Duration('eighth').getGraceDuration()
        elif ticks == 'grace:16th':
            d = music21.duration.Duration('16th').getGraceDuration()
        elif tupdiv is not None:
            # 下のようにtupletsを指定しないと、三連符中の付点音符などで
            # 問題を生じる。
            t = music21.duration.Tuplet(tupdiv, 1 << (tupdiv.bit_length() - 1))
            d = music21.duration.Duration(ticks / (TICKS_PER_QUARTER *
                                                   t.tupletMultiplier()))
            d.tuplets = (t,)
        else:
            d = music21.duration.Duration(ticks / TICKS_PER_QUARTER)
        return d

    def gen_note(self, ev, duration, tupdiv=None):
        m21dur = self.gen_duration(duration, tupdiv)
        m21note = music21.note.Note(self.gen_pitch(ev.n), duration=m21dur)
        m21note.volume.velocity = ev.v
        if hasattr(ev, 'tie'):
            m21note.tie = music21.tie.Tie(
                (None, 'start', 'stop', 'continue')[ev.tie])
        if hasattr(ev, 'mark'):
            for mk in (ev.mark if isinstance(ev.mark, (list, tuple))
                       else (ev.mark,)):
                try:
                    cls, props = NOTATIONS[mk]
                except KeyError:
                    raise Exception('%r: Unknown mark type' % (mk,)) \
                        from None
                obj = cls()
                for k, v in props.items():
                    setattr(obj, k, v)
                if issubclass(cls, music21.expressions.Expression):
                    m21note.expressions.append(obj)
                else:
                    m21note.articulations.append(obj)
        return m21note

    def gen_chord(self, chord, duration, tupdiv=None):
        if len(chord) == 1:
            return self.gen_note(chord[0], duration, tupdiv)
        else:
            notes = tuple(self.gen_note(ev, duration, tupdiv)
                          for ev in sorted(chord, key=lambda ev: ev.n))
            m21chord = music21.chord.Chord(notes)
            for i, m21note in enumerate(notes):
                for cobjs, nobjs in \
                    ((m21chord.expressions, m21note.expressions),
                     (m21chord.articulations, m21note.articulations)):
                    for nobj in nobjs:
                        # Fingering以外は重複した指定を１つにする。Figeringの
                        # 場合コード構成音の順番に指定を並べる (その際、指定の
                        # ない音に対しては空の指定を挿入する）。
                        cnt = sum(type(nobj) is type(cobj) for cobj in cobjs)
                        if type(nobj) is music21.articulations.Fingering:
                            while cnt < i:
                                cobjs.append(type(nobj)())
                                cnt += 1
                            cobjs.append(nobj)
                        elif not cnt:
                            cobjs.append(nobj)
            return m21chord

    def gen_rest(self, duration, tupdiv=None):
        return music21.note.Rest(duration=self.gen_duration(duration, tupdiv))

    def gen_timesig(self, timesigev):
        if getattr(timesigev, 'common', None):
            if timesigev.num_den() == (4, 4):
                return music21.meter.TimeSignature('c')
            elif timesigev.num_den() == (2, 2):
                return music21.meter.TimeSignature('cut')
        return music21.meter.TimeSignature('%d/%d' % timesigev.num_den())

    def gen_keysig(self, keysigev):
        return music21.key.KeySignature(keysigev.value.signs)

    def gen_tempo(self, tempoev):
        m21tempo = music21.tempo.MetronomeMark(number=tempoev.value)
        m21tempo.placement = 'above'  # work in music21 8.3.0 but not in 6.7.1
        return m21tempo

    def gen_mark(self, ev):
        m21mark = music21.expressions.RehearsalMark(ev.value)
        m21mark.style.placement = 'above'
        m21mark.style.fontWeight = 'bold'
        return m21mark

    def checkstr(self, string):
        # decodeでsurrogateescapeに変換された文字列をmusic21へ渡すとエラーに
        # なるので、'replace'モードで変換し直す。
        try:
            string.encode('utf-8')
            return string
        except UnicodeEncodeError:
            warnings.warn("Unrecognized characters in text events. "
                          "Please check the 'encoding' argument when the "
                          "score is read from a MIDI file.",
                          TaktWarning)
            return string.encode(errors='surrogateescape').\
                decode(errors='replace')

    def gen_instname(self, ev):
        return music21.instrument.Instrument(self.checkstr(ev.value))

    def gen_clef(self, ev):
        sign = ev.value
        if sign.upper() in ('G', 'F', 'C') and \
           getattr(ev, 'line', None) is not None:
            sign += str(ev.line)
        return music21.clef.clefFromString(sign,
                                           getattr(ev, 'octave_change', 0))

    def gen_barline(self, ev):
        if ev.value == 'repeat-start' or ev.value == 'repeat-end':
            return music21.bar.Repeat(direction=ev.value[7:])
        else:
            return music21.bar.Barline(type=ev.value)

    def gen_chordsym(self, ev):
        chord = ev.value
        m21chordsym = music21.harmony.ChordSymbol(
            root=self.gen_pitch(chord.root),
            bass=None if chord.bass is None else self.gen_pitch(chord.bass),
            kind=chord.kind)
        for type, num, sf in chord.modifications:
            m21chordsym.addChordStepModification(
                music21.harmony.ChordStepModification(type, num, sf),
                updatePitches=True)
        return m21chordsym

    def gen_stafftext(self, ev):
        m21textexpr = music21.expressions.TextExpression(
            self.checkstr(ev.value))
        m21textexpr.placement = 'above'
        return m21textexpr

    def to_measures(self, evlist, tsigmap) -> List[EventList]:
        result = []
        quant = self.min_note
        for bar in evlist.chord_iterator(tsigmap.iterator()):
            newbar = EventList(duration=bar.duration, start=bar.start)
            for ev in bar:
                if isinstance(ev, NoteEvent):
                    # 小節区切りで音符を分割する
                    if ev.t < bar.start:
                        if self.quantize(ev.t, quant) < bar.start:
                            if self.quantize(ev.t + ev.L, quant) > bar.start:
                                # 前の小節からタイで継続している音符
                                ev = ev.copy().update(
                                    t=bar.start,
                                    L=ev.t + ev.L - bar.start,
                                    tie=getattr(ev, 'tie', 0) | END)
                            else:
                                # 小節区切りで終わる音符
                                continue
                        elif (self.quantize(ev.t + ev.L, quant) == bar.start
                              and (ev.t + ev.L - bar.start <
                                   self.GRACE_NOTE_THRES)):
                            # クオンタイズの結果zero-durationになり、かつ
                            # 音長が閾値未満のものは、前の小節のみに含める。
                            continue
                    if ev.t + ev.L > bar.duration:
                        if self.quantize(ev.t, quant) < bar.duration:
                            if self.quantize(ev.t + ev.L, quant) > \
                               bar.duration:
                                # 次の小節までタイで続く音符
                                ev = ev.copy().update(
                                    L=bar.duration - ev.t,
                                    tie=getattr(ev, 'tie', 0) | BEGIN)
                        elif (self.quantize(ev.t + ev.L, quant) > bar.duration
                              or (ev.t + ev.L - bar.duration >=
                                  self.GRACE_NOTE_THRES)):
                            continue
                newbar.append(ev)
            result.append(newbar)
        return result

    def quantize(self, time, quant) -> Ticks:
        # return int(time / quant + 0.5) * quant
        # return int(math.ceil(time / quant - 0.5)) * quant
        return math.ceil((time + self.GRACE_NOTE_THRES) / quant - 1) * quant

    def noteoff_quantize(self, t, L, nexttime, quant, offquant):
        qtime = self.quantize(t, quant)
        # 下の (offquant-quant)/2 は、修正値の平均を note-on, note-off ともに
        # -quant/2にするための補正
        qofftime = max(self.quantize(t + L + (offquant - quant) / 2, offquant),
                       qtime)

        # 元の音価がスレッショルド以下でない限り、zero-durationを避ける。
        if qofftime <= qtime and L >= self.GRACE_NOTE_THRES:
            # qofftime を、qtimeを超える一番近い offquantの倍数にする。
            qofftime = math.floor(qtime / offquant + 1) * offquant

        # nexttime = qofftime + quant (過少ギャップ), nexttime = qofftime -
        # quant (過少オーバーラップ) の場合は、それによって zero-duration に
        # なる場合を除き、qofftime = nexttime とする。
        if (nexttime == qofftime + quant or nexttime == qofftime - quant) and \
           nexttime != qtime:
            qofftime = nexttime

        return qofftime

    def assign_voices(self, evlist) -> List[EventList]:
        # evlist は NoteEvent以外を含んではいけない
        def is_available(voice_evlist, ev):
            # ev を voice_evlist に置けるなら True を返す。
            # これは、(1) voice_evlist が空、(2) voice_evlist の最後の
            # イベントのノートオン・ノートオフ時刻が ev のそれと一致する
            # (つまり、コードを形成する)、あるいは (3) ev のノートオン時刻が
            # voice_evlist の最後のイベントのノートオフ時刻以降であるときに
            # True になる。
            if not voice_evlist:
                return True
            lastev = voice_evlist[-1]
            offquant = self.min_note * self.NOTEOFF_QUANT_FACTOR
            lastev_qtime = self.quantize(lastev.t, self.min_note)
            ev_qtime = self.quantize(ev.t, self.min_note)
            lastev_offtime = self.noteoff_quantize(
                lastev.t, lastev.L, ev_qtime, self.min_note, offquant)
            ev_offtime = self.noteoff_quantize(
                ev.t, ev.L, ev_qtime, self.min_note, offquant)
            return ((lastev_qtime == ev_qtime and
                     (lastev_offtime == ev_offtime or ev_offtime == ev_qtime))
                    or lastev_offtime <= ev_qtime)

        designated_voices = [EventList([], evlist.duration, **evlist.__dict__)]
        free_voices = []

        for ev in evlist:
            done = False
            if hasattr(ev, 'voice') and ev.voice > 0:
                while len(designated_voices) < ev.voice:
                    designated_voices.append(EventList([], evlist.duration,
                                                       **evlist.__dict__))
                designated_voices[ev.voice - 1].append(ev)
            else:
                for voice_evlist in free_voices:
                    if is_available(voice_evlist, ev):
                        voice_evlist.append(ev)
                        done = True
                        break
                if not done:
                    free_voices.append(EventList([ev], evlist.duration,
                                                 **evlist.__dict__))

        # free_voices をピッチの平均値でソート
        for voice_evlist in free_voices:
            voice_evlist.avr_pitch = sum(ev.n for ev in voice_evlist) \
                                     / max(len(voice_evlist), 1)
        free_voices.sort(key=lambda voice_evlist: -voice_evlist.avr_pitch)

        # designated_voices の中で空のところに free_voices の要素を移す
        for i in range(len(designated_voices)):
            if not free_voices:
                break
            if not designated_voices[i]:
                designated_voices[i] = free_voices.pop(0)
        designated_voices.extend(free_voices)
        return designated_voices

    def round_to_tuplet_time(self, time, div) -> Optional[Ticks]:
        """ 連符での最初の音以外の時刻に近いかを調べ、そうであれば、
        その時刻へ丸めたものを返す。さもなければ None を返す。"""
        # unitは min_note の音符で表したときの個々の連符の長さ
        unit = self.min_note * (1 << (div.bit_length() - 1)) / div
        tolerance = unit * self.TRIPLET_TIME_TOLERANCE if div == 3 else EPSILON
        (q, r) = divmod(time, unit)
        if r < tolerance and (q % div) != 0:
            return q * unit
        elif r > unit - tolerance and ((q+1) % div) != 0:
            return (q+1) * unit
        else:
            return None

    def search_tuplet(self, evlist, idx, tsig, barbegin, barend,
                      lowerbound) -> Optional[Tuple[int, Ticks, Ticks]]:
        """ evlist[idx] のイベントを含む連符の可能性を調べ、連符にすべきとき
        は、分割数と連符区間の開始時刻、区間長のタプルを返す。
        barbegin, barend は小節の開始時刻と終了時刻。lowerboundは、
        それ未満の時刻から開始する連符を禁止する。"""

        def get_match_quality(time, div, tupletlen):
            # time は連符区間の中のある一時刻。これから連符区間が求められる。
            unit = tupletlen / div
            tolerance = unit * self.TRIPLET_TIME_TOLERANCE if div == 3 \
                else EPSILON
            tstart = ((time - barbegin) // tupletlen) * tupletlen + barbegin
            if tstart < lowerbound:
                return (tstart, -math.inf)
            idx = 0
            while (idx < len(evlist) and
                   evlist[idx].t + tolerance < tstart):
                idx += 1
            result = 0
            while (idx < len(evlist) and
                   evlist[idx].t < tstart + tupletlen - tolerance):
                # ノートオン時刻が連符の時刻に該当するなら報酬を与える。
                # 連符内の1/2音価に該当する場合はペナルティを与える。
                # それ以外のノートオン時刻を含む場合は候補から外す。
                ontime = evlist[idx].t
                if ontime >= tstart + tolerance:
                    if (ontime - tstart + EPSILON) % unit <= EPSILON*2:
                        result += self.NOTE_ON_MATCH_REWARD
                    elif (div == 3 and
                          (ontime - tstart + tolerance) % unit <= tolerance*2):
                        result += self.INEXACT_NOTE_ON_MATCH_REWARD
                    elif ((ontime - tstart + tolerance) % (unit/2)
                          <= tolerance*2):
                        result -= self.TUPLET_MIDNOTE_PENALTY
                    else:
                        result = 0
                        break
                idx += 1
            return (tstart, result)

        def len_list(div):  # 連符区間長の候補
            # 例えば4/4拍子で2,3拍目にまたがる連符は除外した方が良いか？
            L = self.min_note * (1 << (div.bit_length() - 1))
            while L <= barend - barbegin:
                yield L
                L *= 2

        # print('search_tuplet:', evlist[idx])

        # eventsは、evlist[idx]と、それと同時刻のものを除いた次のイベントから
        # なる長さ高々2のリスト。連符が存在するときは、この中に連符区間の
        # 最初と最後以外の時刻の音符が含まれているはずである。
        events = [evlist[idx]]
        for idx2 in range(idx + 1, len(evlist)):
            if evlist[idx2].t > evlist[idx].t + EPSILON:
                events.append(evlist[idx2])
                break
        best_quality = 0
        best_tuplet = None
        for div in self.TUPLET_DIVISORS:
            for ev in events:
                time = self.round_to_tuplet_time(ev.t, div)
                if time is None:
                    continue
                for tupletlen in len_list(div):
                    tstart, quality = get_match_quality(time, div, tupletlen)
                    if tupletlen == tsig.beat_length():
                        quality += self.TUPLET_BEATLEN_REWARD
                    # print((div, tstart, tupletlen), ' quality=', quality)
                    if quality >= best_quality:
                        best_quality = quality
                        best_tuplet = (div, tstart, tupletlen)
        if best_tuplet is not None and \
           best_quality / best_tuplet[0] < self.MATCH_QUALITY_THRESHOLD:
            return None
        # print('best:', best_tuplet, f' quality={best_quality}')
        return best_tuplet

    def output_stream(self, evlist, tsig, allow_tuplet, out):
        cur_time = evlist.start
        chordbuf = []  # 出力バッファ

        def divide_duration(begin, end, quant, tupdiv, is_rest) -> List[Ticks]:
            """ 楽譜を読みやすくするために音符・休符を分割する。"""
            def beat_div(duration):
                return 3 if (tsig.numerator() % 3 == 0 and
                             duration == tsig.beat_length()) else 2
            result = []
            d = quant
            k = beat_div(d)
            while begin + d < end:
                nextk = beat_div(d * k)
                r = (begin - evlist.start) % (d * k)
                if r > 0 or k == 3:  # k==3 は 6/8拍子でc*c のようなときに働く
                    if begin + ((d * k) - r) >= end:
                        break
                    if (not is_rest and k == 2 and
                        ((end - begin) in (d*2, d*3)) and
                        (tuplet or
                         (begin + d - evlist.start) % (d * k * nextk) > 0)):
                        # 'c/cc/' や 'c/c.' のときは、2レベル以上越えてまたぐ
                        # 区間でない限り、分割しない
                        break
                    result.append((d * k) - r)
                    begin += (d * k) - r
                d *= k
                k = nextk
                if tupdiv:
                    break
            if end > begin:
                result.append(end - begin)
            return result

        def output_rest(begin, end, stream, tupdiv, quant):
            duration = divide_duration(begin, end, quant, tupdiv, True)
            if duration:
                stream.append(self.gen_rest(duration, tupdiv))

        def split_note(ev, time):
            """ タイで分割する手続き """
            ev1 = ev.copy()
            ev1.L = time - ev1.t
            ev1.tie = getattr(ev1, 'tie', 0) | BEGIN
            ev2 = ev.copy()
            ev2.L -= time - ev2.t
            ev2.t = time
            ev2.tie = getattr(ev2, 'tie', 0) | END
            return (ev1, ev2)

        def output_grace_notes(events, stream, tupdiv, after=False):
            """ quantize step未満の音符を装飾音符で出力する。afterは後打音の
            とき True """
            buf = []
            k1 = 0
            while k1 < len(events):
                k2 = k1
                while (k2 < len(events) and
                       events[k2].t - events[k1].t < EPSILON):
                    k2 += 1
                buf.append(events[k1:k2])
                k1 = k2
            dur = 'grace:16th' if len(buf) >= 2 or after else 'grace:eighth'
            for chord in buf:
                stream.append(self.gen_chord(chord, dur, tupdiv))

        def flush_until(flushtime, stream, tupdiv, quant, offquant):
            """ chordbufの内容を時刻flushtimeになるまで排出 """
            nonlocal cur_time, chordbuf
            tlist = []
            qflushtime = self.quantize(flushtime, quant)
            # print(f'flush_until({flushtime}, tupdiv={tupdiv}, quant={quant},'
            #       f' offquant={offquant}) qflushtime={qflushtime}')
            for ev in chordbuf:
                qofftime = self.noteoff_quantize(ev.t, ev.L, qflushtime,
                                                 quant, offquant)
                # mml('[{L=L128 ceg} ^c]').Voice(1) の例で下のmaxが必要になる
                #   qofftime = max(qofftime, cur_time)
                if qofftime < qflushtime:
                    tlist.append(qofftime)
            tlist.append(qflushtime)
            tlist = sorted(set(tlist))  # 重複除去＆ソート
            for t in tlist:
                this_chord = []
                short_notes = []
                new_chord = []
                for ev in chordbuf:
                    qt = self.quantize(ev.t, quant)
                    qofft = self.noteoff_quantize(ev.t, ev.L, qflushtime,
                                                  quant, offquant)
                    if qt == t:
                        # flushtimeから始まる音符 (qt > t はあり得ない)。
                        # もしくは、t から始まる zero-duration の音符
                        # (zero-durationでもそのあとに休符が続く場合は、
                        # 装飾音でなく通常の音符にしたいため、今すぐに出力
                        # するのはまずい)。
                        new_chord.append(ev)
                    elif qofft > t:
                        # 以後も継続する音符をタイで分割
                        (tev, ev) = split_note(ev, t)
                        this_chord.append(tev)
                        new_chord.append(ev)
                    elif qofft == qt:
                        # zero-duration の場合
                        short_notes.append(ev)
                    else:
                        this_chord.append(ev)
                # print(cur_time, t, f'chord={this_chord} short={short_notes}')
                if this_chord:
                    output_grace_notes(short_notes, stream, tupdiv)
                    duration = divide_duration(cur_time, t, quant,
                                               tupdiv, False)
                    if duration:
                        stream.append(
                            self.gen_chord(this_chord, duration, tupdiv))
                    cur_time = t
                elif short_notes:
                    # short_notesだけが残った場合は、最後の音符および、それと
                    # クオンタイズ前の時刻がほぼ同じものを通常の音符として
                    # 出力し、それより前のものは装飾音符として出力する。
                    k = 0
                    while short_notes[k].t < short_notes[-1].t - EPSILON:
                        k += 1
                    output_grace_notes(short_notes[0:k], stream, tupdiv)
                    d = min(t, int(cur_time / offquant + 1)
                            * offquant) - cur_time
                    stream.append(self.gen_chord(short_notes[k:], d, tupdiv))
                    output_rest(cur_time + d, t, stream, tupdiv, quant)
                    cur_time = t
                chordbuf = new_chord
            output_rest(cur_time, qflushtime, stream, tupdiv, quant)
            cur_time = qflushtime

        def output_note(ev, stream, tupdiv, quant, offquant):
            """ 必要なら出力バッファをフラッシュしてから、音符を出力バッファに
            置く。"""
            flush_until(ev.t, stream, tupdiv, quant, offquant)
            chordbuf.append(ev)

        # メイン
        idx = 0
        while idx < len(evlist):
            tuplet = allow_tuplet and \
                     self.search_tuplet(evlist, idx, tsig, evlist.start,
                                        evlist.duration, cur_time)
            if not tuplet:
                output_note(evlist[idx], out, None, self.min_note,
                            self.min_note * self.NOTEOFF_QUANT_FACTOR)
                idx += 1
            else:
                div, tstart, tupletlen = tuplet
                assert tstart >= cur_time
                tend = tstart + tupletlen
                tquant = Fraction(tupletlen, div)
                toffquant = tquant
                if tquant > self.min_note:
                    tquant /= 2
                if toffquant > self.min_note * self.NOTEOFF_QUANT_FACTOR:
                    toffquant /= 2
                pidx = idx
                while pidx < len(evlist):
                    pev = evlist[pidx]
                    pqt = self.quantize(pev.t, tquant)
                    if pqt >= tstart:
                        break
                    if self.quantize(pev.t + pev.L, tquant) > tstart:
                        # 連符の前から続く音符をタイで分割する。
                        (pev, evlist[pidx]) = split_note(pev, tstart)
                    else:
                        evlist[idx+1:pidx+1] = evlist[idx:pidx]
                        idx += 1
                    output_note(pev, out, None, self.min_note,
                                self.min_note * self.NOTEOFF_QUANT_FACTOR)
                    pidx += 1
                flush_until(tstart, out, None, self.min_note,
                            self.min_note * self.NOTEOFF_QUANT_FACTOR)
                sub = music21.stream.Stream()
                nextidx = idx
                while idx < len(evlist):
                    ev = evlist[idx]
                    qt = self.quantize(ev.t, tquant)
                    if qt >= tend:
                        break
                    if self.quantize(ev.t + ev.L, self.min_note) > tend:
                        # 連符の後まで続く音符をタイで分割する。
                        (ev, evlist[idx]) = split_note(ev, tend)
                    else:
                        nextidx += 1
                    output_note(ev, sub, div, tquant, toffquant)
                    idx += 1
                flush_until(tend, sub, div, tquant, toffquant)
                if len(sub[0].duration.tuplets) > 0 and \
                   len(sub[-1].duration.tuplets) > 0:
                    # 連符の最初と最後にマークをつける
                    sub[0].duration.tuplets[0].type = 'start'
                    sub[-1].duration.tuplets[0].type = 'stop'
                out.append(list(sub))
                cur_time = tend
                idx = nextidx
        flush_until(evlist.duration, out, None, self.min_note,
                    self.min_note * self.NOTEOFF_QUANT_FACTOR)
        # 小節の終了時刻にある zero-duration notes を出力。
        output_grace_notes(chordbuf, out, None, True)

    def convert_to_music21(self, score, min_note, bar0len, allow_tuplet,
                           limit) -> music21.stream.Score:
        if isinstance(score, EventStream) and score.is_consumed():
            raise Exception(
                'convert_to_music21: Input stream has already been consumed')
        self.min_note = min_note
        # 音価がGRACS_NOTE_THRES未満のものは原則として装飾音にする
        self.GRACE_NOTE_THRES = min_note / 4
        evlist = EventList(score, limit=limit).Reject(CtrlEvent) \
            .PairNoteEvents()  # .Quantize(min_note, saveorg=True)
        tracks = evlist.ToTracks()
        keysigs = tracks.Filter(KeySignatureEvent)
        tsigmap = TimeSignatureMap(tracks[0], bar0len)
        metaevents = evlist.Filter(MetaEvent)
        m21score = music21.stream.Score()
        m21metadata = music21.metadata.Metadata()
        for ev in metaevents:
            if ev.mtype == M_TEXT and ev.tk == 0:
                if m21metadata.title is None:
                    m21metadata.title = self.checkstr(ev.value)
                elif ev.value.startswith('Composer: '):
                    m21metadata.composer = self.checkstr(ev.value[10:])
            elif ev.mtype == M_COPYRIGHT:
                msg = self.checkstr(ev.value)
                m21metadata.copyright = music21.metadata.Copyright(
                    msg if m21metadata.copyright is None else
                    str(m21metadata.copyright) + ', ' + msg)

        skip0 = tracks and not tracks[0].Filter(NoteEvent)
        for track_number, track_evlist in enumerate(tracks):
            if (track_number == 0 and skip0) or not track_evlist:
                continue
            if skip0:
                # track 0 をスキップしたときは、その中のXmlEventを
                # 最初の空でないトラックに移動する。
                track_evlist = tracks[0].Filter(XmlEvent) & track_evlist
                track_evlist.sort()
                skip0 = False
            measures = self.to_measures(track_evlist, tsigmap)
            m21part = music21.stream.Part(id=f'Track {track_number}')
            # 下のコードは　m21part に stream.Measure以外の要素を置かない
            # ことを前提としている
            last_tsig = None
            keysig0 = keysigs[0].copy()
            keysig = keysigs[track_number].copy()

            for meas_index, meas_evlist in enumerate(measures):
                m21measure = music21.stream.Measure(
                    number=meas_index + tsigmap.ticks2mbt(0)[0])

                # insert key signature if any
                while keysig and keysig[0].t <= meas_evlist.start:
                    m21measure.append(self.gen_keysig(keysig.pop(0)))
                    keysig0 = None
                while keysig0 and keysig0[0].t <= meas_evlist.start:
                    m21measure.append(self.gen_keysig(keysig0.pop(0)))

                # insert time signature if any
                if meas_index == 0 and tsigmap.ticks2mbt(0)[0] == 0:
                    # 弱起がある場合、小節番号1の拍子を小節番号0でも使う。
                    tsig = tsigmap.timesig_at(tsigmap.mbt2ticks(1))
                else:
                    tsig = tsigmap.timesig_at(meas_evlist.start + EPSILON)
                if tsig is not last_tsig and not hasattr(tsig, 'default'):
                    m21measure.append(self.gen_timesig(tsig))
                    last_tsig = tsig

                # insert notes and rests
                voices = self.assign_voices(meas_evlist.Filter(NoteEvent))
                for voice_idx, voice_evlist in enumerate(voices):
                    if len(voices) >= 2:
                        out = music21.stream.Voice(id=str(voice_idx+1))
                        self.output_stream(voice_evlist, tsig,
                                           allow_tuplet, out)
                        for elm in out:
                            if isinstance(elm, (music21.note.Note,
                                                music21.chord.Chord)):
                                elm.stemDirection = ('up' if voice_idx % 2 == 0
                                                     else 'down')
                        m21measure.insert(0, out)
                    else:
                        self.output_stream(voice_evlist, tsig,
                                           allow_tuplet, m21measure)

                # insert tempo if eny
                while metaevents and metaevents[0].t < meas_evlist.duration:
                    ev = metaevents.pop(0)
                    offset = (ev.t - meas_evlist.start) / TICKS_PER_QUARTER
                    if ev.mtype == M_TEMPO:
                        m21measure.insert(offset, self.gen_tempo(ev))
                    elif ev.mtype == M_MARK:
                        m21measure.insert(offset, self.gen_mark(ev))

                # insert other events if eny
                for ev in meas_evlist:
                    offset = (ev.t - meas_evlist.start) / TICKS_PER_QUARTER
                    if isinstance(ev, MetaEvent) and ev.mtype == M_TRACKNAME:
                        if not m21part.partName:
                            m21part.partName = self.checkstr(ev.value)
                        elif not m21part.partAbbreviation:
                            # 2つ目の TrackNameイベント
                            m21part.partAbbreviation = self.checkstr(ev.value)
                    elif isinstance(ev, MetaEvent) and ev.mtype == M_INSTNAME:
                        m21measure.insert(offset, self.gen_instname(ev))
                    elif isinstance(ev, XmlEvent) and ev.xtype == 'clef':
                        m21measure.insert(offset, self.gen_clef(ev))
                    elif isinstance(ev, XmlEvent) and ev.xtype == 'barline':
                        if offset == 0 and meas_index != 0 and \
                           ev.value != 'repeat-start':
                            m21part[-1].rightBarline = self.gen_barline(ev)
                        else:
                            # 小節の中間のbarlineは、少なくともmusic21 version
                            # 6.7.1 では、MusicXMLに出力されないようだ。
                            m21measure.insert(offset, self.gen_barline(ev))
                    elif isinstance(ev, XmlEvent) and ev.xtype == 'chord':
                        m21measure.insert(offset, self.gen_chordsym(ev))
                    elif isinstance(ev, XmlEvent) and ev.xtype == 'text':
                        m21measure.insert(offset, self.gen_stafftext(ev))

                if meas_index == 0 and tsigmap.ticks2mbt(0)[0] == 0:
                    m21measure.padAsAnacrusis()

                m21part.append(m21measure)

            if m21part:
                # default clef
                if not m21part[0].hasElementOfClass(music21.clef.Clef):
                    # ChordSymbolは取り除かないと予期しない影響を及ぼすようだ
                    s = m21part.flat.getElementsNotOfClass(
                        music21.harmony.ChordSymbol)
                    default_clef = music21.clef.bestClef(s)
                    m21part[0].insert(0, default_clef)
                # default final bar-line
                barlines = m21part[-1].getElementsByClass(music21.bar.Barline)
                if all(bl.offset == 0 for bl in barlines):
                    m21part[-1].rightBarline = 'final'

            m21score.insert(0, m21part)

        m21score.insert(0, m21metadata)
        return m21score


_CHORD_ALIAS = {
    'dominant-seventh': ('dominant', []),
    'minor-major-seventh': ('major-minor', []),
    'augmented-major-seventh': ('augmented', [('add', 7, 1)]),
    'half-diminished-seventh': ('half-diminished', []),
    'seventh-flat-five': ('dominant', [('alter', 5, -1)]),
    'minor-major-ninth': ('major-minor', [('add', 9, 0)]),
    'augmented-major-ninth': ('augmented', [('add', 7, 1), ('add', 9, 0)]),
    'augmented-dominant-ninth': ('augmented-seventh', [('add', 9, 0)]),
    'half-diminished-ninth': ('half-diminished', [('add', 9, 0)]),
    'half-diminished-minor-ninth': ('half-diminished', [('add', 9, -1)]),
    'diminished-ninth': ('diminished-seventh', [('add', 9, 0)]),
    'diminished-minor-ninth': ('diminished-seventh', [('add', 9, -1)]),
    'minor-major-11th': ('major-minor', [('add', 9, 0), ('add', 11, 0)]),
    'augmented-major-11th': ('augmented', [('add', 7, 1), ('add', 9, 0),
                                           ('add', 11, 0)]),
    'augmented-11th': ('augmented-seventh', [('add', 9, 0), ('add', 11, 0)]),
    # 11thだけ "-dominant" がついて無かったので、念のため下を追加
    'augmented-dominant-11th': ('augmented-seventh', [('add', 9, 0),
                                                      ('add', 11, 0)]),
    'half-diminished-11th': ('half-diminished', [('add', 9, -1),
                                                 ('add', 11, 0)]),
    'diminished-11th': ('diminished-seventh', [('add', 9, -1),
                                               ('add', 11, -1)]),
    'minor-major-13th': ('major-minor', [('add', 9, 0), ('add', 11, 0),
                                         ('add', 13, 0)]),
    'augmented-major-13th': ('augmented', [('add', 7, 1), ('add', 9, 0),
                                           ('add', 11, 0), ('add', 13, 0)]),
    'augmented-dominant-13th': ('augmented-seventh', [('add', 9, 0),
                                                      ('add', 11, 0),
                                                      ('add', 13, 0)]),
    'half-diminished-13th': ('half-diminished', [('add', 9, 0),  # b9?
                                                 ('add', 11, 0),
                                                 ('add', 13, 0)]),
    'suspended-fourth-seventh': ('suspended-fourth', [('add', 7, 0)]),
}


class Music21ToTakt:
    def conv_duration(self, m21duration) -> Ticks:
        return int_preferred(m21duration.quarterLength * TICKS_PER_QUARTER)

    def conv_pitch(self, m21pitch) -> Union[Pitch, int]:
        if 12 <= m21pitch.midi <= 127 and -2 <= m21pitch.alter <= 2 and \
           m21pitch.alter == int(m21pitch.alter):
            return Pitch(m21pitch.nameWithOctave)
        else:
            return int_preferred(m21pitch.ps)

    def conv_note(self, m21elm, offset, tknum, voice_idx) -> List[NoteEvent]:
        def create_note_event(m21note, note_idx):
            ev = NoteEvent(t=(int_preferred(offset * TICKS_PER_QUARTER) +
                              self.grace_count),
                           n=self.conv_pitch(m21note.pitch),
                           L=self.conv_duration(m21note.duration),
                           v=max(1, round(m21note.volume.getRealized() * 127)),
                           tk=tknum)
            if m21note.tie is not None:
                if m21note.tie.type == 'start':
                    ev.tie = BEGIN
                elif m21note.tie.type == 'stop':
                    ev.tie = END
                elif m21note.tie.type == 'continue':
                    ev.tie = BEGIN | END
            if voice_idx is not None:
                ev.voice = voice_idx

            fingering_count = 0
            for mk in m21elm.articulations + m21elm.expressions:
                if type(mk) is music21.articulations.Fingering:
                    fingering_count += 1
                    if fingering_count - 1 != note_idx:
                        continue
                try:
                    for props, sym in CLASS_TO_NOTATIONS[type(mk)]:
                        if all(getattr(mk, k) == v for k, v in props.items()):
                            if not hasattr(ev, 'mark'):
                                ev.mark = sym
                            elif not isinstance(ev.mark, tuple):
                                ev.mark = (ev.mark, sym)
                            else:
                                ev.mark = (*ev.mark, sym)
                            break
                except KeyError:
                    pass

            return ev

        # grace_countは装飾音内のコードや、前/後打音を区別するためdelta-tick
        if not isinstance(m21elm.duration, music21.duration.GraceDuration):
            self.grace_count = 0
            self.grace_notes_in_process.clear()

        if isinstance(m21elm, music21.chord.Chord):
            result = [create_note_event(m21note, i)
                      for i, m21note in enumerate(m21elm.notes)]
        else:
            result = [create_note_event(m21elm, 0)]

        if isinstance(m21elm.duration, music21.duration.GraceDuration):
            m = m21elm.getContextByClass(music21.stream.Measure)
            # 下の比較は、後打音の場合、measureNumberは元々の小節番号なのに
            # 対して、flatten後にgetContextByClassで得られるのは次の小節である
            # ことを利用して、後打音の検出をしている。
            if m21elm.measureNumber is not None and \
               m21elm.measureNumber != m.number:
                self.grace_notes_in_process.extend(result)
                for ev in self.grace_notes_in_process:
                    ev.t -= 1
            else:
                self.grace_count += 1

        return result

    def conv_timesig(self, m21timesig, offset) -> TimeSignatureEvent:
        ev = TimeSignatureEvent(int_preferred(offset * TICKS_PER_QUARTER),
                                m21timesig.numerator, m21timesig.denominator)
        if m21timesig.symbol in ['common', 'cut']:
            ev.common = True
        return ev

    def conv_keysig(self, m21keysig, offset) -> Union[None, KeySignatureEvent]:
        if m21keysig.isNonTraditional or abs(m21keysig.sharps) > 11:
            warnings.warn("Skipping a non-traditional key signature",
                          TaktWarning)
            return None
        if not isinstance(m21keysig, music21.key.Key):
            m21keysig = m21keysig.asKey()
        mode = 0
        if m21keysig.mode == 'minor':
            mode = 1
        elif m21keysig.mode != 'major':
            warnings.warn(f"Mode {m21keysig.mode!r} is changed to 'major'",
                          TaktWarning)
        return KeySignatureEvent(int_preferred(offset * TICKS_PER_QUARTER),
                                 Key(m21keysig.sharps, mode, True))

    def conv_tempo(self, m21tempo, offset) -> TempoEvent:
        return TempoEvent(int_preferred(offset * TICKS_PER_QUARTER),
                          m21tempo.getQuarterBPM())

    def conv_mark(self, m21mark, offset) -> MetaEvent:
        return MetaEvent(int_preferred(offset * TICKS_PER_QUARTER),
                         M_MARK, m21mark.content)

    def conv_partname(self, m21part, tknum) -> List[MetaEvent]:
        result = [MetaEvent(0, M_TRACKNAME, m21part.partName, tknum)]
        if m21part.partAbbreviation:
            # 省略名があるときは、2つ目のイベントとして出力する。
            result.append(
                MetaEvent(0, M_TRACKNAME, m21part.partAbbreviation, tknum))
        return result

    def conv_instname(self, m21instrument, offset, tknum) -> MetaEvent:
        return MetaEvent(int_preferred(offset * TICKS_PER_QUARTER),
                         M_INSTNAME, m21instrument.instrumentName, tknum)

    def conv_clef(self, m21clef, offset, tknum) -> XmlEvent:
        return XmlEvent(int_preferred(offset * TICKS_PER_QUARTER),
                        'clef', m21clef.sign, tknum, line=m21clef.line,
                        octave_change=m21clef.octaveChange)

    def conv_barline(self, m21elm, offset, tknum) -> XmlEvent:
        return XmlEvent(int_preferred(offset * TICKS_PER_QUARTER),
                        'barline', "repeat-" + m21elm.direction
                        if isinstance(m21elm, music21.bar.Repeat)
                        else m21elm.type, tknum)

    def conv_chordsym(self, m21chordsym, offset, tknum) -> Optional[XmlEvent]:
        kind = m21chordsym.chordKind
        modifications = [(m.modType, m.degree,
                          int(m.interval) if isinstance(m.interval,
                                                        numbers.Real)
                          else m.interval.semitones)
                         for m in m21chordsym.getChordStepModifications()]
        try:
            # convert chords defined only in Music21
            kind, mods = _CHORD_ALIAS[kind]
            modifications = mods + modifications
        except KeyError:
            pass

        try:
            chord = Chord(kind=kind,
                          root=self.conv_pitch(m21chordsym.root()),
                          bass=self.conv_pitch(m21chordsym.bass()),
                          modifications=modifications)
        except Exception as e:
            warnings.warn("Skipping an unsupported chord: %s" % str(e),
                          TaktWarning)
            return None
        return XmlEvent(int_preferred(offset * TICKS_PER_QUARTER),
                        'chord', chord, tknum)

    def conv_stafftext(self, m21textexpr, offset, tknum) -> XmlEvent:
        return XmlEvent(int_preferred(offset * TICKS_PER_QUARTER),
                        'text', m21textexpr.content, tknum)

    def conv_metadata(self, m21metadata) -> List[MetaEvent]:
        result = []
        if m21metadata.title is not None:
            result.append(MetaEvent(0, M_TEXT, m21metadata.title, tk=0))
        elif m21metadata.movementName is not None:
            result.append(MetaEvent(0, M_TEXT, m21metadata.movementName, tk=0))
        if m21metadata.composer is not None:
            result.append(MetaEvent(0, M_TEXT,
                                    'Composer: ' + m21metadata.composer, tk=0))
        if m21metadata.copyright is not None:
            result.append(MetaEvent(0, M_COPYRIGHT,
                                    str(m21metadata.copyright), tk=0))
        return result

    def move_metaevents_to_track0(self, tracks, bar0len) -> None:
        keysigs = tracks.Filter(KeySignatureEvent)
        # トラックごとに異なる key/time signature を持っている場合は移動しない
        move_keysigs = len(tracks) < 3 or all(keysigs[i] == keysigs[1]
                                              for i in range(2, len(tracks)))
        timesigs = tracks.Filter(TimeSignatureEvent)
        move_timesigs = len(tracks) < 3 or all(timesigs[i] == timesigs[1]
                                               for i in range(2, len(tracks)))
        tempodict = {}  # 重複除去用
        for tknum in range(1, len(tracks)):
            newlist = EventList(duration=tracks[tknum].duration)
            for ev in tracks[tknum]:
                if isinstance(ev, KeySignatureEvent):
                    if move_keysigs:
                        if tknum == 1:
                            tracks[0].append(ev)
                        continue
                    else:
                        ev.tk = tknum
                elif isinstance(ev, TimeSignatureEvent):
                    if move_timesigs:
                        if tknum == 1:
                            tracks[0].append(ev)
                        continue
                    else:
                        ev.tk = tknum
                elif isinstance(ev, TempoEvent):
                    if tempodict.get(ev.t, None) != ev.value:
                        tracks[0].append(ev)
                        tempodict[ev.t] = ev.value
                    continue
                newlist.append(ev)
            tracks[tknum] = newlist

    def create_voice_map(self, m21part, voice_map, voice_idx=None) -> None:
        if isinstance(m21part, music21.stream.Voice):
            for elm in m21part:
                if isinstance(elm, (music21.note.Note, music21.chord.Chord)):
                    if voice_idx is not None:
                        voice_map[elm.id] = voice_idx
        elif isinstance(m21part, music21.stream.Stream):
            voice_idx = 0
            for elm in m21part:
                if isinstance(elm, music21.stream.Voice):
                    voice_idx += 1
                    self.create_voice_map(elm, voice_map, voice_idx)
                else:
                    self.create_voice_map(elm, voice_map)

    def convert_to_takt(self, m21score) -> Tracks:
        tracks = Tracks()
        track0 = EventList()
        tracks.append(track0)
        maxduration = 0
        bar0len = None
        tknum = 1
        m21metadata = m21score.getElementsByClass(music21.metadata.Metadata)
        if m21metadata:
            track0.extend(self.conv_metadata(m21metadata[0]))
        m21parts = m21score.getElementsByClass(music21.stream.Part)
        if not m21parts:
            m21parts = [m21score]
        for m21part in m21parts:
            duration = int_preferred(m21part.highestTime * TICKS_PER_QUARTER)
            maxduration = max(maxduration, duration)
            evlist = EventList()
            if getattr(m21part, 'partName', None):
                evlist.extend(self.conv_partname(m21part, tknum))
            try:
                # 小節番号0の小節の長さを得る
                firstmeas = m21part.getElementsByClass(
                    music21.stream.Measure)[0]
                if firstmeas.duration.quarterLength < \
                   firstmeas.barDuration.quarterLength:  # 弱起のとき
                    bar0len = firstmeas.duration.quarterLength
            except IndexError:
                pass
            voice_map = {}
            self.grace_count = 0
            self.grace_notes_in_process = []
            self.create_voice_map(m21part, voice_map)
            flattened = m21part.flat
            ksclass = music21.key.Key if flattened.hasElementOfClass(
                music21.key.Key) else music21.key.KeySignature
            for m21elm in flattened:
                if isinstance(m21elm, music21.note.Note) or \
                   type(m21elm) is music21.chord.Chord:
                    evlist.extend(
                        self.conv_note(m21elm, m21elm.offset, tknum,
                                       voice_map.get(m21elm.id, None)))
                elif isinstance(m21elm, ksclass):
                    keysigev = self.conv_keysig(m21elm, m21elm.offset)
                    if keysigev is not None:
                        evlist.append(keysigev)
                elif isinstance(m21elm, music21.meter.TimeSignature):
                    evlist.append(self.conv_timesig(m21elm, m21elm.offset))
                    if bar0len is not None and m21elm.offset < bar0len:
                        evlist.append(self.conv_timesig(m21elm, bar0len))
                elif isinstance(m21elm, music21.tempo.MetronomeMark):
                    evlist.append(self.conv_tempo(m21elm, m21elm.offset))
                elif isinstance(m21elm, music21.expressions.RehearsalMark):
                    evlist.append(self.conv_mark(m21elm, m21elm.offset))
                elif isinstance(m21elm, music21.instrument.Instrument):
                    evlist.append(self.conv_instname(m21elm, m21elm.offset,
                                                     tknum))
                elif isinstance(m21elm, music21.clef.Clef):
                    evlist.append(self.conv_clef(m21elm, m21elm.offset, tknum))
                elif isinstance(m21elm, music21.bar.Barline):
                    if m21elm.type != 'regular':
                        evlist.append(self.conv_barline(m21elm, m21elm.offset,
                                                        tknum))
                elif isinstance(m21elm, music21.harmony.ChordSymbol):
                    c = self.conv_chordsym(m21elm, m21elm.offset, tknum)
                    if c:
                        evlist.append(c)
                # elif isinstance(m21elm, music21.expressions.TextExpression):
                #     evlist.append(self.conv_stafftext(m21elm, m21elm.offset,
                #                                       tknum))

            tracks.append(evlist)
            tknum += 1
        for evlist in tracks:
            evlist.duration = maxduration
        self.move_metaevents_to_track0(tracks, bar0len)
        tracks.sort()
        return tracks
