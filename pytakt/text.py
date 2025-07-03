# coding:utf-8
"""
This module defines functions for text format scores that are readable and
can be evaluated in Python.
"""
"""
このモジュールには、可読かつPythonで評価可能なテキスト形式のスコアに
ついての関数が定義されています。
"""
# Copyright (C) 2025  Satoshi Nishimura

import math
import itertools
import sys
import json
import warnings
from fractions import Fraction
from typing import Optional
from pytakt.score import EventList, EventStream, Tracks, Score, DEFAULT_LIMIT
from pytakt.timemap import TempoMap, TimeSignatureMap, TimeMap, \
    current_tempo, set_tempo
import pytakt.event
from pytakt.event import Event, NoteEvent, NoteOnEvent, NoteOffEvent, \
    CtrlEvent, MetaEvent, SysExEvent, TempoEvent, TimeSignatureEvent, \
    KeySignatureEvent
from pytakt.pitch import Pitch, Interval, Key
from pytakt.chord import Chord
from pytakt.constants import CONTROLLERS, META_EVENT_TYPES, \
    TICKS_PER_QUARTER, M_TIMESIG
from pytakt.utils import frac_time_repr, get_file_type
from pytakt._version import __version__

__all__ = ['showtext', 'writepyfile', 'evalpyfile', 'end_score',
           'writejson', 'readjson', 'showsummary']


S_ROUND = 5   # round precision for summary output


def eventrepr(ev, step, timereprfunc):
    attrrepr = ''.join([
        ', dt=%s' % timereprfunc(ev.dt) if ev.dt != 0 else '',
        ', du=%s' % timereprfunc(ev.du) if hasattr(ev, 'du') else '',
        *(', %s=%r' % (k, v) for k, v in ev.__dict__.items() if k != 'du')])
    steprepr = ', duration=%s' % timereprfunc(step) if step else ''
    trackrepr = ', tk=%r' % ev.tk if ev.tk != 0 else ''

    if isinstance(ev, NoteEvent):
        return "note(%-5sL=%s, step=%s, v=%r, nv=%r, ch=%r%s)" % \
            (repr(ev.n) + ',', timereprfunc(ev.L),
             timereprfunc(step), ev.v, ev.nv, ev.ch, attrrepr)
    elif ev.is_pitch_bend():
        return "bend(%r, ch=%r%s%s)" % (ev.value, ev.ch, attrrepr, steprepr)
    elif ev.is_channel_pressure():
        return "cpr(%r, ch=%r%s%s)" % (ev.value, ev.ch, attrrepr, steprepr)
    elif ev.is_program_change():
        return "prog(%r, ch=%r%s%s)" % (ev.value, ev.ch, attrrepr, steprepr)
    elif ev.is_key_pressure():
        return "kpr(%r, %r, ch=%r%s%s)" % \
            (ev.n, ev.value, ev.ch, attrrepr, steprepr)
    elif isinstance(ev, TempoEvent):
        return "tempo(%r%s%s%s)" % (ev.value, trackrepr, attrrepr, steprepr)
    elif isinstance(ev, CtrlEvent):
        return "ctrl(%s, %r, ch=%r%s%s)" % \
            (CONTROLLERS.get(ev.ctrlnum, str(ev.ctrlnum)),
             ev.value, ev.ch, attrrepr, steprepr)
    elif isinstance(ev, TimeSignatureEvent):
        return "timesig(%d, %d%s%s%s%s)" % \
            (*ev.num_den(), ", cc=%r" % ev.get_cc()
             if ev.get_cc() != ev._guess_cc(*ev.num_den()) else "",
             trackrepr, attrrepr, steprepr)
    elif isinstance(ev, KeySignatureEvent):
        return "keysig(%r%s%s%s)" % (ev.value, trackrepr, attrrepr, steprepr)
    elif isinstance(ev, MetaEvent):
        return "meta(%s, %r%s%s)" % \
            (META_EVENT_TYPES.get(ev.mtype, str(ev.mtype)),
             ev.value, attrrepr, steprepr)
    elif isinstance(ev, SysExEvent):
        arbit = ('' if len(ev.value) >= 2 and ev.value[0] == 0xf0
                 and ev.value[-1] == 0xf7 else ', arbitrary=True')
        return "sysex(%r%s%s%s)" % (ev.value, arbit, attrrepr, steprepr)
    else:
        return "EventList([%r], %s)" % \
            (ev.copy().update(t=0), timereprfunc(step))


