# coding:utf-8
"""
This module defines percussion instrument names assigned to each note number
as defined by General MIDI.

The following two constants define the relationship between percussion
instrument names and note numbers.

    - ``DRUMS``: A map (dict) from note numbers (int) to percussion names (str)
    - ``ALIASES``: A list of 2-tuples consisting of an alias (str) and
      the original percussion name (str).

In addition, for each percussion instrument, a function is defined that can
be used in place of the :func:`.note` function, with the percussion name
as its name.
Such a function calls :func:`.note` with the note number of the corresponding
percussion instrument as the first argument, and the calling arguments (if any)
as the second and further arguments.
Moreover, a constant whose name is 'N_percussion_name' and whose value
is its note number is defined for each percussion instrument (also for
aliases).

Examples:
    >>> gm.drums.DRUMS[36]
    'BassDrum1'
    >>> gm.drums.BassDrum1()
    EventList(duration=480, events=[
        NoteOnEvent(t=0, n=36, v=80, tk=1, ch=1, noteoff=(+480)),
        NoteOffEvent(t=480, n=36, nv=None, tk=1, ch=1)])
    >>> gm.drums.BD(v=50)
    EventList(duration=480, events=[
        NoteOnEvent(t=0, n=36, v=50, tk=1, ch=1, noteoff=(+480)),
        NoteOffEvent(t=480, n=36, nv=None, tk=1, ch=1)])
    >>> mml("ch=10 $BD() r $SD() r").play()
    >>> gm.drums.N_BD
    36
"""
"""
このモジュールには、General MIDI で定められている各ノート番号に
割り当てられて打楽器名が定義されています。

次の2つ定数によって打楽器名とノート番号の関係が定義付けられています。

    - ``DRUMS``: ノート番号(int)から打楽器名(str)へのマップ(dict)
    - ``ALIASES``: 別名(str)と元の打楽器名(str)からなる 2-tuple を集めたリスト

さらに、各打楽器名をその名前とした、:func:`.note` 関数のかわりに使用できる
関数が定義されています。これらの関数は、該当する打楽器のノート番号を第1引数、
呼んだ際の引数を（もしあれば）第2引数以降として :func:`.note` を呼び出します。
また、'N_打楽器名' という名前でノート番号を値とした定数も定義されて
います (別名についても同様)。

Examples:
    >>> gm.drums.DRUMS[36]
    'BassDrum1'
    >>> gm.drums.BassDrum1()
    EventList(duration=480, events=[
        NoteOnEvent(t=0, n=36, v=80, tk=1, ch=1, noteoff=(+480)),
        NoteOffEvent(t=480, n=36, nv=None, tk=1, ch=1)])
    >>> gm.drums.BD(v=50)
    EventList(duration=480, events=[
        NoteOnEvent(t=0, n=36, v=50, tk=1, ch=1, noteoff=(+480)),
        NoteOffEvent(t=480, n=36, nv=None, tk=1, ch=1)])
    >>> mml("ch=10 $BD() r $SD() r").play()
    >>> gm.drums.N_BD
    36
"""
# Copyright (C) 2023  Satoshi Nishimura

from pytakt.sc import note

#
# Definitions for note numbers of drum sets
#

DRUMS = {
    35: 'AcouBassDrum',
    36: 'BassDrum1',
    37: 'SideStick',
    38: 'AcouSnare',
    39: 'HandClap',
    40: 'ElectricSnare',
    41: 'LowFloorTom',
    42: 'ClosedHiHat',
    43: 'HighFloorTom',
    44: 'PedalHiHat',
    45: 'LowTom',
    46: 'OpenHiHat',
    47: 'LowMidTom',
    48: 'HiMidTom',
    49: 'CrashCymbal1',
    50: 'HighTom',
    51: 'RideCymbal1',
    52: 'ChineseCymbal',
    53: 'RideBell',
    54: 'Tambourine',
    55: 'SplashCymbal',
    56: 'Cowbell',
    57: 'CrashCymbal2',
    58: 'Vibraslap',
    59: 'RideCymbal2',
    60: 'HiBongo',
    61: 'LowBongo',
    62: 'MuteHiConga',
    63: 'OpenHiConga',
    64: 'LowConga',
    65: 'HighTimbale',
    66: 'LowTimbale',
    67: 'HighAgogo',
    68: 'LowAgogo',
    69: 'Cabasa',
    70: 'Maracas',
    71: 'ShortWhistle',
    72: 'LongWhistle',
    73: 'ShortGuiro',
    74: 'LongGuiro',
    75: 'Claves',
    76: 'HiWoodBlock',
    77: 'LowWoodBlock',
    78: 'MuteCuica',
    79: 'OpenCuica',
    80: 'MuteTriangle',
    81: 'OpenTriangle',
}

ALIASES = [
    ('AcouBD', 'AcouBassDrum'),
    ('BD2', 'AcouBassDrum'),
    ('BD', 'BassDrum1'),
    ('BD1', 'BassDrum1'),
    ('RimShot', 'SideStick'),
    ('SD', 'AcouSnare'),
    ('AcouSD', 'AcouSnare'),
    ('SD2', 'ElectricSnare'),
    ('ElecSnare', 'ElectricSnare'),
    ('LT2', 'LowFloorTom'),
    ('HH', 'ClosedHiHat'),
    ('ClosedHH', 'ClosedHiHat'),
    ('LT1', 'HighFloorTom'),
    ('PedalHH', 'PedalHiHat'),
    ('MT2', 'LowTom'),
    ('OpenHH', 'OpenHiHat'),
    ('MT1', 'LowMidTom'),
    ('HT2', 'HiMidTom'),
    ('HighMidTom', 'HiMidTom'),
    ('CrashCY', 'CrashCymbal1'),
    ('CrashCY1', 'CrashCymbal1'),
    ('HT1', 'HighTom'),
    ('RideCY', 'RideCymbal1'),
    ('RideCY1', 'RideCymbal1'),
    ('ChineseCY', 'ChineseCymbal'),
    ('SplashCY', 'SplashCymbal'),
    ('CrashCY2', 'CrashCymbal2'),
    ('RideCY2', 'RideCymbal2'),
    ('HighConga', 'OpenHiConga'),
    ('Quijada', 'ShortGuiro'),
    ('HighWoodBlock', 'HiWoodBlock'),
    ('Cuica', 'OpenCuica'),
    ('Triangle', 'OpenTriangle')]


for _note_num in DRUMS:
    exec("%s=lambda *args, **kwargs: note(%d, *args, **kwargs)"
         % (DRUMS[_note_num], _note_num))
    exec("%s=%d" % ("N_" + DRUMS[_note_num], _note_num))
for _alias, _inst in ALIASES:
    exec("%s=%s" % (_alias, _inst))
    exec("%s=%s" % ("N_" + _alias, "N_" + _inst))
