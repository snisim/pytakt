from setuptools import setup, find_packages, Extension
import sys


with open('pytakt/_version.py') as f:
    for line in f.readlines():
        if '__version__ =' in line:
            exec(line)


cmidiio = Extension('pytakt.cmidiio',
                    sources=[
                        'pytakt/src/cmidiio.cpp',
                        'pytakt/src/midiin.cpp',
                        'pytakt/src/midiout.cpp',
                        'pytakt/src/sysdep.cpp',
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
    name="pytakt",
    version=__version__,
    author="Satoshi Nishimura",
    author_email='nisim@u-aizu.ac.jp',
    description="A Python library for music description, generation, and processing with realtime MIDI I/O",
    url="http://github.com/snisim/pytakt/",
    license="BSD-3-Clause",
    python_requires=">=3.6",
    install_requires=["Arpeggio>=1.9"],
    packages=find_packages(),
    ext_modules=[cmidiio],
    entry_points={
        "console_scripts": [
            "pytakt = pytakt.pytaktcmd:main",
        ],
    },
    classifiers=[
        'Development Status :: 4 - Beta',
        'License :: OSI Approved :: BSD License',
        'Operating System :: MacOS :: MacOS X',
        'Operating System :: Microsoft :: Windows',
        'Operating System :: POSIX :: Linux',
        'Topic :: Multimedia :: Sound/Audio :: MIDI',
    ],
)
