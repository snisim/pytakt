#pytakt
#
#  Hanon, The Virtuoso Pianist, Nos. 1-20
#

from pytakt import *


def hanon(up_pattern, down_pattern=None):
    cscale = Scale(C4, 'major')
    up_pattern = "L16" + up_pattern

    # If no down pattern is given, use the inversion of the up pattern.
    if down_pattern is None:
        down_pattern = lambda: mml(up_pattern).Invert(E4, cscale)
    else:
        down_pattern = "L16" + down_pattern

    return mml("L2 _{cdefgab}cdefgab").Product(up_pattern, scale=cscale) + \
        mml("L2 ^cbagfedc_{bagfed}").Product(down_pattern, scale=cscale)


# No. 1
hanon1 = hanon("cefgagfe")
# No. 2
hanon2 = hanon("ceagfgfe", "gd_bcdcde")
# No. 3
hanon3 = hanon("ceagfefg", "gd_bcdedc")
# No. 4
hanon4 = hanon("cdceagfe", "gfgd_bcde")
# No. 5
hanon5 = hanon("cagafgef", "cdcedfeg")
# No. 6
_hanon6 = hanon("cagafaea")
hanon6 = _hanon6.Clip(0, L2*13) + mml("L16 ^{_bgfgegdc}") + \
    _hanon6.Clip(L2*14, L2*27) + mml("L16 _{acdcecfe}")
# No. 7
hanon7 = hanon("cedfegfe")
# No. 8
hanon8 = hanon("cegafgef")
# No. 9
hanon9 = hanon("cefegfag").Clip(0, L2*27) + mml("L16 _{afefdede}")
# No. 10
hanon10 = hanon("cagfefef")
# No. 11
hanon11 = hanon("ceagagfg", "gd_bc_bcdc")
# No. 12
_hanon12 = hanon("acedcdec")
hanon12 = mml("L16 _{gcedcdec}") + _hanon12.Clip(L2, L2*13) + \
    mml("L16 ^{g_bdc_bcde}") + _hanon12.Clip(L2*14) + mml("L16 _{cgefgfef}")
# No. 13
hanon13 = hanon("ecfdgefg", "egdfecde")
# No. 14
hanon14 = hanon("cdfefegf")
# No. 15
_hanon15 = hanon("cedfegfa")
hanon15 = _hanon15.Clip(0, L2*13) + mml("L16 ^{_bdcedfef}") + \
    _hanon15.Clip(L2*14, L2*27) + mml("L16 _{afgefded}")
# No. 16
hanon16 = hanon("cedeagfg", "gded_bcdc")
# No. 17
_hanon17 = hanon("ceagbaga", "gd_bc_a_bc_a")
hanon17 = _hanon17.Clip(0, L2*13) + mml("L16 ^{_bdgfagfe}") + \
    _hanon17.Clip(L2*14, L2*26) + mml("L16 _{bfdecded}")
# No. 18
hanon18 = hanon("cdfegfde")
# No. 19
hanon19 = hanon("cafgafeg")
# No. 20
_hanon20 = hanon("eg^c^e^cb^ca", "^e^cgegfge")
hanon20 = _hanon20.Clip(0, L2*14) + mml("L16 ^{eg^c^e^cb^cg}") + \
    _hanon20.Clip(L2*14) + mml("L16 _{^e^cgegfgf}")


hanons = (hanon1 + hanon2 + hanon3 + hanon4 + hanon5 +
          hanon6 + hanon7 + hanon8 + hanon9 + hanon10 +
          hanon11 + hanon12 + hanon13 + hanon14 + hanon15 +
          hanon16 + hanon17 + hanon18 + hanon19 + hanon20)
score = sc.timesig(2, 4) + \
    hanons.Product("[c _c(tk=2)]") + mml("[_e c [__c _c](tk=2)]*")
end_score(score)
