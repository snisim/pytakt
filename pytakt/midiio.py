# coding:utf-8
"""
This module defines functions for real-time MIDI input/output and timers.

.. rubric:: Devices

In Pytakt, devices to send MIDI messages (MIDI interface or application port)
are called output devices, and devices to receive MIDI messages are called
input devices. A list of available devices can be found with the
:func:`show_devices` function. Each device is assigned an integer device
number.

There is a special device called the loopback device (not shown in
:func:`show_devices`). The loopback device is an output device and moreover
an input device, and can receive messages sent to them by itself.
It is normally used for sending and receiving LoopBackEvent's, but can also be
used for other events.

To use a device, it must be opened in advance. However, the loopback device is
always available and does not need to be opened.

For input and output each, there is a currently selected device.
The initial choice of this is platform specific. However, by setting the
environment variables PYTAKT_OUTPUT_DEVICE and PYTAKT_INPUT_DEVICE to a string
recognized by :func:`find_output_device` or :func:`find_input_device`, the
initial choice can be changed.

.. rubric:: Input and Output Queues

Inside the module, there is a queue for storing messages, which are byte
sequences converted from events with :meth:`.Event.to_message`, for input
and output each. Each message is given a timestamp and a track number.
When an event is sent to an output device via the :func:`queue_event` function,
the event is converted to a message, placed in the output queue, and then
kept until the sending time before it is actually sent to the device.
Messages from input devices are first placed in the input queue, where they
are kept until retrieved by the :func:`recv_event` function. There is no limit
on the size of the queues.

.. rubric:: Timer

The module has a timer that indicates the time since the module was imported.
The unit of time is the tick (a floating-point value equal to 1/480th of a
quarter note), and the relationship between seconds and ticks is determined
by two values: tempo (beats per minute, BPM) and tempo scale, with the
following formula:

    ticks = seconds * tempo * tempo_scale / 60 * 480

By default, the tempo is set to 125 BPM and the tempo scale is set to 1,
thus establishing the relationship 1 tick = 1 msec.
Tempo can be changed dynamically by sending a :class:`.TempoEvent` to any of
the output devices, and the tempo scale can be changed by calling the
:func:`set_tempo_scale` function.
"""
"""
このモジュールにはリアルタイムMIDI入出力、およびタイマのための関数が
定義されています。

.. rubric:: デバイス

PytaktではMIDIメッセージの送信の対象となるもの（MIDIインタフェースや
アプリケーションポート) を出力デバイス、受信の対象となるものを入力デバイス
と呼んでいます。使用できるデバイスの一覧は :func:`show_devices` 関数で
確認できます。各デバイスには整数のデバイス番号が割り振られています。

特殊なデバイスとして、ループバックデバイスが用意されています
(:func:`show_devices` では表示されません)。
ループバックデバイスは出力デバイスかつ入力デバイスであり、
送られたメッセージを自分自身で受け取ることができます。
通常はLoopBackEventの送受に利用されますが、
それ以外のイベントについて利用することも可能です。

デバイスを使用するには予めオープンする必要があります。
ただし、ループバックデバイスは常に使用可能で、オープンの必要はありません。

入力、出力デバイスのそれぞれに、現在選択されているデバイスが存在します。
これの初期値はプラットフォームごとに決まっています。ただし、
環境変数 PYTAKT_OUTPUT_DEVICE や PYTAKT_INPUT_DEVICE に
:func:`find_output_device` や :func:`find_input_device` で認識できるような
文字列を設定することで、初期値を変えることができます。

.. rubric:: 入出力キュー

モジュール内部には、入力と出力のそれぞれに、メッセージ (イベントを
:meth:`.Event.to_message` メソッドで変換したバイト列) を蓄えるためのキューが
あります。各メッセージにはタイムスタンプとトラック番号が付与されています。
:func:`queue_event` 関数によってイベントを出力デバイスへ送ると、イベントは
メッセージに変換されたのちにまず出力キューへ置かれ、送出時刻に
なるまで待ってから実際にデバイスへ送出されます。入力デバイスからのメッセージ
は入力キューにまず置かれ、:func:`recv_event` 関数によって取り出されるまで
そこで保管されます。キューの容量制限は特にありません。

.. rubric:: タイマ

モジュールには、モジュールをインポートしたときからの時間を表すタイマ
が備わっています。時間の単位はティック (4分音符の480分の1に相当する
浮動小数点の値) で、秒とティックとの関係はテンポ (beat per minute, BPM) と
テンポスケールという2つの値により下の式によって決定されます。

    ticks = seconds * テンポ * テンポスケール / 60 * 480

初期状態ではテンポは125、テンポスケールは1に設定されており、
これにより 1 tick = 1 msec という関係が成り立っています。
テンポは :class:`.TempoEvent` を出力デバイスのどれかに送ることによって、
またテンポスケールは :func:`set_tempo_scale` 関数を呼ぶことによって、
動的に変更できます。
"""
# Copyright (C) 2025  Satoshi Nishimura

