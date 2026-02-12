# coding:utf-8
"""
This module defines the Score class and its subclasses.
"""
"""
このモジュールには、Scoreおよびその派生クラスが定義されています。
"""
# Copyright (C) 2025  Satoshi Nishimura

import math
import sys
import numbers
import collections
import collections.abc
import itertools
import operator
import heapq
from typing import Union, List, Generator, Callable, Optional
from pytakt.event import Event, NoteEvent, NoteOnEvent, NoteOffEvent, \
    NoteEventClass, CtrlEvent, KeyPressureEvent, TempoEvent, \
    KeySignatureEvent, TimeSignatureEvent, LoopBackEvent
from pytakt.constants import C_DATA, C_DATA_L, C_NRPCL, EPSILON, L32, \
    MAX_DELTA_TIME
from pytakt.utils import int_preferred, std_time_repr, NoteDict, Ticks
from pytakt.context import context

__all__ = ['Score', 'EventList', 'Tracks', 'EventStream', 'RealTimeStream',
           'seq', 'par', 'genseq', 'empty']


DEFAULT_LIMIT = 2e6


class Score(object):
    """
    This class is an abstract class for scores.
    A score is either an event list (an instance of the EventList class),
    an event stream (an instance of the EventStream class),
    or a Tracks container.
    An event list is a list of zero or more events, with an attribute
    called duration (see below) added.
    An event stream is an object that uses Python's generator mechanism
    to generate events in sequence, allowing for the representation of
    infinite-length scores.
    A Tracks container is a list of zero or more event lists or other Tracks
    containers as elements, representing a structure in which all elements
    are played concurrently.

    .. rubric:: Duration

    Scores have the concept of duration, which represents the length of
    the performance in ticks. In sequential concatenation of scores,
    the start time of the performance of a score is set to the start time
    of its previous score plus the duration of the score.
    The duration of an EventList is equal to the value of its duration
    attribute. The duration of a Tracks is the maximum duration among
    its components. The duration of an EventStream is the value attribute of
    the StopIteration exception raised when the end of the stream is reached.
    The duration is non-negative and is not necessarily equal to the maximum
    time of the events in the score; it may be greater or even less.

    .. rubric:: Arithmetic Rules

    * The '+' operator: If `s1` and `s2` are Score objects, then `s1 + s2`
      implies a sequential concatenation and returns a new score that plays
      the two scores in sequence. The result is an EventStream if `s2` is
      an EventStream, otherwise an EventList. `s1` must not be an EventStream.
      Each event in `s2` is copied and its time is shifted by the duraion
      of `s1`. The resulting score's duration is the sum of the durations
      of the two scores.
    * The '+=' operator: In `s1 += s2`, if `s1` is an EventList and `s2` is
      a score other than an EventStream, then the copied events of `s2` are
      added in-place to `s1`.
      Otherwise, it is equivalent to `s1 = s1 + s2`.
    * The '&' operator: If `s1` and `s2` are Score objects, then `s1 & s2`
      implies parallel merging and returns a new score that plays the two
      scores simultaneously. The result is an EventStream if one or both of
      `s1` and `s2` are EventStream, otherwise an EventList. No copying of
      events is performed. The duration of the resulting score will be
      either the durations of the two scores, whichever is greater.
    * The '&=' operator: In `s1 &= s2`, if `s1` is an EventList and `s2` is
      a score other than an EventStream, then the events in `s2` are added
      in-place to `s1`. Otherwise, it is equivalent to `s1 = s1 & s2`.
    * The '*' operator:
      The product of a Score object and an integer is a score that repeats
      the original score by the integer value. `s1` must not be an
      EventStream. The result will always be an EventList.

    Examples:
        ``(note(C4) + note(D4) + note(E4)).play()``

        ``(note(C4) & note(E4) & note(G4)).play()``

        ``(note(C4) * 16).play()``
    """
    """ Scoreクラスはスコアの抽象クラスです。
    スコアはイベントリスト (EventListクラスのオブジェクト) か、
    イベントストリーム (EventStreamクラスのオブジェクト) か、
    Tracks コンテナのいずれかです。
    イベントリストは、0個以上のイベントを要素とするリストに、後述する演奏長
    についての属性を付加したものです。
    イベントストリームは、ジェネレータの仕組みを利用してイベントを順に生成する
    オブジェクトで、無限長スコアの表現を可能にします。
    Tracks コンテナは 0個以上のイベントリストまたは他の Tracks コンテナを要素
    とするリストで、すべての要素を同時並行で演奏するという構造を表します。

    .. rubric:: 演奏長

    スコアには演奏長という概念があり、これはティック単位でのスコアの長さを
    表します。逐次結合において、あるスコアの演奏開始時刻は、
    １つ前のスコアの演奏開始時刻にこの値を加えたものとなります。
    スコアが EventList の場合はそのduration属性の値、Tracks の場合は
    その構成要素の演奏長の最大値、EventStream の場合は StopIteration例外が持つ
    value属性の値が演奏長となります。
    演奏長は非負の値で、スコアに含まれるイベントの時刻の最大値と等しいとは
    限らず、それより大きくても、また小さくても構いません。

    .. rubric:: 演算規則

    * '+' 演算子: `s1`, `s2` をScoreオブジェクトとしたとき、`s1 + s2` は
      逐次結合を意味し、2つのスコアを逐次的に演奏する新たなスコアを返します。
      結果は、`s2` が EventStream なら EventStream、それ以外なら EventList に
      なります。`s1` は EventStream であってはなりません。
      `s2` における各イベントはコピーされた上で、`s1` の演奏長の分だけ時刻が
      ずらされます。
      結果となるスコアの演奏長は、2つのスコアの演奏長の和になります。
    * '+=' 代入演算子: `s1 += s2` においては、`s1` が EventList でかつ `s2` が
      EventStream以外のスコアならば、`s2` に含まれるイベントが (コピーされ時刻
      がずらされた上で) インプレースに `s1` に追加されます。
      そうでなければ、`s1 = s1 + s2` と等価です。
    * '&' 演算子: `s1`, `s2` をScoreオブジェクトとしたとき、`s1 & s2` は、
      並列結合を意味し、2つのスコアを同時に演奏する新たなスコアを返します。
      結果は、`s1` と `s2` の一方または両方が EventStream なら EventStream、
      それ以外なら EventList になります。イベントのコピーは行われません。
      結果となるスコアの演奏長は、2つのスコアの演奏長のうちより大きい方になり
      ます。
    * '&=' 代入演算子: `s1 &= s2` においては、`s1` が EventList でかつ `s2` が
      EventStream以外のスコアならば、`s2` に含まれるイベントがインプレースに
      `s1` に追加されます。そうでなければ、`s1 = s1 & s2` と等価です。
    * '*' 演算: Scoreオブジェクトと整数の積は、元のスコアを整数の値の分だけ
      繰り返し演奏するスコアになります。Scoreオブジェクトは EventStream で
      あってはなりません。結果は常に EventList になります。

    Examples:
        ``(note(C4) + note(D4) + note(E4)).play()``

        ``(note(C4) & note(E4) & note(G4)).play()``

        ``(note(C4) * 16).play()``
    """

    __slots__ = ()

    def __init__(self):
        raise Exception("Score is an abstract class. Use seq() "
                        "for an empty score")

    def __iadd__(self, other):
        # self が EventList で other が EventStream以外の場合に限り、追加。
        if isinstance(self, EventList) and not isinstance(other, EventStream):
            if isinstance(other, Tracks):
                offset = self.duration
                for evlist in other:
                    self.merge(evlist.deepcopy(), offset)
            elif isinstance(other, EventList):
                self.merge(other.deepcopy(), self.duration)
            else:
                raise Exception("%r is not a valid score element" %
                                other.__class__.__name__)
            return self
        else:
            return self.__add__(other)

    def __add__(self, other):
        if not isinstance(other, Score):
            raise Exception("%r is not a valid score element" %
                            other.__class__.__name__)
        if isinstance(self, EventStream):
            # 左項にEventStreamを許可しないのは、durationを簡単には取得でき
            # ない (左項のストリームを全部読み取れば取得できるが結果の
            # EventStreamが一度も読まれなくても全部読まれてしまうのは望ましく
            # ない）ため、右項からのイベントの開始時刻を決定できないから。
            raise Exception("EventStream cannot be followed by other "
                            "score elements")
        if isinstance(other, EventStream):
            # 右のストリームは、tee() はしないが、イベントはコピー
            return self.stream().merged(
                other.stream(copy=True), self.get_duration())
        else:
            # 属性はなくなる。
            result = EventList(self)
            offset = result.duration
            if isinstance(other, Tracks):
                for evlist in other:
                    result.merge(evlist.deepcopy(), offset)
            else:
                result.merge(other.deepcopy(), offset)
            return result

    def __iand__(self, other):
        if isinstance(self, EventList) and not isinstance(other, EventStream):
            if isinstance(other, Tracks):
                for evlist in other:
                    self.merge(evlist)
            elif isinstance(other, EventList):
                self.merge(other)
            else:
                raise Exception("%r is not a valid score element" %
                                other.__class__.__name__)
            return self
        else:
            return self.__and__(other)

    def __and__(self, other):
        # other のイベントをコピーしない。
        if not isinstance(other, Score):
            raise Exception("%r is not a valid score element" %
                            other.__class__.__name__)
        if isinstance(self, EventStream) or isinstance(other, EventStream):
            return self.stream().merged(other.stream())
        else:
            result = EventList(self)
            if isinstance(other, Tracks):
                for evlist in other:
                    result.merge(evlist)
            else:
                result.merge(other)
            return result

    def __mul__(self, repeats):
        if not isinstance(repeats, numbers.Integral):
            raise TypeError("can only multiply integer to score elements")
        else:
            return seq(self for _ in range(repeats))
    __rmul__ = __mul__

    # まだ実験的
    def __or__(self, other):
        if callable(other):
            return other(self)
        else:
            return NotImplemented

    def __str__(self):
        return self.tostr()

    def __repr__(self):
        return self.tostr(repr)

    def tostr(self, timereprfunc=std_time_repr) -> str:
        """ Returns a string representation of the score.

        Args:
            timereprfunc(function): Function to convert a value of time to
                a string. By default, it assumes a function that returns
                a representation rounded to 5 decimal places.
        """
        """ 文字列に変換したものを返します。

        Args:
            timereprfunc(function): 時間の値を文字列に変換する関数。
                デフォルトでは小数点以下5桁に丸められた表現を返す
                関数になります。
        """
        raise Exception("Score.tostr is an abstract method.")

    # listと一緒に多重継承したときに、listから継承されるメソッドを無効化する
    __lt__ = object.__lt__
    __le__ = object.__le__
    __gt__ = object.__gt__
    __ge__ = object.__ge__

    def get_duration(self) -> Ticks:
        """ Returns the duration of the score.
        Not available for EventStream. """
        """ スコアの演奏長を返します。EventStream に対しては使えません。"""
        raise Exception("Score.get_duration() is an abstract method.")

    def tee(self) -> 'Score':
        """ If the score is an EventStream, returns a new equivalent generator
        that can be read independently without changing the read state of the
        original generator. For scores of any other type, returns `self` as is.
        """
        """ スコアが EventStream である場合、元のジェネレータの読み取り状態を
        変えることなく独立に読み出しできるような、新たな等価ジェネレータを
        返します。それ以外の型のスコアの場合は、`self` をそのまま返します。
        """
        raise Exception("Score.tee() is an abstract method.")

    def count(self) -> int:
        """ Returns the number of events in the score.
        Not available for EventStream. """
        """ スコア中のイベント数を返します。EventStream に対しては使えません。
        """
        raise Exception("Score.count() is an abstract method.")

    def mapev(self, func, durfunc=None) -> 'Score':
        """ Calls the function `func` for each event in the score and
        returns a new score where each event is replaced by the return value
        of `func`. The type of the score and the order of events in the score
        remain the same.

        The function `func` is called in the order of appearance of events in
        the score, not necessarily in chronological order.

        The function `func` can return not only a single event, but also None
        or a list of events, which allows insertion or deletion of events.

        Remark: For an EventStream, `func` must not change the value of
        the t attribute in such a way that the time order of the events is
        changed.

        Args:
            func(function): For each event `ev`, this function is called in
                the form `func(ev)`. The return value of this function must be
                of type Event, None, or an iterable of Event.
            durfunc(function, optional): Specifies the function to convert the
                duration. The function is called in the form `durfunc(d)` for
                the duration `d` of the original score, and the return value
                will be the duration of the new score. By default, the original
                score's duration is used in the new score.

        Examples:
            ``score.mapev(lambda ev: ev.update(tk=0))``
                Returns a score of all events with the track number set to 0.
                The original events are overwritten.

            ``score.mapev(lambda ev: ev.copy().update(ch=3)) \
if hasattr(ev, 'ch') else ev)``
                Returns a score with the channel number changed to 3.
                (This is equivalent to ``Modify('ch=3')`` using
                :class:`.Modify`.)

            ``score.mapev(lambda ev: None if hasattr(ev, 'ch') and ev.ch==2 \
else ev)``
                Returns a score where events with channel number 2 are removed.

            ``score.mapev(lambda ev: ev.copy().update(t=ev.t * 2), \
durfunc=lambda d: d*2)``
                Returns a score with time stretched by a factor of 2.
        """
        """ スコア中の各イベントに対して関数 `func` を呼び、その戻り値で
        置き換えた新しいスコアを返します。スコアの型、およびスコア内の
        イベントの順序は変わりません。

        関数 `func` はイベントのスコアにおける出現順で呼ばれます。必ずしも
        時刻順とは限りません。

        関数 `func` は単一のイベントだけなく、Noneやイベントのリストを返すこと
        ができ、これによりイベントの挿入や削除が可能です。

        注意： EventStreamに対して、`func` でイベントの時刻順が入れ替わる
        ような t属性値の変更をしてはいけません。

        Args:
            func(function): 各イベント `ev` に対して `func(ev)` の形式で
                この関数が呼ばれます。この関数の戻り値は Event型、None、
                もしくは Eventのイテラブルでなければなりません。
            durfunc(function, optional): 演奏長を変換する関数を指定します。
                元スコアの演奏長 `d` に対して `durfunc(d)` の形式でこの関数が
                呼ばれ、その戻り値が新しいスコアの演奏長になります。デフォルト
                では元の演奏長がそのまま使われます。

        Examples:
            ``score.mapev(lambda ev: ev.update(tk=0))``
                 すべてのイベントのトラック番号を0にしたスコアを返します。
                 元のイベントが書き換えられます。

            ``score.mapev(lambda ev: ev.copy().update(ch=3) \
if hasattr(ev, 'ch') else ev)``
                 チャネル番号を3に変更したスコアを返します。
                 (これは、:class:`.Modify` を用いた ``Modify('ch=3')`` と
                 等価の変換です。)

            ``score.mapev(lambda ev: None if hasattr(ev, 'ch') and ev.ch==2 \
else ev)``
                 チャネル番号が2のイベントを削除したスコアを返します。

            ``score.mapev(lambda ev: ev.copy().update(t=ev.t * 2), \
durfunc=lambda d: d*2)``
                 時間を2倍に伸張したスコアを返します。
        """
        def _mapev(iterator):
            try:
                while True:
                    ev = next(iterator)
                    rtn = func(ev)
                    if isinstance(rtn, Event):
                        yield rtn
                    elif rtn is None:
                        pass
                    else:
                        try:
                            for subev in rtn:
                                if not isinstance(subev, Event):
                                    raise TypeError()
                                yield subev
                        except TypeError:
                            raise TypeError("mapev: bad return-value "
                                            "of the function")
            # 現在の実装では、funcがStopIterationを送出したとき、ストリームを
            # 打ち切るようになっている。
            except StopIteration as e:
                return None if e.value is None else durfunc(e.value)

        if durfunc is None:
            durfunc = (lambda t: t)
        if isinstance(self, EventList):
            return self.__class__(_mapev(iter(self)),
                                  durfunc(self.duration), **self.__dict__)
        elif isinstance(self, Tracks):
            return self.__class__((elm.mapev(func, durfunc) for elm in self),
                                  **self.__dict__)
        elif isinstance(self, EventStream):
            return self.__class__(_mapev(self), **self.__dict__)
        else:
            raise Exception("%r is not a score" % self.__class__.__name__)

    def chord_mapev(self, func, time_tolerance=None) -> Union[
            'EventList', 'EventStream']:
        """
        For each event in the score, it calls the function `func` with
        additional information about the number of notes being played
        simultaneously and pitch position within those, and returns
        a new score where each event is replaced by the return value of `func`.
        If the original score is Tracks, the result is an EventList.
        For other types of scores, the type remains the same.

        The function `func` is called in the order of time of the events
        (i.e., ascending order of the t attribute values). If they occur
        at the same time, they are called in the order of their appearance
        in the score.

        The function `func` can return not only a single event, but also None
        or a list of events, which allows insertion or deletion of events.

        Args:
            func(function): For each event `ev`, this function is called in
                the form `func(i, m, ev)`, where `i` is the ranking number in
                terms of pitch among the notes being played at the same time
                (0 <= `i` < `m` and 0 representing the lowest note) and `m` is
                the number of notes being played at the same time.
                Events not belonging to NoteEventClass will have both `i`
                and `m` equal to 0.
                The return value of this function must be of type Event,
                None, or an iterable of Event.
            time_tolerance(float, optional):
                See :meth:`chord_iterator` argument of the same name.

        Examples:
            ``score.chord_mapev(lambda i, m, ev: ev.copy().update(v=ev.v + \
(i==m-1)*10) if hasattr(ev, 'v') else ev)``
                Returns a score with the velocity of the highest note of
                each chord increased by 10.
        """
        """ スコア中の各イベントに対して、同時に発音されている音の数や、その
        中で何番目に低い音かの情報とともに関数 `func` を呼び、その戻り値で
        置き換えた新しいスコアを返します。元のスコアが Tracks である場合、
        結果は EventList になります。それ以外のスコアでは型は変わりません。

        関数 `func` はイベントの時刻順（t属性値の昇順。同時刻の場合はスコア
        での出現順）に呼ばれます。

        関数 `func` は単一のイベントだけなく、Noneやイベントのリストを返すこと
        ができ、これによりイベントの挿入や削除が可能です。

        Args:
            func(function): 各イベント `ev` に対して `func(i, m, ev)` の
                形式で、この関数が呼ばれます。`i` は、同時に発音されている
                音の中での音高の順番(0 <= `i` < `m`で、0が最低音)、`m` は
                同時に発音されている音の数を表します。
                :class:`.NoteEventClass` に属さないイベントでは `i` も `m`
                も 0 になります。
                この関数の戻り値は Event型、None、もしくはEventのイテラブル
                でなければなりません。
            time_tolerance(float, optional):
                :meth:`chord_iterator` の同名の引数を参照。

        Examples:
            ``score.chord_mapev(lambda i, m, ev: ev.copy().update(v=ev.v + \
(i==m-1)*10) if hasattr(ev, 'v') else ev)``
                和音の最高音に対してベロシティを10加算したスコアを返します。
        """
        # chord_iterator()を呼んでいる。
        def gen():
            iterator = self.chord_iterator(time_tolerance=time_tolerance)
            notedict = NoteDict()
            while True:
                try:
                    evlist = next(iterator)
                    notes = [(ev, ev.n) for ev in evlist
                             if isinstance(ev, (NoteEvent, NoteOnEvent))]
                    notes.sort(key=lambda x: x[1])
                    # rankはイベントからコード内の順番へ変換する辞書
                    rank = dict((ev, i) for i, (ev, _) in enumerate(notes))
                    for ev in evlist:
                        if ev.t >= evlist.start:
                            if isinstance(ev, (NoteEvent, NoteOnEvent)):
                                i, m = rank[ev], len(notes)
                                if isinstance(ev, NoteOnEvent):
                                    notedict.pushnote(ev, (i, m))
                            elif isinstance(ev, NoteOffEvent):
                                try:
                                    i, m = notedict.popnote(ev)
                                except KeyError:
                                    i, m = 0, 0
                            else:
                                i, m = 0, 0

                            rtn = func(i, m, ev)
                            if isinstance(rtn, Event):
                                yield rtn
                            elif rtn is None:
                                pass
                            else:
                                try:
                                    for subev in rtn:
                                        if not isinstance(subev, Event):
                                            raise TypeError()
                                        yield subev
                                except TypeError:
                                    raise TypeError(
                                        "chord_mapev: bad return-value "
                                        "of the function")
                except StopIteration as e:
                    return e.value

        cls = EventList if isinstance(self, Tracks) else self.__class__
        return cls(gen(), **self.__dict__)

    def mapstream(self, func, *, sort_by_ptime=False) -> 'Score':
        """
        For each event list or event stream in the score, it calls the
        transforming function `func` on the stream, and returns a new score
        replaced by the event stream that the function generates.
        The type of the score does not change (an event list is converted to
        an event stream, `func` is applied, and then it is converted back to
        an event list again).
        Each event is not copied unless explicitly done within the
        transforming function.

        Args:
            func(function): A generator function to transform an event
                sequence. The function is called on the input stream `stream`
                in the form `func(stream)`. The `stream` is the one converted
                by :meth:`stream` in the case of an event list, or itself
                in the case of an event stream.
                The 'value' attribute of the StopIteration raised at the end
                of `stream` contains the duration of the score.
                The generator function `func` should return an iterator of
                events such that StopIteratoin has the converted duration
                (such a function can be implemented by outputting converted
                events with 'yield' and returning the converted duration
                with 'return').
            sort_by_ptime(bool):
                If this is True, the event stream passed as the argument to
                `func` will be sorted by performance time (the sum of the t
                attribute value and the dt attribute value). It is assumed
                that the order of events yielded by `func` is also in the
                order of performance time.
        """
        """ スコア中のイベントリストやイベントストリームに対して、
        ストリームに対する変換関数 `func` を呼び、それが生成するストリーム
        で置き換えた新しいスコアを返します。
        スコアの型は変わりません（イベントリストはストリームに変換されて
        `func` を適用した後、再びイベントリストに戻されます）。
        各イベントは、変換関数内で明示的に行わない限りコピーされません。

        Args:
            func(function): イベント列を変換するジェネレータ関数。入力
                ストリーム `stream` に対して `func(stream)` の形式でこの関数
                が呼ばれます。`stream` はイベントリストの場合 :meth:`stream`
                で変換されたもの、イベントストリームの場合はそれ自身に
                なります。入力ストリームが発する StopIteration の value 属性
                には、スコアの演奏長が格納されます。
                ジェネレータ関数 `func` は、StopIteratoinに
                変換後の演奏長を持つようなイベントのイテレータを返す必要
                があります (関数内で、変換後のイベントを順に yield し、変換後
                の演奏長を return すれば、そのような関数になります）。
            sort_by_ptime(bool):
                Trueの場合、`func` に引数として渡されるイベントストリームが、
                演奏上の時刻（t属性値とdt属性値の和) でソートされたものに
                なります。`func` が yield するイベントの順序も演奏上の時刻順
                であることを前提としています。
        """
        if isinstance(self, EventList):
            if sort_by_ptime:
                return self.__class__(
                    func(self.stream()._sorted(use_ptime=True)),
                    **self.__dict__).sorted()
            return self.__class__(func(self.stream()), **self.__dict__)
        elif isinstance(self, Tracks):
            return self.__class__((s.mapstream(func) for s in self),
                                  **self.__dict__)
        elif isinstance(self, EventStream):
            if sort_by_ptime:
                return self.__class__(func(self._sorted(use_ptime=True)),
                                      **self.__dict__)._sorted()
            return self.__class__(func(self), **self.__dict__)
        else:
            raise Exception("%r is not a score" % self.__class__.__name__)

    def evlist(self, *, limit=DEFAULT_LIMIT) -> 'EventList':
        """
        Converts a score to a new event list where events are sorted in
        chronological order.
        ``score.evlist()`` is equivalent to ``EventList(score)``.

        Args:
            limit (ticks, optional):
                If the score is an EventStream, it limits its length.
                See the `limit` argument of :meth:`Score.stream` for details.
        """
        """
        スコアを、イベントが時刻順にソートされた新たなイベントリストへ
        変換します。``score.evlist()`` は ``EventList(score)`` と等価です。

        Args:
            limit (ticks, optional):
                スコアが EventStream であるときにスコアの長さを制限します。
                詳細については、:meth:`Score.stream` の同名の引数の項目を
                ご覧ください。
        """
        return EventList(self, limit=limit)

    def stream(self, copy=False, *, limit=None) -> 'EventStream':
        """
        Converts a score to an event stream. The returned EventStream object
        yields the events in the score in chronological order (ascending order
        of the t attribute values).
        Events that occur at the same time are yielded in the order of their
        appearance in the score.
        The returned EventStream will raise a StopIteration exception
        when the end of the score is reached, and the 'value' attribute of
        this exception object will contain the duration of the score (or
        the value of `limit` if the `limit` is reached).

        Args:
            copy(bool, optional): If True, copied events are yielded.
            limit(ticks, optional):
                If given, limits the length of the score if `self` is
                an EventStream, and will warn and raise a StopIteration
                exception when it sees an event with a time greater than
                this value (the observed event will not be yielded).
                It has no effect on scores other than EventStream.
        """
        """
        スコアをイベントストリームへ変換します。返される EventStream
        オブジェクトは、スコアに含まれるイベントを時刻順 (t属性値の昇順) に
        yieldします。
        同時刻のイベントについては、スコアでの出現順でyieldされます。
        また、返される EventStream は、スコアの最後に到達すると StopIteration
        例外を送出しますが、この例外オブジェクトのvalue属性には、スコアの演奏長
        （ただし、`limit` に達した場合は `limit` の値）が格納されます。

        Args:
            copy(bool, optional): Trueならばコピーされたイベントが
                yieldされます。
            limit(ticks, optional):
                与えた場合、`self` が EventStream であるときにスコアの長さを
                制限し、この値以上の時刻を持つイベントを観測した時点で、
                警告を出すともに StopIteration 例外を送出します (その観測
                されたイベントは yield されません)。
                EventStream 以外のスコアに対しては効果がありません。
        """
        def _gen():
            if isinstance(self, EventList):
                if copy:
                    for ev in self.sorted():
                        yield ev.copy()
                else:
                    for ev in self.sorted():
                        yield ev
                return self.duration
            elif isinstance(self, EventStream):
                while True:
                    try:
                        ev = next(self)
                    except StopIteration as e:
                        return e.value
                    if limit is not None and ev.t >= limit:
                        print("Warning: Score too long - truncated at %r" %
                              limit, file=sys.stderr)
                        return limit
                    yield ev.copy() if copy else ev
            elif isinstance(self, Tracks):
                def _collect_evlist(s, buf):
                    if isinstance(s, EventList):
                        buf.extend(s)
                    else:
                        for elm in s:
                            _collect_evlist(elm, buf)
                buf = EventList(duration=self.get_duration())
                _collect_evlist(self, buf)
                return (yield from buf.stream(copy, limit=limit))
            else:
                raise Exception("%r is not a score" % self.__class__.__name__)

        cls = self.__class__ if isinstance(self, EventStream) else EventStream
        return cls(_gen(), **self.__dict__)

    def chord_iterator(self, time_sequence=None, *, cont_notes=True,
                       copy=False, time_tolerance=None,
                       limit=None) -> Generator['EventList', None, Ticks]:
        """
        This ia a generator function that yields the information for each time
        span of the score in chronological order.
        Each yielded object is an EventList that contains the events that
        exist in the span and, optionally, the events for notes that have been
        continued since the previous span.
        The EventList has an additional attribute named 'start', which
        contains the start time of the span. The end time of the span is
        stored in the duration attribute.
        The order of events in the EventList follows that of :meth:`stream`.

        Args:
            time_sequence(None, ticks, or iterable of ticks, optional):
                Specifies how to delimit the spans;
                if None (default), the span boundaries are time positions
                where one or more note-ons or note-offs (including
                note-off implied by NoteEvent, that is, the time at
                the sum of its t and L attributes) exist.
                If it is an int or a float, spans are formed with a constant
                interval of that value.
                If it is an int or float iterable, each element of the
                iterable is the time of the span boundary.
                Each span is defined to be greater than or equal to the time
                of a boundary and less than or equal to the time of the next
                boundary.
            cont_notes(bool, optional):
                If True, an additional reference to the NoteEvent or
                NoteOnEvent is inserted into EventList for notes that have
                been continued since the previous span.
                Note that whether or not events are such additional
                references can be determined by comparing the time of the event
                and the start time of the span: an event `ev` is an
                additional reference if `ev.t < evlist.start` where
                `evlist` is the event list yielded.
            copy(bool, optional): If True, the event list to be yielded will
                contain the copied events. If `cont_notes` is True, additional
                references are to the copy.
            time_tolerance(float, optional):
                This is meaningful only when `time_sequence` is None.
                Note-ons and note-offs within this value of time difference
                are considered to be the same time and have a single span
                boundary.
                If omitted, it is set to 50 ticks if `self` is a
                RealTimeStream; otherwise it is set to 10\\ :sup:`-6`.
            limit(ticks, optional):
                Has the same meaning as the 'limit' argument of :meth:`stream`.

        Yields:
            EventList:

        Raises:
            StopIteration: Raised when the end of the score is reached.
                The 'value' attribute of this exception object contains
                the duration of the score. It is also raised when the `limit`
                is reached, in which case the value attribute will contain
                the value of the `limit`.

        Tip:
            From the output sequence of chord_iterator(), you can get the
            score of the same performance as the original (but the duration
            may be different) by the following::

                par(EventList((ev for ev in evlist if ev.t >= evlist.start),
                              evlist.duration)
                    for evlist in score.chord_iterator())

            or ::

                par(score.chord_iterator(cont_notes=False))

        Examples:
            The program below calculates the maximum number of simultaneous
            played notes for a non-empty score s::

                max(sum(isinstance(ev, (NoteEvent, NoteOnEvent)) for ev in \
evlist)
                    for evlist in s.chord_iterator())

            The program below displays a list of sounding pitches for each
            sixteenth-note span::

                for evlist in s.chord_iterator(L16):
                    print(evlist.start,
                          [ev.n for ev in evlist if \
isinstance(ev, (NoteEvent, NoteOnEvent))])

            The program below prints an event list for each measure::

                tm = TimeMap(s)
                for m, evlist in enumerate(s.chord_iterator(tm.iterator())):
                    print(f'Measure {m + tm.ticks2mbt(0)[0]}:', evlist)
        """
        """
        スコアを時間区間ごとに区切って各区間の情報を時刻順に yield する
        ジェネレータ関数です。
        yield されるのは EventList で、当該区間内に存在するイベント、および
        オプションで、前の区間から継続して発音されている音のイベントを含んで
        います。
        この EventList には start という属性が追加されていて、そこに区間の
        開始時刻が格納され、更に、duration属性には区間の終了時刻が格納されて
        います。
        EventList 内でのイベントの順序は :meth:`stream` に準じます。

        Args:
            time_sequence(None, ticks, or iterable of ticks, optional):
                区間の区切り方を指定します。None(デフォルト)の場合、
                ノートオンまたはノートオフの存在する時刻（これは NoteEvent
                のノートオフ時刻、つまりt属性とL属性の和の時刻も含みます）
                が区切り位置となります。
                intまたはfloatの場合は、その値を周期として一定間隔に
                区切られます。intまたはfloatのiterableならば、その各要素
                が区切り位置の時刻になります。各区間は、ある区切り位置の時刻
                以上、次の区切り位置の時刻未満で定義されます。
            cont_notes(bool, optional):
                Trueの場合、前の区間から継続して発音されている音 (continued
                notes) について、その NoteEvent または NoteOnEvent への
                追加参照が EventList に挿入されます。
                なお、これらのイベントが追加参照であるかどうかは、イベントの
                時刻が区間の開始時刻より小さいかどうかで判別できます
                （すなわち、yield されたイベントリストを `evlist`、
                判別すべきイベントを `ev` としたとき、
                `ev.t < evlist.start` なら追加参照です）。
            copy(bool, optional): Trueならば、yield されるイベントリストには
                コピーされたイベントが格納されます。`cont_notes` が True
                のときの追加参照は、コピーへの参照となります。
            time_tolerance(float, optional):
                time_sequenceがNoneのときに意味を持ち、時刻差がこの値以内の
                ノートオン、ノートオフを同一時刻とみなして区切りを1つとします。
                省略された場合、`self` が RealTimeStream であれば 50ティック、
                そうでなければ 10\\ :sup:`-6` に設定されます。
            limit(ticks, optional):
                :meth:`stream` のlimit引数と同じ意味を持ちます。

        Yields:
            EventList:

        Raises:
            StopIteration: スコアの最後に到達するとraiseされます。
                この例外オブジェクトのvalue属性には、スコアの演奏長が
                格納されます。また、`limit` に達した場合も raiseされ、その
                ときは value属性に `limit` の値が格納されます。

        Tip:
            chord_iterator() の出力列から次のようにして元と同じ演奏のスコアを
            得ることができます (ただし、演奏長は異なる場合があります)::

                par(EventList((ev for ev in evlist if ev.t >= evlist.start),
                              evlist.duration)
                    for evlist in score.chord_iterator())

            または::

                par(score.chord_iterator(cont_notes=False))

        Examples:
            下のプログラムは、空でないスコア s について最大同時発音数を計算
            します::

                max(sum(isinstance(ev, (NoteEvent, NoteOnEvent)) for ev in \
evlist)
                    for evlist in s.chord_iterator())

            下のプログラムは、16分音符ごとに発音中の音のリストを表示します::

                for evlist in s.chord_iterator(L16):
                    print(evlist.start,
                          [ev.n for ev in evlist if \
isinstance(ev, (NoteEvent, NoteOnEvent))])

            下のプログラムは、小節ごとにイベントリストを表示します::

                tm = TimeMap(s)
                for m, evlist in enumerate(s.chord_iterator(tm.iterator())):
                    print(f'Measure {m + tm.ticks2mbt(0)[0]}:', evlist)
        """
        # NoteEvent, NoteOnEvent-NoteOffEventのどちらにも対応している。
        # durationが区間の長さでなく終了時刻となっているのは、各イベントの
        # 時刻が区間開始ではなくスコア先頭を0とした時刻だから。
        if isinstance(time_sequence, numbers.Real):
            if time_sequence <= 0:
                raise ValueError("can't use a non-positive time step")
        elif time_sequence is not None:
            time_sequence = iter(time_sequence)
        buf = []  # 現在の区間内のイベントを格納するバッファ
        basetime = 0  # 区間開始時刻
        nexttime = 0  # 次の区切り時刻 (time_sequenceがNoneの時は使用しない)
        notedict = NoteDict()
        rts = isinstance(self, RealTimeStream)
        if time_tolerance is None:
            time_tolerance = 50 if rts else EPSILON
        lbobj = ['_chord_iterator']
        lbqueued = False
        if rts:
            lbev = LoopBackEvent(0, lbobj)
            if time_sequence is not None:
                self.queue_event(lbev)

        def flush(time):  # バッファ内容をyieldする。timeは区間終了時刻。
            nonlocal buf, basetime, nexttime
            nextbuf = []
            if cont_notes:
                for ev in notedict.values():
                    # timeで終わるノートもここで挿入されるが、
                    # 後で buf.remove() により削除される。
                    nextbuf.append(ev)
            if buf or time - basetime > 0:
                yield EventList(buf, duration=time, start=basetime)
            basetime = time
            if isinstance(time_sequence, numbers.Real):
                nexttime += time_sequence
            elif time_sequence is not None:
                nt = next(time_sequence, math.inf)
                if nt < 0:
                    raise Exception("can't use the negative time %r" % nt)
                if nt < nexttime:
                    raise Exception("can't use a decreasing time sequence")
                nexttime = nt
            buf = nextbuf

        yield from flush(0)  # nexttimeを得る
        iterator = self.stream(copy, limit=limit).noteoff_inserted()
        try:
            while True:
                ev = next(iterator)
                if rts:
                    if isinstance(ev, LoopBackEvent) and ev.value is lbobj:
                        yield from flush(ev.t)
                        lbqueued = False
                        if time_sequence is not None:
                            self.queue_event(lbev.update(t=nexttime))
                    if isinstance(ev, NoteEventClass) and not lbqueued:
                        if time_sequence is None:
                            lbev.t = ev.t + time_tolerance
                            self.queue_event(lbev)
                            lbqueued = True
                else:
                    if time_sequence is None:
                        if isinstance(ev, NoteEventClass) and \
                           ev.t > basetime + time_tolerance:
                            yield from flush(ev.t)
                    else:
                        while ev.t >= nexttime:
                            yield from flush(nexttime)

                if isinstance(ev, NoteEvent):
                    notedict.push(ev, ev)
                    buf.append(ev)
                elif isinstance(ev, NoteOnEvent):
                    notedict.pushnote(ev, ev)
                    buf.append(ev)
                elif isinstance(ev, NoteOffEvent):
                    if hasattr(ev, 'noteon'):
                        noteon = notedict.pop(ev.noteon)
                    else:
                        noteon = notedict.popnote(ev, None)
                        buf.append(ev)
                    if cont_notes and ev.t <= basetime + time_tolerance \
                       and noteon is not None \
                       and noteon.t < basetime:  # keep zero-duration notes
                        buf.remove(noteon)
                elif not (isinstance(ev, LoopBackEvent) and ev.value is lbobj):
                    buf.append(ev)

        except StopIteration as e:
            if time_sequence is not None:
                while e.value >= nexttime:
                    yield from flush(nexttime)
            yield from flush(e.value)
            return e.value

    def active_events_at(score, time,
                         event_type=Event, cache=True) -> List['Event']:
        """ Returns a list of events that are active (or effective) at `time`.
        Active events are specifically the following events.

        * NoteEvent or NoteOnEvent for the note sounding at `time`,
          not including a note that has just ended at `time`. NoteEvent or
          NoteOnEvent events for notes that start sounding at `time` are
          included, unless they have zero duration (NoteEvent with the L
          attribute of 0, or NoteOnEvent with a note-off at the same time).
        * KeySignatureEvent representing the key at `time`, including those
          present at exactly `time`.
        * TimeSignatureEvent representing the time signature at `time`,
          including those that exist at exactly `time`.
        * TempoEvent representing the tempo at `time`, including those
          that exist at exactly `time`.
        * The last CtrlEvent before `time` for each controller number,
          each track number, and each MIDI channel number, except
          the mode changes (controller numbers 124-127). For RPCs,
          CtrlEvent's needed to set each parameter value are included.
        * The last KeyPressureEvent before `time` for each track number,
          each MIDI channel number, and each MIDI note number.

        The active events are computed based on notated time (i.e., without
        regard to the dt and du attributes).
        If you want to use the played time as a reference, apply the
        :class:`.Render` effector before calling.

        Args:
            time(ticks): Time of interest
            event_type(class, int, or tuple of class or int):
                If a class is specified, the type of events examined is
                limited to events of that class or its subclasses (in this
                argument, NoteEvent, NoteOnEvent, and NoteOffEvent all have
                the same meaning as NoteEventClass).
                If an integer is specified, events are limited to CtrlEvent's
                of that controller number.
                In the case of a tuple of classes and/or integers, events
                corresponding to any of them are targetted.
                Note that when specifying RPC-related controller numbers
                (6,38,98-101), all of these must be specified at the same time.
            cache(bool):
                If True (default), caching is enabled to speed up multiple
                queries against the same score. However, if the score is
                rewritten after using this method, it will not return correct
                results thereafter, so use False in such a case.

        Returns:
            list of Event: List of active events, which are references to
            events in the score.
            The events are ordered by time. For events present at the same
            time, they are ordered by their appearance in the socre.

        Notes:
            Without caching, the computational complexity of M queries for
            a score with N events is O(NM). With caching, it is reduced to
            O(N+MlogN) for ordinary scores, although the worst-case complexity
            remains O(MN).
        """
        """ 時刻 `time` においてアクティブな（効いている）イベントのリストを
        返します。アクティブなイベントとは具体的には次のようなイベントを
        意味します。

        * `time` において発音中の音に対する NoteEvent または NoteOnEvent。
          `time` でちょうど発音が終わるものは含みません。一方、`time` から
          発音を開始するものは、zero-durationである場合 (L属性が0である
          NoteEvent、もしくはノートオフが同時刻にある NoteOnEvent) を除いて、
          含まれます。
        * `time` における調を表す KeySignatureEvent。ちょうど `time` に存在
          するものを含みます。
        * `time` における拍子を表す TimeSignatureEvent。ちょうど `time` に存在
          するものを含みます。
        * `time` におけるテンポを表す TempoEvent。ちょうど `time` に存在
          するものを含みます。
        * 各コントローラ番号、各トラック番号、各MIDIチャネル番号において、
          `time` 以前に存在する最後の CtrlEvent。モードチェンジ（コントローラ
          番号124〜127) は対象外です。RPCはパラメータ番号ごとにその値の設定に
          必要なCtrlEventが含められます。
        * 各トラック番号、各MIDIチャネル番号、各MIDIノート番号において、
          `time` 以前に存在する最後の KeyPressureEvent。

        アクティブなイベントは、楽譜上の時刻を基準にして（つまり、dt属性や
        du属性は考慮されずに）求められます。
        演奏上の時刻を基準にしたい場合には、予め :class:`.Render` エフェクタを
        適用した上で呼んで下さい。

        Args:
            time(ticks): 対象となる時刻
            event_type(class, int, or tuple of class or int): クラスを指定
                すると、調べるイベントの種類を、そのクラスまたはそのサブクラス
                のイベントに限定します (なお、NoteEvent, NoteOnEvent,
                NoteOffEventはどれも NoteEventClassと同じ意味になります)。
                整数を指定すると、そのコントローラ番号のCtrlEventに限定します。
                クラスおよび整数のタプルの場合は、そのいずれかに該当する
                イベントを対象とします。
                なお、RPC関連のコントローラ番号(6,38,98-101)を指定する場合には
                これらをすべて同時に指定してください。
            cache(bool): True (デフォルト) の場合、キャシュを使用して同じ
                スコアに対する複数の問い合わせを高速化します。ただし、
                このメソッドを使用した後にスコアが書き換えられた場合は、それ
                以降正しい結果を返さなくなりますので、このような場合はFalseに
                して使用してください。

        Returns:
            list of Event: アクティブなイベント(スコア中のイベントへの参照)の
            リスト。イベントの順序は時刻順 (同時刻の場合は出現順）になります。

        Notes:
            キャシュを使用しない場合、イベント数Nのスコアに対するM個の問い合わ
            せの計算量は O(NM) になります。キャシュを使用した場合、最悪の
            計算量は O(MN) のままですが、通常のスコアに対しては O(N+MlogN) に
            削減されます。
        """
        if cache:
            if not hasattr(score, '_cached_event_finder') or \
               not score._cached_event_finder.check_event_type(event_type):
                score._cached_event_finder = _EventFinder(score, event_type,
                                                          True)
            event_finder = score._cached_event_finder
        else:
            event_finder = _EventFinder(score, event_type, False)
        return event_finder.events_at(time)

    def show(self, *args, **kwargs) -> None:
        """ Call :func:`.pianoroll.show` with the given arguments to
        display a pianoroll window."""
        """ :func:`.pianoroll.show` を与えられた引数と
　　　　ともに呼び、ピアノロールウィンドウを表示します。"""
        from pytakt.pianoroll import show
        show(self, *args, **kwargs)

    def showtext(self, *args, **kwargs) -> None:
        """ :func:`.text.showtext` is called with the given arguments
        to convert this score into a descriptive text that can be evaluated
        by Python and output it. """
        """ :func:`.text.showtext` を与えられた引数と
        ともに呼び、このスコアをpythonで評価可能なテキストに変換して
        出力します。"""
        from pytakt.text import showtext
        showtext(self, *args, **kwargs)

    def summary(self, *args, **kwargs) -> None:
        """ Call :func:`.text.showsummary` with the given arguments
        to output statistics of the score. """
        """ :func:`.text.showsummary` を与えられた引数と
　　　　ともに呼び、統計情報を出力します。"""
        from pytakt.text import showsummary
        showsummary(self, *args, **kwargs)

    def play(self, *args, **kwargs) -> None:
        """ :func:`.midiio.play` is called with the given arguments
        to play this score. """
        """ :func:`.midiio.play` を与えられた引数と
　　　　ともに呼び、このスコアを演奏します。"""
        from pytakt.midiio import play
        play(self, *args, **kwargs)

    def writesmf(self, *args, **kwargs) -> None:
        """ Call :func:`.smf.writesmf` with the given arguments to
        write this score to a standard MIDI file. """
        """ :func:`.smf.writesmf` を与えられた引数と
　　　　ともに呼び、このスコアを標準MIDIファイルに書き出します。"""
        from pytakt.smf import writesmf
        writesmf(self, *args, **kwargs)

    def writepyfile(self, *args, **kwargs) -> None:
        """ Call :func:`.text.writepyfile` with the given arguments
        to convert this score to a descriptive text that can be evaluated
        by Python and output it to a file. """
        """ :func:`.text.writepyfile` を与えられた引数と
　　　　ともに呼び、このスコアをpythonで評価可能なテキストに変換して
　　　　ファイルに出力します。"""
        from pytakt.text import writepyfile
        writepyfile(self, *args, **kwargs)

    def writejson(self, *args, **kwargs) -> None:
        """ Call :func:`.text.writejson` with the given arguments
        to convert this score to JSON format and output it to a file. """
        """ :func:`.text.writejson` を与えられた引数と
        ともに呼び、このスコアをJSON形式に変換してファイルに出力します。"""
        from pytakt.text import writejson
        writejson(self, *args, **kwargs)

    def music21(self, min_note=L32, bar0len=None, *,
                allow_tuplet=True, limit=5e5) -> 'music21.stream.Score':
        """
        Converts a Pytakt Score object to a music21 Score object.
        In the conversion, each track in Pytakt, except track 0, is assigned
        a music21 part (one stave).

        The following information that the Pytakt score has is not output
        to the music21 score.

        * Played time information (dt and du attributes)
        * MIDI channel information (ch attribute)
        * Note-off velocity (nv attribute)
        * Information contained in CtrlEvent (and its subclasses)
          and SysExEvent
        * Meta events other than key signature events, time signature events,
          tempo events, copyright information events, track name events,
          instrument name events, and marker events (The generic
          text event (mtype=1) is output as a song title if it exists
          on track 0.)

        In the conversion, if NoteEvent has the following attributes,
        it has the meaning written below.

        * **voice** (int): Specifies a voice number, an integer greater
          than or equal to 1, indicating how the music21 Voice streams
          will be constructed if multiple voices are present.
          If this attribute is not specified, the voice number is
          automatically selected from the voice numbers that are not used
          at the same time.
        * **mark** (str or tuple of str): Specifies a string of symbols
          (staccato, accents, finger numbers, trills, etc.) to be added
          to each note.
          Multiple markers can be specified by tuples. A list of available
          strings can be found at the beginning of the pytakt.m21conv source
          code.

        Currently, lyrics and spanners such as slurs are not supported.

        Args:
            min_note(ticks, optional): The duration (note value) of the
                shortest possible note to be used in the converted score.
                The smaller this value, the more accurately the Pytakt score
                is represented, but it may result in a score that is difficult
                to read when converted to staff notation.
            bar0len(ticks, optional): specifies the length of the bar
                with bar number 0.
            allow_tuplet(bool, optional): By default, up to tredecuplets
                (13-tuplets) are automatically recognized, but setting this
                argument to False disables the use of tuplets altogether.
            limit(ticks, optional): Limits the length of the score
                (see :meth:`.Score.stream` for details).
        """
        """
        Pytakt の Score オブジェクトを music21 のスコアオブジェクトへ変換
        します。変換において、Pytakt におけるトラック0を除くそれぞれの
        トラックに対して、music21 のパート (五線譜の１段）が割り当てられます。

        Pytaktのスコアが持っている情報のうち下のものは music21 のスコアに
        出力されません。

        * 演奏上の時刻の情報 (dt属性およびdu属性)
        * MIDIチャネル情報 (ch属性)
        * ノートオフベロシティ (nv属性)
        * CtrlEvent（およびそのサブクラス), SysExEvent に属するイベントの情報
        * 調号イベント、拍子イベント、テンポイベント、著作権情報イベント、
          トラック名イベント、楽器名イベント、マーカーイベント以外の
          メタイベント (ただし、汎用テキストイベント(mtype=1)はトラック0に存在
          するときのみ曲タイトル情報として出力されます。)

        変換において、NoteEventが次の属性を持っている場合はその右に書かれている
        意味を持ちます。

        * **voice** (int): ボイス(声部)番号を指定します。1以上の整数で、複数の
          声部が存在する場合にこの番号に従ってmusic21のVoiceストリーム群を
          構築します。この属性がない場合は、同時刻において指定に使われていない
          ボイス番号の中から自動で選ばれます。
        * **mark** (str or tuple of str): 音符ごとに付加される記号（
          スタッカート、アクセント、指番号、トリルなど）を文字列で指定します。
          タプルによって複数指定することも可能です。使用できる文字列の一覧
          は pytakt.m21conv のソースコードの冒頭で確認できます。

        現在のところ、スラーなどの Spanner や歌詞には対応していません。

        Args:
            min_note(ticks, optional): 変換後のスコアで使用される可能性のある
                最も短い音符の音価。この値が小さいほど、Pytakt のスコアを
                より正確に表現できるようになりますが、五線譜にしたときに
                見づらい楽譜になることがあります。
            bar0len(ticks, optional): 小節番号 0 の小節の長さを指定します。
            allow_tuplet(bool, optional): デフォルトでは13連符までの連符を
                自動認識しますが、この引数を False にすると連符を一切使用
                しなくなります。
            limit(ticks, optional): スコアの長さを制限します
                (詳細については、:meth:`.Score.stream` を参照)。
        """
        from pytakt.m21conv import TaktToMusic21
        return TaktToMusic21().convert_to_music21(self, min_note, bar0len,
                                                  allow_tuplet, limit)

    def pretty_midi(self, render=True,
                    limit=DEFAULT_LIMIT) -> 'pretty_midi.PrettyMIDI':
        """
        Converts a Pytakt Score object to pretty_midi's PrettyMIDI object.
        Information on notes, pitch-bends, control-changes, tempo, time
        signatures, key signatures, program numbers (via program change),
        track names, lyrics, and text events is output.
        In the pretty_midi object, a new Instrument is allocated if any of
        the track number, MIDI channel number, or program number is different.
        On the other hand, information of track numbers and channel numbers
        themselves will be lost.

        Args:
            render(bool, optional):
                If True (default), the played time is used.
                Otherwise, the notated time is used.
            limit(ticks, optional): Limits the length of the score
                (see :meth:`.Score.stream` for details).
        """
        """
        Pytakt の Score オブジェクトを pretty_midi のPrettyMIDIオブジェクトへ
        変換します。音符、ピッチベンド、コントロールチェンジ、テンポ、拍子、
        調号、(プログラムチェンジによる)プログラム番号、トラック名、歌詞、及び
        テキストイベントの情報が出力されます。
        pretty_midi オブジェクトにおいて、トラック番号、MIDIチャネル番号、プロ
        グラム番号のどれかが異なれば、新しい Instrument が割り当てられます。
        一方、トラック番号、MIDIチャネル番号そのものの情報は失われます。

        Args:
            render(bool, optional):
                デフォルト(True)の場合、演奏上の時間を使用します。
                Falseの場合は、楽譜上の時間を使用します。
            limit(ticks, optional): スコアの長さを制限します
                (詳細については、:meth:`.Score.stream` を参照)。
        """
        from pytakt.pmconv import TaktToPrettyMIDI
        return TaktToPrettyMIDI().convert_to_pretty_midi(self, render, limit)

    @staticmethod
    def from_music21(m21score) -> 'Tracks':
        """
        Converts a music21 score object (an object of
        the music21.stream.Stream class) to a Pytakt Score object.
        In the conversion, a Pytakt track is assigned to each part of music21,
        and the MIDI channel number is always 1.
        If the music21 score uses the Voice structure, the 'voice' attribute
        will be set to each NoteEvent.

        Currently, lyrics and spanners such as slurs are not supported.
        """
        """
        music21 のスコアオブジェクト (music21.stream.Streamクラスの
        オブジェクト）を Pytakt の Score オブジェクトへ変換します。
        変換において、music21 の各パートに対して Pytakt のトラックが割り当て
        られます。MIDIチャネル番号は常に1になります。
        music21 のスコアにおいて Voice構造が使われていれば、各NoteEventに
        voice属性が設定されます。

        現在のところ、スラーなどの Spanner や歌詞には対応していません。
        """
        from pytakt.m21conv import Music21ToTakt
        return Music21ToTakt().convert_to_takt(m21score)

    @staticmethod
    def from_pretty_midi(pmscore) -> 'Tracks':
        """
        Converts a pretty_midi score object (an object of the
        pretty_midi.PrettyMIDI class) to a Pytakt Score object.
        Each instrument in pretty_midi is allocated from Track 1 sequentially.
        MIDI channels 1-16 except 10 are cyclically assigned to each track.
        MIDI channel 10 is assigned to instruments flagged as drums.
        """
        """
        pretty_midi のスコアオブジェクト (pretty_midi.PrettyMIDI クラスの
        オブジェクト）を Pytakt の Score オブジェクトへ変換します。
        pretty_midi における各 Instrument が、1番以降のトラックに順に割り当て
        られます。MIDIチャネルは 10を除く 1〜16 が、各トラックに巡回的に
        割り当てられます。MIDIチャネル10はドラムのフラグのついた Instrument へ
        割り当てられます。
        """
        from pytakt.pmconv import PrettyMIDIToTakt
        return PrettyMIDIToTakt().convert_to_takt(pmscore)

    def dump(self) -> None:
        for ev in self.stream():
            print(ev)

    # jedi で auto-completion を可能にするためエフェクタを変数として仮登録
    EventEffector: Callable[..., 'Score'] = None
    CompositeEffector: Callable[..., 'Score'] = None
    Transpose: Callable[..., 'Score'] = None
    Invert: Callable[..., 'Score'] = None
    ApplyScale: Callable[..., 'Score'] = None
    ConvertScale: Callable[..., 'Score'] = None
    ScaleVelocity: Callable[..., 'Score'] = None
    Repeat: Callable[..., 'Score'] = None
    TimeStretch: Callable[..., 'Score'] = None
    Retrograde: Callable[..., 'Score'] = None
    Quantize: Callable[..., 'Score'] = None
    TimeDeform: Callable[..., 'Score'] = None
    Swing: Callable[..., 'Score'] = None
    ToMilliseconds: Callable[..., 'Score'] = None
    Randomize: Callable[..., 'Score'] = None
    Clip: Callable[..., 'Score'] = None
    Arpeggio: Callable[..., 'Score'] = None
    Filter: Callable[..., 'Score'] = None
    Reject: Callable[..., 'Score'] = None
    Cond: Callable[..., 'Score'] = None
    Modify: Callable[..., 'Score'] = None
    Product: Callable[..., 'Score'] = None
    Apply: Callable[..., 'Score'] = None
    ToTracks: Callable[..., 'Score'] = None
    Render: Callable[..., 'Score'] = None
    Tie: Callable[..., 'Score'] = None
    EndTie: Callable[..., 'Score'] = None
    ConnectTies: Callable[..., 'Score'] = None
    Dump: Callable[..., 'Score'] = None
    Voice: Callable[..., 'Score'] = None
    Mark: Callable[..., 'Score'] = None
    PairNoteEvents: Callable[..., 'Score'] = None
    UnpairNoteEvents: Callable[..., 'Score'] = None
    RetriggerNotes: Callable[..., 'Score'] = None


