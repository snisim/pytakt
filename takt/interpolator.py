# coding:utf-8
"""
このモジュールには、折れ線や区分3次曲線に沿って
値を補間するためのクラスが定義されています。
"""
# Copyright (C) 2023  Satoshi Nishimura

import numbers
from bisect import bisect_right
from typing import Iterator, Tuple
from takt.utils import Ticks

__all__ = ['Point', 'Interpolator']


class Point(object):
    """
    補間の基準となる制御点を表すクラスです。各制御点は、時刻と値、および
    傾きに関する情報を持ちます。このモジュールの補間法では、補間された
    直線/曲線は必ず制御点を通ります。

    Args:
        t(int, float or None): 制御点の時刻。Noneの場合は、前後の制御点の
            時刻から等分分割によってこの制御点の時刻を決定することを
            意味します。
        value(int or float): 制御点での値。
        slope(int, float, None, or 2-tuple): 制御点での傾きを、折れ線の場合に
            対する相対倍率で指定します。従って、すべての傾きが1である
            場合は、折れ線による補間となります（デフォルト）。
            区間の始点と終点の傾きの少なくとも一方が1以外の実数の場合、
            その区間は3次曲線による補間となります。
            `slope` に 'free' という文字列を指定すると、前後の制御点の情報
            から、滑らかに接続できるように傾きが自動計算されます。
            `slope` は 2-tuple でも良く、その場合は左と右の傾き値を個別に
            指定します。左の傾きが None である場合は、補間せずに階段状に
            値を変えることを意味します。`slope=None` は
            `slope=(None, 1)` と等価です。
    """
    def __init__(self, t, value, slope=1):
        if not (isinstance(slope, numbers.Real) or
                (slope is None) or (slope == 'free') or
                (isinstance(slope, tuple) and len(slope) == 2 and
                 (isinstance(slope[0], numbers.Real) or (slope[0] is None))
                 and isinstance(slope[1], numbers.Real))):
            raise Exception("bad slope value %r" % (slope,))
        (self.t, self.value, self.slope) = (t, value, slope)

    def __repr__(self):
        return "Point(t=%r, value=%r, slope=%r%s%s)" % \
            (self.t, self.value, self.slope,
             (', lderiv=%r' % self.lderiv) if hasattr(self, 'lderiv') else '',
             (', rderiv=%r' % self.rderiv) if hasattr(self, 'rderiv') else '')

    def __eq__(self, other):
        if not isinstance(other, Point):
            return NotImplemented
        return self.__dict__ == other.__dict__

    def _lslope(self):
        return self.slope[0] if isinstance(self.slope, tuple) else self.slope

    def _rslope(self):
        return (self.slope[1] if isinstance(self.slope, tuple)
                else 1 if self.slope is None else self.slope)