import os
import itertools
from typing import List, Optional
import pytakt.cmidiio as _cmidiio
from pytakt.event import NoteEvent, NoteEventClass, CtrlEvent, SysExEvent, \
     MetaEvent, TempoEvent, LoopBackEvent, Event, message_to_event
from pytakt.pitch import Pitch
from pytakt.constants import TICKS_PER_QUARTER
from pytakt.score import Score, EventList, EventStream, RealTimeStream, Tracks
from pytakt.mml import mml
from pytakt.timemap import _current_tempo_value
import pytakt.frameutils

__all__ = ['DEV_DUMMY', 'DEV_LOOPBACK']  # extended later


try:
    # Windows の jupyter notebook では、interrupt動作を行ってもカーネルプロセス
    # へシグナル(SIGINT)が送られない。下のコードは、かわりに送られる Windows
    # イベントに対して、その受信ハンドラに細工をすることで、recv_message を
    # 停止させるようにしている。
    os.environ['JPY_INTERRUPT_EVENT']
    from ipykernel import parentpoller
    import _thread

    def _jupyter_interrupt():
        _cmidiio._interrupt_recv_message()
        _thread.interrupt_main()

    parentpoller.interrupt_main = _jupyter_interrupt
except (KeyError, ModuleNotFoundError, ImportError):
    pass


DEV_DUMMY = -1
DEV_LOOPBACK = -2


_output_devnum = DEV_DUMMY
_input_devnum = DEV_DUMMY


_loopback_events = {}  # 送出されてから受信されるまでLoopBackEventを保管
_loopback_count = itertools.count()


# _play_rec の callback の中で stop() が呼ばれたときに _play_rec を抜ける
# ために設定されるフラグ
_stop_request = False


def current_output_device() -> int:
    """ Returns the device number of the currently selected output device. """
    """ 現在選択されている出力デバイスの番号を返します。 """
    return _output_devnum


def current_input_device() -> int:
    """ Returns the device number of the currently selected input device. """
    """ 現在選択されている入力デバイスの番号を返します。 """
    return _input_devnum


def _find_device(dev, devices):
    if isinstance(dev, str):
        devlist = dev.split(';')
    elif isinstance(dev, list) or isinstance(dev, tuple):
        devlist = dev
    else:
        devlist = (dev,)
    for d in devlist:
        devnum = None
        if isinstance(d, int):
            devnum = d
        elif isinstance(d, str):
            if d.strip() == '':
                continue
            try:
                devnum = int(d)
            except ValueError:
                try:
                    devnum = [i for i, devname in enumerate(devices)
                              if devname.find(d) != -1][0]
                except IndexError:
                    pass
        if devnum is not None and DEV_DUMMY <= devnum < len(devices):
            return devnum
    raise ValueError("No such device: %r" % (dev,)) from None


def find_output_device(dev) -> int:
    """
    Get the output device number based on a device description.

    Args:
        dev(int, str, list, tuple): Device description. If it is an integer,
            it is recognized as the device number. If it is a string
            representing an integer, it is converted to an integer, which is
            then recognized as the device number. For other forms of a string,
            it means a device where the string matches all or part of its
            device name (and whichever has the smallest device number if there
            are multiple matched devices).
            The string may be multiple device descriptions separated by
            semicolons, in which case the first one whose existence is
            confirmed is valid.
            If the argument is a list or tuple where each element is an
            integer or a string without a semicolon, it is examined starting
            from the first element in the same manner as a single element,
            and the first device whose existence is confirmed becomes valid.
            If no device is found, an exception is raised.

    Returns:
        Output device number

    Examples:
        - ``find_output_device(1)``
        - ``find_output_device('1')``
        - ``find_output_device('TiMidity; MIDI Mapper')``
        - ``find_output_device([2, 0])``
    """
    """
    デバイスの記述をもとに、出力デバイス番号を取得します。

    Args:
        dev(int, str, list, tuple): デバイスの記述。整数の場合は、それが
            そのままデバイス番号になります。整数を表す文字列の場合は、それが
            整数に変換されてデバイス番号となります。それ以外の文字列の場合は、
            デバイス名の全部または一部がそれと一致するデバイス(複数ある場合は
            デバイス番号の小さい方)を意味します。文字列はセミコロンで区切った
            複数のデバイス記述でも良く、その場合最初に存在を確認できたものが
            有効になります。リストまたはタプルの場合、各要素は整数または
            セミコロンを含まない文字列であり、先頭から順番に単独の場合と同じ
            ように調べられ、最初にデバイスの存在を確認できたものが有効になり
            ます。
            存在を確認できるデバイスがなかった場合には、例外が送出されます。

    Returns:
        出力デバイス番号

    Examples:
        - ``find_output_device(1)``
        - ``find_output_device('1')``
        - ``find_output_device('TiMidity; MIDI Mapper')``
        - ``find_output_device([2, 0])``
    """
    return _find_device(dev, output_devices())


def output_devices() -> List[str]:
    """ Get a list of the device names of all the output devices. """
    """ すべての出力デバイスの名前のリストを取得します。 """
    return _cmidiio.output_devices()


