# coding:utf-8
"""
This module defines functions related to the customizable extended
MML (Music Macro Language).
"""
"""
このモジュールには、カスタマイズ可能な拡張 MML (Music Macro Language) に
関連した関数が定義されています。
"""
# Copyright (C) 2025  Satoshi Nishimura

import re
import os
import builtins
from arpeggio import ZeroOrMore, Optional, RegExMatch, EOF, \
                     NonTerminal, ParserPython, NoMatch, Sequence
from fractions import Fraction
from pytakt.score import Score, EventList
from pytakt.context import context, newcontext, Context
from pytakt.pitch import Pitch
from pytakt.constants import L1, L64
from pytakt.sc import note, rest
from pytakt.frameutils import outerglobals, outerlocals
from pytakt.utils import int_preferred, Ticks
import pytakt.sc
import pytakt.constants
import pytakt.pitch
import pytakt.gm
import pytakt.gm.drums
from typing import Optional as _Optional
from typing import Union, Mapping, Callable


__all__ = ['mml', 'safe_mml', 'mmlconfig', 'MMLAction', 'MMLError']


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
def cmdchar(): return RegExMatch('[^%s%s%s]((?<=[A-Z])bb*)?' %
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
                        ("(", ZeroOrMore(command), ")")]
# \x00はsuffixes/prefixesが空のときにエラーになるのを防ぐ
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
    suffixes: str = '\',#%*.+-!?`~><\\"'
    char_actions: Mapping[Char, Callable[[], _Optional[Score]]] = {
        '^': MMLAction.mod_octaveup,
        '_': MMLAction.mod_octavedown,
        "'": MMLAction.mod_octaveup,
        ',': MMLAction.mod_octavedown,
        '#': MMLAction.mod_sharp,
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
        'c': MMLAction.cmd_note('C'),
        'd': MMLAction.cmd_note('D'),
        'e': MMLAction.cmd_note('E'),
        'f': MMLAction.cmd_note('F'),
        'g': MMLAction.cmd_note('G'),
        'a': MMLAction.cmd_note('A'),
        'b': MMLAction.cmd_note('B'),
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
    def __init__(self, globals, locals, safe_mode):
        self.globals = globals
        self.locals = locals
        self.safe_mode = safe_mode

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
        context().L = getattr(pytakt.constants, node.value)

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
            if self.safe_mode:
                self.safety_error()
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
                action = MMLConfig.char_actions[node.value[0]]
            except KeyError:
                raise MMLError("Unknown command `%c' at position %d"
                               % (node.value, node.position))
            for flat_sign in node.value[1:]:
                if flat_sign == 'b':
                    MMLAction.mod_flat()
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
            from pytakt.effector import Repeat
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
            if self.safe_mode:
                self.safety_error()
            try:
                eff = eval(self.evalnode(node[1]), self.globals, self.locals)
            except Exception as e:
                raise MMLError('effector evaluation', e)
            context()._effectors.append(eff)
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
        return getattr(pytakt.constants, node.value)

    def eval_python_expression(self, node) -> Union[Score, int, float,
                                                    Ticks, None]:
        if self.safe_mode:
            self.safety_error()
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

    def safety_error(self) -> None:
        raise MMLError('Cannot use Python functions/expressions '
                       '("$..." and "|...") in the safe-mode MML')


parser = None


def mml(text, globals=None, locals=None, _safe_mode=False) -> Score:
    """
    Returns a score described in `text` with an extended MML (Music Macro
    Language).
    MML allows concise representation of musical phrases by strings.

    Args:
        text(str): MML string
        globals(dict, optional):
            Global dictionary for Python variable and function names
            contained in the MML string.
            By default, this is the value of globals() at the time when
            the mml() function is called.
        locals(dict, optional):
            Local dictionary for Python variable and function names
            contained in the MML string.
            By default, this is the value of locals() at the time when
            the mml() function is called.

    Examples:
        >>> mml('eefg gfed ccde e.d/d*').play()
        >>> mml('L8 G~rD G~rD GDGB ^D~rr ^C~rA ^C~rA ^CAF#A D~rr').play()
        >>> mml("L8 o=5 key=-3 $tempo(60) _B G~~~ F G F~~ E~  _B G~ \
{C Db C _B% C}/5 ^C~").play()
        >>> mml("L8 {dr=30 E(L16) E(L=L8+L16) E(v+=5) E(dr=50 dt=10)} G/`> \
G/!? G/ G/!? G3*").show(True)
        >>> mml('[ceg]@@').play()  # Press Ctrl-C to stop
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

    .. rubric:: Language Specification of This MML

    The entire score described in this MML consists of a sequence of
    **commands**. Each command contains one **primary command**, preceded by
    optional **premodifiers** and followed by optional **postmodifiers**.
    For example, ``CD#4^E`` consists of three commands, where ``C``, ``D``,
    and ``E`` are the primary commands, ``#`` and ``4`` are postmodifiers
    for ``D``, and ``^`` is a premodifier for ``E``.

    Whitespaces (spaces, tabs, and newlines) may be inserted freely except
    in the middle of identifiers, numbers, and multi-character operators or
    before `b` meaning a flat.
    From a semicolon (';') to the end of the line is considered as a comment
    and may be inserted freely between commands.

    .. rubric:: List of Primary Commands

    The primary commands available in the default configuration are as follows.

    ``A`` to ``G``, or ``a`` to ``g``
        Generates a note with the note name, using the :func:`.note` function.
        ``B`` represents an 11 semitones higher pitch than ``C``.
        Lowercase letters can also be used, and have the same meaning as
        uppercase letters. However, ``b`` means a flat when placed immediately
        after an uppercase letter (or a double-flat when placed twice).
        For example, the ``b`` in ``gab`` is a single B note, but the ``b`` in
        ``G Ab`` means a flat.
        The octave number is taken from the 'o' attribute of the context.
    ``r`` or ``R``
        A rest is inserted using the :func:`.rest` function.
    ``L``\\ <integer>, ``L``\\ <integer>\\ ``DOT``, \
``L``\\ <integer>\\ ``DOTDOT``
        Sets the note value (note length). <integer> can be 1, 2, 4, 8, 16,
        32, 64, or 128.
        Execution of this command will set the L attribute value in the context
        to the value of the constant of the same name defined in the
        :mod:`pytakt.constants` module. For example, ``L8`` makes
        subsequent notes and rests eighth-note length.
    <context attribute name> ``=`` <simple expression>
        Changes the value of a context attribute (e.g. ``v=100``).
        Only dt, tk, ch, v, nv, L, duoffset, du,durate, dr, o, and key are
        available as context attribute names. See below for simple expressions.
    <context attribute name> op\\ ``=`` <simple expression>
        Equivalent to <context attribute name> ``=`` <context attribute name>
        op <simple expression>, where op is one of the operators that can be
        used in simple expressions.
    ``{`` a sequence of zero or more commands ``}``
        Executes the commands in the braces using another context copied,
        and sequentially concatenates the results of scores.
        This can be used to temporarily change the context attribute values,
        e.g., in ``L4 C {L8 D E} F``, the D and E notes will be eighth notes,
        but the F note will return to a quarter note.
    ``[``A sequence of zero or more commands ``]``
        Executes the commands in the brackets using another context copied,
        and merges the results of scores to be played simultaneously.
        For example, it can be used to represent chords, as in ``[CEG]``,
        or multiple voices, as in ``[C* {FE}]``.
    ``$``\\ <Python variable name>\\ ``:{`` a sequence of zero or more \
commands ``}``
        <Python variable name> is a variable whose value is a context,
        The commands in the braces are executed using a copy of that context,
        and the results of scores are concatenated sequentially.
        <Python variable name> is a dot ('.') may contain.
    ``$(``\\ <Python expression>\\ ``)`` and \
``$``\\ <Python function name>\\ ``(``\\ <Python argument>\\ ``,`` ... ``)``
        Both evaluate the string following ``$`` as Python code and insert
        its value as a score (not inserted if it is None).
        The <Python function name> may contain dots ('.').
        Note that the names defined in the following modules can be used in
        the MML string without specifying the package or module name:
        pytakt.pitch, pytakt.sc, pytakt.constants, pytakt.gm.drums.

    .. rubric:: Simple Expressions

    <simple expression> is either an integer, a floating-point number,
    a note-value constant (such as L4), a context attribute name, a simple
    expression enclosed in parentheses, a Python expression enclosed in ``$(``
    and ``)``, a Python function call following ``$``, or an expression that
    combines these with the following operators: ``+``, ``-``, ``*``, ``/``,
    ``//``, and ``%``.

    .. rubric:: Premodifiers

    The following premodifiers are available in the default configuration.
    They can be used in commands other than note-value specification (e.g. L4)
    and assignment commands.
    Modification of context attribute values by modifiers is only valid for
    the command being qualified, and does not affect the execution of
    subsequent commands.

    ``^``
        Octave Up. Increases the value of the 'o' attribute of the context
        by 1.
    ``_``
        Octave down. Decrease the value of the 'o' attribute of the context
        by 1.

    .. rubric:: Postmodifiers

    The following postmodifiers are available by default.
    They can be used in commands other than note-value specification (e.g. L4)
    and assignment commands.
    Modification of context attribute values by modifiers is only valid for
    the command being qualified, and does not affect the execution of
    subsequent commands.

    <Integer>
        Specifies the octave by number (4 being the octave containing the
        middle C).
    ``+`` or ``#``
        A sharp. Raises the pitch by a semitone.
    ``-``
        A flat. Lowers the pitch by a semitone.
    ``%`` natural.
        Natural. Valid only if the value of the 'key' context attribute is
        non-zero. It changes the pitch to the one with no sharps or flats.
    ``'``
        Octave up. Equivalent to ``^``.
    ``,``
        Octave down. Equivalent to ``_``.
    ``*``
        Doubles the note value.
    ``/``
        Multiplies the note value by 0.5.
    ``/``\\ <integer>
        Divides the note value by <integer>. Can be used to represent tuplets.
    ``.``
        Represents a dot in music notation; one multiples the note value by
        a factor of 1.5, and two multiplies it by a factor of 1.75.
    ``~``
        Sums up multiple (possibly empty) note-value specifications.
        For example, ``*~/`` multiplies the note value by 2.5, ``~`` by 2,
        ``~~`` by 3, and ``~..`` means 2.75x.
    :code:`\\``
        Increases velocity by 10. Equivalent to ``(v+=10)``.
    ``?``
        Decreases velocity by 10. Equivalent to ``(v-=10)``.
    ``!``
        Multiplies the value of the 'dr' context attribute by 0.5,
        meaning a so-called staccato. Equivalent to ``(dr*=0.5)``.
    ``>``
        Increases the value of the 'dt' context attribute by 30 ticks
        (equivalent to 64th note), slightly delaying the timing in the
        performance. Equivalent to ``(dt+=30)``.
    ``<``
        Decreases the value of the dt context attribute by 30 ticks
        (equivalent to 64th notes), making the timing in the
        performance slightly earlier. Equivalent to ``(dt-=30)``.
    ``&``
        Sets the duration of the score to 0 to make the performance overlapped
        with subsequent performances.
    ``@``\\ <integer>
        Repeats the performance <integer> times. Equivalent to
        ``|Repeat(``\\ <integer>\\ ``)``.
    ``@@``
        Repeats the performance infinitely. Equivalent to ``|Repeat()``.
    ``(`` a sequence of zero or more commands ``)``.
        In the context created by the target primary command of this modifier,
        the commands in the sequence are executed before executing the
        primary command.
        Primarily used for the purpose of temporarily changing the context.
        Example: ``C(v=30 dt+=10)``
    ``|``\\ <Python identifier>\\ ``(``\\ <Python arguments>\\ ``,`` ... ``)``
        Apply effectors.
        Example: ``{CDE}|Transpose('M2')``
    """
    """
    引数 `text` の拡張 MML (Music Macro Language) 記述に従ったスコアを
    返します。MML は文字列によって音楽フレーズを簡潔に表現します。

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

    空白文字(スペース、タブ、改行)は、識別子、数値、2文字以上からなる
    演算子の途中、およびフラットを表す `b` の前を除き、自由に挿入できます。
    セミコロン (';') から行の終わりまではコメントとみなされ、コマンドと
    コマンドの間に自由に挿入できます。

    .. rubric:: 基本コマンド一覧

    デフォルト設定で使用可能な基本コマンドは以下の通りです。

    ``A`` ～ ``G`` または ``a`` ～ ``g``
        :func:`.note` 関数によって、指定された音名の音符を生成します。
        ``B`` は ``C`` の長七度上の音を表します。
        小文字も使用でき、大文字と意味は同じです。ただし、``b`` は
        英大文字の直後に置かれた場合はフラット (2個置かれた場合はダブル
        フラット) の意味になります (例えば、``gab`` の b は１つの音符ですが、
        ``G Ab`` の b はフラットの意味になります)。
        オクターブ番号はコンテキストのo属性から取得されます。
    ``r`` または ``R``
        :func:`.rest` 関数によって休符を生成します。
    ``L``\\ <整数>, ``L``\\ <整数>\\ ``DOT``, ``L``\\ <整数>\\ ``DOTDOT``
        音価を設定します。<整数>は 1, 2, 4, 8, 16, 32, 64, 128 のいずれかです。
        このコマンドの実行により、コンテキストのL属性の値が
        :mod:`pytakt.constants` モジュールに定義されている同名の定数の値に
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
        なお、次のモジュールで定義されている名前は、MML文字列の中では
        パッケージ名やモジュール名を指定せずに使えます: pytakt.pitch,
        pytakt.sc, pytakt.constants, pytakt.gm.drums。

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
    ``+`` または ``#``
        シャープ。ピッチを半音上げます。
    ``-``
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
    :code:`\\``
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
        修飾される基本コマンドが作成するコンテキストにおいて、
        その基本コマンドを実行する前に、列に含まれる各コマンドを実行します。
        主に、一時的にコンテキストを変更する目的に使われます。
        例: ``C(v=30 dt+=10)``
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
    evaluator = MMLEvaluator(dict(_module_globals, **globals), locals,
                             _safe_mode)
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


# _module_globalsは、MML内で $ に続けて直接利用できる名前の辞書
_module_globals = {'gm': pytakt.gm, 'mml': mml, 'context': context}
for module in (pytakt.sc, pytakt.pitch):
    for var in module.__all__:
        _module_globals[var] = getattr(module, var)
for module in (pytakt.constants, pytakt.gm.drums):
    for var in dir(module):
        if not var.startswith('_'):
            _module_globals[var] = getattr(module, var)


def _Context_mml(ctxt,
                 text, globals=None, locals=None, *args, **kwargs) -> Score:
    if globals is None:
        globals = outerglobals()
    if locals is None:
        locals = outerlocals()
    with ctxt:
        return mml(text, globals, locals, *args, **kwargs)


if '__SPHINX_AUTODOC__' not in os.environ:
    Context.mml = _Context_mml


def safe_mml(text) -> Score:
    """
    This is a security-aware version of :func:`mml`. It prohibits the use of
    Python expressions and Python functions (i.e., syntax beginning with
    ``$`` or ``|``) within MML.
    It is suitable for evaluating MML strings obtained from untrusted sources
    or interactively entered by users.

    Args:
        text(str): MML string
    """
    """
    セキュリティ面を考慮したバージョンの :func:`mml` です。MML中における
    Python式、Python関数（すなわち、``$`` および ``|`` で始まる構文）の使用を
    禁止しています。信頼できないソースから入手したMML文字列や対話的にユーザが
    入力したMML文字列を評価するのに適しています。

    Args:
        text(str): MML文字列
    """
    return mml(text, _safe_mode=True)


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
    Modifies the settings about the MML. When called without arguments,
    the current settings are displayed.

    The following settings can be changed with this function.

    * Change of the character class
        Each character (unicode character) belongs to one of the following
        classes:

        1. Reserved
            The following characters are reserved and their class and function
            cannot be changed.

            L n ( ) [ ] { } = $ | & / \\\\ : ; @ digits whitespace-characters
        2. Prefix character
            A character that serves as a premodifier.
        3. Suffix character
            A character that serves as a postmodifier.
        4. Other characters
            Characters that can be used as primary commands.

        Except for the reserved characters, the class of each character can
        be changed.

    * Change of the function assigned to a character
        Any character that is not reserved can change its meaning.

    * Change the meaning of the "<integer>" postmodifier
        See the octave_number_suffix entry below.
    * Change the amount of parameter change
        See the entries for accent_amount, timeshift_amount, and
        staccato_amount below.

    Args:
        translate((str, str), optional):
            Given a tuple of two strings of equal length, to each
            character in the first string, it assigns the function of the
            corresponding character in the second string (a "no operation"
            function if the character in the second string is ' ').
            To disable a character (i.e., to raise an exception when the
            character is used), specify some undefined character in the
            second string.
        add_prefixes(str, optional):
            Changes the class of each character in the argument to
            "prefix character".
        add_suffixes(str, optional):
            Changes the class of each character in the argument to
            "suffix character".
        del_prefixes(str, optional):
            Changes the class of each character in the argument
            from "prefix character" to "other character".
        del_suffixes(str, optional):
            Changes the class of each character in the argument
            from "suffix character" to "other character".
        actions(dict, optional):
            Specify an action function for each character by giving a dict
            object whose key is a character (single-string) and whose value
            is a function (callable object). Please refer to the MMLAction
            class in the "mml.py" source code for how to write action
            functions.
        octave_number_suffix(bool, optional):
            Specifies the meaning of the <integer> postmodifier.
            If True (default), it means the octave number.
            If False, it means to set the note value to
            that of the whole note divided by <integer>.
        accent_amount(int or float, optional):
            Sets the amount of velocity change in the velocity
            increment/decrement modifiers (:code:`\\`` and ``?``
            in standard configuration). (default value: 10)
        timeshift_amount(ticks, optional):
            Sets the amount of the change of the 'dt' context attribute value
            in the time-shift modifiers (``<`` and ``>``
            in standard configuration). (default value: 30)
        staccato_amount(float or int, optional):
            Sets the factor by which the 'dr' context attribute value is
            multiplied in the staccato modifier (``!`` in standard
            configuration). (default value: 0.5)

    Examples:
        The setting below allows the description of notes, rests, and
        note-stretching operations with Japanese katakana and hiragana
        characters (such notation is known as Sutoton notation)::

            mmlconfig(translate=("ドレミファソラシッどれみふぁそらしっー",
                      "CDEF GABrCDEF GABr~"),
                      add_suffixes="ァぁー")

        The configuration below redefines the ``^`` and ``_`` characters
        as primary commands of octave up and down for subsequent notes::

            mmlconfig(del_prefixes="^_",
                      actions={'^': MMLAction.cmd_octaveup,
                               '_': MMLAction.cmd_octavedown})

    """
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
            標準設定で :code:`\\`` および ``?`` に割り当てられている機能に
            ついて、ベロシティの増減の大きさを指定します。(デフォルト値: 10)
        timeshift_amount(ticks, optional):
            標準設定で ``<`` および ``>`` に割り当てられている機能について、
            dtコンテキスト属性値の増減の大きさを指定します。(デフォルト値: 30)
        staccato_amount(float or int, optional):
            標準設定で ``!`` に割り当てられている機能について、
            drコンテキスト属性値に乗じる係数を指定します。(デフォルト値: 0.5)

    Examples:
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
