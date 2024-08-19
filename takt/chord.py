# coding:utf-8
"""
このモジュールには、コードシンボルに関連するクラスが定義されています。
"""
# Copyright (C) 2023  Satoshi Nishimura

import re
import math
import itertools
import warnings
from typing import Tuple, List, Dict, Iterator, Optional
from takt.pitch import Pitch, Interval, chroma, C3
from takt.constants import L16
from takt.utils import TaktWarning

__all__ = ['Chord']


_CHORD_KIND_DICT = {
    'major-seventh': {1: (0,), 3: (0,), 5: (0,), 7: (1,)},
    'dominant': {1: (0,), 3: (0,), 5: (0,), 7: (0,)},
    'major': {1: (0,), 3: (0,), 5: (0,)},
    'minor-seventh': {1: (0,), 3: (-1,), 5: (0,), 7: (0,)},
    'minor': {1: (0,), 3: (-1,), 5: (0,)},
    'dominant-ninth': {1: (0,), 3: (0,), 5: (0,), 7: (0,), 9: (0,)},
    'dominant-11th': {1: (0,), 3: (0,), 5: (0,), 7: (0,), 9: (0,), 11: (0,)},
    'dominant-13th': {1: (0,), 3: (0,), 5: (0,), 7: (0,), 9: (0,), 11: (0,),
                      13: (0,)},
    'diminished': {1: (0,), 3: (-1,), 5: (-1,)},
    'augmented': {1: (0,), 3: (0,), 5: (1,)},
    'diminished-seventh': {1: (0,), 3: (-1,), 5: (-1,), 7: (-1,)},
    'half-diminished': {1: (0,), 3: (-1,), 5: (-1,), 7: (0,)},
    'augmented-seventh': {1: (0,), 3: (0,), 5: (1,), 7: (0,)},
    'suspended-fourth': {1: (0,), 4: (0,), 5: (0,)},
    'major-sixth': {1: (0,), 3: (0,), 5: (0,), 6: (0,)},
    'minor-sixth': {1: (0,), 3: (-1,), 5: (0,), 6: (0,)},
    'major-minor': {1: (0,), 3: (-1,), 5: (0,), 7: (1,)},
    'major-ninth': {1: (0,), 3: (0,), 5: (0,), 7: (1,), 9: (0,)},
    'major-11th':  {1: (0,), 3: (0,), 5: (0,), 7: (1,), 9: (0,), 11: (0,)},
    'major-13th':  {1: (0,), 3: (0,), 5: (0,), 7: (1,), 9: (0,), 11: (0,),
                    13: (0,)},
    'minor-ninth': {1: (0,), 3: (-1,), 5: (0,), 7: (0,), 9: (0,)},
    'minor-11th': {1: (0,), 3: (-1,), 5: (0,), 7: (0,), 9: (0,), 11: (0,)},
    'minor-13th': {1: (0,), 3: (-1,), 5: (0,), 7: (0,), 9: (0,), 11: (0,),
                   13: (0,)},
    'suspended-second': {1: (0,), 2: (0,), 5: (0,)},
    'power': {1: (0,), 5: (0,)},
}


_CHORD_NAME_DICT = {
    '': 'major',
    '6': 'major-sixth',
    'maj7': 'major-seventh',
    'Maj7': 'major-seventh',
    'M7': 'major-seventh',
    'maj9': 'major-ninth',
    'Maj9': 'major-ninth',
    'M9': 'major-ninth',
    'maj11': 'major-11th',
    'Maj11': 'major-11th',
    'M11': 'major-11th',
    'maj13': 'major-13th',
    'Maj13': 'major-13th',
    'M13': 'major-13th',
    'mM7': 'major-minor',
    'm': 'minor',
    'm6': 'minor-sixth',
    'm7': 'minor-seventh',
    'm9': 'minor-ninth',
    'm11': 'minor-11th',
    'm13': 'minor-13th',
    '7': 'dominant',
    '9': 'dominant-ninth',
    '11': 'dominant-11th',
    '13': 'dominant-13th',
    'aug': 'augmented',
    'aug7': 'augmented-seventh',
    'dim': 'diminished',
    'dim7': 'diminished-seventh',
    'm7b5': 'half-diminished',
    'sus4': 'suspended-fourth',
    'sus2': 'suspended-second',
    'power': 'power',
    '5': 'power',
}

_KIND_TO_NAME = {v: k for k, v in _CHORD_NAME_DICT.items()}


