# coding:utf-8
"""
このモジュールには、音符など基本的なスコアを生成するための関数が定義されて
います。
noteとrest以外の関数は、上位モジュール（taktモジュール）の名前空間に取り
込まれませんので、sc.ctrl のようにサブモジュール名をつけて呼び出して下さい。
"""
# Copyright (C) 2023  Satoshi Nishimura

import math
import numbers
import os
from takt.score import EventList
from takt.event import NoteEvent, CtrlEvent, KeyPressureEvent, TempoEvent, \
    SysExEvent, MetaEvent, TimeSignatureEvent, XmlEvent
from takt.constants import C_MOD, C_BREATH, C_FOOT, C_PORTA, C_VOL, C_EXPR, \
    C_PAN, C_REVERB, C_SUSTAIN, C_SOFTPED, C_PORTAON, C_SOSTENUTO, \
    C_BEND, C_KPR, C_CPR, C_PROG, C_TEMPO, C_BANK, C_NRPCL, C_RPCL, \
    C_DATA, C_ALL_SOUND_OFF, C_RESET_ALL_CTRLS, C_ALL_NOTES_OFF, \
    M_SEQNO, M_TEXT, M_COPYRIGHT, M_TRACKNAME, M_INSTNAME, M_LYRIC, M_MARK, \
    M_EOT, M_KEYSIG, M_CHPREFIX, M_DEVNO, MAX_DELTA_TIME, L64
from takt.context import context, newcontext, Context
from takt.pitch import Key
from takt.utils import takt_round
from takt.interpolator import Interpolator
from takt.chord import Chord

__all__ = []  # extended later


def _getparams(kwargs, *attrs):
    """ イベントコンストラクタのキーワード引数格納したdictを返す。

    Args:
        kwargs(dict): このモジュールの関数に渡されたキーワード引数
        attrs(list of str): イベントコンストラクタの引数のうち、コンテキスト
            から値を持ってくるもののリスト
    """
    attrs += ('dt', 'tk')
    rtn = {k: getattr(context(), k) for k in attrs}
    for k, v in kwargs.items():
        # コンテキストには入っているがattrsには入っていない引数はrtnに含めない
        if not context().has_attribute(k) or k in attrs:
            rtn[k] = v
    if abs(rtn['dt']) > MAX_DELTA_TIME:
        raise ValueError("`dt' has too large absolute value")
    return rtn


def _apply_effectors(score):
    for eff in context().effectors:
        with newcontext(effectors=[]):
            score = eff(score)
    return score


def note(pitch, L=None, step=None, **kwargs) -> EventList:
    """
    1つの音符からなるスコアとして、1つの NoteEvent を含む EventList を生成
    します。生成される NoteEvent の時刻 (t属性値) は常に 0 となります。

    Args:
        pitch(Pitch or int): 音符のピッチを指定します。
            生成される NoteEvent のn属性はこの値となります。
        L(ticks, optional): 音価を指定します。
            省略すると、コンテキストのL属性の値になります。
            生成される NoteEvent のL属性はこの値となります。
        step(ticks, optional): 生成されるイベントリストのduration属性
            の値 (つまり、生成されるスコアの演奏長) を指定します。
            省略すると音価と同じ値になります。
        kwargs: 追加のキーワード引数。コンテキストに同名の(疑似)属性が存在する
            場合は、その属性値を一時的に変更する指定となります。
            そうでなければ、NoteEvent に対する追加の属性となります。

    **影響を受ける可能性のあるコンテキスト属性**

        dt, tk, ch, v, nv, L, duoffset, durate, effectors

    Examples:
        >>> note(C4)
        EventList(duration=480, events=[
            NoteEvent(t=0, n=C4, L=480, v=80, nv=None, tk=1, ch=1)])
        >>> note(C4, L8, step=120)
        EventList(duration=120, events=[
            NoteEvent(t=0, n=C4, L=240, v=80, nv=None, tk=1, ch=1)])
        >>> note(Db5, ch=3, dt=30, dr=50)  # modifying context
        EventList(duration=480, events=[
            NoteEvent(t=0, n=Db5, L=480, v=80, nv=None, tk=1, ch=3, dt=30, \
du=240)])
        >>> note(C3, voice=1)  # extra attribute
        EventList(duration=480, events=[
            NoteEvent(t=0, n=C3, L=480, v=80, nv=None, tk=1, ch=1, voice=1)])
    """
    with context().copy().update(**{k: v for k, v in kwargs.items()
                                    if context().has_attribute(k)}):
        if L is None:
            L = context().L
        else:
            context().L = L
        ev = NoteEvent(0, pitch, L, **_getparams(kwargs, 'v', 'nv', 'ch'))
        if context().du != L:
            ev.du = context().du
        return _apply_effectors(EventList([ev], L if step is None else step))


