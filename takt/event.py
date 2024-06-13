# coding:utf-8
"""
このモジュールには、イベントに関するクラス群が定義されています。
これらのイベントの多くは、標準MIDIファイルで定義されたイベントを
基にしています。
"""
# Copyright (C) 2023  Satoshi Nishimura

import warnings
import numbers
from typing import Union, Tuple
from takt.utils import takt_round, int_preferred, std_time_repr, TaktWarning
from takt.constants import CONTROLLERS, META_EVENT_TYPES, M_TEXT_LIMIT, \
     M_TEXT, C_BEND, C_KPR, C_CPR, C_PROG, C_TEMPO, C_ALL_NOTES_OFF, \
     M_SEQNO, M_CHPREFIX, M_SMPTE, M_MARK, M_TEMPO, M_TIMESIG, M_KEYSIG, \
     M_EOT, TICKS_PER_QUARTER
from takt.pitch import Key
from takt.utils import Ticks

__all__ = ['MidiEventError', 'MidiEventWarning', 'midimsg_size',
           'message_to_event']  # extended later


class MidiEventError(Exception): pass
class MidiEventWarning(TaktWarning): pass


class Event(object):
    """ すべてのイベントの基底クラスです。

    Attributes:
        t (ticks): ティック単位で表されたイベントの時刻
        tk (int): トラック番号 (0から始まる)
        dt (ticks): 楽譜上の時刻と演奏上の時刻との差を表し、
            演奏のときは t にこの値(単位はティック)を加えた時刻が
            用いられます。dt値の大きさには制限があります
            (:const:`takt.constants.MAX_DELTA_TIME` を参照)。

    Args:
        t(ticks): t属性の値
        tk(int): tk属性の値
        dt(ticks, optional): dt属性の値
        kwargs: イベントに対して追加の属性を指定します。

    .. rubric:: 演算規則

    * イベントどうしの等価比較('==')は、クラスが一致し、かつすべての属性値が
      等価であるときのみ真となります。
    * 左オペランドを文字列、イベントを右オペランドにして '|' 演算子を用いると、
      左オペランドは無視され、イベントそのものの値となります。これは、
      showtext() で '|' の左側にある小節番号等を無視するのに利用されます。

    """

    __slots__ = ('t',   # time in ticks
                 'tk',  # track number (base-0)
                 'dt',  # time deviation in ticks
                 '__dict__')

    def __init__(self, t, tk, dt=0, **kwargs):
        if not isinstance(t, numbers.Real) or not isinstance(dt, numbers.Real):
            raise TypeError("time must be int, float, or Fraction")
        if not isinstance(tk, numbers.Integral) or tk < 0:
            raise TypeError("track number must be non-negative int")
        (self.t, self.tk, self.dt) = (t, tk, dt)
        self.__dict__.update(kwargs)

    def copy(self) -> 'Event':
        """
        複製されたイベントを返します(浅いコピー)。
        """
        return self.__class__(self.t, self.tk, self.dt, **self.__dict__)
    __copy__ = copy

    def update(self, **kwargs) -> 'Event':
        """
        `kwargs` の代入記述に従って属性を追加・変更します。

        Returns:
            self
        """
        for k, v in kwargs.items():
            setattr(self, k, v)
        return self

    # (ev, val) のようにタプルにしたときにその大小関係が混乱するのでやめた。
    # def __lt__(self, other):
    #     return self.t < other.t
    # def __gt__(self, other):
    #     return self.t > other.t

    def __eq__(self, other):
        return (type(self) is type(other) and
                all(all(getattr(self, key) == getattr(other, key)
                        for key in cls.__slots__)
                    for cls in self.__class__.__mro__ if cls is not object))

    __hash__ = object.__hash__

    def _getattrs(self):
        attrs = [key for key in ('t', 'n', 'mtype', 'xtype', 'L', 'v', 'nv',
                                 'ctrlnum', 'value', 'tk', 'ch')
                 if hasattr(self, key) and key not in self.__dict__]
        if self.dt != 0:
            attrs.append('dt')
        attrs += self.__dict__
        return attrs

    def _valuestr(self, key, timereprfunc):
        value = getattr(self, key)
        if key == 't' or key == 'dt':
            return timereprfunc(value)
        elif key == 'ctrlnum' and value in CONTROLLERS:
            return CONTROLLERS[value]
        elif key == 'mtype' and value in META_EVENT_TYPES:
            return META_EVENT_TYPES[value]
        else:
            return "%r" % (value,)  # %sだとMetaEvent等で値が文字列の場合に問題

    def tostr(self, timereprfunc=std_time_repr) -> str:
        """ イベントを文字列に変換したものを返します。

        Args:
            timereprfunc(function): 時間の値を文字列に変換する関数。
                デフォルトでは小数点以下5桁に丸められた表現を返す
                関数になります。
        """
        params = ["%s=%s" % (k, self._valuestr(k, timereprfunc))
                  for k in self._getattrs()]
        return "%s(%s)" % (self.__class__.__name__, ', '.join(params))

    def __str__(self):
        return self.tostr()

    def __repr__(self):
        return self.tostr(repr)

    def __ror__(self, other):
        if isinstance(other, str):
            return self
        else:
            return NotImplemented

    def is_pitch_bend(self) -> bool:
        """ピッチベンドイベントのとき真を返します。"""
        return (isinstance(self, CtrlEvent) and self.ctrlnum == C_BEND)
    def is_key_pressure(self) -> bool:
        """キープレッシャーイベントのとき真を返します。"""
        return isinstance(self, KeyPressureEvent)
    def is_channel_pressure(self) -> bool:
        """チャネルプレッシャーイベントのとき真を返します。"""
        return (isinstance(self, CtrlEvent) and self.ctrlnum == C_CPR)
    def is_program_change(self) -> bool:
        """プログラムチェンジイベントのとき真を返します。"""
        return (isinstance(self, CtrlEvent) and self.ctrlnum == C_PROG)
    def is_all_notes_off(self) -> bool:
        """オールノートオフイベント(値が0の123番のコントロールチェンジ
            イベント)のとき真を返します。"""
        return (isinstance(self, CtrlEvent) and
                self.ctrlnum == C_ALL_NOTES_OFF and self.value == 0)
    def is_marker(self) -> bool:
        """マーカーイベント(6番のメタイベント）のとき真を返します。"""
        return (isinstance(self, MetaEvent) and self.mtype == M_MARK)
    def is_end_of_track(self) -> bool:
        """トラック終了イベント(47番のメタイベント）のとき真を返します。"""
        return (isinstance(self, MetaEvent) and self.mtype == M_EOT)
    def is_text_event(self) -> bool:
        """テキストイベント(1～15番のメタイベント）のとき真を返します。"""
        return (isinstance(self, MetaEvent) and 1 <= self.mtype <= 15)

    def to_message(self) -> Union[bytes, bytearray]:
        """イベントをバイト列に変換します。
        """
        return b''

    def _get_ch(self):
        if not isinstance(self.ch, numbers.Integral) or not 1 <= self.ch <= 16:
            raise MidiEventError("event with invalid channel number")
        return min(max(self.ch, 1), 16) - 1

    def _get_n(self):
        if not isinstance(self.n, numbers.Real):
            raise MidiEventError("event with ill-typed note number")
        n = takt_round(self.n)
        if not 0 <= n <= 127:
            warnings.warn("Out-of-range note number (n=%r, ch=%r)" %
                          (self.n, self.ch), MidiEventWarning, stacklevel=2)
        return min(max(n, 0), 127)

    def _get_ctrl_val(self, low, high):
        if not isinstance(self.value, numbers.Real):
            raise MidiEventError("event with ill-typed control value")
        val = takt_round(self.value)
        if not low <= val <= high:
            warnings.warn("Out-of-range control value (value=%r, \
ctrlnum=%r, ch=%r)" % (self.value, self.ctrlnum, self.ch),
                          MidiEventWarning, stacklevel=2)
        return min(max(val, low), high)

    def _get_data_bytes(self, encoding='utf-8'):
        if isinstance(self.value, str):
            return self.value.encode(encoding, errors='surrogateescape')
        else:
            return bytes(self.value)

    def ptime(self) -> Ticks:
        """ 演奏上の時刻 (t属性値とdt属性値の和) を返します。"""
        return self.t + self.dt