def set_output_device(dev) -> None:
    """ Specifies `dev` as the currently selected output device.

    Args:
        dev: Device description recognized by :func:`find_output_device`.
    """
    """ `dev` を　"現在選択されている出力デバイス" として指定します。

    Args:
        dev: :func:`find_output_device` によって認識可能なデバイス記述。
    """
    global _output_devnum
    _output_devnum = find_output_device(dev)


def open_output_device(dev=None) -> None:
    """
    Open the output device `dev`.
    This may take a little time depending on the device.

    Args:
        dev: Target output device. If None, the currently selected output
            device is used; otherwise, the target device is the result of
            calling :func:`find_output_device` with this as an argument.
    """
    """ 出力デバイス `dev` をオープンします。

    デバイスによっては少し時間がかかる場合があります。

    Args:
        dev: 対象となる出力デバイス。Noneの場合は現在選択されている
            出力デバイス、それ以外の場合はこれを引数として
            :func:`find_output_device` を呼んだ結果が対象のデバイス
            となります。
    """
    devnum = _output_devnum if dev is None else find_output_device(dev)
    _cmidiio._open_output_device(devnum)


def close_output_device(dev=None) -> None:
    """ Close the output device `dev`.

    Args:
        dev: Target output device. If None, the currently selected output
            device is used; otherwise, the target device is the result of
            calling :func:`find_output_device` with this as argument.
    """
    """ 出力デバイス `dev` をクローズします。

    Args:
        dev: 対象となる出力デバイス。Noneの場合は現在選択されている
            出力デバイス、それ以外の場合はこれを引数として
            :func:`find_output_device` を呼んだ結果が対象のデバイス
            となります。
    """
    devnum = _output_devnum if dev is None else find_output_device(dev)
    _cmidiio._close_output_device(devnum)


def is_opened_output_device(dev) -> bool:
    """ Returns true if the output device `dev` is opened, or false otherwise.

    Args:
        dev: Device description that can be recognized by
            :func:`find_output_device`.
    """
    """ 出力デバイス `dev` がオープンされていれば True、そうでなければ
    False を返します。

    Args:
        dev: :func:`find_output_device` によって認識可能なデバイス記述。
    """
    return _cmidiio._is_opened_output_device(find_output_device(dev))


def find_input_device(dev) -> int:
    """
    Get the input device number based on a device description.

    Args:
        dev(int, str, list, tuple): Device description in the same format as
            :func:`find_output_device`.
    """
    """
    デバイスの記述をもとに、入力デバイス番号を取得します。

    Args:
        dev(int, str, list, tuple): :func:`find_output_device` と同じ形式の
            デバイス記述。
    """
    return _find_device(dev, input_devices())


def input_devices() -> List[str]:
    """ Get a list of the device names of all the input devices. """
    """ すべての入力デバイスの名前のリストを取得します。 """
    return _cmidiio.input_devices()


def set_input_device(dev) -> None:
    """ Specifies `dev` as currently selected input device.

    Args:
        dev: Device description recognized by :func:`find_intput_device`.
    """
    """ `dev` を　"現在選択されている入力デバイス" として指定します。

    Args:
        dev: :func:`find_intput_device` によって認識可能なデバイス記述。
    """
    global _input_devnum
    _input_devnum = find_input_device(dev)


def open_input_device(dev=None) -> None:
    """ Open the input device `dev`.

    The input device inserts received messages into the input queue only while
    it is open, and discards messages while it is closed. To avoid unintended
    message accumulation in the input queue, openings should be limited to the
    necessary period of time.

    Args:
        dev: Target input device. If None, the currently selected input device
            is used; otherwise, the target device is the result of calling
            :func:`find_input_device` with this as an argument.
    """
    """ 入力デバイス `dev` をオープンします。

    入力デバイスはオープンしている期間のみ受信したメッセージを入力キューに
    挿入し、クローズ中はメッセージを破棄します。入力キューに意図しない
    メッセージが溜まるのを避けるため、オープンは必要な期間のみに
    限定する必要があります。

    Args:
        dev: 対象となる入力デバイス。Noneの場合は現在選択されている
            入力デバイス、それ以外の場合はこれを引数として
            :func:`find_input_device` を呼んだ結果が対象のデバイス
            となります。
    """
    devnum = _input_devnum if dev is None else find_input_device(dev)
    _cmidiio._open_input_device(devnum)


def close_input_device(dev=None) -> None:
    """ Close the input device `dev`.

    Args:
        dev: Target input device. If None, the currently selected input device
            is used; otherwise, the target device is the result of calling
            :func:`find_input_device` with this as argument.
    """
    """ 入力デバイス `dev` をクローズします。

    Args:
        dev: 対象となる入力デバイス。Noneの場合は現在選択されている
            入力デバイス、それ以外の場合はこれを引数として
            :func:`find_input_device` を呼んだ結果が対象のデバイス
            となります。
    """

    devnum = _input_devnum if dev is None else find_input_device(dev)
    _cmidiio._close_input_device(devnum)