class _EventFinder(object):
    __noteevent = NoteEvent(0, 60, 0)

    def __init__(self, score, event_type, cache):
        self.event_type, self.ctrlnums = self._parse_event_type(event_type)
        if isinstance(self.__noteevent, self.event_type):
            self.stream = score.tee().stream().noteoff_inserted()
        else:
            self.stream = score.tee().stream()
        self.cache = cache
        self.noteevents = []  # list of (seqno, event, back-index)
        # back-index は、直近の継続音を伴わない音符の noteeventsにおける位置
        self.notedict = NoteDict()
        self.ctrldict = {}  # key=ctrlnum etc.  value=list of (seqno, event)
        self.seqno = 0
        self.last_event_time = 0

    def _parse_event_type(self, event_type):
        if not isinstance(event_type, tuple):
            event_type = (event_type,)
        et = tuple(set((NoteEventClass if issubclass(elm, NoteEventClass)
                        else elm if issubclass(elm, object)  # error check
                        else None)  # not reached
                       for elm in event_type
                       if not isinstance(elm, int)))
        cn = set(elm for elm in event_type if isinstance(elm, int))
        return (et, cn)

    def check_event_type(self, event_type):
        return (self.event_type, self.ctrlnums) == \
            self._parse_event_type(event_type)

    def _bisect_right_ev(self, events, time):
        lo = 0
        hi = len(events)
        while lo < hi:
            mid = (lo+hi)//2
            if time < events[mid][1].t:
                hi = mid
            else:
                lo = mid+1
        return lo

    def _get_rpn(self, tk, ch):
        # 現在アクティブな RPNの情報 ((L,H,N),(seqnoL,evL),(seqnoH,evH))を
        # を返す。NはNRPCで0、RPCで1。
        # NRPC と RPC が両方存在している場合は、より後に出現した方を返す。
        rpns = [[None, None], [None, None]]
        seqno = -1
        last_n = 1
        for n in (0, 1):
            for lh in (0, 1):
                try:
                    s, ev = self.ctrldict[(C_NRPCL + n*2 + lh, tk, ch)][-1]
                    rpns[n][lh] = s, ev
                    if s > seqno:
                        seqno = s
                        last_n = n
                except KeyError:
                    pass
        evL, evH = rpns[last_n]
        return ((evL and evL[1].value, evH and evH[1].value, last_n),
                evL, evH)

    def _fill_until(self, ticks):
        try:
            while (self.last_event_time != math.inf and
                   self.last_event_time <= ticks):
                ev = next(self.stream)
                self.last_event_time = ev.t
                if not self.cache and ev.t > ticks:
                    break
                if not (isinstance(ev, self.event_type) or
                        (isinstance(ev, CtrlEvent) and
                         ev.ctrlnum in self.ctrlnums)):
                    continue
                if isinstance(ev, NoteEventClass):
                    if isinstance(ev, NoteEvent):
                        self.notedict.push(ev, (self.seqno, ev,
                                                len(self.noteevents)))
                    elif isinstance(ev, NoteOnEvent):
                        self.notedict.pushnote(ev, (self.seqno, ev,
                                                    len(self.noteevents)))
                    else:  # ev is a NoteOffEvent
                        if hasattr(ev, 'noteon'):
                            self.notedict.pop(ev.noteon)
                        else:
                            self.notedict.popnote(ev, None)
                    if self.cache:
                        try:
                            backidx = next(self.notedict.values())[2]
                        except StopIteration:
                            backidx = None
                        self.noteevents.append((self.seqno, ev, backidx))
                elif isinstance(ev, KeyPressureEvent):
                    self.ctrldict.setdefault(
                        (ev.ctrlnum, ev.tk, ev.ch, ev.n), []) \
                        .append((self.seqno, ev))
                elif (isinstance(ev, CtrlEvent) and
                      not 124 <= ev.ctrlnum <= 127):   # exclude mode change
                    if ev.ctrlnum in (C_DATA, C_DATA_L):
                        key, evL, evH = self._get_rpn(ev.tk, ev.ch)
                        self.ctrldict.setdefault(
                            (ev.ctrlnum, key, ev.tk, ev.ch), []) \
                            .append((self.seqno, ev))
                        if evL:
                            self.ctrldict.setdefault(
                                (evL[1].ctrlnum, key, ev.tk, ev.ch), []) \
                                .append(evL)
                        if evH:
                            self.ctrldict.setdefault(
                                (evH[1].ctrlnum, key, ev.tk, ev.ch), []) \
                                .append(evH)
                    else:
                        self.ctrldict.setdefault(
                            (ev.ctrlnum, ev.tk, ev.ch), []) \
                                 .append((self.seqno, ev))
                elif isinstance(ev, (TempoEvent, KeySignatureEvent,
                                     TimeSignatureEvent)):
                    self.ctrldict.setdefault(ev.mtype, []) \
                                 .append((self.seqno, ev))
                self.seqno += 1
        except StopIteration:
            self.last_event_time = math.inf

    def events_at(self, ticks):
        self._fill_until(ticks)
        results = {}  # RPCで重複が発生する可能があるため、dictにしている。

        if not self.cache:
            for seqno, ev, _ in self.notedict.values():
                results[seqno] = ev
        elif self.noteevents:
            i = self._bisect_right_ev(self.noteevents, ticks)
            if i > 0:
                bi = self.noteevents[i-1][2]
                if bi is not None:
                    ndict = NoteDict()
                    for seqno, ev, _ in self.noteevents[bi:i]:
                        if isinstance(ev, NoteEvent):
                            ndict.push(ev, (seqno, ev))
                        elif isinstance(ev, NoteOnEvent):
                            ndict.pushnote(ev, (seqno, ev))
                        elif isinstance(ev, NoteOffEvent):
                            if hasattr(ev, 'noteon'):
                                ndict.pop(ev.noteon, None)
                            else:
                                ndict.popnote(ev, None)
                    for seqno, ev in ndict.values():
                        results[seqno] = ev

        for events in self.ctrldict.values():
            i = self._bisect_right_ev(events, ticks)
            if i <= 0:
                continue
            seqno, ev = events[i-1]
            results[seqno] = ev

        return [results[seqno] for seqno in sorted(results)]