class NoteEventClass(Event):
    """
    NoteEvent, NoteOnEvent, および NoteOffEvent を総括した抽象クラスです。
    """
    __slots__ = ()

    def __init__(self, *args, **kwargs):
        raise Exception("NoteEventClass is an abstract class")


class NoteEvent(NoteEventClass):
    """
    音符を表すイベントのクラスです。1対のノートオンとノートオフに相当します。

    Attributes:
        ch (int): MIDIチャネル番号 (1から始まる)
        n (int or Pitch): MIDIノート番号
        L (ticks): ティック単位で表された楽譜上の音の長さ (音価)
        v (int): MIDIベロシティ
        nv (int or None): MIDIノートオフベロシティ。Noneならば、MIDI
            バイト列に変換したときにベロシティ0のノートオンが使用されます。
        du (ticks, optional): 演奏時音長 (ノートオンとノートオフの時間差)
            を表します。この属性が無いとき、L属性と同じ値であるとみなされます。

    継承された他の属性
        t, tk, dt

    Args:
        t(ticks): t属性の値
        n(int or Pitch): n属性の値
        L(ticks): L属性の値
        v(int, optional): v属性の値
        nv(int or None, optional): nv属性の値
        du(ticks, optional): du属性の値
        tk(int, optional): tk属性の値
        ch(int, optional): ch属性の値
        dt(ticks, optional): dt属性の値
        kwargs: イベントに対して追加の属性を指定します。
    """

    __slots__ = ('ch',  # MIDI channel number (base-1)
                 'n',   # MIDI note number
                 'L',   # note value in ticks
                 'v',   # MIDI velocity
                 'nv')  # nv: MIDI note-off velocity (possibly None)

    def __init__(self, t, n, L, v=80, nv=None, du=None, tk=1, ch=1, dt=0,
                 **kwargs):
        (self.ch, self.n, self.L, self.v, self.nv) = (ch, n, L, v, nv)
        if du is not None:
            self.du = du
        Event.__init__(self, t, tk, dt, **kwargs)

    def copy(self) -> Event:
        return self.__class__(self.t, self.n, self.L, self.v, self.nv,
                              tk=self.tk, ch=self.ch, dt=self.dt,
                              **self.__dict__)
    __copy__ = copy

    def get_du(self) -> Ticks:
        """ du属性の値(なければLの値)を返します。"""
        return getattr(self, 'du', self.L)

    def offtime(self) -> Ticks:
        """ ノートオフ時刻(t属性値とL属性値の和)を返します。"""
        return self.t + self.L

    def pofftime(self) -> Ticks:
        """ 演奏上のノートオフ時刻を返します。"""
        return self.ptime() + self.get_du()

    def to_message(self) -> Union[bytes, bytearray]:
        return NoteOnEvent.to_message(self) + NoteOffEvent.to_message(self)


