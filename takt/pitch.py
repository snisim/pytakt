# coding:utf-8
"""
このモジュールには、Pitchクラス, Intervalクラス、Keyクラス、
及びノート番号についてのユーティリティ関数が定義されています。
"""
# Copyright (C) 2023  Satoshi Nishimura

import re
import numbers
import math
from typing import List
from takt.utils import takt_round

__all__ = ['chroma', 'octave', 'chroma_profile', 'Pitch', 'Interval', 'Key']


def chroma(note_number) -> int:
    """
    MIDIノート番号からクロマ値(ピッチクラスとも言い、Cを0, C#を1,
    Dを2, ..., Bを11とした0〜11の整数)を計算して返します。

    Args:
        note_number(int or float):
            MIDIノート番号。floatの場合はまずintに丸められてから計算されます。
    """
    return takt_round(note_number) % 12


def octave(note_number) -> int:
    """
    MIDIノート番号からオクターブ番号（中央ハから始まるオクターブを4とした整数）
    を計算して返します。

    Args:
        note_number(int or float):
            MIDIノート番号。floatの場合はまずintに丸められてから計算されます。
    """
    return takt_round(note_number) // 12 - 1


def chroma_profile(pitches) -> List[int]:
    """
    `pitches` で与えられたピッチの列に対して、クロマ値(ピッチクラス) ごとに
    出現頻度を計上した12要素のリストを返します。

    Args:
        pitches(iterable of Pitch or int):
            Pitch オブジェクトまたはMIDIノート番号を表す整数のイテラブル。

    Examples:
        >>> chroma_profile([C4, Bb5])
        [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0]
        >>> chroma_profile(ev.n for ev in readsmf('menuet.mid').Filter(\
NoteEvent).stream())
        [20, 5, 33, 0, 14, 0, 19, 48, 0, 30, 0, 35]
    """
    result = [0 for _ in range(12)]
    for p in pitches:
        result[chroma(p)] += 1
    return result


PITCH_IDS = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}
_SFTBL = (
    (-2, -1, -2, -2, -1, -2, -1, -2, -1, -2, -2, -1),  # sf == -2
    ( 0, -1,  0, -1, -1,  0, -1,  0, -1,  0, -1, -1),  # sf == -1
    ( 0,  1,  0,  1,  0,  0,  1,  0,  1,  0,  1,  0),  # sf == 0
    ( 1,  1,  0,  1,  0,  1,  1,  0,  1,  0,  1,  0),  # sf == 1
    ( 1,  2,  2,  1,  2,  1,  2,  2,  1,  2,  1,  2))  # sf == 2
_NSTBL_INDEX = (0, None, 1, None, 2, 3, None, 4, None, 5, None, 6)

# 長音階向けのsf値 (黒鍵の非音階音で使用)
_ENH_HEURISTIC_MAJ = (0, 1, 0, 1, 0, 0, 1, 0, -1, 0, -1, 0)
# 短音階向けのsf値 (黒鍵の非音階音で使用)
_ENH_HEURISTIC_MIN = (0, -1, 0, 0, 1, 0, 1, 0, 0, 1, 0, 1)
# 調号がシャープのときのsf値 (白鍵の非音階音で使用)
#    _ENH_HEURISTIC_S[9], ENH_HEURISTIC_S[11] が 1 なのは、短音階でこれらの
#    音にナチュラルよりもダブルシャープを使う傾向が強いから。
_ENH_HEURISTIC_S = (0, -1, 0, -1, -1, 0, -1, 0, -1, 1, -1, 1)
# 調号がフラットのときのsf値 (白鍵の非音階音で使用)
_ENH_HEURISTIC_F = (0, 1, 0, 1, 1, 0, 1, 0, 1, 1, 1, 1)