def rest(L=None) -> EventList:
    """　休符のスコアとして、空イベントの EventList を生成します。

    Args:
        L(ticks, optional): 休符の長さを指定します。
            生成されるイベントリストのduration属性はこの値と一致します。
            省略すると、コンテキストのL属性の値になります。

    **影響を受ける可能性のあるコンテキスト属性**

        L, effectors

    """
    return _apply_effectors(
        EventList(duration=context().L if L is None else L))


def ctrl(ctrlnum, value, *, n=None, word=False, duration=0,
         tstep=L64, ystep=1, _rpc=None, **kwargs) -> EventList:
    """ CtrlEvent または TempoEvent を含む EventList を生成します。
    単一のコントロール値だけでなく、:class:`.Interpolator` を利用して
    段階的に変化するような複数のコントロール値を生成することも可能です。

    Args:
        ctrlnum(int): コントローラ番号を指定します
            (:class:`.CtrlEvent` を参照)。この値が C_TEMPO (192) であるときは
            TempoEvent が生成されます。
        value(int, float, 2-tuple, or list): コントロール値を指定します。
            int または float であるときは、単一のコントロール値に基づいた
            CtrlEvent/TempoEvent が生成されます。2-tupleであるときは、
            `word` 引数が暗黙に True であることが仮定され、(MSB, LSB) の形式に
            よって上位バイトと下位バイトを別々に指定します。list型であるとき
            は、その値が :class:`.Interpolator` のコンストラクタへ渡され、
            段階的に変化するような CtrlEvent/TempoEvent の列が生成されます。
        n(int or Pitch, optional): キープレッシャーイベントの場合 (`ctrlnum`
            が C_KPR の場合) に、MIDIノート番号を指定します。それ以外の種類の
            イベントでは指定できません。
        word(bool, optional): `ctrlnum` が 31 以下の場合のコントロール
            チェンジの場合において、この引数を True にすると、
            14ビットのコントロール値をコントローラ番号の異なる2つの CtrlEvent
            に分けて生成するようになります。段階的に変化するコントロールの
            場合でも、出力値のそれぞれにおいて2つのCtrlEvent が生成されます。
        duration(ticks, optional): イベントリストの duration属性値を
            指定します。'auto'を指定した場合、単一のコントロール値の場合は 0、
            段階的に変化するコントロールの場合は最後の CtrlEvent/TempoEvent
            の時刻になります。
        tstep(ticks, optional): 段階的に変化するコントロールの場合
            おけるの時間の刻み値を指定します (:meth:`.Interpolator.iterator`
            を参照)。
        ystep(int or float, optional): 段階的に変化するコントロールの場合に
            おいて、出力値の変化スレッショルドを指定します
            (:meth:`.Interpolator.iterator` を参照)。
        kwargs: 追加のキーワード引数。コンテキストに同名の属性が存在する
            場合は、その属性値を一時的に変更する指定となります。
            そうでなければ、出力されるすべての CtrlEvent/TempoEvent に対する
            追加の属性となります。

    **影響を受ける可能性のあるコンテキスト属性**
        dt, tk, ch, effectors

    Examples:
        >>> sc.ctrl(7, 60, ch=2)  # volume control: value=60  MIDI_channel=2
        EventList(duration=0, events=[
            CtrlEvent(t=0, ctrlnum=C_VOL, value=60, tk=1, ch=2)])
        >>> sc.ctrl(7, [0, (L4, 100)], tstep=120)  # linearly increasing volume
        EventList(duration=480, events=[
            CtrlEvent(t=0, ctrlnum=C_VOL, value=0.0, tk=1, ch=1),
            CtrlEvent(t=120, ctrlnum=C_VOL, value=25.0, tk=1, ch=1),
            CtrlEvent(t=240, ctrlnum=C_VOL, value=50.0, tk=1, ch=1),
            CtrlEvent(t=360, ctrlnum=C_VOL, value=75.0, tk=1, ch=1),
            CtrlEvent(t=480, ctrlnum=C_VOL, value=100, tk=1, ch=1)])
        >>> sc.ctrl(1, 80, duration=120)
        EventList(duration=120, events=[
            CtrlEvent(t=0, ctrlnum=C_MOD, value=80, tk=1, ch=1)])
        >>> sc.ctrl(0, (2, 3))  # specifying the value with (MSB,LSB) pair
        EventList(duration=0, events=[
            CtrlEvent(t=0, ctrlnum=C_BANK, value=2, tk=1, ch=1),
            CtrlEvent(t=0, ctrlnum=C_BANK_L, value=3, tk=1, ch=1)])
    """
    if ctrlnum == C_KPR and n is None:
        raise Exception("key-pressure event requires a note number")
    elif ctrlnum != C_KPR and n is not None:
        raise Exception("only key-pressure event takes a note number")

    if isinstance(value, tuple) and len(value) == 2:
        word = True
        value = (value[0] << 7) | (value[1] & 0x7f)

    if ctrlnum >= 32 and word:
        raise Exception("ctrlnum must be less than 32 when 'word' is True")

    def create_events(t, value):
        if ctrlnum == C_TEMPO:
            with newcontext(tk=0):
                return [TempoEvent(t, value, **_getparams(kwargs))]
        params = _getparams(kwargs, 'ch')
        if ctrlnum == C_KPR:
            return [KeyPressureEvent(t, n, value, **params)]
        rtn = []
        if _rpc is not None:
            rtn = [CtrlEvent(t, _rpc[0], _rpc[1][1], **params),
                   CtrlEvent(t, _rpc[0] + 1, _rpc[1][0], **params)]
        if word:
            v = round(value)
            rtn.append(CtrlEvent(t, ctrlnum, (v >> 7) & 0x7f, **params))
            rtn.append(CtrlEvent(t, ctrlnum + 0x20, v & 0x7f, **params))
        else:
            rtn.append(CtrlEvent(t, ctrlnum, value, **params))
        return rtn

    if isinstance(value, numbers.Real):
        return _apply_effectors(EventList(
            create_events(0, value), 0 if duration == 'auto' else duration))
    elif isinstance(value, list):
        itpl = Interpolator(value)
        rtn = EventList([], itpl.maxtime() if duration == 'auto' else duration)
        for t, val in itpl.iterator(tstep, ystep):
            rtn.extend(create_events(t, val))
        return _apply_effectors(rtn)
    else:
        raise Exception("Bad 'value' argument")