class EventList(Score, list):
    """
    EventList is a class for event lists and inherits from both the Score
    and 'list' classes.
    An event list is a list of zero or more events, with an attribute
    called duration added, which represents the length of the performance.
    The events in the list are not necessarily ordered by time.

    Attributes:
        duration (ticks): Duration in ticks. Must not be a negative value.

    .. rubric:: Arithmetic Rules

    * The bool value is False if the number of elements is 0, as in the normal
      list. Note that an empty event list with a non-zero duration will
      also be false.
    * The equivalence comparison ('==') between event lists results in True
      if and only if the classes match, the list lengths match, all list
      elements are equivalent, and all attribute values of the event list
      are equivalent.
    * If the '|' operator is used with the left operand being a string and
      the right operand being an event list, the left operand is ignored and
      the result is the value of the event list itself. This is used
      in showtext() to ignore measure numbers, etc. to the left of the '|'.

    Args:
        events (Score or iterable of Event):
            * If it is a Score (including the case of an EventList),
              the score is converted (or 'flattened') to an event list where
              the events therein are sorted by time. Each event is not copied.
              The value of the duration attribute is set to the value of
              the `duration` argument, if any, otherwise
              the duration of the source score (or the value of `limit`
              if the EventStream is terminated by the `limit` feature below).
            * If it is an Event iterable (but not an EventList or EventStream),
              the event list is created with keeping the order of events
              as it is. Each event is not copied.
              The value of the duration attribute is determined in the
              following order: (1) the value of the `duration` argument,
              if any, (2) the value owned by StopIteration
              if `events` is an iterator and has the value attribute
              in its StopIteration, or (3) 0 for an empty iterable.
              An exception is raised if none of these apply.
        duration (ticks, optional):
            Specifies the value of the duration attribute.
        limit (ticks, optional):
            If `events` is an EventStream, it limits the length of the score.
            See the `limit` argument of :meth:`Score.stream` for details.
        kwargs: Specifies additional attributes for the event list.
    """
    """
    EventListはイベントリストのクラスで、Scoreクラスとlistクラスの両方を
    継承しています。
    イベントリストとは、0個以上のイベントのリストに、durationと
    呼ばれる演奏長の情報を付加したものです。
    なお、リスト内のイベントは必ずしも時刻順に並んでいるとは限りません。

    Attributes:
        duration (ticks): 演奏長 (ティック単位)。負であってはなりません。

    .. rubric:: 演算規則

    * bool値は、通常のリストと同様、要素数が0なら False となります。
      duration属性値が0以外でも要素数が0ならFalseとなる点に注意してください。
    * イベントリストどうしの等価比較 ('==') は、クラスが一致し、リスト長が
      一致し、リスト要素のすべてが等価であり、かつイベントリストのすべての
      属性値が等価であるときのみ真となります。
    * 文字列を左オペランド、イベントリストを右オペランドにして '|' 演算子を
      用いると、左オペランドは無視され、イベントそのものの値となります。
      これは、showtext() で '|' の
      左側にある小節番号等を無視するのに利用されます。

    Args:
        events (Score or iterable of Event):
            * Score型である場合(EventListの場合を含む)、
              そのスコアが時刻順にソート済みのイベントリストへ変換されます。
              各イベントはコピーされません。
              duration属性の値は、`duration` 引数があればその値、そうでな
              ければ、スコアの演奏長（ただし、EventStream が `limit` の制限で
              打ち切られたときは `limit` の値）になります。
            * Eventのイテラブルである（しかし、EventList や EventStream
              ではない）場合、そのままの順序でイベントリストが作成されます。
              各イベントはコピーされません。
              duration属性の値は、次の順で決定されます。(1) `duration` 引数が
              あればその値、(2) `events` が StopIteration に value属性値を
              持つイテレータならその値、(3) 空のイテラブルならば 0。どれに
              も該当しなければ例外を送出します。
        duration (ticks, optional):
            duration属性の値を指定します。
        limit (ticks, optional):
            `events` が EventStream型のスコアである場合に、スコアの長さを
            制限します。詳細については、:meth:`Score.stream` の同名の
            引数の項目を見てください。
        kwargs: イベントリストに対して追加の属性を指定します。
    """
    __slots__ = ('duration', '__dict__', '_cached_event_finder')

    def __init__(self, events=[], duration=None,
                 *, limit=DEFAULT_LIMIT, **kwargs):
        self.duration = duration
        if isinstance(events, Score):
            iterator = events.stream(limit=limit)
        elif isinstance(events, collections.abc.Iterator):
            iterator = events
        else:
            list.__init__(self, events)
            iterator = None
        if iterator is not None:
            try:
                while True:
                    self.append(next(iterator))
            except StopIteration as e:
                if self.duration is None:
                    self.duration = e.value
        if self.duration is None:
            if len(self) == 0:
                self.duration = 0
            else:
                raise Exception("EventList(): duration must be specified for "
                                "non-empty iterable of events")
            # self.duration = max(((ev.t + ev.L if isinstance(ev, NoteEvent)
            #                       else ev.t) for ev in self), default=0)
        self.__dict__.update(kwargs)

    def tostr(self, timereprfunc=std_time_repr) -> str:
        attrs = ["%s=%r, " % (k, v) for k, v in self.__dict__.items()]
        return ("%s(duration=%s, %sevents=[%s])" %
                (self.__class__.__name__,
                 timereprfunc(self.duration), ''.join(attrs),
                 ','.join('\n    ' +
                          (ev.tostr(timereprfunc) if isinstance(ev, Event)
                           else repr(ev))
                          for ev in self),))

    # def __bool__(self):
    #     return bool(self.duration != 0) or len(self) != 0

    def __eq__(self, other):
        return type(self) is type(other) and \
            self.duration == other.duration and \
            self.__dict__ == other.__dict__ and \
            list.__eq__(self, other)

    def __ror__(self, other):
        # showtext で '|' の左側にある小節番号等を無視するのに利用される
        if isinstance(other, str):
            return self
        else:
            return NotImplemented

    def copy(self) -> 'EventList':
        """
        Returns a duplicated event list (shallow copy).
        """
        """
        複製されたイベントリストを返します(浅いコピー)。
        """
        # 古い pytakt では深いコピーになってしまうバグがあった。
        return self.__class__(list(self), self.duration, **self.__dict__)

    def deepcopy(self) -> 'EventList':
        """
        Returns a new event list with each event duplicated.
        """
        """
        各イベントが複製された新しいイベントリストを返します。
        """
        return self.__class__(map(lambda ev: ev.copy(), self),
                              self.duration, **self.__dict__)

    def sort(self, *, key=None) -> None:
        """
        Sorts the events (by default, in ascending order of the t attribute
        value). Uses the stable sorting algorithm same as list.sort().

        Args: key(function, optional)
            key(function, optional): has the same meaning as the 'key'
               argument of list.sort().
        """
        """
        イベントを(デフォルトではt属性の時刻順に)ソートします。
        list.sort() と同様に安定なソートアルゴリズムを使用します。

        Args:
            key(function, optional): list.sort() の key引数と同じ意味を
                持ちます。
        """
        if key is None:
            key = operator.attrgetter('t')
        list.sort(self, key=key)

    def sorted(self, *, key=None) -> 'EventList':
        """
        Returns a new list of events sorted (by default, in ascending order of
        the t attribute value).
        Uses the stable sorting algorithm same as list.sort().

        Args: key(function, optional)
            key(function, optional): has the same meaning as the 'key'
                argument of list.sort().
        """
        """
        イベントを(デフォルトではt属性の時刻順に)ソートした新しい
        イベントリストを返します。
        list.sort() と同様に安定なソートアルゴリズムを使用します。

        Args:
            key(function, optional): list.sort() の key引数と同じ意味を
                持ちます。
        """
        if key is None:
            key = operator.attrgetter('t')
        return self.__class__(sorted(self, key=key), self.duration,
                              **self.__dict__)

    def __getitem__(self, key):
        if isinstance(key, slice):
            return self.__class__(list.__getitem__(self, key), self.duration,
                                  **self.__dict__)
        else:
            return list.__getitem__(self, key)

    def add(self, ev) -> None:
        """
        Add an event `ev` to the end of the event list. In addition,
        it updates the duration attribute of the event list by the greater
        of that value and the t attribute value of `ev` (or the sum of the
        t and L attribute values in the case of a NoteEvent).

        Args: Args
            ev(Event): event to add
        """
        """
        イベントリストの末尾にイベント `ev` を追加します。更に、
        イベントリストの duration 属性値を、その値と `ev` の
        t属性値（ただし NoteEvent の場合は t属性値とL属性値の和）
        の大きい方に更新します。

        Args:
            ev(Event): 追加するイベント
        """
        self.append(ev)
        self.duration = max(self.duration,
                            ev.t + ev.L if isinstance(ev, NoteEvent) else ev.t)

    def merge(self, other, time=0) -> None:
        """
        Adds all events in the event list `other` to the end of the event
        list `self`. The resulting duration attribute value of event list
        `self` will be the greater of that value and the duration attribute
        value of `other` plus `time`.

        Caution: If `time` is non-zero, events in `other` are destroyed by
        default. To avoid this, deepcopy `other` before calling this method.

        Args:
            other(EventList): list of events to merge
            time(ticks, optional): add value of time
        """
        """
        イベントリスト `self` の末尾に、別のイベントリスト `other` に含まれる
        すべてのイベントを追加します。その際、追加するイベントの時刻には `time`
        の値が加えられます。mergeの結果、
        イベントリスト `self` の duration 属性値は、その値と、`other` の
        duration属性値に `time` を加えたものうちで、より大きい方となります。

        Caution:
            `time` が0以外の場合、デフォルトでは `other` に含まれるイベント
            が破壊されます。これを避けるには merge を呼ぶ前に `other` を
            deepcopy して下さい。

        Args:
            other(EventList): 併合するイベントリスト
            time(ticks, optional): 時刻の加算値
        """
        if not isinstance(other, EventList):
            raise TypeError("can only merge/concat event-list to event-list")
        for ev in other:
            if time != 0:
                ev.t = int_preferred(ev.t + time)
            self.append(ev)
        self.duration = max(self.duration,
                            int_preferred(other.duration + time))

    def get_duration(self) -> Ticks:
        """ Returns the value of the duration attribute. """
        """ スコアの演奏長として、duration属性の値を返します。"""
        return self.duration

    def tee(self) -> 'EventList':
        """ Returns `self` as is. """
        """ `self` をそのまま返します。"""
        return self

    def count(self) -> int:
        """ Returns the number of events in the score. """
        """ スコア中のイベント数を返します。"""
        return len(self)