def is_opened_input_device(dev) -> bool:
    """ Returns true if the input device `dev` is opened, or false otherwise.

    Args:
        dev: Device description that can be recognized by
            :func:`find_input_device`.
    """
    """ 入力デバイス `dev` がオープンされていれば True、そうでなければ
    False を返します。

    Args:
        dev: :func:`find_input_device` によって認識可能なデバイス記述。
    """
    return _cmidiio._is_opened_input_device(find_input_device(dev))


def show_devices() -> None:
    """ Show the list of all the available devices. """
    """ 利用可能なデバイスの一覧を表示します。 """
    print("MIDI Output Devices:")
    odev = output_devices()
    for i, devname in enumerate(odev):
        print(" %c %c[%d] %s" % ('>' if i == _output_devnum else ' ',
                                 '*' if is_opened_output_device(i) else ' ',
                                 i, devname))
    if not odev:
        print("  Not available")
    print("\nMIDI Input Devices:")
    idev = input_devices()
    for i, devname in enumerate(idev):
        print(" %c %c[%d] %s" % ('>' if i == _input_devnum else ' ',
                                 '*' if is_opened_input_device(i) else ' ',
                                 i, devname))
    if not idev:
        print("  Not available")
    print("\n'*': opened   '>': currently selected")


def current_time() -> float:
    """ Returns the current time.

    Returns:
        Time in ticks, being 0 when the module was imported.
    """
    """ 現在の時刻を返します。

    Returns:
        モジュールがimportされた時を0としたティック単位の時刻。
    """
    return _cmidiio.current_time()


def _current_tempo() -> float:
    """ Returns the current tempo.

    Returns:
        Tempo value (beats per minute).
    """
    """ 現在のテンポを返します。

    Returns:
        テンポ値 (beats per minute)
    """
    return _cmidiio.current_tempo()


def _set_tempo(bpm) -> None:
    """ Changes the current tempo.

    Args:
        bpm(float): Tempo value (beats per minute)
    """
    """ 現在のテンポを変更します。

    Args:
        bpm(float): テンポ値 (beats per minute)
    """
    t = current_time()
    _cmidiio.queue_message(DEV_DUMMY, t, 0, TempoEvent(t, bpm).to_message())


def current_tempo_scale() -> float:
    """ Returns the current tempo scale value.

    Returns:
        Tempo scale value
    """
    """ 現在のテンポスケールを返します。

    Returns:
        テンポスケール値
    """
    return _cmidiio.current_tempo_scale()


def set_tempo_scale(tempo_scale) -> None:
    """ Changes the tempo scale value.

    Args:
        tempo_scale(float): tempo scale value (non-negative)
    """
    """ テンポスケールを変更します。

    Args:
        tempo_scale(float): テンポスケール値 (非負)
    """
    _cmidiio.set_tempo_scale(tempo_scale)


def queue_event(ev, time=None, devnum=None) -> None:
    """
    Converts an event to a message (a sequence of bytes) and places the message
    with its sending time and track number on the output queue. The message is
    sent to the output device when the sending time is reached.
    There is no blocking (waiting for output) in this function.

    Note: When queuing a TempoEvent for a tempo change, the sending time must
    not be earlier than the current time.

    Args:
        ev(Event): The event to queue. This is converted to a message by the
            :meth:`.Event.to_message` method and placed on the output queue.
            If `ev` is a NoteEvent, two messages, one for note-on and the other
            for note-off, are placed (the sending time of note-off is that of
            note-on plus the value of the 'du' attribute if it exists or
            the L attribute otherwise).
            Even if the event is updated after calling this function, the
            queued message is not affected.
        time(ticks, optional): Specifies the time (in ticks) at which the
            message is sent. If not specified, the value of the 't' attribute
            of `ev` is used.
        devnum(int, optional): Specifies the output device number to which
            the message will be sent. If not specified, the currently selected
            output device is used.
            If `ev` is a LoopBackEvent, the message is always sent to the
            loopback device regardless of this value.
    """
    """
    イベントをメッセージ (バイト列) に変換した上で、そのメッセージを送出時刻と
    トラック番号とともに出力キューへ置きます。置かれたメッセージは
    その送出時刻に達すると出力デバイスへ送られます。
    この関数でのブロック (出力待ち) はありません。

    注意: テンポ変更のため TempoEvent をキューする場合は、送出時刻が現時刻
    より過去であってはなりません。

    Args:
        ev(Event): キューするイベント。これは、:meth:`.Event.to_message`
            メソッドによりメッセージに変換されて、出力キューに置かれます。
            `ev` が NoteEvent の場合は、ノートオンとノートオフの2つの
            メッセージが置かれます（このとき、ノートオフの送出時刻は
            ノートオンの送出時刻に対して、`ev` がdu属性を持つならその値、
            無ければL属性の値を加えたものとなります）。
            この関数を呼び出した後にイベントを書き換えても
            キュー中のメッセージには影響を与えません。
        time(ticks, optional): メッセージ送出時刻(ティック単位)を
            指定します。指定しない場合は、`ev` が持つt属性の値になります。
        devnum(int, optional):
            メッセージを送る出力デバイス番号を指定します。指定しない場合は、
            現在選択されている出力デバイスとなります。
            `ev` が LoopBackEvent であったときには、この値にかかわらず
            必ずループバックデバイスへ送られます。
    """
    if time is None:
        time = ev.t
    if isinstance(ev, LoopBackEvent):
        seqno = next(_loopback_count)
        # 他の種類のメッセージは先頭バイトが0x80以上なので区別可能。
        _cmidiio.queue_message(DEV_LOOPBACK, time, ev.tk, str(seqno).encode())
        _loopback_events[seqno] = ev
    else:
        if devnum is None:
            devnum = _output_devnum
        if isinstance(ev, NoteEvent):
            _cmidiio.queue_message(devnum, time, ev.tk, ev.to_message()[0:3])
            _cmidiio.queue_message(devnum, time + ev.get_du(),
                                   ev.tk, ev.to_message()[3:])
        else:
            _cmidiio.queue_message(devnum, time, ev.tk, ev.to_message())


