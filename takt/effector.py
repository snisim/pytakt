# coding:utf-8
"""
このモジュールには、エフェクタ関連のクラスが定義されています。
"""
# Copyright (C) 2023  Satoshi Nishimura

import math
import itertools
import numbers
import os
import warnings
import heapq
import random
from collections import deque
from abc import ABC, abstractmethod
from typing import Optional
from takt.event import Event, NoteEvent, NoteOnEvent, NoteOffEvent, \
    NoteEventClass, CtrlEvent, KeyPressureEvent, MetaEvent, \
    KeySignatureEvent, LoopBackEvent, TempoEvent
from takt.pitch import Interval, C4, Key
from takt.utils import int_preferred, TaktWarning, NoteDict
from takt.context import context, newcontext
from takt.score import Score, EventList, EventStream, Tracks, \
    DEFAULT_LIMIT, genseq, RealTimeStream
from takt.mml import mml
from takt.interpolator import Interpolator
from takt.ps import note
from takt.constants import L32, L1, MAX_DELTA_TIME, EPSILON, LOG_EPSILON, \
    BEGIN, END
from takt.timemap import TimeSignatureMap, TempoMap
import takt.frameutils

__all__ = []  # extended later


def _check_dt(ev):
    if abs(ev.get_dt()) > MAX_DELTA_TIME:
        warnings.warn("`dt' has too large absolute value",
                      TaktWarning, stacklevel=2)


class Effector(ABC):
    """ Effectorクラスは、すべてのエフェクタの基底となる抽象クラスです。

    エフェクタとは、スコア変換を行う呼び出し可能オブジェクト
    (callable object) で、下の例のようにエフェクタオブジェクトに対して
    スコアを引数として呼び出すと、変換されたスコアを返します。

        >>> eff = Transpose(2)
        >>> eff(note(C4))
        EventList(duration=480, events=[
            NoteEvent(t=0, n=D4, L=480, v=80, nv=None, tk=1, ch=1)])

    エフェクタによるスコア変換には次の性質があります。

    * 元のスコアは破壊されずにそのまま残ります（ただし、EventStream の場合、
      変換時に要素が読み出されることがあります）。
    * 修正の必要のないイベントは、原則として元のスコアのものがそのまま出力
      されます。そのようなイベントは元のスコアと変換後のスコアとで共有される
      ことになります。
    * 変換後の各イベントリストにおけるイベントは時間順にソートされているとは
      限りません。

    特に断りのない限り、EventStream (無限長の場合を含む) に対しても適用でき
    ます。また、特に断りのない限り、分離したノートイベント (NoteOnEvent,
    NoteOffEvent) を含んだスコアに対しても適用できます。

    各エフェクタクラスのコンストラクタは、Scoreクラスのメソッドとしても利用
    できます。
    その場合はエフェクタインスタンスの生成とスコア変換が連続して行われます
    (例: ``note(C4).Transpose(2)``)。

    """

    @abstractmethod
    def __call__(self, score) -> 'Score':
        pass

    def __init_subclass__(cls):
        # Scoreのメソッドとしても利用できるようにする。
        if '__SPHINX_AUTODOC__' not in os.environ:
            if not hasattr(Score, cls.__name__) and cls.__name__[0] != '_':
                print("Internal error: %s is not registerred in Score"
                      % cls.__name__)
            setattr(Score, cls.__name__,
                    lambda score, *args, **kwargs: cls(*args, **kwargs)(score))

    def __or__(self, other):
        if isinstance(other, Effector):
            return CompositeEffector(self, other)
        else:
            return NotImplemented

    def __ror__(self, other):
        if isinstance(other, Effector):
            return CompositeEffector(other, self)
        elif isinstance(other, Score):
            return self(other)
        else:
            return NotImplemented


class EventEffector(Effector):
    """ EventEffector クラスは、各イベントに対して独立に変換を行うエフェクタの
    抽象クラスです。

    このクラスのエフェクタは、スコアだけでなく、単独のイベントに対しても変換
    を適用することができます。

        >>> eff = Transpose(2)
        >>> eff(NoteOnEvent(0, C4))
        NoteOnEvent(t=0, n=D4, v=80, tk=1, ch=1)
    """
    @abstractmethod
    def _process_event(self, ev) -> 'Event':
        # イベントを書き換えるときは、コピーする必要がある。
        return ev

    def __call__(self, score_or_event) -> 'Score':
        if isinstance(score_or_event, Event):
            return self._process_event(score_or_event)
        else:
            return score_or_event.mapev(self._process_event)


class CompositeEffector(Effector):
    """ 2つのエフェクタを合成したエフェクタのクラスです。
    このエフェクタを適用すると、まず第1のエフェクタが適用された後に
    第2のエフェクタが適用されます。

    Args:
        first(Effector): 第1のエフェクタのオブジェクト。
        second(Effector): 第2のエフェクタのオブジェクト。
    """
    def __init__(self, first, second):
        self.first = first
        self.second = second

    def __call__(self, score_or_event) -> 'Score':
        return self.second(self.first(score_or_event))


class Transpose(EventEffector):
    """ トランスポーズ操作 (ピッチを一定幅で上下させる操作) を適用します。
    n属性を持つすべてのイベントに対して適用されます。

    `scale` を指定しない場合、chromatic transposition になります。
    `value` には Interval オブジェクトもしくは半音数を表す整数を
    指定します (Interval オブジェクトの方が、異名同音を正しく処理するのに
    有利です)。

    `scale` を指定した場合、スケール上での transposition (diatonicスケールなら
    diatonic transposition) になります。`value` には、スケール上で何音上下
    するかを表す整数を指定します。元のピッチを `n` とすると、
    `scale.pitch(scale.tonenum(n) + value)` へ変換されます。

    Args:
        value(Interval, str, or int): 上下の幅。str型のときは
            `Interval(value)` と同じ意味になります。
        scale(Scale, optional): スケールの指定。
        transpose_keysig: この引数が Ture (デフォルト) で、かつスケールの指定が
            ない場合、KeySignatureEvent も移調の対象とします。それ以外の場合、
            KeySignatureEvent はそのまま出力されます。

    Examples:
        * ``mml("CDE").Transpose('M3')`` は ``mml("EF#G#")``
          と等価なスコアを生成します。``Transpose(E4-C4)`` でも同じ意味に
          なります。
        * ``mml("CDE").Transpose(DEG(3), scale=Scale(C4))`` は
          ``mml("EFG")`` と等価なスコアを生成します。
    """
    def __init__(self, value, scale=None, transpose_keysig=True):
        self.value = Interval(value) if isinstance(value, str) else value
        self.scale = scale
        self.transpose_keysig = transpose_keysig

    def _process_event(self, ev) -> 'Event':
        if hasattr(ev, 'n'):
            ev = ev.copy()
            ev.n = (ev.n + self.value) if self.scale is None \
                else self.scale[self.scale.tonenum(ev.n) + self.value]
        elif self.transpose_keysig and self.scale is None and \
             isinstance(ev, KeySignatureEvent):
            ev = ev.copy()
            ev.value = Key.from_tonic(ev.value.gettonic() + self.value,
                                      ev.value.minor)
        return ev


class Invert(EventEffector):
    """ 反行形のスコアに変換します。具体的には、中心となるピッチ `center` を
    指定し、n属性を持つ各イベントのピッチを、そのピッチと `center` との距離
    の分だけ `center` から逆方向へ動かしたピッチへ変換します。

    Args:
        center(Pitch or int): 反転の中心となるピッチ。
        scale(Scale, optional): スケールの指定。
            省略時は chromatic inversion になり、指定した場合はそのスケール
            上の inversion (diatonicスケールなら diatonic inversion) になり
            ます。

    Examples:
        * ``mml("EFG*").Invert(E4)`` は ``mml("ED#C#*")`` と等価なスコアを
          生成します。
        * ``mml("EFG*").Invert(E4, scale=Scale(C4))`` は
          ``mml("EDC*")`` と等価なスコアを生成します。
    """
    def __init__(self, center, scale=None):
        self.center = center
        self.scale = scale

    def _process_event(self, ev):
        if hasattr(ev, 'n'):
            ev = ev.copy()
            ev.n = self.center - (ev.n - self.center) if self.scale is None \
                else self.scale[self.scale.tonenum(self.center) * 2
                                - self.scale.tonenum(ev.n)]
        return ev


class ApplyScale(EventEffector):
    """
    n属性を持つ各イベントのピッチを、:meth:`.Scale.get_near_scale_tone`
    を用いて、それに近いスケール上の音のピッチに変換します。

    Args:
        scale(Scale): スケール
        round_mode(str or function):
            :func:`.takt_roundx` へ渡す丸めモード。

    Examples:
        * ``mml("C C# Db D E").ApplyScale(Scale(C4, 'minor'))`` は、
          ``mml("C C D D Eb")`` と等価なスコアを生成します。'C#' と 'Db' で
          変換結果が違うのは、:meth:`.Scale.tonenum` の `enharmonic_delta` の
          影響によるものです。
    """
    def __init__(self, scale, round_mode='nearestup'):
        self.scale = scale
        self.round_mode = round_mode

    def _process_event(self, ev):
        if hasattr(ev, 'n'):
            ev = ev.copy()
            ev.n = self.scale.get_near_scale_tone(ev.n, self.round_mode)
        return ev


