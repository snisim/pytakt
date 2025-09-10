from setuptools import setup, find_packages, Extension
import sys
import os


with open('pytakt/_version.py') as f:
    for line in f.readlines():
        if '__version__ =' in line:
            exec(line)


cppflags = os.getenv('CPPFLAGS')
use_generic = cppflags and '-DUSE_GENERIC' in cppflags


cmidiio = Extension('pytakt.cmidiio',
                    sources=[
                        'pytakt/src/cmidiio.cpp',
                        'pytakt/src/midiin.cpp',
                        'pytakt/src/midiout.cpp',
                        'pytakt/src/sysdep.cpp',
                    ],
                    libraries=(
                        ["winmm"]
                        if not use_generic and (sys.platform == 'win32' or
                                                sys.platform == 'cygwin') else
                        ["asound"]
                        if not use_generic and sys.platform == 'linux' else
                        []),
                    extra_link_args=(
                        ["-framework", "CoreFoundation",
                         "-framework", "CoreServices",
                         "-framework", "CoreMIDI",
                         "-framework", "CoreAudio"]
                        if not use_generic and sys.platform == 'darwin'
                        else []),
                    )


with open('README.md') as f:
    readme = f.readlines()
readme = ''.join(readme[1:])  # Skip the first line


setup(
    name="pytakt",
    version=__version__,
    author="Satoshi Nishimura",
    author_email='nisim@u-aizu.ac.jp',
    description="A Python library for music description, generation, and processing with realtime MIDI I/O",
    long_description=readme,
    long_description_content_type='text/markdown',
    keywords="MIDI, standard MIDI files, MML, algorithmic composition",
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