def time_column(t, tsigmap, resolution, time_format):
    def blankzeros(s):
        s2 = s.rstrip('0').rstrip('.')
        return s2 + ' ' * (len(s) - len(s2))

    if time_format == 'measures':
        m, tm, b, tb = tsigmap.ticks2mbt(t * TICKS_PER_QUARTER / resolution)
        tcs = blankzeros("%+10.3f" % ((tm / TICKS_PER_QUARTER) * resolution))
        return "'%3s%s'| " % (m, tcs)
    elif time_format in ('mbt', 'all'):
        m, tm, b, tb = tsigmap.ticks2mbt(t * TICKS_PER_QUARTER / resolution)
        tcs = blankzeros("%+10.3f" % (tb * resolution / TICKS_PER_QUARTER))
        s = "'%3s:%r%s" % (m, b, tcs)
        if time_format == 'all':
            s += blankzeros("%12.3f" % t)
        return s + "'| "
    elif time_format == 'ticks':
        return "'" + blankzeros("%12.3f" % t) + "'| "
    elif time_format == 'none' or time_format is None:
        return "    "
    else:
        raise ValueError("Unrecognized time format: %r" % time_format)


def showtext(score, rawmode=False, time='measures',
             resolution=TICKS_PER_QUARTER, limit=DEFAULT_LIMIT, bar0len=None,
             file=sys.stdout, timereprfunc=None) -> None:
    """
    This function displays the contents of the score in a Python-evaluatable
    text, with notes, rests, and other information in chronological order for
    each track.
    This display contains all the information the score has.
    By default, each line displays a note, rest, ctrl, tempo, timesig, keysig,
    sysex, and other command, along with the measure number and number of
    ticks in the measure.
    This text can be eval'd to generate a score compatible with the original
    (although the structure of the score will generally be different).

    Args:
        score(Score): Input score
        rawmode(bool, optional): If True, events are displayed on each line
            instead of commands. In this mode (raw mode), for a score read
            from a standard MIDI file with pair_note_events=False as shown
            below, converting it to text and then eval'ing it will
            reproduce the exactly same score, except for the attribute
            information of the Tracks object.

            >>> buf = io.StringIO()
            >>> score = readsmf('a.mid', pair_note_events=False)
            >>> score.showtext(rawmode=True, file=buf)
            >>> print(list(score) == list(eval(buf.getvalue())))
            True
        time(str, optional): One of the followings which determines the format
            of the time displayed at the beginning of each line.

            - 'measures' (default): displays the measure number and ticks
              within the measure.
            - 'mbt': displays measure number, beat number, and ticks
              within the beat.
            - 'ticks': displays ticks from the beginning of the score.
            - 'all': displays all the values displayed by 'mbt' and 'ticks'.
            - 'none': no display.
        resolution(int or float, optional):
            Specifies ticks per quarter note in the display.
        limit(ticks, optional): Limits the length of the score.
            For details on limit, see the same name argument of
            :meth:`.Score.stream`.
        bar0len(ticks, optional):
            Specifies the length of the initial measure (Bar 0).
            Affects only time display at the beginning of each line.
        file(file object): Specifies the file object to output to.
            The default is sys.stdout (standard output).
        timereprfunc(function): Specifies the function to convert a time value
            to a string.
            By default, it is set to the 'repr' function for the raw mode
            and :func:`.frac_time_repr` otherwise.
    """
    """
    スコアの内容を、トラックごと、時間順に音符、休符およびその他の
    情報を並べたPythonによって評価可能なテキストに変換して表示します。
    この表示には、スコアが持っているすべての情報が含まれています。
    デフォルトでは、各行に note, rest, ctrl, tempo, timesig, keysig, sysex
    などのコマンドが、小節番号、小節内ティック数とともに表示されます。
    このテキストは eval することによって元とコンパチブルなスコアを生成する
    ことができます（ただし、スコアの構造は一般に異なります)。

    Args:
        score(Score): 入力スコア
        rawmode(bool, optional): True にすると、各行にコマンドではなく
            イベントが表示されるようになります。
            このモード (raw モード) では、下のように、pair_note_events=False
            として標準MIDIファイルから読んだスコアに対して、テキストに変換した
            後にそれをevalすると、Tracksが持つ属性情報を除き、完全に同じスコア
            に戻ります。

            >>> buf = io.StringIO()
            >>> score = readsmf('a.mid', pair_note_events=False)
            >>> score.showtext(rawmode=True, file=buf)
            >>> print(list(score) == list(eval(buf.getvalue())))
            True
        time(str, optional): 次のいずれかにより、各行先頭の時刻表示の形式を
            決めます。

            - 'measures' (デフォルト): 小節番号と小節内ティック数を表示します。
            - 'mbt': 小節番号、拍番号、拍内ティック数を表示します。
            - 'ticks': スコア先頭からのティック数を表示します。
            - 'all': 'mbt' と 'ticks' で表示されるものをすべて表示します。
            - 'none': 表示をしません。
        resolution(int or float, optional):
            表示における4分音符当たりのティック数を指定します。
        limit(ticks, optional): スコアの長さを制限します。
            制限の詳細については、:meth:`.Score.stream` の同名の引数
            の項目を見てください。
        bar0len(ticks, optional):
            小節番号 0 の小節の長さを指定します。各行先頭の時刻表示にのみ
            影響を与えます。
        file(file object): 出力先のファイルオブジェクトを指定します。
            デフォルトでは sys.stdout (標準出力) です。
        timereprfunc(function): 時間の値を文字列に変換する関数を指定します。
            デフォルトでは、rawモードならばrepr関数、そうでないなら
            :func:`.frac_time_repr` に設定されます。
    """
    if isinstance(score, EventStream) and score.is_consumed():
        warnings.warn('showtext: Input stream has already been consumed')
    if timereprfunc is None:
        timereprfunc = repr if rawmode else frac_time_repr
    tracks = score.ConnectTies().ToTracks(limit=limit)
    tsigmap = TimeSignatureMap(tracks, bar0len)
    if resolution != TICKS_PER_QUARTER:
        tracks = tracks.TimeStretch(resolution / TICKS_PER_QUARTER)
    fmt = "%s%s,"
    print("Tracks([", file=file)
    for tk, evlist_tk in enumerate(tracks):
        if len(evlist_tk) == 0:
            continue
        print("# Track %d %s  %8d events" %
              (tk, ("(Originally Track %d)" % evlist_tk.org_tk
                    if hasattr(evlist_tk, 'org_tk') else ''),
               len(evlist_tk)), file=file)
        if rawmode:
            print("EventList(duration=%s, events=[" %
                  timereprfunc(evlist_tk.duration), file=file)
            for ev in evlist_tk:
                print(fmt % (time_column(ev.t, tsigmap, resolution, time),
                             ev.tostr(timereprfunc)), file=file)
            print("]),", file=file)
            continue
        print("seq(newcontext(tk=%d).do(lambda: [" % tk, file=file)
        firstrest = evlist_tk.duration if len(evlist_tk) == 0 \
            else evlist_tk[0].t
        if firstrest:
            print(fmt % (time_column(0, tsigmap, resolution, time),
                         "rest(%s)" % timereprfunc(firstrest)), file=file)
        for i, ev in enumerate(evlist_tk):
            step = (evlist_tk[i+1].t - ev.t if i != len(evlist_tk) - 1 else
                    max(0, evlist_tk.duration - ev.t))
            print(fmt % (time_column(ev.t, tsigmap, resolution, time),
                         eventrepr(ev, step, timereprfunc)), file=file)
        print("])),", file=file)
    if resolution != TICKS_PER_QUARTER:
        print("]).TimeStretch(%r / %r)" % (TICKS_PER_QUARTER, resolution),
              file=file)
    else:
        print("])", file=file)


