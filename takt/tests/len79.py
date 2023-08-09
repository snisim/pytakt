#!/usr/bin/python3
import sys
import unicodedata

if len(sys.argv) < 2:
    print("usage: len79 python-files")
    exit(1)

for filename in sys.argv[1:]:
    with open(filename, 'r') as f:
        for linenum, buf in enumerate(f.readlines()):
            L = 0
            for char in buf.rstrip():
                if unicodedata.east_asian_width(char) in ['F', 'W', 'A']:
                    L += 2
                else:
                    L += 1
            if L > 79:
                print(filename + ':' + str(linenum+1) + ':' + buf.rstrip())
