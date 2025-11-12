#pytakt
#
# J. S. Bach, Prelude in C Major from the Well-Tempered Clavier I (BWV 846)
#

from pytakt import *


def pattern(n1, n2, n3, n4, n5):
    # Note that we need double braces for a literal brace in Python's f-string.
    return mml(f"""L16 tk=2 [{{{n1}~~~~~~~}}
                            {{r{n2}~~~~~~}}
                       tk=1 {{rr{n3}{n4}{n5}{n3}{n4}{n5}}}]@2 """)


score = sc.tempo(72)
# Bars 1-4
score += pattern('c', 'e', 'g', '^c', '^e')
score += pattern('c', 'd', 'a', '^d', '^f')
score += pattern('_b', 'd', 'g', '^d', '^f')
score += pattern('c', 'e', 'g', '^c', '^e')
# Bars 5-8
score += pattern('c', 'e', 'a', '^e', '^a')
score += pattern('c', 'd', 'f#', 'a', '^d')
score += pattern('_b', 'd', 'g', '^d', '^g')
score += pattern('_b', 'c', 'e', 'g', '^c')
# Bars 9-12
score += pattern('_a', 'c', 'e', 'g', '^c')
score += pattern('_d', '_a', 'd', 'f#', '^c')
score += pattern('_g', '_b', 'd', 'g', 'b')
score += pattern('_g', '_b-', 'e', 'g', '^c#')
# Bars 13-16
score += pattern('_f', '_a', 'd', 'a', '^d')
score += pattern('_f', '_a-', 'd', 'f', 'b')
score += pattern('_e', '_g', 'c', 'g', '^c')
score += pattern('_e', '_f', '_a', 'c', 'f')
# Bars 17-20
score += pattern('_d', '_f', '_a', 'c', 'f')
score += pattern('__g', '_d', '_g', '_b', 'f')
score += pattern('_c', '_e', '_g', 'c', 'e')
score += pattern('_c', '_g', '_b-', 'c', 'e')
# Bars 21-24
score += pattern('__f', '_f', '_a', 'c', 'e')
score += pattern('__f#', '_c', '_a', 'c', 'e-')
score += pattern('__a-', '_f', '_b', 'c', 'd')
score += pattern('__g', '_f', '_g', '_b', 'd')
# Bars 25-28
score += pattern('__g', '_e', '_g', 'c', 'e')
score += pattern('__g', '_d', '_g', 'c', 'f')
score += pattern('__g', '_d', '_g', '_b', 'f')
score += pattern('__g', '_e-', '_a', 'c', 'f#')
# Bars 29-32
score += pattern('__g', '_e', '_g', 'c', 'g')
score += pattern('__g', '_d', '_g', 'c', 'f')
score += pattern('__g', '_d', '_g', '_b', 'f')
score += pattern('__c', '_c', '_g', '_b-', 'e')
# Bars 33-
score += mml("""[L16 tk=2 __c~~~~~~~~~~~~~~~
                          {r_c~~~~~~~~~~~~~~}
                     tk=1 {rr_f_acfc_ac_a_f_a_f_d_f_d}]""")
score += mml("""[L16 tk=2 __c~~~~~~~~~~~~~~~
                          {r__b~~~~~~~~~~~~~~}
                     tk=1 {rrgb^d^f^db^dbgbdfed}]""")
score += mml("[tk=2 __c _c tk=1 e g ^c]**")

end_score(score)