def bank(value, **kwargs) -> EventList:
    """ バンクセレクト（0, 32番のコントロールチェンジ) の CtrlEvent を含む
    EventList を生成します。``ctrl(0, value, **kwargs)`` と等価です。"""
    return ctrl(C_BANK, value, **kwargs)


def mod(value, **kwargs) -> EventList:
    """ モジュレーションデプス（1, 33番のコントロールチェンジ) の CtrlEvent
    を含む EventList を生成します。
    ``ctrl(1, value, **kwargs)`` と等価です。"""
    return ctrl(C_MOD, value, **kwargs)


def breath(value, **kwargs) -> EventList:
    """ ブレスコントローラ（2, 34番のコントロールチェンジ) の CtrlEvent
    を含む EventList を生成します。
    ``ctrl(2, value, **kwargs)`` と等価です。"""
    return ctrl(C_BREATH, value, **kwargs)


def foot(value, **kwargs) -> EventList:
    """ フットコントローラ（4, 36番のコントロールチェンジ) の CtrlEvent
    を含む EventList を生成します。
    ``ctrl(4, value, **kwargs)`` と等価です。"""
    return ctrl(C_FOOT, value, **kwargs)


def porta(value, **kwargs) -> EventList:
    """ ポルタメントタイム（5, 37番のコントロールチェンジ) の CtrlEvent
    を含む EventList を生成します。
    ``ctrl(5, value, **kwargs)`` と等価です。"""
    return ctrl(C_PORTA, value, **kwargs)


