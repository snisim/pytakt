# coding:utf-8
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
LoopBackEvent以外のイベントについても、そのメッセージ送受に
ループバックデバイスを利用することができます。

デバイスを使用するには予めオープンする必要があります。
ただし、ループバックデバイスは常に使用可能で、オープンの必要はありません。

入力、出力デバイスのそれぞれに、現在選択されているデバイスが存在します。
これの初期値はプラットフォームごとに決まっています。ただし、
出力デバイスについては、環境変数 TAKT_OUTPUT_DEVICE に
:func:`find_output_device` で認識できるような文字列を設定することで、
初期値を変えることができます。

.. rubric:: 入出力キュー

モジュール内部には、入力と出力のそれぞれに、メッセージ (イベントを to_message
メソッドで変換したバイト列) を蓄えるためのキューがあります。
各メッセージにはタイムスタンプとトラック番号が付与されています。
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
# Copyright (C) 2023  Satoshi Nishimura

import os
import itertools
from typing import List, Optional
import takt.cmidiio as _cmidiio
from takt.event import NoteEvent, NoteEventClass, CtrlEvent, SysExEvent, \
     MetaEvent, TempoEvent, LoopBackEvent, Event, message_to_event
from takt.pitch import Pitch
from takt.constants import TICKS_PER_QUARTER
from takt.score import Score, EventList, EventStream, RealTimeStream, Tracks
from takt.mml import mml
from takt.timemap import _current_tempo_value

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
_input_devnum = _cmidiio.default_input_device()


_loopback_events = {}  # 送出されてから受信されるまでLoopBackEventを保管
_loopback_count = itertools.count()


def current_output_device() -> int:
    """ 現在選択されている出力デバイスの番号を返します。 """
    return _output_devnum


def current_input_device() -> int:
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
    デバイスの記述をもとに、出力デバイス番号を取得します。

    Args:
        dev(int, str, list, tuple): デバイスの記述。整数の場合は、それが
            そのままデバイス番号になります。整数を表す文字列の場合は、それが
            整数に変換されてデバイス番号となります。それ以外の文字列の場合は、
            デバイス名の全部または一部がそれと一致するデバイス(複数ある場合は
            デバイス番号の小さい方)のデバイス番号となります。文字列は
            セミコロンで区切った複数のデバイス記述でも良く、その場合最初に
            存在を確認できたものが有効になります。リストまたはタプルの場合、
            各要素は整数またはセミコロンを含まない文字列であり、先頭から順番に
            単独の場合と同じように調べられ、最初にデバイスの存在を確認できた
            ものが有効になります。
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
    """ すべての出力デバイスの名前のリストを取得します。 """
    return _cmidiio.output_devices()


def set_output_device(dev) -> None:
    """ `dev` を　"現在選択されている出力デバイス" として指定します。

    Args:
        dev: :func:`find_output_device` によって認識可能なデバイス記述。
    """
    global _output_devnum
    _output_devnum = find_output_device(dev)


def open_output_device(dev=None) -> None:
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
    """ 出力デバイス `dev` がオープンされていれば True、そうでなければ
    False を返します。

    Args:
        dev: :func:`find_output_device` によって認識可能なデバイス記述。
    """
    return _cmidiio._is_opened_output_device(find_output_device(dev))


def find_input_device(dev) -> int:
    """
    デバイスの記述をもとに、入力デバイス番号を取得します。

    Args:
        dev(int, str, list, tuple): :func:`find_output_device` と同じ形式の
            デバイス記述。
    """
    return _find_device(dev, input_devices())


def input_devices() -> List[str]:
    """ すべての入力デバイスの名前のリストを取得します。 """
    return _cmidiio.input_devices()


def set_input_device(dev) -> None:
    """ `dev` を　"現在選択されている入力デバイス" として指定します。

    Args:
        dev: :func:`find_intput_device` によって認識可能なデバイス記述。
    """
    global _input_devnum
    _input_devnum = find_input_device(dev)


def open_input_device(dev=None) -> None:
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
    """ 入力デバイス `dev` がオープンされていれば True、そうでなければ
    False を返します。

    Args:
        dev: :func:`find_input_device` によって認識可能なデバイス記述。
    """
    return _cmidiio._is_opened_input_device(find_input_device(dev))


def show_devices() -> None:
    """ デバイスの一覧を表示します。 """
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
    """ 現在の時刻を返します。

    Returns:
        モジュールがimportされた時を0としたティック単位の時刻。
    """
    return _cmidiio.current_time()


def _current_tempo() -> float:
    """ 現在のテンポを返します。

    Returns:
        テンポ値 (beats per minute)
    """
    return _cmidiio.current_tempo()


def _set_tempo(bpm) -> None:
    """ 現在のテンポを変更します。

    Args:
        bpm(float): テンポ値 (beats per minute)
    """
    t = current_time()
    _cmidiio.queue_message(DEV_DUMMY, t, 0, TempoEvent(t, bpm).to_message())


def current_tempo_scale() -> float:
    """ 現在のテンポスケールを返します。

    Returns:
        テンポスケール値
    """
    return _cmidiio.current_tempo_scale()


