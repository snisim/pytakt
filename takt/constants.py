# coding:utf-8
from takt.utils import int_preferred

TICKS_PER_QUARTER = 480
"""
Constant defining the length of one tick in the takt package.
"""
"""
taktパッケージ内における1ティックの長さを定義している定数です。
"""

L1 = int_preferred(TICKS_PER_QUARTER * 4)  # whole note
""
L1DOT = int_preferred(TICKS_PER_QUARTER * 4 * 1.5)  # dotted whole note
""
L1DOTDOT = int_preferred(TICKS_PER_QUARTER * 4 * 1.75)
""
L2 = int_preferred(TICKS_PER_QUARTER * 2)
""
L2DOT = int_preferred(TICKS_PER_QUARTER * 2 * 1.5)
""
L2DOTDOT = int_preferred(TICKS_PER_QUARTER * 2 * 1.75)
""
L4 = int_preferred(TICKS_PER_QUARTER)  # quarter note
""
L4DOT = int_preferred(TICKS_PER_QUARTER * 1.5)
""
L4DOTDOT = int_preferred(TICKS_PER_QUARTER * 1.75)
""
L8 = int_preferred(TICKS_PER_QUARTER / 2)
""
L8DOT = int_preferred(TICKS_PER_QUARTER / 2 * 1.5)
""
L8DOTDOT = int_preferred(TICKS_PER_QUARTER / 2 * 1.75)
""
L16 = int_preferred(TICKS_PER_QUARTER / 4)
""
L16DOT = int_preferred(TICKS_PER_QUARTER / 4 * 1.5)
""
L16DOTDOT = int_preferred(TICKS_PER_QUARTER / 4 * 1.75)
""
L32 = int_preferred(TICKS_PER_QUARTER / 8)
""
L32DOT = int_preferred(TICKS_PER_QUARTER / 8 * 1.5)
""
L32DOTDOT = int_preferred(TICKS_PER_QUARTER / 8 * 1.75)
""
L64 = int_preferred(TICKS_PER_QUARTER / 16)
""
L64DOT = int_preferred(TICKS_PER_QUARTER / 16 * 1.5)
""
L64DOTDOT = int_preferred(TICKS_PER_QUARTER / 16 * 1.75)
""
L128 = int_preferred(TICKS_PER_QUARTER / 32)
""
L128DOT = int_preferred(TICKS_PER_QUARTER / 32 * 1.5)
""
L128DOTDOT = int_preferred(TICKS_PER_QUARTER / 32 * 1.75)
"""
Constants that represent the number of ticks for each note value.
L\\ :math:`n` means :math:`n`-th notes/rests.
DOT means dotted, DOTDOT means double dotted note/rests.
"""
"""
各音価に相当するティック数を表した定数です。
L\\ :math:`n` は、:math:`n` 分音符/休符を意味します。
DOTは付点、DOTDOTは複付点音符/休符を意味します。
"""


MAX_DELTA_TIME = L1
"""
Represents the maximum range of time that can be modified by the dt
attribute of an event.
The absolute value of the dt attribute must be less than or equal
to this value.
"""
"""
イベントのdt属性によって修正できる時刻の最大幅を表します。
dt属性の絶対値はこの値以下でなければなりません。
"""


EPSILON = 1e-6
LOG_EPSILON = -6


BEGIN = 1   # used by ties
END = 2


CONTROLLERS = {
    0: 'C_BANK',
    1: 'C_MOD',
    2: 'C_BREATH',
    4: 'C_FOOT',
    5: 'C_PORTA',
    6: 'C_DATA',
    7: 'C_VOL',
    8: 'C_BALANCE',
    10: 'C_PAN',
    11: 'C_EXPR',
    32: 'C_BANK_L',
    33: 'C_MOD_L',
    34: 'C_BREATH_L',
    36: 'C_FOOT_L',
    37: 'C_PORTA_L',
    38: 'C_DATA_L',
    39: 'C_VOL_L',
    40: 'C_BALANCE_L',
    42: 'C_PAN_L',
    43: 'C_EXPR_L',
    64: 'C_SUSTAIN',
    65: 'C_PORTAON',
    66: 'C_SOSTENUTO',
    67: 'C_SOFTPED',
    68: 'C_LEGATO',
    69: 'C_HOLD2',
    70: 'C_SOUND_VARIATION',
    71: 'C_TIMBRE_INTENSITY',
    72: 'C_RELEASE_TIME',
    73: 'C_ATTACK_TIME',
    74: 'C_BRIGHTNESS',
    75: 'C_DECAY_TIME',
    76: 'C_VIBRATO_RATE',
    77: 'C_VIBRATO_DEPTH',
    78: 'C_VIBRATO_DELAY',
    84: 'C_PORTA_CTRL',
    91: 'C_REVERB',
    92: 'C_TREMOLO',
    93: 'C_CHORUS',
    94: 'C_CELESTE_DEPTH',
    95: 'C_PHASER_DEPTH',
    96: 'C_DATA_INC',
    97: 'C_DATA_DEC',
    98: 'C_NRPCL',
    99: 'C_NRPCH',
    100: 'C_RPCL',
    101: 'C_RPCH',
    120: 'C_ALL_SOUND_OFF',
    121: 'C_RESET_ALL_CTRLS',
    122: 'C_LOCAL_CONTROL',
    123: 'C_ALL_NOTES_OFF',
    128: 'C_BEND',  # EXTENDED: pitch bend
    129: 'C_KPR',   # EXTENDED: key pressure
    130: 'C_CPR',   # EXTENDED: channel pressure
    131: 'C_PROG',  # EXTENDED: program change
    #    132: 'C_VSCALE',   # EXTENDED: velocity scaler
    192: 'C_TEMPO'   # EXTENDED: tempo,
    #    193: 'C_RTEMPO',# EXTENDED: tempo scaler
}
"""
A dict object defining the controller numbers.
Each string that is a value of the dict can also be used as an independent
constant, such as ``ctrl(C_BANK, 1)``.
"""
"""
コントローラ番号を定義した dictオブジェクトです。
値となっている各文字列は、``ctrl(C_BANK, 1)`` のように
独立した定数としても使用可能です。
"""

META_EVENT_TYPES = {
    0: 'M_SEQNO',
    1: 'M_TEXT',
    2: 'M_COPYRIGHT',
    3: 'M_TRACKNAME',
    4: 'M_INSTNAME',
    5: 'M_LYRIC',
    6: 'M_MARK',
    7: 'M_CUE',
    0x20: 'M_CHPREFIX',
    0x21: 'M_DEVNO',
    0x2f: 'M_EOT',
    0x51: 'M_TEMPO',
    0x54: 'M_SMPTE',
    0x58: 'M_TIMESIG',
    0x59: 'M_KEYSIG',
}
"""
A dict object that defines numbers representing the types of meta-events.
Each string value can also be used as an independent constant.
"""
"""
メタイベントの種類を表す番号を定義した dictオブジェクトです。
値となっている各文字列は、独立した定数としても使用可能です。
"""

M_TEXT_LIMIT = 0xf

for _k in CONTROLLERS:
    exec("%s=%d" % (CONTROLLERS[_k], _k))
for _k in META_EVENT_TYPES:
    exec("%s=%d" % (META_EVENT_TYPES[_k], _k))