class NoteOnEvent(NoteEventClass):
    """ ノートオンイベントのクラスです。

    Attributes:
        ch (int): MIDIチャネル番号 (1から始まる)
        n (int or Pitch): MIDIノート番号
        v (int): MIDIベロシティ

    継承された他の属性
        t, tk, dt

    Args:
        t(ticks): t属性の値
        n(int or Pitch): n属性の値
        v(int, optional): v属性の値
        tk(int, optional): tk属性の値
        ch(int, optional): ch属性の値
        dt(ticks, optional): dt属性の値
        kwargs: イベントに対して追加の属性を指定します。
    """

    __slots__ = ('ch',  # MIDI channel number (base-1)
                 'n',   # MIDI note number
                 'v')   # MIDI velocity

    def __init__(self, t, n, v=80, tk=1, ch=1, dt=0, **kwargs):
        (self.ch, self.n, self.v) = (ch, n, v)
        Event.__init__(self, t, tk, dt, **kwargs)

    def copy(self) -> Event:
        return self.__class__(self.t, self.n, self.v,
                              self.tk, self.ch, self.dt, **self.__dict__)
    __copy__ = copy

    def to_message(self) -> Union[bytes, bytearray]:
        if not isinstance(self.v, numbers.Real):
            raise MidiEventError("note-on with ill-typed velocity")
        v = takt_round(self.v)
        if not 1 <= v <= 127:
            warnings.warn("Out-of-range velocity (v=%r, ch=%r)" %
                          (self.v, self.ch), MidiEventWarning, stacklevel=2)
        v = min(max(v, 1), 127)
        return b"%c%c%c" % (0x90 | self._get_ch(), self._get_n(), v)


