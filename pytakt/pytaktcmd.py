#!/usr/bin/python3

# Driver script for Pytakt
#  Copyright (C) 2025  Satoshi Nishimura

import argparse
import os
import sys
import re
import math
import pytakt as takt
from pytakt import *  # required by '-e' and '-a'


def StoreAndCheck(valid_modes, append=False, const=None):
    class StoreAndCheckClass(argparse.Action):
        def __call__(self, parser, namespace, values, option_string):
            if const is not None:
                values = const
            if append:
                items = getattr(namespace, self.dest)
                items = [] if items is None else items
                items.append(values)
                setattr(namespace, self.dest, items)
            else:
                setattr(namespace, self.dest, values)
            if not hasattr(namespace, 'mode_check_list'):
                namespace.mode_check_list = []
            namespace.mode_check_list.append((valid_modes, option_string))
    return StoreAndCheckClass


def error_exit(str_or_excp, option=None):
    if option is not None:
        print("Error occurred while evaluating the argument of %r option:" %
              option, file=sys.stderr)
    if isinstance(str_or_excp, Exception):
        print('%s: %s' % (str_or_excp.__class__.__name__, str_or_excp),
              file=sys.stderr)
    else:
        print(str_or_excp, file=sys.stderr)
    sys.exit(1)


def set_device(args):
    if args.device is not None:
        os.environ['PYTAKT_OUTPUT_DEVICE'] = args.device


def filter_tracks(args, score):
    if args.tracks is None:
        return score
    xs = []
    for s in args.tracks.split(','):
        try:
            x = [int(num) for num in s.split('-')]
            xs.append(x if len(x) == 1 else
                      range(x[0], x[1]+1) if len(x) == 2 else 0/0)
        except Exception:
            error_exit("Bad track-number spec '%s'" % args.tracks)
    for i in range(len(score)):
        if not any(i in x for x in xs):
            score[i] = takt.EventList()
    return score


# SMFを '-t' オプションでテキストに変換したときの可逆性について:
# 下のようにするとで、Raw モードを使用したときには原則バイナリレベルで
# 同じ SMF へ戻る。
#   $ pytakt -t -R sample.mid > sample.py
#   $ python sample.py write sample2.mid supply_tempo=False
#   $ cmp sample.mid sample2.mid
#   $
# ただし、次の場合には戻らないことがある。
#   1. 規格に準じていない SMF の場合 (system-exclusiveをまたがった running
#      status を使用している、あるいはend-of-trackイベントが無いなど)
#   2. 分解能の値が負である SMF の場合 (pytakt ではサポートしていない)
# Rawモードを使用しなかった場合は、同一時刻にあるノートオンとノートオフの
# 順序が入れ替わる可能性があるため、バイナリレベルでの可逆性は保証されなく
# なるが、演奏したときの違いはないはず。