class Pitch(int):
    """
    音高を表すオブジェクトのクラスです。intクラスを継承していて、
    MIDIノート番号を表す整数と同じように振る舞うことができます。
    ただし、sf属性という異名同音に関する付加情報を持つ点において、
    intクラスとは異なります。

    Attributes:
        sf (int): 異名同音に関する情報 (sharp-flat)で、楽譜上での調号による
             ものを含めたシャープ/フラットの数を表します。2, -1, 0, 1, 2 の
             いずれかで、正ならばシャープの数、負ならばその絶対値が
             フラットの数を表します。例えば、オブジェクトが整数値として61を
             持つ場合（つまり、MIDIノート番号が61の場合)、sfが1であれば
             C#4音を表し、sfが-1であればDb4音を表します。

    Args:
        value(int, str, or Pitch): MIDIノート番号、および省略時のsf属性値を
            決める値。
            intならその値、Pitchならその整数値がMIDIノート番号となります。
            また、以下の文字から構成された文字列によって音高を指定できます。

            * 音名を表す 'A' から 'G' (小文字でも可。
              'B' は 'C' の長七度上を表す)
            * シャープを表す '#', 's', または '+' (高々2個。音名の後に置く)
            * フラットを表す 'b', 'f', または '-' (高々2個。音名の後に置く)
            * ナチュラルを表す '%' または 'n' (音名の後に置く)
            * オクターブ番号を表す '0' から '9' (省略可。音名の後に置く。
              '4' が中央ハから始まるオクターブを表す)
            * オクターブアップを表す '^' またはシングルクオート
            * オクターブダウンを表す '_' または ','

            文字列をノート番号に変換する際には、`key` 引数の値が考慮されます。
        sf(int, optional): sf属性の値。指定された場合には、その値がsf属性値に
            なります。指定されなかった場合は以下のルールにより定められます。

            * `value` がPitchの場合、そのsf情報がコピーされる。
            * `value` がintの場合、`key` 引数の値を考慮して推測される。
            * `value` がstrの場合、文字列に含まれる臨時記号、および
              `key` 引数の値から決定される。
        key(Key, int, or str, optional): `value` がintまたはstrである
            ときに参照される調の情報。Keyクラスのオブジェクト、もしくは
            Key()コンストラクタの第1引数。defaultはハ長調。
        octave(int, optional): `value` がstrで、かつ文字列内にオクターブ
            番号が含まれていないときのオクターブ値。

    Examples:
        >>> Pitch(61)   # MIDIノート番号=61
        Cs4             # Pitch(61, 1) と同等
        >>> Pitch(61, -1)
        Db4
        >>> Pitch(61, key='Db major')
        Db4
        >>> Pitch(C4, 1)
        Bs3
        >>> Pitch('C#4')
        Cs4
        >>> Pitch('_C', key='e major')
        Cs3
        >>> Pitch('Cn', key=3, octave=5)
        C5
        >>> Db4 + 2
        63

    .. rubric:: ピッチ定数

    Pitchオブジェクトを値とする定数として、'C0' から 'B9' まで、
    及びその各々に対して s(シャープ)、ss(ダブルシャープ)、b(フラット)、
    bb(ダブルフラット)を伴ったもの (例: Ds5, Bbb6) が予め定義されています。
    これらの値は、その定数名を文字列として Pitch() コンストラクタに
    渡したものに等しいです。

    .. rubric:: 演算規則

    * Pitch型どうしの比較 (等値比較、大小比較) はノート番号だけで行われ、
      sf の値は比較の結果に影響しません。例えば、
      Cs4 == Db4 は True になります。
    * Pitch - Pitch の結果は Interval型になります。
    * Pitch + Interval, Interval + Pitch, Pitch - Interval の結果は Pitch 型
      となり、sf は +-2 の範囲内である限り正しく計算されます。
    * それ以外の演算は int 型としての演算となります。
    """

    def __new__(cls, value, sf=None, key=0, octave=4):
        if sf is not None and not -2 <= sf <= 2:
            raise ValueError('sf must be in [-2,2] range')
        if isinstance(value, str):
            return Pitch._new_from_str(value, sf, key, octave)
        elif isinstance(value, Pitch):
            obj = int.__new__(cls, value)
            obj.sf = sf if sf is not None else value.sf
            return obj
        elif isinstance(value, numbers.Integral):
            obj = int.__new__(cls, value)
            obj.sf = sf
            if sf is None:
                obj.sf = obj._fixsf_impl(key)
            return obj
        else:
            raise TypeError('%r is not a valid value for Pitch' % value)

    def _new_from_str(string, osf, key, octave):
        key = 0 if key is None else key
        m = re.match(
            "([',^_]*)([a-gA-G])([0-9]*)([-+sfn#b%',^_]*)([0-9]*)\\s*$",
            string)
        if not m:
            raise ValueError("Invalid note name")
        has_accidental = False
        sf = 0
        for i in (1, 3, 4, 5):
            if i in (3, 5):
                octave = int(m.group(i)) if m.group(i) else octave
            else:
                for c in m.group(i):
                    if c in "^'":
                        octave += 1
                    elif c in "_,":
                        octave -= 1
                    else:
                        has_accidental = True
                        sf += 1 if c in 's#+' else -1 if c in 'fb-' else 0
        p = PITCH_IDS[m.group(2).upper()]
        if not has_accidental:
            sf = Key(key).getsf(p)