_ALIAS_DICT = {
    '7sus4': ('sus4', (7,)),
    '9sus4': ('sus4', (7, 9)),
    '7sus2': ('sus2', (7,)),
    'mM9': ('mM7', (9,)),
    'mM11': ('mM7', (9, 11)),
    'mM13': ('mM7', (9, 11, 13)),
    'aug9': ('aug7', (9,)),
    'aug11': ('aug7', (9, 11)),
    'aug13':  ('aug7', (9, 11, 13)),
    'dim9': ('dim7', (9,)),
    'dim11': ('dim7', (9, 11)),
    'm9b5': ('m7b5', (9,)),
    'm11b5': ('m7b5', (9, 11)),
    'm13b5': ('m7b5', (9, 11, 13)),
    '7alt': ('7(b9,#9,#11,b13)', ()),
}

_MAX_NAME_LEN = 6

_TENSION_ALTER_DICT = {
    'b5': [(5, -1)],
    '#5': [(5, 1)],
    'M7': [(7, 1)],
    'M9': [(7, 1), (9, 0)],
    'M11': [(7, 1), (9, 0), (11, 0)],
    'M13': [(7, 1), (9, 0), (11, 0), (13, 0)],
    'b9': [(9, -1)],
    '9': [(9, 0)],
    '#9': [(9, 1)],
    '11': [(11, 0)],
    '#11': [(11, 1)],
    '13': [(13, 0)],
    'b13': [(13, -1)],
}

_INV_TENSION_ALTER_DICT = {
    (5, -1): 'b5',
    (5, 1): '#5',
    (7, 1): 'M7',
    (9, -1): 'b9',
    (9, 0): '9',
    (9, 1): '#9',
    (11, 0): '11',
    (11, 1): '#11',
    (13, 0): '13',
    (13, -1): 'b13',
}

_DEG2SEMITONES = (0, 2, 4, 5, 7, 9, 10)
_CHROMA2DEGSF = ((1, 0), (9, -1), (9, 0), (9, 1), (3, 0), (11, 0), (11, 1),
                 (5, 0), (13, -1), (13, 0), (7, 0), (7, 1))


