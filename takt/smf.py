# coding:utf-8
"""
このモジュールには、標準MIDIファイル(SMF)を読み書きするため関数が
定義されています。
"""
# Copyright (C) 2023  Satoshi Nishimura

from struct import unpack, pack
import warnings
import math
import sys
from takt.score import EventList, Tracks, DEFAULT_LIMIT
from takt.event import NoteEventClass, CtrlEvent, KeyPressureEvent, \
    MetaEvent, SysExEvent, TempoEvent, KeySignatureEvent, \
    midimsg_size, message_to_event
from takt.constants import TICKS_PER_QUARTER, M_KEYSIG, M_EOT
from takt.utils import int_preferred, TaktWarning
from takt.pitch import Pitch, Key
from takt.timemap import current_tempo, KeySignatureMap

__all__ = ['readsmf', 'writesmf', 'SMFError']


class SMFError(Exception):
    pass


class SMFReader(object):
    def read(self, fp, encoding):
        self.read_header_string(fp, 'MThd')
        try:
            (hdrsize, fmt, ntrks, resolution) = unpack(">Lhhh", fp.read(10))
            assert hdrsize >= 6 and 0 <= fmt <= 2 and ntrks >= 0
            assert resolution >= 1
        except Exception:
            raise SMFError("Bad file header") from None
        self.ntrks = ntrks
        self.resolution = resolution
        self.encoding = encoding
        tracks = Tracks()
        for self.cur_track in range(ntrks):
            tracks.append(self.read_track(fp))
        tracks.smf_format = fmt
        tracks.smf_resolution = resolution
        return tracks

    def read_track(self, fp):
        evlist = EventList()
        self.read_header_string(fp, 'MTrk')
        self.run_st = 0
        try:
            (trksize,) = unpack(">L", fp.read(4))
        except Exception:
            raise SMFError("Bad track header") from None
        buf = fp.read(trksize)
        if len(buf) != trksize:
            raise SMFError("No sufficient track data")
        inp = iter(buf)
        self.abs_ticks = 0
        try:
            while True:
                ev = self.read_event(inp)
                if not ev:
                    break
                evlist.append(ev)
                evlist.duration = max(evlist.duration, ev.t)
        except StopIteration:
            raise SMFError("Unexpected EOF") from None
        return evlist

    def read_event(self, inp):
        try:
            delta_ticks = self.read_varlen(inp)
        except StopIteration:
            return None
        self.abs_ticks += delta_ticks
        event_time = int_preferred(self.abs_ticks * TICKS_PER_QUARTER /
                                   self.resolution)
        status = next(inp)
        msg = bytearray()
        if status in (0xf0, 0xf7):  # sysex
            length = self.read_varlen(inp)
            msg.append(0xf0)
            if status == 0xf0:
                msg.append(status)
        elif status == 0xff:  # meta
            mtype = next(inp)
            length = self.read_varlen(inp)
            msg.extend((0xff, mtype))
        else:
            if status >= 0x80:
                if status < 0xf0:
                    self.run_st = status
                msg.append(status)
                length = midimsg_size(status) - 1
            else:
                if not self.run_st:
                    raise SMFError("No MIDI running status")
                msg.extend((self.run_st, status))
                length = midimsg_size(self.run_st) - 2
        for _ in range(length):
            msg.append(next(inp))
        return message_to_event(msg, event_time, self.cur_track, self.encoding)

    def read_varlen(self, inp):
        value = 0
        c = 0x80
        while c & 0x80:
            c = next(inp)
            value = (value << 7) + (c & 0x7f)
        return value

    # Read a header string ("MThd", "MTrk", etc.) with skipping leading garbage
    def read_header_string(self, fp, chunkname):
        # Assume that chunk name consists of 4 different characters
        state = 0
        while state < 4:
            c = fp.read(1)
            if not c:
                raise SMFError("Could not find header %r" % chunkname)
            if ord(c) == ord(chunkname[state]):
                state += 1
            else:
                warnings.warn("ignoring garbage data",
                              TaktWarning, stacklevel=2)
                state = 0


