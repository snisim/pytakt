#pytakt
#
# Minuet in G major from Notebook for Anna Magdalena Bach (BWV Anh. 114)
#
from pytakt import *

rh = newcontext(tk=1, ch=1, v=80)  # context for the right hand
lh = newcontext(tk=2, ch=2, v=60, o=3)  # context for the left hand

score = sc.keysig('G-major') + sc.timesig(3, 4) + sc.tempo(160)

# Bars 1-16
score += (rh.mml("^D {G A B ^C}/ ^D G G  ^E ^{C D E F#}/  ^G G G") &
          lh.mml("[{G* A} B*. ^D*.] B~~  ^C~~ B~~"))
score += (rh.mml("^C {^D ^C B A}/ B {^C B A G}/"
                 "F# {G A B G}/ A~~|Product('{L16 d}c')") &
          lh.mml("A~~ G~~  ^D B G ^D {D ^C B A}/"))
score += (rh.mml("^D {G A B ^C}/ ^D G G  ^E ^{C D E F#}/  ^G G G") &
          lh.mml("B~ A G B G  ^C~~ B {^C B A G}/"))
score += (rh.mml("^C {^D ^C B A}/ B {^C B A G}/  A {B A G F#}/ G~~") &
          lh.mml("A~ F# G~ B  ^C ^D D G~ _G"))
# Or, you can write it in the following way:
#   score += mml("""
#     [$rh:{ ^D {G A B ^C}/ ^D G G  ^E ^{C D E F#}/  ^G G G }
#      $lh:{ [{G* A} B*. ^D*.] B~~  ^C~~ B~~ }]
#     [$rh:{ ^C {^D ^C B A}/ B {^C B A G}/  F# {G A B G}/ A~~ }
#          :
#   """)

# Bars 17-32
score += (rh.mml("o+=1 B {G A B G}/ A {D E F# D}/"
                 "G {E F# G D}/ C# {_B C#}/ _A") &
          lh.mml("G~~ F#~~ E G E A~ _A"))
score += (rh.mml("{A B ^C# ^D ^E ^F#}/ ^G ^F# ^E  ^F# A ^C# ^D~~") &
          lh.mml("A~~ B ^D ^C#  ^D F# A ^D D ^C"))
score += (rh.mml("^D {G F#}/ G ^E {G F#}/ G  ^D ^C B {A G F# G}/ A") &
          lh.mml("[{B~ B} {r ^D~}] [{^C~ ^C} {r ^E~}]  B A G ^D~~"))
score += (rh.mml("{D E F# G A B}/ ^C B A  {B ^D}/ G F# [_B D G]~~") &
          lh.mml("[D~~ {r~ F#}] E G F#  G _B D G D _G"))


end_score(score)