def recv_ready() -> bool:
    """
    Returns true if there is a message on the input queue, or false otherwise.
    If this value is true, it is guaranteed that the next call to
    :func:`recv_event` will not be blocked.
    """
    """
    入力キューにメッセージがあれば True, そうでなければ False を返します。
    この値が True であれば、次に :func:`recv_event` を呼んだときにブロック
    状態にならないことが保証されます。
    """
    return _cmidiio.recv_ready()


def recv_event() -> Optional[Event]:
    """
    Receives a message from an input device and returns it as an event.
    All the opened input devices are subject for receiving.
    If there is no message in the input queue, it enters a blocking state
    and waits for the input.
    Execution is resumed whtn a message arrives or a keyboard interrupt
    is received.

    If a message from the loopback device and a message from a normal input
    device arrive almost at the same time, the order of receiving may be
    different from the order of event times.

    System messages other than exclusive messages are ignored and cannot be
    received.

    Returns:
        The event converted from the received message. Its 't' attribute value
        is the time the message was received. Returns None when a keyboard
        interrupt is received.
    """
    """
    入力デバイスからのメッセージを受け取りイベントとして返します。
    すべてのオープンされている入力デバイスが対象となります。
    入力キューにメッセージが無いときはブロック(入力待ち)状態になります。
    ブロックはメッセージが到着するか、キーボード・インタラプトを受けると
    解除されます。

    ループバックデバイスからのメッセージと通常の入力デバイスからのメッセージが
    ほぼ同時刻に到着した場合、その受け取り順序がイベントの時刻順にならないこと
    があります。

    エクスクルーシブ・メッセージ以外のシステム・メッセージは無視され、
    受け取ることができません。

    Returns:
        受け取ったメッセージを変換したイベント。そのt属性は
        メッセージを受け取った時刻になっています。キーボード・インタラプトを
        受けたときは None を返します。
    """
    # 今のところ、recv_eventではdevnumの情報を得る手段がない。
    # devnumからtkへのdict指定してtkに反映させるようにしたら良いかもしれない。
    (devnum, ticks, tk, msg) = _cmidiio.recv_message()
    if not msg:
        return None  # keyboard interrupt while receiving
    elif msg[0] < 0x80:
        try:
            return _loopback_events.pop(int(msg.decode()))
        except KeyError:
            raise Exception("Received a corrupted loop-back event")
    else:
        ev = message_to_event(msg, ticks, tk)
        if hasattr(ev, 'n'):
            ev.n = Pitch(ev.n)
        return ev


def cancel_events(tk=-1, devnum=None) -> None:
    """
    Performs the following two operations on the specified track of the
    specified device.

        1. Delete all messages in the output queue.
        2. Sends messages to turn off the notes being played and the sustain
           pedal in use.

    Args:
        tk(int, optional):
            Specifies the target track number. A value of -1 means all tracks.
        devnum(int, optional):
            Specifies the target output device number. If not specified,
            the currently selected output device is used.
            The loopback device cannot be specified.
    """
    """
    指定されたデバイスの指定されたトラックに対して、以下の2つの
    操作を行います。

        1. 出力キューに入っているメッセージをすべて削除します。
        2. 発音中のノートおよび使用中のサスティンペダルに対してそれらを
           オフにするメッセージを送ります。

    Args:
        tk(int, optional):
            対象となるトラック番号を指定します。-1 を指定すると、全ての
            トラックの意味になります。
        devnum(int, optional):
            対象となる出力デバイス番号を指定します。指定しない場合は、
            現在選択されている出力デバイスとなります。ループバックデバイスは
            指定できません。
    """
    if devnum is DEV_LOOPBACK:
        # 実は今の実装でもまだ送出時刻に達していないものに限り削除できるが、
        # 削除されるかどうかが不確定なのは役立ちそうもない。
        raise Exception("Loop-back events cannot be canceled")
    _cmidiio.cancel_messages(_output_devnum if devnum is None else devnum, tk)