def vol(value, **kwargs) -> EventList:
    """ メイン(チャンネル)ボリューム（7, 39番のコントロールチェンジ) の
    CtrlEvent を含む EventList を生成します。
    ``ctrl(7, value, **kwargs)`` と等価です。"""
    return ctrl(C_VOL, value, **kwargs)


def pan(value, **kwargs) -> EventList:
    """ パンポット（10, 42番のコントロールチェンジ) の CtrlEvent を含む
    EventList を生成します。``ctrl(10, value, **kwargs)`` と等価です。"""
    return ctrl(C_PAN, value, **kwargs)


def expr(value, **kwargs) -> EventList:
    """ エクスプレッション（11, 43番のコントロールチェンジ) の
    CtrlEvent を含む  EventList を 生成します。
    ``ctrl(11, value, **kwargs)`` と等価です。"""
    return ctrl(C_EXPR, value, **kwargs)


def reverb(value, **kwargs) -> EventList:
    """ エフェクト１（リバーブ）デプス（91番のコントロールチェンジ) の
    CtrlEvent を含む  EventList を 生成します。
    ``ctrl(91, value, **kwargs)`` と等価です。"""
    return ctrl(C_REVERB, value, **kwargs)


def ped(value=127, **kwargs) -> EventList:
    """ ダンパーペダルを ON にする CtrlEvent を含む EventList を生成します。
    ``ctrl(64, value, **kwargs)`` と等価です。"""
    return ctrl(C_SUSTAIN, value, **kwargs)


def pedoff(**kwargs) -> EventList:
    """ ダンパーペダルを OFF にする CtrlEvent を含む EventList を生成します。
    ``ctrl(64, 0, **kwargs)`` と等価です。"""
    return ctrl(C_SUSTAIN, 0, **kwargs)


def ped2(value=127, **kwargs) -> EventList:
    """ ソフトペダルを ON にする CtrlEvent を含む EventList を生成します。
    ``ctrl(67, value, **kwargs)`` と等価です。"""
    return ctrl(C_SOFTPED, value, **kwargs)


def ped2off(**kwargs) -> EventList:
    """ ソフトペダルを OFF にする CtrlEvent を含む EventList を生成します。
    ``ctrl(67, 0, **kwargs)`` と等価です。"""
    return ctrl(C_SOFTPED, 0, **kwargs)


def ped3(value=127, **kwargs) -> EventList:
    """ ソステヌートペダルを ON にする CtrlEvent を含む EventList を生成
    します。``ctrl(66, value, **kwargs)`` と等価です。"""
    return ctrl(C_SOSTENUTO, value, **kwargs)


def ped3off(**kwargs) -> EventList:
    """ ソステヌートペダルを OFF にする CtrlEvent を含む EventList を生成
    します。``ctrl(66, 0, **kwargs)`` と等価です。"""
    return ctrl(C_SOSTENUTO, 0, **kwargs)


def portaon(value=127, **kwargs) -> EventList:
    """ ポルタメントを ON にする CtrlEvent を含む EventList を生成します。
    ``ctrl(65, value, **kwargs)`` と等価です。"""
    return ctrl(C_PORTAON, value, **kwargs)


def portaoff(**kwargs) -> EventList:
    """ ポルタメントを OFF にする CtrlEvent を含む EventList を生成します。
    ``ctrl(65, 0, **kwargs)`` と等価です。"""
    return ctrl(C_PORTAON, 0, **kwargs)


def all_sound_off(**kwargs) -> EventList:
    """ オール・サウンド・オフの CtrlEvent を含む EventList を生成します。
    ``ctrl(120, 0, **kwargs)`` と等価です。"""
    return ctrl(C_ALL_SOUND_OFF, 0, **kwargs)


def reset_all_ctrls(**kwargs) -> EventList:
    """ リセット・オール・コントローラの CtrlEvent を含む EventList を
    生成します。``ctrl(121, 0, **kwargs)`` と等価です。"""
    return ctrl(C_RESET_ALL_CTRLS, 0, **kwargs)


