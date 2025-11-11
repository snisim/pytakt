# coding:utf-8
"""
Simple and safe version of eval() designed for Python code embedded
in safe_mml().

safe_eval() below evaluates a Python expression with the following
restrictions:
 - Function calls are possible only when the '()' operators are directly
   applied to the names listed in a given dictionary ('namedict').
   (Thus, name[0]() fails even if 'name' is contained in the dictionary.)
 - The '.' operator cannot be used. (However, by including names with dots
   in 'namedict', you can simulate some of its behavior.
 - lambda expressions, starred expressions, comprehension, prefixed strings
   (such as r'abc'), and triple-quote strings are not available.
"""
# Copyright (C) 2025  Satoshi Nishimura

from arpeggio import ZeroOrMore, Optional, RegExMatch, EOF, \
                     NonTerminal, ParserPython, NoMatch, Not
from typing import List, Tuple, Set, Dict
import ast


__all__ = ['safe_eval']


# grammar begin
def top(): return expression, EOF
def expression(): return (conditional, )
def conditional(): return [(logical_or, "if", logical_or, "else", expression),
                           logical_or]
def logical_or(): return logical_and, ZeroOrMore("or", logical_and)
def logical_and(): return logical_not, ZeroOrMore("and", logical_not)
def logical_not(): return [(RegExMatch(r'not(?!\w)'), logical_not), comparison]
# 上の (?!\w) がないと、例えば not1 という名前が使えなくなってしまう。
def comparison(): return bitwise_or, ZeroOrMore([
        "==", "!=", "<=", "<", ">=", ">",
        RegExMatch(r"not[ \t]+in"), "in",
        RegExMatch(r"is[ \t]+not"), "is"], bitwise_or)
def bitwise_or(): return bitwise_xor, ZeroOrMore("|", bitwise_xor)
def bitwise_xor(): return bitwise_and, ZeroOrMore("^", bitwise_and)
def bitwise_and(): return shift_expr, ZeroOrMore("&", shift_expr)
def shift_expr(): return sum_, ZeroOrMore(["<<", ">>"], sum_)
def sum_(): return term, ZeroOrMore(["+", "-"], term)
def term(): return factor, ZeroOrMore(["*", "//", "/", "%"], factor)
def factor(): return [(["+", "-", "~"], factor), power]
def power(): return [(primary, "**", factor), primary]

def primary(): return atom, ZeroOrMore([("[", slices, "]"), (".", identifier)])
def slices(): return slice_, ZeroOrMore(",", slice_), Optional(",")
def slice_(): return [(Optional(expression), ":", Optional(expression),
                       Optional(":", Optional(expression))),
                      expression]
def atom(): return [floating, hexinteger, integer, funcall, identifiers,
                    tuple_, list_, set_, dict_, strings,
                    ("(", expression, ")")]
def identifier(): return RegExMatch(r'[^\d\W]\w*')
def identifiers(): return identifier, ZeroOrMore(".", identifier)
def funcall(): return (identifiers,
                       "(", Optional(arguments, Optional(",")), ")")
def arguments(): return [(positional_arguments,
                          Optional(",", keyword_arguments)),
                         keyword_arguments]
def positional_arguments(): return (expression, Not("="),
                                    ZeroOrMore(",", expression, Not("=")))
def keyword_arguments(): return keyword_item, ZeroOrMore(",", keyword_item)
def keyword_item(): return identifier, "=", expression

def integer(): return RegExMatch(r'\d+')
def hexinteger(): return RegExMatch(r'0[xX][\da-fA-F]+')
def floating(): return RegExMatch(r'\d+\.\d*|\d*\.\d+')
def tuple_(): return "(", Optional(expression, ",", Optional(expressions)), ")"
def list_(): return "[", Optional(expressions), "]"
def set_(): return "{", expressions, "}"
def expressions(): return (expression, ZeroOrMore(",", expression),
                           Optional(","))
def dict_(): return "{", Optional(kvpairs), "}"
def kvpairs(): return kvpair, ZeroOrMore(",", kvpair), Optional(",")
def kvpair(): return expression, ":", expression
def strings(): return string, ZeroOrMore(string)
def string(): return [RegExMatch(r'"([^"\n\\]|\\.)*"'),
                      RegExMatch(r"'([^'\n\\]|\\.)*'")]