class Tracks(Score, list):
    """
    Container class for representing a concurrently played structure.
    It inherits from both the Score and list classes.
    Elements are limited to EventList or other Tracks containers;
    EventStreams cannot be the elements.
    The overall duration is the maximum of the elements' duration.

    .. rubric:: Arithmetic Rules

    * The equivalence comparison ('==') between Tracks objects results in true
      if and only if the classes match, the list lengths match, all list
      elements are equivalent, and all attribute values of the Tracks
      object are equivalent.

    Args:
        elms(iterable of Score): element scores
        kwargs: additional attributes for the Tracks object.
    """
    """
    同時並行で演奏する構造を表現するためのコンテナクラスです。
    Scoreクラスとlistクラスの両方を継承しています。
    構成要素は EventList または他の Tracksコンテナに限られ、
    EventStream は要素にできません。
    全体の演奏長は、要素の演奏長の最大値になります。

    .. rubric:: 演算規則

    * Tracksオブジェクトどうしの等価比較 ('==') は、クラスが一致し、リスト長が
      一致し、リスト要素のすべてが等価であり、かつTracksオブジェクトのすべての
      属性値が等価であるときのみ真となります。

    Args:
        elms(iterable of Score): 要素となるスコア群
        kwargs: Tracksオブジェクトに対して追加の属性を指定します。
    """
    __slots__ = ('__dict__', '_cached_event_finder')

    def __init__(self, elms=[], **kwargs):
        list.__init__(self, elms)
        self.__dict__.update(kwargs)
        for elm in self:
            if not isinstance(elm, (EventList, Tracks)):
                raise Exception("%r: each element must be EventList or Tracks"
                                % self.__class__.__name__)

    def tostr(self, timereprfunc=std_time_repr) -> str:
        def add_indent(s):
            return '    ' + s.replace('\n', '\n    ')
        attrs = [", %s=%r" % (k, v) for k, v in self.__dict__.items()]
        bodylist = [add_indent(elm.tostr(timereprfunc)
                               if isinstance(elm, Score) else repr(elm))
                    for elm in self]
        return "%s([%s%s%s]%s)" % (self.__class__.__name__,
                                   '\n' if self else '',
                                   ',\n'.join(bodylist),
                                   '\n' if self else '',
                                   ''.join(attrs))

    def __eq__(self, other):
        return type(self) is type(other) and \
            self.__dict__ == other.__dict__ and \
            list.__eq__(self, other)

    def copy(self) -> 'Tracks':
        """
        Returns a duplicated object (shallow copy).
        """
        """
        複製されたオブジェクトを返します(浅いコピー)。
        """
        return self.__class__(self, **self.__dict__)

    def __getitem__(self, key):
        if isinstance(key, slice):
            return self.__class__(list.__getitem__(self, key), **self.__dict__)
        else:
            return list.__getitem__(self, key)

    def get_duration(self) -> Ticks:
        """ Returns the maximum of the elements' duration as the duration of
            the score.
        """
        """ スコアの演奏長として、構成要素の演奏長の最大値を返します。
        """
        return max((s.get_duration() for s in self), default=0)

    def tee(self) -> 'Tracks':
        """ Returns `self` as is. """
        """ `self` をそのまま返します。"""
        return self

    def count(self) -> int:
        """ Returns the number of events in the score. """
        """ スコア中のイベント数を返します。"""
        return sum(s.count() for s in self)

    def sort(self, *, key=None) -> None:
        """
        Applies the sort() method to all the elements.

        Args:
            key(function, optional): has the same meaning as the 'key'
                argument of list.sort().
        """
        """
        すべての構成要素に対して sortメソッドを適用します。

        Args:
            key(function, optional): list.sort() の key引数と同じ意味を
                持ちます。
        """
        for elm in self:
            elm.sort(key=key)