def all_notes_off(**kwargs) -> EventList:
    """ オール・ノート・オフの CtrlEvent を含む EventList を生成します。
    ``ctrl(123, 0, **kwargs)`` と等価です。"""
    return ctrl(C_ALL_NOTES_OFF, 0, **kwargs)


def bend(value, **kwargs) -> EventList:
    """ ピッチベンドの CtrlEvent を含む EventList を生成します。
    値は -8192～8191の範囲で指定します。
    ``ctrl(C_BEND, value, **kwargs)`` と等価です。"""
    return ctrl(C_BEND, value, **kwargs)


def cpr(value, **kwargs) -> EventList:
    """ チャネルプレッシャーの CtrlEvent を含む EventList を生成します。
    ``ctrl(C_CPR, value, **kwargs)`` と等価です。"""
    return ctrl(C_CPR, value, **kwargs)


def prog(value, **kwargs) -> EventList:
    """ プログラムチェンジの CtrlEvent を含む EventList を生成します。
    値は 1～128 の範囲で指定します。
    ``ctrl(C_PROG, value, **kwargs)`` と等価です。"""
    return ctrl(C_PROG, value, **kwargs)


def kpr(pitch, value, **kwargs) -> EventList:
    """ KeyPressureEvent を含む  EventList を生成します。
    ``ctrl(C_KPR, value, n=pitch, **kwargs)`` と等価です。"""
    return ctrl(C_KPR, value, n=pitch, **kwargs)


def rpc(rpn, data, nrpc=False, **kwargs) -> EventList:
    """ RPC (Registered Parameter Control) または NRPC (Non-Registered
    Parameter Control) のための EventList を生成します。

    Args:
        rpn(int or 2-tuple): RPN または NRPN を指定します。int 型の場合は
            16ビットの数値(上位8ビットがMSB, 下位8ビットがLSB)、
            2-tuple の場合は (MSB, LSB) の形式で指定します。
        data(int, float, 2-tuple, or list): データエントリー
            (6, 36番のコントロールチェンジ) で送出するデータを指定します。
        nrpc(bool, optional): NPC のとき False, NRPC のとき True。
        kwargs: ctrl() 関数に渡される他の引数。

    **影響を受ける可能性のあるコンテキスト属性**
        dt, tk, ch, effectors

    Examples:
        >>> sc.rpc((0, 1), 8835, word=True)  # Fine tuning to A=442Hz
        EventList(duration=0, events=[
            CtrlEvent(t=0, ctrlnum=C_RPCL, value=1, tk=1, ch=1),
            CtrlEvent(t=0, ctrlnum=C_RPCH, value=0, tk=1, ch=1),
            CtrlEvent(t=0, ctrlnum=C_DATA, value=69, tk=1, ch=1),
            CtrlEvent(t=0, ctrlnum=C_DATA_L, value=3, tk=1, ch=1)])
    """
    if isinstance(rpn, int):
        rpn = ((rpn >> 8) & 0x7f, rpn & 0x7f)
    return ctrl(C_DATA, data,
                _rpc=(C_NRPCL if nrpc else C_RPCL, rpn), **kwargs)


def bender_range(semitones, **kwargs) -> EventList:
    """ rpc() を使ってピッチ・ベンド・センシティビティ設定のための
    EventList を生成します。

    Args:
        semitones(int): ピッチベンド範囲を半音数で指定します。例えば、
            +-1オクターブなら 12 とします。
        kwargs: ctrl() 関数に渡される他の引数。
    """
    return rpc(0x0000, (semitones, 0), False, **kwargs)


