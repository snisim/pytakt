#
# Realtime harmonizer
#
from pytakt import *
from pytakt.midiio import *
import tkinter
from tkinter import ttk
from tkinter.messagebox import showerror


GUI_UPDATE_PERIOD = 50  # milliseconds
MAXNOTES = 8


class GUIMain(tkinter.Frame):
    def __init__(self, master):
        self.master = master
        self.scaleroot = tkinter.StringVar(value='C')
        self.scaletype = tkinter.StringVar(value='Major')
        self.scale = Scale(C4, 'major')
        self.scalelist = ['Major', 'NaturalMinor', 'MelodicMinor',
                          'HarmonicMinor', 'Chromatic', 'Wholetone',
                          'DiminishedWH', 'DiminishedHW', 'Pentatonic']
        self.degrees = [tkinter.IntVar() for i in range(MAXNOTES)]
        self.degrees[0].set(3)
        self.degrees[1].set(5)
        self.arpeggio = tkinter.IntVar(value=0)
        self.crescendo = tkinter.IntVar(value=0)
        self.echoback = tkinter.BooleanVar()
        self.quitted = False
        super().__init__(master)
        self.create_widgets()
        self.master.protocol("WM_DELETE_WINDOW", lambda: self.quit())
        self.pack()

    def create_widgets(self):
        scale_frame = tkinter.Frame(self, relief='raised', borderwidth=2)
        tkinter.Label(scale_frame, text="Scale:").pack(
            side=tkinter.LEFT, padx=20, pady=20)
        scaleroot_box = ttk.Combobox(
            scale_frame, values=[Pitch(p).tostr(sfn='#b', octave=False)
                                 for p in range(C4, C5)],
            textvariable=self.scaleroot, width=3)
        scaleroot_box.bind('<Return>', lambda _: self.set_scale())
        scaleroot_box.bind('<<ComboboxSelected>>', lambda _: self.set_scale())
        scaleroot_box.pack(side=tkinter.LEFT, padx=10)
        scaletype_box = ttk.Combobox(scale_frame, values=self.scalelist,
                                     textvariable=self.scaletype, width=14)
        scaletype_box.bind('<Return>', lambda _: self.set_scale())
        scaletype_box.bind('<<ComboboxSelected>>', lambda _: self.set_scale())
        scaletype_box.pack(side=tkinter.LEFT, padx=10)
        self.scaletype_box = scaletype_box
        scale_frame.pack(fill='x')

        degrees_frame = tkinter.Frame(self, relief='raised', borderwidth=2)
        tkinter.Label(degrees_frame, text="Degrees:").pack(
            side=tkinter.LEFT, padx=20)
        for i in range(MAXNOTES):
            tkinter.Spinbox(degrees_frame, from_=-15, to=15, increment=1,
                            width=3, justify=tkinter.RIGHT,
                            textvariable=self.degrees[i]).pack(
                                side=tkinter.LEFT, padx=10, pady=20)
        degrees_frame.pack(fill='x')

        arpeggio_frame = tkinter.Frame(self, relief='raised', borderwidth=2)
        tkinter.Label(arpeggio_frame, text="Arpeggio:").pack(
            side=tkinter.LEFT, padx=20, pady=20)
        tkinter.Scale(arpeggio_frame, var=self.arpeggio, from_=0, to=500,
                      resolution=5, orient='horizontal', length=300,
                      width=20).pack(side=tkinter.LEFT)
        tkinter.Label(arpeggio_frame, text="(msec)").pack(
            side=tkinter.LEFT, padx=10)
        arpeggio_frame.pack(fill='x')

        crescendo_frame = tkinter.Frame(self, relief='raised', borderwidth=2)
        tkinter.Label(crescendo_frame, text="Crescendo:").pack(
            side=tkinter.LEFT, padx=20, pady=20)
        tkinter.Scale(crescendo_frame, var=self.crescendo, from_=-30, to=30,
                      orient='horizontal', length=300, width=20).pack(
                          side=tkinter.LEFT)
        crescendo_frame.pack(fill='x')

        echoback_frame = tkinter.Frame(self, relief='raised', borderwidth=2)
        tkinter.Label(echoback_frame, text="Output original notes:").pack(
            side=tkinter.LEFT, padx=20, pady=20)
        tkinter.Checkbutton(echoback_frame, variable=self.echoback).pack(
            side=tkinter.LEFT)
        echoback_frame.pack(fill='x')

    def set_scale(self):
        scroot = self.scaleroot.get()
        sctype = self.scaletype.get()
        try:
            self.scale = Scale(Pitch(scroot), sctype)
        except ValueError:
            showerror("Error", f'Bad scale name "{scroot} {sctype}"')

    def quit(self):
        stop()
        self.master.destroy()
        self.quitted = True


open_input_device()
open_output_device()

root_window = tkinter.Tk()
root_window.option_add("*Font", ('TkDefaultFont', 18))
root_window.title("Pytakt Demo - Realtime Harmonizer")
gui = GUIMain(root_window)

# This application does not use mainloop() - instead, update() is called
# at regular intervals using the loopback event below.
update_event = LoopBackEvent(current_time(), 'update')
queue_event(update_event)

# main loop
while True:
    ev = recv_event()  # Receive an event from the MIDI input
    if isinstance(ev, NoteEventClass):
        delay = 0
        add_velocity = 0
        # Output a transposed event for each of the specified degrees
        for deg in gui.degrees:
            if gui.echoback.get():
                queue_event(ev)
            delay += gui.arpeggio.get()
            add_velocity += gui.crescendo.get()
            if deg.get() != 0:
                tev = Transpose(DEG(deg.get()), gui.scale)(ev)
                tev.t += delay
                if isinstance(ev, NoteOnEvent):
                    tev.v = max(min(tev.v + add_velocity, 127), 1)
                queue_event(tev)
    elif isinstance(ev, LoopBackEvent):
        root_window.update()
        if gui.quitted:
            break
        ev.t += GUI_UPDATE_PERIOD
        queue_event(ev)
