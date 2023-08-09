from setuptools import setup, find_packages, Extension
import sys


with open('takt/__init__.py') as f:
    for line in f.readlines():
        if '__version__ =' in line:
            exec(line)


cmidiio = Extension('takt.cmidiio',
                    sources=[
                        'takt/src/cmidiio.cpp',
                        'takt/src/midiin.cpp',
                        'takt/src/midiout.cpp',
                        'takt/src/sysdep.cpp',
                    ],
                    libraries=(
                        ["winmm"] if (sys.platform == 'win32' or
                                      sys.platform == 'cygwin') else 
                        ["asound"] if sys.platform == 'linux' else
                        []),
                    extra_link_args=(
                        ["-framework", "CoreFoundation",
                         "-framework", "CoreServices",
                         "-framework", "CoreMIDI",
                         "-framework", "CoreAudio"] if sys.platform == 'darwin'
                        else []),
                    )

setup(
    name="takt",
    version=__version__,
    author="Satoshi Nishimura",
    description="A Music Information Processing Library with Realtime MIDI I/O",
    url="http://github.com/snisim/pytakt/",
    python_requires=">=3.6",
    install_requires=["Arpeggio>=1.9"],
    packages=find_packages(),
    ext_modules=[cmidiio],
    entry_points={
        "console_scripts": [
            "pytakt = takt.pytakt:main",
        ],
    }
)
