# coding:utf-8
"""
このサブパッケージには、General MIDI で定められている楽器名が
定義されています。

次の2つ定数によって楽器名とプログラム番号の関係が定義付けられています。

    - ``INSTRUMENTS``: プログラム番号(int)から楽器名(str)へのマップ(dict)
    - ``ALIASES``: 別名(str)と元の楽器名(str)からなる 2-tuple を集めたリスト

さらに、各楽器名をその名前とした、プログラム番号を値とした定数が
定義されています。

Examples:
    >>> gm.INSTRUMENTS[41]
    'Violin'
    >>> gm.Violin
    41
    >>> prog(gm.Piano2)
    EventList(duration=0, events=[
        CtrlEvent(t=0, ctrlnum=C_PROG, value=2, tk=1, ch=1)])
    >>> mml("$prog(gm.Strings) [CEG]").play()
    >>> getattr(gm, 'Flute')
    74
"""
# Copyright (C) 2023  Satoshi Nishimura

# import takt.gm.drums

#
# Definitions for General MIDI instrument names
#

INSTRUMENTS = {
    # Piano
    1: 'AcouGrandPiano',
    2: 'BrightAcouPiano',
    3: 'ElecGrandPiano',
    4: 'HonkyTonk',
    5: 'ElecPiano1',
    6: 'ElecPiano2',
    7: 'Harpsichord',
    8: 'Clavi',
    # Chromatic Percussion
    9: 'Celesta',
    10: 'Glockenspiel',
    11: 'MusicBox',
    12: 'Vibraphone',
    13: 'Marimba',
    14: 'Xylophone',
    15: 'TubularBells',
    16: 'Dulcimer',
    # Organ
    17: 'DrawbarOrgan',
    18: 'PercussiveOrgan',
    19: 'RockOrgan',
    20: 'ChurchOrgan',
    21: 'ReedOrgan',
    22: 'Accordion',
    23: 'Harmonica',
    24: 'TangoAccordion',
    # Guitar
    25: 'NylonAcouGuitar',
    26: 'SteelAcouGuitar',
    27: 'JazzElecGuitar',
    28: 'CleanElecGuitar',
    29: 'MutedElecGuitar',
    30: 'OverdrivenGuitar',
    31: 'DistortionGuitar',
    32: 'GuitarHarmonics',
    # Bass
    33: 'AcouBass',
    34: 'FingeredElecBass',
    35: 'PickedElecBass',
    36: 'FretlessBass',
    37: 'SlapBass1',
    38: 'SlapBass2',
    39: 'SynthBass1',
    40: 'SynthBass2',
    # Strings
    41: 'Violin',
    42: 'Viola',
    43: 'Cello',
    44: 'Contrabass',
    45: 'TremoloStrings',
    46: 'PizzicatoStrings',
    47: 'OrchestralHarp',
    48: 'Timpani',
    # Ensamble
    49: 'StringEnsemble1',
    50: 'StringEnsemble2',
    51: 'SynthStrings1',
    52: 'SynthStrings2',
    53: 'ChoirAahs',
    54: 'VoiceOohs',
    55: 'SynthVoice',
    56: 'OrchestraHit',
    # Brass
    57: 'Trumpet',
    58: 'Trombone',
    59: 'Tuba',
    60: 'MutedTrumpet',
    61: 'FrenchHorn',
    62: 'BrassSection',
    63: 'SynthBrass1',
    64: 'SynthBrass2',
    # Reed
    65: 'SopranoSax',
    66: 'AltoSax',
    67: 'TenorSax',
    68: 'BaritoneSax',
    69: 'Oboe',
    70: 'EnglishHorn',
    71: 'Bassoon',
    72: 'Clarinet',
    # Pipe
    73: 'Piccolo',
    74: 'Flute',
    75: 'Recorder',
    76: 'PanFlute',
    77: 'BlownBottle',
    78: 'Shakuhachi',
    79: 'Whistle',
    80: 'Ocarina',
    # Synth Lead
    81: 'SquareLead',
    82: 'SawtoothLead',
    83: 'CalliopeLead',
    84: 'ChiffLead',
    85: 'CharangLead',
    86: 'VoiceLead',
    87: 'FifthLead',
    88: 'BassAndLead',
    # Synth Pad
    89: 'NewAgePad',
    90: 'WarmPad',
    91: 'PolysynthPad',
    92: 'ChoirPad',
    93: 'BowedPad',
    94: 'MetallicPad',
    95: 'HaloPad',
    96: 'SweepPad',
    # Synth Effects
    97: 'Rain',
    98: 'Soundtrack',
    99: 'Crystal',
    100: 'Atmosphere',
    101: 'Brightness',
    102: 'Goblins',
    103: 'Echoes',
    104: 'SciFi',
    # Ethnic
    105: 'Sitar',
    106: 'Banjo',
    107: 'Shamisen',
    108: 'Koto',
    109: 'Kalimba',
    110: 'BagPipe',
    111: 'Fiddle',
    112: 'Shanai',
    # Percussive
    113: 'TinkleBell',
    114: 'Agogo',
    115: 'SteelDrums',
    116: 'Woodblock',
    117: 'TaikoDrum',
    118: 'MelodicTom',
    119: 'SynthDrum',
    120: 'ReverseCymbal',
    # Sound Effects
    121: 'GuitarFretNoise',
    122: 'BreathNoise',
    123: 'Seashore',
    124: 'BirdTweet',
    125: 'TelephoneRing',
    126: 'Helicopter',
    127: 'Applause',
    128: 'Gunshot',
}


