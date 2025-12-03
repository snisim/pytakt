#
# Generate a stream of random-pitch notes.
#
#  Description of the parameters
#  -----------------------------
#  Pitch range: Range of pitches (LOW and HIGH)
#  Scale: Musical scale from which pitches are sampled.
#  RNG type: Type of the random number generator.
#      uniform - a white noise with uniform distribution between LOW and HIGH.
#      Gaussian - a white noise with Gaussian distribution where the LOW-HIGH
#          range corresponds to the -3 sigma to +3 sigma range.  It may
#          generate values out of the LOW-HIGH range.
#      1/f - a pink noise generated with Voss's algorithm (# of dice is 3).
#      shuffle - the list of pitches on the scale between LOW and HIGH is
#          repeated with a random shuffle each time.
#      shuffle-repeat - the list of pitches on the scale between LOW and HIGH
#          is once randomly shuffled and then repeated.
#  Rhythm patterns: Rhythm patterns described in Pytakt MML.  Pitches in the
#    patterns are ignored.  Duration, velocity, delta time, MIDI channels, and
#    non-note events in the patterns are considered.  If two or more patterns
#    are specified, they are randomly selected each time they are applied.
#
#  The strings in the Comboboxes can be edited.
#
import pytakt as takt
import pytakt.midiio as midiio
import random
import itertools
import math
import tkinter
from tkinter import ttk
from tkinter.messagebox import showerror


GUI_UPDATE_PERIOD = 50


# 1/f random number generator using Voss's algorithm
class Rand1OverF:
    def __init__(self, ndice):
        self.ndice = ndice
        self.count = -1
        self.values = [0 for _ in range(ndice)]

    def random(self):
        newcount = (self.count + 1) % (1 << self.ndice)
        for i in range(self.ndice):
            if (self.count ^ newcount) & (1 << i):
                self.values[i] = random.random()
        self.count = newcount
        return sum(self.values) / self.ndice

    def randrange(self, start, stop):
        return start + int(self.random() * (stop - start))


class MyCombobox(ttk.Combobox):
    def __init__(self, master, values, initial, width, validate, command,
                 addnewvalue=False):
        # `validate' is a function that is called when the value is selected
        # or entered. It should return False if the entered value is invalid,
        # or return True otherwise.
        # If `addnewvalue' is True, the entered value is appended to `values'
        # unless it is already there.
        self.values = values
        self.textvar = tkinter.StringVar(value=initial)
        self.validate = validate
        self.command = command
        self.addnewvalue = addnewvalue
        self.value_at_enter = None
        super().__init__(master, values=values, textvariable=self.textvar,
                         width=width)
        self.bind('<Return>', self.on_enter)
        self.bind('<<ComboboxSelected>>', self.on_enter)

    def get(self):
        return self.textvar.get()

    def on_enter(self, tkevent):
        if self.validate():
            if self.addnewvalue and self.get() not in self.values:
                self.values.append(self.get())
                self.configure(values=self.values)
        else:
            showerror("Error", f'Bad entered value "{self.get()}"')
        self.command()