class SMFWriter(object):
    # 下のEPSILONは、例えば、時刻 100/3をresolution=480のSMFに出力する場合に
    # 160すべきところを計算誤差で159になるのを防ぐ。
    EPSILON = 1e-4

    def write(self, fp, tracks, format, resolution, encoding):
        assert 0 <= format <= 2 and resolution >= 1
        fp.write(pack(">4sLhhh", b'MThd', 6, format, len(tracks), resolution))
        self.resolution = resolution
        self.encoding = encoding
        for track in tracks:
            self.write_track(fp, track)

    def write_track(self, fp, track):
        self.run_st = 0
        self.abs_ticks = 0
        out = bytearray()
        for ev in track:
            if ev is not None:
                self.write_event(out, ev)
        fp.write(pack(">4sL", b'MTrk', len(out)))
        fp.write(out)

    def write_event(self, out, ev):
        if not isinstance(ev, (NoteEventClass, CtrlEvent,
                               MetaEvent, SysExEvent)):
            pass  # ignore events not related to MIDI file
        else:
            event_ticks = max(int(ev.t * self.resolution / TICKS_PER_QUARTER +
                                  self.EPSILON), 0)
            delta_ticks = event_ticks - self.abs_ticks
            self.abs_ticks = event_ticks
            out += self.to_varlen(delta_ticks)
            if isinstance(ev, SysExEvent):
                msg = ev.to_message()
                del msg[0]
                if len(msg) >= 1 and msg[0] == 0xf0:
                    out.append(0xf0)
                    del msg[0]
                else:
                    out.append(0xf7)
                out += self.to_varlen(len(msg))
                out += msg
                self.run_st = 0
            elif isinstance(ev, MetaEvent):
                msg = ev.to_message(self.encoding)
                out += msg[0:2]
                out += self.to_varlen(len(msg) - 2)
                out += msg[2:]
                self.run_st = 0
            else:
                msg = ev.to_message()
                if msg[0] == self.run_st:
                    out += msg[1:]
                else:
                    out += msg
                self.run_st = msg[0]

    def to_varlen(self, value):
        result = bytearray((value & 0x7f,))
        while (value >> 7) > 0:
            value >>= 7
            result.insert(0, (value & 0x7f) | 0x80)
        return result


def check_eot(tracks):
    for tk, track in enumerate(tracks):
        hasEOT = False
        for i in reversed(range(len(track))):
            if track[i].is_end_of_track():
                if hasEOT:  # 複数EOTがある場合は最後のものだけを有効とする
                    track[i] = None
                else:
                    hasEOT = True
                    # 同時刻にある他の種類のイベントはEOTの前へ移動する
                    k = i + 1
                    eot = track[i]
                    while k < len(track) and track[k].t == eot.t:
                        track[k-1] = track[k]
                        k += 1
                    track[k-1] = eot
                    # 最後のEOTの後にイベントがある場合は警告を出す
                    if k != len(track):
                        warnings.warn("(Track %d) event(s) exist after "
                                      "end-of-track" % tk,
                                      TaktWarning, stacklevel=2)
        if not hasEOT:
            # EOTが無い場合は補う
            track.append(MetaEvent(
                max(track.duration, track[-1].t if len(track) > 0 else 0),
                M_EOT, b''))


def readsmf(filename, supply_tempo=True, pair_note_events=True,
            encoding='utf-8') -> Tracks:
    """ 標準MIDIファイルを読んでスコアを返します。
    返されるスコアは、トラック毎にEventListがあり、それらがTracksとして
    まとめられた構造になっています。

    Args:
        filename(str): ファイル名 ('-' なら標準入力)
        supply_tempo(bool, optional): Trueであると、時刻 0 にテンポイベントが
            ない場合に、120 BPM のテンポイベントが補われます。
        pair_note_events(bool): Trueの場合、ノートオンとノートオフは組み合わ
            されてすべて NoteEvent として出力されます。Falseの場合、独立した
            NoteOnEvent と NoteOffEvent として出力されます。
        encoding(str, optional): テキストイベントが持つ文字列がSMFの中で
            どのようにエンコーディングされているかを指定します。

    Returns:
        結果のスコア。このTracksオブジェクトには、smf_format と
        smf_resolution という2つの属性が付加されていて、それぞれSMFの
        フォーマット (0, 1, または 2) と分解能が格納されています。
    """
    if filename == '-':
        tracks = SMFReader().read(sys.stdin.buffer, encoding)
    else:
        with open(filename, "rb") as fp:
            tracks = SMFReader().read(fp, encoding)
    if supply_tempo and not tracks.active_events_at(0, TempoEvent):
        if not tracks:
            tracks.append(EventList())
        tracks[0].insert(0, TempoEvent(0, 120))
    if pair_note_events:
        tracks = tracks.PairNoteEvents()
    ksmap = KeySignatureMap(tracks)
    for evlist in tracks:
        for ev in evlist:
            if isinstance(ev, (NoteEventClass, KeyPressureEvent)):
                ev.n = Pitch(ev.n, key=ksmap.key_at(ev.t, ev.tk))
    return tracks


