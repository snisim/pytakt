# coding:utf-8
"""
This module defines the Context class and its associated functions.
"""
"""
このモジュールには、Contextクラスおよびそれに関連した関数が定義されています。
"""
# Copyright (C) 2025  Satoshi Nishimura

import numbers
import os
import threading
from typing import List, Tuple, Any
from pytakt.utils import int_preferred
from pytakt.constants import L4

__all__ = ['Context', 'context', 'newcontext']


thread_local = threading.local()


class Context(object):
    """
    The Context class object (context) is a collection of parameters that
    are referenced by functions defined in the sc module as well as the mml()
    function.

    Contexts can be switched by using the 'with' syntax. For example::

        mycontext = Context(ch=2, v=50)
        with mycontext:
            ...

    will activate mycontext within the 'with' block, and return to the
    original context upon exiting the block.

    It is possible to change the value of the context's attribute by
    ``mycontext.ch=3`` for example, but you must use the addattr() method
    to add a new attribute.

    The functions defined in the sc module and the mml() function can also
    be used as methods of the Context class, allowing context-specific score
    generation (e.g. ``mycontext.note(C4)``, ``mycontext.mml('CDE')``, etc.).

    To ensure safe use in multi-threaded environments, the currently active
    context is managed separately for each thread. When a new thread is
    created, its context is always the default context (the context obtained
    by Context()).

    Attributes:
        dt (ticks): Specifies the value of the dt attribute (difference
            between the notated time and played time) of generated events.
        tk (int): Specifies the value of the tk attribute (track number) of
            generated events.
        ch (int): Specifies the value of the ch attribute (MIDI channel
            number) of generated events.
        v (int): Specifies the value of the v attribute (velocity) of
            generated NoteEvent events.
        nv (int or None): Specifies the value of the nv attribute (note-off
            velocity) of generated NoteEvent events.
        L (ticks): Specifies the value of the L attribute of generated
            NoteEvent events.
            This corresponds to the note value in ticks in the score.
            It is also used to specify the length of rests in the rest()
            function.
        duoffset(ticks or function): Holds the offset value of the playing
            duration of the note (the difference between note-on and note-off
            times in the performance, aka. gate time).
            Optionally, a function to get that value from the value of
            the L attribute can be specified.
            Together with **durate** below, it is used to determine
            the playing duration of a note.
        durate(int or float): The value added to the playing duration
            as a percentage of the note value. The playing duration is
            determined by the following equation together with the
            **duoffset** above.

                note duration at play = **duoffset** + **L** * **durate** \
/ 100 (when **duoffset** is an int/float)

                note duration at play = **duoffset(L)** + **L** * **durate** \
/ 100 (when **duoffset** is a function)

            If the note duration at play is negative, it is corrected to 0.

            The note() function sets the above value to the du attribute of
            NoteEvent (or omitted if the value is the same as the L attribute
            value).
        o (int): An integer representing the octave (4 being the octave
            starting from the middle C).
            This is used only by the mml() function.
        key (Key, int, or str): Specifies the key for automatic sharpening or
            flattening. It can be a :class:`.Key` object or
            the first argument of the Key() constructor.
            This is only used by the mml() function.
        effectors (list of callable objects): A list of callable objects
            for score conversion; callables (typically Effector instances)
            in this list are applied to the return value of the mml()
            function or that of the functions in the sc module, in sequence
            from the first element of the list to the last.

    .. rubric:: Pseudo-attributes

    In order to facilitate the specification of the playing duration of notes,
    the following two pseudo-attributes are provided.
    These can be read and written in the same way as normal instance
    attributes, but they are not registered as attributes.

    **du**
        Represents the note duration at play.
        Reading **du** yields the note duration at play (see the expression
        shown in the **durate** item above).
        Writing a value `x` to **du** sets **duoffset** to `x` and
        simultaneously sets **durate** to 0 (or 100 if `x` is negative).

        Examples:
            ``note(C4, du=120)``: Fixes the note duration at play to 120 ticks.

            ``note(C4, du=-30)``: sets the playing duration to 30 ticks less
            than the L attribute value and thus keeps the gap between notes
            to 30 ticks.

        Type:: ticks

    **dr**
        Represents the percentage of the duration at play to the note value.
        Reading **dr** yields the value of the **durate** attribute.
        Writing a value to **dr** sets **durate** to that value and
        simultaneously sets **duoffset** to 0.

        Examples:
            ``note(C4, dr=50)`` : sets the playing duration to 50% of
            the note value (simulating so-called "staccato" playing).

        Type:: int or float

    Args:
        dt, L, v, nv, duoffset, durate, tk, ch, o, key:
            Specifies attribute values of the same name.
        effectors:
            Specifies the value of the 'effectors' attribute.
            A copy of the list is assigned to the attribute.
        kwargs: specifies additional attributes for the context.
    """
    """ Context クラスのオブジェクト (コンテキスト) は、sc モジュールで
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

    sc モジュールで定義されている関数および mml() 関数は、
    Context クラスのメソッドとしても使用でき、コンテキストを指定した
    スコア生成が可能です
    (例: ``mycontext.note(C4)``、``mycontext.mml('CDE')`` など)。

    マルチスレッド環境でも安全に使用できるように、現在有効なコンテキストは
    スレッドごと別々に管理されています。新しいスレッドが生成されたとき、
    そのスレッドのコンテキストは常にデフォルトコンテキスト (Context() で
    得られるコンテキスト) になります。

    Attributes:
        dt (ticks): 生成されるイベントの dt 属性の値 (楽譜上の時刻と
            演奏上の時刻との差) を指定します。
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
            の時間差、いわゆるゲートタイム) のオフセット値、もしくは L 属性
            の値からその値を得る関数を保持します。
            下の durate とともに、演奏時音長を決めるのに使われます。
        durate(int or float): 演奏時音長に対する加算値を音価に対する百分率で
            指定します。演奏時音長は、上の duoffsetとともに、下式によって
            決定されます。

                演奏時音長 = duoffset + L * durate / 100 　\
(duoffset が int/float のとき)

                演奏時音長 = duoffset(L) + L * durate / 100 　\
(duoffset が関数のとき)

            演奏時音長が負の場合は 0 に修正されます。

            note() 関数は、上の演奏時音長を NoteEvent の du 属性に設定します。
            （ただし、L属性値と同じ値の場合は省略されます）。
        o (int):  オクターブを表す整数(4が中央ハから始まるオクターブ)。
            これは mml() 関数でのみ使用されます。
        key (Key, int, or str): 自動的にシャープやフラットをつけるための調
            を :class:`.Key` クラスのオブジェクト、もしくは
            Key()コンストラクタの第1引数を指定します。
            これは mml() 関数でのみ使用されます。
        effectors (list of callable objects): スコア変換を行う呼び出し可能
            オブジェクトのリストです。scモジュールの関数や mml() 関数の
            戻り値に対して、このリストに含まれる呼び出し可能オブジェクト
            （典型的にはEffectorインスタンス）が先頭から順に適用されます。

    .. rubric:: 疑似属性

    各音符に対する演奏時音長の指定を容易にするため、下の2つの疑似属性が
    提供されています。
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
        dt, L, v, nv, duoffset, durate, tk, ch, o, key:
            同名の属性値を指定します。
        effectors: effector属性の値を指定します。
            属性にはリストのコピーが格納されます。
        kwargs: コンテキストに対する追加の属性を指定します。
    """
    __slots__ = ('dt', 'tk', 'ch', 'v', 'nv', 'L', 'duoffset', 'durate',
                 'o', 'key', 'effectors', '_outer_context', '__dict__')
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
        self.effectors = effectors.copy()
        self._outer_context = None
        self.__dict__.update(kwargs)

    def copy(self) -> 'Context':
        """
        Returns a duplicated context. For the 'effectors' attribute value,
        the list is duplicated. For other attributes, a shallow copy is made.
        """
        """
        複製されたコンテキストを返します。effectors 属性値についてはリスト
        の複製が行われます。それ以外の属性については浅いコピーとなります。
        """
        return self.__class__(self.dt, self.L, self.v, self.nv,
                              self.duoffset, self.durate, self.tk, self.ch,
                              self.o, self.key,
                              self.effectors, **self.__dict__)
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
        Adds a new attribute to the context.

        Args:
            name(str): name of the attribute
            value(any): initial value of the attribute
        """
        """
        コンテキストに新たな属性を追加します。

        Args:
            name(str): 属性の名前
            value(any): 属性の初期値
        """
        object.__setattr__(self, name, value)

    def has_attribute(self, name) -> bool:
        """
        Returns true if `name` is an attribute of the context.
        Differs from hasattr(self, name) in that it does not target
        method names.

        Args:
            name(str): name of the attribute
        """
        """
        `name` がコンテキストの属性であれば真を返します。メソッド名は対象に
        しない点において、hasattr(self, name) とは異なります。

        Args:
            name(str): 属性の名前
        """
        return name in (*self.__slots__, 'du', 'dr', *self.__dict__)

    def reset(self) -> None:
        """
        Returns all the attribute values to their initial values
        (i.e., default constructor argument values).
        """
        """
        すべての属性値を初期値 (デフォルトのコンストラクタ引数値) へ
        戻します。
        """
        self.__dict__.clear()
        self.__init__()

    def keys(self) -> List[str]:
        """
        Returns a list of attribute names.
        """
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
        Returns a list of attribute name/value pairs.
        """
        """
        属性名とその値の組のリストを返します。
        """
        return [(key, getattr(self, key)) for key in self.keys()]

    def update(self, **kwargs) -> 'Context':
        """
        Change attribute values according to the assignment description
        in `kwargs`.

        Returns:
            self
        """
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
        ctxt._outer_context = context()
        thread_local.current_context = ctxt

    @staticmethod
    def _pop():
        ctxt = context()
        if ctxt._outer_context is None:
            raise RuntimeError("pop on empty context stack")
        thread_local.current_context = ctxt._outer_context

    # example:
    #  with newcontext(ch=2): note(C4)
    def __enter__(self):
        Context._push(self)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        Context._pop()

    def do(self, func, *args, **kwargs) -> Any:
        """ Execute the function `func` in this context and return
        its return value.

        Args:
            args, kwargs: arguments passed to `func`.

        Examples:
            ``somecontext.do(lambda: note(C4) + note(D4))``
        """
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
        Inserts the score conversion function `func` at the beginning of
        the list in the 'effectors' attribute.

        Returns:
            self

        Examples:
            >>> horn_in_F = newcontext().attach(Transpose(-Interval('P5')))
            >>> horn_in_F.note(C4)
            EventList(duration=480, events=[
                NoteEvent(t=0, n=F3, L=480, v=80, nv=None, tk=1, ch=1)])
        """
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
        Deletes the first element of the list in the 'effectors' attribute.

        Returns:
            self
        """
        """
        effectors属性が持つリストの先頭要素を削除します。

        Returns:
            self
        """
        self.effectors.pop(0)
        return self


# 理想を言えば context をグローバル変数としたいが、python では import
# するときにグローバル変数のコピーが行われるので、モジュール内から global文で
# もって書き換えることができない。

def context() -> Context:
    """
    Returns the currently active context.
    """
    """
    現在有効になっているコンテキストを返します。
    """
    pass


# 上の context() の定義だと、 'context().attr = value' を誤って、
# 'context.attr = value' と書いたときにエラーにならないので、
# 下の定義に変更している (autodocのために元のも残してある)。
class _context_function(object):
    __slots__ = ()

    def __call__(self) -> Context:
        if not hasattr(thread_local, 'current_context'):
            thread_local.current_context = Context()
        return thread_local.current_context


if '__SPHINX_AUTODOC__' not in os.environ:
    context = _context_function()


def newcontext(**kwargs) -> Context:
    """
    Returns a copy of the currently active context with attribute values
    changed according to the assignment description in `kwargs`.
    Equivalent to ``context().copy().update(**kwargs)``.
    """
    """
    現在有効になっているコンテキストをコピーし、`kwargs` の代入記述に従って
    属性値を変更したものを返します。``context().copy().update(**kwargs)`` と
    等価です。
    """
    ctxt = context().copy()
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
