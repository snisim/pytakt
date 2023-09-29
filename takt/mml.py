# coding:utf-8
"""
このモジュールには、カスタマイズ可能な MML (Music Macro Language) に
関連した関数が定義されています。
"""
# Copyright (C) 2023  Satoshi Nishimura

import re
import os
import builtins
from arpeggio import ZeroOrMore, Optional, RegExMatch, EOF, \
                     NonTerminal, ParserPython, NoMatch, Sequence
from fractions import Fraction
from takt.score import Score, EventList
from takt.context import context, newcontext, Context
from takt.pitch import *
from takt.ps import *
from takt.constants import *
import takt.gm as gm
from takt.gm.drums import *
from takt.frameutils import outerglobals, outerlocals
from takt.utils import int_preferred, Ticks
from typing import Optional as _Optional
from typing import Union, Mapping, Callable


__all__ = ['mml', 'mmlconfig', 'MMLAction']


Char = str

class MMLError(Exception):
    def __init__(self, message, source=None):
        super().__init__(message)
        self.source = source


# MML grammar begin
def score(): return ZeroOrMore(command), EOF
def command(): return [setlength,
                       assignment,
                       modified_command,
                       comment_string]
def comment_string(): return RegExMatch(';[^\n]*')
def setlength(): return length_constant()
def assignment(): return (context_variable_lhs, assign_op, expression),
def modified_command(): return (ZeroOrMore(prefixchar),
                                primary_command, ZeroOrMore(modifier))
def primary_command(): return [cmdchar,
                               ("{", ZeroOrMore(command), "}"),
                               ("[", ZeroOrMore(command), "]"),
                               ("$", python_id, ":", "{",
                                ZeroOrMore(command), "}"),
                               python_expression]
def cmdchar(): return RegExMatch('[^%s%s%s]' %
                                 (_RESERVED_CHARS,
                                  re.escape(MMLConfig.prefixes),
                                  re.escape(MMLConfig.suffixes)))
def modifier(): return [suffixchar,
                        ("/", Optional(integer)),
                        ("|", python_funcall),
                        integer,
                        "&",
                        ("@", integer),
                        ("@", "@"),
                        ("(", ZeroOrMore(command), ")"),
                        (':', balanced_paren)]
def suffixchar(): return RegExMatch('[\x00%s]' % re.escape(MMLConfig.suffixes))
def prefixchar(): return RegExMatch('[\x00%s]' % re.escape(MMLConfig.prefixes))
def context_variable(): return ["dt", "tk", "ch", "v", "nv", "L",
                                "duoffset", "du", "durate", "dr", "o", "key"]
def length_constant(): return RegExMatch(r'L\d+(DOT){0,2}')
def context_variable_lhs(): return context_variable()
def assign_op(): return ["=", "+=", "-=", "*=", "/=", "//=", "%="]

def python_expression(): return [("$", python_funcall),
                                 ("$", balanced_paren)]
def python_funcall(): return (python_id, ZeroOrMore((".", python_id)),
                              balanced_paren)
def python_id(): return RegExMatch(r'[^\d\W]\w*')
def balanced_paren(): return Sequence(RegExMatch(r'\s*\('),
                                      ZeroOrMore(balanced_paren_body),
                                      ")", skipws=False)
def balanced_paren_body(): return [balanced_paren,
                                   RegExMatch(r'[^()]')]

def expression(): return term, ZeroOrMore(["+", "-"], term)
def term(): return factor, ZeroOrMore(["*", "//", "/", "%"], factor)
def factor(): return Optional("-"), primary
def primary(): return [floating, integer,
                       length_constant, context_variable,
                       python_expression, ("(", expression, ")")]
def integer(): return RegExMatch(r'\d+')
# "v=0x10ceg" のような曖昧なケースが発生するので廃止。必要なら $(0x..) を使う。
# def hexinteger(): return RegExMatch(r'0[xX][\da-fA-F]+')
def floating(): return RegExMatch(r'\d+\.\d*|\d*\.\d+')
# MML grammar end


_RESERVED_CHARS = r'Ln\d\s()\[\]{}=$|&/:;@'


def check_reserved(char) -> None:
    if re.match('[%s]' % _RESERVED_CHARS, char):
        raise ValueError("`%c' is not a configurable character" % char)