class ConvertScale(EventEffector):
    """
    n属性を持つ各イベントについて、スケールの変換を行います。
    元のピッチを `n` とすると、変換後のピッチは
    `dst_scale.pitch(src_scale.tonenum(n))` になります。

    Args:
        src_scale(Scale): 元のスケール。
        dst_scale(Scale): 変換後のスケール。
            スケール構成音の数は、`src_scale` と `dst_scale` とで同じで
            なければなりません。

    Examples:
        * ``mml("C C# D E").ConvertScale(Scale(C4, 'major'), Scale(C4, \
'minor'))`` は ``mml("C C# D Eb")`` と等価なスコアを生成します。
    """
    def __init__(self, src_scale, dst_scale):
        if len(src_scale) != len(dst_scale):
            raise Exception("src_scale and dst_scale must have "
                            "the same number of scale tones")
        self.src_scale = src_scale
        self.dst_scale = dst_scale

    def _process_event(self, ev):
        if hasattr(ev, 'n'):
            ev = ev.copy()
            ev.n = self.dst_scale[self.src_scale.tonenum(ev.n)]
        return ev


class ScaleVelocity(EventEffector):
    """
    ベロシティー(v属性)の値に `value` の値を乗じます。

    Args:
        value(float, int, or list): ベロシティーの倍率。
            float または int であるときは、その値がそのまま倍率となります。
            list型であるときは、その値が :class:`.Interpolator` の
            コンストラクタへ渡され、それによって補間された値が倍率となります。

    Examples:
        * ``note(C4, v=80).ScaleVelocity(1.2)`` は ``note(C4, v=96)`` と
          等価なスコアを生成します。
        * ``mml("v=80 CDEF").ScaleVelocity([1.0, (L1, 0.5)])`` は
          ``mml("C(v=80) D(v=70) E(v=60) F(v=50)")`` と
          等価なスコアを生成します。

    """
    def __init__(self, value):
        if isinstance(value, numbers.Real):
            self.vfunc = lambda ev: ev.v * value
        elif isinstance(value, list):
            interpolator = Interpolator(value)
            self.vfunc = lambda ev: ev.v * interpolator(ev.t)
        else:
            raise Exception("Bad 'value' argument")

    def _process_event(self, ev):
        if hasattr(ev, 'v'):
            ev = ev.copy().update(v=self.vfunc(ev))
        return ev


class Repeat(Effector):
    """
    入力スコアを `rep` 回繰り返し演奏するスコアへ変換します。

    Args:
        rep(int, optional): 繰り返し回数 (デフォルトは無限回)
    """
    def __init__(self, rep=math.inf):
        self.rep = rep

    def __call__(self, score):
        if self.rep == math.inf:
            return genseq(score for i in itertools.count())
        else:
            return score * self.rep


class TimeStretch(Effector):
    """ 時間を `stretch` 倍に伸長します。

    Args:
        stretch(float or int): 伸長の倍率。正の値で、1未満なら収縮になります。

    Examples:
        ``mml("CDE*").TimeStretch(2)`` は ``mml("C*D*E**")`` と等価なスコアを
        生成します。
    """
    def __init__(self, stretch):
        self.stretch = stretch

    def _scale_time(self, time):
        return int_preferred(time * self.stretch)

    def _time_stretch(self, ev):
        ev = ev.copy()
        ev.t = self._scale_time(ev.t)
        if hasattr(ev, 'dt'):
            ev.dt = self._scale_time(ev.dt)
            _check_dt(ev)
        if hasattr(ev, 'L'):
            ev.L = self._scale_time(ev.L)
        if hasattr(ev, 'du'):
            ev.du = self._scale_time(ev.du)
        return ev

    def __call__(self, score):
        return score.mapev(self._time_stretch, durfunc=self._scale_time)


class Retrograde(Effector):
    """
    時間を逆行させたスコアへ変換します。

    NoteEvent 以外のイベントについては時間の変換を行いません。

    EventStreamに対しては適用できません。

    Examples:
        * ``mml("CDE*").Retrograde()`` は ``mml("E*DC")`` と同じ演奏になる
          ようなスコアを生成します。
    """
    def __init__(self):
        pass

    def _retrograde(self, ev):
        if isinstance(ev, NoteEvent):
            ev = ev.copy()
            ev.t = self.duration - ev.t - ev.L
            if hasattr(ev, 'tie'):
                ev.tie = ((ev.tie & BEGIN) << 1) | ((ev.tie & END) >> 1)
        return ev

    def __call__(self, score):
        self.duration = score.get_duration()
        return score.mapev(self._retrograde)


class Quantize(Effector):
    """
    各イベントの時刻、およびスコアの演奏長に対して、クォンタイズ処理を
    適用します。

    Args:
        tstep(ticks):
            クォンタイズのステップ時間。
        strength(float, optional):
            クォンタイズの強さ (0～1)。1.0 (デフォルト) ならば、各イベントの
            時刻は `tstep` の整数倍になるように修正されます。そうでないなら、
            1.0 のときの修正量にこの値を乗じたものが実際の修正量になります。
        window(float, optional):
            クォンタイズの対象となる時間区間の幅を、`tstep` に対する倍率で
            指定します (0～1)。`tstep` の整数倍となる時刻を中心としたこの幅の
            区間の中にあるイベントだけがクォンタイズの対象になります。
            例えば、`window=0.5` の場合、`tstep * (N - 0.25)` から
            `tstep * (N + 0.25)` が対象区間となります (N=0,1,2,...)。
        keepdur(bool, optional):
            Trueならば、NoteEventのL属性の値を変更せずに、元の音価を保ちます（
            NoteOffEventに対しては効果がありません）。
            False (デフォルト) ならば、発音終了時刻もクォンタイズされるように
            L属性の値が調整されます。
        saveorg(bool, optional):
            Trueならば、クオンタイズ前の時刻が演奏上の時刻として残るように
            dtとdu属性を設定します。もともと存在していたdtとdu属性の情報は
            失われます。

    Examples:
        * ``note(C4, 450).Quantize(120)`` は ``note(C4, 480)``
          と等価なスコアを生成します。
        * ``note(C4, 450).Quantize(120, strength=0.5)`` は ``note(C4, 465)``
          と等価なスコアを生成します。
    """
    def __init__(self, tstep, strength=1.0, window=1.0,
                 keepdur=False, saveorg=False):
        self.tstep = tstep
        self.strength = strength
        self.w = tstep * window / 2
        self.keepdur = keepdur
        self.saveorg = saveorg

    def _quantized_time(self, tm):
        tx = tm % self.tstep
        if tx < self.w:
            tm -= tx * self.strength
        elif tx >= self.tstep - self.w:
            tm += (self.tstep - tx) * self.strength
        return int_preferred(tm)

    def _quantize(self, ev):
        ev = ev.copy()
        qt = self._quantized_time(ev.t)
        if self.saveorg:
            ev.dt = ev.t - qt
            _check_dt(ev)
            if isinstance(ev, NoteEvent):
                ev.du = ev.L
        if not self.keepdur and isinstance(ev, NoteEvent):
            ev.L = self._quantized_time(ev.t + ev.L) - qt
        ev.t = qt
        return ev

    def __call__(self, score):
        return score.mapev(self._quantize, durfunc=self._quantized_time)