ALIASES = [
    ('Piano1', 'AcouGrandPiano'),
    ('Piano2', 'BrightAcouPiano'),
    ('Piano3', 'ElecGrandPiano'),
    ('EPiano1', 'ElecPiano1'),
    ('EPiano2', 'ElecPiano2'),
    ('Glocken', 'Glockenspiel'),
    ('Santur', 'Dulcimer'),
    ('Organ1', 'DrawbarOrgan'),
    ('Organ2', 'PercussiveOrgan'),
    ('Organ3', 'RockOrgan'),
    ('Bandoneon', 'TangoAccordion'),
    ('AcouGuitar', 'NylonAcouGuitar'),
    ('SteelGuitar', 'SteelAcouGuitar'),
    ('JazzGuitar', 'JazzElecGuitar'),
    ('CleanGuitar', 'CleanElecGuitar'),
    ('MutedGuitar', 'MutedElecGuitar'),
    ('Overdrive', 'OverdrivenGuitar'),
    ('Distortion', 'DistortionGuitar'),
    ('FingeredBass', 'FingeredElecBass'),
    ('PickedBass', 'PickedElecBass'),
    ('Pizzicato', 'PizzicatoStrings'),
    ('Harp', 'OrchestralHarp'),
    ('Strings', 'StringEnsemble1'),
    ('SlowStrings', 'StringEnsemble2'),
    ('Horn', 'FrenchHorn'),
    ('BottleBlow', 'BlownBottle'),
    ('Square', 'SquareLead'),
    ('SquareWave', 'SquareLead'),
    ('Sawtooth', 'SawtoothLead'),
    ('SawWave', 'SawtoothLead'),
    ('Calliope', 'CalliopeLead'),
    ('Chiff', 'ChiffLead'),
    ('ChifferLead', 'ChiffLead'),
    ('Charang', 'CharangLead'),
    ('Voice', 'VoiceLead'),
    ('SoloVox', 'VoiceLead'),
    ('Fifths', 'FifthLead'),
    ('FifthSawWave', 'FifthLead'),
    ('NewAge', 'NewAgePad'),
    ('Fantasia', 'NewAgePad'),
    ('Warm', 'WarmPad'),
    ('Polysynth', 'PolysynthPad'),
    ('Choir', 'ChoirPad'),
    ('SpaceVoice', 'ChoirPad'),
    ('Bowed', 'BowedPad'),
    ('BowedGlass', 'BowedPad'),
    ('Metallic', 'MetallicPad'),
    ('MetalPad', 'MetallicPad'),
    ('Halo', 'HaloPad'),
    ('Sweep', 'SweepPad'),
    ('IceRain', 'Rain'),
    ('EchoDrops', 'Echoes'),
    ('Taiko', 'TaikoDrum'),
    ('FretNoise', 'GuitarFretNoise')]


for _prog_num in INSTRUMENTS:
    exec("%s=%d" % (INSTRUMENTS[_prog_num], _prog_num))
for _alias, _inst in ALIASES:
    exec("%s=%s" % (_alias, _inst))
