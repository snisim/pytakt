import pytest
from pytakt import *
import random
import os

random.seed(0)

def test_events_at():
    s = mml("$vol(70) $rpc(100, 77, nrpc=True, word=True) [c {e f}/]"
            "$vol(80) $rpc((0, 2), 88) e $ctrl(C_DATA, 77) g")
    for c in (False, True, True, False):
        assert s.active_events_at(0, cache=c) == \
            list(mml("$vol(70) $rpc(100, 77, nrpc=True, word=True) [c e/]"))
        assert s.active_events_at(1, cache=c) == \
            list(mml("$vol(70) $rpc(100, 77, nrpc=True, word=True) [c e/]"))
        assert s.active_events_at(240, cache=c) == \
            list(mml("$vol(70) $rpc(100, 77, nrpc=True, word=True) [c {rf}/]"))
        assert s.active_events_at(480, cache=c) == \
            list(mml("$rpc(100, 77, nrpc=True, word=True) r"
                     "$vol(80) $rpc((0, 2), 88) e"))
        assert s.active_events_at(960, cache=c) == \
            list(mml("$rpc(100, 77, nrpc=True, word=True) r"
                     "$vol(80) $rpc((0, 2), 77)|Reject('ctrlnum==C_DATA')"
                     "r $ctrl(C_DATA, 77) g"))
        assert s.active_events_at(240, NoteEvent, cache=c) == \
            list(mml("[c {rf}/]"))
        assert s.active_events_at(960, (NoteEvent, 7), cache=c) == \
            list(mml("r $vol(80) r g"))
        assert s.active_events_at(1440, NoteEvent, cache=c) == []

    for mid in ['menuet.mid', 'grieg.mid']:
        s = readsmf(os.path.join(os.path.dirname(__file__), mid))
        t = 0
        while t <= s.get_duration():
            assert s.active_events_at(t) == s.active_events_at(t, cache=False)
            t += random.randrange(10000)