#        elif sf == 0:  # `natural' case
#            sf = -Key(key).getsf(p)
#            p -= sf
        return Pitch(p + sf + (octave + 1) * 12,
                     osf if osf is not None else sf)

    def __repr__(self):
        return self.tostr(lossless=True)

    def __str__(self):
        return self.tostr(lossless=True)
#        return "Pitch(%d, %r)" % (self, self.sf)

    def __add__(self, other):
        if isinstance(other, Interval):
            return Interval._add_pitch_interval(self, other)
#        elif type(other) == int:
#            return Pitch(int(self) + other, self.sf)
        else:
            return int.__add__(self, other)
    __radd__ = __add__

    def __sub__(self, other):
        if isinstance(other, Pitch):
            return Interval._pitch_subtract(self, other)
        elif isinstance(other, Interval):
            return Interval._add_pitch_interval(self, -other)
#        elif type(other) == int:
#            return Pitch(int(self) - other, self.sf)
        else:
            return int.__sub__(self, other)

    def __pos__(self):
        return Pitch(self)

    def natural(self) -> 'Pitch':
        """ 幹音（シャープ、フラットのない音）の Pitchオブジェクトを返します。
        """
        return Pitch(self - _SFTBL[self.sf + 2][chroma(self)], 0)

    def tostr(self, *, lossless=False, octave=True,
              pitch_strings='CDEFGAB', sfn='sbn') -> str:
        """ 音高を表す文字列('C4', 'Gbb6' など)に変換します。

        Args:
            lossless(bool): デフォルト(False)では、常に `pitch_strings` と
                `sfn` を使った文字列を返します。
                Trueのときは、eval関数を適用したときに
                元のPitchオブジェクトへ正確に戻るよう、必要に応じて
                'Pitch(Cs4, 0)' のようなコンストラクタを呼ぶ形式の文字列へ
                変換します。
            octave(bool, optional): Falseにすると、オクターブ番号を含めない
                文字列を返します。losslessがFalseのときだけ有効です。
            pitch_strings(sequence of str): 音名に使用される
                0から6までインデックス可能な文字列の集まりで、
                pitch_strings[0], ..., pitch_strings[6]は、それぞれ、
                C音, ..., B音に対する文字列に相当します。
            sfn(sequence of str): 臨時記号に使用される
                0から2(または1)までインデックス可能な文字列の集まりです。
                sfn[0]はシャープに対する文字列、sfn[1]はフラットに対する
                文字列で、sfn[2]は現在のところ使用されていません。

        Returns:
            結果文字列
        """
        np = self.natural()
        alter = self - np
        oc = globals()['octave'](np)
        string = "%s%s%s" % (
            pitch_strings[_NSTBL_INDEX[chroma(np)]],
            sfn[1 if alter < 0 else 0] * abs(alter),
            str(oc) if octave or lossless else '')
        if lossless and (oc < 0 or oc >= 10):
            return "Pitch(%d, %r)" % (self, self.sf)
        elif lossless and alter != self.sf:
            return "Pitch(%s, %r)" % (string, self.sf)
        else:
            return string

    def fixsf(self, key, set_sf_for_naturals=False,
              enh='heuristic') -> 'Pitch':
        """sf属性の値を調`key` にふさわしいように修正した新しいPitch
        オブジェクトを返します。
        元のsfの値は、それが0以外の整数だった場合、ヒントとして働きます。

        Args:
            key(Key, int, or str): 調 (Keyクラスのオブジェクト、もしくは
                Key()コンストラクタの第１引数)
            set_sf_for_naturals(bool): Trueにすると、楽譜にしたときに
                ナチュラルになる場合(例えば Db major key での D)に対して、
                sfを 1または-1 (調号と反対) にセットします。
            enh(str): undocumented

        Returns:
            新しいPitchオブジェクト

        Examples:
            >>> Dbb4.fixsf('C major')
            C4
            >>> Ds4.fixsf('Eb major')
            Eb4
            >>> Pitch(Fs4, 0).fixsf('C major')
            Fs4
            >>> Pitch(D4, -1).fixsf('Db major')  # -1 はヒント
            Ebb4
        """
        return Pitch(self, self._fixsf_impl(key, set_sf_for_naturals, enh))

    def _fixsf_impl(self, key, set_sf_for_naturals=False, enh='heuristic'):
        chrm = chroma(self)
        is_black_key = _NSTBL_INDEX[chrm] is None
        key = key if isinstance(key, Key) else Key(key)
        sign = 1 if key.signs >= 0 else -1
        sf = self.sf
        if key.is_scale_tone(chrm):
            # スケールトーンの場合、元のsfは無視して調号に沿ったものにする。
            return key.getsf(self - sign)
        else:
            if is_black_key:
                # 非スケールトーンで黒鍵の場合、sfを 1 か -1 へ修正。
                if not sf:
                    # sf=0の場合は、ヒューリスティックによって決める。
                    sf = Pitch._fixsf_enh(enh, chrm, key)
                else:
                    sf = 1 if sf > 0 else -1
            else:
                # 非スケールトーンで白鍵の場合
                if not sf:
                    # sf=0の場合、ヒューリスティックによって決める
                    # (この際なるべく重記号を避けるようにする)。
                    sf = Pitch._fixsf_enh(enh, chrm, key, True) + sign
                # cfebはシャープの調でのC,F音、或いはフラットの調でのE,B音で1
                cfeb = chrm in ((0, 5) if sign == 1 else (4, 11))
                if sf * sign < 0 and not cfeb:
                    # 調号と逆の臨時記号の場合 (cfebの場合を除く)
                    if not set_sf_for_naturals:
                        sf = 0
                elif sf * sign > 0:
                    # 調号と同じ臨時記号の場合。
                    sf = sign * (2 - cfeb)
                else:  # sf == 0 or cfeb
                    sf = -sign * set_sf_for_naturals
        return sf

    @staticmethod
    def _fixsf_enh(enh, chrm, key, use_alt_tab=False):
        if enh == 'heuristic':
            if use_alt_tab:
                tab = _ENH_HEURISTIC_S if key.signs >= 0 else _ENH_HEURISTIC_F
            else:
                tab = _ENH_HEURISTIC_MIN if key.minor else _ENH_HEURISTIC_MAJ
            return tab[(chrm - key.gettonic()) % 12]
        elif enh == 'sharp':
            return 1
        elif enh == 'flat':
            return -1
        elif enh == 'undecided':
            return 0
        else:
            raise ValueError("Invalid 'enh' value")

    def freq(self) -> float:
        """ A=440Hzおよび平均律を仮定したときの周波数を返します。 """
        return 440.0 * (2 ** ((self - 69) / 12))

    @staticmethod
    def from_freq(freq, sf=None, key=0) -> 'Pitch':
        """ A=440Hzおよび平均律を仮定したときの周波数から、それに最も
        周波数の近いPitchオブジェクトを構築します。

        Args:
            freq(float): 周波数
            sf(int, optional):
                Pitchコンストラクタのsf引数と同じ意味を持ちます。
            key(Key, int, or str, optional):
                Pitchコンストラクタのkey引数と同じ意味を持ちます。
        """
        return Pitch(takt_round(math.log2(freq / 440.0) * 12 + 69), sf, key)