class TimeDeform(Effector):
    """
    :class:`.Interpolator` によって記述された時間変換関数に従って、
    各イベントの時刻、および演奏長を変換します。

    Args:
        points(list of Point, etc.): :class:`.Interpolator` に渡される引数。
            これによって記述される時間変換関数は、単調非減少関数でなければ
            なりません。
        periodic(bool, optional):
            Trueである場合、`points` のうちの最後の制御点の時刻を周期として、
            同じパターンの時間変換関数が繰り返されることを仮定して時間変換が
            行われます。
        perf_only(bool, optional):
            Trueである場合、楽譜上の時間 (t属性とL属性) は元のまま保たれ、
            演奏上の時間だけ変換されるように dt属性と du属性の値を調節します。
            Falseの場合は、楽譜上の時間も変換されます。

    Examples:
        * ``TimeDeform([(0, 0), (480, 482), (1920, 1950)])`` を適用した場合、
          元のスコアにおける時刻 0, 240, 480, 1920, 2000 は、それぞれ 0, 241,
          482, 1950, 1950 に変換されます。
        * ``TimeDeform([0, (240, 360), (480, 480)], periodic=True)`` を適用
          した場合、元のスコアにおける時刻 0, 240, 480, 720, 960 は、それぞれ
          0, 360, 480, 840, 960 に変換されます。この種の変換は、下の Swing
          エフェクタによってより簡潔に表現できます。
    """
    def __init__(self, points, periodic=False, perf_only=False):
        itpl = Interpolator(points)
        if not periodic:
            self.deformed_time = lambda t: int_preferred(itpl(t))
        else:
            period = itpl.maxtime()
            dest_period = itpl(period)
            self.deformed_time = \
                lambda t: int_preferred((t // period) * dest_period +
                                        itpl(t % period))
        self.perf_only = perf_only

    def _time_deform(self, ev):
        ev = ev.copy()
        time = self.deformed_time(ev.t)
        ptime = self.deformed_time(ev.t + ev.dt) if hasattr(ev, 'dt') else time
        if isinstance(ev, NoteEvent):
            offtime = self.deformed_time(ev.t + ev.L)
            pofftime = self.deformed_time(ev.t + ev.get_dt() + ev.get_du())
        if self.perf_only:
            ev.dt = ptime - ev.t
            _check_dt(ev)
            if isinstance(ev, NoteEvent):
                ev.du = pofftime - ptime
        else:
            ev.t = time
            if hasattr(ev, 'dt'):
                ev.dt = ptime - time
                _check_dt(ev)
            if isinstance(ev, NoteEvent):
                ev.L = offtime - time
                if hasattr(ev, 'du') or abs(pofftime - ptime - ev.L) > EPSILON:
                    # 元々duが無くても、時間変換の結果、必要になる場合がある。
                    ev.du = pofftime - ptime
        return ev

    def __call__(self, score):
        return score.mapev(self._time_deform, durfunc=self.deformed_time)


class Swing(TimeDeform):
    """
    周期 `period` の各時間区間において、その中央の時刻が区間開始から
    `period * rate` 経過した時刻になるように時間変換を行います。

    Args:
        period(ticks): 周期
        rate(float): スウィング効果の調節値 (0～1。0.5なら効果なし)
        perf_only(bool, optional):
            Trueである場合、楽譜上の時間 (t属性とL属性) は元のまま保たれ、
            演奏上の時間だけ変換されるように dt属性と du属性の値を調節します。
            Falseの場合は、楽譜上の時間も変換されます。

    Examples:
        ``mml("CDEF").Swing(L2, 0.75, False)`` は ``mml("C.D/E.F/")`` と等価な
        スコアを生成します。
    """
    def __init__(self, period, rate=2/3, perf_only=True):
        super().__init__([0, period * rate, (period, period)],
                         periodic=True, perf_only=perf_only)


class ToMilliseconds(TimeDeform):
    """
    スコア中のすべて時間をミリ秒へ変換した上で、テンポイベントを取り除きます。

    Examples:
        >>> mml("$tempo(120) c $tempo(240) d").ToMilliseconds()
        EventList(duration=750.0, events=[
            NoteEvent(t=0.0, n=C4, L=500.0, v=80, nv=None, tk=1, ch=1),
            NoteEvent(t=500.0, n=D4, L=250.0, v=80, nv=None, tk=1, ch=1)]
    """

    def __init__(self):
        super().__init__([0])

    def __call__(self, score):
        self.tempo_map = TempoMap(score)
        self.deformed_time = lambda time: self.tempo_map.ticks2sec(time) * 1000
        return super().__call__(score.Reject(TempoEvent))


_RAND_LIMIT = 3


class Randomize(Effector):
    """
    各音符に対して、その演奏時刻 (実際には dt属性値) とベロシティに
    乱数値を加えます。デフォルトでは、平均0、標準偏差は引数で指定された値の
    ガウス分布に従った乱数が使われます。

    Args:
        time(int, float or function, optional):
            int または float の場合、時刻に加える乱数値の標準偏差を
            指定します（ティック単位）。生成された乱数値の絶対値が
            標準偏差の3倍を超える場合は、3倍以内へ修正されます。
            この引数が関数の場合は、その戻り値がそのまま乱数値になります。
        veloc(int, float or function, optional):
            int または float の場合、ベロシティに加える乱数値の標準偏差を
            指定します。関数の場合は、その戻り値が乱数値として使われます。
        adjust_ctrl(bool, optional):
            Trueの場合、NoteEvent あるいは NoteOnEvent の演奏時刻に加えられる
            乱数値が負であった場合で、修正された演奏時刻から元の演奏時刻までの
            区間に、同じトラック、同じチャネル、同じピッチ (KeyPressureEventの
            ときのみ) の CtrlEvent が存在するときは、その CtrlEvent の演奏時刻
            も NoteEvent あるいは NoteOnEvent の演奏時刻と同じ値に
            修正されます。
    """
    def __init__(self, time=10, veloc=10, adjust_ctrl=True):
        self.ftime = ((lambda: max(-time * _RAND_LIMIT,
                                   min(time * _RAND_LIMIT,
                                       random.gauss(0, time))))
                      if isinstance(time, numbers.Real) else time)
        self.fveloc = ((lambda: random.gauss(0, veloc))
                       if isinstance(veloc, numbers.Real) else veloc)
        self.adjust_ctrl = adjust_ctrl

    def _adjust_ctrl(self, ev):
        if not isinstance(ev, CtrlEvent):
            if isinstance(ev, (NoteEvent, NoteOnEvent)):
                self.note_events_in_outq -= 1
            return ev
        for i, (nev, nev_org_ptime) in enumerate(self.notequeue):
            if (ev.tk == nev.tk and ev.ch == nev.ch and
                (not isinstance(ev, KeyPressureEvent) or ev.n == nev.n) and
                ev.ptime() > nev.ptime() and
                (ev.ptime() < nev_org_ptime or
                 (ev.ptime() == nev_org_ptime and
                  # evの方がnevより先に入力ストリームから読まれた
                  i >= len(self.notequeue) - self.note_events_in_outq))):
                # 該当するノートイベントが複数あるときは、結果的に最小値になる
                ev = ev.copy()
                ev.dt = nev.ptime() - ev.t
                _check_dt(ev)
        return ev

    def _randomize(self, stream):
        notedict = NoteDict()  # NoteOnEvent/NoteOffEventで使用
        outqueue = deque()  # adjust_ctrl==Falseなら、常に空
        # notequeueは、各CtrlEventについてその前後のNote(On)Eventを見つける
        # ために使われる。
        self.notequeue = deque()
        self.note_events_in_outq = 0

        try:
            while True:
                ev = next(stream)
                while outqueue and outqueue[0].t < ev.t - MAX_DELTA_TIME * 2:
                    yield self._adjust_ctrl(outqueue.popleft())
                while (self.notequeue and self.notequeue[0][0].t < ev.t -
                       MAX_DELTA_TIME * 4):
                    self.notequeue.popleft()
                if isinstance(ev, (NoteEvent, NoteOnEvent)):
                    ev = ev.copy()
                    ev.v = max(1, min(127, ev.v + self.fveloc()))
                    r = self.ftime()
                    self.notequeue.append((ev, ev.ptime()))
                    ev.dt = ev.get_dt() + r
                    _check_dt(ev)
                    if isinstance(ev, NoteOnEvent):
                        notedict.pushnote(ev, r)
                    self.note_events_in_outq += 1
                elif isinstance(ev, NoteOffEvent):
                    try:
                        r = notedict.popnote(ev)
                    except KeyError:
                        pass
                    else:
                        ev = ev.copy().update(dt=ev.get_dt() + r)
                if self.adjust_ctrl:
                    outqueue.append(ev)
                else:
                    yield ev
        except StopIteration as e:
            while outqueue:
                yield self._adjust_ctrl(outqueue.popleft())
            return e.value

    def __call__(self, score):
        return score.mapstream(self._randomize)


class Clip(Effector):
    """
    時刻が `start` 以上、`end` 未満の部分だけ切り出します。
    スコアの構造は保たれます。

    Args:
        start(ticks or str): 開始時刻。
            スコア先頭からのティック数を表す数値、もしくは
            :meth:`.mbt2ticks` が受けつける文字列で指定します。
        end(ticks or str, optional): 終了時刻。
            スコア先頭からのティック数を表す数値、もしくは
            :meth:`.mbt2ticks` が受けつける文字列で指定します。
            省略すると、スコアの終わりまでの意味になります。
            小節番号だけの文字列を与えたときは、その小節の終わりまでという
            意味になります。
        initializer(bool, optional):
            Trueの場合、`start` の時点でアクティブ
            (:meth:`.active_events_at` を参照) な CtrlEvent, TempoEvent,
            KeySignatureEvent, TimeSignatureEvent を冒頭でまとめて出力します。
        split_notes(bool, optional):
            Trueの場合、`start` または `end` あるいはその両方の境界に
            またがったnoteは分割されて、結果にはその断片が格納されます。
            Falseの場合は分割は行われずに、発音開始時刻(t属性値)が範囲内にある
            noteのみがそのまま結果に格納されます。
            この機能は NoteEvent にのみ有効で、NoteOnEventやNoteOffEventに
            対しては無効です。

    Examples:
        ``Clip(960)``
            960ティック以降のスコアを切り出します。

        ``Clip('3:2', '7')``
            小節番号3、拍番号2の位置から、小節番号7の小節の終わりまで
            を切り出します。拍番号は0から始まります。
    """
    def __init__(self, start, end=math.inf,
                 initializer=True, split_notes=True):
        self.start = start
        self.end = end
        self.initializer = initializer
        self.split_notes = split_notes

    def _clip(self, ev):
        if ev.t >= self.e:
            exc = StopIteration()
            exc.value = self.e
            raise exc
        if self.split_notes and isinstance(ev, NoteEvent):
            if ev.t < self.s and ev.t + ev.L > self.s:  # start境界を跨ぐ音符
                cut = self.s - ev.t
                ev = ev.copy().update(t=self.s, L=ev.L-cut)
                if hasattr(ev, 'du'):
                    ev.du = max(0, ev.du - cut)
            if ev.t >= self.s and ev.t + ev.L > self.e:  # end境界を跨ぐ音符
                ev = ev.copy().update(L=self.e-ev.t)
                if hasattr(ev, 'du'):
                    ev.du = min(ev.du, ev.L)
        if ev.t >= self.s:
            if self.s != 0:
                ev = ev.copy().update(t=ev.t-self.s)
            return ev
        elif self.initializer and ev in self.iset:
            return ev.copy().update(t=0)
        else:
            return None

    def _durfunc(self, duration):
        return max(0, min(duration, self.e) - self.s)

    def __call__(self, score):
        self.s = TimeSignatureMap(score).mbt2ticks(self.start) \
            if isinstance(self.start, str) else self.start
        if isinstance(self.end, str):
            try:
                bar = int('+' + self.end)  # self.end == '+123' のときは失敗
            except ValueError:
                self.e = TimeSignatureMap(score).mbt2ticks(self.end)
            else:
                self.e = TimeSignatureMap(score).mbt2ticks(bar + 1)
        else:
            self.e = self.end
        if self.initializer:
            self.iset = set(score.active_events_at(self.s,
                                                   (CtrlEvent, MetaEvent)))
        return score.mapev(self._clip, durfunc=self._durfunc)


class Arpeggio(Effector):
    """
    スコア中のコード（同時に発音される音符のグループ）に対して、アルペジオ
    演奏が行われるように、コードの各構成音に対してピッチに順番に応じた値を
    dt属性に加えます。また、ノートオフの時刻が変わらないようにdu属性の値を
    調整します。デフォルトでは、下から上への (つまり、最高音が最も遅れる)
    アルペジオになります。

    Args:
        delay(ticks):
            コード構成音間の時間のずれ幅を指定します。負の数を指定すると、
            上から下へのアルペジオになります。
    """
    def __init__(self, delay=L32):
        self.delay = delay

    def _arpeggio(self, i, m, ev):
        if isinstance(ev, (NoteEvent, NoteOnEvent)):
            if m == 0:
                d = 0
            elif self.delay < 0:
                d = (m - 1 - i) * -self.delay
            else:
                d = i * self.delay
            if d != 0:
                ev = ev.copy()
                if hasattr(ev, 'dt'):
                    ev.dt += d
                else:
                    ev.dt = d
                _check_dt(ev)
                if isinstance(ev, NoteEvent):
                    ev.du = max(0, ev.get_du() - d)
            if isinstance(ev, NoteOnEvent):
                self.notedict.pushnote(ev, ev.ptime())
        elif isinstance(ev, NoteOffEvent):
            noteon_ptime = self.notedict.popnote(ev, 0)
            # ノートオフの演奏時刻がノートオンのものより前の場合は修正
            if noteon_ptime > ev.ptime():
                ev = ev.copy().update(dt=noteon_ptime-ev.t)
        return ev

    def __call__(self, score):
        self.notedict = NoteDict()
        return score.chord_mapev(self._arpeggio)


# class _Undefined:
#     def __add__(self, other):
#         return self

#     def __radd__(self, other):
#         return self

#     def __sub__(self, other):
#         return self

#     def __rsub__(self, other):
#         return self

#     def __mul__(self, other):
#         return self

#     def __rmul__(self, other):
#         return self

#     def __matmul__(self, other):
#         return self

#     def __rmatmul__(self, other):
#         return self

#     def __truediv__(self, other):
#         return self

#     def __rtruediv__(self, other):
#         return self

#     def __floordiv__(self, other):
#         return self

#     def __rfloordiv__(self, other):
#         return self

#     def __mod__(self, other):
#         return self

#     def __rmod__(self, other):
#         return self

#     def __pow__(self, other):
#         return self

#     def __rpow__(self, other):
#         return self

#     def __lshift__(self, other):
#         return self

#     def __rlshift__(self, other):
#         return self

#     def __rshift__(self, other):
#         return self

#     def __rrshift__(self, other):
#         return self

#     def __and__(self, other):
#         return self

#     def __rand__(self, other):
#         return self

#     def __or__(self, other):
#         return self

#     def __ror__(self, other):
#         return self

#     def __xor__(self, other):
#         return self

#     def __rxor__(self, other):
#         return self

#     def __pos__(self):
#         return self

#     def __neg__(self):
#         return self

#     def __invert__(self):
#         return self

#     def __bool__(self):
#         return False

#     def __eq__(self, other):
#         return False

#     def __ne__(self, other):
#         return False

#     def __lt__(self, other):
#         return False

#     def __le__(self, other):
#         return False

#     def __gt__(self, other):
#         return False

#     def __ge__(self, other):
#         return False

#     def __getitem__(self, key):
#         return self

#     def __getattr__(self, name):
#         return self

#     def __float__(self):
#         return self

#     def __floor__(self):
#         return self


# Undefined = _Undefined()


def _event_dict(ev):
    return dict(ev=ev, t=ev.t, tk=ev.tk, dt=ev.get_dt(),
                n=getattr(ev, 'n', None),
                v=getattr(ev, 'v', None),
                nv=getattr(ev, 'nv', None),
                ch=getattr(ev, 'ch', None),
                L=getattr(ev, 'L', None),
                du=getattr(ev, 'du', ev.get_du()
                           if isinstance(ev, NoteEvent)
                           else None),
                ctrlnum=getattr(ev, 'ctrlnum', None),
                mtype=getattr(ev, 'mtype', None),
                xtype=getattr(ev, 'xtype', None),
                value=getattr(ev, 'value', None))


class Filter(Effector):
    """
    条件を満たした（あるいは満たさない）イベントのみ含むスコアへ変換します。
    スコアの構造は保存され、従って、空のイベントリストが残ることがあります。
    各イベントはコピーされません。

    Args:
        conds(class, str, or function, each): 各引数は基本条件を表し、
            それらすべての論理和が最終的な条件となります。
            各引数は次のいずれかです。

            * イベントクラス -- そのクラス (またはそのサブクラス) に属する
              イベントならば真となります。
            * eval() によって評価可能な文字列 -- bool値を与える Python の式を
              含んだ文字列によって条件を指定します。文字列の中で、'ev' は
              イベント自身、また、't', 'tk', 'dt', 'n', 'v', 'nv', 'ch',
              'L', 'du', 'ctrlnum', 'mtype', 'xtype', 'value' はイベントの
              属性値を表す定数として使用できます。
              イベントが持っていない属性については、これらの定数の値は
              None になります (ただし、'dt'については 0, NoteEventに
              対する'du'については 'L'と同じ値となります)。式の評価において
              TypeError 例外が発生した場合は、式の値をFalseだとみなして処理を
              続けます。
            * bool値を返す関数 -- イベントを引数として呼び出され、その戻り値が
              条件の真偽になります。

        negate(bool, optional):
            False(デフォルト)の場合、条件を満たすイベントからなるスコアを
            出力します。Trueの場合、条件を満たさないイベント（つまり、デフォル
            トの場合に出力されないイベント）からなるスコアを出力します。
        globals(dict, optional):
            `conds` が文字列のときに、その中に出現する大域変数の辞書を指定
            します。
            デフォルトでは、コンストラクタを呼ぶ時点での globals() の値に
            なっています。
        locals(dict, optional):
            `conds` が文字列のときに、その中に出現する局所変数の辞書を指定
            します。
            デフォルトでは、コンストラクタを呼ぶ時点での locals() の値に
            なっています。

    Examples:
        ``Filter(NoteEventClass, TempoEvent)``
            ノート関連イベント (NoteEvent、NoteOnEvent、および、NoteOffEvent)
            とテンポイベントを抜き出します。

        ``Filter('ctrlnum == 7')``
            7番のコントロールチェンジイベントを抜き出します。

        ``Filter(lambda ev: hasattr(ev, 'ctrlnum') and ev.ctrlnum == 7)``
            上の例と等価な操作を関数で記述した例です。

        ``Filter('ctrlnum == C_PROG', negate=True)``
            プログラムチェンジイベントを取り除きます。
            ``Filter('ctrlnum != C_PROG')`` あるいは 
            ``Reject('ctrlnum == C_PROG')`` でも同じ意味になります。

        ``Filter('n >= C4')``
            ピッチがC4以上のノート関連イベントおよびKeyPressureEventを抜き出し
            ます (n属性の無いイベントは TypeError例外を生じるため結果として
            出力されません)。

        ``Filter('n < C4', negate=True)``
            ピッチがC4未満のノート関連イベントおよびKeyPressureEventを取り除き
            ます（つまり、ピッチがC4以上のそれらのイベントと、n属性を持たない
            その他のイベントを抜き出します)。``Reject('n < C4')`` とも
            書けます。この例のように TypeError例外が生じるケースでは、
            ``Filter('...')`` と ``Reject('not ...')`` は等価ではありません。

        ``Filter('n >= C5 and L == L4')``
            ピッチがC5以上、かつ音価が4分音符と等しいNoteEventを抜き出します。

        ``Filter('ch in (1,2,4)', MetaEvent)``
            MIDIチャネルが1,2,4のいずれかであるイベント、および
            すべてのメタイベントを抜き出します。

        ``Filter('isinstance(ev, SysExEvent) and value[0] != 0xf0')``
            最初のバイトが 0xf0 でないシステムエクルシーブメッセージのイベント
            を抜き出します。
    """
    def __init__(self, *conds, negate=False, globals=None, locals=None):
        self.eventclasses = []
        self.condexprs = []
        for cond in conds:
            # issubclassだけだと、condがクラスでないときに例外が発生してしまう
            if hasattr(cond, '__base__') and issubclass(cond, Event):
                self.eventclasses.append(cond)
            elif isinstance(cond, str) or callable(cond):
                self.condexprs.append(cond)
            else:
                raise Exception("each argument must be a event class, "
                                "a string or a function")
        self.negate = negate
        self.globals = (takt.frameutils.outerglobals()
                        if globals is None else globals)
        self.locals = (takt.frameutils.outerlocals()
                       if locals is None else locals)

    def _eval_cond(self, cond, ev):
        if isinstance(cond, str):
            try:
                return eval(cond, self.globals,
                            dict(self.locals, **_event_dict(ev)))
            except TypeError:
                return False
        else:
            return cond(ev)

    def __call__(self, score):
        return score.mapev(lambda ev:
                           ev if ((any(isinstance(ev, cls)
                                       for cls in self.eventclasses) or
                                   any(self._eval_cond(cond, ev)
                                       for cond in self.condexprs))
                                  != self.negate) else None)


class Reject(Filter):
    """
    条件を満たさないイベントのみ含むスコアへ変換します。
    Reject(...) は Filter(..., negate=True) と等価です。
    """
    def __init__(self, *conds, globals=None, locals=None):
        super().__init__(*conds, negate=True, globals=globals, locals=locals)
    

class Cond(Effector):
    """
    条件を満たしたイベントにのみ指定されたエフェクタを適用します。
    条件を満たさないイベントはそのまま出力されます。

    出力において、エフェクタを適用したものとそうでない同時刻のイベントが
    存在するときは、エフェクタを適用したイベントの方が必ず後になります。

    Args:
        cond(class, str, or function): 条件を :class:`Filter` の `conds` 引数と
            同じ形式（ただし１つの基本条件のみ）で指定します。
        effector(Effector): 適用するエフェクタのオブジェクト。
        globals(dict, optional):
            :class:`Filter` の `globals` 引数と同じ意味です。
        locals(dict, optional):
            :class:`Filter` の `locals` 引数と同じ意味です。

    Examples:
        ``Cond('n >= C5', ScaleVelocity(1.2))``
            ピッチが C5 以上 NoteEvent および NoteOnEvent に対して、
            ベロシティを1.2倍します。
    """
    def __init__(self, cond, effector, globals=None, locals=None):
        self.conds = cond if isinstance(cond, tuple) else (cond,)
        self.effector = effector
        if globals is None:
            globals = takt.frameutils.outerglobals()
        if locals is None:
            locals = takt.frameutils.outerlocals()
        self.filter_t = Filter(*self.conds, globals=globals, locals=locals)
        self.filter_f = Filter(*self.conds, negate=True,
                               globals=globals, locals=locals)

    def _do_cond(self, stream):
        return (self.filter_f(stream.tee()) &
                self.effector(self.filter_t(stream)))

    def __call__(self, score):
        return score.mapstream(self._do_cond)


class Modify(EventEffector):
    """
    各イベントに対して、`operation` で指定された文の列を実行し、その結果に
    従って更新したイベントを出力します。これにより、:meth:`.Score.mapev` に
    代わる簡易的なイベント更新の手段を提供します。

    イベントは常にコピーされてから更新されます（コピーを避けたい場合は
    :meth:`.Score.mapev` を使用して下さい）。

    Args:
        operation(str):
            exec() によって評価可能な文字列を指定します。
            文字列の中で、'ev' はイベント自身を表す変数として使用できます。
            また、't', 'tk', 'dt', 'n', 'v', 'nv', 'ch', 'L', 'du', 'ctrlnum',
            'mtype', 'xtype', 'value' はイベントの属性値を表す変数として使用で
            き、それらを書き換えることによってイベントの属性値を変更できます。
            'ev' を通じて属性の追加・変更をすることは可能ですが、上に挙げた
            変数に対応する属性についは、その変数の値の方が優先します。
            文字列の評価中に TypeError 例外が発生した場合は、そのイベント
            に対する更新は行われません。
        globals(dict, optional):
            `operation` 文字列中に出現する大域変数の辞書。
            デフォルトでは、コンストラクタを呼ぶ時点での globals() の値に
            なっています。
        locals(dict, optional):
            `operation` 文字列中に出現する局所変数の辞書。
            デフォルトでは、コンストラクタを呼ぶ時点での locals() の値に
            なっています。

    Examples:
        ``Modify('ch=3')``
            MIDIチャネル番号をすべて3に変更したものを出力します。`ch` 属性を
            持たないイベントについては何も変更せずに出力します。
        ``Modify('v*=0.8; nv=30')``
            ノート関連イベントについて、ベロシティを0.8倍し、ノートオフ
            ベロシティを30に設定して出力します。それ以外のイベントは何も変更
            せずに出力します。
        ``Modify('if tk==2: v*=1.1')``
            トラック番号が2である NoteEvent, NoteOnEvent について、
            ベロシティを1.1倍して出力します。それ以外のイベントは何も変更
            せずに出力します。
        ``Modify('ev.voice=2')``
            すべてのイベントに対し、'voice' という属性を無ければ追加し、
            値を2に設定して出力します。
    """
    def __init__(self, operation, globals=None, locals=None):
        self.operation = operation
        self.globals = (takt.frameutils.outerglobals()
                        if globals is None else globals)
        self.locals = (takt.frameutils.outerlocals()
                       if locals is None else locals)

    def _process_event(self, ev):
        env = dict(self.locals, **_event_dict(ev.copy()))
        try:
            exec(self.operation, self.globals, env)
        except TypeError:
            return ev
        ev = env['ev']
        ev.t = env['t']
        ev.tk = env['tk']
        if env['dt'] != 0:
            ev.dt = env['dt']
        for attr in ('n', 'v', 'nv', 'ch', 'L', 'ctrlnum',
                     'mtype', 'xtype', 'value'):
            if hasattr(ev, attr):
                setattr(ev, attr, env[attr])
        if isinstance(ev, NoteEvent) and env['du'] != env['L']:
            ev.du = env['du']
        # コンテキストではないので dr=50 みたいのはできない (du*=0.5とする)。
        return ev


if '__SPHINX_AUTODOC__' not in os.environ:
    # デフォルトのScoreへの登録法だと outerglobals/locals が正しく設定されない.
    def __filter(score, *args, globals=None, locals=None, **kwargs):
        if globals is None:
            globals = takt.frameutils.outerglobals()
        if locals is None:
            locals = takt.frameutils.outerlocals()
        eff = Filter(*args, globals=globals, locals=locals, **kwargs)
        return eff(score)
    setattr(Score, Filter.__name__, __filter)

    def __reject(score, *args, globals=None, locals=None, **kwargs):
        if globals is None:
            globals = takt.frameutils.outerglobals()
        if locals is None:
            locals = takt.frameutils.outerlocals()
        eff = Reject(*args, globals=globals, locals=locals, **kwargs)
        return eff(score)
    setattr(Score, Reject.__name__, __reject)

    def __cond(score, *args, globals=None, locals=None, **kwargs):
        if globals is None:
            globals = takt.frameutils.outerglobals()
        if locals is None:
            locals = takt.frameutils.outerlocals()
        eff = Cond(*args, globals=globals, locals=locals, **kwargs)
        return eff(score)
    setattr(Score, Cond.__name__, __cond)

    def __modify(score, *args, globals=None, locals=None, **kwargs):
        if globals is None:
            globals = takt.frameutils.outerglobals()
        if locals is None:
            locals = takt.frameutils.outerlocals()
        eff = Modify(*args, globals=globals, locals=locals, **kwargs)
        return eff(score)
    setattr(Score, Modify.__name__, __modify)


class _StreamReader:
    def __init__(self, pscore, time_offset):
        self.pscore = pscore
        self.stream = pscore.stream()
        self.time_offset = time_offset
        self.notedict = NoteDict()
        self.topev = None  # look-ahead event
        self.limit = None
        self.read_next()

    def read_next(self) -> None:
        try:
            ev = next(self.stream)
            ev = ev.copy().update(t=ev.t+self.time_offset)
            self.topev = ev
            if self.limit is not None and ev.t >= self.limit:
                self.topev = None
            else:
                if isinstance(ev, NoteOnEvent):
                    self.notedict.pushnote(ev, ev)
                elif isinstance(ev, NoteOffEvent):
                    self.notedict.popnote(ev, None)
        except StopIteration:
            self.topev = None

        # limitによる打ち切りのあと、発音中のノートに対してnote-offを送る。
        if (self.limit is not None) and (self.topev is None) and self.notedict:
            _, ev = self.notedict.popitem()
            self.topev = NoteOffEvent(self.limit, ev.n, None, ev.tk, ev.ch,
                                      **ev.__dict__)

    def top(self) -> Optional[Event]:
        return self.topev

    def end(self) -> bool:
        return self.topev is None

    def terminate(self, limit) -> None:
        self.limit = limit
        ev = self.topev
        if ev is not None and ev.t >= limit:
            if isinstance(ev, NoteOffEvent):
                ev.t = limit
            else:
                if isinstance(ev, NoteOnEvent):
                    self.notedict.popnote(ev, None)
                self.read_next()


class Product(Effector):
    """
    入力スコア中の各音符をパターンとなるスコアで置き換えます。
    これは、オクターブ演奏、ロール演奏、装飾音、トリル演奏など様々な用途に
    応用できます。パターンは、MML文字列 (:func:`.mml` を参照)、もしくは
    スコアを返す関数の形で与えます。

    デフォルトの場合、出力される音符のピッチは、入力スコアでの音符のピッチに、
    パターン中のピッチの C4 から音程を加えたものとなります。例えば、
    ``mml('CD').Product('[CE]')`` は、元のそれぞれの音符を完全1度
    と長3度からなる和音に置き換える意味になり、その結果 ``mml('[CE][DF#]')``
    と等価なスコアになります。

    出力中の各パターンの開始時刻は、元になる入力スコア中の音符の開始時刻と
    常に同一です。また、全体の演奏長は変わりません。
    各音符に対応するパターンの演奏期間がその音符の音価より長い場合は、
    通常、その音価の長さで打ち切られます。ただし、パターンに演奏長
    が 0 である EventList または Tracks を指定している場合は (例えば、
    ``Product('{CDEF}&')`` のような場合) は、この打ち切りが行われません
    (その場合、そのパターンと次の音符に対するパターンとのオーバーラップを
    許すことになります）。

    このエフェクタは入力デバイスからの RealTimeStream に対して適用することも
    できます。

    Args:
        pattern(str or function):
            パターンのスコアを生成する MML 文字列、またはスコアを返す関数を
            を指定します。生成されるスコアは無限長であっても構いません。
            この文字列や関数を評価するときのコンテキストは
            入力スコア中の NoteEvent または NoteOnEvent によって各音符ごとに
            設定され、それによって入力スコア中の音符のパラメータをパターンに
            反映することが可能です。v、nv、L、tk、ch、dt 属性は（あれば）
            元のイベントと同じ値に設定されます。元のイベントがNoteOnEventだった
            場合、L属性は無限大に設定されます。一方 NoteEventだった場合、
            dr 疑似属性が元の音符と同じになるように設定されます。
            o属性は常に4に設定されます。
        tail(str or function, optional):
            パターンの終了部分のスコアを生成する MML 文字列、またはスコアを
            返す関数を指定します。`tail` によるスコアの演奏長の分だけ
            `pattern` によるスコアは短くなります。これは、
            トリル演奏の最後に装飾音を挿入する場合などに利用できます。
            `tail` によって生成されるスコアは無限長であってはなりません。
            また、入力スコアに含まれるイベントが NoteOnEvent の場合は
            使用できません。コンテキストは `pattern` と同様に設定されます。
        scale(Scale, optional):
            この引数でスケールを指定した場合、そのスケール上のトーン番号
            (:class:`.Scale` を参照) に基づいて出力される音符のピッチを決定
            します。具体的には、出力される音符のトーン番号は、
            入力スコアでの音符のトーン番号に、パターン中のピッチのトーン番号を
            加えたものとなります。

    Examples:
        ``Product("[C ^C]")``
            各音符に対して、１オクターブ上の音を付加します。
        ``Product(lambda: note(C4) & note(C5))``
            上と等価の処理を関数を使って記述したものです。
        ``Product("[[v*=0.9 CE]G]")``
            各音符を、それを根音とした長3和音へ変換します。最高音以外の音に
            対してはベロシティを0.9倍しています。
        ``Product("{CDEF}//", scale=Scale(C4))``
            各音符に対して、C major scale上の連続する4音を、元の1/4の音価
            で演奏します。例えば、
            ``mml("CDE").Product("{CDEF}//", scale=Scale(C4))``
            は ``mml("{CDEF DEFG EFGA}//")`` と等価なスコアを生成します。
        ``Product("{L16 CDEFGAB^C}&")``
            各音符に対して、それを開始音とした長音階スケールを16分音符
            で演奏します。元の音符の音価にかかわらず、常に最後まで
            スケールが演奏されます。(もしMML最後の '&' がない場合は、
            元の音符の音価に相当する長さに切り詰められます。）
        ``Product("G(L32)F", scale=Scale(F4, 'minor'))``
            各音符に対して、F natural minor scale における1つ上の音の前打音を
            付加します。後の音符の音価は、元の音符の音価より32音符の分だけ短く
            なります。
        ``Product("L32 C@@")``
            各音符に対して、32分音符で同じピッチの音を繰り返す演奏
            (いわゆるロール演奏) を行います。
        ``Product("L32 {CD}@@", tail="L=L8/5 CDC_BC")``
            各音符に対して、32分音符でその全音上の音と交互に繰り返す
            演奏 (いわゆるトリル演奏) を行います。各音符の終わりの部分には
            `tail` で指定した演奏が挿入されます。
    """
    def __init__(self, pattern, *, tail=None, scale=None):
        self.pattern = pattern
        self.tail = tail
        self.scale = scale
        self.root = C4 if scale is None else scale.tonic

    def _get_score(self, arg):
        if isinstance(arg, str):
            return mml(arg)
        else:
            return arg()

    def _conv_pitch(self, n):
        return Transpose(n - self.root if self.scale is None
                         else self.scale.tonenum(n), scale=self.scale)

    def _product(self, stream):
        nexttime = 0
        duration = 0
        readers = []
        notedict = NoteDict()
        lbobj = ['_product']

        while nexttime != math.inf:
            try:
                ev = next(stream)
                if isinstance(ev, NoteEvent):
                    with newcontext(v=ev.v, nv=ev.nv, tk=ev.tk, ch=ev.ch,
                                    L=ev.L, dt=ev.get_dt(),
                                    dr=ev.get_du()/ev.L*100, o=4):
                        pscore = self._get_score(self.pattern)
                        taillen = 0
                        if self.tail is not None:
                            tailscore = self._get_score(self.tail)
                            tailscore = tailscore.Clip(
                                max(0, tailscore.get_duration() - ev.L),
                                initializer=False)
                            taillen = tailscore.get_duration()
                    if isinstance(pscore, EventStream) or \
                       pscore.get_duration() != 0:
                        pscore = EventList(pscore.Clip(
                            0, max(0, ev.L - taillen), initializer=False))
                    if self.tail is not None:
                        pscore += tailscore
                    pscore = self._conv_pitch(ev.n)(pscore)
                    r = _StreamReader(pscore, ev.t)
                    if not r.end():
                        readers.append(r)
                elif isinstance(ev, NoteOnEvent):
                    with newcontext(v=ev.v, tk=ev.tk, ch=ev.ch,
                                    L=math.inf, dt=ev.get_dt(), o=4):
                        pscore = self._get_score(self.pattern)
                    pscore = self._conv_pitch(ev.n)(pscore)
                    r = _StreamReader(pscore.UnpairNoteEvents(), ev.t)
                    if not r.end():
                        readers.append(r)
                    notedict.pushnote(ev, r)
                elif isinstance(ev, NoteOffEvent):
                    r = notedict.popnote(ev, None)
                    if r is not None:
                        if not r.end() and (isinstance(r.pscore, EventStream)
                                            or r.pscore.get_duration() != 0):
                            r.terminate(ev.t)
                            if r.end():
                                readers.remove(r)
                elif isinstance(ev, LoopBackEvent) and ev.value is lbobj:
                    pass
                else:
                    yield ev
                nexttime = ev.t
            except StopIteration as e:
                duration = e.value
                nexttime = math.inf

            # nextimeに至るまでの間、readersからイベントを取得してyield
            while True:
                rmin = min(readers, default=None, key=lambda r: r.top().t)
                if rmin is None:
                    break
                elif rmin.top().t > nexttime:
                    if isinstance(self.score, RealTimeStream):
                        if rmin.top().t != math.inf:
                            self.score.queue_event(LoopBackEvent(rmin.top().t,
                                                                 lbobj))
                    break
                else:
                    yield rmin.top()
                    rmin.read_next()
                    if rmin.end():
                        readers.remove(rmin)

        return duration

    def __call__(self, score):
        self.score = score
        return score.mapstream(self._product)


class Apply(Effector):
    """
    入力スコアに対して、別のスコア（パターン）のリズムおよび表情付け情報を
    適用します。ピッチは異なるが共通のリズムや表情付けを持ったフレーズが多く
    出現するような曲の記述に特に有効です。

    変換は次のように行われます。入力スコアの音符とパターンの音符との間で
    照合が行われ、入力スコアの各音符について、それに対応するパターン中の音符の
    情報が次のように適用されます。

    - ピッチは入力スコアのものが使われ、パターンのものは無視されます。
    - dtは入力スコアのものとパターンのものの和になります。
    - vは、パターンのものに、入力スコアのものとコンテキストが持つ値との
      差分を加えた値になります。
    - 発音時刻、音長を含むそれ以外の属性はパターンのものが使われます。

    照合は、同時発音される音符をまとめたグループ（単音の場合を含めて以下では
    コードと呼ぶ）を単位として行われます。
    コード内における各音符の照合は、出現順に後ろから行われます。入力スコアの
    方がコード構成音が多い時は、その分だけパターンの最初のコード構成音が複製
    されます。

    入力スコアの方がパターンより短い (コード数が少ない) 場合、パターンにおける
    余ったコードは捨てられます。入力スコアの方がパターンよりコード数が
    多い場合は、例外が送出されます。

    入力スコア中に n属性が Noneである NoteEvent を含まれている場合、
    これも１つの音符として照合の対象になりますが、出力はされません。

    パターン中のノート以外のイベントはそのまま出力されます。入力スコア中の
    NoteEvent 以外のイベントは無視されます。NoteOnEvent および NoteOffEvent
    を含んだ入力スコアに対しては使用できません。

    Args:
        pattern(Score or str):
            パターンとなるスコアを指定します。文字列の場合は MMLだと
            見なされます。無限長であっても構いません。

    Examples:
        ``mml("CDEF`").Apply("{C!C`>C/C/}")``
            ``mml("C!D`>E/F`/")`` と等価なスコアを生成します。
        ``mml("CDEF").Apply("{C.C/}@@")``
            付点のリズムに変換され、``mml("C.D/E.F/")`` と等価なスコアを
            生成します。
        ``mml("[CE] [EG] [EGB]").Apply("C [C? C] [C? C]")``
            ``mml("[CE] [E? G] [E? G? B]")`` と等価なスコアを生成します。
    """
    def __init__(self, pattern):
        if isinstance(pattern, str):
            pattern = mml(pattern)
        self.pattern = pattern

    def _apply(self, stream):
        duration = 0
        chord_iter = stream.Filter(NoteEvent).chord_iterator(cont_notes=False)
        pchord_iter = self.pattern.tee().chord_iterator(cont_notes=False)
        # 空のコードを取り除く
        chord_iter = (chord for chord in chord_iter if len(chord) > 0)

        for chord in chord_iter:
            while True:
                try:
                    pchord_org = next(pchord_iter)
                except StopIteration:
                    raise Exception("pattern is shorter than target score")
                pchord = pchord_org.Filter(NoteEvent)
                if len(pchord) != 0:
                    break
                yield from pchord_org
                duration = pchord_org.duration
            if len(chord) > len(pchord):
                # chord の方がコード構成音数の方が多い場合は、
                # その分だけパターン先頭要素を複製する。
                pchord[0:0] = list(pchord)[0:1] * (len(chord) - len(pchord))
            elif len(chord) < len(pchord):
                # 逆の場合は、余分なパターン先頭要素を削除する
                del pchord[0:(len(pchord) - len(chord))]
            outdict = {}  # dict: pev => list_of_output_events
            for (ev, pev) in zip(chord, pchord):
                if ev.n is not None:
                    result = pev.copy()
                    result.n = ev.n
                    if hasattr(ev, 'dt') or hasattr(pev, 'dt'):
                        result.dt = ev.get_dt() + pev.get_dt()
                    result.v = ev.v - context().v + pev.v
                    outdict.setdefault(pev, []).append(result)
            yield from pchord_org.mapev(lambda pev: outdict.get(pev, [])
                                        if isinstance(pev, NoteEvent)
                                        else pev.copy())
            duration = pchord_org.duration

        return duration

    def __call__(self, score):
        return score.mapstream(self._apply)


class ToTracks(Effector):
    """
    トラック番号 (tk属性の値) によって仕分けした構造に変換します。
    変換されたスコアでは、トラック毎にイベントリストが存在し、それが
    :class:`.Tracks` によって1つにまとめられた構造になります。
    各トラックのイベントは時間順にソートされます。

    Args:
        set_tk_by_ch(bool): 仕分ける前に各イベントのtk属性にch属性の値をセット
            します。結果的に、MIDIチャネル番号で仕分けすることになります。
            ch属性のないイベントのトラック番号は0になります。
        limit(ticks): スコアの長さを制限します。
            制限の詳細については、:meth:`.Score.stream` の同名の引数
            の項目を見てください。
    """
    def __init__(self, set_tk_by_ch=False, limit=DEFAULT_LIMIT):
        self.set_tk_by_ch = set_tk_by_ch
        self.limit = limit

    def __call__(self, score):
        iterator = score.stream(limit=self.limit)
        result = Tracks([EventList()])  # 無イベントでもEventListを1つ残す
        try:
            while True:
                ev = next(iterator)
                if self.set_tk_by_ch:
                    ev = ev.copy().update(tk=getattr(ev, 'ch', 0))
                tk = max(ev.tk, 0)
                while len(result) < tk + 1:
                    result.append(EventList())
                result[tk].append(ev)
        except StopIteration as e:
            for evlist in result:
                evlist.duration = e.value
        if isinstance(score, Tracks):
            # scoreが Tracks ならば、属性情報をコピーする(textモジュールで使用)
            result.__dict__.update(score.__dict__)
        return result


class Render(Effector):
    """
    dtやdu属性を持っているイベントに対し、楽譜上の時間を演奏上の時間
    で更新します。具体的には、t属性に(あれば)dt属性の値を加え、L属性に
    (あれば)du属性の値を設定します。デフォルトでは、dtやdu属性はその後削除
    されます。

    スコアだけでなく、単独のイベントに対しても変換を適用することができます。

    Args:
        swap(bool, optional): Trueの場合、楽譜上の時間と演奏上の時間を
            入れ替えます。2回適用すると元へ戻ります。
    """
    def __init__(self, swap=False):
        self.swap = swap

    def _render(self, ev):
        if hasattr(ev, 'dt') or hasattr(ev, 'du'):
            ev = ev.copy()
            if hasattr(ev, 'dt'):
                ev.t += ev.dt
                if self.swap:
                    ev.dt = -ev.dt
                else:
                    delattr(ev, 'dt')
            if hasattr(ev, 'du'):
                le = ev.L
                ev.L = ev.du
                if self.swap:
                    ev.du = le
                else:
                    delattr(ev, 'du')
        return ev

    def _render_stream(self, stream):
        delaybuf = []
        seqno = itertools.count()
        try:
            while True:
                ev = next(stream)
                while delaybuf and delaybuf[0][0] < ev.t - MAX_DELTA_TIME:
                    yield delaybuf[0][2]
                    heapq.heappop(delaybuf)
                ev = self._render(ev)
                heapq.heappush(delaybuf, (ev.t, next(seqno), ev))
        except StopIteration as e:
            while delaybuf:
                yield delaybuf[0][2]
                heapq.heappop(delaybuf)
            return e.value

    def __call__(self, score_or_event):
        if isinstance(score_or_event, Event):
            return self._render(score_or_event)
        elif isinstance(score_or_event, EventStream):
            return score_or_event.__class__(
                self._render_stream(score_or_event))
        else:
            return score_or_event.mapev(self._render)


class Tie(EventEffector):
    """ スコア中の NoteEvent に対して、タイの開始を表す属性を
    付加します。"""
    def _process_event(self, ev):
        if isinstance(ev, NoteEvent):
            return ev.copy().update(tie=getattr(ev, 'tie', 0) | BEGIN)
        else:
            return ev


class EndTie(EventEffector):
    """ スコア中の NoteEvent に対して、タイの終了を表す属性を
    付加します。タイの開始かつ終了となる音符に対しては、このエフェクタと
    Tie() エフェクタの両方を適用してください。"""
    def _process_event(self, ev):
        if isinstance(ev, NoteEvent):
            return ev.copy().update(tie=getattr(ev, 'tie', 0) | END)
        else:
            return ev


class ConnectTies(Effector):
    """ スコア中のタイで結ばれた NoteEvent を統合して１つの NoteEvent に
    します。正しく結ばれるためには、前の NoteEvent の終了時刻 (t属性と
    L属性の値の和) と後の NoteEvent の開始時刻 (t属性値) が一致していなくては
    なりません。
    """
    def _connect_ties(self, stream):
        notedict = NoteDict()  # (firstev, lastev)   lastevは警告メッセージ用。
        evbuf = []  # notedictが空でない間は、出力をここへ一時保管する。

        def getkey(ev, addL=True):
            return (ev.tk, ev.ch, ev.n,
                    round(ev.t + addL * ev.L, -LOG_EPSILON))

        try:
            while True:
                if not notedict:
                    yield from evbuf
                    evbuf.clear()
                ev = next(stream)
                if isinstance(ev, NoteEvent) and hasattr(ev, 'tie'):
                    if ev.tie == BEGIN:
                        ev = ev.copy()
                        notedict.push(getkey(ev), (ev, ev))
                    else:  # end or end&begin
                        try:
                            firstev, _ = notedict.pop(getkey(ev, False))
                            if hasattr(ev, 'du'):
                                firstev.du = firstev.L + ev.du
                            firstev.L += ev.L
                            if ev.tie == END | BEGIN:
                                notedict.push(getkey(firstev), (firstev, ev))
                            else:  # end
                                del firstev.tie
                        except KeyError:
                            warnings.warn("Beginning of the tie not found: %r"
                                          % (ev,), TaktWarning, stacklevel=2)
                        continue
                evbuf.append(ev)
        except StopIteration as e:
            for _, ev in notedict.values():
                warnings.warn("Unterminted tie: %r" % (ev,),
                              TaktWarning, stacklevel=2)
            yield from evbuf
            return e.value

    def __call__(self, score):
        return score.mapstream(self._connect_ties)


class Dump(EventEffector):
    def _process_event(self, ev):
        print(ev)
        return ev


class Voice(EventEffector):
    """
    スコアに含まれる NoteEventClass に属するイベントに対して、
    voice属性を追加します。voice属性は :meth:`.Score.music21` で利用されます。

    Args:
        voice(int): voice属性の値
    """
    def __init__(self, voice):
        self.voice = voice

    def _process_event(self, ev):
        if isinstance(ev, NoteEventClass):
            return ev.copy().update(voice=self.voice)
        else:
            return ev


class Mark(EventEffector):
    """
    スコアに含まれる NoteEventClass に属するイベントに対して、
    mark属性の追加（すでにmark属性が存在すればそれへの値の追加) を行います。
    mark属性は :meth:`.Score.music21` で利用されます。

    Args:
        mark(str or tuple of str): mark属性として追加する文字列またはそのタプル
    """
    def __init__(self, mark):
        self.mark = mark

    def _process_event(self, ev):
        if isinstance(ev, NoteEventClass):
            m = getattr(ev, 'mark', ())
            m = (*(m if isinstance(m, (tuple, list)) else (m,)),
                 *(self.mark if isinstance(self.mark, (tuple, list))
                   else (self.mark,)))
            return ev.copy().update(mark=m[0] if len(m) == 1 else m)
        else:
            return ev


class PairNoteEvents(Effector):
    """
    スコアに含まれる NoteOnEvent と NoteOffEvent を対にして、
    NoteEvent へ変換します。このエフェクタ適用後は NoteOnEvent と NoteOffEvent
    を含まないことが保証されます。

    NoteOnEventとNoteOffEventの対応づけは、tk属性、ch属性、n属性が
    すべて一致するものの間で行われますが、複数の可能性がある場合は、
    より早い時刻のNoteOnEventはより早い時刻のNoteOffEventと組になる
    ような対応づけが行われます。なお、異なる EventList あるいは EventStream
    にまたがった対応づけは行われません。

    対応する NoteOnEvent が無い NoteOffEvent を含む場合は、警告とともに
    削除されます。
    対応する NoteOffEvent が無い NoteOnEvent を含む場合は、警告が出されると
    ともに、当該 EventList または EventStream の演奏長まで続く音符（それが
    不可能な場合は音価0の音符）として NoteEvent が生成されます。
    """
    def _pair_note_events(self, stream):
        notedict = NoteDict()
        outqueue = deque()
        try:
            while True:
                while outqueue and (not isinstance(outqueue[0], NoteEvent) or
                                    outqueue[0].L is not None):
                    yield outqueue.popleft()
                ev = next(stream)
                if isinstance(ev, NoteOnEvent):
                    noteev = NoteEvent(ev.t, ev.n, None, ev.v, None,
                                       tk=ev.tk, ch=ev.ch, **ev.__dict__)
                    notedict.pushnote(ev, noteev)
                    outqueue.append(noteev)
                elif isinstance(ev, NoteOffEvent):
                    try:
                        noteev = notedict.popnote(ev)
                    except KeyError:
                        warnings.warn("deleted orphan note-off events "
                                      "(t=%r, n=%r)" % (ev.t, ev.n),
                                      TaktWarning, stacklevel=1)
                    else:
                        noteev.L = ev.t - noteev.t
                        noteev.nv = ev.nv
                        if abs(noteev.get_dt() - ev.get_dt()) > EPSILON:
                            noteev.du = noteev.L - noteev.get_dt() \
                                        + ev.get_dt()
                else:
                    outqueue.append(ev)
        except StopIteration as e:
            for ev in outqueue:
                if isinstance(ev, NoteEvent) and ev.L is None:
                    warnings.warn("forced to close unterminated notes "
                                  "(t=%r, n=%r)" % (ev.t, ev.n),
                                  TaktWarning, stacklevel=1)
                    ev.L = max(stream.duration - ev.t, 0)
                yield ev
            return e.value

    def __call__(self, score):
        return score.mapstream(self._pair_note_events)


class UnpairNoteEvents(Effector):
    """
    スコア中に含まれる NoteEvent を、NoteOnEvent と NoteOffEvent の
    対に変換します。NoteOffEvent の時刻は、元の NoteEvent の時刻に
    L属性値を加えたものになります。
    """
    def _unpair_note_events(self, stream):
        noteoffbuf = []
        seqno = itertools.count()
        try:
            while True:
                ev = next(stream)
                while noteoffbuf and noteoffbuf[0][0] <= ev.t:
                    yield noteoffbuf[0][2]
                    heapq.heappop(noteoffbuf)
                if isinstance(ev, NoteEvent):
                    dic = ev.__dict__.copy()
                    dic.pop('du', None)
                    offev = NoteOffEvent(ev.t + ev.L, ev.n, ev.nv,
                                         ev.tk, ev.ch, **dic)
                    if hasattr(ev, 'du'):
                        offev.dt = offev.get_dt() + ev.du - ev.L
                        _check_dt(offev)
                    heapq.heappush(noteoffbuf,
                                   (ev.t + ev.L, next(seqno), offev))
                    yield NoteOnEvent(ev.t, ev.n, ev.v, ev.tk, ev.ch, **dic)
                else:
                    yield ev
        except StopIteration as e:
            while noteoffbuf:
                yield noteoffbuf[0][2]
                heapq.heappop(noteoffbuf)
            return e.value

    def __call__(self, score):
        return score.mapstream(self._unpair_note_events)


class RetriggerNotes(Effector):
    """
    ノート衝突に対してリトリガー処理を施して衝突を回避します。
    ノート衝突とは、同じトラック、同じMIDIチャネルの同じピッチに対して、
    2つ以上の発音期間 (NoteEvent の t属性値から始まる L属性値の長さの期間
    もしくは NoteOnEvent から NoteOffEvent までの期間）が重なる状況を
    意味します。ノート衝突が起きた場合、シンセサイザーによっては発音時間が
    期待されるものより短くなってしまうことがあります。
    リトリガー処理では、先の音符の発音区間を適宜減らすことにより
    衝突を回避します。
    """
    def _retrigger_notes(self, stream):
        stream = stream.noteoff_inserted()
        outqueue = deque()  # deque of [lock, event]
        notedict = {}  # (tk, ch, n) => (NoteEvent_in_outqueue, count)

        def key(ev):
            return (ev.tk, ev.ch, ev.n)

        try:
            while True:
                while outqueue and not outqueue[0]:  # yield unlocked events
                    yield outqueue.popleft()[1]
                ev = next(stream)
                if isinstance(ev, NoteEvent) or isinstance(ev, NoteOnEvent):
                    (prev, count) = notedict.get(key(ev), (None, 0))
                    if count > 0:
                        if prev is None:  # NoteOnEvent の場合
                            noff = NoteOffEvent(ev.t, ev.n, tk=ev.tk, ch=ev.ch)
                            outqueue.append([False, noff])
                        else:  # NoteEvent の場合
                            prev[0] = False  # lockを外す
                            prev[1] = prev[1].copy().update(
                                L=ev.t - prev[1].t, nv=None)
                    if isinstance(ev, NoteOnEvent):
                        notedict[key(ev)] = (None, count + 1)
                        outqueue.append([False, ev])
                    else:
                        new = [True, ev]
                        notedict[key(ev)] = (new, count + 1)
                        outqueue.append(new)
                elif isinstance(ev, NoteOffEvent):
                    try:
                        (prev, count) = notedict[key(ev)]
                    except KeyError:
                        pass  # orphan note-off
                    else:
                        if count == 1:
                            if prev is None:  # NoteOnEvent の場合
                                if hasattr(ev, 'noteon'):
                                    delattr(ev, 'noteon')
                                outqueue.append([False, ev])
                            else:  # NoteEvent の場合
                                prev[0] = False  # lockを外す
                                prev[1] = prev[1].copy().update(
                                    L=ev.t - prev[1].t, nv=ev.nv)
                            del notedict[key(ev)]
                        else:
                            notedict[key(ev)] = (prev, count - 1)
                else:
                    outqueue.append([False, ev])
        except StopIteration as e:
            while outqueue:
                yield outqueue.popleft()[1]
            return e.value

    def __call__(self, score):
        return score.mapstream(self._retrigger_notes)


# Effectorとそのサブクラスを自動的に __all__ に含める
__all__.extend([name for name, value in globals().items()
               if name[0] != '_' and isinstance(value, type) and 
               issubclass(value, Effector)])
