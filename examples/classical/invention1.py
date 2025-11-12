#pytakt
#
# J. S. Bach, Invention in C major  (BWV 772)
#
from pytakt import *
import os


motive = mml("L16 cdefdec")
# motive = mml("L16 cde{fededc}*/3")  # triplet version
try:
    motive = safe_mml(os.environ['PYTAKT_MOTIVE'])  # from invention1_gui.py
except KeyError:
    pass

c_scale = Scale(C4, 'major')
g_scale = Scale(G4, 'major')
dm_scale = Scale(D4, 'melodicminor')
dmh_scale = Scale(D4, 'harmonicminor')
am_scale = Scale(A3, 'melodicminor')
f_scale = Scale(F4, 'major')
motive_inv = motive.Invert(C4, c_scale)

rh = sc.tempo(66)
lh = empty()

# Bars 1-6
rh += mml("r//") + motive + mml("{g ^c b ^c}/")
rh += mml("^d//") + motive.Transpose(DEG(5), c_scale) + mml("{^d ^g ^f ^g}/")
rh += mml("^e//") + motive_inv.Transpose(DEG(6)+DEG(8), c_scale) + \
    mml("^g//") + motive_inv.Transpose(DEG(4)+DEG(8), c_scale)
rh += mml("^e//") + \
    motive_inv.Transpose(DEG(5), c_scale).ConvertScale(c_scale, g_scale) + \
    mml("^c//") +\
    motive_inv.Transpose(DEG(3), c_scale).ConvertScale(c_scale, g_scale)
rh += mml("a/ d/ ^c/. ^d//") + mml("b//") + \
    motive_inv.Transpose(DEG(2), c_scale).ConvertScale(c_scale, g_scale)
rh += (motive_inv.Transpose(DEG(4), c_scale).Clip(L16*3) +
       motive_inv.Transpose(DEG(6), c_scale).Clip(L16*3)).\
       ConvertScale(c_scale, g_scale) + \
       mml("{^d {b ^c}/ ^d ^g}// {b {a g}/}/")

lh += mml("r* r//") + motive.Transpose(-DEG(8), c_scale)
lh += mml("{_g __g}/ r r//") + motive.Transpose(-DEG(4), c_scale)
lh += mml("{c _b c d e _g _a _b}/")
lh += mml("{c _e _f# _g _a _b}/ c~//")
lh += motive.Transpose(-DEG(11), c_scale).ConvertScale(c_scale, g_scale)
lh += mml("{_g __b _c _d _e _f# _g _e __b. _c/ _d __d}/")

# Bars 7-10
rh += mml("g/ r/ r r//") + motive.ConvertScale(c_scale, g_scale)
rh += mml("f#/ r/ r r//") + motive.Transpose(DEG(6), c_scale)
rh += mml("b/ r/ r r//") + motive_inv.Transpose(DEG(9), c_scale)
rh += mml("^c/ r/ r r//") + \
    motive_inv.Transpose(DEG(10), c_scale).Clip(0, L16*3) + \
    motive_inv.Transpose(DEG(9), c_scale).\
    ConvertScale(c_scale, dm_scale).Clip(L16*3)

lh += mml("r//") + \
    motive.Transpose(-DEG(15), c_scale).ConvertScale(c_scale, g_scale) + \
    mml("_{d g f# g}/")
lh += mml("_a//") + motive.Transpose(-DEG(11), c_scale).\
    ConvertScale(c_scale, g_scale) + mml("{_a d c d}/")
lh += mml("_g//") + motive_inv.Transpose(DEG(5), c_scale) + mml("{f e f d}/")
lh += mml("e//") + motive_inv.Transpose(DEG(6), c_scale) + mml("{g f g e}/")

# Bars 11-14
rh += mml("{^d ^c# ^d ^e ^f a b ^c#}/")
rh += mml("{^d f# g# a b ^c}/ ^d~//")
rh += motive.Transpose(DEG(5), c_scale).ConvertScale(c_scale, am_scale) + \
    mml("^{e d c e d c}//") + motive_inv.Transpose(DEG(11), c_scale).\
    ConvertScale(c_scale, am_scale).Clip(L16*5)
rh += mml("^{c a}//") + motive_inv.Transpose(DEG(16), c_scale).\
    ConvertScale(c_scale, am_scale).Clip(L16*5) + \
    mml("^{a e}//") + motive.Transpose(DEG(9), c_scale).Clip(L16*5) + \
    mml("{g# ^f ^e ^d ^c~ b a}//")

lh += mml("f//") + \
    motive_inv.Transpose(DEG(6), c_scale).ConvertScale(c_scale, dmh_scale) + \
    mml("a//") + \
    motive_inv.Transpose(DEG(4), c_scale).ConvertScale(c_scale, dm_scale)
lh += mml("f//") + \
    motive_inv.Transpose(DEG(5), c_scale).ConvertScale(c_scale, am_scale) + \
    mml("d//") + \
    motive_inv.Transpose(DEG(3), c_scale).ConvertScale(c_scale, am_scale)
lh += mml("_b/ _e/ d/. e// c//") + \
    motive_inv.Transpose(-DEG(2), c_scale).Clip(0, L16*3) + \
    motive_inv.Transpose(DEG(2), c_scale).ConvertScale(c_scale, am_scale).\
    Clip(L16*3)
lh += motive_inv.Transpose(DEG(2), c_scale).Clip(L16*3) + \
    motive_inv.Transpose(DEG(4), c_scale).Clip(L16*3) + mml("{e _a e _e}/")

# Bars 15-18
rh += mml("a//") + motive_inv.Transpose(DEG(13), c_scale) + mml("^g*~//")
rh += motive.Transpose(DEG(10), c_scale) + mml("^f*~//")
rh += motive_inv.Transpose(DEG(12), c_scale) + mml("^f*~//")
rh += motive.Transpose(DEG(9), c_scale) + mml("^e*~//")

s = motive_inv.Transpose(DEG(3), c_scale)
lh += mml("_a/ __a/ r r//") + \
    motive_inv.Transpose(DEG(3), c_scale).Clip(0, L16*3) + \
    motive_inv.Transpose(DEG(2), c_scale).\
    ConvertScale(c_scale, dm_scale).Clip(L16*3)
lh += mml("d*~//") + motive.Transpose(-DEG(3), c_scale)
lh += mml("_b*~//") + motive_inv.Transpose(DEG(2), c_scale)
lh += mml("c*~//") + \
    motive.Transpose(-DEG(7), c_scale).ConvertScale(c_scale, f_scale)

# Bars 19-
rh += motive.Transpose(DEG(5), c_scale).ConvertScale(c_scale, f_scale) + \
    mml("^d//") + \
    motive.Transpose(DEG(7), c_scale).ConvertScale(c_scale, f_scale)
rh += mml("^f//") + motive.Transpose(DEG(12), c_scale) + \
    mml("^{^c g e {d c}/}/")
rh += mml("^c//") + motive_inv.Transpose(DEG(4), c_scale).\
    ConvertScale(c_scale, f_scale) + \
    mml("{a b ^c e $tempo([66, (L4, 40)]) d ^c f b}//")
rh += mml("$tempo(66) [e g ^c]**")

lh += mml("{_a _b- _a _g _f d c _b-}/")
lh += mml("{_a f e d}/ e//") + motive.Transpose(-DEG(7), c_scale)
lh += mml("{_e _c _d _e}/ _{f d e f}// _g/ __g/")
lh += mml("[__c _c]**")


score = rh & lh.Modify('tk=2')
end_score(score)