class NoteOffEvent(NoteEventClass):
    """ ノートオフイベントのクラスです。

    Attributes:
        ch (int): MIDIチャネル番号 (1から始まる)
        n (int or Pitch): MIDIノート番号
        nv (int or None): MIDIノートオフベロシティ。Noneならば、MIDI
            バイト列に変換したときにベロシティ0のノートオンが使用されます。

    継承された他の属性
        t, tk, dt

    Args:
        t(ticks): t属性の値
        n(int or Pitch): n属性の値
        nv(int or None, optional): nv属性の値
        tk(int, optional): tk属性の値
        ch(int, optional): ch属性の値
        dt(ticks, optional): dt属性の値
        kwargs: イベントに対して追加の属性を指定します。
    """

    __slots__ = ('ch',  # MIDI channel number (base-1)
                 'n',   # MIDI note number
                 'nv', )  # nv: MIDI note-off velocity (possibly None)

    def __init__(self, t, n, nv=None, tk=1, ch=1, dt=0, **kwargs):
        (self.ch, self.n, self.nv) = (ch, n, nv)
        Event.__init__(self, t, tk, dt, **kwargs)

    def copy(self) -> Event:
        return self.__class__(self.t, self.n, self.nv,
                              self.tk, self.ch, self.dt, **self.__dict__)
    __copy__ = copy

    def to_message(self) -> Union[bytes, bytearray]:
        if self.nv is None:
            return b"%c%c%c" % (0x90 | self._get_ch(), self._get_n(), 0)
        else:
            if not isinstance(self.nv, numbers.Real):
                raise MidiEventError("note-off with ill-typed velocity")
            nv = takt_round(self.nv)
            if not 0 <= nv <= 127:
                warnings.warn("Out-of-range note-off velocity (nv=%r, ch=%r)" %
                              (self.nv, self.ch),
                              MidiEventWarning, stacklevel=2)
            nv = min(max(nv, 0), 127)
            return b"%c%c%c" % (0x80 | self._get_ch(), self._get_n(), nv)


class CtrlEvent(Event):
    """
    コントローラ番号とコントロール値を持った制御イベントのクラスです。
    これには、MIDIコントロールチェンジ、プログラムチェンジ、ピッチベンド、
    チャネルプレッシャー、およびキープレッシャーが含まれます。
    キープレッシャーについては専用のサブクラスが用意されていますので、
    インスタンス生成の際にはそのコンストラクタを使用してください。

    Attributes:
        ch (int): MIDIチャネル番号 (1から始まる)
        ctrlnum (int): コントローラ番号を表し、下の意味を持ちます。

            * 0～127: MIDIコントロールチェンジ (`value` は0～127)
            * 128(C_BEND): MIDIピッチベンド (`value` は -8192～8191)
            * 129(C_KPR): MIDIキープレッシャー (KeyPressureEventを参照)
            * 130(C_CPR): MIDIチャネルプレッシャー (`value` は0～127)
            * 131(C_PROG): MIDIプログラムチェンジ (`value` は1～128)
            * それ以外: 内部処理用
        value (int, etc.): コントロール値

    継承された他の属性
        t, tk, dt

    Args:
        t(ticks): t属性の値
        ctrlnum (int): ctrlnum属性の値
        value(int, etc.): value属性の値
        tk(int, optional): tk属性の値
        ch(int, optional): ch属性の値
        dt(ticks, optional): dt属性の値
        kwargs: イベントに対して追加の属性を指定します。
    """
    __slots__ = 'ch', 'ctrlnum', 'value'

    def __init__(self, t, ctrlnum, value, tk=1, ch=1, dt=0, **kwargs):
        if not isinstance(ctrlnum, numbers.Integral):
            raise TypeError("controller number must be int")
        if ctrlnum in (C_KPR, C_TEMPO):
            raise ValueError("Use other constructors for that type of event")
        self._init_base(t, ctrlnum, value, tk, ch, dt, **kwargs)

    def _init_base(self, t, ctrlnum, value, tk, ch, dt, **kwargs):
        (self.ch, self.ctrlnum, self.value) = (ch, ctrlnum, value)
        super().__init__(t, tk, dt, **kwargs)

    def copy(self) -> Event:
        return self.__class__(self.t, self.ctrlnum, self.value,
                              self.tk, self.ch, self.dt, **self.__dict__)
    __copy__ = copy

    def to_message(self) -> Union[bytes, bytearray]:
        if self.ctrlnum == C_PROG:
            low, high = 1, 128
        elif self.ctrlnum == C_BEND:
            low, high = -8192, 8191
        else:
            low, high = 0, 127
        val = self._get_ctrl_val(low, high)
        if 0 <= self.ctrlnum <= 127:
            return b"%c%c%c" % (0xb0 | self._get_ch(), self.ctrlnum, val)
        elif self.ctrlnum == C_BEND:
            val += 8192
            return b"%c%c%c" % (0xe0 | self._get_ch(),
                                val & 0x7f, (val >> 7) & 0x7f)
        elif self.ctrlnum == C_CPR:
            return b"%c%c" % (0xd0 | self._get_ch(), val)
        elif self.ctrlnum == C_PROG:
            return b"%c%c" % (0xc0 | self._get_ch(), val - 1)
        else:
            raise MidiEventError("event with invalid controller number")