def writepyfile(score, filename, rawmode=False, time='measures',
                resolution=TICKS_PER_QUARTER, limit=DEFAULT_LIMIT,
                bar0len=None, end_score_args={}) -> None:
    """
    Output the text converted by :func:`showtext` to a file with a header and
    footer. This file is executable as a Python program, and when executed,
    it can play the score, show the score content, and convert it to a
    standard MIDI or JSON file, as shown in the example below.

        | >>> score.writepyfile('sample.py')
        | >>> <Ctrl-D>
        | $ python sample.py
        | Usage: /usr/bin/python sample.py (play|show|write) [WRITE_FILE] \
[PARAM=VALUE ..]
        | $ python sample.py play \
　# Play the score. Parameters, if any, are passed to :func:`.play`.
        | $ python sample.py show velocity=True \
　# Show the piano roll. Parameters are passed to :func:`.show`.
        | $ python sample.py write sample.mid "encoding='sjis'" \
　# Write to SMF. Parameters are passed to :func:`.writesmf`.
        | $ python sample.py write sample.json indent=4 \
　# If the file name extension is '.json', it is written to a JSON file. \
Parameters are passed to :func:`.writejson`.

    Args:
        filename(str): name of output file ('-' for standard output)
        end_score_args(dict, optional): additional arguments passed to
            the end_score function

    The meaning of the other arguments is the same as :func:`showtext`.
    """
    """
    :func:`showtext` によって変換されたテキストを、ヘッダ、フッタとともに
    ファイルへ出力します。このファイルは Python のプログラムとして実行可能
    であり、実行すると下の例のようにスコア内容の再生、表示、および SMFやJSON
    ファイルへの変換が可能です。

        | >>> score.writepyfile('sample.py')
        | >>> <Ctrl-D>
        | $ python sample.py
        | Usage: /usr/bin/python sample.py (play|show|write) [WRITE_FILE] \
[PARAM=VALUE ..]
        | $ python sample.py play \
　# 再生する。引数はあれば :func:`.play` へ渡される。
        | $ python sample.py show velocity=True \
　# ピアノロール表示を行う。引数は :func:`.show` へ渡される。
        | $ python sample.py write sample.mid "encoding='sjis'" \
　# SMFへ書き出す。引数は :func:`.writesmf` へ渡される。
        | $ python sample.py write sample.json indent=4 \
　# 拡張子が'.json'ならば、JSONファイルへ書き出される。\
引数は :func:`.writejson` へ渡される。

    Args:
        filename(str): 出力ファイル名 ('-' なら標準出力)
        end_score_args(dict, optional): end_score関数へ渡される追加の引数

    他の引数の意味は :func:`showtext` と同じです。
    """
    def _writepyfile(f):
        print("#pytakt " + __version__)
        print("from pytakt import *", file=f)
        print("from pytakt.sc import *", file=f)
        print("\nscore = ", end='', file=f)
        showtext(score, rawmode, time, resolution, limit, bar0len, f)
        print("", file=f)
        print("end_score(score", end='', file=f)
        for key, value in end_score_args.items():
            print(", %s=%r" % (key, value), end='', file=f)
        print(")", file=f)

    if filename == '-':
        _writepyfile(sys.stdout)
    else:
        with open(filename, "w") as f:
            _writepyfile(f)


