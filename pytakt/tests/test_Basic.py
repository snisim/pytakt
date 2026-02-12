import pytest
from pytakt import *
import itertools
import random
import math
import os

random.seed(0)
sample_score = readsmf(os.path.join(os.path.dirname(__file__), "grieg.mid"))

def test_pitch():
    for count in range(100):
        n = random.randrange(21, 109)
        k = random.randrange(-7, 8)
        assert(Pitch(repr(Pitch(n, key=k))) == n)
        assert(eval(repr(Pitch(n, key=k))) == n)
        sf = random.randrange(-2, 3)
        p1 = eval(repr(Pitch(n, sf)))
        assert(p1 == n and p1.sf == sf)
        d = random.randrange(-100, 100)
        assert(Pitch(n) + d == n + d)
        n2 = random.randrange(21, 109)
        assert(int(n - n2) == int(n) - int(n2))
        p2 = Pitch(n, key=k) - Pitch(n2, key=k) + Pitch(n2, key=k)
        assert(p2 == n and p2.sf == Pitch(n, key=k).sf)


def test_mml():
    assert mml("CCrD") == note(C4) + note(C4) + rest() + note(D4)
    with newcontext(ch=2):
        assert mml("EF(ch=3)(v=90)") == note(E4, ch=2) + note(F4, ch=3, v=90)
    assert mml("C^C^^CC'_C__CC,C7") == \
        note(C4) + note(C5) + note(C6) + note(C5) + note(C3) \
        + note(C2) + note(C3) + note(C7)
    with newcontext(L=L8):
        assert mml("CL16DE(L2DOT)") == \
            note(C4, L8) + note(D4, L16) + note(E4, L2DOT)
    assert mml("[{v+=(10*(1+2)) CD} E*]") == \
        (note(C4, v=110) + note(D4, v=110)) & note(E4, L2)
    x = note(C4)
    def f():
        return note(C4)
    assert mml("E$f()(v=90)[F$(x)]") == \
        note(E4) + note(C4,v=90) + (note(F4) & note(C4))
    assert mml("C$vol(80)E") == note(C4) + sc.vol(80) + note(E4)
    assert mml("key=3 CC##C#CbC%") == \
           note(Cs4) + note(Css4) + note(Cs4) + note(Cb4) + note(C4)
    assert mml("{C*/5C/C..}/") == \
        note(C4, L4/5) + note(C4, L16) + note(C4, L8DOTDOT)
    assert mml("C*~/ C~ C~~ C~..") == \
        note(C4, L2+L8) + note(C4, L2) + note(C4, L4*3) + note(C4, L4+L4DOTDOT)
    assert mml("{C~}~") == note(C4, L1)
    assert mml("C`??!<<>") == note(C4, v=70, dr=50, dt=-L64)
    assert mml("{C(v+=10)}(v=90)") == note(C4, v=100)
    assert mml("C($bend(100))") == sc.bend(100) & note(C4)
    assert mml("C@2") == note(C4) + note(C4)
    ctx = newcontext(v=90)
    assert mml("{C $ctx:{D}}") == note(C4) + ctx.note(D4)
    assert mml("{C|Transpose(2)G}|Transpose(2)") == mml("EA")
    assert mml("C|Modify('v+=10')") == note(C4, v=90)
    def f(x, y):
        return y + x
    assert safe_mml("$prog(gm.Piano1) cd/|Transpose(DEG(2), scale=Scale(C4))")\
        == mml("$prog(gm.Piano1) cd/|Transpose(DEG(2), scale=Scale(C4))")
    try:
        safe_mml("$(x)")
    except NameError:
        pass
    else:
        assert False
    try:
        safe_mml("$open('file')")
    except NameError:
        pass
    else:
        assert False
    try:
        safe_mml("$eval('note(C4)')")
    except NameError:
        pass
    else:
        assert False
    assert mml("$note(C4, v=v+10)") == safe_mml("$note(C4, v=v+10)") == \
        mml("$note(C4, v=90)")
    assert mml("$note(C4, ch=ch+1)") == mml("C4(ch=2)")
    assert mml("$zz=$(C4) $vv=50+10 $note(zz, v=vv)") == mml("c(v=60)")
    assert safe_mml("$zz=$(C4) $vv=50+10 $note(zz, v=vv)") == mml("c(v=60)")
    try:
        x = zz
    except NameError:
        pass
    else:
        assert False
    assert safe_mml("$f(x)=$vol(x+10)+$expr(x) $f(50)") == \
        mml("$vol(60) $expr(50)")
    assert safe_mml("$f(x, y=2) = $(vol(x+10*y)+expr(x)*y) $f(50)") == \
        mml("$vol(70) $expr(50) $expr(50)")
    assert safe_mml("$f(x, y=2) = $mml('$vol(x) $mod(y)') $f(50, 4)") == \
        mml("$f(x, y=2) = $mml('$vol(x) $mod(y)') $f(50, 4)") == \
        mml("$vol(50) $mod(4)")
    assert safe_mml("$f(x=L4) = ${L=$(x) cde} $f() $f(L8) f") == \
        mml("$f(x=L4) = ${L=$(x) cde} $f() $f(L8) f") == mml("cde L8 cde L4 f")
    assert safe_mml("$T() = $Transpose('M2') {cd}|T()") == \
        mml("$T() = $Transpose('M2') {cd}|T()") == mml("de")
    assert safe_mml("$Trill() = $Product('{L16 cd}@@') g|Trill()") == \
        mml("$Trill() = $Product('{L16 cd}@@') g|Trill()") == mml("L16 gaga")
    try:
        safe_mml("""$mml("v=$eval('0')")""")
    except NameError:
        pass
    else:
        assert False
    assert mml("$if(True){c}$else{d}") == mml("c")
    assert mml("$if(False){c}$else{d}") == mml("d")
    assert mml("$if(False){c}$elif(True){d}$else{e}") == mml("d")
    assert mml("$if(False){c}$elif(False){d}$else{e}") == mml("e")
    text = "$for(i in [1, 2, 3]) {$if(i == 2) {c} d}"
    assert mml(text) == safe_mml(text) == mml("dcdd")
    text = "v=80 $for(i in range(2)) {c d v+=10} e"
    assert mml(text) == safe_mml(text) == mml("v=80 cd v=90 cd v=100 e")