def _deg2semitones(num):
    num = (num - 1) if num > 0 else (num + 1) if num < 0 else 0
    return _DEG2SEMITONES[num % 7] + (num // 7) * 12


# from_chroma_profileのためのビットベクトル化したクロマプロファイル
_CHORD_BCP = [sum(1 << chroma(_deg2semitones(num) + sf[0])
                  for num, sf in degrees.items())
              for degrees in _CHORD_KIND_DICT.values()]


class Chord(object):
    """
    ジャズやポピュラー音楽などで使われるコードシンボルを表すオブジェクトの
    クラスです。これは、MusicXMLの <harmony> 要素におけるコードの表現法を
    ベースにしています。ただし、一部のコード種別や、フレットボード表示に
    関する情報などは省かれています。

    Attributes:
        kind(str): 下のいずれかの文字列によってコードの種別を表します。
            それぞれの意味については、下の **コード名の記述** の項、および
            MusicXMLの <harmony> 要素の `kind の項目 <https://www.w3.org/\
2021/06/musicxml40/musicxml-reference/data-types/kind-value/>`_ を
            参照して下さい。

            'major', 'major-sixth', 'major-seventh', 'major-ninth',
            'major-11th', 'major-13th', 'major-minor',
            'minor', 'minor-sixth', 'minor-seventh', 'minor-ninth',
            'minor-11th', 'minor-13th',
            'dominant', 'dominant-ninth', 'dominant-11th', 'dominant-13th',
            'augmented', 'augmented-seventh',
            'diminished', 'diminished-seventh', 'half-diminished',
            'suspended-fourth', 'suspended-second', 'power'
        root(Pitch or int): コード根音のピッチ。
            オクターブも意味を持ちます。
        bass(Pitch, int, or None): コードのバス音のピッチ。
            オクターブも意味を持ちます。Noneのときは `root` と同一だと見な
            されます。
        modifications(list of (str, int, int)): MusicXMLの <degree>
            要素に相当し、コードの追加音、変化音、および省略音を表します。
            集合の各要素は、長さ3のタプルです。各タプルの第1項目は
            'add' (追加音)、'alter' (変化音)、'subtract' (省略音) のいずれかの
            文字列です。第2項目は、根音からの度数を表す整数です。
            第3項目は、基準となるピッチからの半音単位の変化分を表す整数です。
            基準となるピッチとは、追加音の場合は Mixolydian スケール上の
            ピッチ、変化音の場合はkind要素で指定されるコードの構成音のピッチ
            を意味します。

            例: C7b9 コードは、kind='dominant', root=C4,
            modifications=[('add', 9, -1)] として表します。

    Args:
        name(str, optional):
            下に示すコード名によってコードを指定します。この引数が Noneの場合
            は、`kind` 引数、および `root` 引数の指定が必須となります。
        kind(str, optional):
            kind属性を指定します。コード名によって既に指定されている場合は、
            それをオーバライドします。
        root(Pitch or int, optional):
            root属性を指定します。コード名によって既に指定されている場合は、
            それをオーバライドします。
        bass(Pitch or int, optional):
            bass属性を指定します。コード名によって既に指定されている場合は、
            それをオーバライドします。
        modifications(iterable of (str, int, int)):
            modifications属性を指定します。コード名によって既に与えられている
            場合は、それにこの引数で指定されたタプルを追加します。

    .. rubric:: コード名の記述

    本クラスでは、次のように並んだ文字列をコード名として使用します。
    <type>以降の各部分文字列の間にはスペース、カンマおよび丸括弧を自由に
    挿入できます。

        <root> <type> <modification>* [/<bass>]

    <root>は根音のピッチを表し、'A'から'G'の英文字 (小文字も可) に
    高々2個のシャープ '#' またはフラット 'b' を続けたものです。
    コード名を使った場合オクターブは常に3となります。他のオクターブを
    指定したい場合は、`root` 引数を使ってください。

    <type>は、次の表に示された文字列によってコードの種別 (kind属性の値) を
    表します (case-sensitive)。

        ==================  =====================  =======================
        kind属性            <type>                 構成音
        ==================  =====================  =======================
        major               ''                     1, 3, 5
        major-sixth         '6'                    1, 3, 5, 6
        major-seventh       'M7' 'maj7' 'Maj7'     1, 3, 5, 7
        major-ninth         'M9' 'maj9' 'Maj9'     1, 3, 5, 7, 9
        major-11th          'M11' 'maj11' 'Maj11'  1, 3, 5, 7, 9, 11
        major-13th          'M13' 'maj13' 'Maj13'  1, 3, 5, 7, 9, 11, 13
        major-minor         'mM7'                  1, b3, 5, 7
        minor               'm'                    1, b3, 5
        minor-sixth         'm6'                   1, b3, 5, 6
        minor-seventh       'm7'                   1, b3, 5, b7
        minor-ninth         'm9'                   1, b3, 5, b7, 9
        minor-11th          'm11'                  1, b3, 5, b7, 9, 11
        minor-13th          'm13'                  1, b3, 5, b7, 9, 11, 13
        dominant            '7'                    1, 3, 5, b7
        dominant-ninth      '9'                    1, 3, 5, b7, 9
        dominant-11th       '11'                   1, 3, 5, b7, 9, 11
        dominant-13th       '13'                   1, 3, 5, b7, 9, 11, 13
        augmented           'aug'                  1, 3, #5
        augmented-seventh   'aug7'                 1, 3, #5, b7
        diminished          'dim'                  1, b3, b5
        diminished-seventh  'dim7'                 1, b3, b5, 6
        half-diminished     'm7b5'                 1, b3, b5, b7
        suspended-fourth    'sus4'                 1, 4, 5
        suspended-second    'sus2'                 1, 2, 5
        power               '5', 'power'           1, 5
        ==================  =====================  =======================

    これらに加えて、<type> には次の文字列を指定できます。これらは
    各々の等号の右にあるコードと同じものだと解釈されます。

        '7sus4' = 'sus4add7', '9sus4' = 'sus4(9)add7',
        '7sus2' = 'sus2add7', 'mM11' = 'mM7(9,11)',
        'mM13' = 'mM7(9,11,13)', 'aug9' = 'aug7(9)',
        'aug11' = 'aug7(9,11)', 'aug13' = 'aug7(9,11,13)',
        'dim9' = 'dim7(9)', 'dim11' = 'dim7(9,11)',
        'm9b5' = 'm7b5(9)', 'm11b5' = 'm7b5(9,11)', 'm13b5' = 'm7b5(9,11,13)',
        '7alt' = '7(b9,#9,#11,b13)'

    <modification> は、次のいずれかによって変化音、追加音、または省略音を
    指定します。これは複数指定可能です。

        'add<任意個の#/b><整数>', 'alter<任意個の#/b><整数>', 'omit<整数>',
        'b5', '#5', 'M7', 'M9', 'M11', 'M13', 'b9', '9', '#9', '11', '#11',
        '13', 'b13'

    'add' は追加音、'alter' は変化音、'omit' は省略音の指定です。それ以外
    の <modification> は、指定された度数が <type> で定まるベースコードに
    含まれていれば変化音、そうでなければ追加音として扱われます。
    'M9', 'M11' 'M13' はそれぞれ、'M7,9 ', 'M7,9,11', 'M7,9,11,13' と等価です。

    /<bass> ばバス音を指定します（省略可）。指定方法は <root> と同じです。

    <root>, <type>, および 各<modification> への文字列の分け方に曖昧性があ
    る場合、先(左)にある要素にできるだけ長い文字列を割り当てようとします（
    いわゆる greedy ルール）。
    例えば、'Ab9' は、根音が 'Ab' の dominant-ninth コードと解釈されます。
    根音が 'A' の major コードに 'b9' のテンションを付加したものとしたい
    場合は、'A(b9)' のように間に区切りの文字を入れてください。
    同様に、'Ab5' は根音が 'Ab' のパワーコード、'A(b5)' は A majorコードの
    5度音を半音下げたコードと解釈されます。

    コード名の例: 'C7b9', 'C(9)', 'C69', 'C13#11', 'CaugM7', 'C#11',
        'CdimM9', 'F#m7b5(11)', 'C7sus4b9', 'C7omit3add2', 'C7(alter#5,addb9)',
        'C/E', 'FM7/G'

    .. rubric:: 演算規則

    * Chordオブジェクトどうしの等価比較('==')は、すべての属性値が
      等価であるときのみ真となります。
    * chord をChordオブジェクトとするとき、pitch ``in`` chord は
      chord.is_chord_tone(pitch) と等価です。
    """
    def __init__(self, name=None, *, kind=None, root=None, bass=None,
                 modifications=[]):
        self.kind = None
        self.root = None
        self.bass = None
        self.modifications = []
        if name is not None:
            self._parse_chord_name(name)
        if kind is not None:
            if kind not in _CHORD_KIND_DICT:
                raise TypeError("Unknown chord kind %r" % (kind, ))
            self.kind = kind
        if root is not None:
            self.root = root
        if self.kind is None or self.root is None:
            raise Exception("Either name or kind/root pair must be specified")
        if bass is not None:
            self.bass = bass
        for m in modifications:
            if not isinstance(m, (tuple, list)) or len(m) != 3 or \
               m[0] not in ('add', 'alter', 'subtract'):
                raise ValueError("Invalid chord modification %r" % (m,))
            self.modifications.append(tuple(m))

    def __repr__(self):
        return "%s(kind=%r, root=%r, bass=%r, modifications=%r)" % \
            (self.__class__.__name__, self.kind, self.root, self.bass,
             self.modifications)

    def __eq__(self, other):
        if not isinstance(other, Chord):
            return NotImplemented
        return self.__dict__ == other.__dict__

    def __contains__(self, pitch):
        return self.is_chord_tone(pitch)

    def copy(self) -> 'Chord':
        """
        複製されたChordオブジェクトを返します。modifications属性はリスト
        としての複製が行われます。
        """
        return self.__class__(kind=self.kind, root=self.root, bass=self.bass,
                              modifications=self.modifications.copy())
    __copy__ = copy

    def _parse_chord_name(self, name):
        def _skip_delim():
            nonlocal pos
            while pos < len(name) and name[pos] in " ,()":
                pos += 1

        # <root>
        pos = 0
        m = re.match("[A-Ga-g][#b]*", name[pos:])
        if not m:
            raise Exception("Unrecognized chord name: %s" % name)
        self.root = Pitch(m.group(0), octave=3)
        pos = m.end()

        # <type>
        tensions_by_alias = []
        while self.kind is None:
            for i in range(min(_MAX_NAME_LEN, len(name) - pos), -1, -1):
                try:
                    newtype, tensions = _ALIAS_DICT[name[pos:pos+i]]
                    name = name[0:pos] + newtype + name[pos+i:]
                    tensions_by_alias.extend(tensions)
                    break
                except KeyError:
                    pass
                try:
                    self.kind = _CHORD_NAME_DICT[name[pos:pos+i]]
                    pos += i
                    break
                except KeyError:
                    pass

        # <modification>*
        degrees = _CHORD_KIND_DICT[self.kind]
        _skip_delim()
        while pos < len(name):
            m = re.match("b5|#5|M7|M9|M11|M13|b9|9|#9|11|#11|13|b13|"
                         "(add|alter|omit)([#b]*|M)(-?[0-9]+)", name[pos:])
            if not m:
                break
            noeffect = False
            if m.group(1) is None:  # regular tensions/alternations
                for num, sf in _TENSION_ALTER_DICT[m.group(0)]:
                    if num in degrees:
                        # alterのときは、sfを元のコードのピッチからの相対値に
                        a = sf - degrees[num][0]
                        noeffect = (a == 0)
                        self.modifications.append(('alter', num, a))
                    else:
                        self.modifications.append(('add', num, sf))
            else:
                num = int(m.group(3))
                if m.group(1) == 'add' and abs(num) > 52 or \
                   m.group(1) != 'add' and (num < 1 or num > 13):
                    raise ValueError("Out-of-range degree number %d" % num)
                if m.group(1) == 'omit':
                    noeffect = (num not in degrees)
                    self.modifications.append(('subtract', num, 0))
                else:
                    sf = m.group(2).count('#') - m.group(2).count('b')
                    if num == 7 and m.group(2) == 'M':
                        sf = 1
                    noeffect = (m.group(1) == 'add' and num in degrees and
                                sf == degrees[num][0]) or \
                               (m.group(1) == 'alter' and num not in degrees)
                    self.modifications.append((m.group(1), num, sf))
            if noeffect:
                warnings.warn('%r of %r has no effect' % (m.group(0), name),
                              TaktWarning)
            pos += m.end()
            _skip_delim()
        for num in tensions_by_alias:
            # 'C9sus4b9'のような場合に♮9とb9が両方入らないようにする必要あり
            if not any(m[1] == num for m in self.modifications):
                self.modifications.append(('add', num, 0))

        mset = set()
        for m in self.modifications:
            if m in mset:
                warnings.warn('Duplicated modification %r in %r' % (m, name),
                              TaktWarning)
            mset.add(m)

        # /<bass>
        _skip_delim()
        m = re.match("/([A-Ga-g][#b]*)", name[pos:])
        if m:
            self.bass = Pitch(m.group(1), octave=3)
            pos += m.end()

        # error check
        _skip_delim()
        if pos < len(name):
            raise Exception("Unrecognized chord name: %s >>> %s <<<" %
                            (name[:pos], name[pos:]))

    def name(self) -> str:
        """ コード名を返します。このコード名をコンストラクタへ渡すと、
        根音やバス音のオクターブ番号を除いて等価な Chordオブジェクトが
        生成されます。
        """
        rootstr = Pitch(self.root).tostr(octave=False, sfn='#b')
        kindstr = _KIND_TO_NAME[self.kind]
        degrees = _CHORD_KIND_DICT[self.kind]
        modstrs = []
        for type, num, sf in self.modifications:
            if type == 'add' and (num not in degrees):
                ta = _INV_TENSION_ALTER_DICT.get((num, sf), None)
                if ta:
                    modstrs.append(ta)
                    continue
                if num == 7 and sf == 0 and kindstr in ('sus4', 'sus2'):
                    # '7sus4', '7sus2' が利用できる場合
                    kindstr = '7' + kindstr
                    continue
            if type == 'alter' and (num in degrees):
                ta = _INV_TENSION_ALTER_DICT.get((num, sf + degrees[num][0]),
                                                 None)
                if ta:
                    modstrs.append(ta)
                    continue
            modstrs.append('%s%s%d' %
                           ('omit' if type == 'subtract' else type,
                            'M' if num == 7 and sf == 1 else
                            '#' * sf if sf >= 0 else 'b' * -sf,
                            num))
        bassstr = ''
        if self.bass is not None:
            bstr = Pitch(self.bass).tostr(octave=False, sfn='#b')
            if rootstr != bstr:
                bassstr = '/' + bstr
        return rootstr + kindstr + (('(' + ','.join(modstrs) + ')')
                                    if modstrs else '') + bassstr

    # MusicXMLの <degrees>要素 (modifications) についての仕様の細部については、
    # 下のように解釈している。
    #   - subtractとalterは、基本コード(<kind>で指定されるコード)中の音のみを
    #     対象とし、addや他のalterによって生成された音は対象にしない。
    #   - <degree-alter>の値が 0 の alter は無効とする。
    #   - 基本コードに同じ度数かつ同じピッチの音が含まれている add は無効
    #     とする。
    #   - 同じ度数にピッチの異なる複数のalterがあるときは、すべての音をコード
    #     に含める。
    #   - addは、基本コードに同じ度数だが違うピッチの音が含まれている場合、
    #     単純に追加を行う（したがって、基本コードの音も残る)。
    #   - subtractは、その <degree-alter> の値にかかわらず、基本コード中の
    #     指定された度数の音をすべて削除する。

    def degrees(self, maxinterval=None) -> Dict[int, Tuple[int]]:
        """
        度数ごとの構成音を表した辞書(dict)オブジェクトを返します。
        辞書のキーは度数を表す整数であり、辞書の値は整数のタプルで各整数は
        Mixolydian スケール上の音からの乖離（半音単位）を表します。
        bass音は考慮されません。また、辞書のキー、および各タプル中の値は、
        ソートされているとは限りません。

        Args:
            maxinterval(Interval or int, optional): Intervalオブジェクト
                もしくは半音数を表す整数を指定すると、根音からの音程がこの値
                以内の音だけを出力するようになります。デフォルトでは、
                すべての音が出力されます。

        Examples:
            >>> Chord('CM7').degrees()
            {1: (0,), 3: (0,), 5: (0,), 7: (1,)}
            >>> Chord('G7(b13,#9,b9)').degrees()
            {1: (0,), 3: (0,), 5: (0,), 7: (0,), 13: (-1,), 9: (1, -1)}
            >>> Chord('CM13').degrees(maxinterval=Interval('M7'))
            {1: (0,), 3: (0,), 5: (0,), 7: (1,)}
        """
        base = _CHORD_KIND_DICT[self.kind]
        result = base.copy()
        for type, num, sf in self.modifications:
            if type == 'add' or type == 'alter':
                if type == 'alter':
                    if sf == 0 or num not in base:
                        continue
                    # resultの方からは削除（しないと元の音と両方入ってしまう)
                    bsf = base[num][0]
                    if num in result:
                        result[num] = tuple(x for x in result[num] if x != bsf)
                    sf += bsf
                # baseだけに入っている音(omitやalterによってresultから除か
                # れた音)に対してのadd は無視する (そうしないと alter#5 add5
                # と add5 alter#5 で結果が変わってしまうから)
                if not ((num in base and sf in base[num]) or
                        (num in result and sf in result[num])):
                    result[num] = (*result.get(num, ()), sf)
            elif type == 'subtract':
                if num in base:
                    sf = base[num][0]
                    if num in result and sf in result[num]:
                        result[num] = tuple(x for x in result[num] if x != sf)
        # maxintervalの条件を満たさないものを削除
        if maxinterval is not None:
            for num in result:
                result[num] = tuple(x for x in result[num]
                                    if _deg2semitones(num) + x <= maxinterval)
        # 空タプルの項目を削除
        for num in list(result.keys()):
            if not result[num]:
                del result[num]
        return result

    def simplify(self, use_extended_chords=True) -> 'Chord':
        """
        コード構成音を変えずに、modifications属性の要素数が最小になる
        ように修正した新しい Chord オブジェクトを返します。ルート音、
        バス音は変わりません。返されるコードにおいて modifications属性は、
        種別、度数、変化量をこの順にキーとしてソートされています。

        Args:
            use_extended_chords(bool, optional):
                False を指定すると、9th, 11th, 13th を含むコードは基本コード
                (kind属性で指定されるコード) として使用されなくなります。

        Examples:
            >>> Chord('C7add9')
            Chord(kind='dominant', root=C3, bass=None, modifications=[('add', \
9, 0)])
            >>> Chord('C7add9').simplify()
            Chord(kind='dominant-ninth', root=C3, bass=None, modifications=[])
            >>> Chord('C7add9').simplify().name()
            'C9'
            >>> Chord("C13(#11)").simplify(False).name()
            'C7(9,#11,13)'
        """
        def cost(base_degrees, target_degrees) -> Tuple[int, int, int]:
            add = alter = omit = 0
            for num, sflist in target_degrees.items():
                if num not in base_degrees:
                    add += len(sflist)
                elif not sflist:
                    omit += 1
                elif base_degrees[num][0] in sflist:
                    add += len(sflist) - 1
                else:
                    alter += 1
                    add += len(sflist) - 1
            for num, _ in base_degrees.items():
                if num not in target_degrees:
                    omit += 1
            return (add, alter, omit)

        # コスト(=add,alter,omitの数)が最小のkindを求める
        # (同コストのときは _CHORD_KIND_DICTで先に出現するものを優先)。
        degrees = self.degrees()
        bestkind = None
        bestcost = math.inf
        for kind, base_degrees in _CHORD_KIND_DICT.items():
            if not use_extended_chords and 9 in base_degrees:
                continue
            c = sum(cost(base_degrees, degrees))
            if kind in ('power', 'sus2') and c > 0:
                # 上のコードのときは、modifications を認めないようしている。
                continue
            if c < bestcost:
                bestcost = c
                bestkind = kind

        # modificationsを求める
        base = _CHORD_KIND_DICT[bestkind]
        newmods = []
        for num, sflist in degrees.items():
            basesf = base.get(num, (None,))[0]
            omit = (basesf is not None) and (basesf not in sflist)
            for sf in sorted(sflist):
                if sf != basesf:
                    if omit:
                        newmods.append(('alter', num, sf - basesf))
                        omit = False
                    else:
                        newmods.append(('add', num, sf))
            if omit:
                newmods.append(('subtract', num, 0))
        for num, sflist in base.items():
            if num not in degrees:
                newmods.append(('subtract', num, 0))

        newmods.sort(key=lambda m:
                     ({'alter': 0, 'add': 1, 'subtract': 2}[m[0]], m[1], m[2]))
        return Chord(kind=bestkind, root=self.root, bass=self.bass,
                     modifications=newmods)

    def pitches(self, maxinterval=None) -> List[Pitch]:
        """
        コード構成音のピッチのリストを返します。バス音が指定されている場合、
        それも含められます（このときバス音と同じピッチクラスの他の音は取り
        除かれ、また、バス音より低い他の音は、バス音より高くなるように
        オクターブが上げられます）。

        Args:
            maxinterval(Interval or int, optional): :meth:`degrees` の
                同名の引数と同じ意味を持ちます。

        Examples:
            >>> Chord('Cdim7').pitches()
            [C3, Eb3, Gb3, A3]
            >>> Chord('G7/F').pitches()
            [F3, G3, B3, D4]
            >>> Chord('F/G').pitches()
            [G3, A3, C4, F4]
        """
        degrees = self.degrees()
        result = []
        for num, sflist in self.degrees(maxinterval).items():
            s = _deg2semitones(num)
            for sf in sflist:
                if num == 7 and sf == -1:
                    # dim7の第4音は、ダブルフラットにしない方がより一般的か
                    p = self.root + Interval(s + sf, 5)
                else:
                    p = self.root + Interval(s + sf, num - 1)
                if self.bass is not None:
                    if chroma(p) == chroma(self.bass):
                        continue
                    while p < self.bass:
                        p += Interval('P8')
                result.append(p)
        if self.bass is not None:
            result.append(self.bass)
        result.sort()
        return result

    def pitches_above(self, pitch, stop=None,
                      maxinterval=None) -> Iterator[Pitch]:
        """
        `pitch` より上にあるコード構成音 (bass音およびオクターブが異なる音を
        含む) のピッチを順に yield するジェネレータ関数です。

        Args:
            pitch(Pitch or int):
                基準となるピッチ
            stop(int, optional):
                指定すると、その個数だけに限定して出力します。
            maxinterval(Interval or int, optional): :meth:`degrees` の
                同名の引数と同じ意味を持ちます。

        Examples:
            >>> list(Chord('C7').pitches_above(D4, 5))
            [E4, G4, Bb4, C5, E5]
        """
        # 下の式は p を pitch+1 から始まる1オクターブ内に補正している。
        pitches = sorted({(math.floor((pitch - p) / 12) + 1) * Interval('P8')
                          + p for p in self.pitches(maxinterval)})

        def _gen():
            for k in itertools.count():
                for p in pitches:
                    yield p + k * Interval('P8')
        return itertools.islice(_gen(), 0, stop)

    def pitches_below(self, pitch, stop=None,
                      maxinterval=None) -> Iterator[Pitch]:
        """
        `pitch` より下にあるコード構成音 (bass音およびオクターブが異なる音を
        含む) のピッチを順に yield するジェネレータ関数です。

        Args:
            pitch(Pitch or int):
                基準となるピッチ
            stop(int, optional):
                指定すると、その個数だけに限定して出力します。
            maxinterval(Interval or int, optional): :meth:`degrees` の
                同名の引数と同じ意味を持ちます。
        """
        pitches = sorted({-(math.floor((p - pitch) / 12) + 1) * Interval('P8')
                          + p for p in self.pitches(maxinterval)}, reverse=True)

        def _gen():
            for k in itertools.count():
                for p in pitches:
                    yield p - k * Interval('P8')
        return itertools.islice(_gen(), 0, stop)

    # Now, use chroma_profile(c.pitches())
    # def chroma_profile(self, maxinterval=None) -> List[int]:
    #     """
    #     ピッチクラス (:func:`.chroma` を参照) ごとに、音が存在すれば 1、
    #     存在しなければ 0 とした 12要素のリストを返します。

    #     Args:
    #         maxinterval(Interval or int, optional): :meth:`degrees` の
    #             同名の引数と同じ意味を持ちます。

    #     Examples:
    #         >>> Chord('G7').chroma_profile()
    #         [0, 0, 1, 0, 0, 1, 0, 1, 0, 0, 0, 1]
    #     """
    #     result = [0 for _ in range(12)]
    #     for num, sflist in self.degrees(maxinterval).items():
    #         s = int(self.root) + _deg2semitones(num)
    #         for sf in sflist:
    #             result[chroma(s + sf)] = 1
    #     if self.bass is not None:
    #         result[chroma(self.bass)] = 1
    #     return result

    def is_chord_tone(self, pitch, maxinterval=None) -> bool:
        """
        コード構成音に `pitch` と同じピッチクラスの音が含まれていれば
        真を返し、そうでなければ偽を返します。
        なお、pitch ``in`` self は self.is_chord_tone(pitch) と等価です。

        Args:
            maxinterval(Interval or int, optional): :meth:`degrees` の
                同名の引数と同じ意味を持ちます。
        """
        for num, sflist in self.degrees(maxinterval).items():
            s = int(self.root) + _deg2semitones(num)
            for sf in sflist:
                if chroma(s + sf) == chroma(pitch):
                    return True
        if self.bass is not None and chroma(self.bass) == chroma(pitch):
            return True
        return False

    def demo(self, **kwargs) -> 'Score':
        """ コードについてのデモ演奏のスコアを返します。

        Args:
             kwargs: note関数に渡される追加の引数
        """
        from takt.sc import note
        from takt.score import par
        score = par(note(p, **kwargs) for p in self.pitches())
        return score * 4 + score.TimeStretch(3).Arpeggio(L16)

    @staticmethod
    def from_chroma_profile(chroma_profile, bass=None) -> 'Chord':
        """
        クロマプロファイル (:func:`.chroma_profile` を参照) から推測した
        コードをを返します。クロマプロファイルの各要素はその真偽値のみが
        推測に利用されます。全要素が偽のクロマプロファイルを与えたときは
        例外を送出します。

        Args:
            bass(Pitch or int, optional): コードのバス音を指定します。
                これは出力されるコードにバス音として設定されるだけでなく、
                推測の際の根音のヒントとして働きます。

        Examples:
            >>> cp = [1, 0, 1, 0, 1, 1, 0, 0, 0, 1, 0, 0]
            >>> Chord.from_chroma_profile(cp).name()
            'Dm9'
            >>> Chord.from_chroma_profile(cp, bass=F3).name()
            'FM7(13)'
            >>> Chord.from_chroma_profile(cp, bass=C3).name()
            'Dm9/C'
        """
        if len(chroma_profile) != 12:
            raise Exception('Length of the chorma profile must be 12')
        bcp = sum(bool(v) << i for i, v in enumerate(chroma_profile))
        if not bcp:
            raise Exception('Empty chorma profile')
        if bass is not None:
            bcp |= 1 << chroma(bass)

        best_dist = math.inf
        best_idx = math.inf
        best_isbass = 0
        best_chroma = None
        best_bcp = None
        for i in range(12):
            if bcp & 1:
                isbass = bass is not None and i == chroma(bass)
                for idx, kind_bcp in enumerate(_CHORD_BCP):
                    dist = bin(bcp ^ kind_bcp).count('1')  # Hamming距離
                    if kind_bcp in (0x81, 0x85) and dist != 0:
                        # 'power', 'sus2' のときは、exact match以外認めない
                        continue
                    if (dist - isbass, idx) < (best_dist - best_isbass,
                                               best_idx):
                        best_dist = dist
                        best_idx = idx
                        best_isbass = isbass
                        best_chroma = i
                        best_bcp = bcp
            bcp = (bcp >> 1) | ((bcp & 1) << 11)

        kind, degrees = tuple(_CHORD_KIND_DICT.items())[best_idx]
        modifications = []
        for i in range(12):
            if (best_bcp >> i) & 1 and not (_CHORD_BCP[best_idx] >> i) & 1:
                num, sf = _CHROMA2DEGSF[i]
                # b5/#11, #5/b13の選択 => 基本コードに5があって、omitされてい
                # ないときに #11,b13
                if i in (6, 8) and not ((5 in degrees) and
                                        (best_bcp >> (7 + degrees[5][0])) & 1):
                    num = 5
                    sf = -sf
                modifications.append(('add', num, sf))
        for num, sf in degrees.items():
            if not (best_bcp >> ((_deg2semitones(num) + sf[0]) % 12)) & 1:
                modifications.append(('subtract', num, 0))

        root = Pitch(int(C3) + best_chroma)
        if isinstance(bass, Pitch) and chroma(bass) == best_chroma:
            root.sf = bass.sf
        return Chord(kind=kind, root=root, bass=bass,
                     modifications=modifications).simplify()