_returned_score = None
_score_file_reading = False


def evalpyfile(filename, supply_tempo=True) -> Score:
    """
    Execute a Python file containing :func:`end_score` (which can be
    generated by :func:`writepyfile` or written by a user) and return
    the score described in it.

    **Caution**: This function executes the contents of a file as a Python
    program, and therefore poses a significant security risk. Use extreme
    caution when applying this function to files obtained from outside such
    as the Internet.

    Args:
        filename(str): file name
        supply_tempo(bool or float, optional): If True, a tempo event of the
            value specified in the `default_tempo` argument of
            :func:`end_score` is supplied if there is no tempo event at time 0.
            If a valid tempo value (BPM) is specified, a tempo event of that
            value is inserted if there is no tempo event at time 0.
            If False, no tempo event is added.

    Returns:
        The score passed as an argument to :func:`end_score`.
        This score object has the additional attributes 'default_tempo',
        'smf_format', and 'smf_resolution', whose values are set to the
        values of the `default_tempo`, `format`, and `resolution` arguments
        of :func:`end_score`.
    """
    """
    :func:`end_score` を含んだ Python ファイル (これは、:func:`writepyfile` に
    よって生成されたものでも、ユーザによって書かれたものでも構いません) を
    実行し、その中に記述されているスコアを返します。

    **注意**: この関数はファイルの内容をPythonプログラムとして実行するため
    セキュリティ上の重大なリスクがあります。インターネット等外部から取得した
    ファイルに対してこの関数を適用する場合には、細心の注意を払ってください。

    Args:
        filename(str): ファイル名
        supply_tempo(bool, optional): Trueであると、時刻 0 にテンポイベントが
            ない場合に、:func:`end_score` の `default_tempo` 引数に指定され
            ている値のテンポイベントが補われます。
            有効なテンポ値(BPM)を指定すると、時刻 0 にテンポイベントがない
            場合に、その値のテンポイベントが補われます。
            Falseの場合、テンポイベントは補われません。

    Returns:
        :func:`end_score` に引数として渡されたスコア。このスコア
        オブジェクトには属性として、default_tempo, smf_format, および
        smf_resolution が追加されていて、それぞれの値は、:func:`end_score` の
        `default_tempo`, `format`, および `resolution` 引数の値に設定されて
        います。
    """
    global _score_file_reading, _returned_score
    env = globals().copy()  # ファイル中で定義された名前は保持しない
    _returned_score = None
    with open(filename, "r") as f:
        if f.readline()[0:7] != "#pytakt":
            raise Exception('No "#pytakt" signature found in %r' %
                            filename)
        _score_file_reading = True
        try:
            exec(f.read(), env, env)
        finally:
            _score_file_reading = False
    if _returned_score is None:
        raise Exception("No 'end_score' found in %r" % filename)
    score = _returned_score
    if supply_tempo and not score.active_events_at(0, TempoEvent):
        ev = TempoEvent(0, score.default_tempo if supply_tempo is True
                        else supply_tempo)
        if isinstance(score, Tracks):
            if not score:
                score.append(EventList())
            score[0].insert(0, ev)
        else:
            score = EventList([ev], 0) & score
    return score