def fine_tune(*, freq=None, cents=None, **kwargs) -> EventList:
    """ rpc() を使ってファイン・チューニングのための EventList を生成します。

    Args:
        freq(int or float): A4音の周波数を指定します。
            `cents` と同時には指定できません。
        cents(int or float):
            標準チューニング (A4=440Hz) からのずれをセント (半音の1/100)
            単位で指定します。-100 <= `cents` < 100 の範囲をとります。
            `freq` と同時には指定できません。
        kwargs: ctrl() 関数に渡される他の引数。
    """
    if freq is not None:
        if cents is not None:
            raise Exception(
                "fine_tune: can't use 'freq' and 'cents' simultaneously")
        cents = math.log(freq / 440.0) * (1200 / math.log(2))
    elif cents is None:
        raise Exception(
            "fine_tune() requires either 'freq' or 'cents' keyword arguments")
    val = takt_round(cents * (0x2000 / 100.0)) + 0x2000
    if not 0 <= val < 0x4000:
        raise ValueError("fine_tune: Out of parameter range")
    return rpc(0x0001, val, False, word=True, **kwargs)


def coarse_tune(semitones, **kwargs) -> EventList:
    """ rpc() を使ってコース・チューニングのための EventList を生成します。

    Args:
        semitones(int): 標準チューニングからのずれを半音数（符号つき）
            で指定します。
        kwargs: ctrl() 関数に渡される他の引数。
    """
    return rpc(0x0002, (semitones + 0x40, 0), False, **kwargs)


def tempo(value, **kwargs) -> EventList:
    """ TempoEvent を含む EventList を生成します。
    トラック番号 (tk属性) は、明示的に指定しない限り、コンテキストによらず
    0 になります。
    ``ctrl(C_TEMPO, value, **kwargs)`` と等価です。

    Args:
        value (int or float): BPMで表されたテンポ値 (最低値は4)
        kwargs: ctrl() 関数に渡される他の引数。
    """
    return ctrl(C_TEMPO, value, **kwargs)


def sysex(data, arbitrary=False, *, duration=0, **kwargs) -> EventList:
    """ SysExEvent を含む EventList を生成します。

    Args:
        data(bytes, bytearray, or iterable of int):
            システム・エクスクルーシブ・メッセージの内容。
            メッセージ先頭の 0xf0 およびメッセージ末尾の 0xf7 を明示的に
            含める必要があります。また、それ以外の各バイトの値は0x7f(127)以下
            である必要があります。
        arbitrary(bool, optional):
            この値が True のときは、`data` の先頭が 0xf0、末尾が 0xf7 で
            なくても、また0x80以上のバイトデータを含んでいてもイベントを
            生成します (デフォルトでは例外を送出します)。
            これは、システム・エクスクルーシブ・メッセージを複数の SysEvEvent
            に分割したり、シンセサイザに任意のメッセージを送る際に使います。
        duration(ticks, optional): イベントリストの duration属性値を
            指定します。
        kwargs: 追加のキーワード引数。コンテキストに同名の属性が存在する
            場合は、その属性値を一時的に変更する指定となります。
            そうでなければ、出力されるイベントに対する追加の属性となります。

    **影響を受ける可能性のあるコンテキスト属性**
        dt, tk, effectors

    Examples:
        ``sc.sysex((0xf0, 0x7e, 0x7f, 0x09, 0x01, 0xf7))  # GM On``

        ``sc.sysex((0xf0, 0x7f, 0x7f, 4, 1, 0, 50, 0xf7))  # Master volume \
= 50``
    """
    data = bytes(data)
    if not arbitrary:
        if len(data) < 2 or data[0] != 0xf0 or data[-1] != 0xf7:
            raise ValueError("Missing sysex header(F0)/footer(F7) bytes")
        elif any(b >= 0x80 for b in data[1:-1]):
            raise ValueError("Sysex data bytes must be less than 0x80")
    return _apply_effectors(
        EventList([SysExEvent(0, data, **_getparams(kwargs))], duration))


def meta(mtype, data, *, duration=0, **kwargs) -> EventList:
    """ MetaEvent を含む EventList を生成します。

    Args:
        mtype (int): メタイベントの種類 (0～127)
        data(bytes, bytearray, str, Key, or iterable of int):
            :class:`.MetaEvent` の value 属性の値。
        duration(ticks, optional): イベントリストの duration属性値を
            指定します。
        kwargs: 追加のキーワード引数。コンテキストに同名の属性が存在する
            場合は、その属性値を一時的に変更する指定となります。
            そうでなければ、出力されるイベントに対する追加の属性となります。

    **影響を受ける可能性のあるコンテキスト属性**
        dt, tk, effectors
    """
    return _apply_effectors(
        EventList([MetaEvent(0, mtype, data, **_getparams(kwargs))], duration))


