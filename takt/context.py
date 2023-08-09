# coding:utf-8
"""
このモジュールには、Contextクラスおよびそれに関連した関数が定義されています。
"""
# Copyright (C) 2023  Satoshi Nishimura

import numbers
import os
from typing import List, Tuple, Any
from takt.utils import int_preferred
from takt.constants import L4

__all__ = ['Context', 'context', 'newcontext']


class Context(object):
    """ Context クラスのオブジェクト (コンテキスト) は、ps モジュールで
    定義されている関数および mml() 関数によって参照されるパラメータ情報を
    集めたものです。

    コンテキストは with 構文によって、切り替えることができます。例えば::

        mycontext = Context(ch=2, v=50)
        with mycontext:
            ...

    とすると、with の中では mycontext が有効になり、with を抜けると元の
    コンテキストに戻ります。

    コンテキストが持っている属性の値は ``mycontext.ch=3`` のようにして変更でき
    ますが、新しい属性を追加するには addattr() メソッドを使う必要があります。

    ps モジュールで定義されている関数および mml() 関数は、
    Context クラスのメソッドとしても使用でき、コンテキストを指定した
    スコア生成が可能です
    (例: ``mycontext.note(C4)``、``mycontext.mml('CDE')`` など)。

    Attributes:
        dt (ticks): 生成されるイベントの dt 属性の値 (楽譜上の時刻と
            演奏上の時刻との差) を指定します。この値が 0 のときは、一般に
            dt属性は付加されません。
        tk (int): 生成されるイベントの tk 属性の値 (トラック番号)
            を指定します。
        ch (int): 生成されるイベントの ch 属性の値 (MIDIチャネル番号)
            を指定します。
        v (int): 生成される NoteEvent の v 属性の値 (ベロシティ) を指定
            します。
        nv (int or None): 生成される NoteEvent の nv 属性の値 (ノートオフ
            ベロシティ) を指定します。
        L (ticks): 生成される NoteEvent の L 属性の値を指定します。
            これは楽譜上の音価をティック単位で表したものに相当します。
            また、rest() 関数における休符の長さ指定にも使われます。
        duoffset(ticks or function): 演奏時音長 (ノートオンとノートオフ
            の時間差) のオフセット値、もしくは L 属性の値からその値を得る
            関数を保持します。
            下の durate とともに、演奏時音長を決めるのに使われます。
        durate(int or float): 演奏時音長に対する加算値を音価に対する百分率で
            指定します。演奏時音長は、上の duoffsetとともに、下式によって
            決定されます。

                演奏時音長 = duoffset + L * durate / 100 　\
(duoffset が int/float のとき)

                演奏時音長 = duoffset(L) + L * durate / 100 　\
(duoffset が関数のとき)

            演奏時音長が負の場合は 0 に修正されます。

            note() 関数は、上の演奏時音長を NoteEvent の du 属性に設定します
            （ただし、L属性値と同じ値の場合は省略されます）。
        o (int):  オクターブを表す整数(4が中央ハから始まるオクターブ)。
            これは mml() 関数でのみ使用されます。
        key (Key, int, or str): 自動的にシャープやフラットをつけるための調
            を :class:`.Key` クラスのオブジェクト、もしくは
            Key()コンストラクタの第1引数で指定します。
            これは mml() 関数でのみ使用されます。
        effectors (list of callable objects): スコア変換を行う呼び出し可能
            オブジェクトのリストです。psモジュールの関数や mml() 関数の
            戻り値に対して、このリストに含まれる関数が変換前のスコアを引数
            として先頭から順に適用されます。

    .. rubric:: 疑似属性

    演奏時音長 (表情づけされた音長、いわゆるゲートタイム) の指定を容易にする
    ため、下の2つの疑似属性が提供されています。
    これらは通常のインスタンス属性と同じように値の読み出しや書き込みを行え
    ますが、属性として登録はされていません。

    **du**
        演奏時音長を表しています。
        読み出すと演奏時音長 (上の durate の項を式を参照) が得られます。
        値xを書き込むと、xを duoffset にセットするのと同時に、durate を
        0 (ただし、xが負の場合は 100) にセットします。

        使用例:
            ``note(C4, du=120)`` : 音価(L属性値)にかかわらず演奏時音長を\
120ティックに固定します。

            ``note(C4, du=-30)`` : 演奏時音長をL属性値より30ティック少ない値\
に設定し、音符間のギャップを30ティックに保ちます。

        Type:: ticks

    **dr**
        演奏時音長の音価に対する百分率を表しています。
        読み出すと durate 属性の値が得られます。
        値を書き込むと、その値を durate にセットするのと同時に、duoffset を
        0 に設定します。

        使用例:
            ``note(C4, dr=50)`` : 演奏時音長を音価の50%に設定します (いわゆる\
スタッカート演奏に相当します)。

        Type:: int or float

    Args:
        dt, L, v, nv, duoffset, durate, tk, ch, o, key, effectors:
            同名の属性値を指定します。
        kwargs: コンテキストに対する追加の属性を指定します。
    """
    __slots__ = ('dt', 'tk', 'ch', 'v', 'nv', 'L', 'duoffset', 'durate',
                 'o', 'key', 'effectors', '_outer_context', '__dict__')
    _current_context = None
    _newtrack_count = 1

    def __init__(self, dt=0, L=L4, v=80, nv=None, duoffset=0, durate=100,
                 tk=1, ch=1, o=4, key=0, effectors=[], **kwargs):
        self.dt = dt
        self.L = L
        self.v = v
        self.nv = nv
        self.duoffset = duoffset
        self.durate = durate
        self.tk = tk
        self.ch = ch
        self.o = o
        self.key = key
        self.effectors = effectors
        self._outer_context = None
        self.__dict__.update(kwargs)

    def copy(self) -> 'Context':
        """
        複製されたコンテキストを返します。effectors 属性値についてはリスト
        の複製が行われます。それ以外の属性については浅いコピーとなります。
        """
        return self.__class__(self.dt, self.L, self.v, self.nv,
                              self.duoffset, self.durate, self.tk, self.ch,
                              self.o, self.key,
                              self.effectors.copy(), **self.__dict__)
    __copy__ = copy

    def __getattr__(self, name):
        if name == 'du':
            duo = self.duoffset if isinstance(self.duoffset, numbers.Real) \
                  else self.duoffset(self.L)
            return int_preferred(max(0, duo + self.L * self.durate / 100))
        elif name == 'dr':
            return self.durate
        else:
            return object.__getattribute__(self, name)

    def __setattr__(self, name, value):
        if name in self.__slots__ or name in self.__dict__:
            object.__setattr__(self, name, value)
        elif name == 'du':
            self.duoffset = value
            self.durate = (100 if isinstance(value, numbers.Real) and value < 0
                           else 0)
        elif name == 'dr':
            self.duoffset = 0
            self.durate = value
        else:
            raise AttributeError(
                'No such attribute %r. Use addattr() to add a new attribute.'
                % name)

    def addattr(self, name, value=None) -> None:
        """
        コンテキストに新たな属性を追加します。

        Args:
            name(str): 属性の名前
            value(any): 属性の初期値
        """
        object.__setattr__(self, name, value)

    def has_attribute(self, name) -> bool:
        """
        `name` がコンテキストの属性であれば真を返します。メソッド名は対象に
        しない点において、hasattr(self, name) とは異なります。

        Args:
            name(str): 属性の名前
        """
        return name in (*self.__slots__, 'du', 'dr', *self.__dict__)

    def reset(self) -> None:
        """
        すべての属性値を初期値 (デフォルトのコンストラクタ引数値) へ
        戻します。
        """
        self.__dict__.clear()
        self.__init__()

    def keys(self) -> List[str]:
        """
        属性名のリストを返します。
        """
        attrs = []
        attrs += self.__slots__
        attrs.remove('__dict__')
        attrs.remove('_outer_context')
        attrs += self.__dict__
        return attrs

    def items(self) -> List[Tuple[str, Any]]:
        """
        属性名とその値の組のリストを返します。
        """
        return [(key, getattr(self, key)) for key in self.keys()]

    def update(self, **kwargs) -> 'Context':
        """
        `kwargs` の代入記述に従って属性値を変更します。

        Returns:
            self
        """
        for k, v in kwargs.items():
            setattr(self, k, v)
        return self

    def __repr__(self):
        attrs = ["%s=%r" % (k, getattr(self, k)) for k in self.keys()]
        return "<Context: " + str.join(" ", attrs) + ">"

    @staticmethod
    def _push(ctxt):
        ctxt._outer_context = Context._current_context
        Context._current_context = ctxt

    @staticmethod
    def _pop():
        if Context._current_context._outer_context is None:
            raise RuntimeError("pop on empty context stack")
        Context._current_context = Context._current_context._outer_context

    # example:
    #  with newcontext(ch=2): note(C4)
    def __enter__(self):
        Context._push(self)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        Context._pop()

    def do(self, func, *args, **kwargs) -> Any:
        """ このコンテキストにおいて関数 `func` を実行し、その戻り値を
        返します。

        Args:
            args, kwargs: `func` へ渡す引数。

        Examples:
            ``somecontext.do(lambda: note(C4) + note(D4))``
        """
        with self:
            return func(*args, **kwargs)

    def attach(self, func) -> 'Context':
        """
        effectors属性が持つリストの先頭にスコア変換関数 `func` を挿入します。

        Returns:
            self

        Examples:
            >>> horn_in_F = newcontext().attach(Transpose(-Interval('P5')))
            >>> horn_in_F.note(C4)
            EventList(duration=480, events=[
                NoteEvent(t=0, n=F3, L=480, v=80, nv=None, tk=1, ch=1)])
        """
        self.effectors.insert(0, func)
        return self

    def detach(self) -> 'Context':
        """
        effectors属性が持つリストの先頭要素を削除します。

        Returns:
            self
        """
        self.effectors.pop(0)
        return self