def end_score(score, default_tempo=125.0, format=1, resolution=480) -> None:
    """
    Depending on the command line arguments when Python is invoked,
    this function plays, displays, or outputs the contents of `score`
    to a file.
    This function is intended to be used for final processing in a Python file
    that describes a score.
    Files generated by :func:`writepyfile` will have this function at the end.
    See :func:`writepyfile` for the usage of command line arguments.

    Args:
        score(Score): the output score
        default_tempo(float or int, optional):
            Specifies the tempo when there is no tempo event at time 0.
        format(int, optional):
            Specifying the SMF format by one of the integers 0, 1, and 2.
            This is referenced when writing to SMF with the write operation.
        resolution(int, optional):
            Specifies the resolution (ticks per quarter note) in SMF.
            This is referenced when writing to SMF with the write operation.
    """
    """
    Python を起動したときのコマンドライン引数に応じて、`score` の内容を
    再生、表示、あるいはファイルに出力します。この関数は、スコアを記述した
    Python ファイルにおいて、その終了処理として使用すること想定しています。
    :func:`writepyfile` によって生成されたファイルには末尾にこの関数が
    置かれています。コマンドライン引数の使い方については
    :func:`writepyfile` を見てください。

    Args:
        score(Score): 出力となるスコア
        default_tempo(float or int, optional):
            時刻 0 にテンポイベントがないときのテンポを指定します。
        format(int, optional): 0, 1, 2いずれかの整数で、SMFのフォーマットを
            指定します。write操作でSMFに書き出すときに参照されます。
        resolution(int, optional): SMFにおける分解能(四分音符あたりの
            ティック数)を指定します。write操作でSMFに書き出すとき
            に参照されます。
    """
    global _returned_score
    if _score_file_reading:
        score.smf_format = format
        score.smf_resolution = resolution
        score.default_tempo = default_tempo
        _returned_score = score
        return
    kwargs = {}
    if len(sys.argv) > 1 and sys.argv[1] == 'write':
        if len(sys.argv) == 2 or ('=' in sys.argv[2]):
            print("'write' requires a filename")
            return
        try:
            ext = get_file_type(sys.argv[2], ('smf', 'json'), guess=False)
        except Exception as e:
            print(e)
            return
        exec('kwargs.update(%s)' % ','.join(sys.argv[3:]))
        if ext == 'smf':
            kwargs2 = {'format': format, 'resolution': resolution,
                       'supply_tempo': default_tempo}
            kwargs2.update(kwargs)
            score.writesmf(sys.argv[2], **kwargs2)
        else:
            score.writejson(sys.argv[2], **kwargs)
    else:
        exec('kwargs.update(%s)' % ','.join(sys.argv[2:]))
        if len(sys.argv) > 1 and sys.argv[1] == 'play':
            set_tempo(default_tempo)
            score.play(**kwargs)
        elif len(sys.argv) > 1 and sys.argv[1] == 'show':
            set_tempo(default_tempo)
            score.show(**kwargs)
        else:
            print("Usage: %s %s (play|show|write) [WRITE_FILE] "
                  "[PARAM=VALUE ..]" % (sys.executable, sys.argv[0]))