class KeyPressureEvent(CtrlEvent):
    """ キープレッシャーイベントのクラスです。

    Attributes:
        n (int or Pitch): MIDIノート番号
        value (int or float): コントロール値(0～127)

    継承された他の属性
        t, tk, dt, ch, ctrlnum

    Args:
        t(ticks): t属性の値
        n(int or Pitch): n属性の値
        value(int, etc.): value属性の値
        tk(int, optional): tk属性の値
        ch(int, optional): ch属性の値
        dt(ticks, optional): dt属性の値
        kwargs: イベントに対して追加の属性を指定します。
    """
    __slots__ = ('n',)

    def __init__(self, t, n, value, tk=1, ch=1, dt=0, **kwargs):
        self.n = n
        super()._init_base(t, C_KPR, value, tk, ch, dt, **kwargs)

    def copy(self) -> Event:
        return self.__class__(self.t, self.n, self.value,
                              self.tk, self.ch, self.dt, **self.__dict__)
    __copy__ = copy

    def _getattrs(self):
        attrs = super()._getattrs()
        attrs.remove('ctrlnum')
        return attrs

    def to_message(self) -> Union[bytes, bytearray]:
        val = self._get_ctrl_val(0, 127)
        return b"%c%c%c" % (0xa0 | self._get_ch(), self._get_n(), val)


class SysExEvent(Event):
    """ システムエクスクルーシブメッセージのイベントです。

    Attributes:
        value (bytes, bytearray, or iterable of int): 先頭の0xf0および
            末尾の0xf7を明示的に含むメッセージの内容。
            1つのメッセージを複数のSysExEventに分割することは可能で、
            その場合は、最初のイベントに0xf0、最後のイベントに0xf7を置きます。

    継承された他の属性
        t, tk, dt

    Args:
        t(ticks): t属性の値
        value(bytes, bytearray, or iterable of int): value属性の値
        tk(int, optional): tk属性の値
        dt(ticks, optional): dt属性の値
        kwargs: イベントに対して追加の属性を指定します。
    """
    __slots__ = ('value',)

    def __init__(self, t, value, tk=1, dt=0, **kwargs):
        self.value = value  # should be bytes or list/tupple of int
        super().__init__(t, tk, dt, **kwargs)

    def copy(self) -> Event:
        return self.__class__(self.t, self.value, self.tk, self.dt,
                              **self.__dict__)
    __copy__ = copy

    def to_message(self) -> Union[bytes, bytearray]:
        """イベントをバイト列(valueの先頭に更に0xf0を加えたもの)に変換します。
        """
        result = bytearray((0xf0,))
        result.extend(self.value)
        return result


class MetaEvent(Event):
    """ 標準MIDIファイルで定義されているメタイベントのクラスです。
    これには、テキストイベント、調号イベント、拍子イベント、
    テンポ変更イベント、トラック終了イベントなどが含まれます。

    Attributes:
        mtype (int): メタイベントの種類 (0～127)
        value (bytes, bytearray, str, Key, int, float, or iterable of int):
            メタイベントのデータ。mtypeが1～15のときは、この属性は str型である
            ことが推奨されます。mtypeが M_KEYSIG (調号イベント) であるときは、
            この属性はKey型でなければなりません。mtypeが M_TEMPO
            (テンポ変更イベント) であるときは、この属性は int または float型
            でなければなりません。それ以外のメタイベントでは、bytes,
            bytearray もしくは整数のイテラブルが推奨されます。

    継承された他の属性
        t, tk, dt

    Args:
        t(ticks): t属性の値
        mtype(int): mtype属性の値
        value(bytes, bytearray, str, Key, int, float, or iterable of int):
            value属性の値
        tk(int, optional): tk属性の値
        dt(ticks, optional): dt属性の値
        kwargs: イベントに対して追加の属性を指定します。

    Notes:
        調号イベント、拍子イベント、およびテンポ変更イベントについては
        それぞれ専用のサブクラスが用意されています。
        インスタンス生成の際、テンポ変更イベントについては専用のサブクラス
        (TempoEvent) を使用してください。
        調号イベントと拍子イベントについては、このクラスのコンストラクタで
        作成することも可能ですが、各サブクラスのコンストラクタを用いた方が
        より便利です。
    """

    __slots__ = ('mtype', 'value')

    def __init__(self, t, mtype, value, tk=1, dt=0, **kwargs):
        if not isinstance(mtype, numbers.Integral):
            raise TypeError("meta-event type must be int")
        if mtype == M_TEMPO:
            raise ValueError("Use TempoEvent for create a tempo event")
        elif mtype == M_KEYSIG:
            self.__class__ = KeySignatureEvent
            if not isinstance(value, Key):
                raise TypeError(
                    "value must be a Key object for key-signature event")
        elif mtype == M_TIMESIG:
            self.__class__ = TimeSignatureEvent
        self._init_base(t, mtype, value, tk, dt, **kwargs)

    def _init_base(self, t, mtype, value, tk, dt, **kwargs):
        (self.mtype, self.value) = (mtype, value)
        super().__init__(t, tk, dt, **kwargs)

    def copy(self) -> Event:
        return MetaEvent(self.t, self.mtype, self.value,
                         self.tk, self.dt, **self.__dict__)
    __copy__ = copy

    def to_message(self, encoding='utf-8') -> Union[bytes, bytearray]:
        """ イベントをバイト列(長さ情報を除いた標準MIDIファイル中のデータ)に
        変換します。

        Args:
            encoding(str): テキストイベントが持つ文字列を、バイト列中で
                どのようにエンコーディングするかを指定します。
        """
        try:
            result = bytearray((0xff, self.mtype))
        except (TypeError, ValueError):
            raise MidiEventError("invalid meta event type")
        data_bytes = self._get_data_bytes(encoding)
        if self.mtype == M_SEQNO and len(data_bytes) != 2 or \
           self.mtype == M_CHPREFIX and len(data_bytes) != 1 or \
           self.mtype == M_EOT and len(data_bytes) != 0 or \
           self.mtype == M_TEMPO and len(data_bytes) != 3 or \
           self.mtype == M_SMPTE and len(data_bytes) != 5 or \
           self.mtype == M_TIMESIG and len(data_bytes) != 4 or \
           self.mtype == M_KEYSIG and len(data_bytes) != 2:
            raise MidiEventError("meta event with inappropriate data length")
        result.extend(data_bytes)
        return result