def seqno(value, **kwargs) -> EventList:
    """ シーケンス番号のイベント (mtype=0 のメタイベント) を含むEventList を
    生成します。

    Args:
        value(int): シーケンス番号 (0-65535)
        kwargs: meta() 関数に渡される他の引数。

    **影響を受ける可能性のあるコンテキスト属性**
        dt, effectors
    """
    return meta(M_SEQNO, bytes((value >> 8, value & 0xff)), **kwargs)


def title(string, **kwargs) -> EventList:
    """ 汎用テキストのイベント (mtype=1 のメタイベント) を含む EventList
    を生成します。多くの場合、曲タイトルの記述に使われます。
    トラック番号 (tk属性) は、明示的に指定しない限り、コンテキストによらず
    0 になります。

    Args:
        string(str): テキスト文字列
        kwargs: meta() 関数に渡される他の引数。

    **影響を受ける可能性のあるコンテキスト属性**
        dt, effectors
    """
    with newcontext(tk=0):
        return meta(M_TEXT, string, **kwargs)


def comment(string, **kwargs) -> EventList:
    """ 汎用テキストのイベント (mtype=1 のメタイベント) を含む EventList
    を生成します。:func:`title` と異なり、トラック番号はコンテキストのtk属性の
    値になります。``meta(1, string, **kwargs)`` と等価です。"""
    return meta(M_TEXT, string, **kwargs)


def copyright(string, **kwargs) -> EventList:
    """ 著作権表示のイベント (mtype=2 のメタイベント) を含む EventList
    を生成します。トラック番号 (tk属性) は、明示的に指定しない限り、
    コンテキストによらず 0 になります。

    Args:
        string(str): テキスト文字列
        kwargs: meta() 関数に渡される他の引数。

    **影響を受ける可能性のあるコンテキスト属性**
        dt, effectors
    """
    with newcontext(tk=0):
        return meta(M_COPYRIGHT, string, **kwargs)


def trackname(string, **kwargs) -> EventList:
    """ トラック名のイベント (mtype=3 のメタイベント) を含む EventList
    を生成します。``meta(3, string, **kwargs)`` と等価です。"""
    return meta(M_TRACKNAME, string, **kwargs)


def instname(string, **kwargs) -> EventList:
    """ 楽器名のイベント (mtype=4 のメタイベント) を含む EventList
    を生成します。``meta(4, string, **kwargs)`` と等価です。"""
    return meta(M_INSTNAME, string, **kwargs)


def lyric(string, **kwargs) -> EventList:
    """ 歌詞のイベント (mtype=5 のメタイベント) を含む EventList
    を生成します。``meta(5, string, **kwargs)`` と等価です。"""
    return meta(M_LYRIC, string, **kwargs)


def marker(string, **kwargs) -> EventList:
    """ マーカーイベント (mtype=6 のメタイベント) を含む EventList
    を生成します。
    トラック番号 (tk属性) は、明示的に指定しない限り、コンテキストによらず
    0 になります。

    Args:
        string(str): マーカー文字列
        kwargs: meta() 関数に渡される他の引数。

    **影響を受ける可能性のあるコンテキスト属性**
        dt, effectors
    """
    with newcontext(tk=0):
        return meta(M_MARK, string, **kwargs)


def chprefix(value, **kwargs) -> EventList:
    """ MIDIチャネルプレフィックスのイベント (mtype=0x20 のメタイベント)
    を含むEventList を生成します。``meta(0x20, bytes((value,)), **kwargs)`` と
    等価です。"""
    return meta(M_CHPREFIX, bytes((value,)), **kwargs)


def devno(value, **kwargs) -> EventList:
    """ デバイス(ポート)番号指定のイベント (mtype=0x21 のメタイベント) を含む
    EventList を生成します。``meta(0x21, bytes((value,)), **kwargs)`` と
    等価です。"""
    return meta(M_DEVNO, bytes((value,)), **kwargs)