def writejson(score, filename, **kwargs) -> None:
    """
    Writes the contents of `score` to Pytakt's original file in JSON format.
    Reading this file with :func:`readjson` yields an object that is
    equivalent to the original (i.e., true when compared with '==').
    It cannot be used if `score` contains objects other than those of
    the classes below.

        int, float, str, bool, None, Fraction, Pitch, Interval, Key, list,
        tuple, dict (each key must be a string), bytes, bytearray,
        Event and its subclasses, EventList, Tracks, and Chord

    Scores, except for EventStreams, usually consist of only the above objects,
    so this function is useful for saving score information to a file.
    It has the advantage over standard MIDI files in that it can include
    information about enharmonics, both notated and played times,
    and additional event attributes.

    Args:
        filename: Output filename ('-' for standard output)
        kwargs: Other arguments passed to json.dump

    Examples:
        >>> writejson(note(C4), '-', indent=4)
        {
            "__event_list__": true,
            "duration": 480,
            "events": [
                {
                    "__event__": "NoteEvent",
                    "t": 0,
                    "n": {
                        "__pitch__": "C4"
                    },
                    "L": 480,
                    "v": 80,
                    "nv": null,
                    "tk": 1,
                    "ch": 1
                }
            ]
        }>>>
        >>> s = mml("C C# Db> D")
        >>> writejson(s, 'a.json')
        >>> s == readjson('a.json')
        True
    """
    """
    `score` の内容をJSON形式によるPytakt独自のファイルに書き出します。
    このファイルを :func:`readjson` で読むと、元と等価な(つまり、
    '==' で比較したときに真となる)オブジェクトが得られます。
    ただし、`score` に下のクラス以外のオブジェクトが含まれている場合は
    使用できません。

        int, float, str, bool, None, Fraction, Pitch, Interval, Key, list,
        tuple, dict (キーは文字列に限る), bytes, bytearray,
        Event とそのサブクラス, EventList, Tracks, Chord

    EventStreamを除くスコアは、通常、上のオブジェクトのみで構成されています
    ので、この関数によってスコア情報をファイルへ保存できます。異名同音の情報、
    楽譜上と演奏上の両方の時刻、あるいは、追加のイベント属性を含められる点に
    おいて、標準MIDIファイルより有利です。

    Args:
        filename: 出力ファイル名 ('-' なら標準出力)
        kwargs: json.dump へ渡されるその他の引数

    Examples:
        >>> writejson(note(C4), '-', indent=4)
        {
            "__event_list__": true,
            "duration": 480,
            "events": [
                {
                    "__event__": "NoteEvent",
                    "t": 0,
                    "n": {
                        "__pitch__": "C4"
                    },
                    "L": 480,
                    "v": 80,
                    "nv": null,
                    "tk": 1,
                    "ch": 1
                }
            ]
        }>>>
        >>> s = mml("C C# Db> D")
        >>> writejson(s, 'a.json')
        >>> s == readjson('a.json')
        True
    """
    def pre_encode(obj):
        if isinstance(obj, Pitch):
            pstr = obj.tostr(lossless=True, sfn='#b')
            return {'__pitch__': (int(obj), obj.sf) if '(' in pstr else pstr}
        elif isinstance(obj, Interval):
            return {'__interval__': (int(obj), obj.ds)}
        elif isinstance(obj, Key):
            return {'__key__': (obj.signs, obj.minor)}
        elif isinstance(obj, Chord):
            return {'__chord__': True, 'kind': obj.kind,
                    'root': pre_encode(obj.root), 'bass': pre_encode(obj.bass),
                    'modifications': obj.modifications}
        elif isinstance(obj, Fraction):
            return {'__fraction__': True,
                    'numerator': obj.numerator, 'denominator': obj.denominator}
        elif isinstance(obj, bytes):
            return {'__bytes__': tuple(obj)}
        elif isinstance(obj, bytearray):
            return {'__bytearray__': tuple(obj)}
        elif isinstance(obj, Event):
            return {'__event__': obj.__class__.__name__,
                    **{attr: pre_encode(getattr(obj, attr))
                       for attr in obj._getattrs()}}
        elif isinstance(obj, EventList):
            return {'__event_list__': True,
                    'duration': pre_encode(obj.duration),
                    'events': [pre_encode(o) for o in obj],
                    **{attr: pre_encode(getattr(obj, attr))
                       for attr in obj.__dict__}}
        elif isinstance(obj, Tracks):
            return {'__tracks__': True,
                    'elms': [pre_encode(o) for o in obj],
                    **{attr: pre_encode(getattr(obj, attr))
                       for attr in obj.__dict__}}
        elif isinstance(obj, list):
            return [pre_encode(o) for o in obj]
        elif isinstance(obj, tuple):
            return {'__tuple__': [pre_encode(o) for o in obj]}
        elif isinstance(obj, dict):
            return {k: pre_encode(v) for k, v in obj.items()}
        else:
            return obj

    score = pre_encode(score)
    if filename == '-':
        json.dump(score, sys.stdout, **kwargs)
    else:
        with open(filename, 'w') as f:
            json.dump(score, f, **kwargs)