def test_effectors():
    assert mml("C D E").Transpose(Interval('M3')) == mml("E F# G#")
    assert mml("C D E").Transpose('M3') == mml("E F# G#")
    assert mml("C D E").Transpose(E4-C4) == mml("E F# G#")
    assert mml("C D E").Transpose(DEG(3), scale=Scale(C4)) == mml("E F G")
    assert mml("$keysig('B-minor') C D E").Transpose(Interval('m2')) \
        == mml("$keysig('C-minor') Db Eb F")
    assert mml("E F G").Invert(E4) == mml("E D# C#")
    assert mml("E F G").Invert(E4, scale=Scale(C4)) == mml("E D C")
    assert mml("CC#DbDE").ApplyScale(Scale(C4, 'minor')) == mml("CCDDEb")
    assert mml("C C# D E").ConvertScale(Scale(C4, 'major'),
                                        Scale(C4, 'minor')) == mml("C C# D Eb")
    assert note(C4, v=80).ScaleVelocity(1.2) == note(C4, v=96)
    assert mml("v=80 CDEF").ScaleVelocity([1.0, (L1, 0.5)]) \
        == mml("C(v=80) D(v=70) E(v=60) F(v=50)")
    assert mml("CDE*").TimeStretch(2) == mml("C*D*E**")
    assert sorted(mml("CDE*").Retrograde(), key=lambda x: x.n) \
        == sorted(EventList(mml("E*DC")), key=lambda x: x.n)
    assert note(C4, 450).Quantize(120) == note(C4, 480)
    assert note(C4, 450).Quantize(120, strength=0.5) == note(C4, 465)
    assert note(C4, 450).Quantize(120, window=0.4) == note(C4, 450)
    assert note(C4, 450).Quantize(120, window=0.6) == note(C4, 480)
    assert mml("C/D/E*.F").TimeDeform([(0, 0), (480, 482), (1920, 1950)]) \
        == mml("C(L=241) D(L=241) E(L=1468) F(L=0)")
    assert mml("{CDEF}/").TimeDeform([0, (240, 360), (480, 480)],
                                     periodic=True) \
        == mml("{C.D/E.F/}/")
    assert mml("CDEF").Swing(L2, 0.75, False) == mml("C.D/E.F/")
    assert mml("$tempo(120) C $tempo(240) D(dt=-60)").ToMilliseconds() \
        == mml("L=500 C L=250 D(dt=-62.5 du=281.25)")

    s = mml("$tempo(150) $keysig(1) $prog(49) C $vol(80) D(ch=5 v=30)")
    assert s.Filter(NoteEvent, TempoEvent) == mml("$tempo(150) C D(ch=5 v=30)")
    assert s.Filter('ctrlnum == 7') == mml("R $vol(80) R")
    assert s.Filter(lambda ev: hasattr(ev, 'ctrlnum') and ev.ctrlnum == 7) \
        == mml("R $vol(80) R")
    assert s.Filter('ctrlnum == C_PROG', negate=True) \
        == mml("$tempo(150) $keysig(1) C $vol(80) D(ch=5 v=30)")
    assert s.Filter('v >= 50') == mml("C R")
    assert s.Filter('ch in (1,2,4)', TempoEvent, MetaEvent) \
        == mml("$tempo(150) $keysig(1) $prog(49) C $vol(80) R")
    assert s.Filter('n > C4') == mml("rD(ch=5 v=30)")
    assert mml("CD/").Filter('L >= L4') == mml("Cr/")
    assert mml("C4 C5 C6 $kpr(C6, 100)").Cond('n >= C5', ScaleVelocity(1.2)) \
        == mml("C4 C5(v=96) C6(v=96) $kpr(C6, 100)")
    assert mml("$tempo(150) C $prog(4)").Modify('ch=3') \
        == mml("ch=3 $tempo(150) C $prog(4)")
    assert mml("$vol(7)CDE").Modify('v*=0.8; nv=30') \
        == mml("v=64 nv=30 $vol(7)CDE")
    assert mml("$vol(7)CDE").Modify('v*=0.8; nv=30').UnpairNoteEvents() \
        == mml("v=64 nv=30 $vol(7)CDE").UnpairNoteEvents()
    assert mml("$vol(7)C tk=2 DE").Modify('if tk==2: v*=1.1') \
        == mml("$vol(7)C tk=2 v=88 DE")
    assert mml("$vol(7)CDE").Modify('ev.voice=2') \
        == mml("$vol(7)CDE").mapev(lambda ev: ev.update(voice=2))
    assert mml("CD dr=80 E").Modify('L=240') \
        == mml("CD dr=80 E").mapev(lambda ev: ev.update(L=240))
    assert mml("CD dr=80 E").Modify('du*=0.5') \
        == mml("dr=50 CD dr=40 E")
    assert mml("$prog(49) CDEF").Clip(480, 1440) == mml("$prog(49) DE")
    assert mml("CDEF").Clip(240, 1200) == mml("C/DE/")
    assert mml("CDEF").Clip(240, 1200, split_notes=False) == \
        EventList(mml("r/DE"), 960)
    assert mml("C(du=250)DE(du=300)F").Clip(240, 1200) == \
        mml("C/(du=10)D") + EventList([NoteEvent(0, E4, 240, du=240)], 240)
    assert mml("CDEF").Clip(490, 500) == mml("D(L=10)")
    assert mml("$vol(50)C$vol(60)DEF").Clip(960, 1440) == mml("$vol(60)E")
    assert mml("[C{E(dr=75)F(dt=10)}/G]").UnpairNoteEvents().PairNoteEvents() \
        == EventList(mml("[C{E(dr=75)F(dt=10)}/G]"))
    assert mml("[{rE}C*]").Clip(0, 480) == mml("C")
    assert s.UnpairNoteEvents().PairNoteEvents() == s
    with pytest.warns(TaktWarning):
        assert mml("CE").UnpairNoteEvents().Filter(NoteOnEvent). \
            PairNoteEvents() == mml("[C* {rE}]")
    s2 = s.UnpairNoteEvents(True)
    assert s2[3].noteev is s[3]
    assert s2[4].noteev is s[3]
    assert s2.PairNoteEvents(True)[3].noteonev is s2[3]
    assert s2.PairNoteEvents(True)[3].noteoffev is s2[4]


