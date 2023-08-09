# coding:utf-8
"""
このモジュールには、スケール (音階) に関連するクラスとユーティリティ関数が
定義されています。
"""
# Copyright (C) 2023  Satoshi Nishimura

import re
import math
import numbers
import collections.abc
import itertools
from typing import Union, List
from takt.pitch import chroma, octave, Pitch, Key, Interval
from takt.utils import takt_round, takt_roundx
from takt.ps import note
from takt.score import seq, Score

__all__ = ['Scale', 'ScaleLibrary', 'DEG']


class Scale(object):
    """
    スケール (音階) を表すオブジェクトのクラスです。

    Attributes:
        tonic(Pitch or int): スケール開始音のピッチ (オクターブも
            意味を持ちます)
        tone_list(list of Interval or int): スケール構成音のリスト。
            各要素は `tonic` からの音程 (Interval オブジェクトもしくは
            半音数表す整数)。
        minor_like(int): 短調スケールに近いときに1、それ以外で0。これは、
            pitch()で返されるPitchオブジェクトの異名同音の選択に影響します。

    Args:
        tonic(Pitch or int): スケール開始音
        type(str or 2-tuple): スケールの種類。ScaleLibraryクラスに登録されいる
            クラス変数名の文字列、または、tone_list属性とminor_like属性から
            なる2要素タプル。

    Examples:
        >>> Scale(C4, 'major')
        Scale(C4, ([Interval('P1'), Interval('M2'), Interval('M3'), \
Interval('P4'), Interval('P5'), Interval('M6'), Interval('M7')], 0))
        >>> s = Scale(F4, ScaleLibrary.minor)
        >>> s.pitches()
        [F4, G4, Ab4, Bb4, C5, Db5, Eb5]
        >>> s[1], s[14]
        (G4, F6)
        >>> s.demo().play()

    .. rubric:: トーン番号

    トーン番号とは、tonicを0として、スケール上の音に対して順に無限に
    番号を振ったもので、tonicより下の音には負のトーン番号が割り当て
    られます。トーン番号は浮動小数点数のこともあり、非スケール音を
    表すのに使われます。

    .. rubric:: 演算規則

    * s を Scale オブジェクトとしたとき、s[i] の値は、トーン番号がiである
      音の Pitch オブジェクトになります (s.pitch(i) と等価)。
    * len(Scaleオブジェクト) は、スケール構成音の数を返します。
    * Scaleオブジェクトどうしの等価比較('==')は、すべての属性値が
      等価であるときのみ真となります。
    """

    def __init__(self, tonic, type='major'):
        if not isinstance(tonic, numbers.Integral):
            raise TypeError("'tonic' must be a valid pitch")
        self.tonic = tonic
        if isinstance(type, str):
            name = str.lower(re.sub(r'[-\s]', '', type))
            try:
                (self.tone_list, self.minor_like) = getattr(ScaleLibrary, name)
            except AttributeError:
                raise ValueError(
                    '%r: Unrecognized scale name' % type) from None
        elif (isinstance(type, tuple) and len(type) == 2 and
              isinstance(type[0], collections.abc.Iterable)):
            self.tone_list = list(type[0])
            self.minor_like = type[1]
            if not isinstance(self.minor_like, numbers.Integral) or \
               not 0 <= self.minor_like <= 1:
                raise ValueError("'minor_like' must be 0 or 1")
        else:
            raise TypeError("Invalid scale type")

    def __repr__(self):
        return "%s(%r, (%r, %r))" % (self.__class__.__name__, self.tonic,
                                     self.tone_list, self.minor_like)

    def __eq__(self, other):
        if not isinstance(other, Scale):
            return NotImplemented
        return self.__dict__ == other.__dict__

    def __len__(self):
        return len(self.tone_list)

    def __getitem__(self, x):
        return self.pitch(x)

    def __iter__(self):
        raise TypeError("'Scale' object is not iterable")

    def to_key(self) -> Key:
        """
        同じ主音を持った、minor_like属性が0なら長調、1なら短調の
        Keyオブジェクトを返します。
        """
        return Key.from_tonic(self.tonic, self.minor_like, extended=True)

    def is_scale_tone(self, note_number) -> bool:
        """ `note_number` がスケール上の音であれば真を返します。

        Args:
            note_number(int): MIDIノート番号
        """
        return self.tone_list.count(chroma(note_number - self.tonic)) > 0

    def _extended_tone_list(self):
        return self.tone_list + [self.tone_list[0] + Interval('P8')]

    def tonenum(self, pitch, enharmonic_delta=0.01) -> Union[int, float]:
        """ Pitch オブジェクトをトーン番号に変換します。

        Args:
            pitch(Pitch or int):
                PitchオブジェクトまたはMIDIノート番号を表す整数
            enharmonic_delta(float): `pitch` がPitchオブジェクトであり、かつ、
                非スケール音を表しているとき、異名同音に応じて結果に
                この値が増減されます。下のスケール音からピッチを上げるような
                表記のときは減じられ、逆のときは加えられます。

        Returns:
            トーン番号。非スケール音のときは線形補間によって
            求められた浮動小数点数を返します。
        """
        chrm = chroma(pitch - self.tonic)
        tlist = self._extended_tone_list()
        k = -1
        for x in tlist:
            if x > chrm:
                break
            k += 1
        result = k + (octave(pitch - self.tonic) + 1) * len(self)
        if tlist[k] == chrm:
            return result
        result += float(chrm - tlist[k]) / (tlist[k+1] - tlist[k])
        if isinstance(pitch, Pitch):
            thres = 0.5 if self.to_key().signs >= 0 else -0.5
            result += -enharmonic_delta if pitch.sf > thres \
                else enharmonic_delta
        return result

    def pitch(self, tone_number) -> Pitch:
        """ トーン番号を Pitch オブジェクトに変換します。
        トーン番号が整数でないときは、近傍のスケール音から線形補間によって
        実数のMIDIノート番号がまず求められ、それに最も近い整数が
        結果のピッチとなります(最も近い整数が2つあるときは上の音が選ばれます)。

        Args:
            tone_number(int or float):
                トーン番号
        """
        oct = int(tone_number // len(self))
        k = tone_number - oct * len(self)   # 0 <= k < len(self)
        if isinstance(tone_number, numbers.Integral):
            iv = self.tone_list[k]
        else:
            tlist = self._extended_tone_list()
            ik = int(math.floor(k))
            iv1, iv2 = tlist[ik], tlist[ik+1]
            n = self.tonic + iv1 + (k - ik) * (iv2 - iv1) + oct * 12
            ni = takt_round(n)
            if ni == self.tonic + iv1:  # 結果的にスケールトーンになったか
                iv = iv1
            elif ni == self.tonic + iv2:
                iv = iv2
            elif isinstance(ni, numbers.Integral):
                # MIDI番号の丸めで切り上げ(下げ)となった際には、ヒントとして
                # sf=1(-1) とする (enharmonic_delta を考慮するため)。
                rtn = Pitch(ni, sf=(0 if n == ni else 1 if ni > n else -1))
                return rtn.fixsf(self.to_key())
            else:
                return ni
        # スケールトーンの場合
        n = self.tonic + iv + oct * 12
        if isinstance(self.tonic, Pitch) and isinstance(iv, Interval):
            return n
        else:
            return Pitch(n).fixsf(self.to_key())

    def pitches(self) -> List[Pitch]:
        """ スケール構成音のピッチのリストを返します。"""
        return [(self.tonic + iv) if
                isinstance(self.tonic, Pitch) and isinstance(iv, Interval)
                else Pitch(self.tonic + iv).fixsf(self.to_key())
                for iv in self.tone_list]

    def get_near_scale_tone(self, pitch, round_mode='nearestup') -> Pitch:
        """ `pitch` に近いスケール上の音のピッチを返します。
        Scaleオブジェクトをsとしたとき、``s.get_near_scale_tone(p, r)`` は
        ``s[takt_roundx(s.tonenum(p), r)]`` と等価です。

        Args:
            pitch(Pitch or int):
                PitchオブジェクトまたはMIDIノート番号を表す整数
            round_mode(str or function):
                :func:`.takt_roundx` へ渡す丸めモード。
        """
        return self[takt_roundx(self.tonenum(pitch), round_mode)]

    def demo(self, noct=1, dir='up', **kwargs) -> Score:
        """ スケールについてのデモ演奏のスコアを返します。

        Args:
             noct(int): オクターブ数
             dir(str): 'up' (上行)、'down' (下行)、
                 または 'updown' (上行のち下行)
             kwargs: note関数に渡される追加の引数
        """

        iterator = (range(len(self) * noct, -1, -1) if dir == 'down' else
                    itertools.chain(range(0, len(self) * noct),
                                    range(len(self) * noct, -1, -1)) if
                    dir == 'updown' else
                    range(0, len(self) * noct + 1))
        return seq(note(self[n], **kwargs) for n in iterator)


class ScaleLibrary(object):
    """さまざまな音階のライブラリ。各クラス変数の値は、
    Scaleクラスのtone_listとminor_likeに相当する2要素タプルを表します。"""
    def _mode(n, org):
        tlist = org[0]
        return [(tlist[((n - 1) + i) % len(tlist)] - tlist[n - 1])
                % Interval('P8') for i in range(len(tlist))]

    major = ([Interval('P1'), Interval('M2'), Interval('M3'), Interval('P4'),
              Interval('P5'), Interval('M6'), Interval('M7')], 0)
    ionian = major
    dorian = (_mode(2, major), 1)
    phrygian = (_mode(3, major), 1)
    lydian = (_mode(4, major), 0)
    mixolydian = (_mode(5, major), 0)
    dominant = mixolydian
    aeolian = (_mode(6, major), 1)
    locrian = (_mode(7, major), 1)
    naturalminor = aeolian
    minor = aeolian

    melodicminor = ([Interval('P1'), Interval('M2'), Interval('m3'),
                     Interval('P4'), Interval('P5'), Interval('M6'),
                     Interval('M7')], 1)
    dorianf2 = (_mode(2, melodicminor), 0)
    phrygians6 = dorianf2
    lydianaugmented = (_mode(3, melodicminor), 0)
    lydiandominant = (_mode(4, melodicminor), 0)
    overtone = lydiandominant
    lydian7th = lydiandominant
    mixolydianf6 = (_mode(5, melodicminor), 0)
    locrians2 = (_mode(6, melodicminor), 1)
    aeolianf5 = locrians2
    halfdiminished = locrians2
    altereddominant = (_mode(7, melodicminor), 1)
    superlocrian = altereddominant
    # altered = altereddominant
    altered = ([Interval('P1'), Interval('m2'), Interval('A2'), Interval('M3'),
                Interval('A4'), Interval('m6'), Interval('m7')], 1)

    harmonicminor = ([Interval('P1'), Interval('M2'), Interval('m3'),
                      Interval('P4'), Interval('P5'), Interval('m6'),
                      Interval('M7')], 1)
    phrygiandominant = (_mode(5, harmonicminor), 0)
    harmonicminor5below = phrygiandominant
    ukrainiandorian = (_mode(4, harmonicminor), 0)
    altereddorian = ukrainiandorian

    chromatic = ([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11], 0)
    wholetone = ([0, 2, 4, 6, 8, 10], 0)

    diminished = ([0, 2, 3, 5, 6, 8, 9, 11], 0)
    diminishedwh = diminished
    dominantdiminished = (_mode(2, diminished), 0)
    combdiminished = dominantdiminished
    diminishedhw = dominantdiminished

    pentatonic = ([Interval('P1'), Interval('M2'), Interval('M3'),
                   Interval('P5'), Interval('M6')], 0)
    majorpentatonic = pentatonic
    minorpentatonic = (_mode(5, pentatonic), 1)
    japaneseyo = (_mode(2, pentatonic), 0)
    japaneseyodown = (_mode(4, pentatonic), 0)
    japanesein = ([Interval('P1'), Interval('m2'), Interval('P4'),
                   Interval('P5'), Interval('m7')], 1)
    japaneseindown = ([Interval('P1'), Interval('m2'), Interval('P4'),
                       Interval('P5'), Interval('m6')], 1)
    miyakobushi = japaneseindown
    minoryonanuki = (_mode(3, japaneseindown), 1)
    ryukyu = ([Interval('P1'), Interval('M3'), Interval('P4'),
               Interval('P5'), Interval('M7')], 0)

    blues = ([Interval('P1'), Interval('m3'), Interval('P4'), Interval('d5'),
              Interval('P5'), Interval('m7')], 1)
    doubleharmonic = ([Interval('P1'), Interval('m2'), Interval('M3'),
                       Interval('P4'), Interval('P5'), Interval('m6'),
                       Interval('M7')], 1)
    gypsyminor = (_mode(4, doubleharmonic), 1)
    hungarianminor = gypsyminor
    hungariangypsy = ([Interval('P1'), Interval('M2'), Interval('m3'),
                       Interval('A4'), Interval('P5'), Interval('m6'),
                       Interval('m7')], 1)
    neapolitanmajor = ([Interval('P1'), Interval('m2'), Interval('m3'),
                        Interval('P4'), Interval('P5'), Interval('M6'),
                        Interval('M7')], 1)
    neapolitanminor = ([Interval('P1'), Interval('m2'), Interval('m3'),
                        Interval('P4'), Interval('P5'), Interval('m6'),
                        Interval('M7')], 1)
    majorlocrian = (_mode(5, neapolitanmajor), 0)


def DEG(n) -> int:
    """
    整数nに対して、絶対値を1減らした整数を返します。nが0なら例外を送出します。
    この関数は、ダイアトニックスケールおけるトーン番号の差を音度で表すのに
    有効です。

    Examples:
        >>> s = Scale(C4, 'major')
        >>> s[DEG(3)]
        E4
        >>> s[s.tonenum(D4) + DEG(6)]
        B4
    """
    if n == 0:
        raise ValueError("Zero degree is not allowed")
    return n-1 if n >= 0 else n+1
