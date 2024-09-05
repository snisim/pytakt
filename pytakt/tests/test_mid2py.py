import pytest
import os
import io
import sys
from pytakt import *


SKIP_SLOW = os.getenv('TEST_ALL') is None


@pytest.mark.parametrize(
    "midfile", ['menuet.mid',
                'test1.mid',
                pytest.param('grieg.mid',
                             marks=pytest.mark.skipif(SKIP_SLOW,
                                                      reason='slow test'))])
@pytest.mark.parametrize(
    "options", ['', '--time=mbt -r100', '-r101', '-r99', '-r253', '-r1'])
def test_mid2py(tmp_path, midfile, options):
    __test_mid2py_raw(tmp_path, midfile, options)
    __test_mid2py_normal(tmp_path, midfile, options)
    if options == '':
        __test_mid2py_showtext(tmp_path, midfile, options)


def __test_mid2py_raw(tmp_path, midfile, options):
    midfile = os.path.join(os.path.dirname(__file__), midfile)
    pyfile = tmp_path.joinpath('tmp_mid2py.py')
    outmidfile = tmp_path.joinpath('tmp_mid2py.mid')
    os.system("rm -f %s" % str(pyfile))
    os.system("pytaktcmd.py -t -R %s %s > %s" %
              (options, midfile, str(pyfile)))
    assert pyfile.exists() and pyfile.stat().st_size > 0
    os.system("rm -f %s" % str(outmidfile))
    os.system("%s %s write %s limit=1e10 supply_tempo=False" %
              (sys.executable, str(pyfile), str(outmidfile)))
    with open(midfile, 'rb') as f:
        assert f.read() == outmidfile.read_bytes()


def __test_mid2py_normal(tmp_path, midfile, options):
    midfile = os.path.join(os.path.dirname(__file__), midfile)
    pyfile = tmp_path.joinpath('tmp_mid2py.py')
    outmidfile = tmp_path.joinpath('tmp_mid2py.mid')
    os.system("rm -f %s" % str(pyfile))
    os.system("pytaktcmd.py -t %s %s > %s" % (options, midfile, str(pyfile)))
    assert pyfile.exists() and pyfile.stat().st_size > 0
    os.system("rm -f %s" % str(outmidfile))
    os.system("%s %s write %s limit=1e10 supply_tempo=False" %
              (sys.executable, str(pyfile), str(outmidfile)))
    s1 = [repr(ev) for ev in readsmf(midfile).stream()]
    s2 = [repr(ev) for ev in readsmf(str(outmidfile)).stream()]
    s1.sort()
    s2.sort()
    assert s1 == s2


def __test_mid2py_showtext(tmp_path, midfile, options):
    midfile = os.path.join(os.path.dirname(__file__), midfile)
    sorg = readsmf(midfile, pair_note_events=False)
    with io.StringIO() as buf:
        sorg.showtext(rawmode=True, file=buf)
        s = eval(buf.getvalue())
        assert list(s) == list(sorg)