def test_tie():
    assert mml("C|Tie() C/|EndTie()|Tie() C/|EndTie()").ConnectTies() == \
        mml("C*")
    assert mml("dr=50 C|Tie() C/|EndTie()|Tie() C/|EndTie()").ConnectTies() \
        == mml("C*(du=480+240+120)")
    assert mml("[C [EG]|Tie()] [C|Tie() [EG]|EndTie()] "
               "[C|EndTie() EG]").ConnectTies().sorted() == \
        mml("[{C C*} {[EG]* [EG]}]").sorted()


def test_retrigger():
    assert mml("[CC]").RetriggerNotes() == mml("C(L=0)C")
    assert mml("[CC]").UnpairNoteEvents().RetriggerNotes() == \
        mml("C(L=0)C").UnpairNoteEvents()
    assert mml("[C(nv=80)**{rC}]").RetriggerNotes() == mml("CC(nv=80)*.")
    assert mml("[C(nv=80)**{rC}]").UnpairNoteEvents().RetriggerNotes() == \
        mml("CC(nv=80)*.").UnpairNoteEvents()
    assert mml("[C*{RC(nv=80)*.}]").RetriggerNotes() == mml("CC(nv=80)*.")
    assert mml("[C*{RC(nv=80)*.}]").UnpairNoteEvents().RetriggerNotes() == \
        mml("CC(nv=80)*.").UnpairNoteEvents()
    assert mml("[CC|UnpairNoteEvents()]").RetriggerNotes() == \
        mml("[C(L=0)C|UnpairNoteEvents()]")
    assert mml("[C(nv=80)**{rC}|UnpairNoteEvents()]").RetriggerNotes() == \
        mml("CC(nv=80)*.|UnpairNoteEvents()")
    assert mml("[C(nv=80)|UnpairNoteEvents()**{rC}]").RetriggerNotes() == \
        mml("C|UnpairNoteEvents()C(nv=80)*.")
    assert mml("[C*{RC(nv=80)*.}|UnpairNoteEvents()]").RetriggerNotes() == \
        mml("CC(nv=80)*.|UnpairNoteEvents()")
    assert mml("[C*|UnpairNoteEvents(){RC(nv=80)*.}]").RetriggerNotes() == \
        mml("C|UnpairNoteEvents()C(nv=80)*.")
    assert mml("[C*.[{rC*.}{rrrC*(nv=10)}]|UnpairNoteEvents(){rrC*.}]")\
        .RetriggerNotes() == \
        mml("CC|UnpairNoteEvents()CC*(nv=10)|UnpairNoteEvents()")