def stop() -> None:
    """
    Deletes all messages in the input and output queues, as well as sends
    messages to turn off the notes being played and the sustain pedal in use.
    In addition, it will send the MIDI message below to all channels of all
    opened output devices, attempting to completely stop all sound from the
    synthesizers.

        - All notes off (control change #123)
        - Sustain pedal control with value 0 (control change #64)
        - All sounds off (control change #120)

    This function is automatically called when a keyboard interrupt is
    received with this module imported.
    """
    """
    入出力キューに入っているすべてのメッセージを削除するとともに、
    発音中のノートおよび使用中のサスティンペダルに対してそれらをオフにする
    メッセージを送ります。
    さらに、下のMIDIメッセージをすべてのオープンされている出力デバイスの
    すべてのチャネルに送り、シンセサイザからの発音の完全停止を試みます。

        - オール・ノート・オフ (123番のコントロールチェンジ)
        - 値が0のサスティン・ペダル・コントロール (64番のコントロールチェンジ)
        - オール・サウンド・オフ (120番のコントロールチェンジ)

    このモジュールをインポートした状態でキーボードインタラプトを受けた
    ときにはこの関数が自動的に呼ばれます。
    """
    global _stop_request
    _cmidiio.stop()
    _loopback_events.clear()
    _stop_request = True


# もたつきを防ぐため先読みする時間幅。少なくとも MAX_DELTA_TIME*2 より大きい
# 必要がある。
_QUEUE_LOOK_AHEAD = TICKS_PER_QUARTER * 16

_METRONOME_TRACK = 65536

_KEYBOARD_INTERRUPT_RERAISING_PERIOD = 100  # msec


def _play_rec(score, rec=False, outdev=None, indev=None, metro=None,
              monitor=False, callback=None):
    global _stop_request
    # score が EventStream である場合、playやrecordがリターンするのは
    # Keybordinterruptのみ。
    devnum = _output_devnum if outdev is None else find_output_device(outdev)
    indevnum = DEV_DUMMY
    if rec:
        indevnum = _input_devnum if indev is None else find_input_device(indev)
    open_output_device(devnum)  # may take some seconds
    open_input_device(indevnum)
    _stop_request = False
    if score is None:
        score = EventList()
        isstream = False
    else:
        isstream = isinstance(score, EventStream)
        if isstream and score.is_consumed():
            raise Exception('play: Input stream has already been consumed')
        if not isstream:
            score = Tracks([score,
                            EventList([LoopBackEvent(score.get_duration(),
                                                     'done')], 0)])
    if metro:
        score = score & metro.mapev(
            lambda ev: ev.copy().update(tk=_METRONOME_TRACK))
    event_stream = score.ConnectTies().stream()
    tempo_scale_save = current_tempo_scale()
    recevlist = EventList()

    def resume_tempo_scale():
        nonlocal tempo_scale_save
        if tempo_scale_save is not None:
            set_tempo_scale(tempo_scale_save)
        tempo_scale_save = None

    done = False

    if isinstance(score, RealTimeStream):
        toffset = score.starttime
    else:
        # 出だしのもたつきを防ぐため、tempo_scale を 0 にする。
        set_tempo_scale(0)
        while current_tempo_scale() > 0:
            pass  # スレッドが切り替わって tempo-scale が更新されるまで待つ
        toffset = current_time()

    if callback is not None:
        queue_event(LoopBackEvent(toffset, 'callback'))

    try:
        while True:
            try:
                ev = next(event_stream)
                # qt はキューに入れるべきシステム時刻
                qt = ev.t - _QUEUE_LOOK_AHEAD + toffset
            except StopIteration as e:
                if isstream and not isinstance(score, RealTimeStream):
                    queue_event(LoopBackEvent(e.value, 'done'),
                                e.value + toffset)
                ev = None
            if isinstance(score, RealTimeStream):
                if ev is None:
                    done = True
            else:
                if ev is None or (isstream and qt >= current_time()):
                    resume_tempo_scale()
                    if ev is not None:
                        queue_event(LoopBackEvent(qt, 'next'))
                    while True:
                        rev = recv_event()
                        if isinstance(rev, LoopBackEvent):
                            if rev.value == 'next':
                                break
                            elif rev.value == 'done':
                                recevlist.duration = rev.t
                                cancel_events(_METRONOME_TRACK, devnum)
                                done = True
                                break
                            elif rev.value == 'callback':
                                callback(rev)
                                if _stop_request:
                                    recevlist.duration = rev.t
                                    done = True
                                    break
                        elif rec:
                            if monitor:
                                queue_event(rev, devnum=devnum)
                            recevlist.append(rev)
            if done:
                break
            if isinstance(ev, (NoteEventClass, CtrlEvent, MetaEvent,
                               SysExEvent, LoopBackEvent)):
                queue_event(ev, ev.t + ev.dt + toffset, devnum)

    except KeyboardInterrupt:
        stop()
        recevlist.duration = current_time() - toffset
        # The following print() avoids command-line corruption by '^C'
        print(f"{'record' if rec else 'play'} interrupted")

        # To avoid the problem that programs like "while True: mml('c').play()"
        # can never be terminated by pressing Ctrl-C, we re-raise
        # KeyboardInterrupt for a short period after starting play()/record().
        if current_time() < toffset + _KEYBOARD_INTERRUPT_RERAISING_PERIOD:
            raise
    finally:
        resume_tempo_scale()
        close_input_device(indevnum)

    if rec:
        for ev in recevlist:
            ev.t = max(0, ev.t - toffset)
        return recevlist