def main():
    parser = argparse.ArgumentParser(
        description=f"""Driver script for Pytakt: a Music Information \
Processing Library with Realtime MIDI I/O
Version {takt.__version__}

INFILE/OUTFILE is either a standard MIDI file or a Pytakt JSON file.
When invoked with no arguments, it enters interactive mode.""",
        usage='%(prog)s [options] [INFILE]',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        prefix_chars='-+',
        epilog="""examples:
  pytakt -c7 -cPROG -cBEND a.mid
  pytakt -C -cTEMPO a.mid
  pytakt -d1 a.mid
  pytakt -p --device=SomeSoftSynth a.mid
  pytakt -t -T0,3-6 -r100 --start=16 a.mid
  pytakt -o b.mid --start +10000 a.mid
  pytakt -o b.mid -a 'ToTracks(True)' a.mid
  pytakt -p -m '{CDE}@@'""",
    )
    group1 = parser.add_mutually_exclusive_group()
    group1.add_argument('-s', '--summary', action='store_const',
                        dest='mode', const='s',
                        help="show a statistical summary of INFILE")
    group1.add_argument('-l', '--list-devices', action='store_const',
                        dest='mode', const='l',
                        help="show list of MIDI devices and exit")
    group1.add_argument('-t', '--text', action='store_const',
                        dest='mode', const='t',
                        help="translate INFILE to Python-evaluatable text")
    group1.add_argument('-g', '--view', action='store_const',
                        dest='mode', const='g',
                        help="show a piano-roll view of INFILE (default)")
    group1.add_argument('-p', '--play', action='store_const',
                        dest='mode', const='p',
                        help="play INFILE")
    group1.add_argument('-o', '--output', action='store', dest='outfile',
                        help="write output to OUTFILE")
    parser.add_argument('--version', action='version',
                        version='pytakt ' + takt.__version__)

    group2 = parser.add_argument_group("mode-specific options")
    group2.add_argument('-R', '--raw', action=StoreAndCheck('t'), nargs=0,
                        help='output individual events (raw mode) (-t)')
    group2.add_argument('--time', action=StoreAndCheck('t'),
                        default='measures',
                        choices=['measures', 'ticks', 'mbt', 'all', 'none'],
                        help="specify the format of the time column"
                        " (default: 'measures') (-t)")
    group2.add_argument('--encoding', action=StoreAndCheck('to'),
                        default='utf-8',
                        help="specify character enconding for text events in"
                        " MIDI files (default: 'utf-8') (-t/-o)")
    group2.add_argument('-r', '--resolution', action=StoreAndCheck('to'),
                        type=int, help="specify time resolution"
                        " in displayed text (-t) or output MIDI file (-o)")
    group2.add_argument('+v', '++velocity',
                        action=StoreAndCheck('g', const=True), nargs=0,
                        default='auto', help='show velocity pane (-g)')
    group2.add_argument('-v', '--velocity',
                        action=StoreAndCheck('g', const=False), nargs=0,
                        default='auto', help='hide velocity pane (-g)')
    group2.add_argument('-c', '--ctrl',
                        action=StoreAndCheck('g', append=True),
                        default=[], help="add controller pane (-g)")
    group2.add_argument('-C', '--allctrls', dest='ctrl', nargs=0, default=[],
                        action=StoreAndCheck('g', const=['auto']),
                        help="show all actively used controller(s) (-g)")
    group2.add_argument('+C', '++allctrls', dest='ctrl', nargs=0, default=[],
                        action=StoreAndCheck('g', const=['verbose']),
                        help="show all used controller(s) (-g)")
    group2.add_argument('-d', '--device', action=StoreAndCheck('gpli'),
                        help="select MIDI output device for playback"
                        " (-g/-p/iteractive)")
    group2.add_argument('-T', '--tracks', action=StoreAndCheck('stgpo'),
                        help="filter track(s) (-s/-t/-g/-p/-o)")
    group2.add_argument('--start', action=StoreAndCheck('stgpo'),
                        metavar="[BAR][:BEAT][+TICKS]",
                        help="remove the portion before the time"
                        " (-s/-t/-g/-p/-o)")
    group2.add_argument('--end', action=StoreAndCheck('stgpo'),
                        metavar="[BAR][:BEAT][+TICKS]",
                        help="remove the portion at and after the time"
                        " (-s/-t/-g/-p/-o)")
    group2.add_argument('--bar0len', action=StoreAndCheck('tg'),
                        type=int, help="specify length of Bar 0 (zero)"
                        " in ticks (-t/-g)")
    group2.add_argument('--magnify', action=StoreAndCheck('gi'), type=float,
                        help="specify window magnification (-g/iteractive)")
    group2.add_argument('--geometry', action=StoreAndCheck('gi'),
                        help="specify window geometry (-g/iteractive)")
    group2.add_argument('-a', '--apply', dest='effectors',
                        action=StoreAndCheck('stgpo', append=True),
                        help="apply an effector (-s/-t/-g/-p/-o)")
    group2.add_argument('-e', '--eval', dest='python_expr',
                        action=StoreAndCheck('stgpo'),
                        help="instead of INFILE, use PYTHON_EXPR to generate"
                        " a score (-s/-t/-g/-p/-o)")
    group2.add_argument('-m', '--mml', dest='mml_string',
                        action=StoreAndCheck('stgpo'),
                        help="evaluate the MML string (= --eval "
                        "'mml(\"MML_STRING\")') (-s/-t/-g/-p/-o)")
    group2.add_argument('--run', dest='pythonfile',
                        action=StoreAndCheck('stgpo'),
                        help="instead of INFILE, run a Python program"
                        " to generate a score (don't use for an unidentified"
                        " program) (-s/-t/-g/-p/-o)")

    parser.add_argument('INFILE', nargs='?', help=argparse.SUPPRESS)

    args = parser.parse_args()

    if args.outfile is not None:
        args.mode = 'o'

    cnt = (args.INFILE is not None) + (args.python_expr is not None) + \
          (args.mml_string is not None) + (args.pythonfile is not None)
    if cnt == 0:
        if args.mode is None:
            args.mode = 'i'  # interactive mode
        elif args.mode != 'l':
            error_exit("pytakt: error: one of INFILE, '-e' option, "
                       "'-m' option, or '--run' option is required")
    elif cnt > 1:
        error_exit("pytakt: error: '-e' option, '-m' option, '--run' option, "
                   "and INFILE are mutually exclusive")
    else:
        if args.mode is None:
            args.mode = 'g'

    if hasattr(args, 'mode_check_list'):
        for valid_modes, option_string in args.mode_check_list:
            if args.mode not in valid_modes:
                print("pytakt: warning: %r option has no effect" %
                      option_string, file=sys.stderr)

    if args.magnify is not None:
        os.environ['PYTAKT_MAGNIFY'] = str(args.magnify)
    if args.geometry is not None:
        os.environ['PYTAKT_GEOMETRY'] = args.geometry

    if args.mode == 'i':
        print("pytakt version", takt.__version__)
        set_device(args)
        cmd = 'from pytakt import *; from pytakt.midiio import *; '
        if sys.platform == 'win32':
            try:
                os.system(sys.executable + ' -i -c "' + cmd + '"')
            except KeyboardInterrupt:
                pass
            sys.exit(0)
        else:
            os.execl(sys.executable, sys.executable, '-i', '-c', cmd)
    elif args.mode == 'l':
        set_device(args)
        from pytakt.midiio import show_devices
        show_devices()
        sys.exit(0)

    # read INFILE, eval PYTHON_EXPR, or read PYTHONFILE
    if args.INFILE is not None:
        try:
            ext = takt.get_file_type(args.INFILE, ('smf', 'json'))
            if ext == 'smf':
                org_score = takt.readsmf(
                    args.INFILE, supply_tempo=False, encoding=args.encoding,
                    pair_note_events=args.mode != 't' or args.raw is None)
                takt.set_tempo(120.0)
            else:
                org_score = takt.readjson(args.INFILE)
                takt.set_tempo(125.0)
        except Exception as e:
            error_exit(e)
    elif args.pythonfile is not None:
        try:
            org_score = takt.evalpyfile(args.pythonfile, supply_tempo=False)
        except Exception as e:
            error_exit(e)
        takt.set_tempo(org_score.default_tempo)
    else:
        if args.python_expr is not None:
            try:
                org_score = eval(args.python_expr)
                if not isinstance(org_score, takt.Score):
                    raise TypeError("not a Score object")
            except Exception as e:
                error_exit(e, '-e/--eval')
        else:
            try:
                org_score = mml(args.mml_string)
            except Exception as e:
                error_exit(e, '-m/--mml')
        takt.set_tempo(125.0)

    # get format & resolution info
    if not hasattr(org_score, 'smf_format'):
        org_score.smf_format = 1
    if args.resolution is not None:
        if args.resolution <= 0:
            error_exit("Bad resolution value: %s" % args.resolution)
        resolution = {'resolution': args.resolution}
    elif args.mode == 'o' and hasattr(org_score, 'smf_resolution'):
        resolution = {'resolution': org_score.smf_resolution}
    else:
        resolution = {}

    # transform the score
    score = org_score
    if args.start is not None or args.end is not None:
        score = score.Clip(0 if args.start is None else args.start,
                           math.inf if args.end is None else args.end)
    score = filter_tracks(args, score)
    if args.effectors:
        for eff in args.effectors:
            try:
                score = eval("score.%s" % eff)
                if not isinstance(score, takt.Score):
                    raise TypeError("not a valid effector")
            except Exception as e:
                error_exit(e, '-a/--apply')

    # mode-specific actions
    if args.mode == 's':
        if args.INFILE is not None and hasattr(org_score, 'smf_format') and \
           hasattr(org_score, 'smf_resolution'):
            print("SMF format: %r   SMF resolution: %r   Number of tracks: %r"
                  % (org_score.smf_format, org_score.smf_resolution,
                     len(org_score)))
        takt.showsummary(score.Render(), takt.current_tempo())
    elif args.mode == 't':
        try:
            end_score_args = {}
            if hasattr(org_score, 'smf_resolution'):
                end_score_args['format'] = org_score.smf_format
                end_score_args['resolution'] = org_score.smf_resolution
            end_score_args['default_tempo'] = takt.current_tempo()
            score.writepyfile('-', rawmode=args.raw is not None,
                              time=args.time, bar0len=args.bar0len,
                              end_score_args=end_score_args, **resolution)
        except BrokenPipeError:
            # to avoid BrokenPipeError when using the 'head' command  in WSL
            sys.stdout = os.fdopen(0)
    elif args.mode == 'o':
        try:
            ext = takt.get_file_type(args.outfile, ('smf', 'json'), False)
        except Exception as e:
            error_exit(e)
        if ext == 'smf':
            score.writesmf(args.outfile, encoding=args.encoding,
                           supply_tempo=takt.current_tempo(),
                           format=org_score.smf_format, **resolution)
        else:
            score.writejson(args.outfile)
    elif args.mode == 'p':
        set_device(args)
        score.play()
    else:  # -g option
        set_device(args)
        for i, celm in enumerate(args.ctrl):
            if celm not in ('auto', 'verbose'):
                sign = 1
                if celm.startswith('-'):
                    sign = -1
                    celm = celm[1:]
                iv = None
                try:
                    iv = int(celm, 0)
                except ValueError:
                    pass
                if iv is None:
                    try:
                        iv = getattr(takt, 'C_' + celm.upper())
                    except AttributeError:
                        pass
                if iv is None:
                    raise Exception('%r: No such controller' % celm)
                if iv == 0 and sign == -1:
                    iv = 256
                args.ctrl[i] = sign * iv
        score.show(velocity=args.velocity, ctrlnums=args.ctrl,
                   bar0len=args.bar0len, **({} if args.INFILE is None
                                            else {'title': args.INFILE}))


if __name__ == '__main__':
    main()