def writesmf(score, filename, format=1, resolution=480, ntrks=None,
             retrigger_notes=False, supply_tempo=True, render=True,
             encoding='utf-8', limit=DEFAULT_LIMIT) -> None:
    """ `score` の内容を標準MIDIファイルに書き出します。
    `score` はどのような構造のスコアであっても構いません。
    format-0以外のSMFでは、
    各イベントが持つtk属性の値に従って、SMF中での格納トラックが決まります。
    SMF中でのイベントの時刻は、各イベントのt属性の値に
    (あれば)dt属性の値を加えたものになります。
    各トラックの最後にEnd-of-trackイベントがない場合は補われます。

    Args:
        score(Score): 入力スコア
        filename(str): ファイル名 ('-' なら標準出力)
        format(int, optional): 0, 1, 2いずれかの整数で、SMFのフォーマットを
            指定します。
        resolution(int, optional): SMFにおける分解能(四分音符あたりの
            ティック数)を指定します。
        ntrks(int, optional): format-0以外のSMFで、トラック数を指定します。
            デフォルトでは、`score` に含まれるイベントが持つtk属性の
            最大値+1となります。この値より大きな値を `ntrks` に指定した
            ときは、その分だけ空のトラックが補われます。逆に、より小さな値を
            指定した場合、`ntrks` 以上のtk属性値を持つイベントは格納
            されません。
        retrigger_notes(bool, optional): Trueであると、SMFに書き出される前に、
            衝突noteに対するリトリガー処理
            (:meth:`.EventList.retrigger_notes` を参照)が適用されます。
        supply_tempo(bool, float, or int, optional):
            有効なテンポ値(BPM)を指定すると、時刻 0 にテンポイベントがない
            場合に、その値のテンポイベントが補われます。
            Trueであると、時刻 0 にテンポイベントがない場合に、テンポ値が
            :func:`.current_tempo` であるテンポイベントが補われます。
            Falseの場合、テンポイベントは補われません。
        render(bool, optional):
            デフォルト(True)の場合、演奏上の時間でイベントを出力します。
            Falseの場合は、楽譜上の時間で出力します。
        encoding(str, optional): テキストイベントが持つ文字列のSMF中での
            エンコーディング方法を指定します。
        limit(ticks, optional): スコアの長さを制限します。
            制限の詳細については、:meth:`.Score.stream` の同名の引数
            の項目を見てください。
    """

    inp = score.stream(limit=limit).ConnectTies()
    if render:
        inp = inp.Render()
    inp = inp.UnpairNoteEvents()
    if retrigger_notes:
        inp = inp.RetriggerNotes()
    evlist = EventList(inp, limit=math.inf)
    if format == 0:
        evlist.sort()
        tracks = Tracks([evlist])
    else:
        tracks = evlist.ToTracks()
        if ntrks is not None:
            while len(tracks) < ntrks:
                tracks.append(EventList())
            tracks = tracks[:ntrks]

    if supply_tempo:
        if not tracks.active_events_at(0, TempoEvent):
            if not tracks:
                tracks.append(EventList())
            tracks[0].insert(0, TempoEvent(0, current_tempo() if supply_tempo
                                           is True else supply_tempo))

    check_eot(tracks)
    if filename == '-':
        SMFWriter().write(sys.stdout.buffer,
                          tracks, format, resolution, encoding)
    else:
        with open(filename, "wb") as fp:
            SMFWriter().write(fp, tracks, format, resolution, encoding)
