# coding:utf-8
"""
This module defines classes for retrieving tempo values and time signatures
in a score and for converting between ticks, seconds, bar numbers, and beat
numbers.
"""
"""
このモジュールにはスコア中のテンポ値や拍子を取得したり、
ティック、秒、小節番号、拍番号間の変換するためのクラスが定義されています。
"""
# Copyright (C) 2023  Satoshi Nishimura

import math
import sys
from bisect import bisect_right
from typing import Union, Tuple, Generator
from takt.event import TempoEvent, TimeSignatureEvent, KeySignatureEvent
from takt.constants import TICKS_PER_QUARTER, EPSILON
from takt.score import EventStream
from takt.pitch import Key
from takt.utils import int_preferred, Ticks


__all__ = ['current_tempo', 'set_tempo',
           'TempoMap', 'TimeSignatureMap', 'TimeMap', 'KeySignatureMap']


# takt.midiio モジュールをインポートしないでもテンポ値の設定・取得を
# できるようにしている。
_current_tempo_value = 125.0


def current_tempo() -> float:
    """ Returns the current tempo.

    Returns:
        Tempo value (beats per minute)
    """
    """ 現在のテンポを返します。

    Returns:
        テンポ値 (beats per minute)
    """
    try:
        return sys.modules['takt.midiio']._current_tempo()
    except KeyError:
        return _current_tempo_value


def set_tempo(bpm) -> None:
    """ Changes the current tempo.

    Args:
        bpm(float): Tempo value (beats per minute)
    """
    """ 現在のテンポを変更します。

    Args:
        bpm(float): テンポ値 (beats per minute)
    """
    global _current_tempo_value
    _current_tempo_value = bpm
    try:
        sys.modules['takt.midiio']._set_tempo(bpm)
    except KeyError:
        pass


class TempoMap(object):
    """
    This class represents a data structure (tempo map) in which tempo
    events are extracted from the score.
    Tempo maps can be used to obtain tempo values at arbitrary time and
    to convert between ticks (480ths of a quarter note) and seconds.

    Args:
        score(Score): Target score (infinite-length score allowed)
        default_tempo(float): If there is a section at the beginning of the
            score with no tempo events, the tempo for that section is assumed
            to be this value.
    """
    """
    スコアからテンポイベントを抽出したデータ構造 (テンポマップ) のクラスです。
    テンポマップは、任意時刻のテンポ値の取得やティック数(4分音符の1/480)と
    秒数との相互変換に利用できます。

    Args:
        score(Score): 対象となるスコア (無限長スコア可)
        default_tempo(float): スコア冒頭部分にテンポイベントがない区間が
            存在する場合、その区間のテンポはこの値であると仮定されます。
    """
    def __init__(self, score, default_tempo=125.0):
        self.event_iterator = score.tee().stream()
        self.tempo_list = [default_tempo]
        self.tempo_ticks_list = [0]
        self.seconds_list = [0]
        self.last_event_time = 0
        if not isinstance(score, EventStream):
            self._fill_list_until(math.inf)

    def _register_tempo_event(self, ev):
        self.seconds_list.append(self.seconds_list[-1] +
                                 ((ev.t - self.tempo_ticks_list[-1]) * 60 /
                                  (self.tempo_list[-1] * TICKS_PER_QUARTER)))
        self.tempo_list.append(ev.value)
        self.tempo_ticks_list.append(ev.t)

    def _fill_list_until(self, ticks):
        try:
            while (self.last_event_time != math.inf and
                   self.last_event_time <= ticks):
                ev = next(self.event_iterator)
                if isinstance(ev, TempoEvent):
                    self._register_tempo_event(ev)
                self.last_event_time = ev.t
        except StopIteration:
            self.last_event_time = math.inf

    def tempo_at(self, ticks) -> Union[int, float]:
        """
        Returns the tempo at `ticks` from the beginning of the score.

        Args:
            ticks(ticks): Ticks from the beginning of the score.

        Returns:
            Tempo value (BPM)
        """
        """
        スコア先頭からのティック数 `ticks` の時点におけるテンポを返します。

        Args:
            ticks(ticks): スコア先頭からのティック数

        Returns:
            テンポ値 (BPM)
        """
        self._fill_list_until(ticks)
        i = max(0, bisect_right(self.tempo_ticks_list, ticks) - 1)
        return self.tempo_list[i]

    def ticks2sec(self, ticks) -> float:
        """
        Converts ticks from the beginning of the score to seconds.

        Args:
            ticks(ticks): Ticks from the beginning of the score

        Returns:
            Seconds from the beginning of the score
        """
        """
        スコア先頭からのティック数を秒数へ変換します。

        Args:
            ticks(ticks): スコア先頭からのティック数

        Returns:
            スコア先頭からの秒数
        """
        self._fill_list_until(ticks)
        i = max(0, bisect_right(self.tempo_ticks_list, ticks) - 1)
        return self.seconds_list[i] + \
            ((ticks - self.tempo_ticks_list[i]) * 60 /
             (self.tempo_list[i] * TICKS_PER_QUARTER))

    def sec2ticks(self, seconds) -> Ticks:
        """
        Converts seconds from the beginning of the score to ticks.

        Args:
            seconds(float): Seconds from the beginning of the score

        Returns:
            Ticks from the beginning of the score
        """
        """
        スコア先頭からの秒数をティック数へ変換します。

        Args:
            seconds(float): スコア先頭からの秒数

        Returns:
            スコア先頭からのティック数
        """
        while True:
            i = max(0, bisect_right(self.seconds_list, seconds) - 1)
            ticks = self.tempo_ticks_list[i] + \
                ((seconds - self.seconds_list[i]) *
                 self.tempo_list[i] * TICKS_PER_QUARTER / 60)
            if ticks <= self.last_event_time:
                return int_preferred(ticks)
            self._fill_list_until(ticks)