def test_product():
    assert EventList(mml("C[EG]").Product("[C^C]")) == \
        EventList(mml("[C^C][[E^E][G^G]]"))
    assert EventList(mml("C[EG]").Product(lambda: note(C4) & note(C5))) == \
        EventList(mml("[C^C][[E^E][G^G]]"))
    assert EventList(mml("CD(v=90)").Product("[[v-=10 CE]G]")) == \
        EventList(mml("[[v=70CE]v=80G] [[v=80DF#]v=90A]"))
    assert EventList(mml("CE*G/").Product("{CDEF}//", scale=Scale(C4))) == \
        EventList(mml("{CDEF}//{EFGA}/{GAB^C}///"))
    assert EventList(mml("CE*G/").Product("L16{CDEF}", scale=Scale(C4))) == \
        EventList(mml("{CDEF}//{EFGARRRR}//{GA}//"))
    assert EventList(mml("CE*G/").Product("L32 C@@")) == \
        EventList(mml("L32CCCCCCCCEEEEEEEEEEEEEEEEGGGG"))
    assert EventList(mml("CG/").Product("L32 {CD}@@",
                                        tail="L=L8/5 CDC_BC")) == \
        EventList(mml("L32CDCD{L=L8/5CDC_BC}{L=L8/5GAGF#G}"))
    assert EventList(mml("CG").Product("L8 {CDEF}&")) == \
        EventList(mml("[{CDEF}/{rrGAB^C}/&]"))
    assert EventList(mml("CAb*").Product("G(L32)F",
                                         scale=Scale(F4, 'minor'))) == \
        EventList(mml("Db(L32)C(L=L4-L32)Bb(L32)Ab(L=L2-L32)"))