class KeySignatureEvent(MetaEvent):
    """ 調号イベントのクラスです。

    継承された属性
        t, tk, dt, mtype, value

    Args:
        t(ticks): t属性の値
        value(Key, int, or str): Keyコンストラクタの第１引数
        tk(int, optional): tk属性の値
        dt(ticks, optional): dt属性の値
        kwargs: イベントに対して追加の属性を指定します。
    """
    __slots__ = ()

    def __init__(self, t, value, tk=0, dt=0, **kwargs):
        super().__init__(t, M_KEYSIG, Key(value), tk, dt, **kwargs)

    def _getattrs(self):
        attrs = super()._getattrs()
        attrs.remove('mtype')
        return attrs

    def to_message(self, encoding='utf-8') -> Union[bytes, bytearray]:
        """イベントをバイト列(長さ情報を除いた標準MIDIファイル中のデータ)に
        変換します。
        """
        return b"\xff%c%c%c" % (M_KEYSIG,
                                self.value.signs & 0xff, self.value.minor)


class TimeSignatureEvent(MetaEvent):
    """ 拍子イベントのクラスです。

    継承された属性
        t, tk, dt, mtype, value

    Args:
        t(ticks): t属性の値
        num(int): 分子の値
        den(int): 分母の値
        cc(int, optional): メトロノームクリックの間隔を四分音符の1/24を単位
            として表したもの。デフォルトでは、`num` と `den` から自動的に
            推測されます。
        tk(int, optional): tk属性の値
        dt(ticks, optional): dt属性の値
        kwargs: イベントに対して追加の属性を指定します。

    Examples:
        時刻が0で4/4拍子の場合、``TimeSignatureEvent(0, 4, 4)``
    """
    __slots__ = ()

    def __init__(self, t, num, den, cc=None, tk=0, dt=0, **kwargs):
        if den <= 0 or den & (den - 1) != 0:
            raise ValueError("TimeSignatureEvent: Bad denominator")
        value = (num, (den - 1).bit_length(),
                 cc if cc is not None else self._guess_cc(num, den), 8)
        value = kwargs.pop('value', value)
        super().__init__(t, M_TIMESIG, bytes(value), tk, dt, **kwargs)

    def _getattrs(self):
        attrs = super()._getattrs()
        attrs.remove('mtype')
        return attrs

    def _guess_cc(self, num, den):
        cc = 96 * (3 if den >= 8 and num in (6, 9, 12) else 1)
        if cc % den != 0:
            cc = 24  # very rare case like 4/64
        else:
            cc //= den
        return cc

    def numerator(self) -> int:
        """ 分子の値を返します。"""
        return self._get_data_bytes()[0]

    def denominator(self) -> int:
        """ 分母の値を返します。"""
        return 1 << self._get_data_bytes()[1]

    def num_den(self) -> Tuple[int, int]:
        """ 分子と分母からなる2要素タプルを返します。"""
        data = self._get_data_bytes()
        return (data[0], 1 << data[1])

    def get_cc(self) -> int:
        """ メトロノームクリックの間隔(四分音符の1/24単位)を返します。"""
        return self._get_data_bytes()[2]

    def tostr(self, timereprfunc=std_time_repr) -> str:
        if isinstance(self.value, bytes) and self.value[3] == 8:
            num = self.value[0]
            den = 1 << self.value[1]
            params = ["%s=%s" % ('t', self._valuestr('t', timereprfunc)),
                      "num=%r" % num, "den=%r" % den]
            if self.value[2] != self._guess_cc(num, den):
                params.append("cc=%r" % self.value[2])
            attrs = self._getattrs()
            attrs.remove('t')
            attrs.remove('value')
            params.extend("%s=%s" % (k, self._valuestr(k, timereprfunc))
                          for k in attrs)
            return "%s(%s)" % (self.__class__.__name__, ', '.join(params))
        else:
            return super().tostr(timereprfunc)

    def beat_length(self) -> Ticks:
        """ 1拍の長さをティック単位で返します。"""
        data = self._get_data_bytes()
        return int_preferred(TICKS_PER_QUARTER * 4 / (1 << data[1]))

    def measure_length(self) -> Ticks:
        """ 1小節の長さをティック単位で返します。"""
        return self.numerator() * self.beat_length()