class MMLAction(object):
    @staticmethod
    def mod_octaveup():
        context().o += 1

    @staticmethod
    def mod_octavedown():
        context().o -= 1

    @staticmethod
    def mod_sharp():
        context()._accidentals += '+'

    @staticmethod
    def mod_flat():
        context()._accidentals += '-'

    @staticmethod
    def mod_natural():
        context()._accidentals += '%'

    @staticmethod
    def mod_double_length():
        context().L *= 2

    @staticmethod
    def mod_dotted_note():
        n = (0 if not hasattr(context(), '_dotcnt')
             else context()._dotcnt) + 1
        context().addattr('_dotcnt', n)
        context().L = int_preferred(context().L * (2 - 0.5 ** n)
                                    / (2 - 0.5 ** (n - 1)))

    @staticmethod
    def clear_dotcnt():
        if hasattr(context(), '_dotcnt'):
            delattr(context(), '_dotcnt')

    @staticmethod
    def mod_increase_velocity():
        context().v += MMLConfig.accent_amount

    @staticmethod
    def mod_decrease_velocity():
        context().v -= MMLConfig.accent_amount

    @staticmethod
    def mod_increase_dt():
        context().dt += MMLConfig.timeshift_amount

    @staticmethod
    def mod_decrease_dt():
        context().dt -= MMLConfig.timeshift_amount

    @staticmethod
    def mod_staccato():
        context().dr *= MMLConfig.staccato_amount

    @staticmethod
    def mod_addlength():
        if not hasattr(context(), '_ladd'):
            context().addattr('_ladd', 0)
        context()._ladd += context().L
        context().L = context()._lorg
        MMLAction.clear_dotcnt()

    @staticmethod
    def update_length():
        if hasattr(context(), '_ladd'):
            context().L += context()._ladd
            delattr(context(), '_ladd')
        delattr(context(), '_lorg')
        MMLAction.clear_dotcnt()

    @staticmethod
    def mod_undefined(char):
        def func():
            raise MMLError("Undefined modifier charactor `%c'" % char)
        return func

    @staticmethod
    def cmd_note(pitch_char):
        return lambda: note(Pitch(pitch_char + context()._accidentals,
                                  key=context().key, octave=context().o))

    @staticmethod
    def cmd_rest():
        return rest(context().L)

    @staticmethod
    def cmd_octaveup():
        context()._outer_context.o += 1

    @staticmethod
    def cmd_octavedown():
        context()._outer_context.o -= 1

    @staticmethod
    def cmd_undefined(char):
        def func():
            raise MMLError("Undefined command charactor `%c'" % char)
        return func

    @staticmethod
    def no_op():
        pass


class MMLConfig(object):
    prefixes: str = '^_'
    suffixes: str = '\',#b%*.+-!?`~><\\"'
    char_actions: Mapping[Char, Callable[[], _Optional[Score]]] = {
        '^': MMLAction.mod_octaveup,
        '_': MMLAction.mod_octavedown,
        "'": MMLAction.mod_octaveup,
        ',': MMLAction.mod_octavedown,
        '#': MMLAction.mod_sharp,
        'b': MMLAction.mod_flat,
        '%': MMLAction.mod_natural,
        '*': MMLAction.mod_double_length,
        '.': MMLAction.mod_dotted_note,
        '+': MMLAction.mod_sharp,
        '-': MMLAction.mod_flat,
        '`': MMLAction.mod_increase_velocity,
        '?': MMLAction.mod_decrease_velocity,
        '!': MMLAction.mod_staccato,
        '~': MMLAction.mod_addlength,
        '>': MMLAction.mod_increase_dt,
        '<': MMLAction.mod_decrease_dt,
        '\\': MMLAction.mod_undefined('\\'),
        '"': MMLAction.mod_undefined('"'),

        'C': MMLAction.cmd_note('C'),
        'D': MMLAction.cmd_note('D'),
        'E': MMLAction.cmd_note('E'),
        'F': MMLAction.cmd_note('F'),
        'G': MMLAction.cmd_note('G'),
        'A': MMLAction.cmd_note('A'),
        'B': MMLAction.cmd_note('B'),
        'H': MMLAction.cmd_note('B'),
        'c': MMLAction.cmd_note('C'),
        'd': MMLAction.cmd_note('D'),
        'e': MMLAction.cmd_note('E'),
        'f': MMLAction.cmd_note('F'),
        'g': MMLAction.cmd_note('G'),
        'a': MMLAction.cmd_note('A'),
        'h': MMLAction.cmd_note('B'),
        'R': MMLAction.cmd_rest,
        'r': MMLAction.cmd_rest,
        # '^': MMLAction.cmd_octaveup,
        # '_': MMLAction.cmd_octavedown,
        ' ': MMLAction.no_op,
    }
    octave_number_suffix: bool = True
    accent_amount: Ticks = 10
    timeshift_amount: Ticks = L64
    staccato_amount: float = 0.5

    @staticmethod
    def show_config():
        print("prefixes=%r" % MMLConfig.prefixes)
        print("suffixes=%r" % MMLConfig.suffixes)
        print("char_actions:")
        for item in MMLConfig.char_actions.items():
            print("    %r: %r" % item)
        print("octave_number_suffix=%r" % MMLConfig.octave_number_suffix)
        print("accent_amount=%r" % MMLConfig.accent_amount)
        print("timeshift_amount=%r" % MMLConfig.timeshift_amount)
        print("staccato_amount=%r" % MMLConfig.staccato_amount)