#     assert sorted(EventList(mml("[C{FE}/]").product(
#         lambda i, m: mml("L32rC" if i else "L32Cr").Repeat(), chord=True)),
#                   key=lambda ev: str(type(ev))) == \
#         sorted(EventList(mml("L32CFCFCECE")), key=lambda ev: str(type(ev)))
    assert mml('c').Product(lambda: mml('e').UnpairNoteEvents()) == mml('e')
    assert mml('c').UnpairNoteEvents().Product('c*@@') == \
        mml('c').UnpairNoteEvents()

def test_apply():
    assert mml("CDEF`").Apply("{C!C`>C/C/}") == mml("C!D`>E/F`/")
    assert mml("CDEF").Apply("{C.C/}@@") == mml("C.D/E.F/")
    assert mml("[CE] [EG] [EGB]").Apply("C [C? C] [C? C]") == \
        mml("[CE] [E? G] [E? G? B]")
    assert mml("CDEF").Apply("C$vol(70)rCr$vol(80)C$vol(90)C") == \
        mml("CDEF").Apply("C$vol(70)rDr$vol(80)E$vol(90)F")


def test_mapstream():
    pitches = []

    def func(stream):
        try:
            while True:
                ev = next(stream)
                pitches.append(ev.n)
                yield ev
        except StopIteration as e:
            return e.value

    s = mml('c{de}/').Retrograde()
    assert s.mapstream(func) == s.sorted()
    assert s.stream().mapstream(func).evlist() == s.sorted()
    assert pitches == [E4, D4, C4, E4, D4, C4]
    s = mml('[c(dt=30){r(L=50)d(dt=99)}{r(L=100)e(dt=-99)}]')
    pitches = []
    assert s.mapstream(func, sort_by_ptime=True) == s
    assert s.stream().mapstream(func, sort_by_ptime=True).evlist() == s
    assert pitches == [E4, C4, D4, E4, C4, D4]


def test_chord_iterator():
    c4 = NoteEvent(t=0, n=C4, L=480, v=80, nv=None, tk=1, ch=1)
    e4 = NoteEvent(t=0, n=E4, L=240, v=80, nv=None, tk=1, ch=1)
    s = note(C4) & note(E4, 240) & sc.vol([(120, 50)])
    assert list(s.chord_iterator()) == \
        [EventList([c4, e4, CtrlEvent(120, C_VOL, 50)], 240, start=0),
         EventList([c4], 480, start=240)]
    assert par(s.chord_iterator(cont_notes=False)) == s
    assert par(EventList((ev for ev in evlist if ev.t >= evlist.start),
                         evlist.duration)
               for evlist in s.chord_iterator()) == s
    s = note(C4, step=960)
    assert list(s.chord_iterator()) == \
        [EventList([c4], 480, start=0), EventList([], 960, start=480)]
    assert par(s.chord_iterator(cont_notes=False)) == s
    assert list(s.chord_iterator(240)) == \
        [EventList([c4], 240, start=0), EventList([c4], 480, start=240),
         EventList([], 720, start=480), EventList([], 960, start=720)]
    assert par(s.chord_iterator(240, cont_notes=False)) == s
    s2 = note(C4, step=950)
    assert list(s2.chord_iterator(240)) == \
        [EventList([c4], 240, start=0), EventList([c4], 480, start=240),
         EventList([], 720, start=480), EventList([], 950, start=720)]
    assert par(s2.chord_iterator(240, cont_notes=False)) == s2
    assert list(s.chord_iterator([240, 480])) == \
        [EventList([c4], 240, start=0), EventList([c4], 480, start=240),
         EventList([], 960, start=480)]
    assert par(s.chord_iterator([240, 480], cont_notes=False)) == s
    assert list(s.chord_iterator(i*300 for i in itertools.count())) == \
        [EventList([c4], 300, start=0), EventList([c4], 600, start=300),
         EventList([], 900, start=600), EventList([], 960, start=900)]
    assert par(s.chord_iterator((i*300 for i in itertools.count()),
                                cont_notes=False)) == s