def readjson(filename) -> Score:
    """
    Reads a file in JSON format written by :func:`writejson` and
    returns the object described.

    Args:
        filename: Input file name ('-' for standard input)
    """
    """
    :func:`writejson` で書き出されたJSON形式のファイルを読んで
    記述されているオブジェクトを返します。

    Args:
        filename: 入力ファイル名 ('-' なら標準入力)
    """
    def object_hook(dic):
        if '__pitch__' in dic:
            value = dic['__pitch__']
            obj = Pitch(value) if isinstance(value, str) else Pitch(*value)
        elif '__interval__' in dic:
            obj = Interval(*dic['__interval__'])
        elif '__key__' in dic:
            obj = Key(*dic['__key__'])
        elif '__chord__' in dic:
            del dic['__chord__']
            return Chord(**dic)
        elif '__fraction__' in dic:
            obj = Fraction(dic['numerator'], dic['denominator'])
        elif '__bytes__' in dic:
            obj = bytes(dic['__bytes__'])
        elif '__bytearray__' in dic:
            obj = bytearray(dic['__bytearray__'])
        elif '__event__' in dic:
            try:
                evclass = getattr(pytakt.event, dic['__event__'])
                if not issubclass(evclass, Event):
                    raise Exception()
            except Exception:
                raise Exception('%r: No such event class' %
                                (dic['__event__'],))
            del dic['__event__']
            if evclass == TimeSignatureEvent:
                obj = MetaEvent(mtype=M_TIMESIG, **dic)
            else:
                obj = evclass(**dic)
        elif '__event_list__' in dic:
            if type(dic['events']) is not list:
                raise TypeError('__event_list__')
            del dic['__event_list__']
            return EventList(**dic)
        elif '__tracks__' in dic:
            del dic['__tracks__']
            return Tracks(**dic)
        elif '__tuple__' in dic:
            obj = tuple(dic['__tuple__'])
        else:
            obj = dic
        return obj

    if filename == '-':
        return json.load(sys.stdin, object_hook=object_hook)
    else:
        with open(filename, 'r') as f:
            return json.load(f, object_hook=object_hook)


def statis(values=(), weights=itertools.repeat(1), times=itertools.repeat(0)):
    sumw = sumval = sqrsum = maxat = minat = 0
    minval, maxval = math.inf, -math.inf
    for x, w, t in zip(values, weights, times):
        sumw += w
        if x > maxval:
            maxval = x
            maxat = t
        if x < minval:
            minval = x
            minat = t
        sumval += w * x
        sqrsum += w * x * x
    if not sumw:
        return (None, None, None, None, 0, 0)
    else:
        mean = sumval / sumw
        stddev = math.sqrt(max(0, sqrsum / sumw - mean * mean))
        return (round(minval, S_ROUND), round(maxval, S_ROUND),
                round(mean, S_ROUND), round(stddev, S_ROUND),
                round(maxat, S_ROUND), round(minat, S_ROUND))