def play(score, dev=None, callback=None) -> None:
    """
    Plays a score. Messages are sent to the output device in sequence
    according to the events contained in the score. This function does not
    return until the time corresponding to the duration of the score has
    elapsed, or until a keyboard interrupt is received.

    Args:
        score(Score or str): Score to be played. It may be an infinite-length
            score. If this argument is a string, it is considered as MML.
        dev: Target output device. If None, the currently selected output
            device is used; otherwise, the target device is the result of
            calling :func:`find_output_device` with this as argument.
            If the specified device is not opened, it will be opened
            automatically.
        callback(function, optional):
            Given a function taking a single argument (a callback function),
            it will be called at the beginning of the playback.
            A loopback event is passed as the argument. By updating the time
            of the event and inserting it to the output queue using
            :func:`queue_event` within the callback function, it is possible
            to schedule the callback function to be called again at that time.
    """
    """
    スコアを再生します。スコアに含まれるイベントに従って順にメッセージを出力
    デバイスへ送ります。この関数は、スコアの演奏長に相当する時間が経過するか、
    あるいはキーボード・インタラプトを受けるまでリターンしません。

    Args:
        score(Score or str): 演奏対象のスコア。無限長スコアであっても
            構いません。この引数が文字列の場合はMMLだと見なされます。
        dev: 対象となる出力デバイス。Noneの場合は現在選択されている
            出力デバイス、それ以外の場合はこれを引数として
            :func:`find_output_device` を呼んだ結果が対象のデバイス
            となります。
            指定したデバイスがオープンされていないときは、自動的にオープン
            されます。
        callback(function, optional):
            単一の引数を取る関数(コールバック関数)を指定すると、再生開始時に
            それが呼び出されます。引数にはループバックイベントが渡され、
            そのイベントをコールバック関数内で時刻を更新して
            :func:`queue_event` で出力キューに挿入すれば、その時刻に再び
            コールバック関数が呼ばれるようにスケジュールすることができます。
    """
    if isinstance(score, str):
        score = mml(score, pytakt.frameutils.outerglobals(),
                    pytakt.frameutils.outerlocals())
    _play_rec(score, False, dev, callback=callback)