class TempoEvent(MetaEvent):
    """ テンポ変更イベントのクラスです。

    Attributes:
        value (int or float):
            1分あたりの4分音符数で表されたテンポ値 (最低値は4)

    継承された他の属性
        t, tk, dt, mtype, value

    Args:
        t(ticks): t属性の値
        value(int or float): value属性の値
        tk(int, optional): tk属性の値
        dt(ticks, optional): dt属性の値
        kwargs: イベントに対して追加の属性を指定します。
    """
    __slots__ = ()

    def __init__(self, t, value, tk=0, dt=0, **kwargs):
        super()._init_base(t, M_TEMPO, value, tk, dt, **kwargs)

    def copy(self) -> Event:
        return self.__class__(self.t, self.value, self.tk, self.dt,
                              **self.__dict__)
    __copy__ = copy

    def _getattrs(self):
        attrs = super()._getattrs()
        attrs.remove('mtype')
        return attrs

    def to_message(self, encoding='utf-8') -> Union[bytes, bytearray]:
        """イベントをバイト列(長さ情報を除いた標準MIDIファイル中のデータ)に
        変換します。
        """
        low, high = 4, 1e8
        if not low <= self.value <= high:
            warnings.warn("Out-of-range tempo value (value=%r)" %
                          (self.value,), MidiEventWarning, stacklevel=2)
        val = takt_round(6e+7 / min(max(self.value, low), high))
        return b"\xff%c%c%c%c" % (M_TEMPO, (val >> 16) & 0xff,
                                  (val >> 8) & 0xff, val & 0xff)


class LoopBackEvent(Event):
    """ ループバックイベントのクラスです。

    Attributes:
        value: イベントを区別するための任意のデータ

    継承された他の属性
        t, tk, dt

    Args:
        t(ticks): t属性の値
        value(str): value属性の値
        tk(int, optional): tk属性の値
        dt(ticks, optional): dt属性の値
        kwargs: イベントに対して追加の属性を指定します。
    """
    __slots__ = ('value',)

    def __init__(self, t, value, tk=0, dt=0, **kwargs):
        self.value = value
        super().__init__(t, tk, dt, **kwargs)

    def copy(self) -> Event:
        return self.__class__(self.t, self.value, self.tk, self.dt,
                              **self.__dict__)
    __copy__ = copy

    def to_message(self) -> Union[bytes, bytearray]:
        raise Exception("Cannot convert LoopBackEvent to a message")


class XmlEvent(Event):
    """ 五線譜のための追加情報を記述したイベントのクラスです。

    Attributes:
        xtype (str): 情報の種類を表す文字列
        value: 情報の内容データ

    継承された他の属性
        t, tk, dt

    Args:
        t(ticks): t属性の値
        xtype(str): xtype属性の値
        value: value属性の値
        tk(int, optional): tk属性の値
        dt(ticks, optional): dt属性の値
        kwargs: イベントに対して追加の属性を指定します。

    有効なイベントの一覧
        ========== ============ ============================= ================
        xtype      desc.         value                        optional attrs.
        ========== ============ ============================= ================
        'clef'     音部記号     'G', 'F', 'C'                 line(int),
                                'percussion', 'TAB',          octave_change
                                'jianpu', 'none'              (int)
        'barline'  小節区切り   'dashed', 'dotted', 'heavy',
                                'heavy-heavy', 'heavy-light',
                                'light-heavy', 'light-light',
                                'none', 'regular', 'short',
                                'tick', 'double', 'final',
                                'repeat-start', 'repeat-end'
        'chord'    コード記号   Chord
        'text'     汎用テキスト str
        ========== ============ ============================= ================
    """
    __slots__ = ('xtype', 'value',)

    def __init__(self, t, xtype, value, tk=1, dt=0, **kwargs):
        self.xtype = xtype
        self.value = value
        super().__init__(t, tk, dt, **kwargs)

    def copy(self) -> Event:
        return self.__class__(self.t, self.xtype, self.value,
                              self.tk, self.dt, **self.__dict__)
    __copy__ = copy

    def to_message(self) -> Union[bytes, bytearray]:
        raise Exception("Cannot convert XmlEvent to a message")