class EventStream(Score):
    """
    Class for generators (generator iterators) that yield events in
    chronological order.
    This makes it possible to construct scores of infinite length.

    Args:
        iterator(iterator of Event): The iterator from which a sequence of
            events are generated.
            The order of events generated must be in ascending order
            of time (the t attribute values).
            In addition, the StopIteration object raised at the end of the
            event sequence must have the 'value' attribute with the score
            duration as its value.
            This duration may be less than the time of the last event.
        kwargs: Additional attributes for the EventStream object.
    """
    """
    イベントを時刻順に yield するジェネレータ（ジェネレータイテレータ）の
    クラスです。
    これによって無限長のスコアを構築することが可能となります。

    Args:
        iterator(iterator of Event): イベント列を出力する元となるイテレータ。
            イベントの出力順序は、時刻 (t属性) の昇順でなければなりません。
            また、イベント列が有限の場合にイベント列の終わり送出される
            StopIterationオブジェクトは、演奏長を値とした value属性を持つ
            必要があります。
            この演奏長は最後のイベントの時刻より小さくても構いません。
        kwargs: EventStream オブジェクトに対して追加の属性を指定します。
    """

    # EventStream(score) で、イベントのコピーはしない。
    __slots__ = ('iterator', '__dict__',
                 '_cached_event_finder', '_is_consumed')

    def __init__(self, iterator, **kwargs):
        if isinstance(iterator, collections.abc.Iterator):
            self.iterator = iterator
        else:
            raise TypeError("argument must be an iterator object")
        self.__dict__.update(kwargs)
        self._is_consumed = False

    def __iter__(self):
        return self

    def __next__(self):
        self._is_consumed = True
        return next(self.iterator)

    def is_consumed(self):
        """ Returns True if next() has been executed on this stream in the
        past, or False otherwise. """
        """ このストリームに対して過去にnextを実行したことがあればTrue、
        そうでなければFalseを返します。"""
        return self._is_consumed

    def tostr(self, timereprfunc=std_time_repr) -> str:
        attrs = [", %s=%r" % (k, v) for k, v in self.__dict__.items()]
        return "%s(%r%s)" % (self.__class__.__name__,
                             self.iterator, ''.join(attrs))

    def get_duration(self) -> Ticks:
        """ Raises an exception. """
        """ 例外を送出します。"""
        raise Exception("Cannot use get_duration() for EventStream")

    def count(self) -> int:
        """ Raises an exception. """
        """ 例外を送出します。"""
        raise Exception("Cannot use count() for EventStream")

    def tee(self) -> 'EventStream':
        """ Returns a new equivalent generator that can be read independently
        without changing the read state of the original generator.
        """
        """ 元のジェネレータの読み取り状態を変えることなく独立に読み出しできる
        ような、新たな等価ジェネレータを返します。
        """
        # itertools.tee は StopIteration の value を無視するようだ
        def save_duration(s):
            try:
                while True:
                    yield next(s)
            except StopIteration as e:
                self._duration = e.value

        def restore_duration(s):
            yield from s
            return self._duration

        (i1, i2) = itertools.tee(save_duration(self.iterator))
        self.iterator = restore_duration(i1)
        rtn = self.__class__(restore_duration(i2), **self.__dict__)
        rtn._is_consumed = self._is_consumed
        return rtn

    def merged(self, other, time=0) -> 'EventStream':
        """
        Returns a new EventStream that merges the two event streams `self`
        and `other`.

        The duration of the returned EventStream will be the greater of
        `self`'s duration or `other`'s duration plus `time`.

        Args:
            other(EventStream):
                Event stream to be merged.
            time(ticks, optional):
                This value is added to the time of the events output
                by `other`.
                At that time, the original events are rewritten without
                copying the events.
        """
        """
        `self` と `other` の2つのイベント列を併合した新たな EventStream を
        返します。

        返される EventStream の演奏長は、`self` の演奏長と、`other` の
        演奏長に `time` を加えたものうちで、より大きい方となります。

        Args:
            other(EventStream):
                併合するイベント列。
            time(ticks, optional): 時刻の加算値。
                `other` が出力するイベントの時刻にはこの値が加えられます。
                この際、イベントのコピーは行われずに元のイベントが書き換え
                られます。
        """
        duration = 0

        def next_event(s, tm):
            nonlocal duration
            try:
                return next(s)
            except StopIteration as e:
                duration = max(duration, e.value + tm)
                return None

        def shift_time(ev, tm):
            if tm != 0:
                ev.t = int_preferred(ev.t + tm)
            return ev

        def _merged(self, other, time):
            ev1 = next_event(self, 0)
            ev2 = next_event(other, time)
            while ev1 or ev2:
                if ev2 is None or (ev1 and ev1.t <= ev2.t + time):
                    yield ev1
                    ev1 = next_event(self, 0)
                else:
                    yield shift_time(ev2, time)
                    ev2 = next_event(other, time)
            return duration

        def _merged_RT(self, other, time1, time2):
            lbobj = ['_merged']
            lbev = LoopBackEvent(0, lbobj)
            # ↑ イベントはコピーされる可能性があるので、直接lbevを同一性の
            # 判定に使うことはできない。

            ev1 = next_event(self, time1)
            if ev1 is not None:
                other.queue_event(lbev, ev1.t + time1 - time2)
            while True:
                ev2 = next_event(other, time2)
                if ev2 is None:
                    break
                elif isinstance(ev2, LoopBackEvent) and ev2.value is lbobj:
                    yield shift_time(ev1, time1)
                    ev1 = next_event(self, time1)
                    if ev1 is not None:
                        other.queue_event(lbev, ev1.t + time1 - time2)
                else:
                    yield shift_time(ev2, time2)

            while ev1:
                yield shift_time(ev1, time1)
                ev1 = next_event(self, time1)

            return duration

        if isinstance(other, RealTimeStream):
            if isinstance(self, RealTimeStream):
                raise Exception('Cannot merge two real-time event streams')
            return RealTimeStream(_merged_RT(self, other, 0, time),
                                  other.starttime)
        elif isinstance(self, RealTimeStream):
            return RealTimeStream(_merged_RT(other, self, time, 0),
                                  self.starttime)
        else:
            return EventStream(_merged(self, other, time))

    def noteoff_inserted(self) -> 'EventStream':
        """
        Returns a new EventStream with a NoteOffEvent inserted for each
        NoteEvent in the event stream.
        The t attribute value of the added NoteOffEvent is set to the sum
        of the NoteEvent's t and L attribute values and inserted at the
        appropriate position in the stream.
        The attribute 'noteon' is added to that NoteOffEvent, whose value
        is the original NoteEvent. This method is mainly used for the return
        value of :meth:`.stream` and is useful when some processing needs to
        be done at the time of note-off.
        """
        """
        イベント列中の各 NoteEvent に対して NoteOffEvent を追加した新たな
        EventStream を返します。
        追加される NoteOffEvent の t属性値は NoteEvent の t属性とL属性の
        値の和に設定され、ストリーム中の適切な位置に挿入されます。
        この NoteOffEvent には 'noteon' という属性が追加されており、その値は
        元となった NoteEvent です。主に、:meth:`.stream` の戻り値に
        対して使用し、ノートオフのタイミングで何らかの処理を行う必要がある
        場合に便利です。
        """
        def _noteoff_inserted(self):
            noteoffq = []
            seqno = itertools.count()
            try:
                while True:
                    ev = next(self)
                    while noteoffq and noteoffq[0][0] <= ev.t:
                        yield noteoffq[0][2]
                        heapq.heappop(noteoffq)
                    if isinstance(ev, NoteEvent):
                        noteoff = NoteOffEvent(ev.t + ev.L, ev.n, ev.nv, ev.tk,
                                               ev.ch, noteon=ev, **ev.__dict__)
                        heapq.heappush(noteoffq,
                                       (noteoff.t, next(seqno), noteoff))
                    yield ev
            except StopIteration as e:
                while noteoffq:
                    yield noteoffq[0][2]
                    heapq.heappop(noteoffq)
                return e.value

        return self.__class__(_noteoff_inserted(self), **self.__dict__)

    def _sorted(self, use_ptime=False,
                disorder_limit=MAX_DELTA_TIME*2) -> 'EventStream':
        def _generator(self):
            delaybuf = []
            seqno = itertools.count()
            try:
                while True:
                    ev = next(self)
                    t = ev.ptime() if use_ptime else ev.t
                    while delaybuf and delaybuf[0][0] < t - disorder_limit:
                        yield delaybuf[0][2]
                        heapq.heappop(delaybuf)
                    heapq.heappush(delaybuf, (t, next(seqno), ev))
            except StopIteration as e:
                while delaybuf:
                    yield delaybuf[0][2]
                    heapq.heappop(delaybuf)
                return e.value

        return self.__class__(_generator(self), **self.__dict__)


