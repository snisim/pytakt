#
# Bach's Invention in C major and more
#

import pytakt as takt
import tkinter
from tkinter import ttk
from tkinter.messagebox import showerror
import subprocess
import os
import sys
from pathlib import Path


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


class GUIMain(tkinter.Frame):
    def __init__(self, master):
        self.master = master
        self.motivelist = ["L16 cdefdec",
                           "L16 cde{fededc}*/3",
                           "L16 r/c/d.e/f.d/e.c/",
                           "L16 cdefedc",
                           "L16 cdefgab",
                           "L16 bagfedc",
                           "L16 gfededc",
                           "L16 gggfedc",
                           "L16 {cdedce}/fdec",
                           "L16 {cdedeg}/f.d/e.c/",
                           "L8 {cdefgab}./7^c/{bagfedc}./7",
                           "L16 [{cdefdec} {c~~_b~c~}]",
                           "L16 [{cdefdec} {c_bcr_f_g_a}]"]
        super().__init__(master)
        self.create_widgets()
        self.pack()

    def create_widgets(self):
        tkinter.Label(self, text="Motive:").pack(
            side=tkinter.LEFT, padx=20, pady=20)
        self.motivebox = MyCombobox(
            self, values=self.motivelist, initial="L16 cdefdec",
            width=30, validate=self.validate_motive, addnewvalue=True,
            command=lambda: None)
        self.motivebox.pack(side=tkinter.LEFT, padx=10)
        tkinter.Button(self, text='Open',
                       command=lambda: self.run_subprocess()).pack(
                           side=tkinter.LEFT, padx=20)

    def validate_motive(self):
        try:
            takt.safe_mml(self.motivebox.get())
        except takt.MMLError:
            return False
        return True

    def run_subprocess(self):
        os.environ['PYTAKT_MOTIVE'] = self.motivebox.get()
        subprocess.Popen(
            [sys.executable, Path(__file__).parent / "invention1.py", 'show'])


root_window = tkinter.Tk()
root_window.option_add("*Font", ('TkDefaultFont', 18))
root_window.title("Pytakt Demo - Bach's Invention in C major and more")
gui = GUIMain(root_window)
root_window.mainloop()