_msg_size_table = (3, 3, 3, 3, 2, 2, 3, 0)


def midimsg_size(status) -> int:
    """ MIDIメッセージのステータスバイトからメッセージの長さを求めます。

    Args:
        status(int): MIDIステータスバイトの値

    Returns:
        メッセージの長さ
    """
    return (-1 if status < 0x80 or status >= 0x100 else
            _msg_size_table[(status >> 4) & 7] if status <= 0xf0 else
            2 if status in (0xf1, 0xf3) else
            3 if status == 0xf2 else
            1)


def message_to_event(msg, time, tk, encoding='utf-8') -> Event:
    """ 各クラスの to_message メソッドが返す形式のバイト列を受け取って、
    それを適切なクラスのイベントへ変換します (LoopBackEventを除く)。

    Args:
        msg(bytes, bytearray, or iterable of int): 入力バイト列
        time(ticks): イベントの時刻
        tk(int): トラック番号
        encoding(str or None): テキストイベントの持つ文字列が、バイト列中で
                どのようにエンコーディングされているかを指定します。None
                のときは、バイト列のままのテキストイベントを生成します。

    Returns:
        作成されたイベント
    """
    ch = (msg[0] & 0xf) + 1
    etype = msg[0] & 0xf0
    if etype == 0x80:
        return NoteOffEvent(time, msg[1], msg[2], tk, ch)
    elif etype == 0x90:
        if msg[2] == 0:
            return NoteOffEvent(time, msg[1], None, tk, ch)
        else:
            return NoteOnEvent(time, msg[1], msg[2], tk, ch)
    elif etype == 0xa0:
        return KeyPressureEvent(time, msg[1], msg[2], tk, ch)
    elif etype == 0xb0:
        return CtrlEvent(time, msg[1], msg[2], tk, ch)
    elif etype == 0xc0:
        return CtrlEvent(time, C_PROG, msg[1] + 1, tk, ch)
    elif etype == 0xd0:
        return CtrlEvent(time, C_CPR, msg[1], tk, ch)
    elif etype == 0xe0:
        return CtrlEvent(time, C_BEND, msg[1] + (msg[2] << 7) - 8192, tk, ch)
    elif msg[0] == 0xf0:
        return SysExEvent(time, bytes(msg[1:]), tk)
    elif msg[0] == 0xff:
        if msg[1] == M_TEMPO:
            usecsPerBeat = (msg[2] << 16) + (msg[3] << 8) + msg[4]
            usecsPerBeat = max(usecsPerBeat, 1)
            return TempoEvent(time, 6e+7 / usecsPerBeat, tk)
        elif M_TEXT <= msg[1] <= M_TEXT_LIMIT:
            if encoding is None:
                return MetaEvent(time, msg[1], bytes(msg[2:]), tk)
            try:
                strvalue = msg[2:].decode(encoding)
            except UnicodeDecodeError:
                # warnings.warn("Unrecognized characters in text events. "
                #               "Please check the 'encoding' argument.",
                #               TaktWarning)
                strvalue = msg[2:].decode(encoding, errors='surrogateescape')
            return MetaEvent(time, msg[1], strvalue, tk)
        elif msg[1] == M_KEYSIG:
            return MetaEvent(time, msg[1],
                             Key(msg[2] - ((msg[2] & 0x80) << 1), msg[3]), tk)
        else:
            return MetaEvent(time, msg[1], bytes(msg[2:]), tk)
    else:
        warnings.warn("unrecognized MIDI message: %r" % bytes(msg),
                      MidiEventWarning, stacklevel=2)
        return SysExEvent(time, bytes(msg), tk)


# Eventとそのサブクラスを自動的に __all__ に含める
__all__.extend([name for name, value in globals().items()
               if name[0] != '_' and isinstance(value, type) and
               issubclass(value, Event)])