class Interpolator(object):
    """
    値を補間するためのオブジェクトを表すクラスです。
    制御点のリストを与えてこのオブジェクト `f` を生成すると、
    `f(時刻)` のように呼び出して補間された値を取得できるようになります。
    最初の制御点の時刻以前は最初の制御点の値、
    最後の制御点の時刻以後は最後の制御点の値になります。

    Args:
        points(list of Point, etc.): 制御点の list (長さ1以上) です。
            制御点は時刻順に並んでいる必要があります。
            同一時刻に2つの制御点を指定することは可能で、のこぎり波状の
            変化の場合に利用できます。各制御点は :class:`Point` インスタンス
            の他、次の省略形が使えます。

            * value -- Point(None, value) と等価。
            * (t, value) -- Point(t, value) と等価。
            * [value, slope] -- Point(None, value, slope) と等価。
            * (t, value, slope) -- Point(t, value, slope) と等価。

            最初の制御点の時刻が None である場合は、0とみなされます。
            最後の制御点の時刻に対して None は指定できません。
            `slope` に 'free' を指定できるのは、最初と最後以外の制御点のみ
            です。

    Examples:
        ``Interpolator([0, (480, 100)])``
            時刻0で0、時刻480で100となるように線形補間する関数を表します。

        ``Interpolator([0, 100, (960, 50)])``
            時刻0で0、時刻480で100, 時刻960で50となるような折れ線に沿って
            変化する関数を表します。

        ``Interpolator([0, [100, None], (960, 50, None)])``
            時刻0で0、時刻480で100, 時刻960で50と階段状に変化する関数を
            表します。

        ``Interpolator([0, [100, 'free'], (960, 50)])``
            時刻0で0、時刻480で100, 時刻960で50と滑らかに変化する
            区分3次曲線を表します。

        ``Interpolator([(0, 100, 3.0), (480, 0, 0.0)])``
            時刻0は値が100で傾きは2点をつなぐ直線の3倍、時刻480は値が0で
            傾きは0となるような3次曲線（この場合、指数的な減衰に似た曲線）を
            表します。

        ``Interpolator([(0, 100, 0), (240, 0, 0) (480, 100, 0)])``
            100 -> 0 -> 100 と cos関数のように滑らかに変化する
            区分3次曲線を表します。

    """
    def __init__(self, points):
        if not isinstance(points, list):
            raise TypeError("'points' must be a list")
        if not points:
            raise ValueError("'points' must not be an empty list")
        self.plist = list(self._point_iterator(points))
        self.tlist = [p.t for p in self.plist]

    def maxtime(self) -> Ticks:
        """ 最後の制御点の時刻を返します。"""
        return self.tlist[-1]

    def _point_iterator(self, points):
        points_iter = iter(points)
        done = False
        count = 0
        pending_points = []  # 内分点やslope-freeの点を溜める
        while not done:
            try:
                while True:
                    p = next(points_iter)
                    if isinstance(p, Point):
                        p = Point(p.t, p.value, p.slope)
                    elif isinstance(p, numbers.Real):
                        p = Point(None, p)
                    elif isinstance(p, tuple) and len(p) in [2, 3]:
                        p = Point(*p)
                    elif isinstance(p, list) and len(p) == 2:
                        p = Point(None, *p)
                    else:
                        raise TypeError("%r is not a valid form of a value"
                                        % (p,))
                    if p.t is None and count == 0:
                        p.t = 0
                    if p.slope == 'free' and count == 0:
                        raise Exception("slope cannot be 'free' at endpoints")
                    pending_points.append(p)
                    count += 1
                    if count > 1 and p.t is not None and p.slope != 'free':
                        break
            except StopIteration:
                if count > 0:
                    if pending_points[-1].t is None:
                        raise Exception("t must be given for the last point")
                    if pending_points[-1].slope == 'free':
                        raise Exception("slope cannot be 'free' at endpoints")
                done = True

            internal_point_count = 0
            for i, p in enumerate(pending_points):
                if p.t is None:
                    internal_point_count += 1
                elif i > 0:
                    t1 = pending_points[i - internal_point_count - 1].t
                    if p.t < t1:
                        raise Exception("t must be non-decreasing\n%r" % p)
                    for j in range(internal_point_count):
                        pending_points[i - internal_point_count + j].t = (
                            (p.t - t1) * (j + 1) /
                            (internal_point_count + 1) + t1)
                    internal_point_count = 0

            self._calc_derivatives(pending_points)
            for p in pending_points[:-1]:
                yield p
            del pending_points[:-1]  # 最後の点だけ残す
        if count > 0:
            yield pending_points[0]

    def _fritsch_butland(self, points):
        # Reference: F. N. Fritsch and J. Butland, "A method for
        # constructing local monotone piecewise cubic interpolants", 1984
        for j in range(1, len(points) - 1):
            m1, m2 = points[j].m, points[j+1].m
            if m1 * m2 <= 0:
                points[j].lderiv = points[j].rderiv = 0
            else:
                h1 = points[j].t - points[j-1].t
                h2 = points[j+1].t - points[j].t
                a = (h1 + h2 * 2) / ((h1 + h2) * 3)
                points[j].lderiv = points[j].rderiv = (
                    m1 / (a * m2 + (1-a) * m1) * m2)
        return points

    def _calc_derivatives(self, points):
        spline_point_count = 0
        for i, p in enumerate(points):
            if i > 0:
                pp = points[i-1]
                if p.t == pp.t:
                    m = 0
                else:
                    m = (p.value - pp.value) / (p.t - pp.t)
                p.lderiv = p._lslope()
                if isinstance(p.lderiv, numbers.Real):
                    p.lderiv *= m
                pp.rderiv = pp._rslope()
                if isinstance(pp.rderiv, numbers.Real):
                    pp.rderiv *= m
                p.m = m

            if p.slope == 'free':
                spline_point_count += 1
            elif spline_point_count > 0:
                k = i - spline_point_count - 1
                points[k:i+1] = self._fritsch_butland(points[k:i+1])
                spline_point_count = 0

    def __call__(self, t) -> float:
        i = bisect_right(self.tlist, t)
        if i == 0:
            return self.plist[0].value
        elif i == len(self.plist):
            return self.plist[-1].value
        elif self.plist[i]._lslope() is None:
            return self.plist[i-1].value
        elif self.plist[i]._lslope() == 1 and self.plist[i-1]._rslope() == 1:
            # elseにある3次補間でも計算できるが、下の式の方が精度的に有利。
            return ((t - self.plist[i-1].t) * self.plist[i].m
                    + self.plist[i-1].value)
        else:
            h = self.plist[i].t - self.plist[i-1].t
            m = self.plist[i].m
            p2 = 3 * m - self.plist[i].lderiv - 2 * self.plist[i-1].rderiv
            p3 = self.plist[i].lderiv + self.plist[i-1].rderiv - 2 * m
            a = t - self.plist[i-1].t
            b = a / h
            return (((p3 * b + p2) * b + self.plist[i-1].rderiv) * a
                    + self.plist[i-1].value)

    def iterator(self, tstep, ystep=-1) -> Iterator[Tuple[Ticks, float]]:
        """
        補間された直線・曲線に沿って時刻と値の組 (t, value) を順に yield
        するジェネレータ関数です。時刻の範囲は、最初の制御点の時刻から
        最後の制御点の時刻までです。

        Args:
            tstep(ticks): 時間の刻み値を指定します。
                制御点の存在する時刻を基準にしてそこからこの時間間隔で順に
                出力されます。制御点の存在する時刻では、この値によらず、
                必ず出力されます。
            ystep(int or float, optional): 指定した場合、
                直前に出力した値と比べ変化の絶対値が `ystep` 以下の場合に
                出力が省かれます(ただし、制御点の存在する時刻では、それに
                かかわらず出力されます）。
        """
        t = 0
        for i in range(len(self.tlist)):
            prev_v = None
            if i > 0:
                while t < self.tlist[i]:
                    v = self(t)
                    if prev_v is None or abs(prev_v - v) > ystep:
                        yield (t, v)
                        prev_v = v
                    t += tstep
            t = self.tlist[i]
        if len(self.tlist) > 0:
            yield (t, self(t))


# import matplotlib.pyplot as plt
# e = Interpolator([0, (50,100), (50,0), (75,80,None), (100,100,2)])
# print(list(e.iterator(10, 20.0)))
# plt.plot([e(t) for t in range(100)])
# plt.show()
