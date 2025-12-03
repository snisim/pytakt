#pytakt
#
# C. P. E. Bach: Einfall, einen doppelten Contrapunct in der Octave von sechs
# Tacten zu machen, ohne die Regeln davon zu wissen (A method for making six
# bars of double counterpoint at the octave without knowing the rules)
#

from pytakt import *
from pytakt.midiio import *
import random
import itertools

table1 = [
    ["e~g~e~c~", "d~_g~g~~~|Tie()", "g|EndTie()ab^cf~~~|Tie()", 
     "f|EndTie()~f~ecac", "d~~~~~cd", "efdec~~~"],
    ["regfegec", "gagf+g~~~|Tie()", "g|EndTie()~c~f~~~|Tie()", 
     "f|EndTie()~ede~c~", "d~gag~~f", "efedc~~~"],
    ["e~~~~~c~", "d_ggf+g~~~|Tie()", "g|EndTie()cdef~f~|Tie()",
     "f|EndTie()fedeedc", "d~~~d~~~", "e~dec~~~"],
    ["c~_g~e~c~", "d~d~g~~~|Tie()", "g|EndTie()c_bcf~~~|Tie()",
     "f|EndTie()~edegec", "d~~~~~~~", "ededc~~~"],
    ["r~cde~c~", "d~gf+g~~~|Tie()", "g|EndTie()g^cgf~f~|Tie()",
     "f|EndTie()~f~fedc", "d~g~~~fg", "efgec~~~"],
    ["efgfedec", "d~~~g~~~|Tie()", "g|EndTie()~~~f~~~|Tie()",
     "f|EndTie()~~fedec", "d~dcdef~", "egedc~~~"],
    ["c~~~e~~~", "g_gggg~~~|Tie()", "g|EndTie()gfef~~~|Tie()",
     "f|EndTie()~f~~~e~", "d~_g~g~f~", "ecedc~~~"],
    ["rccdeedc", "ddgf+g~~~|Tie()", "g|EndTie()edcf~f~|Tie()",
     "f|EndTie()~f~e~a~", "d~g~_g~f~", "e~~dc~~~"],
    ["c~cdedec", "g~_g~g~~~|Tie()", "g|EndTie()cfef~~~|Tie()",
     "f|EndTie()_bcdegfe", "d~gagafg", "e^cgec~~~"],
]

table2 = [
    ["r~~~c~c~|Tie()", "c|EndTie()~_b_a_b~_g~", "_a~~~dc_b_a",
     "_g~_a_bc~~~|Tie()", "c|EndTie()~_b_a_b~~~", "c~~~~~~~"],
    ["c~~~~~c~|Tie()", "c|EndTie()~c~_b~_b~", "_a~~~~~_a-~",
     "_g~~~c~c~|Tie()", "c|EndTie()~_b_a_b~_a_b", "c~~~~~~~"],
    ["c~edc~c~|Tie()", "c|EndTie()c_{babbag}", "_{a~a~a^caf}",
     "_g~_g~c~~~|Tie()", "c|EndTie()~_b~~_a_b~", "c~~~~~~~"],
    ["_c~~~c~~~|Tie()", "c|EndTie()~_b_a_bd_b_g", "_a~~~~_bcd",
     "_{ggab}c~~~|Tie()", "c|EndTie()_a_bc_bc_a_b", "c~~~~~~~"],
    ["r~~~c~~~|Tie()", "c|EndTie()~c~~~_b~", "_a~~~_{dfed}",
     "_gdc_bc~c~|Tie()", "c|EndTie()~c~_b~_b~", "c~~~~~~~"],
    ["r~_{edc~}c~|Tie()", "c|EndTie()~c~_b~e~", "_a~~~~~d~",
     "_g~_g~c~c~|Tie()", "c|EndTie()~_b~~~_a_b", "c~~~~~~~"],
    ["c~~~~~~~|Tie()", "c|EndTie()~_b_a_bcde", "_{a~a~~agf}",
     "_g_gc_bc~c~|Tie()", "c|EndTie()~~~_b~~~", "c~~~~~~~"],
    ["_{c~eg}c~c~|Tie()", "c|EndTie()~_b~edc_b", "_a~_a~~~d~",
     "_g~c_bc~~~|Tie()", "c|EndTie()~~~_{b~ab}", "c~~~~~~~"],
    ["c_c_e_gc~c~|Tie()", "c|EndTie()c_b_ac_b_a_g", "_a~~~~c_b_a",
     "_g~~~_c~c~|Tie()", "c|EndTie()c_{babbab}", "c~~~~~~~"],
]

inst1 = newcontext(tk=1, ch=1, o=5, L=L8)
inst2 = newcontext(tk=2, ch=2, o=4, L=L8)

header = inst1.prog(gm.Flute) + inst2.prog(gm.Cello)

def generate_six_measures():
    score1 = empty()
    score2 = empty()
    for i in range(6):
        score1 += inst1.mml(table1[random.randrange(9)][i])
        score2 += inst2.mml(table2[random.randrange(9)][i])
    return (score1, score2)

def generate_twelve_measures():
    s1, s2 = generate_six_measures()                               
    # In the second half, the same phrases are repeated with the voices swapped.
    return (s1 & s2) + (s1.Modify('tk=2; ch=2; n-=12') &
                        s2.Modify('tk=1; ch=1; n+=12'))

score = header + genseq(generate_twelve_measures() for _ in itertools.count())

end_score(score)
