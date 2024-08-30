#
# Convert bilingually documented Python code to monolingual code
#

import argparse
import re
import sys


def error():
    raise Exception("Error: Unexpected end of file")


parser = argparse.ArgumentParser(description="Convert bilingually documented "
                                "Python code to monolingual code")

parser.add_argument('--lang', choices=['en', 'ja'], default='en')
parser.add_argument('PYFILE')
args = parser.parse_args()

inp = iter(open(args.PYFILE))

while True:
    try:
        line = next(inp)
    except StopIteration:
        break
    docs = []
    while re.match(r' *"""', line):
        doc = []
        first_line = True
        while True:
            doc.append(line)
            if (not first_line and re.search(r'(^|[^\\])""" *$', line)) or \
               (first_line and re.search(r'(^|[^\\])"""[^"]*""" *$', line)):
                break
            try:
                line = next(inp)
            except StopIteration:
                error()
            first_line = False
        try:
            line = next(inp)
        except StopIteration:
            error()
        docs.append(doc)

    if docs:
        lang = 1 if args.lang == 'ja' else 0
        if len(docs) != 2:
            print(f"{args.PYFILE}: Warning: The following doc string is not "
                  "bilingual:", file=sys.stderr)
            for s in docs[0]:
                print(s, end='', file=sys.stderr)
            lang = 0
        for s in docs[lang]:
            print(s, end='')
    print(line, end='')