# define pitch names like 'C4', 'Ds5', and 'Bb6' as constants
for _sf, _d in (("", 0), ("s", 1), ("b", -1), ("ss", 2), ("bb", -2)):
    for _oct in range(0, 10):
        for _k in PITCH_IDS:
            exec("%s%s%d=Pitch(%d, %d)" %
                 (_k, _sf, _oct,
                  PITCH_IDS[_k] + _d + (_oct + 1) * 12, _d))
            __all__.append('%s%s%d' % (_k, _sf, _oct))


_MAJOR_TONES = (0, 2, 4, 5, 7, 9, 11)
_IS_PERFECT = (1, 0, 0, 1, 1, 0, 0)
_SEMITONES_TO_DS = (0, 1, 1, 2, 2, 3, 3, 4, 5, 5, 6, 6)


class Interval(int):
    """
    音程を表すオブジェクトのクラスです。intクラスを継承していて、
    半音数を表す整数と同じように使用することができます。符号つきであり、
    負の音程も表現します。

    Attributes:
        ds(int): 五線譜上での符号付き距離 (signed distance on the staff)。
            これは、度数より1少ない数で、例えば、"～3度" という音程では
            すべて2になります。負の音程では負になります。

    Args:
        value(str or int): str型の場合、下のような文字列で音程を指定します。

                * 'P1' -- 完全1度, 'm2' -- 短2度, 'M2' -- 長2度,
                  'm3' -- 短3度, 'M3' -- 長3度, 'P4' -- 完全4度,
                  'P5' -- 完全5度, …
                * 'A1' -- 増1度, 'A2' -- 増2度, 'A3' -- 増3度,
                  'A4' -- 増4度, …
                * 'd2' -- 減2度, 'd3' -- 減3度, …
                * 'AA1' -- 重増1度, 'AA2' -- 重増2度, …
                * 'dd3' -- 重減3度, 'dd4' -- 重減4度, …
                * 'A' や 'd' は更に増やすこともできます。

            int型のときは、半音数で音程を指定します。
        ds(int, optional): `value` がint型のときは、この引数によって
            ds属性の値を指定する必要があります。

    .. rubric:: 演算規則

    * Interval型どうしの比較 (等値比較、大小比較) は半音数だけで行われ、
      ds属性の値は比較の結果に影響しません。例えば、Interval('A4') ==
      Interval('d5') は True になります。
    * Interval 型の符号反転は、半音数、ds値をともに符号反転させます。
    * Interval 型どうしの加算の結果は Interval 型になり、2つの音程を積み
      重ねた音程 (半音数、ds値をそれぞれ加えたもの) になります。
    * Interval 型どうしの減算(x-y)の結果は Interval 型になり、x+(-y)と
      等価です。
    * Interval 型と整数との乗算の結果は Interval 型になり、
      半音数、ds値それぞれを整数倍したものになります。
    * Interval 型どうしの剰余演算(x % y)の結果は Interval型になり、これは
      x - (int(x) // int(y)) * y と等価です。
    * Interval 型と Pitch 型の間の演算については、Pitch クラスの演算規則
      を見てください。
    * それ以外の演算は int 型としての演算となります。

    Examples:
        >>> B4 - F4
        Interval('A4')
        >>> C4 + Interval('d5')
        Gb4
        >> Interval('A4') + Interval('d5')
        Interval('P8')
        >> Interval('P8') - Interval('M3')
        Interval('m6')
        >>> G5 - C4
        Interval('P12')
        >>> Interval('P12') % Interval('P8')
        Interval('P5')
        >>> int(Interval('A4'))
        6
        >>> Interval('A4') + 1
        7
    """
    def __new__(cls, value, ds=None):
        if isinstance(value, numbers.Integral):
            obj = int.__new__(cls, value)
            if ds is None:
                raise Exception("Requires 2nd argument when 'value' is int")
            obj.ds = ds
            return obj
        else:
            return Interval._parse_str(value)

    def _parse_str(string):
        m = re.match("([PpMm]|[Aa]+|[Dd]+)([0-9]+)$", string)
        if not m:
            raise ValueError("Invalid interval name")
        quality = m.group(1)
        ds = int(m.group(2)) - 1
        (oc, i) = divmod(ds, 7)
        semi = _MAJOR_TONES[i] + oc * 12
        perf = _IS_PERFECT[i]
        if ds < 0 or (perf and (quality in "Mm")) \
           or not perf and (quality in "Pp"):
            raise ValueError("Invalid interval name %r" % string)
        if quality == 'm':
            semi -= 1
        elif quality[0] in "Aa":
            semi += len(quality)
        elif quality[0] in "Dd":
            semi -= len(quality) + (1 - perf)
        return Interval(semi, ds)

    def __repr__(self):
        if self < 0 or \
           (self == 0 and self.ds < 0):  # use -'d2' rather than 'A0'
            return '-' + repr(Interval(-self, -self.ds))
        (oc, i) = divmod(self.ds, 7)
        semi = _MAJOR_TONES[i] + oc * 12
        perf = _IS_PERFECT[i]
        if self == semi:
            s = "MP"[perf]
        elif not perf and self == semi - 1:
            s = 'm'
        elif self > semi:
            s = 'A' * (self - semi)
        else:
            s = 'd' * (semi - (1 - perf) - self)
        return "Interval('%s%d')" % (s, self.ds + 1)

    def __pos__(self):
        return Interval(int(self), self.ds)

    def __neg__(self):
        return Interval(-int(self), -self.ds)

    def __add__(self, other):
        if isinstance(other, Interval):
            return Interval(int(self) + int(other), self.ds + other.ds)
        else:
            # return int.__add__(self, other) だと Interval + Pitch が失敗する
            return NotImplemented

    def __sub__(self, other):
        if isinstance(other, Interval):
            return Interval(int(self) - int(other), self.ds - other.ds)
        else:
            return NotImplemented

    def __mul__(self, other):
        if type(other) == int:
            return Interval(int(self) * other, self.ds * other)
        else:
            # NotImplemented だと Interval * Interval がエラーになる
            return int.__mul__(self, other)
    __rmul__ = __mul__

    def __mod__(self, other):
        if isinstance(other, Interval):
            return self - (self // other) * other
        else:
            return int.__mod__(self, other)

    def __divmod__(self, other):
        return (self // other, self % other)

    @staticmethod
    def _add_pitch_interval(pitch, interval):
        # pitch.natural()に度数の分を上げた(下げた)のが結果のnatural()。
        # 半音数は単純に足し、結果の半音数と結果のnatural()の差がsf。
        n = int(pitch.natural())
        chm = chroma(n)
        d = _SEMITONES_TO_DS[chm] + interval.ds
        (oc, i) = divmod(d, 7)
        n += _MAJOR_TONES[i] - chm + oc * 12
        semi = int(pitch) + int(interval)
        sf = semi - n
        # sf が+-2に収まらない場合は、範囲内に修正
        sf = 2 if sf > 2 else -2 if sf < -2 else sf
        return Pitch(semi, sf)

    @staticmethod
    def _pitch_subtract(p1, p2):
        (n1, n2) = (int(p1.natural()), int(p2.natural()))
        (oc, k) = divmod(n1 - n2, 12)
        d = _SEMITONES_TO_DS[k]
        if k == 6 and chroma(n2) == 11:
            d += 1  # augmented 4th => diminished 5th
        return Interval(int(p1) - int(p2), d + oc * 7)


_KEY_TAB = [
    (0x000000, 0xab5, 'C major', 'A minor'),
    (0x000400, 0xad5, 'G major', 'E minor'),
    (0x000401, 0xad6, 'D major', 'B minor'),
    (0x004401, 0xb56, 'A major', 'F# minor'),
    (0x004411, 0xb5a, 'E major', 'C# minor'),
    (0x044411, 0xd5a, 'B major', 'G# minor'),
    (0x044511, 0xd6a, 'F# major', 'D# minor'),
    (0x444511, 0x56b, 'C# major', 'A# minor'),

    # following 9 entries (extended keys) are used by Scale module
    (0x444911, 0x5ab, 'G# major', 'E# minor'),
    (0x444912, 0x5ad, 'D# major', 'B# minor'),
    (0x448912, 0x6ad, 'A# major', 'F## minor'),
    (0x448922, 0x6b5, 'E# major', 'C## minor'),
    (0, 0, '', ''),
    (0x884621, 0xad5, 'Abb major', 'Fb minor'),
    (0x884611, 0xad6, 'Ebb major', 'Cb minor'),
    (0x844611, 0xb56, 'Bbb major', 'Gb minor'),
    (0x844511, 0xb5a, 'Fb major', 'Db minor'),

    (0x444511, 0xd5a, 'Cb major', 'Ab minor'),
    (0x444111, 0xd6a, 'Gb major', 'Eb minor'),
    (0x444110, 0x56b, 'Db major', 'Bb minor'),
    (0x440110, 0x5ab, 'Ab major', 'F minor'),
    (0x440100, 0x5ad, 'Eb major', 'C minor'),
    (0x400100, 0x6ad, 'Bb major', 'G minor'),
    (0x400000, 0x6b5, 'F major', 'D minor'),
]
_KEYSIG_TAB = (0, -5, 2, -3, 4, -1, 6, 1, -4, 3, -2, 5)


class Key(object):
    """
    調を表すオブジェクトのクラスです。

    Attributes:
        signs(int): 絶対値は調号に含まれる記号の数(通常0〜7、拡張時11まで)を
            表し、符号はシャープ(正)かフラット(負)を表します。
        minor(int): 長調のとき0、短調のとき1

    Args:
        keydesc(int, str, or Key): int型ならば、signs属性の値を指定します。
            str型の場合、下の正規表現にマッチした文字列によって調を指定します。
            大文字/小文字は区別されません。

            ``[A-G][#bsf]?[- ]*(major|minor)``

            Key型の場合は、コピーコンストラクタとして働きます。
        minor(int, optional):
            `keydesc` がint型のとき、minor属性の値を指定します。
            `keydesc` がそれ以外の型のときは無視されます。
        extended(bool, optional):
            Trueなら'G# major'など一般的に使用されない調も許容します。

    Examples:
        ``Key('C major')  Key('Eb-minor')  Key(-3)  Key(3,1)``

    """

    def __init__(self, keydesc, minor=0, extended=False):
        if isinstance(keydesc, Key):
            (self.signs, self.minor) = (keydesc.signs, keydesc.minor)
        else:
            if isinstance(keydesc, str):
                m = re.match("\\s*([a-g])([sf#b]?)[-\\s]*(major|minor)\\s*$",
                             keydesc.lower())
                if not m:
                    raise ValueError("Unrecognized key-signature string")
                p = PITCH_IDS[m.group(1).upper()]
                sf = sum([(1 if c in "s#" else -1) for c in m.group(2)])
                minor = 1 if m.group(3) == "minor" else 0
                k = _KEYSIG_TAB[(p + sf) % 12] - minor * 3
                k += 12 if sf > 0 and k < 0 else -12 if sf < 0 and k > 0 else 0
            elif (isinstance(keydesc, numbers.Integral) and
                  not isinstance(keydesc, Pitch)):
                k = keydesc
            else:
                raise TypeError("invalid 'keydesc' type")
            lim = 7 if not extended else 11
            if not -lim <= k <= lim:
                raise ValueError('more than %d shaprs/flats are not allowed'
                                 % lim)
            if minor not in [0, 1]:
                raise ValueError("'minor' must be 0 (major) or 1 (minor)")
            (self.signs, self.minor) = (k, minor)

    def __repr__(self):
        return "Key('%s')" % _KEY_TAB[self.signs % 24][self.minor + 2]

#    def __str__(self):
#        return "Key(%r, %r)" % (self.signs, self.minor)

    def __eq__(self, other):
        if not isinstance(other, Key):
            return NotImplemented
        return self.signs == other.signs and self.minor == other.minor

    def getsf(self, note_number) -> int:
        """
        ノート番号が与えられたとき、その音に対して調号によって付く
        sharp/flatの数を返します。

        Args:
            note_number(int): MIDIノート番号

        Returns:
            正ならばsharpの数、負ならばその絶対値がflatの数を意味する整数。

        Examples:
            >>> Key('G-major').getsf(F4)
            1
            >>> Key('G-major').getsf(Fs4)
            0
        """
        sf = (_KEY_TAB[self.signs % 24][0] >> (chroma(note_number)*2)) & 0b11
        if self.signs < 0:
            sf = -sf
        return sf

    def is_scale_tone(self, note_number) -> bool:
        """
        ノート番号が与えられたとき、調の基準となっている音階(長調の場合は
        長音階、短調の場合は自然短音階)に含まれる音かどうかを調べます。

        Args:
            note_number(int): MIDIノート番号

        Returns:
            音階上の音ならTrue、そうでなければFalse。
        """
        return ((_KEY_TAB[self.signs % 24][1] >> chroma(note_number)) & 1) == 1

    def gettonic(self, octave=4) -> Pitch:
        """調の主音を返します。

        Args:
            octave(int): 返される主音のオクターブ番号
        """
        return Pitch(_KEY_TAB[self.signs % 24][self.minor + 2][:-6],
                     octave=octave)

    @staticmethod
    def from_tonic(tonic, minor=0, extended=False) -> 'Key':
        """主音を与えて、Keyオブジェクトを生成します。

        Args:
            tonic(Pitch or int): 主音
            minor(int, optional): 長調のとき0、短調のとき1
            extended(bool, optional):
                Trueなら一般的に使用されない調も許容します。
        """
        k = _KEYSIG_TAB[chroma(tonic)]
        if minor:
            k -= 3
            if k < -6:
                k += 12
        lim = 7 if not extended else 11
        if isinstance(tonic, Pitch):
            if tonic.sf > 0 and k < 0 and k + 12 <= lim:
                k += 12
            elif tonic.sf < 0 and k > 0 and k - 12 >= -lim:
                k -= 12
        return Key(k, minor, extended)