class RealTimeStream(EventStream):
    """
    A subclass of EventStream that represents an event stream
    from an input device.
    """
    """
    入力デバイスからのイベントストリームを表す、EventStream のサブクラスです。
    """
    def __init__(self, iterator, starttime, **kwargs):
        self.starttime = starttime
        super().__init__(iterator, **kwargs)

    def queue_event(self, ev, time=None, devnum=None):
        from pytakt.midiio import queue_event as _queue_event
        _queue_event(ev, (ev.t if time is None else time) + self.starttime,
                     devnum)

    def _sorted(self, use_ptime=True,
                disorder_limit=MAX_DELTA_TIME) -> 'EventStream':
        return self


def seq(elms=[], **kwargs) -> 'EventList':
    """
    Returns an EventList that is a sequential concatenation of all scores
    given in ``elms``.
    For example, ``seq([note(C4), note(D4), note(E4)])`` is equivalent to
    ``EvenList() + note(C4) + note(D4) + note(E4)``.
    It cannot be used for infinite-length scores.

    Args:
        elms(iterable of Score): scores to concatenate
        kwargs: additional attributes for the resulting EventList.

    Examples:
        ``seq(note(i) for i in range(C4, C5)).show()``
    """
    """
    `elms` に指定されたスコアの列をすべて逐次結合した EventList を返します。
    例えば、``seq([note(C4), note(D4), note(E4)])`` は、
    ``EvenList() + note(C4) + note(D4) + note(E4)`` と等価です。
    無限長スコアに対しては使用できません。

    Args:
        elms(iterable of Score): 結合するスコアの列
        kwargs: 結果の EventList に対して追加の属性を指定します。

    Examples:
        ``seq(note(i) for i in range(C4, C5)).show()``
    """
    s = EventList([], **kwargs)
    for elm in elms:
        s += elm
    return s