class RandomStream(tkinter.Frame):
    def __init__(self, master):
        self.master = master
        self.scalelist = ['Major', 'NaturalMinor', 'MelodicMinor',
                          'HarmonicMinor', 'Dorian', 'Phrygian', 'Lydian',
                          'MixoLydian', 'Locrian',
                          'Chromatic', 'Wholetone', 'DiminishedWH',
                          'DiminishedHW', 'HalfDiminished', 'Altered',
                          'Overtone', 'PhrygianDominant',
                          'Pentatonic', 'MinorPentatonic',
                          'JapaneseYo', 'JapaneseIn', 'Ryukyu',
                          'Blues', 'GypsyMinor', 'HungarianGypsy',
                          'NeapolitanMajor', 'NeapolitanMinor']
        self.rhythmlist = ['', 'c', 'c/', 'c//', 'c/3',
                           'c*', 'c/.c//', '{c~c}/3',
                           'c{cc}/', '{cc}/c', 'c/cc/', 'c{ccc}/3',
                           'cc', '{cccc}/', '{ccc}*/3', 'cc!!', 'c`c?',
                           '[cc]', '[ccc]']
        self.randtype = tkinter.StringVar(value='uniform')
        super().__init__(master)
        self.create_widgets()
        self.validate_all()

    def create_widgets(self):
        pitches = [takt.Pitch(p).tostr(sfn='#b')
                   for p in range(takt.A0, takt.C8)]
        pitch_frame = tkinter.Frame(self, relief='raised', borderwidth=2)
        tkinter.Label(pitch_frame, text="Pitch range:").pack(
            side=tkinter.LEFT, padx=20, pady=20)
        self.lowlimitbox = MyCombobox(
            pitch_frame, values=pitches, initial='C4', width=4,
            validate=self.validate_limits, command=self.master.restart)
        self.lowlimitbox.pack(side=tkinter.LEFT, padx=20)
        self.highlimitbox = MyCombobox(
            pitch_frame, values=pitches, initial='C6', width=4,
            validate=self.validate_limits, command=self.master.restart)
        self.highlimitbox.pack(side=tkinter.LEFT, padx=20)
        pitch_frame.pack(fill='x')

        scale_frame = tkinter.Frame(self, relief='raised', borderwidth=2)
        tkinter.Label(scale_frame, text="Scale:").pack(
            side=tkinter.LEFT, padx=20, pady=20)
        self.scalerootbox = MyCombobox(
            scale_frame,
            values=[takt.Pitch(p).tostr(sfn='#b', octave=False)
                    for p in range(takt.C4, takt.C5)], initial='C',
            width=3, validate=self.validate_scale, command=self.master.restart)
        self.scalerootbox.pack(side=tkinter.LEFT, padx=20)
        self.scaletypebox = MyCombobox(
            scale_frame, values=self.scalelist, initial='Major', width=14,
            validate=self.validate_scale, command=self.master.restart,
            addnewvalue=True)
        self.scaletypebox.pack(side=tkinter.LEFT, padx=20)
        scale_frame.pack(fill='x')

        rng_frame = tkinter.Frame(self, relief='raised', borderwidth=2)
        tkinter.Label(rng_frame, text="RNG type:").grid(
            row=0, column=0, padx=20)
        tkinter.Radiobutton(
            rng_frame, text='uniform', value='uniform',
            variable=self.randtype, command=self.master.restart).grid(
                row=0, column=1, stick='w')
        tkinter.Radiobutton(
            rng_frame, text='Gaussian', value='Gaussian',
            variable=self.randtype, command=self.master.restart).grid(
                row=0, column=2, stick='w')
        tkinter.Radiobutton(
            rng_frame, text='1/f', value='1/f',
            variable=self.randtype, command=self.master.restart).grid(
                row=0, column=3, stick='w')
        tkinter.Radiobutton(
            rng_frame, text='shuffle', value='shuffle',
            variable=self.randtype, command=self.master.restart).grid(
                row=1, column=1, stick='w')
        tkinter.Radiobutton(
            rng_frame, text='shuffle-repeat', value='shuffle-repeat',
            variable=self.randtype, command=self.master.restart).grid(
                row=1, column=2, stick='w')
        rng_frame.pack(fill='x')

        rhythm_frame = tkinter.Frame(self, relief='raised', borderwidth=2)
        tkinter.Label(rhythm_frame, text="Rhythm patterns:").pack(
            side=tkinter.LEFT, padx=20, pady=20)
        self.rhythmboxes = [
            MyCombobox(rhythm_frame, values=self.rhythmlist, initial='c',
                       width=14, validate=self.validate_rhythm,
                       command=self.master.restart, addnewvalue=True),
            MyCombobox(rhythm_frame, values=self.rhythmlist, initial='',
                       width=8, validate=self.validate_rhythm,
                       command=self.master.restart, addnewvalue=True),
            MyCombobox(rhythm_frame, values=self.rhythmlist, initial='',
                       width=8, validate=self.validate_rhythm,
                       command=self.master.restart, addnewvalue=True),
        ]
        for rb in self.rhythmboxes:
            rb.pack(side=tkinter.LEFT, padx=10)
        rhythm_frame.pack(fill='x')

    def validate_limits(self):
        try:
            self.limits = [takt.Pitch(self.lowlimitbox.get()),
                           takt.Pitch(self.highlimitbox.get())]
        except ValueError:
            return False
        self.limits.sort()
        return True

    def validate_scale(self):
        try:
            self.scale = takt.Scale(takt.Pitch(self.scalerootbox.get()),
                                    self.scaletypebox.get())
        except ValueError:
            return False
        return True

    def validate_rhythm(self):
        try:
            self.rhythms = [takt.safe_mml(rb.get()).evlist()
                            for rb in self.rhythmboxes]
        except takt.MMLError:
            return False
        return True

    def validate_all(self):
        return self.validate_limits() and self.validate_scale() and \
            self.validate_rhythm()

    def getscore(self):
        self.validate_all()
        tonenum_range = (math.ceil(self.scale.tonenum(self.limits[0])),
                         math.floor(self.scale.tonenum(self.limits[1])) + 1)
        if self.randtype.get() == 'uniform':
            pitch_stream = (self.scale[random.randrange(*tonenum_range)]
                            for _ in itertools.count())
        elif self.randtype.get() == 'Gaussian':
            pitch_stream = (
                self.scale[int(random.gauss(
                    (tonenum_range[0]+tonenum_range[1])/2,
                    sigma=(tonenum_range[1]-tonenum_range[0])/2/3))]
                for _ in itertools.count())
        elif self.randtype.get() == '1/f':
            rng = Rand1OverF(ndice=3)
            pitch_stream = (self.scale[rng.randrange(*tonenum_range)]
                            for _ in itertools.count())
        elif self.randtype.get() == 'shuffle':
            ps = self.scale.pitches(self.limits[0], self.limits[1])
            pitch_stream = itertools.chain.from_iterable(
                random.sample(ps, len(ps)) for _ in itertools.count())
        elif self.randtype.get() == 'shuffle-repeat':
            ps = self.scale.pitches(self.limits[0], self.limits[1])
            shuffled = random.sample(ps, len(ps))
            pitch_stream = itertools.chain.from_iterable(
                shuffled for _ in itertools.count())

        zipped_lists = []
        for evlist in self.rhythms:
            notes = evlist.Filter(takt.NoteEvent)
            ctrls = takt.EventList(evlist.Reject(takt.NoteEvent), duration=0)
            if notes:
                t1list = [ev.t for ev in notes]
                # t2list is a list of the next event's time for each event
                t2list = t1list[1:] + [notes.duration]
                ctllist = [ctrls] + [takt.empty() for _ in range(len(notes)-1)]
                zipped_lists.append(list(zip(t1list, t2list, notes, ctllist)))
        if not zipped_lists:
            return takt.EventList()
        rhythm_stream = itertools.chain.from_iterable(
            random.choice(zipped_lists) for _ in itertools.count())
        return takt.genseq(
            ctrls + takt.note(n, ev.L, step=t2-t1, v=ev.v,
                              du=ev.get_du(), dt=ev.dt, ch=ev.ch)
            for n, (t1, t2, ev, ctrls) in zip(pitch_stream, rhythm_stream))


