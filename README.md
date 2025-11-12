[English](README.md) | [日本語](README-ja.md)

# Pytakt
**A Python library for music description, generation, and processing
with realtime MIDI I/O**

Pytakt is a **Python library** for music information processing based on
musical events such as notes and MIDI control changes.
It supports both real-time and non-real-time processing.
Intended uses of Pytakt include research in the field of
music information science such as automatic composition,
as well as simple text-based music production or building music applications.

* [Paper](https://doi.org/10.1080/09298215.2025.2540434)
* [Pytakt API Documents](http://u-aizu.ac.jp/~nisim/pytakt/index.html)


## Main Features

* It is possible to read a **standard MIDI file** and generate a Pytakt score
  object (hereafter, *score*), which is based on the event list.
  Conversely, scores can be exported to standard MIDI files.
  It can handle all types of events defined in the specification of
  standard MIDI files.
* It is possible to concatenate or merge scores and apply various
  transformations on scores such as transposition, extraction of certain
  types of events, channel renumbering, quantization, etc. through
  a mechanism called an **Effector**.
* Has MIDI input/output capability, allowing Pytakt to **play** scores and
  perform MIDI recording.
* Has a simple **piano-roll viewer** to visualize the score contents.
* Conversion of scores to/from [music21](http://web.mit.edu/music21/)
  is possible.
* Each note in the score can be represented either as a single event or
  as two separate events, note-on and note-off.
  Effectors are also provided to convert between these two representations.
* Scores can be generated using an extended **MML (Music Macro Language)**.
  This allows for a concise representation of a piece of music by a string,
  and also allows for the addition of expressive information such as
  dynamics, etc.
* There is a function called *note* that generates a single note, which can
  be used for **procedural score generation**.
  Moreover, using Python's generator mechanism, it is possible to represent
  **infinite-length scores**.
* It can receive events from MIDI input, allowing for platform independent
  **real-time MIDI processing**. Many of the effectors are also available
  for event streams from MIDI input.
* A driver program named **pytakt** is provided to convert between
  a standard MIDI file and a text file, display piano rolls, playback,
  show summary information, display available devices, etc.
  without program coding.


## Supported Platforms

* **Windows**  
  Works with both Python from python.org and Anaconda.
* **Windows (Cygwin)**  
  Works if you have two Cygwin packages pythonXX-devel and pythonXX-tkinter
  (XX is the version number of Python) already installed for Cygwin.
  X-Window is required for piano roll display.
* **Mac**  
  Works. To produce sounds on a PC alone, it is necessary to connect Pytakt
  output to a DAW such as GarageBand via IAC.
* **Linux**
  It will work if you have the ALSA development module (libasound2-dev)
  installed on your OS. As mentioned below, a software synthesizer
  such as TiMidity++ is required to produce sound on a PC.


## How To Install

The Pytakt library can be installed via pip as below.

    pip install pytakt

If you need conversion to/from music21, music21 (version 6.7.1 or later)
also needs to be installed (it is not installed automatically).

    pip install music21


## Operation Check

After starting Python, import the pytakt module as follows.

    >>> from pytakt import *
    >>> from pytakt.midiio import *

(The second line above is needed only if you perform direct operations on
MIDI input/output; it is not necessary for show() or play())

Instead of the above, the pytakt command can be invoked from
the command prompt (shell) with no arguments. The modules will be
automatically imported and the same state as above will be achieved.

    % pytakt
    pytakt version X.XX
    >>>

Let's try to generate a score with the Music Macro Language
using the mml function.

    >>> mml('cde')
    EventList(duration=1440, events=[
        NoteEvent(t=0, n=C4, L=480, v=80, nv=None, tk=1, ch=1),
        NoteEvent(t=480, n=D4, L=480, v=80, nv=None, tk=1, ch=1),
        NoteEvent(t=960, n=E4, L=480, v=80, nv=None, tk=1, ch=1)])

What is printed is the content of the score object.
Next, let's display a piano roll using the show() method.

    >>> mml('cde').show()

<img src="https://github.com/snisim/pytakt/assets/141381385/e80e8169-a7b3-491e-99dc-486c6f8f9ff1" width=500 alt="pianoroll">

After confirming the view, close the Piano Roll window.

Now, let's try to play the score. Playback requires a synthesizer of some
kind (a means of converting MIDI messages into sound waveforms).
If you have a MIDI keyboard that produces sound,
you can use it by connecting it to your PC via MIDI.
To produce sound on your PC by itself, a software synthesizer is required.
For Windows, a built-in software synthesizer is available.
For Mac, it is necessary to connect Pytakt output to a DAW such as GarageBand
via IAC.
For Linux, TiMidity++ or other synthesizing software needs to be installed.

The MIDI devices available for output can be checked with show_devices()
as below (an example on a Windows PC with an external MIDI interface is
shown here).

    >>> show_devices()
     >  [0] Microsoft MIDI Mapper
        [1] Microsoft GS Wavetable Synth
        [2] UM-1

    MIDI Input Devices:
     >  [0] UM-1

    '*': opened   '>': currently selected

If you want to change the output device, use set_output_device() to switch.

    >>> set_output_device(2)
    >>> show_devices()
        [0] Microsoft MIDI Mapper
        [1] Microsoft GS Wavetable Synth
     >  [2] UM-1
       :

If everything is set up correctly, you should be able to play a score like
this:

    >>> mml('cde').play()

In the example below, the performance is repeated infinitely.

    >>> mml('cde').Repeat().play()

To stop the performance, press Ctrl-C (or the 'i' key twice in the case of 
Jupyter Notebook).

If you have a MIDI keyboard connected as an input device, you can display
what you play using the monitor() function.

    >>> monitor()
    NoteOnEvent(t=7067.07837, n=E4, v=49, tk=0, ch=1)
    NoteOffEvent(t=7194.10766, n=E4, nv=None, tk=0, ch=1)

If music21 is installed and the MusicXML viewer is configured correctly,
staff notation can be displayed by the following:

    >>> mml('cde').music21().show()


## Licence

The Pytakt package is released under the 3-Clause BSD License.
See the LICENSE.txt file for details.


## CAVEAT

Running Python programs that generate or process music, including those
converted using the -t option of the pytakt command,
obtained from untrusted sources poses serious security risks.
Similarly, evaluating MML strings obtained from external sources carries
a similar risk due to the ability to embed Python code within MML,
unless safe_mml() is used.


## Publication

* Satoshi Nishimura and Atsushi Marui, "Pytakt: a Python library for
symbolic music description, generation, and real-time processing,"
Journal of New Music Research, doi: [10.1080/09298215.2025.2540434](https://doi.org/10.1080/09298215.2025.2540434), 2025.


## Author

Satoshi Nishimura (University of Aizu)


## Collaborator

Atsushi Marui (Tokyo University of the Arts)