def record(indev=None, play=None, outdev=None,
           metro=None, monitor=False, callback=None) -> EventList:
    """
    Records a performance from an input device and returns an event list.
    It is also possible to record with a score being played back.
    This function does not return until the time corresponding to the duration
    of the playback score has elapsed, or until a keyboard interrupt is
    received.

    Args:
        indev: Target input device. If None, the currently selected input
            device is used; otherwise, the target device is the result of
            calling :func:`find_input_device` with this as the argument.
            If the specified device is not opened, it will be opened
            automatically. Also, it will be closed when returning from this
            function.
            If another input device other than this device is already open,
            events from that device will be recorded as well.
        play(Score, optional): The score to be played back simultaneously.
            It may be an infinite-length score.
        outdev: The output device for playback. If None, the currently selected
            output device is used; otherwise, the target device is the result
            of calling :func:`find_output_device` with this as the argument.
        metro(str, bool or Score, optional):
            If specified, a metronome will be sounded. The default metronome
            assumes that a GM standard rhythmic instrument is assigned to
            MIDI channel 10.
            This argument can be a string representing a time signature,
            such as "3/4", True (equivalent to "4/4"), or a score to play
            the metronome sound
            (e.g., ``record(metro=mml("ch=10 {A5 {Ab5* Ab5}/3 }@@"))``).
        monitor(bool, optional):
            If True, sends messages from the input device to the output device.
        callback(function, optional):
            Given a function taking a single argument (a callback function),
            it will be called at the beginning of recording.
            A loopback event is passed as the argument. By updating the time
            of the event and inserting it to the output queue using
            :func:`queue_event` within the callback function, it is possible
            to schedule the callback function to be called again at that time.

    Returns:
        Recorded score
    """
    """
    入力デバイスからの演奏を録音してイベントリストを返します。
    スコアを再生しながら録音することもできます。
    この関数は、再生スコアの演奏長に相当する時間が経過するか、
    あるいはキーボード・インタラプトを受けるまでリターンしません。

    Args:
        indev: 対象となる入力デバイス。Noneの場合は現在選択されている
            入力デバイス、それ以外の場合はこれを引数として
            :func:`find_input_device` を呼んだ結果が対象のデバイス
            となります。指定したデバイスがオープンされていないときは、
            自動的にオープンされます。また、関数から戻るときにはクローズ
            されます。
            このデバイス以外の他の入力デバイスが既にオープンされていた場合
            には、そのデバイスからのイベントも一緒に録音されます。
        play(Score, optional): 同時に再生するスコア。
            無限長スコアであっても構いません。
        outdev: 再生するときの出力デバイス。Noneの場合は現在選択されている
            出力デバイス、それ以外の場合はこれを引数として
            :func:`find_output_device` を呼んだ結果が対象のデバイス
            となります。
            指定したデバイスがオープンされていないときは、自動的にオープン
            されます。
        metro(str, bool or Score, optional):
            指定するとメトロノームを鳴らします。標準のメトロノームは、
            MIDIチャンネル10がGM規格のリズム音源であることを仮定しています。
            この引数には、"3/4" のような拍子を表す文字列を指定するか、
            True ("4/4"と同じ意味) を指定するか、あるいはメトロノームを
            鳴らすためのスコアを指定します
            (例: ``record(metro=mml("ch=10 {A5 {Ab5* Ab5}/3}@@"))``)。
        monitor(bool, optional):
            Trueの場合、入力デバイスからのメッセージを出力デバイスへ送ります。
        callback(function, optional):
            単一の引数を取る関数(コールバック関数)を指定すると、録音開始時に
            それが呼び出されます。引数にはループバックイベントが渡され、
            そのイベントをコールバック関数内で時刻を更新して
            :func:`queue_event` で出力キューに挿入すれば、その時刻に再び
            コールバック関数が呼ばれるようにスケジュールすることができます。

    Returns:
        録音されたスコア
    """
    try:
        if metro is True:
            metro = '4/4'
        if isinstance(metro, str):
            d = [int(s) for s in metro.split('/')]
            if len(d) == 2 and d[0] > 0 and \
               d[1] in (1, 2, 4, 8, 16, 32, 64, 128):
                metro = mml('ch=10 L%d {A5 %s}@@' % (d[1], 'Ab5' * (d[0]-1)))
            else:
                raise ValueError()
        elif metro is not None and not isinstance(metro, Score):
            raise ValueError()
    except ValueError:
        raise ValueError("Unrecognized 'metro' argument") from None

    return _play_rec(play, True, outdev, indev, metro, monitor, callback)


def listen(dev=None) -> RealTimeStream:
    devnum = _input_devnum if dev is None else find_input_device(dev)
    open_input_device(devnum)
    toffset = current_time()

    def _listen():
        try:
            while True:
                ev = recv_event()
                if not isinstance(ev, LoopBackEvent):
                    ev.update(t=ev.t-toffset)
                yield ev
        except KeyboardInterrupt:
            print("listen interrupted")
            stop()
            return current_time() - toffset
        finally:
            close_input_device(devnum)

    return RealTimeStream(_listen(), toffset)


def monitor(dev=None) -> None:
    """
    Displays the sequence of events from the input device.
    This function does not return until it receives a keyboard interrupt.

    Args:
        dev: Target input device. If None, the currently selected input
            device is used; otherwise, the target device is the result of
            calling :func:`find_input_device` with this as the argument.
            If the specified device is not opened, it will be opened
            automatically. Also, it will be closed when returning from this
            function.
    """
    """
    入力デバイスからのイベント列を表示します。
    この関数はキーボード・インタラプトを受けるまでリターンしません。

    Args:
        dev: 対象となる入力デバイス。Noneの場合は現在選択されている
            入力デバイス、それ以外の場合はこれを引数として
            :func:`find_input_device` を呼んだ結果が対象のデバイス
            となります。指定したデバイスがオープンされていないときは、
            自動的にオープンされます。また、関数から戻るときにはクローズ
            されます。
    """
    devnum = _input_devnum if dev is None else find_input_device(dev)
    open_input_device(devnum)
    try:
        while True:
            print(recv_event())
    except KeyboardInterrupt:
        pass
    finally:
        close_input_device(devnum)


# モジュールで定義された関数を自動的に __all__ に含める
__all__.extend([name for name, value in globals().items()
                if name[0] != '_' and callable(value) and
                value.__module__ == 'pytakt.midiio'])


# current output device は、PYTAKT_OUTPUT_DEVICE 環境変数が定義されていれば
# その値 (-1 でも可) になり、そうでなければ default output deivce になる。
set_output_device(os.environ['PYTAKT_OUTPUT_DEVICE']
                  if 'PYTAKT_OUTPUT_DEVICE' in os.environ
                  else _cmidiio.default_output_device())


# current input device は、PYTAKT_INPUT_DEVICE 環境変数が定義されていれば
# その値 (-1 でも可) になり、そうでなければ default input deivce になる。
set_input_device(os.environ['PYTAKT_INPUT_DEVICE']
                 if 'PYTAKT_INPUT_DEVICE' in os.environ
                 else _cmidiio.default_input_device())


# midiioモジュールのインポートより前に設定されたいたテンポを引き継ぐ
_set_tempo(_current_tempo_value)