def showsummary(score, default_tempo=125.0) -> None:
    """
    Displays summary information about the score, including length,
    number of measures, pitch range, and number of events.

    Args:
        score(Score): Input score
        default_tempo(float): If there is a section at the beginning of
            the score with no tempo events, the tempo of that section is
            assumed to be this value.
    """
    """
    スコアに関して、演奏長、小節数、音域、イベント数などのサマリー情報を表示
    します。

    Args:
        score(Score): 入力スコア
        default_tempo(float): スコア冒頭部分にテンポイベントがない区間が
            存在する場合、その区間のテンポはこの値であると仮定されます。
    """
    if isinstance(score, EventStream) and score.is_consumed():
        raise Exception('showsummary: Input stream has already been consumed')

    evlist = EventList(score).ConnectTies()
    timemap = TimeMap(evlist, default_tempo)
    bycategory = [[] for cat in range(0, 14)]
    bytrack = {}
    bychannel = {}
    controllers = set()
    textevents = set()

    for ev in evlist:
        bytrack.setdefault(ev.tk, []).append(ev)
        if hasattr(ev, 'ch') and ev.ch >= 1:
            bychannel.setdefault(ev.ch, []).append(ev)
        category = (0 if isinstance(ev, NoteEvent) else
                    1 if isinstance(ev, NoteOnEvent) else
                    2 if isinstance(ev, NoteOffEvent) else
                    4 if ev.is_pitch_bend() else
                    5 if ev.is_key_pressure() else
                    6 if ev.is_program_change() else
                    9 if isinstance(ev, TempoEvent) else
                    3 if isinstance(ev, CtrlEvent) else
                    7 if isinstance(ev, TimeSignatureEvent) else
                    8 if isinstance(ev, KeySignatureEvent) else
                    10 if ev.is_text_event() else
                    13 if ev.is_end_of_track() else
                    11 if isinstance(ev, MetaEvent) else
                    12 if isinstance(ev, SysExEvent) else
                    None)
        if category is not None:
            bycategory[category].append(ev)
        if isinstance(ev, CtrlEvent) and \
           (ev.ctrlnum <= 127 or ev.is_channel_pressure()):
            controllers.add(ev.ctrlnum)
        if ev.is_text_event():
            textevents.add(ev.mtype)

    print("Total duration: %r ticks, %r seconds   Measures: %r" %
          (round(evlist.duration, S_ROUND),
           round(timemap.ticks2sec(evlist.duration), S_ROUND),
           timemap.num_measures()))

    print("Event time (ticks): %r-%r" % statis(ev.t for ev in evlist)[:2],
          end='')

    nrange = statis(ev.n for ev in bycategory[0] + bycategory[1])[:2]
    print("    Note pitch: %r-%r (%s-%s)" %
          (*nrange, *('' if n is None else Pitch(n).tostr() for n in nrange)))

    print("Time signature(s): ", end='')
    if not bycategory[7]:
        print("4/4 (default)")
    else:
        print(', '.join("%d/%d (at %r)" % (*ev.num_den(), round(ev.t, S_ROUND))
                        for ev in bycategory[7]))

    print("Key(s):",
          ', '.join("%s (at %r)" % (repr(ev.value)[5:-2], round(ev.t, S_ROUND))
                    for ev in bycategory[8]))

    print("Tempo (BPM):   ", end='')
    if not bycategory[9]:
        print("%r (default)" % default_tempo)
    else:
        times = [ev.t for ev in bycategory[9]]
        timespans = (max(0, t2 - t1) for t1, t2 in
                     zip(times, times[1:] + [evlist.duration]))
        print("%r-%r (mean: %r, stddev: %r)" %
              statis((ev.value for ev in bycategory[9]), timespans)[:4])

    print("Note velocity: %r-%r (mean: %r, stddev: %r)" %
          statis(ev.v for ev in bycategory[0] + bycategory[1])[:4])

    print("Note duration: ", end='')
    if bycategory[1] or bycategory[2]:
        print("N/A")
    else:
        print("%r-%r (mean: %r, stddev: %r)" %
              statis(ev.L for ev in bycategory[0])[:4])

    overlaps = [(sum(isinstance(ev, (NoteEvent, NoteOnEvent)) for ev in span),
                 span.duration - span.start, span.start)
                for span in evlist.chord_iterator()]
    print("Note overlaps: %r-%r (mean: %r, stddev: %r, maxat: %r)" %
          statis(*zip(*overlaps))[:5])

    print("Used controllers: %s" %
          ', '.join("%d(%s)" % (i, CONTROLLERS[i][2:]) if i in
                    CONTROLLERS else str(i)
                    for i in sorted(controllers)))

    print("Used text events: %s" %
          ', '.join("%d(%s)" % (i, META_EVENT_TYPES[i][2:]) if i in
                    META_EVENT_TYPES else str(i)
                    for i in sorted(textevents)))

    print("# of events (by track)")
    (sbufk, sbufv) = ("", "")
    for i, tk in enumerate(sorted(bytrack)):
        sbufk += "%5s " % ("tk%d" % tk)
        sbufv += "%5d " % len(bytrack[tk])
        if i % 13 == 12:
            print(sbufk.rstrip() + '\n' + sbufv.rstrip())
            (sbufk, sbufv) = ("", "")
    sbufk += " total"
    sbufv += "%6d" % len(evlist)
    print(sbufk + '\n' + sbufv)

    print("# of events (by channel)")
    (sbufk, sbufv) = ("", "")
    for i, ch in enumerate(sorted(bychannel)):
        sbufk += "%5s " % ("ch%d" % ch)
        sbufv += "%5d " % len(bychannel[ch])
        if i % 13 == 12 or i == len(bychannel) - 1:
            print(sbufk.rstrip() + '\n' + sbufv.rstrip())
            (sbufk, sbufv) = ("", "")

    print("# of events (by category)")
    print(" note  n-on n-off  ctrl  bend   kpr prog "
          "tsig ksig tempo  text  meta  excl eot")
    print("%5d %5d %5d %5d %5d %5d %4d %4d %4d %5d %5d %5d %5d %3d" %
          (tuple(len(events) for events in bycategory)))
    #  # of notes (by chroma)?
