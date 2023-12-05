import pytest
from takt import *
import itertools
import random
import os

random.seed(0)
sample_score = readsmf(os.path.join(os.path.dirname(__file__), "grieg.mid"))

def test_tempomap():
    tm = TempoMap(sc.tempo([(0, 60), (480, 120, None)]))
    assert tm.ticks2sec(0) == 0 and tm.ticks2sec(240) == 0.5 and \
        tm.ticks2sec(480) == 1.0 and tm.ticks2sec(960) == 1.5
    tm = TempoMap(sc.tempo([(0, 60), (480, 120, None)]))
    assert tm.sec2ticks(0) == 0 and tm.sec2ticks(0.5) == 240 and \
        tm.sec2ticks(1.0) == 480 and tm.sec2ticks(1.5) == 960
    tm = TempoMap(rest(480) + sc.tempo(60) + note(C4) + sc.tempo(80) +
                  genseq(note(C4) for i in itertools.count()))
    assert tm.tempo_at(1) == 125 and tm.ticks2sec(1440) == 2.23 \
        and tm.sec2ticks(2.23) == 1440

    for j in range(100):
        tm = TempoMap(genseq(sc.tempo(random.random() * 1000 + 1,
                                      duration=random.random() * 1000)
                             for i in itertools.count()))
        for k in range(10):
            if (j+k) % 2 == 0:
                x = random.random() * 100000
                assert abs(tm.sec2ticks(tm.ticks2sec(x)) - x) < 1e-6
            else:
                x = random.random() * 100
                assert abs(tm.ticks2sec(tm.sec2ticks(x)) - x) < 1e-6

    tm = TempoMap(sample_score)
    total_seconds = tm.ticks2sec(sample_score.get_duration())
    assert round(total_seconds, 4) == 752.4923
    for k in range(100):
        if k % 2 == 0:
            x = random.random() * sample_score.get_duration()
        assert abs(tm.sec2ticks(tm.ticks2sec(x)) - x) < 1e-6
    else:
        x = random.random() * total_seconds
        assert abs(tm.ticks2sec(tm.sec2ticks(x)) - x) < 1e-6