def test_genseq():
    s = genseq([note(C4), rest(), note(D4)])
    assert EventList(s) == mml("CrD")
    s = genseq([note(C4, step=240), note(D4), note(E4, step=240)])
    assert EventList(s) == mml("[c{r/d}{r/re}]& rr")
    s = genseq(note(p) for p in range(40, 80))
    s2 = seq(note(p) for p in range(40, 80))
    assert(EventList(s.tee()) == s2)
    assert(EventList(s.tee()) == EventList(s2.stream()))


def test_scale():
    scale = Scale(C4, 'major')
    assert(scale[0] == C4 and scale[2] == E4 and scale[0.5] == Cs4)
    scale = Scale(F4, ScaleLibrary.minor)
    assert(str(scale.pitches()) == "[F4, G4, Ab4, Bb4, C5, Db5, Eb5]")
    assert(scale.to_key() == Key('F minor'))
    assert(scale.is_scale_tone(Ab5) and not scale.is_scale_tone(E4))
    assert(scale.tonenum(G3) == -6 and scale.tonenum(Fs4) == 0.5 - 0.01)
    assert(scale.get_near_scale_tone(G5) == G5 and
           scale.get_near_scale_tone(Fs4) == F4 and
           scale.get_near_scale_tone(Gb4) == G4)


def test_chord():
    chords = ('C7b9', 'C(9)', 'C7(9)', 'C69', 'C13#11', 'CaugM7', 'C#11',
              'CdimM9', 'F#m7b5(11)', 'C7sus4b9', 'C7omit3add2',
              'C7(alter#5,addb9)', 'G7(b13,#9,b9)', 'C/E', 'FM7/G')
    pitches = ((C3, E3, G3, Bb3, Db4),
               (C3, E3, G3, D4),
               (C3, E3, G3, Bb3, D4),
               (C3, E3, G3, A3, D4),
               (C3, E3, G3, Bb3, D4, Fs4, A4),
               (C3, E3, Gs3, B3),
               (Cs3, Es3, Gs3, B3, Ds4, Fs4),
               (C3, Eb3, Gb3, B3, D4),
               (Fs3, A3, C4, E4, B4),
               (C3, F3, G3, Bb3, Db4),
               (C3, D3, G3, Bb3),
               (C3, E3, Gs3, Bb3, Db4),
               (G3, B3, D4, F4, Ab4, As4, Eb5),
               (E3, G3, C4),
               (G3, A3, C4, E4, F4))
    for c, ps in zip(chords, pitches):
        assert Chord(Chord(c).name()) == Chord(c)
        assert Chord(c).simplify().degrees() == \
            { k: tuple(sorted(v)) for k,v in Chord(c).degrees().items() }
        assert chroma_profile(Chord(c).simplify().pitches()) ==  \
            chroma_profile(Chord(c).pitches())
        assert Chord(c).pitches() == list(ps)
        assert Chord(c).simplify().pitches() == list(ps)

    assert list(Chord('C7').pitches_above(D4, 5)) == [E4, G4, Bb4, C5, E5]
    assert list(Chord('C7').pitches_below(D4, 5)) == [C4, Bb3, G3, E3, C3]

    for b in range(1, 4096):
        cp = [int(bool(b & (1 << k))) for k in range(12)]
        assert chroma_profile(Chord.from_chroma_profile(cp).pitches()) == cp


def test_json(tmp_path):
    tmpfile = tmp_path.joinpath('test.json')

    for mid in ['menuet.mid', 'test1.mid', 'grieg.mid']:
        s = readsmf(os.path.join(os.path.dirname(__file__), mid))
        writejson(s, str(tmpfile))
        assert s == readjson(str(tmpfile))

    testobj = {'a': Interval('A6'), 'b': (1, Cs8), 'c': Fraction(3, 4),
               'd': XmlEvent(480, 'chord', Chord('C7b9omit3')),
               'f': NoteEvent(0, C5, 80, user1=math.inf, user2=-math.inf),
               'g': EventList([], user3=None, user4=True)}  
    writejson(testobj, str(tmpfile))
    assert testobj == readjson(str(tmpfile))