class TimeSignatureMap(object):
    """
    This class represents a data structure (time signature map) in which
    time signature events are extracted from the score. This can be used to
    obtain time signature at arbitrary time or to convert between ticks and
    measure/beat numbers.

    If there are no time-signature events, the score is assumed to be in
    4/4 time.

    The measure (bar) number starts from 0 if there is a special measure
    ("Bar 0") at the beginning due to Auftakt, etc., otherwise it starts
    from 1. The first measure number can be obtained with ``ticks2mbt(0)[0]``.

    Args:
        score(Score): Target score (infinite-length score allowed)
        bar0len(ticks, optional): Specifies the length of Bar 0.
            If 0 is specified, it means that the score does not have Bar 0.
            If it is None, the length is inferred from the positions of
            the time signature events.
    """
    """
    スコアから拍子イベントを抽出したデータ構造 (time signature map) のクラス
    です。これは、任意時刻の拍子情報の取得やティック数と小節番号/拍数との
    相互変換に利用できます。

    拍子イベントがない場合は、4/4拍子であると仮定されます。

    小節番号は、冒頭に弱起等に起因する特別な小節がある場合は0から始まり、
    そうでない場合は1から始まります。最初の小節番号は ``ticks2mbt(0)[0]`` で
    取得できます。

    Args:
        score(Score): 対象となるスコア (無限長スコア可)
        bar0len(ticks, optional): 小節番号 0 の小節の長さを指定します。0を
            指定したときは、小節番号 0 の小節は無いとみなされます。Noneの
            場合は、拍子イベントの位置から推測されます。
    """
    def __init__(self, score, bar0len=None):
        self.score = score
        self.event_iterator = score.tee().stream()
        self.tsig_event_list = [TimeSignatureEvent(0, 4, 4, default=True)]
        self.tsig_ticks_list = [0]
        self.measures_list = [0]
        self.last_event_time = 0
        self.score_duration = None
        self.bar0len = bar0len
        if bar0len == 0:
            self.measures_list[0] = 1
        elif bar0len is not None:
            self.tsig_event_list.append(TimeSignatureEvent(bar0len, 4, 4,
                                                           default=True))
            self.tsig_ticks_list.append(bar0len)
            self.measures_list.append(1)
        else:
            # bar0lenがNoneの場合、最初の3小節のうち2番目と3番目の長さが同じで
            # かつ1番目の長さがその半分以下の場合に、小節番号を0から始める。
            first3 = [self.mbt2ticks(m) for m in range(1, 4)]
            if not (first3[1] - first3[0] == first3[2] - first3[1] and
                    first3[0] <= (first3[1] - first3[0]) / 2):
                for i in range(len(self.measures_list)):
                    self.measures_list[i] += 1
        if not isinstance(score, EventStream):
            self._fill_list_until(math.inf)

    def _register_tsig_event(self, ev):
        if ev.t >= self.tsig_ticks_list[-1]:
            self.measures_list.append(
                self.measures_list[-1] +
                int(math.ceil((ev.t - self.tsig_ticks_list[-1] - EPSILON) /
                              self.tsig_event_list[-1].measure_length())))
            self.tsig_event_list.append(ev.copy())
            self.tsig_ticks_list.append(ev.t)
        else:  # bar0len のイベントより前の場合
            self.tsig_event_list[-1].value = ev.value
            try:
                del self.tsig_event_list[-1].default
            except AttributeError:
                pass
            self.tsig_event_list.insert(-1, ev.copy())
            self.measures_list.insert(-1, 0)
            self.tsig_ticks_list.insert(-1, 0)

    def _fill_list_until(self, ticks):
        try:
            while (self.last_event_time != math.inf and
                   self.last_event_time <= ticks):
                ev = next(self.event_iterator)
                if isinstance(ev, TimeSignatureEvent):
                    self._register_tsig_event(ev)
                self.last_event_time = ev.t
        except StopIteration as e:
            self.score_duration = max(self.last_event_time, e.value)
            self.last_event_time = math.inf

    def timesig_at(self, ticks) -> TimeSignatureEvent:
        """
        Returns the time signature as of `ticks` from the beginning of
        the score.

        Args:
            ticks(ticks): Ticks from the beginning of the score.

        Returns:
            A time signature event. The attribute 'default' is added for
            the 4/4 time signature event compensated for scores with no
            indication of time signature.
        """
        """
        スコア先頭からのティック数 `ticks` の時点における拍子を返します。

        Args:
            ticks(ticks): スコア先頭からのティック数

        Returns:
            拍子イベント。拍子の指定がないスコアに対して補われた4/4拍子の
            イベントについては 'default' という属性が追加されています。
        """
        self._fill_list_until(ticks)
        i = max(0, bisect_right(self.tsig_ticks_list, ticks) - 1)
        return self.tsig_event_list[i]

    def num_measures(self) -> int:
        """
        Returns the total number of measures in the score; not available
        for EventStream.
        """
        """
        スコア全体の小節数を返します。EventStreamに対しては使えません。
        """
        mbt = self.ticks2mbt(self.score.get_duration() - EPSILON*2)
        return mbt[0] - self.measures_list[0] + 1

    def ticks2mbt(self, ticks) -> Tuple[int, Ticks, int, Ticks]:
        """
        Converts ticks from the beginning of the score to a 4-element tuple
        of (measure number, ticks within the measure, beat number, ticks
        within the beat).

        Args:
            ticks(ticks): Ticks from the beginning of the score

        Returns:
            The first element represents the measure number.
            The second element represents ticks within the measure.
            The third element represents the beat number in the measure,
            starting from 0.
            The last element represents ticks within the beat.
            The length of a beat depends on the time signature (e.g., in 3/8
            time, it is an eighth note (i.e., 240 ticks)).
        """
        """
        スコア先頭からのティック数を (小節番号、小節内ティック数、拍番号、
        拍内ティック数) の4要素タプルへ変換します。

        Args:
            ticks(ticks): スコア先頭からのティック数

        Returns:
            最初の要素は小節番号を表します。
            2番目の要素はその小節内におけるティック数を表します。
            3番目の要素は、その小節における 0から始まる拍番号を表します。
            最後の要素は、その拍内におけるティック数を表します。
            1拍の長さは拍子によって変わります（例えば 3/8拍子では 8分音符の
            長さ (=240ティック) になります)。
        """
        self._fill_list_until(ticks)
        i = max(0, bisect_right(self.tsig_ticks_list, ticks) - 1)
        mlen = self.tsig_event_list[i].measure_length()
        if self.bar0len is not None and ticks < self.bar0len:
            mlen = self.bar0len
        dur = ticks - self.tsig_ticks_list[i]
        m, mticks = int(self.measures_list[i] + dur // mlen), dur % mlen
        # 計算誤差によって微小時間の小節ができてしまうのを避ける。
        if mlen - mticks < EPSILON:
            m += 1
            mticks -= mlen
        blen = self.tsig_event_list[i].beat_length()
        b, bticks = int(mticks // blen), mticks % blen
        if blen - bticks < EPSILON:
            b += 1
            bticks -= blen
        return (m, int_preferred(mticks), b, int_preferred(bticks))

    def mbt2ticks(self, measures, beats=0, ticks=0) -> Ticks:
        """
        Given the measure number, the beat number, and additional ticks,
        it finds ticks from the beginning of the score.

        Args:
            measures(int or str): a measure number or a string of the form
                "`measures`[:\\ `beats`][+\\ `ticks`]"
                ("[]" means optional). If `beats` or `ticks` is specified
                in the string, the corresponding argument values show below
                are invalid.
                If a non-existent beat number is specified in the string,
                an exception is raised.
            beats(int or float, optional): The number of beats in the measure,
                starting from 0.
                The length of a beat depends on the time signature.
            ticks(ticks, optional): Ticks to be added,
                which may be longer than one beat.

        Returns:
            Ticks from the beginning of the score.
        """
        """
        小節番号、拍番号、および加算ティック数を与えて、スコア先頭からの
        ティック数を求めます。

        Args:
            measures(int or str): 小節番号、または
                "`measures`[:\\ `beats`][+\\ `ticks`]" という形式の文字列
                ("[]"は省略可を意味する)。
                文字列で `beats` や `ticks` を指定した場合、
                対応する以降の引数の値は無効となります。
                文字列で存在しない拍番号を指定したときは例外が送出されます。
            beats(int, optional): 0から始まる小節内の拍番号。
                1拍の長さは拍子によって変わります。
            ticks(ticks, optional): 加算されるティック数。1拍より長い
                値であっても構いません。

        Returns:
            スコア先頭からのティック数
        """
        beats_set_by_str = False
        if isinstance(measures, str):
            try:
                b = measures.split('+', maxsplit=1)
                a = b[0].split(':', maxsplit=1)
                measures = int(a[0])
                if len(a) >= 2 and a[1].strip() != '':
                    beats = float(a[1])
                    beats_set_by_str = True
                if len(b) >= 2 and b[1].strip() != '':
                    ticks = float(b[1])
            except Exception:
                raise ValueError("Invalid time representation") from None
        while True:
            i = max(0, bisect_right(self.measures_list, measures) - 1)
            mlen = self.tsig_event_list[i].measure_length()
            blen = self.tsig_event_list[i].beat_length()
            base_ticks = self.tsig_ticks_list[i] + \
                (measures - self.measures_list[i]) * mlen
            if base_ticks <= self.last_event_time:
                break
            self._fill_list_until(base_ticks)
        if beats_set_by_str and \
           (beats < 0 or beats >= self.tsig_event_list[i].numerator()):
            raise ValueError("Beat %d does not exist in Measure %d" %
                             (beats, measures)) from None
        return int_preferred(base_ticks + blen * beats + ticks)

    def iterator(self) -> Generator[Ticks, None, Ticks]:
        """
        A generator function that yields the start time of each measure
        in order.

        Yields:
            ticks: The start time of each measure

        Raises:
            StopIteration: Raised when the end of the score is reached.
                The 'value' attribute of this exception object contains
                the duration of the score.
        """
        """
        小節開始時刻を順にyield するジェネレータ関数です。

        Yields:
            ticks: 小節開始時刻

        Raises:
            StopIteration: スコアの最後に到達するとraiseされます。
                この例外オブジェクトのvalue属性には、スコアの演奏長が
                格納されます。
        """
        # 最後を yield でなくて StopIteration の value にしているのは、
        # chord_iterator に渡した時、最後にEnd-of-trackだけの小節ができる
        # のを防ぐため。
        m = self.measures_list[0]
        ticks = self.mbt2ticks(m)
        while True:
            m += 1
            next_ticks = self.mbt2ticks(m)
            # 1つ先の小節まで読まないと、最後の小節がEnd-of-trackだけのときに
            # その時刻がyieldとして出力されてしまう。
            if self.score_duration is not None and \
               ticks >= self.score_duration:
                return self.score_duration
            yield ticks
            ticks = next_ticks


class TimeMap(TempoMap, TimeSignatureMap):
    """
    This class integrates the TempoMap and TimeSignatureMap classes. If both
    functionalites are needed for a single score, it is more efficient to use
    this class because it requires only one score traversal.

    Args:
        score(Score): Target score (infinite-length score allowed)
        default_tempo(float): If there is a section at the beginning of the
            score with no tempo events, the tempo for that section is assumed
            to be this value.
        bar0len(ticks, optional): Specifies the length of Bar 0.
            If 0 is specified, it means that the score does not have Bar 0.
            If it is None, the length is inferred from the positions of
            the time signature events.
    """
    """
    TempoMap と TimeSignatureMap を統合したクラスです。両方のクラスの機能を
    併せ持っています。1つのスコアに対して両方の機能を必要とする場合は、
    このマップを使ったほうが、スコア走査が1回で済むため効率的です。

    Args:
        score(Score): 対象となるスコア (無限長スコア可)
        default_tempo(float): スコア冒頭部分にテンポイベントがない区間が
            存在する場合、その区間のテンポはこの値であると仮定されます。
        bar0len(ticks, optional): 小節番号 0 の小節の長さを指定します。0を
            指定したときは、小節番号 0 の小節は無いとみなされます。Noneの
            場合は、拍子イベントの位置から推測されます。
    """
    def __init__(self, score, default_tempo=125.0, bar0len=None):
        self.tempo_list = [default_tempo]
        self.tempo_ticks_list = [0]
        self.seconds_list = [0]
        TimeSignatureMap.__init__(self, score, bar0len)

    def _fill_list_until(self, ticks):
        try:
            while (self.last_event_time != math.inf and
                   self.last_event_time <= ticks):
                ev = next(self.event_iterator)
                if isinstance(ev, TempoEvent):
                    self._register_tempo_event(ev)
                elif isinstance(ev, TimeSignatureEvent):
                    self._register_tsig_event(ev)
                self.last_event_time = ev.t
        except StopIteration as e:
            self.score_duration = max(self.last_event_time, e.value)
            self.last_event_time = math.inf


class KeySignatureMap(object):
    """
    Class for a data structure (key signature map) that extracts key signature
    events from a score. This is used to obtain the key at any given time.

    If there is no key signature event, the key is assumed to be C major.

    Args:
        score(Score): Target score (infinite-length score allowed)
    """
    """
    スコアから調号イベントを抽出したデータ構造 (key signature map) のクラス
    です。これは任意時刻における調を取得するために利用されます。

    調号イベントがない場合は、ハ長調であると仮定されます。

    Args:
        score(Score): 対象となるスコア (無限長スコア可)
    """
    def __init__(self, score):
        self.event_iterator = score.tee().stream()
        self.has_keysig = [False]
        self.key_list = [[Key(0)]]
        self.ticks_list = [[0]]
        self.last_event_time = 0
        if not isinstance(score, EventStream):
            self._fill_list_until(math.inf)

    def _fill_list_until(self, ticks):
        try:
            while (self.last_event_time != math.inf and
                   self.last_event_time <= ticks):
                ev = next(self.event_iterator)
                if isinstance(ev, KeySignatureEvent):
                    while len(self.key_list) <= ev.tk:
                        self.has_keysig.append(False)
                        self.key_list.append([Key(0)])
                        self.ticks_list.append([0])
                    self.has_keysig[ev.tk] = True
                    self.key_list[ev.tk].append(ev.value)
                    self.ticks_list[ev.tk].append(ev.t)
                self.last_event_time = ev.t
        except StopIteration:
            self.last_event_time = math.inf

    def key_at(self, ticks, tk=0) -> Key:
        """
        Returns the key at `ticks` from the beginning of the score.

        Args:
            ticks(ticks): Ticks from the beginning of the score.
            tk(int): Specifies the track number. If there are any key
                signature events on this track, they are used to determine
                the key. If not, the key is determined based on the key
                signature events in Track 0.
        """
        """
        スコア先頭からのティック数 `ticks` の時点における調を返します。

        Args:
            ticks(ticks): スコア先頭からのティック数
            tk(int): トラック番号を指定します。そのトラックに調号イベントが
                が存在する場合、それらに基づいて調を決定します。無い場合は、
                トラック0に含まれる調号イベントに基づいて調を決定します。
        """
        self._fill_list_until(ticks)
        if tk > 0 and (tk >= len(self.key_list) or not self.has_keysig[tk]):
            tk = 0
        i = max(0, bisect_right(self.ticks_list[tk], ticks) - 1)
        return self.key_list[tk][i]