def set_tempo_scale(tempo_scale) -> None:
    """ テンポスケールを変更します。

    Args:
        tempo_scale(float): テンポスケール値 (非負)
    """
    _cmidiio.set_tempo_scale(tempo_scale)


def queue_event(ev, time=None, devnum=None) -> None:
    """
    イベントをメッセージ (バイト列) に変換した上で、そのメッセージを送出時刻と
    トラック番号とともに出力キューへ置きます。置かれたメッセージは
    その送出時刻に達すると出力デバイスへ送られます。
    この関数でのブロック (出力待ち) はありません。

    注意: テンポ変更のため TempoEvent をキューする場合は、送出時刻が現時刻
    より過去であってはなりません。

    Args:
        ev(Event): キューするイベント。これは、to_message メソッドにより
            メッセージに変換されて、出力キューに置かれます。
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


def recv_event() -> Optional[Event]:
    """
    入力デバイスからのメッセージを受け取りイベントとして返します。
    すべてのオープンされている入力デバイスが対象となります。
    入力キューにメッセージが無いときはブロック(入力待ち)状態になります。
    ブロックはメッセージが到着するか、キーボード・インタラプトを受けると
    解除されます。

    ループバックデバイスからのメッセージと通常の入力デバイスからのメッセージが
    ほぼ同時刻に到着した場合、その受け取り順序が前後することがあります。

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
    _cmidiio.stop()
    _loopback_events.clear()


# もたつきを防ぐため先読みする時間幅。少なくとも MAX_DELTA_TIME*2 より大きい
# 必要がある。
_QUEUE_LOOK_AHEAD = TICKS_PER_QUARTER * 16

_METRONOME_TRACK = 65536


def _play_rec(score, rec=False, outdev=None, indev=None, metro=None,
              monitor=False):
    # score が EventStream である場合、playやrecordがリターンするのは
    # Keybordinterruptのみ。
    devnum = _output_devnum if outdev is None else find_output_device(outdev)
    indevnum = DEV_DUMMY
    if rec:
        indevnum = _input_devnum if indev is None else find_input_device(indev)
    open_output_device(devnum)  # may take some seconds
    open_input_device(indevnum)
    if not isinstance(score, EventStream):
        score = Tracks(
            [score, EventList([LoopBackEvent(score.get_duration(), 'done')],
                              0)])
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

    try:
        while True:
            try:
                ev = next(event_stream)
                # qt はキューに入れるべきシステム時刻
                qt = ev.t - _QUEUE_LOOK_AHEAD + toffset
            except StopIteration:
                ev = None
            if isinstance(score, RealTimeStream):
                if ev is None:
                    done = True
            else:
                if ev is None or qt >= current_time():
                    resume_tempo_scale()
                    if ev is not None:
                        queue_event(LoopBackEvent(qt, 'next'))
                    while True:
                        rev = recv_event()
                        if isinstance(rev, LoopBackEvent):
                            if rev.value == 'next':
                                break
                            elif rev.value == 'done':
                                recevlist.duration = rev.t - toffset
                                cancel_events(_METRONOME_TRACK, devnum)
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
                queue_event(ev, ev.t + ev.get_dt() + toffset, devnum)

    except KeyboardInterrupt:
        stop()
        recevlist.duration = current_time() - toffset
        # The following print() avoids command-line corruption by '^C'
        print(f"{'record' if rec else 'play'} interrupted")
    finally:
        resume_tempo_scale()
        close_input_device(indevnum)

    if rec:
        for ev in recevlist:
            ev.t = max(0, ev.t - toffset)
        return recevlist


def play(score, dev=None) -> None:
    """
    スコアを再生します。スコアに含まれるイベントに従って順にメッセージを出力
    デバイスへ送ります。この関数は、スコアの演奏長に相当する時間が経過するか、
    あるいはキーボード・インタラプトを受けるまでリターンしません。

    Args:
        score(Score): 演奏対象のスコア。無限長スコアであっても構いません。
        dev: 対象となる出力デバイス。Noneの場合は現在選択されている
            出力デバイス、それ以外の場合はこれを引数として
            :func:`find_output_device` を呼んだ結果が対象のデバイス
            となります。
            指定したデバイスがオープンされていないときは、自動的にオープン
            されます。
    """
    # scoreにMML文字列を渡せるようにしないのは、MML中でPython関数を
    # 呼んだときに関数スコープの問題を生じやすいから。
    _play_rec(score, False, dev)


def record(indev=None, play=None, outdev=None,
           metro=None, monitor=False) -> EventList:
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

    Returns:
        録音されたスコア
    """
    score = play if play is not None else mml("L1r@@")
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

    return _play_rec(score, True, outdev, indev, metro, monitor)


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
                value.__module__ == 'takt.midiio'])


# current_device は、TAKT_OUTPUT_DEVICE 環境変数が定義されていればその値
# (-1 でも可) になり、そうでなけれあば default output deivce になる。
set_output_device(os.environ['TAKT_OUTPUT_DEVICE']
                  if 'TAKT_OUTPUT_DEVICE' in os.environ
                  else _cmidiio.default_output_device())


# midiioモジュールのインポートより前に設定されたいたテンポを引き継ぐ
_set_tempo(_current_tempo_value)