class MMLEvaluator(object):
    def __init__(self, globals, locals):
        self.globals = globals
        self.locals = locals

    def evalnode(self, node) -> Union[Score, int, float, Ticks, str, None]:
        method_name = "eval_" + node.rule_name
        if hasattr(self, method_name):
            return getattr(self, method_name)(node)
        else:
            if isinstance(node, NonTerminal):
                return self.evalnode(node[0])
            else:
                return node.value

    def eval_EOF(self, node) -> None:
        pass

    def concat_scores(self, score1, score2) -> _Optional[Score]:
        if score1 is None:
            return score2
        elif score2 is None:
            return score1
        else:
            score1 += score2
            return score1

    def merge_scores(self, score1, score2) -> _Optional[Score]:
        if score1 is None:
            return score2
        elif score2 is None:
            return score1
        else:
            score1 &= score2
            return score1

    def eval_score(self, node) -> Score:
        result = EventList()
        for child in node:
            result = self.concat_scores(result, self.evalnode(child))
        return result

    def eval_comment_string(self, node) -> None:
        pass

    def eval_setlength(self, node) -> None:
        context().L = eval(node.value, self.globals, self.locals)

    def eval_assignment(self, node) -> None:
        varname = node[0].value
        rhs = self.evalnode(node[2])
        if node[1].value == '=':
            setattr(context(), varname, rhs)
        elif node[1].value == '+=':
            setattr(context(), varname, getattr(context(), varname) + rhs)
        elif node[1].value == '-=':
            setattr(context(), varname, getattr(context(), varname) - rhs)
        elif node[1].value == '*=':
            setattr(context(), varname, getattr(context(), varname) * rhs)
        elif node[1].value == '/=':
            setattr(context(), varname, getattr(context(), varname) / rhs)
        elif node[1].value == '//=':
            setattr(context(), varname, getattr(context(), varname) // rhs)
        elif node[1].value == '%=':
            setattr(context(), varname, getattr(context(), varname) % rhs)
        else:
            assert False

    def eval_modified_command(self, node) -> _Optional[Score]:
        com = 0
        while node[com].rule_name == 'prefixchar':
            com += 1
        if node[com][0].value == '$':
            nc = eval(self.evalnode(node[com][1]),
                      self.globals, self.locals).copy()
        else:
            nc = newcontext()
        nc.addattr('_accidentals', '')
        nc.addattr('_lorg', nc.L)
        nc.addattr('_effectors', [])
        nc.addattr('_ampersand', False)
        with nc:
            result = None
            # evaluate prefixes (pre-modifiers)
            for k in range(0, com):
                result = self.merge_scores(result, self.evalnode(node[k]))
            # evaluate suffixes (post-modifiers)
            for k in range(com + 1, len(node)):
                result = self.merge_scores(result, self.evalnode(node[k]))
            MMLAction.update_length()
            # evaluate body command
            result = self.merge_scores(result, self.evalnode(node[com]))
            while context()._effectors and result is not None:
                result = context()._effectors.pop(0)(result)
            if context()._ampersand and result is not None:
                result = EventList(result, duration=0)
            return result

    def eval_primary_command(self, node) -> _Optional[Score]:
        if node[0].value == '{' or node[0].value == '$':
            result = EventList()
            for i in range(1 if node[0].value == '{' else 4, len(node) - 1):
                result = self.concat_scores(result, self.evalnode(node[i]))
        elif node[0].value == '[':
            result = EventList()
            for i in range(1, len(node) - 1):
                result = self.merge_scores(result, self.evalnode(node[i]))
        elif node[0].rule_name == 'python_expression':
            result = self.evalnode(node[0])
        else:
            try:
                action = MMLConfig.char_actions[node.value]
            except KeyError:
                raise MMLError("Unknown command `%c' at position %d"
                               % (node.value, node.position))
            result = action()
        return result

    def eval_modifier(self, node) -> _Optional[Score]:
        if node[0].rule_name == 'integer':
            if MMLConfig.octave_number_suffix:
                context().o = self.evalnode(node[0])
            else:
                context().L = int_preferred(Fraction(L1,
                                                     self.evalnode(node[0])))
        elif node[0].value == '/':
            div = 2 if len(node) == 1 else self.evalnode(node[1])
            if type(context().L) == float:
                context().L = int_preferred(context().L / div)
            else:
                context().L = int_preferred(Fraction(context().L, div))
        elif node[0].value == '&':
            context()._ampersand = True
        elif node[0].value == '@':
            from takt.effector import Repeat
            if node[1].value == '@':
                context()._effectors.append(Repeat())
            else:
                context()._effectors.append(Repeat(self.evalnode(node[1])))
        elif node[0].value == '(':
            result = None
            for i in range(1, len(node) - 1):
                result = self.merge_scores(result, self.evalnode(node[i]))
            return result
        elif node[0].value == '|':
            try:
                eff = eval(self.evalnode(node[1]), self.globals, self.locals)
            except Exception as e:
                raise MMLError('effector evaluation', e)
            context()._effectors.append(eff)
        elif node[0].value == ':':
            eval("context().update" + self.evalnode(node[1]),
                 self.globals, self.locals)
        else:
            return self.evalnode(node[0])

    def eval_prefixchar(self, node) -> _Optional[Score]:
        try:
            return MMLConfig.char_actions[node.value]()
        except KeyError:
            MMLAction.mod_undefined(node.value)()

    eval_suffixchar = eval_prefixchar

    def eval_context_variable(self, node) -> Union[int, float, Ticks, None]:
        return getattr(context(), node.value)

    def eval_length_constant(self, node) -> Ticks:
        return eval(node.value, self.globals, self.locals)

    def eval_python_expression(self, node) -> Union[Score, int, float,
                                                    Ticks, None]:
        try:
            return eval(self.evalnode(node[-1]), self.globals, self.locals)
        except Exception as e:
            raise MMLError('python expression', e)

    def eval_python_funcall(self, node) -> str:
        return ''.join([self.evalnode(n) for n in node])

    def eval_balanced_paren(self, node) -> str:
        return ''.join([self.evalnode(n) for n in node])

    def eval_expression(self, node) -> Union[int, float, Ticks, None]:
        result = self.evalnode(node[0])
        for i in range(1, len(node), 2):
            if node[i].value == '+':
                result += self.evalnode(node[i + 1])
            elif node[i].value == '-':
                result -= self.evalnode(node[i + 1])
            else:
                assert False
        return result

    def eval_term(self, node) -> Union[int, float, Ticks, None]:
        result = self.evalnode(node[0])
        for i in range(1, len(node), 2):
            if node[i].value == '*':
                result *= self.evalnode(node[i + 1])
            elif node[i].value == '/':
                result /= self.evalnode(node[i + 1])
            elif node[i].value == '//':
                result //= self.evalnode(node[i + 1])
            elif node[i].value == '%':
                result %= self.evalnode(node[i + 1])
            else:
                assert False
        return result

    def eval_factor(self, node) -> Union[int, float, Ticks, None]:
        return self.evalnode(node[0]) if len(node) == 1 \
            else -self.evalnode(node[1])

    def eval_primary(self, node) -> Union[int, float, Ticks, None]:
        return self.evalnode(node[0]) if len(node) == 1 \
            else self.evalnode(node[1])

    def eval_integer(self, node) -> int:
        return int(node.value)

    def eval_hexinteger(self, node) -> int:
        return int(node.value, 16)

    def eval_floating(self, node) -> float:
        return float(node.value)


parser = None


def mml(text, globals=None, locals=None) -> Score:
    """
    引数 `text` の MML (Music Macro Language) 記述に従ったスコアを返します。
    MML は文字列によって音楽フレーズを簡潔に表現します。

    Args:
        text(str): MML文字列
        globals(dict, optional):
            MML文字列中のPython変数名やPython関数名に対する大域変数辞書。
            デフォルトでは、mml関数を呼ぶ時点での globals() の値になって
            います。
        locals(dict, optional):
            MML文字列中のPython変数名やPython関数名に対する局所変数辞書。
            デフォルトでは、mml関数を呼ぶ時点での locals() の値になって
            います。

    Examples:
        >>> mml('eefg gfed ccde e.d/d*').play()
        >>> mml('L8 G~rD G~rD GDGB ^D~rr ^C~rA ^C~rA ^CAF#A D~rr').play()
        >>> mml("L8 o=5 key=-3 $tempo(60) _B G~~~ F G F~~ E~  _B G~ \
{C Db C _B% C}/5 ^C~").play()
        >>> mml("L8 {dr=30 E(L16) E(L=L8+L16) E(v+=5) E(dr=50 dt=10)} G/`> \
G/!? G/ G/!? G3*").show(True)
        >>> mml('[ceg]@@').play()  # 停止するには Ctrl-C
        >>> rh = newcontext(tk=1)
        >>> lh = newcontext(tk=2)
        >>> mml(\"""
        ... $tempo(160)
        ... $prog(gm.Harpsichord)
        ... [
        ...    $rh: { ^D {G A B ^C}/  ^D G G }
        ...    $lh: { [{_G* _A} _B*. D*.] _B*. }
        ... ]
        ... [
        ...    $rh: { ^E ^{C D E F#}/  ^G G G }
        ...    $lh: { C*. _B*. }
        ... ]
        ... \""").play()
        >>> mml('ch=10 [{$BD() r $SD() r} $HH()@4]').play()

    .. rubric:: 本MMLの言語仕様

    本MMLの記述全体は、**コマンド** の列から成ります。各コマンドは、1つの
    **基本コマンド** を含み、その前には任意個の **前置修飾子**、その後には
    任意個の **後置修飾子** が置かれます。たとえば、``CD#4^E`` は3つの
    コマンドから成り、``C``, ``D``, ``E`` がそれぞれ基本コマンド、``#`` と
    ``4`` は ``D`` に対する後置修飾子、``^`` は ``E`` に対する前置修飾子です。

    空白文字(スペース、タブ、改行)は、識別子、数値、および2文字以上からなる
    演算子の途中を除き、自由に挿入できます。セミコロン (';') から
    行の終わりまではコメントとみなされ、コマンドとコマンドの間に自由に挿入
    できます。

    .. rubric:: 基本コマンド一覧

    デフォルト設定で使用可能な基本コマンドは以下の通りです。

    ``A`` ～ ``H`` または ``a`` ～ ``h`` (``b`` を除く)
        :func:`.note` 関数によって指定された音名の音符を生成します。
        ``B`` と ``H`` は、ともに ``C`` の長七度上の音を表します。
        小文字も使用でき、意味は変わりません（ただし、``b`` はフラットに
        割り当てられているため使用できません）。
        オクターブ番号はコンテキストのo属性から取得されます。
    ``r`` または ``R``
        :func:`.rest` 関数によって休符を生成します。
    ``L``\\ <整数>, ``L``\\ <整数>\\ ``DOT``, ``L``\\ <整数>\\ ``DOTDOT``
        音価を設定します。<整数>は 1, 2, 4, 8, 16, 32, 64, 128 のいずれかです。
        このコマンドの実行により、コンテキストのL属性の値が
        :mod:`takt.constants` モジュールに定義されている同名の定数の値に
        なります。たとえば、``L8`` は以降の音符・休符を8分音符の長さに設定
        します。
    <コンテキスト属性名> ``=`` <単純式>
        コンテキスト属性の値を変更します (例: ``v=100``)。
        使用できるコンテキスト属性名は、dt, tk, ch, v, nv, L, duoffset, du,
        durate, dr, o, key のみです。単純式については下を見てください。
    <コンテキスト属性名> op\\ ``=`` <単純式>
        <コンテキスト属性名> ``=`` <コンテキスト属性名> op <単純式> と
        等価です。opは単純式の中で使える演算子のいずれかです。
    ``{`` 0個以上のコマンドの列 ``}``
        コピーされた別のコンテキストを用いて中括弧内のコマンドを実行し、
        その結果のスコア群を逐次的に結合します。
        これは一時的にコンテキスト属性値を変更する場合に使用でき、たとえば
        ``L4 C {L8 D E} F`` において、D, E音は8分音符になりますが、F音は
        4分音符に戻ります。
    ``[`` 0個以上のコマンドの列 ``]``
        コピーされた別のコンテキストを用いて角括弧内のコマンドを実行し、
        その結果のスコア群を同時演奏するように併合します。
        たとえば、``[CEG]`` のように和音を表したり、
        ``[C* {FE}]`` のように複数の声部を表現するために使用できます。
    ``$``\\ <Python変数名>\\ ``:{`` 0個以上のコマンドの列 ``}``
        <Python変数名>にコンテキストが格納されている変数の名前を指定すると、
        そのコンテキストのコピーを用いて中括弧内のコマンドを実行し、
        その結果のスコア群を逐次的に結合します。
        <Python変数名> はドット('.')を含んでいても構いません。
    ``$(``\\ <Python式>\\ ``)`` および \
    ``$``\\ <Python関数名>\\ ``(``\\ <Python引数>\\ ``,`` ... ``)``
        ともに ``$`` に続く文字列を Pythonのコードとみなして評価し、その値を
        スコアとして挿入します (ただし、Noneの場合は挿入されません)。
        <Python関数名> はドット('.')を含んでいても構いません。
        なお、次のモジュールで定義されている名前、および takt.gm モジュールを
        表す 'gm' は、たとえ mml関数の外では直接参照できない場合でも、
        MML文字列の中ではパッケージ名やモジュール名を指定せずに使えます:
        takt.pitch, takt.ps, takt.constants, takt.gm.drums。

    .. rubric:: 単純式

    <単純式> は、整数、浮動小数点数、音価定数(L4など)、コンテキスト属性名、
    括弧で囲んだ単純式、``$(`` と ``)`` で囲まれたPythonの式、``$`` に続く
    Pythonの関数呼び出し、またはこれらを演算子(``+``, ``-``, ``*``, ``/``,
    ``//``, ``%`` のいずれか) で結合したものです。

    .. rubric:: 前置修飾子

    デフォルト設定で使用可能な前置修飾子は以下の通りです。
    これらは、音価指定、代入コマンドを除くコマンドにおいて使用可能です。
    修飾子によるコンテキスト属性値の変更は、修飾されるコマンドにのみ有効で、
    後続のコマンドの実行には影響を与えません。

    ``^``
        オクターブ・アップ。コンテキストのo属性の値を1増やします。
    ``_``
        オクターブ・ダウン。コンテキストのo属性の値を1減らします。

    .. rubric:: 後置修飾子

    デフォルト設定で使用可能な後置修飾子は以下の通りです。
    これらは、音価指定、代入コマンドを除くコマンドにおいて使用可能です。
    修飾子によるコンテキスト属性値の変更は、修飾されるコマンドにのみ有効で、
    後続のコマンドの実行には影響を与えません。

    <整数>
        数値によってオクターブを指定します (4が中央ハを含むオクターブ)。
    ``#`` または ``+``
        シャープ。ピッチを半音上げます。
    ``b`` または ``-``
        フラット。ピッチを半音下げます。
    ``%``
        ナチュラル。keyコンテキスト属性の値が0以外のときのみ有効で、シャープや
        フラットのないピッチへ戻します。
    ``'``
        オクターブ・アップ。``^`` と同じ意味です。
    ``,``
        オクターブ・ダウン。``_`` と同じ意味です。
    ``*``
        音価を2倍にします。
    ``/``
        音価を0.5倍にします。
    ``/``\\ <整数>
        音価を <整数> 分の1にします。連符の表現に使用できます。
    ``.``
        付点。1つ置くと音価が1.5倍、2つ置くと1.75倍になります。
    ``~``
        複数の（空を含む）音価指定を結合してその和をとります。たとえば、
        ``*~/`` は音価を2.5倍、``~`` は2倍、``~~`` は3倍、``~..`` は
        2.75倍にすることを意味します。
    :code:`\``
        ベロシティを 10 増やします。``(v+=10)`` と等価です。
    ``?``
        ベロシティを 10 減らします。``(v-=10)`` と等価です。
    ``!``
        drコンテキスト属性の値を 0.5倍します。``(dr*=0.5)`` と等価です。
        いわゆるスタッカートに相当します。
    ``>``
        dtコンテキスト属性の値を 30ティック (64分音符相当) 増やして、
        演奏タイミングを少し遅らせます。``(dt+=30)`` と等価です。
    ``<``
        dtコンテキスト属性の値を 30ティック (64分音符相当) 減らして、
        演奏タイミングを少し早めます。``(dt-=30)`` と等価です。
    ``&``
        演奏長を 0 にして以降の演奏に重ねます。
    ``@``\\ <整数>
        <整数>回演奏を繰り返します。``|Repeat(``\\ <整数>\\ ``)`` と等価です。
    ``@@``
        無限回演奏を繰り返します。``|Repeat()`` と等価です。
    ``(`` 0個以上のコマンドの列 ``)``
        各コマンドを実行してから、修飾の対象となるコマンドを実行します。
        主に、一時的にコンテキストを変更する目的に使われます。
        例: ``C(v=30 dt+=10)``
    ``:(``\\ <Python識別子>\\ ``=``\\ <Python式>\\ ``,`` ... ``)``
        任意のコンテキスト属性を一時的に変更します。
        例: ``{CDE}:(user_attr=1)``
    ``|``\\ <Python識別子>\\ ``(``\\ <Python引数>\\ ``,`` ... ``)``
        エフェクタを適用します。
        例: ``{CDE}|Transpose('M2')``
    """
    global parser
    if not parser:
        parser = ParserPython(score, ws="\t\n\r 　")  # 全角スペースを加えた
    try:
        parse_tree = parser.parse(text)
    except NoMatch as e:
        raise MMLError("Syntax error at position %d\n    %s ===> %s <==="
                       % (e.position, (text + '.')[:e.position],
                          (text + '.')[e.position:])) from None
    # outerglobals(), outerlocals()は mml関数を呼び出した元の環境を取得する。
    #  (これを行わないと、mmlモジュールの中の名前しかアクセスできない)
    if globals is None:
        globals = outerglobals()
    if locals is None:
        locals = outerlocals()
    evaluator = MMLEvaluator(dict(builtins.globals(), **outerglobals()),
                             outerlocals())
    effectors = context().effectors
    with newcontext(effectors=[]):
        try:
            s = evaluator.evalnode(parse_tree)
        except MMLError as e:
            if e.source is not None:
                raise e.source from None
            else:
                raise MMLError(str(e)) from None
        for eff in effectors:
            s = eff(s)
    return s


def _Context_mml(ctxt, *args, **kwargs) -> Score:
    with ctxt:
        return mml(*args, **kwargs)


if '__SPHINX_AUTODOC__' not in os.environ:
    Context.mml = _Context_mml


def mmlconfig(translate=("", ""), *,
              add_prefixes="",
              add_suffixes="",
              del_prefixes="",
              del_suffixes="",
              actions={},
              octave_number_suffix=None,
              accent_amount=None,
              timeshift_amount=None,
              staccato_amount=None) -> None:
    """
    MMLに関する設定を行います。引数無しで呼ぶと、現在の設定を表示します。

    この関数で変更できる設定は以下の4つです。

    * 文字クラスの変更
        各文字(unicode文字)は次のどれかのクラスに属しています。

        1. 予約済み
            次の文字は予約されていて、クラスを変更したり機能を変更することが
            できません。

            L n ( ) [ ] { } = $ | & / \\\\ : ; @ 数字 空白文字
        2. prefix文字
            前置修飾子となる文字です。
        3. suffix文字
            後置修飾子となる文字です。
        4. その他の文字
            基本コマンドとして使用できる文字です。

        予約済みの文字を除き、各文字のクラスを変更することができます。

    * 文字に割り当てられている機能の変更
        予約済みでない文字は、その意味を変更することができます。

    * "<整数>" 後置修飾子の意味の変更
        下の octave_number_suffix の項目を参照。

    * パラメータ変化量の変更
        下の accent_amount, timeshift_amount, staccato_amount の項目を参照。

    Args:
        translate((str, str), optional):
            長さの等しい2つの文字列からなるタプルを指定し、
            第1の文字列の各文字に対して、第2の文字列中の同位置にある文字の
            機能 (' ' なら空の機能) を割り当てます。文字を無効にしたいときには
            第2の文字列で未定義の文字を指定します。
        add_prefixes(str, optional):
            この引数に含まれている各文字のクラスを、"prefix文字" に変更します。
        add_suffixes(str, optional):
            この引数に含まれている各文字のクラスを、"suffix文字" に変更します。
        del_prefixes(str, optional):
            この引数に含まれている各文字のクラスを、"prefix文字" から
            "その他の文字" に変更します。
        del_suffixes(str, optional):
            この引数に含まれている各文字のクラスを、"suffix文字" から
            "その他の文字" に変更します。
        actions(dict, optional):
            キーが文字(1文字文字列)、値が関数(callable object)であるような
            dictオブジェクトを与えることで、各文字に対するアクション関数を
            指定します。アクション関数の記述法についてはソースコードの
            MMLActionクラスを参考にして下さい。
        octave_number_suffix(bool, optional):
            後置演算子としての <整数> の意味を指定します。
            True (default) ならばオクターブ番号を指定する意味、
            Falseなら音価を全音符のその整数分の1に設定する意味になります。
        accent_amount(int or float, optional):
            標準設定で :code:`\`` および ``?`` に割り当てられている機能に
            ついて、ベロシティの増減の大きさを指定します。(デフォルト値: 10)
        timeshift_amount(ticks, optional):
            標準設定で ``<`` および ``>`` に割り当てられている機能について、
            dtコンテキスト属性値の増減の大きさを指定します。(デフォルト値: 30)
        staccato_amount(float or int, optional):
            標準設定で ``!`` に割り当てられている機能について、
            drコンテキスト属性値に乗じる係数を指定します。(デフォルト値: 0.5)

    Examples:
        下の設定は ``b`` をフラットではなく ``B`` と同じ意味に変更します::

            mmlconfig(translate=('b', 'B'), del_suffixes='b')

        下の設定は、日本語仮名文字による音符、休符、および音価を伸ばす操作\
の記述を可能にします (このような表記はストトン表記として知られています)::

            mmlconfig(translate=("ドレミファソラシッどれみふぁそらしっー",
                      "CDEF GABrCDEF GABr~"),
                      add_suffixes="ァぁー")

        下の設定は、``^`` と ``_`` の文字を、以降のオクターブを上下する\
基本コマンドとして再定義します::

            mmlconfig(del_prefixes="^_",
                      actions={'^': MMLAction.cmd_octaveup,
                               '_': MMLAction.cmd_octavedown})

    """
    global parser
    if translate == ("", "") and not add_prefixes and not add_suffixes \
       and not del_prefixes and not del_suffixes and not actions \
       and octave_number_suffix is None and accent_amount is None \
       and timeshift_amount is None and staccato_amount is None:
        MMLConfig.show_config()
        return

    for ch in add_prefixes:
        check_reserved(ch)
        MMLConfig.prefixes += ch
        del_suffixes += ch
        parser = None
    for ch in add_suffixes:
        check_reserved(ch)
        MMLConfig.suffixes += ch
        del_prefixes += ch
        parser = None
    for ch in del_prefixes:
        MMLConfig.prefixes = MMLConfig.prefixes.replace(ch, '')
        parser = None
    for ch in del_suffixes:
        MMLConfig.suffixes = MMLConfig.suffixes.replace(ch, '')
        parser = None

    if len(translate[0]) != len(translate[1]):
        raise ValueError("legnth mismatch in translation strings")
    translate_dict = {}
    for cs, cd in zip(translate[0], translate[1]):
        check_reserved(cs)
        if cd != ' ':
            check_reserved(cd)
        translate_dict[cs] = (MMLConfig.char_actions[cd] if cd in
                              MMLConfig.char_actions else
                              MMLAction.cmd_undefined(cs))
    MMLConfig.char_actions.update(translate_dict)

    for ca in actions.keys():
        if len(ca) != 1:
            raise ValueError("`%s': Must be a single charactor" % (ca,))
        check_reserved(ca)
    MMLConfig.char_actions.update(actions)

    if octave_number_suffix is not None:
        MMLConfig.octave_number_suffix = octave_number_suffix
    if accent_amount is not None:
        MMLConfig.accent_amount = accent_amount
    if timeshift_amount is not None:
        MMLConfig.timeshift_amount = timeshift_amount
    if staccato_amount is not None:
        MMLConfig.staccato_amount = staccato_amount


# mmlconfig(translate=(u"どれみふぁそらしっんドレミファソラシッンー＃♯♭♮",
#                      "CDEF GABRRCDEF GABrr~##b%"),
#           add_suffixes=u"ァぁー＃♯♭♮")

# mmlconfig(del_suffixes="><",
#           actions={'>': MMLAction.cmd_octaveup,
#                    '<': MMLAction.cmd_octavedown},
#           octave_number_suffix=False)