def par(elms=[], **kwargs) -> 'EventList':
    """
    Returns an EventList that merges all the scores given in ``elms``.
    For example, ``par([note(C4), note(D4), note(E4)])`` is equivalent to
    ``note(C4) & note(D4) & note(E4)``.

    Args:
        elms(iterable of Score): scores to merge
        kwargs: additional attributes for the resulting EventList.

    Examples:
        ``par(note(i) for i in range(C4, C5, 2)).show()``
    """
    """
    `elms` に指定されたスコアの列をすべて併合した EventList を返します。
    例えば、``par([note(C4), note(D4), note(E4)])`` は、
    ``note(C4) & note(D4) & note(E4)`` と等価です。

    Args:
        elms(iterable of Score): 併合するスコアの列
        kwargs: 結果の EventList に対して追加の属性を指定します。

    Examples:
        ``par(note(i) for i in range(C4, C5, 2)).show()``
    """
    s = EventList([], **kwargs)
    for elm in elms:
        s &= elm
    return s


def genseq(elms=[], **kwargs) -> 'EventStream':
    """
    Returns an EventStream that is a sequential concatenation of all the
    scores given in `elms`.
    `elms` can be a generator that generates an infinite number of scores.

    Args:
        elms(iterable of Score): Sequence of scores to be combined.
             Each score must be an EventList or Tracks.
        kwargs: Additional attributes for the resulting EventStream.

    Examples:
        >>> from itertools import count
        >>> genseq(note(C4) for i in count()).play()
        >>> genseq(note(C4 + (i % 4)) for i in count()).play()
        >>> from random import randrange
        >>> genseq(note(randrange(C4, C5)) for i in count()).play()

    """
    """
    `elms` に指定されたスコアの列をすべて逐次結合した EventStream を返します。
    `elms` は無限にスコアを生成するジェネレータであっても構いません。

    Args:
        elms(iterable of Score): 結合するスコアの列。
             各スコアは EventList または Tracks でなくてはなりません。
        kwargs: 結果の EventStream に対して追加の属性を指定します。

    Examples:
        >>> from itertools import count
        >>> genseq(note(C4) for i in count()).play()
        >>> genseq(note(C4 + (i % 4)) for i in count()).play()
        >>> from random import randrange
        >>> genseq(note(randrange(C4, C5)) for i in count()).play()

    """
    # iterator の要素として EventStream は認めていない。（これを認めて
    # ると、StopIterationが持つdurationが時間逆戻りをしたときに、出力の
    # イベント列が時間順でなくなってしまう。また、同じ EventStream を
    # 複数回参照する場合には、tee()する必要性が発生する。）

    iterator = iter(elms)
    _context = context()  # contextを保存しておきnextの際にそれに切り替える。

    def _generator():
        duration = 0
        buf = []  # list of [top_event, time_offset, eventstream]
        done = False

        def fill_top(k):
            try:
                ev = next(buf[k][2])
                buf[k][0] = ev.update(t=ev.t+buf[k][1])
            except StopIteration as e:
                del buf[k]

        while True:
            try:
                with _context:
                    elm = next(iterator)
                if not isinstance(elm, Score):
                    raise Exception("%r is not a valid score element" %
                                    elm.__class__.__name__)
                elif isinstance(elm, EventStream):
                    raise Exception("genseq: EventStream cannot be followed "
                                    "by other score elements")
                buf.append([None, duration, elm.stream(copy=True)])
                fill_top(-1)
                duration += elm.get_duration()
                nexttime = duration
            except StopIteration:
                nexttime = math.inf
                done = True

            if done and not buf:
                break

            while True:
                argmin = None
                tmin = None
                # Note that buf[i][0].t and nexttime are possibly math.inf
                for i in range(len(buf)):
                    if argmin is None or buf[i][0].t < tmin:
                        tmin = buf[i][0].t
                        argmin = i
                if argmin is None or tmin > nexttime:
                    break
                else:
                    yield buf[argmin][0]
                    fill_top(argmin)
        return duration

    return EventStream(_generator(), **kwargs)


def empty() -> 'EventList':
    """ Returns an empty EventList as an empty score. """
    """ 空のスコアとして、空のEventListを返します。"""
    return EventList()