def trackend(**kwargs) -> EventList:
    """ トラックの終りを表すイベント (mtype=0x2f のメタイベント) を含む
    EventList を生成します。``meta(0x2f, b'', **kwargs)`` と等価です。"""
    return meta(M_EOT, b'', **kwargs)


def timesig(num, den, cc=None, *, duration=0, **kwargs) -> EventList:
    """ 拍子イベント (mtype=0x58 のメタイベント) を含む EventList を
    生成します。
    トラック番号 (tk属性) は、明示的に指定しない限り、コンテキストによらず
    0 になります。

    Args:
        num(int): 分子の値
        den(int): 分母の値
        cc(int, optional): メトロノームクリックの間隔
            (:class:`.KeySignatureEvent` を参照)。
        duration(ticks, optional): イベントリストの duration属性値を
            指定します。
        kwargs: 追加のキーワード引数。コンテキストに同名の属性が存在する
            場合は、その属性値を一時的に変更する指定となります。
            そうでなければ、出力されるイベントに対する追加の属性となります。

    **影響を受ける可能性のあるコンテキスト属性**
        dt, effectors

    Examples:
        ``sc.timesig(4,4)   sc.timesig(5,8)``
    """
    with newcontext(tk=0):
        return _apply_effectors(
            EventList([TimeSignatureEvent(0, num, den, cc,
                                          **_getparams(kwargs))], duration))


def keysig(keydesc, minor=0, **kwargs) -> EventList:
    """ 調号イベント (mtype=0x59 のメタイベント) を含む EventList を
    生成します。
    トラック番号 (tk属性) は、明示的に指定しない限り、コンテキストによらず
    0 になります。

    Args:
        keydesc(int, str, or Key): 調の指定 (:class:`.Key` を参照)
        minor(int, optional): モードの指定 (:class:`.Key` を参照)
        kwargs: meta() 関数に渡される他の引数。

    **影響を受ける可能性のあるコンテキスト属性**
        dt, effectors

    Examples:
        ``sc.keysig('Eb-major')   sc.keysig(0)``
    """
    key = Key(keydesc, minor)
    with newcontext(tk=0):
        return meta(M_KEYSIG, key, **kwargs)


def xml(xtype, value, *, duration=0, **kwargs) -> EventList:
    """ XmlEvent (五線譜のための追加情報イベント）を含む EventList を
    生成します。情報の種類の一覧については :class:`.XmlEvent` を見てください。

    Args:
        xtype(str): 情報の種類を表す文字列
        value: 情報の内容データ
        duration(ticks, optional): イベントリストの duration属性値を
            指定します。

    **影響を受ける可能性のあるコンテキスト属性**
        dt, tk, effectors
    """
    if xtype == 'clef':
        if value.lower() not in \
           ('g', 'f', 'c', 'percussion', 'tab', 'jianpu', 'none'):
            raise ValueError("Invalid clef type %r" % (value,))
    elif xtype == 'barline':
        if (value.lower() not in
            ('dashed', 'dotted', 'heavy', 'heavy-heavy', 'heavy-light',
             'light-heavy', 'light-light', 'none', 'regular', 'short',
             'tick', 'double', 'final', 'repeat-start', 'repeat-end')):
            raise ValueError("Invalid barline type %r" % (value,))
    elif xtype == 'chord':
        if isinstance(value, str):
            value = Chord(value)
        elif not isinstance(value, Chord):
            raise TypeError("Bad data type for a chord")
    elif xtype == 'text':
        if not isinstance(value, str):
            raise TypeError("Bad data type for a text")
    else:
        raise Exception("Unknown XmlEvent type %r" % (xtype,))

    return _apply_effectors(
        EventList([XmlEvent(0, xtype, value, **_getparams(kwargs))], duration))


# モジュールで定義された関数を自動的に __all__ に含める
__all__.extend([name for name, value in globals().items()
                if name[0] != '_' and callable(value) and
                value.__module__ == 'takt.sc'])


# 関数をContextクラスのメソッドとして利用できるようにする
if '__SPHINX_AUTODOC__' not in os.environ:
    for name in __all__:
        exec(f"""
def _Context_{name}(ctxt, *args, **kwargs):
    with ctxt:
        return {name}(*args, **kwargs)
Context.{name} = _Context_{name}""")
