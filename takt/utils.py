# coding:utf-8
import math
import random
import os
from fractions import Fraction
from typing import Union

# Copyright (C) 2023  Satoshi Nishimura

__all__ = ['takt_round', 'takt_roundx', 'int_preferred', 'std_time_repr',
           'frac_time_repr', 'TaktWarning', 'NoteDict', 'get_file_ext',
           'Ticks', 'Fraction']


Ticks = Union[int, float, Fraction]


def takt_round(x) -> int:
    """
    `x` を最も近い整数へ丸めます。2つ可能性があるときは大きい方になります。

    Args:
        x(float): 元の値

    Returns:
        結果の値
    """
    # Python's round() has differnt behavior in V2 and V3
    return int(math.floor(x + .5))


_ROUNDX_EPSILON = 1e-4


def takt_roundx(x, mode) -> int:
    """さまざまな丸めモードを持った整数への丸め関数

    Args:
        x(float): 元の値
        mode(str or function): 次のうちのいずれかによって丸めモードを表す。

            * 'nearestup': `x` に最も近い整数。
              2つ可能性があるときは大きい方。
            * 'nearestdown': `x` に最も近い整数。
              2つ可能性があるときは小さい方。
            * 'floor': `x` 以下の最大の整数。
            * 'ceil': `x` 以上の最小の整数。
            * 'down': (`x` + 10 :sup:`-4`) 以下の最大の整数
              (計算誤差を考慮した切り捨て)。
            * 'up': (`x` - 10 :sup:`-4`) 以上の最小の整数
              (計算誤差を考慮した切り上げ)。
            * 'random': 'up'と'down'が等確率でランダムに選ばれる。
            * 関数: `x` を引数としてその関数を呼ばれ、その戻り値が結果となる。

    Returns:
        結果の値
    """
    if mode == 'nearestup':
        return int(math.floor(x + .5))
    elif mode == 'nearestdown':
        return int(math.ceil(x - .5))
    elif mode == 'down':
        return int(math.floor(x + _ROUNDX_EPSILON))
    elif mode == 'up':
        return int(math.ceil(x - _ROUNDX_EPSILON))
    elif mode == 'floor':
        return int(math.floor(x))
    elif mode == 'ceil':
        return int(math.ceil(x))
    elif mode == 'random':
        return random.choice((takt_roundx(x, 'up'), takt_roundx(x, 'down')))
    elif callable(mode):
        return mode(x)
    else:
        raise ValueError('%r: Unrecognized rounding mode' % (mode,))


def int_preferred(x) -> Union[int, float, Fraction]:
    """
    `x` が整数値を持つ場合はint型に変換して、そうでなければ元のまま返します。

    Args:
        x(int, float, or Fraction): 元の値

    Returns:
        結果の値
    """
    try:
        return int(x) if int(x) == x else x
    except (OverflowError, ValueError):
        return x


def std_time_repr(time) -> str:
    """
    `time` を小数点以下5桁以内で表した文字列へ変換します。

    この関数は、Event や EventList を str 関数で文字列に変換する際に、
    時間に対して使われています。

    Args:
        time(ticks): 値
    """
    if isinstance(time, Fraction):
        time = float(time)
    return repr(round(time, 5))


def frac_time_repr(time) -> str:
    """
    `time` を分数表記を使ってできるだけ正確かつコンパクトな文字列に変換
    します。repr関数と異なり 1e-8 程度の変換誤差を含む場合があります。

    この関数は :func:`.showtext` において、rawモードでないときのデフォルトの
    時間→文字列変換関数になっています。

    Args:
        time(ticks): 値
    """
    if int(time) == time:
        return repr(int(time))
    elif round(time, 5) == time:
        return repr(time)
    else:
        ratio = Fraction(time).limit_denominator(99)
#        if ('%.9e' % ratio) == ('%.9e' % time):
        if abs(ratio - time) < 1e-8:
            # 99.99999999999999のときのように分母が1になることがある。
            return '%d' % ratio.numerator if ratio.denominator == 1 else \
                '%d+%d/%d' % (ratio.numerator // ratio.denominator,
                              ratio.numerator % ratio.denominator,
                              ratio.denominator)
        else:
            return repr(time)


class TaktWarning(UserWarning):
    pass


class NoteDict:
    """
    イベント間 (典型的には NoteOnEvent と NoteOffEvent) の対応を見つけるため
    の辞書。
    デフォルトでは (トラック番号, チャネル番号, ノート番号) をキーとして
    同じキーを持つイベントを探します。通常の dict と異なり、同じキーに対して
    複数の要素を許しています。
    """
    def __init__(self):
        self.notedict = {}  # dict of list

    def __repr__(self):
        return f"<NoteDict notedict={self.notedict!r}>"

    def __bool__(self):
        return bool(self.notedict)

    def clear(self):
        self.notedict.clear()

    def copy(self):
        result = NoteDict()
        result.notedict = {k: lst.copy() for (k, lst) in self.notedict.items()}
        return result

    def push(self, key, value):
        self.notedict.setdefault(key, []).append(value)

    def pushuniq(self, key, value):
        self.notedict[key] = (value,)

    def pushnote(self, ev, value):  # evは典型的にはNoteOnEvent
        self.push((ev.tk, ev.ch, ev.n), value)

    __default = object()

    def pop(self, key, default=__default):
        try:
            lst = self.notedict[key]
        except KeyError:
            if default is self.__default:
                raise
            return default
        value = lst.pop(0)  # use FIFO heuristic
        if not lst:
            del self.notedict[key]
        return value

    def popuniq(self, key, default=__default):
        if default is self.__default:
            return self.notedict.pop(key)[0]
        else:
            return self.notedict.pop(key, (default,))[0]

    def popnote(self, ev, default=__default):  # evは典型的にはNoteOffEvent
        return self.pop((ev.tk, ev.ch, ev.n), default)

    def items(self):
        return ((k, v) for (k, lst) in self.notedict.items() for v in lst)

    def keys(self):
        return (k for (k, lst) in self.notedict.items() for v in lst)

    def values(self):
        return (v for lst in self.notedict.values() for v in lst)

    def uniquekeys(self):
        return self.notedict.keys()

    def popitem(self):
        # dict.popitemと異なりFIFOの順序で取り出す
        if not self.notedict:
            raise KeyError('popitem(): notedict is empty')
        else:
            k, lst = next(iter(self.notedict.items()))
            if len(lst) == 1:
                del self.notedict[k]
                return k, lst[0]
            else:
                return k, lst.pop(0)


def get_file_ext(path, types=('smf', 'json', 'mxl')) -> str:
    """
    `path` で与えられたパス名に含まれる拡張子を調べて、
    標準MIDIファイル、jsonファイル、MusicXMLファイルのうちのどれであるかを
    判別します。どれにも該当しなければ例外を送出します。

    Args:
        path(str): ファイルのパス名
        types(tuple of str): 受け入れ可能なファイル形式

    Returns:
        str: 標準MIDIファイルなら 'smf', jsonファイルなら 'json',
        MusicXMLファイルなら 'mxl'
    """
    _, ext = os.path.splitext(path)
    ext = ext.lower()
    extdict = {}
    for typ in types:
        elist = ('.mid', '.midi', '.smf') if typ == 'smf' else \
                ('.json',) if typ == 'json' else \
                ('.mxl', '.musicxml', '.xml') if typ == 'mxl' \
                else ()
        for x in elist:
            extdict[x] = typ
    try:
        return extdict[ext]
    except KeyError:
        raise Exception("Only the following file types supported: "
                        + ' '.join(extdict))