def test_timesigmap():
    tm = TimeSignatureMap(sc.timesig(3, 4) + rest(1440) + sc.timesig(5, 8) +
                          rest(1920))
    assert tm.timesig_at(0).num_den() == (3, 4)
    assert tm.timesig_at(100).num_den() == (3, 4)
    assert tm.timesig_at(1440).num_den() == (5, 8)
    assert tm.timesig_at(1440 - 1e-10).num_den() == (3, 4)
    assert tm.timesig_at(2000).num_den() == (5, 8)
    assert tm.ticks2mbt(0) == (1, 0, 0, 0) and tm.mbt2ticks(1) == 0
    assert tm.ticks2mbt(100) == (1, 100, 0, 100) and \
        tm.mbt2ticks(1, 0, 100) == 100
    assert tm.ticks2mbt(500) == (1, 500, 1, 20) and \
        tm.mbt2ticks(1, 1, 20) == 500
    assert tm.ticks2mbt(1440) == (2, 0, 0, 0) and tm.mbt2ticks(2, 0, 0) == 1440
    assert tm.ticks2mbt(2000) == (2, 560, 2, 80) and \
        tm.mbt2ticks(2, 2, 80) == 2000
    assert tuple(round(x, 6) for x in tm.ticks2mbt(1440 - 1e-10)) \
        == (2, 0, 0, 0)
    assert tuple(round(x, 6) for x in tm.ticks2mbt(960 - 1e-10)) \
        == (1, 960, 2, 0)
    assert tm.num_measures() == 3
    tm = TimeSignatureMap(rest(3840 + 1e-10) + sc.timesig(4, 4))
    assert tm.num_measures() == 2 and tm.ticks2mbt(3850)[0] == 3
    tm = TimeSignatureMap(rest(3840 - 1e-10) + sc.timesig(4, 4))
    assert tm.num_measures() == 2 and tm.ticks2mbt(3850)[0] == 3
    tm = TimeSignatureMap(rest(100) + sc.timesig(2, 4))
    assert tm.mbt2ticks(3, 1, 100) == 100 + 960 + 960 + 480 + 100
    assert tm.ticks2mbt(100 + 960 + 960 + 480 + 100) == (3, 580, 1, 100)
    tm = TimeSignatureMap(rest(1000) + sc.timesig(2, 4), bar0len=1000)
    assert tm.ticks2mbt(980) == (0, 980, 2, 20)
    assert tm.ticks2mbt(1000) == (1, 0, 0, 0)
    assert tm.mbt2ticks(0) == 0 and tm.mbt2ticks(1) == 1000
    tm = TimeSignatureMap(rest(1000) + sc.timesig(2, 4), bar0len=960)
    assert tm.ticks2mbt(0) == (0, 0, 0, 0)
    assert tm.ticks2mbt(960) == (1, 0, 0, 0)
    assert tm.ticks2mbt(1020) == (2, 20, 0, 20)
    assert tm.mbt2ticks(1) == 960 and tm.mbt2ticks(2) == 1000
    tm = TimeSignatureMap(rest(1000) + sc.timesig(2, 4), bar0len=1020)
    assert tm.ticks2mbt(0) == (0, 0, 0, 0)
    assert tm.ticks2mbt(1000) == (0, 1000, 2, 40)
    assert tm.ticks2mbt(1020) == (1, 0, 0, 0)
    assert tm.mbt2ticks(1) == 1020 and tm.mbt2ticks(2) == 1980
    assert tm.timesig_at(1020).num_den() == (2, 4)
    tm = TimeSignatureMap(rest(1000) + sc.timesig(2, 4), bar0len=0)
    assert tm.ticks2mbt(0) == (1, 0, 0, 0)
    assert tm.ticks2mbt(1000) == (2, 0, 0, 0)
    assert tm.ticks2mbt(1020) == (2, 20, 0, 20)
    assert tm.mbt2ticks(2) == 1000 and tm.mbt2ticks(3) == 1960
    assert tm.timesig_at(1000).num_den() == (2, 4)

    for j in range(50):
        tm = TimeSignatureMap(
            genseq(sc.timesig(random.randrange(50) + 1,
                              1 << random.randrange(8),
                              duration=random.random() * 1000)
                   for i in itertools.count()))
        for k in range(10):
            if (j+k) % 2 == 0:
                x = random.random() * 100000
                mbt = tm.ticks2mbt(x)
                assert abs(tm.mbt2ticks(mbt[0], mbt[2], mbt[3]) - x) < 1e-6
            else:
                x = random.randrange(100)
                assert tm.ticks2mbt(tm.mbt2ticks(x))[0] == x

    tm = TimeSignatureMap(sample_score)
    num_measures = tm.num_measures()
    assert num_measures == 231
    for k in range(100):
        if k % 2 == 0:
            x = random.random() * sample_score.get_duration()
            mbt = tm.ticks2mbt(x)
            assert abs(tm.mbt2ticks(mbt[0], mbt[2], mbt[3]) - x) < 1e-6
        else:
            x = random.randrange(num_measures)
            assert tm.ticks2mbt(tm.mbt2ticks(x))[0] == x


def test_keysigmap():
    s = mml("$keysig('A-major')")
    km = KeySignatureMap(s)
    assert km.key_at(0) == Key(3) 
    assert km.key_at(0, 2) == Key(3) 
    s = mml("c $keysig('A-major') d $keysig('E-minor') e $keysig(5, tk=2)")
    km = KeySignatureMap(s)
    assert km.key_at(0) == Key(0) 
    assert km.key_at(480) == Key(3) 
    assert km.key_at(960) == Key(1, 1)
    assert km.key_at(1440) == Key(1, 1)
    assert km.key_at(0, 1) == Key(0) 
    assert km.key_at(480, 1) == Key(3) 
    assert km.key_at(960, 1) == Key(1, 1)
    assert km.key_at(1440, 1) == Key(1, 1)
    assert km.key_at(0, 2) == Key(0) 
    assert km.key_at(480, 2) == Key(0) 
    assert km.key_at(960, 2) == Key(0)
    assert km.key_at(1440, 2) == Key(5)
    assert km.key_at(0, 3) == Key(0) 
    assert km.key_at(480, 3) == Key(3) 
    assert km.key_at(960, 3) == Key(1, 1)
    assert km.key_at(1440, 3) == Key(1, 1)