Context._current_context = Context()


# 理想を言えば context をグローバル変数としたいが、python では import
# するときにグローバル変数のコピーが行われるので、モジュール内から global文で
# もって書き換えることができない。

def context() -> Context:
    """
    現在有効になっているコンテキストを返します。
    """
    return Context._current_context


# 上の context() の定義だと、 'context().attr = value' を誤って、
# 'context.attr = value' と書いたときにエラーにならないので、
# 下の定義に変更している (autodocのために元のも残してある)。
class _context_function(object):
    __slots__ = ()

    def __call__(self) -> Context:
        return Context._current_context


if '__SPHINX_AUTODOC__' not in os.environ:
    context = _context_function()


def newcontext(**kwargs) -> Context:
    """
    現在有効になっているコンテキストをコピーし、`kwargs` の代入記述に従って
    属性値を変更したものを返します。``context().copy().update(**kwargs)`` と
    等価です。
    """
    ctxt = Context._current_context.copy()
    ctxt.update(**kwargs)
    return ctxt


# def newtrack(**kwargs):
#     ctxt = newcontext(**kwargs)
#     ctxt.tk = Context._newtrack_count
#     Context._newtrack_count += 1
#     return ctxt


# def withcontext(ctxt, func):
#     with ctxt:
#         return func()