# grammar end


class Evaluator(object):
    def __init__(self, namedict={}):
        namedict['True'] = True
        namedict['False'] = False
        namedict['None'] = None
        self.namedict = namedict

    def visit(self, node):
        method_name = "visit_" + node.rule_name
        if hasattr(self, method_name):
            return getattr(self, method_name)(node)
        else:
            if isinstance(node, NonTerminal):
                return self.visit(node[0])
            else:
                return node.value

    def visit_EOF(self, node) -> None:
        pass

    def visit_conditional(self, node):
        if len(node) == 1:
            return self.visit(node[0])
        else:
            return self.visit(node[0]) \
                if self.visit(node[2]) else self.visit(node[4])

    def visit_logical_or(self, node):
        result = self.visit(node[0])
        for i in range(1, len(node), 2):
            if result:
                break
            result = result or self.visit(node[i + 1])
        return result

    def visit_logical_and(self, node):
        result = self.visit(node[0])
        for i in range(1, len(node), 2):
            if not result:
                break
            result = result and self.visit(node[i + 1])
        return result

    def visit_logical_not(self, node):
        if len(node) == 1:
            return self.visit(node[0])
        else:
            return not self.visit(node[1])

    def visit_comparison(self, node):
        if len(node) == 1:
            return self.visit(node[0])
        result = True
        lastvalue = self.visit(node[0])
        for i in range(1, len(node), 2):
            value = self.visit(node[i + 1])
            if node[i].value == '==':
                result = result and lastvalue == value
            elif node[i].value == '!=':
                result = result and lastvalue != value
            elif node[i].value == '<=':
                result = result and lastvalue <= value
            elif node[i].value == '<':
                result = result and lastvalue < value
            elif node[i].value == '>=':
                result = result and lastvalue >= value
            elif node[i].value == '>':
                result = result and lastvalue > value
            elif node[i].value == '>':
                result = result and lastvalue > value
            elif node[i].value[:3] == 'not':
                result = result and lastvalue not in value
            elif node[i].value == 'in':
                result = result and lastvalue in value
            elif node[i].value[-3:] == 'not':
                result = result and lastvalue is not value
            elif node[i].value == 'is':
                result = result and lastvalue is value
            else:
                assert False
            lastvalue = value
        return result

    def visit_bitwise_or(self, node):
        result = self.visit(node[0])
        for i in range(1, len(node), 2):
            result |= self.visit(node[i + 1])
        return result

    def visit_bitwise_xor(self, node):
        result = self.visit(node[0])
        for i in range(1, len(node), 2):
            result ^= self.visit(node[i + 1])
        return result

    def visit_bitwise_and(self, node):
        result = self.visit(node[0])
        for i in range(1, len(node), 2):
            result &= self.visit(node[i + 1])
        return result

    def visit_shift_expr(self, node):
        result = self.visit(node[0])
        for i in range(1, len(node), 2):
            if node[i].value == '<<':
                result <<= self.visit(node[i + 1])
            elif node[i].value == '>>':
                result >>= self.visit(node[i + 1])
            else:
                assert False
        return result

    def visit_sum_(self, node):
        result = self.visit(node[0])
        for i in range(1, len(node), 2):
            if node[i].value == '+':
                result += self.visit(node[i + 1])
            elif node[i].value == '-':
                result -= self.visit(node[i + 1])
            else:
                assert False
        return result

    def visit_term(self, node):
        result = self.visit(node[0])
        for i in range(1, len(node), 2):
            if node[i].value == '*':
                result *= self.visit(node[i + 1])
            elif node[i].value == '/':
                result /= self.visit(node[i + 1])
            elif node[i].value == '//':
                result //= self.visit(node[i + 1])
            elif node[i].value == '%':
                result %= self.visit(node[i + 1])
            else:
                assert False
        return result

    def visit_factor(self, node):
        if len(node) == 1:
            return self.visit(node[0])
        elif node[0].value == '+':
            return self.visit(node[1])
        elif node[0].value == '-':
            return -self.visit(node[1])
        elif node[0].value == '~':
            return ~self.visit(node[1])
        assert False

    def visit_power(self, node):
        if len(node) == 3:
            return self.visit(node[0]) ** self.visit(node[2])
        else:
            return self.visit(node[0])

    def visit_primary(self, node):
        result = self.visit(node[0])
        for i in range(2, len(node), 3):
            if node[i-1].value == '.':
                raise SyntaxError("The '.' operator cannot be used")
            result = result[self.visit(node[i])]
        return result

    def visit_slices(self, node):
        if len(node) == 1:
            return self.visit(node[0])
        return tuple(self.visit(node[i]) for i in range(0, len(node), 2))

    def visit_slice_(self, node):
        slice_args = [None]
        for n in node:
            if n.value != ':':
                slice_args[-1] = self.visit(n)
            else:
                slice_args.append(None)
        return slice_args[0] if len(slice_args) == 1 else slice(*slice_args)

    def visit_atom(self, node):
        return self.visit(node[0]) if len(node) == 1 \
            else self.visit(node[1])

    def visit_identifier(self, node):
        return node.value

    def visit_identifiers(self, node):
        ids = ''.join(self.visit(n) for n in node)
        try:
            return self.namedict[ids]
        except KeyError:
            raise NameError("name '" + ids + "' is not defined")

    def visit_funcall(self, node):
        func = self.visit(node[0])
        if len(node) >= 4:
            args, kwargs = self.visit(node[2])
        else:
            args, kwargs = [], {}
        return func(*args, **kwargs)

    def visit_arguments(self, node) -> Tuple[Tuple, Dict]:
        args = self.visit(node[0])
        if len(node) == 1:
            if isinstance(args, Tuple):
                return (args, {})
            else:
                return ((), args)
        else:
            return (args, self.visit(node[2]))

    def visit_positional_arguments(self, node) -> Tuple:
        return tuple(self.visit(node[i]) for i in range(0, len(node), 2))

    def visit_keyword_arguments(self, node) -> Dict:
        return dict(self.visit(node[i]) for i in range(0, len(node), 2))

    def visit_keyword_item(self, node) -> Tuple:
        return (self.visit(node[0]), self.visit(node[2]))

    def visit_integer(self, node) -> int:
        return ast.literal_eval(node.value)

    def visit_hexinteger(self, node) -> int:
        return ast.literal_eval(node.value)

    def visit_floating(self, node) -> float:
        return ast.literal_eval(node.value)

    def visit_tuple_(self, node) -> Tuple:
        if len(node) == 2:
            return ()
        elif len(node) == 4:
            return (self.visit(node[1]),)
        else:
            return tuple([self.visit(node[1])] + self.visit(node[3]))

    def visit_list_(self, node) -> List:
        if len(node) == 2:
            return []
        else:
            return self.visit(node[1])

    def visit_expressions(self, node) -> List:
        return [self.visit(node[i]) for i in range(0, len(node), 2)]

    def visit_set_(self, node) -> Set:
        return set(self.visit(node[1]))

    def visit_dict_(self, node) -> Dict:
        if len(node) == 2:
            return {}
        else:
            return dict(self.visit(node[1]))

    def visit_kvpairs(self, node) -> List[Tuple]:
        return [self.visit(node[i]) for i in range(0, len(node), 2)]

    def visit_kvpair(self, node) -> Tuple:
        return (self.visit(node[0]), self.visit(node[2]))

    def visit_strings(self, node) -> str:
        return ''.join(self.visit(n) for n in node)

    def visit_string(self, node) -> str:
        return ast.literal_eval(node.value)


parser = ParserPython(top, ws="\t\n\r ")


def safe_eval(text, namedict={}):
    try:
        parse_tree = parser.parse(text)
    except NoMatch as e:
        raise SyntaxError("Syntax error within Python expression: "
                          "%s ==> %s <==" %
                          ((text+'.')[:e.position], (text+'.')[e.position:]))
    try:
        return Evaluator(namedict).visit(parse_tree)
    except Exception as e:
        raise e.__class__(str(e))


if __name__ == '__main__':
    while True:
        try:
            text = input("> ")
        except EOFError:
            break

        print("Input:", repr(text))
        try:
            value = safe_eval(text, {'print': print})
        except Exception as e:
            print(f"{e.__class__.__name__}: {e}")
        else:
            print("Parsing result:", parser.parse(text))
            print("Value:", value)
