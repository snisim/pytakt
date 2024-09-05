# coding:utf-8
import pytest
import math
from takt import *


@pytest.mark.parametrize("format,resolution,retrigger",
                         [(0, 480, False),
                          (1, 480, False),
                          (1, 100, False),
                          (1, 1200, True)])
def test_basic_smf(tmp_path, format, resolution, retrigger):
    tmpfile = tmp_path.joinpath('smftest.mid')
    score = sc.tempo(120) + note(C4) + note(Ds5, L8) + sc.vol(100) + \
            sc.prog(50) + sc.bend(-2000) + sc.cpr(25, ch=2) + \
            sc.kpr(E5, 70) + rest(L4) + note(C2, ch=3, tk=2) + rest(L4*3/5) + \
            note(C4) + rest(L4*1e6) + sc.meta(M_EOT, b'', tk=0)
    writesmf(score, str(tmpfile), format, resolution,
             retrigger_notes=retrigger, limit=math.inf)
    tracks = readsmf(str(tmpfile))
    tracks_unpaired = readsmf(str(tmpfile), pair_note_events=False)
    assert tracks.smf_format == format
    assert tracks.smf_resolution == resolution
    if format == 0:
        score = score.mapev(lambda ev: ev.update(tk=0))
        assert len(tracks) == 1
    else:
        score += sc.meta(M_EOT, b'', tk=1) + sc.meta(M_EOT, b'', tk=2)
        assert len(tracks) == 3
    assert EventList(score, limit=math.inf) == \
        EventList(tracks, limit=math.inf)
    score = score.UnpairNoteEvents()
    assert EventList(score, limit=math.inf) == \
        EventList(tracks_unpaired, limit=math.inf)


@pytest.mark.parametrize("ntrks", [None, 0, 1, 2, 3, 4])
def test_ntrks(tmp_path, ntrks):
    tmpfile = tmp_path.joinpath('smftest.mid')
    score = note(C4, tk=2)
    writesmf(score, str(tmpfile), ntrks=ntrks, supply_tempo=False)
    tracks = readsmf(str(tmpfile), supply_tempo=False)
    if ntrks is None:
        ntrks = 3
    assert len(tracks) == ntrks
    for i, trk in enumerate(tracks):
        assert trk.get_duration() == (L4 if i <= 2 else 0)
        assert len(trk) == (2 if i == 2 else 1)


@pytest.mark.parametrize("encoding", ['utf-8', 'sjis'])
def test_meta_sysex(tmp_path, encoding):
    tmpfile = tmp_path.joinpath('smftest.mid')
    with newcontext(tk=0):
        score = note(C4) + \
            sc.meta(M_SEQNO, b'\x01\x02') + \
            sc.meta(M_TEXT, 'texteventテキストイベント') + \
            sc.tempo(120) + sc.tempo(150) + sc.tempo(30) + sc.tempo(1000) + \
            sc.meta(M_SMPTE, b'\x01\x02\x03\x04\x05') + \
            sc.timesig(3, 4) + sc.timesig(5, 8) + \
            sc.keysig(0) + sc.keysig(3, 1) + sc.keysig(4, 0) + \
            note(C4) + \
            sc.sysex([0xf0, 0x01, 0x02, 0xf7]) + \
            sc.sysex([0xf3, 0x01, 0xf4], arbitrary=True) + \
            sc.meta(M_EOT, b'', tk=0)
    writesmf(score, str(tmpfile), encoding=encoding)
    s2 = readsmf(str(tmpfile), encoding=encoding)
    assert EventList(sc.tempo(125) + score) == EventList(s2)


def test_bad_midi_files(tmp_path):
    tmpfile = tmp_path.joinpath('smftest.mid')
    tmpfile.write_bytes(b'MThd\x00\x00\x00\x06\x00\x01\x00\x02\x01\xe0'
                        b'MTrk\x00\x00\x00\x05\x9e\x00\xff\x2f\x00MTr')
    with pytest.raises(SMFError, match=r".*Could not find header 'MTrk'.*"):
        readsmf(str(tmpfile))

    tmpfile.write_bytes(b'')
    with pytest.raises(SMFError, match=r".*Could not find header 'MThd'.*"):
        readsmf(str(tmpfile))

    tmpfile.write_bytes(b'\x01\x02\x03\x04')
    with pytest.warns(TaktWarning, match=r'.*garbage data.*'):
        with pytest.raises(SMFError,
                           match=r".*Could not find header 'MThd'.*"):
            readsmf(str(tmpfile))

    tmpfile.write_bytes(b'MThd\x00\x00\x00\x06\x00\x01')
    with pytest.raises(SMFError, match=r".*Bad file header.*"):
        readsmf(str(tmpfile))

    tmpfile.write_bytes(b'MThd')
    with pytest.raises(SMFError, match=r".*Bad file header.*"):
        readsmf(str(tmpfile))

    tmpfile.write_bytes(b'MThd\x00\x00\x00\x06\x00\x01\x00\x01\x01\xe0'
                        b'MTrk\x00\x00\x00\x05\x9e')
    with pytest.raises(SMFError, match=r".*No sufficient track data.*"):
        readsmf(str(tmpfile))

    tmpfile.write_bytes(b'MThd\x00\x00\x00\x06\x00\x01\x00\x01\x01\xe0'
                        b'MTrk\x00\x00\x00\x03\x9e\x00\xff')
    with pytest.raises(SMFError, match=r".*Unexpected EOF.*"):
        readsmf(str(tmpfile))

    tmpfile.write_bytes(b'MThd\x00\x00\x00\x06\x00\x01\x00\x01\x01\xe0'
                        b'MTrk\x00\x00\x00\x03\x9e\x00\x40')
    with pytest.raises(SMFError, match=r".*No MIDI running status.*"):
        readsmf(str(tmpfile))