class GUIMain(tkinter.Frame):
    def __init__(self, master):
        self.master = master
        self.state = 'stopped'
        self.tempo = tkinter.IntVar(value=125)
        super().__init__(master)
        self.create_widgets()
        self.master.protocol("WM_DELETE_WINDOW", lambda: self.quit())
        self.pack()

    def create_widgets(self):
        self.stream1 = RandomStream(self)
        self.stream1.pack()

        tempo_frame = tkinter.Frame(self, relief='raised', borderwidth=2)
        tkinter.Label(tempo_frame, text="Tempo:").pack(
            side=tkinter.LEFT, padx=20, pady=20)
        tkinter.Scale(tempo_frame, var=self.tempo, from_=40, to=400,
                      orient='horizontal', length=300, width=20,
                      command=self.settempo).pack(side=tkinter.LEFT, padx=10)
        tempo_frame.pack(fill='x')

        button_frame = tkinter.Frame(self, relief='raised', borderwidth=2)
        tkinter.Button(button_frame, text='Play', command=self.play).pack(
            side=tkinter.LEFT, expand=True)
        tkinter.Button(button_frame, text='Stop', command=self.stop).pack(
            side=tkinter.LEFT, expand=True)
        button_frame.pack(fill='x')

    def play(self):
        if self.state == 'playing':
            midiio.stop()
        self.state = 'playing'
        midiio.play(self.stream1.getscore(),
                    callback=lambda ev: self.callback(ev))

    def stop(self):
        midiio.stop()
        self.state = 'stopped'

    def restart(self):
        if self.state == 'playing':
            self.play()

    def settempo(self, val):
        takt.set_tempo(int(val))

    def callback(self, ev):
        self.master.update()
        # convert GUI_UPDATE_PERIOD (msec) to ticks, to make the callback
        # function called at nearly equal interval independent of the tempo.
        ticks = GUI_UPDATE_PERIOD * takt.current_tempo() \
            / 60000 * takt.TICKS_PER_QUARTER
        ev.t += ticks
        midiio.queue_event(ev)

    def quit(self):
        midiio.stop()
        self.master.destroy()


root_window = tkinter.Tk()
root_window.option_add("*Font", ('TkDefaultFont', 18))
root_window.title("Pytakt Demo - Random Stream Generator")
gui = GUIMain(root_window)
root_window.mainloop()
