# coding:utf-8
"""
このモジュールにはピアノロールビューアのための関数が定義されています。
"""
# Copyright (C) 2023  Satoshi Nishimura

import tkinter
import tkinter.simpledialog
import math
import sys
import os
from takt.score import EventList
from takt.event import NoteEventClass, NoteEvent, NoteOnEvent, NoteOffEvent, \
    MetaEvent, CtrlEvent, TempoEvent, KeyPressureEvent, SysExEvent
from takt.constants import M_TRACKNAME, M_INSTNAME, \
    CONTROLLERS, C_BEND, C_PROG, C_KPR, C_CPR, C_TEMPO, TICKS_PER_QUARTER
from takt.pitch import Pitch
from takt.timemap import TimeSignatureMap, current_tempo
from takt.utils import std_time_repr
from takt.effector import Render
import takt.midiio as midiio

__all__ = ['show']


FONT_FAMILY = 'Helvetica' if sys.platform == 'win32' else 'TkDefaultFont'
MAGNIFY = float(os.environ.get('PYTAKT_MAGNIFY', "1.0"))
GEOMETRY = os.environ.get('PYTAKT_GEOMETRY')


def setup_globals(mag):
    globals().update(
        PIXELS_PER_QUARTER_NOTE=round(50 * mag),
        PIXELS_PER_NOTE_NUM=round(10 * mag),
        VIEW_WIDTH=round(1400 * mag),
        # NOTE_PANE_VIEW_HEIGHT=PIXELS_PER_NOTE_NUM * 88
        NOTE_PANE_VIEW_HEIGHT=round(10 * mag) * 88,
        CTRL_PANE_VIEW_HEIGHT=round(120 * mag),
        CTRL_PANE_YMARGIN=round(10 * mag),
        CTRL_THICKNESS=round(2 * mag),
        MSG_FONT=(FONT_FAMILY, round(13 * mag)),
        # WindowsではSCROLLBAR_WIDTHを11未満にすると矢印が不自然になる。
        SCROLLBAR_WIDTH=max(round(12 * mag),
                            11 if sys.platform == 'win32' else 0),
        YRULER_WIDTH=round(80 * mag),
        YRULER_FONT=(FONT_FAMILY, round(12 * mag)),
        YRULER_FONT_S=(FONT_FAMILY, round(10 * mag)),
        XRULER_HEIGHT=round(24 * mag),
        XRULER_FONT=(FONT_FAMILY, round(12 * mag)),
        PANE_BORDER_WIDTH=round(2 * mag),
        ZOOM_RATE=1.25,
        SNAP_PIXELS=round(5 * mag),
        CURSOR_UPDATE_PERIOD=30,
        XRULER_CURSOR_WIDTH=round(6 * mag),
        CLOSE_BUTTON_SIZE=round(20 * mag),
        CLOSE_BUTTON_LINE_WIDTH=round(1 * mag),
        AUTO_SCROLL_THRES=0.8,
        MAX_TRACK_BUTTONS=30,
        TRACK_BUTTON_FONT=(FONT_FAMILY, round(13 * mag)),
        TEMPO_SCALE_SPINBOX_FONT=(FONT_FAMILY, round(16 * mag)),
        MAX_TEMPO_SCALE=5.0,
        MIN_TEMPO_SCALE=0.1,
        TEMPO_SCALE_STEP=0.1,
        PLAY_BUTTON_WIDTH=round(35 * mag),
        BUTTON_BORDER=round(4 * mag),
        SHOW_LIMIT=5e5,
        MENU_FONT=(FONT_FAMILY, round(12 * mag)),
        CL_BACK='gray90',
        CL_HLINE='gray60',
        CL_HBAND='gray85',
        CL_VLINE='gray50',
        CL_VLINE_DASHED='gray70',
        CL_VLINE_ORG='gray20',
        CL_BLACKKEY='gray20',
        CL_OUTLINE='gray20',
        TRACK_COLORS=('gray60', '#B09060', 'red1', 'orange1', 'yellow1',
                      'green1', 'cyan1', 'magenta1', 'gray75', 'gray95',
                      '#8080F0', 'pink', 'red3', 'orange3', 'yellow3',
                      'green3', 'cyan3', 'magenta3', 'gray70', 'gray90'),
        CURSOR_COLORS=('green', 'red', 'red'))


setup_globals(1)


HSCROLL_BY_VWHEEL = 'vertical'  # 1, -1, 0, or 'vertical'
if sys.platform == 'darwin':
    HSCROLL_BY_VWHEEL = 0
elif sys.platform == 'win32':
    HSCROLL_BY_VWHEEL = -1


RIGHTBUTTON = '<Button-2>' if sys.platform == 'darwin' else '<Button-3>'


class ViewPaneBase(tkinter.Frame):
    def __init__(self, master, height, viewheight,
                 ymargin=0, no_yscroll=False):
        super().__init__(master, borderwidth=PANE_BORDER_WIDTH,
                         relief=tkinter.RIDGE, background='black')
        self.master = master
        self.pixels_per_tick = master.pixels_per_tick
        self.width = master.evlist.duration * master.pixels_per_tick
        self.height = height
        self.ymargin = ymargin
        self.yzoom = 1.0
        self.create_widgets(master.viewwidth, viewheight, no_yscroll)
        self.master.panelist.append(self)
        self.draw()
        self.bind_actions()
        master.xscroll.config(command=lambda *args: self.xview_all(*args))

    def create_widgets(self, viewwidth, viewheight, no_yscroll):
        if no_yscroll:
            self.yscroll = DummyScrollbar(self, width=SCROLLBAR_WIDTH)
        else:
            self.yscroll = tkinter.Scrollbar(self, orient=tkinter.VERTICAL,
                                             width=SCROLLBAR_WIDTH)
        self.canvas = tkinter.Canvas(self, width=viewwidth, height=viewheight,
                                     highlightthickness=0, background=CL_BACK,
                                     xscrollcommand=self.master.xscroll.set,
                                     yscrollcommand=self.yscroll.set)
        self.yruler = tkinter.Canvas(self, width=YRULER_WIDTH,
                                     highlightthickness=0, background=CL_BACK,
                                     height=viewheight,
                                     yscrollcommand=self.yscroll.set)
        self.yscroll.config(command=lambda *args: self.yview(*args))
        self.yscroll.pack(side=tkinter.RIGHT, fill='y')
        self.yruler.pack(side=tkinter.LEFT, fill='y')
        self.canvas.pack(expand=1, fill='both')

    def set_scrollregion(self):
        self.canvas.config(scrollregion=(0, 0, self.width * self.master.xzoom,
                                         self.height * self.yzoom))
        self.yruler.config(scrollregion=(0, 0, YRULER_WIDTH,
                                         self.height * self.yzoom))

    def destroy(self):
        self.master.panelist.remove(self)
        super().destroy()

    def xview_all(self, *args):
        for pane in self.master.panelist:
            rtn = pane.canvas.xview(*args)
        return rtn

    def xview_scroll_all(self, *args):
        for pane in self.master.panelist:
            pane.canvas.xview_scroll(*args)

    def xview_moveto_all(self, *args):
        for pane in self.master.panelist:
            pane.canvas.xview_moveto(*args)

    def yview(self, *args):
        self.canvas.yview(*args)
        return self.yruler.yview(*args)

    def yview_scroll(self, *args):
        self.canvas.yview_scroll(*args)
        self.yruler.yview_scroll(*args)

    def yview_moveto(self, *args):
        self.canvas.yview_moveto(*args)
        self.yruler.yview_moveto(*args)

    def horiz_zoom(self, center, zoom):
        # center (デバイス座標, pixel単位) を中心にしてズームする
        wc_center = self.canvas.canvasx(center) / self.master.xzoom
        self.master.xzoom *= zoom
        moveto = max(0, wc_center - center / self.master.xzoom) / self.width
        for pane in self.master.panelist:
            pane.set_scrollregion()
            pane.canvas.scale('all', 0, 0, zoom, 1)
            pane.canvas.xview_moveto(moveto)

    def vert_zoom(self, center, zoom):
        wc_center = self.canvas.canvasy(center) / self.yzoom
        self.yzoom *= zoom
        moveto = max(0, wc_center - center / self.yzoom) / self.height
        self.set_scrollregion()
        self.canvas.scale('all', 0, 0, 1, zoom)
        self.yruler.scale('all', 0, 0, 1, zoom)
        self.yview_moveto(moveto)

    def button1_press(self, tkevent):
        self.button1coord = {'x': self.canvas.canvasx(tkevent.x),
                             'y': self.canvas.canvasy(tkevent.y)}

    def button1_xmotion(self, tkevent):
        if hasattr(self, 'button1coord'):
            self.xview_moveto_all((self.button1coord['x'] - tkevent.x) /
                                  (self.width * self.master.xzoom))

    def button1_ymotion(self, tkevent):
        if hasattr(self, 'button1coord'):
            self.yview_moveto((self.button1coord['y'] - tkevent.y) /
                              (self.height * self.yzoom))

    def shift_button1_motion(self, tkevent):
        self.button1_xmotion(tkevent)
        self.button1_ymotion(tkevent)

    def scroll_by_vwheel(self, direction):
        if HSCROLL_BY_VWHEEL == 'vertical':
            self.yview_scroll(-direction, 'units')
        else:
            self.xview_scroll_all(HSCROLL_BY_VWHEEL * direction, 'units')

    def scroll_by_button4567(self, tkevent, axis):
        if axis == 'x':
            if tkevent.num == 6 or tkevent.num == 4 and tkevent.state & 1:
                self.xview_scroll_all(-1, 'units')
            elif tkevent.num == 7 or tkevent.num == 5 and tkevent.state & 1:
                self.xview_scroll_all(1, 'units')
            elif tkevent.num == 4:
                self.scroll_by_vwheel(1)
            elif tkevent.num == 5:
                self.scroll_by_vwheel(-1)
        else:
            if tkevent.num == 4:
                self.yview_scroll(-1, 'units')
            elif tkevent.num == 5:
                self.yview_scroll(1, 'units')

    def viewportx(self, screenx):
        return max(0, min(self.canvas.winfo_width(),
                          screenx - self.canvas.winfo_rootx()))

    def viewporty(self, screeny):
        return max(0, min(self.canvas.winfo_height(),
                          screeny - self.canvas.winfo_rooty()))

    def zoom_in(self, pointerx, pointery, axis='xy'):
        if 'x' in axis:
            self.horiz_zoom(self.viewportx(pointerx), ZOOM_RATE)
        if 'y' in axis:
            self.vert_zoom(self.viewporty(pointery), ZOOM_RATE)

    def zoom_out(self, pointerx, pointery, axis='xy'):
        if 'x' in axis:
            self.horiz_zoom(self.viewportx(pointerx), 1 / ZOOM_RATE)
        if 'y' in axis:
            self.vert_zoom(self.viewporty(pointery), 1 / ZOOM_RATE)

    def reset_zoom(self, pointerx):
        self.horiz_zoom(self.viewportx(pointerx), 1 / self.master.xzoom)
        for pane in self.master.panelist:
            pane.vert_zoom(0, 1 / pane.yzoom)
            if isinstance(pane, NoteViewPane):
                pane.ycenter()

    def bind_actions(self):
        self.bind("<Right>", lambda e: self.xview_scroll_all(1, 'units'))
        self.bind("<Left>", lambda e: self.xview_scroll_all(-1, 'units'))
        self.bind("<Shift-Right>", lambda e: self.xview_scroll_all(1, 'pages'))
        self.bind("<Shift-Left>", lambda e: self.xview_scroll_all(-1, 'pages'))
        self.bind("<Home>", lambda e: self.xview_moveto_all(0))
        self.bind("<End>", lambda e: self.xview_moveto_all(1))
        self.bind("<Up>", lambda e: self.yview_scroll(-1, 'units'))
        self.bind("<Down>", lambda e: self.yview_scroll(1, 'units'))
        self.bind("<Shift-Up>", lambda e: self.yview_scroll(-1, 'pages'))
        self.bind("<Shift-Down>",
                  lambda e: self.canvas.yview_scroll(1, 'pages'))
        self.bind("<Enter>", lambda e: self.focus_set())
        self.bind("<Control-plus>",
                  lambda e: self.zoom_in(self.winfo_pointerx(),
                                         self.winfo_pointery()))
        self.bind("<Control-minus>",
                  lambda e: self.zoom_out(self.winfo_pointerx(),
                                          self.winfo_pointery()))
        self.bind("<Control-equal>",
                  lambda e: self.reset_zoom(self.winfo_pointerx()))
        c = self.canvas
        c.bind("<Button-1>", lambda e: self.button1_press(e))
        c.bind("<B1-Motion>", lambda e: self.button1_xmotion(e))
        c.bind("<Shift-B1-Motion>", lambda e: self.shift_button1_motion(e))
        c.bind("<Button>", lambda e: self.scroll_by_button4567(e, 'x'))
        # マウスホイールで発生するイベントは次のようである。
        #  .platform    垂直　　　　    水平
        #    win32   <MouseWheel>    なし
        #    cygwin  <Button-4/5>    <Shift-Button-4/5>
        #    darwin  <MouseWheel>    <Shift-MouseWheel>
        #    linux   <Button-4/5>    <Button-6/7>
        c.bind("<MouseWheel>",
               lambda e: self.scroll_by_vwheel(1 if e.delta > 0 else -1))
        c.bind("<Shift-MouseWheel>",
               lambda e: self.xview_scroll_all(-1, 'units') if e.delta > 0
               else self.xview_scroll_all(1, 'units'))
        c.bind("<Control-Button-4>",
               lambda e: self.zoom_in(e.x_root, e.y_root))
        c.bind("<Control-Button-5>",
               lambda e: self.zoom_out(e.x_root, e.y_root))
        c.bind("<Control-MouseWheel>",
               lambda e: self.zoom_in(e.x_root, e.y_root) if e.delta > 0
               else self.zoom_out(e.x_root, e.y_root))
        c.bind(RIGHTBUTTON,
               lambda e: self.master.menu_popup(self, e.x_root, e.y_root))
        self.yruler.bind("<Button-1>", lambda e: self.button1_press(e))
        self.yruler.bind("<B1-Motion>", lambda e: self.button1_ymotion(e))
        self.yruler.bind(RIGHTBUTTON, lambda e: self.master.menu_popup(
            self, e.x_root, e.y_root))
        self.yruler.bind("<Control-Button-4>",
                         lambda e: self.zoom_in(e.x_root, e.y_root, 'y'))
        self.yruler.bind("<Control-Button-5>",
                         lambda e: self.zoom_out(e.x_root, e.y_root, 'y'))
        self.yruler.bind("<Control-MouseWheel>",
                         lambda e: self.zoom_in(e.x_root, e.y_root, 'y')
                         if e.delta > 0
                         else self.zoom_out(e.x_root, e.y_root, 'y'))
        self.yruler.bind("<Button>",
                         lambda e: self.scroll_by_button4567(e, 'y'))
        self.yruler.bind("<MouseWheel>",
                         lambda e: self.yview_scroll(-1, 'units')
                         if e.delta > 0 else self.yview_scroll(1, 'units'))

    def draw(self):
        self.set_scrollregion()
        self.draw_vertical_lines()
        self.draw_cursors()
        self.canvas.create_line(0, 0, 0, 0, width=0, tag='sentinel')

    def draw_vertical_lines(self):
        h = self.height - self.ymargin
        first_meas = self.master.tsigmap.ticks2mbt(0)[0]
        for measure in range(first_meas,
                             first_meas + self.master.tsigmap.num_measures()):
            time = self.master.tsigmap.mbt2ticks(measure)
            x = time * self.pixels_per_tick
            self.canvas.create_line(x, self.ymargin, x, h, fill=CL_VLINE)
            tsig = self.master.tsigmap.timesig_at(time)
            measlen = self.master.tsigmap.mbt2ticks(measure + 1) - time
            for beat in range(1, tsig.numerator()):
                x1 = x + (beat * tsig.beat_length() * self.pixels_per_tick)
                if x1 > self.width or beat * tsig.beat_length() >= measlen:
                    break
                self.canvas.create_line(x1, self.ymargin, x1, h,
                                        fill=CL_VLINE_DASHED, dash=(2, 2))
        self.canvas.create_line(self.width, self.ymargin, self.width, h,
                                fill=CL_VLINE, width=2)

    def draw_cursors(self):
        for i in range(3):
            w = XRULER_CURSOR_WIDTH if isinstance(self, XRulerPane) else 2
            self.canvas.create_line(0, 0, 0, self.height,
                                    fill=CURSOR_COLORS[i], width=w,
                                    tag=('cursor%d' % i),
                                    dash=(2, 2) if i == 1 and w <= 2 else ())
        self.update_cursors()

    def update_cursors(self, playingpos_only=False):
        for i, t in enumerate((self.master.playingpos,
                               self.master.playstart_tmp,
                               self.master.playstart)):
            if i == 0 or not playingpos_only:
                for pane in self.master.panelist:
                    pane.canvas.itemconfig('cursor%d' % i,
                                           state='hidden' if t is None
                                           else 'normal')
                if t is not None:
                    xnew = t * self.master.xzoom * self.pixels_per_tick
                    for pane in self.master.panelist:
                        xold = pane.canvas.coords('cursor%d' % i)[0]
                        pane.canvas.move('cursor%d' % i, xnew - xold, 0)

    def item_enter_action(self, item, ev):
        self.master.msgpane.showmsg(0, ev.org_repr if hasattr(ev, 'org_repr')
                                    else str(ev))
        self.current_ev = ev
        if hasattr(ev, 'n'):
            self.master.msgpane.showmsg(1, repr(Pitch(ev.n)))
        for pane in self.master.panelist:
            if hasattr(pane, 'emphasize_item'):
                pane.emphasize_item('id%x' % id(ev))
        # 重なっているitemをすべて探して、トラック番号リストを求める。
        x1 = ev.t * self.pixels_per_tick * self.master.xzoom
        if isinstance(self, CtrlEventViewPane):
            x2 = x1
            y = self.gety(ev.value) * self.yzoom
        else:
            if isinstance(self, NoteViewPane):
                y = (self.height - 1 -
                     (ev.n + 0.5) * self.pixels_per_notenum) * self.yzoom
                x1 += 1
                x2 = ((ev.t + ev.L) * self.pixels_per_tick *
                      self.master.xzoom) - 1
            elif isinstance(self, VelocityViewPane):
                y = self.gety(ev.v) * self.yzoom
                x1 += 1
                x2 = x1
        items = self.canvas.find('overlapping', x1, y, x2, y)
        items = [item for item in items
                 if 'note' in self.canvas.gettags(item) or
                 'ctrl' in self.canvas.gettags(item)]
        # gettagsの中でtk%dのタグを見つけ、トラック番号のリストを作成
        tracks = [next(int(tg[2:])
                       for tg in self.canvas.gettags(item) if tg[:2] == 'tk')
                  for item in items]
        try:
            tracks.remove(ev.tk)
        except ValueError:
            pass
        # 重複したトラック番号の除去
        tracks = sorted(set(tracks))
        tracks.insert(0, ev.tk)
        self.master.msgpane.showtrack(tracks)

    def item_leave_action(self):
        self.master.msgpane.clear()
        tags = self.canvas.gettags('current')
        idtag = next(tg for tg in tags if tg[:2] == 'id')
        for pane in self.master.panelist:
            if hasattr(pane, 'deemphasize_item'):
                pane.deemphasize_item(idtag)

    def sound_note_on_click(self, release=False):
        if hasattr(self, 'current_ev') and \
           isinstance(self.current_ev, NoteEvent):
            ev = self.current_ev
            midiio.queue_event(NoteOnEvent(ev.t, ev.n, ev.v, ev.tk, ev.ch)
                               if not release else
                               NoteOffEvent(ev.t, ev.n, ev.nv, ev.tk, ev.ch),
                               midiio.current_time())

    def item_press_action(self):
        tags = self.canvas.gettags('current')
        for pane in self.master.panelist:
            pane.canvas.tkraise(next(tg for tg in tags if tg[:2] == 'tk'))
            pane.canvas.tkraise(next(tg for tg in tags if tg[:2] == 'id'))
        self.sound_note_on_click()

    def item_release_action(self):
        self.sound_note_on_click(release=True)

    def item_shift_press_action(self):
        tags = self.canvas.gettags('current')
        for pane in self.master.panelist:
            # 下の raise は実際は lower の意味
            pane.canvas.tkraise(next(tg for tg in tags if tg[:2] == 'id'),
                                'sentinel')
            pane.canvas.tkraise(next(tg for tg in tags if tg[:2] == 'tk'),
                                'sentinel')
        self.sound_note_on_click()

    def item_shift_release_action(self):
        self.sound_note_on_click(release=True)

    def item_ctrl_click_action(self):
        tags = self.canvas.gettags('current')
        tk = int(next(tg for tg in tags if tg[:2] == 'tk')[2:])
        self.master.trackbuttonpane.button_click_action(tk)

    def bind_item_actions(self, item, ev):
        self.canvas.tag_bind(item, "<Enter>", lambda e:
                             self.item_enter_action(item, ev))

    def bind_common_item_actions(self, item):
        self.canvas.tag_bind(item, "<Leave>",
                             lambda e: self.item_leave_action())
        self.canvas.tag_bind(item, "<ButtonPress-1>",
                             lambda e: self.item_press_action())
        self.canvas.tag_bind(item, "<ButtonRelease-1>",
                             lambda e: self.item_release_action())
        self.canvas.tag_bind(item, "<Shift-ButtonPress-1>",
                             lambda e: self.item_shift_press_action())
        self.canvas.tag_bind(item, "<Shift-ButtonRelease-1>",
                             lambda e: self.item_shift_release_action())
        self.canvas.tag_bind(item, "<Control-Button-1>",
                             lambda e: self.item_ctrl_click_action())


class NoteViewPane(ViewPaneBase):
    def __init__(self, master, viewheight):
        self.pixels_per_notenum = master.pixels_per_notenum
        super().__init__(master, self.pixels_per_notenum * 128, viewheight)
        # side=BOTTOMとして逆順にpackするのは、ウィンドウを縮小したときに、
        # 他のpaneの高さをキープしてNoteViewPaneだけを縮小するため。
        self.pack(expand=1, side=tkinter.BOTTOM, fill='both')

    def ycenter(self):
        self.yview_moveto(63 / 128 - self.canvas.winfo_height() * 0.5
                          / (self.height * self.yzoom))  # to display A0-C8

    def draw(self):
        self.draw_horizontal_lines()
        super().draw()
        self.draw_yruler()
        self.draw_notes()

    def draw_horizontal_lines(self):
        w = self.width
        for y in range(0, 128):
            y1 = self.height - 1 - y * self.pixels_per_notenum
            y2 = self.height - 1 - (y + 1) * self.pixels_per_notenum
            if y % 12 in (0, 5):
                self.canvas.create_line(0, y1, w, y1, fill=CL_HLINE,
                                        width=3 if y % 2 == 0 else 1)
            elif y % 12 in (1, 3, 6, 8, 10):
                self.canvas.create_rectangle(0, y1, w, y2, fill=CL_HBAND,
                                             width=0)

    def draw_yruler(self):
        w = YRULER_WIDTH
        self.yruler.create_line(w - 1, 0, w - 1, self.height,
                                fill=CL_VLINE_ORG)
        for y in reversed(range(0, 128)):
            y1 = self.height - 1 - y * self.pixels_per_notenum
            y2 = self.height - 1 - (y + 1) * self.pixels_per_notenum
            if y % 12 == 0:
                self.yruler.create_line(0, y1, w, y1, fill=CL_HLINE, width=2)
                self.yruler.create_text(w - 1, y1 + 2, font=YRULER_FONT,
                                        text=Pitch(y).tostr(), anchor='se')
                self.yruler.create_text(w / 2, y1, text='%d' % y,
                                        font=YRULER_FONT_S,
                                        fill='blue', anchor='s')
            elif y % 12 == 5:
                self.yruler.create_line(0, y1, w, y1, fill=CL_HLINE)
            elif y % 12 in (1, 3, 6, 8, 10):
                ym = (y1 + y2 - 1) / 2
                ym = math.floor(ym) if y % 12 in (1, 6) else math.ceil(ym)
                self.yruler.create_line(0, ym, w, ym, fill=CL_HLINE)
                self.yruler.create_rectangle(0, y1, w / 2, y2,
                                             fill=CL_BLACKKEY, width=0)

    def draw_notes(self):
        # 重なった表示が自然になるようにトラック番号を第１キーとしてでソート
        for ev in sorted(self.master.evlist, key=lambda ev: (ev.tk, ev.t)):
            if isinstance(ev, NoteEvent):
                self.draw_note(ev)
        self.bind_common_item_actions('note')

    def draw_note(self, ev):
        y1 = self.height - 1 - ev.n * self.pixels_per_notenum
        y2 = self.height - 1 - (ev.n + 1) * self.pixels_per_notenum
        x1 = ev.t * self.pixels_per_tick
        x2 = (ev.t + ev.L) * self.pixels_per_tick
        color = TRACK_COLORS[ev.tk % len(TRACK_COLORS)]
#        stipple = TRACK_STIPPLES[(ev.tk // len(TRACK_COLORS))
#                                 % len(TRACK_STIPPLES)]
        rect = self.canvas.create_polygon(
            x1, y1, x1, y2-2, min(x1+2, x2), y2-2, min(x1+4, x2), y2,
            x2, y2, x2, y1, fill=color, width=1, outline=CL_OUTLINE,
            tags=('note', 'tk%d' % ev.tk, 'id%x' % id(ev)))
#        rect = self.canvas.create_rectangle(
#            x1, y1, x2, y2, fill=color, width=1, outline=CL_OUTLINE,
#            tags=('note', 'tk%d' % ev.tk, 'id%x' % id(ev)))
        self.bind_item_actions(rect, ev)

    def emphasize_item(self, item):
        self.canvas.itemconfigure(item, outline='black', width=3)

    def deemphasize_item(self, item):
        self.canvas.itemconfigure(item, outline=CL_OUTLINE, width=1)


class CtrlViewPaneBase(ViewPaneBase):
    def __init__(self, master, ctrlnum, viewheight, title,
                 low, high, majorstep, minorstep):
        self.ctrlnum = ctrlnum
        self.title = title
        self.low, self.high = low, high
        self.majorstep, self.minorstep = majorstep, minorstep
        super().__init__(master, viewheight, viewheight,
                         ymargin=CTRL_PANE_YMARGIN)
        self.canvas.scale('all', 0, 0, self.master.xzoom, 1)
        self.pack(before=self.master.panelist[-2],
                  side=tkinter.BOTTOM, fill='x')
        self.canvas.xview_moveto(self.master.xscroll.get()[0])

    def create_widgets(self, viewwidth, viewheight, no_yscroll):
        super().create_widgets(viewwidth, viewheight, no_yscroll)
        self.pane_close_button = tkinter.Canvas(
            self, width=CLOSE_BUTTON_SIZE, height=CLOSE_BUTTON_SIZE,
            background=CL_BACK)
        self.pane_close_button.place(x=0, y=0)

    def bind_actions(self):
        super().bind_actions()
        self.bind("<Control-d>",
                  lambda e: self.master.close_ctrlpane(self.ctrlnum))
        self.pane_close_button.bind("<ButtonPress-1>", lambda e:
                                    self.master.close_ctrlpane(self.ctrlnum))

    def gety(self, value):
        return self.height - 1 - \
            ((self.height - CTRL_PANE_YMARGIN * 2) *
             (value - self.low) / (self.high - self.low) + CTRL_PANE_YMARGIN)

    def draw(self):
        self.draw_horizontal_lines()
        super().draw()
        self.draw_yruler()
        a, b = int(CLOSE_BUTTON_SIZE * 0.2), int(CLOSE_BUTTON_SIZE * 0.6)
        self.pane_close_button.create_line(
            a, a, a, b, b, b, b, a, a, a, b, b, a, b, b, a,
            fill=CL_VLINE_ORG, width=CLOSE_BUTTON_LINE_WIDTH)

    def draw_horizontal_lines(self):
        for i in range(-(self.low // -self.minorstep),
                       self.high // self.minorstep + 1):
            val = i * self.minorstep
            y = self.gety(val)
            self.canvas.create_line(
                0, y, self.width, y, fill=CL_HLINE,
                dash=(2, 2) if val % self.majorstep != 0 else ())
        for y in (self.gety(self.low), self.gety(self.high)):
            self.canvas.create_line(0, y, self.width, y, fill=CL_HLINE)

    def draw_yruler(self):
        self.yruler.create_line(YRULER_WIDTH - 1, 0, YRULER_WIDTH - 1,
                                self.height, fill=CL_VLINE_ORG)
        for i in range(-(self.low // -self.majorstep),
                       self.high // self.majorstep + 1):
            val = i * self.majorstep
            y = self.gety(val)
            self.yruler.create_text(YRULER_WIDTH - 3, y, font=YRULER_FONT_S,
                                    text="%g" % val, anchor='e')
        self.yruler.create_text(2, self.height / 2, font=YRULER_FONT_S,
                                text=self.title, anchor='w')

    def emphasize_item(self, item):
        self.canvas.itemconfigure(item, outline='black', width=3)

    def deemphasize_item(self, item):
        self.canvas.itemconfigure(item, outline=CL_OUTLINE, width=1)


class VelocityViewPane(CtrlViewPaneBase):
    def __init__(self, master, viewheight):
        super().__init__(master, -1, viewheight, "VELOC", 0, 127, 60, 20)

    def draw(self):
        super().draw()
        self.draw_notes()

    def draw_notes(self):
        for ev in sorted(self.master.evlist, key=lambda ev: (ev.tk, ev.t)):
            if isinstance(ev, NoteEvent):
                self.draw_note(ev)
        self.bind_common_item_actions('ctrl')

    def draw_note(self, ev):
        x1 = ev.t * self.pixels_per_tick
        x2 = (ev.t + ev.L) * self.pixels_per_tick
        y = self.gety(ev.v)
        color = TRACK_COLORS[ev.tk % len(TRACK_COLORS)]
        rect = self.canvas.create_rectangle(
            x1, y - CTRL_THICKNESS, x2, y + CTRL_THICKNESS,
            fill=color, outline=CL_OUTLINE,
            tags=('ctrl', 'tk%d' % ev.tk, 'id%x' % id(ev)))
#        circle = self.canvas.create_oval(
#            x1 - 3, y - 3, x1 + 3, y + 3,
#            fill=color, outline=CL_OUTLINE, width=1,
#            tags=('ctrl', 'head', 'tk%d' % ev.tk, 'id%x' % id(ev)))
        self.bind_item_actions(rect, ev)
#        self.bind_item_actions(circle, ev)


class CtrlEventViewPane(CtrlViewPaneBase):
    def __init__(self, master, viewheight, ctrlnum, title=None):
        if title is None:
            self.title = "#%d\n%.6s" % (ctrlnum,
                                        CONTROLLERS.get(ctrlnum, '')[2:])
        else:
            self.title = title
        if ctrlnum == C_BEND:
            param = (-8192, 8191, 4000, 2000)
        elif ctrlnum == C_TEMPO:
            param = (0, 240, 120, 40)
        else:
            param = (0, 127, 60, 20)
        super().__init__(master, ctrlnum, viewheight, self.title, *param)

    def draw(self):
        super().draw()
        self.draw_ctrl_events()

    def draw_ctrl_event(self, ev, until):
        x1 = ev.t * self.pixels_per_tick
        x2 = until * self.pixels_per_tick
        y = self.gety(ev.value)
        color = TRACK_COLORS[ev.tk % len(TRACK_COLORS)]
        # テンポイベントはTrack 0が非表示になっていても表示する
        htag = ('nohide',) if self.ctrlnum == C_TEMPO else ()
        rect = self.canvas.create_rectangle(
            x1, y - CTRL_THICKNESS, x2, y + CTRL_THICKNESS,
            fill=color, outline=CL_OUTLINE,
            tags=('ctrl', 'tk%d' % ev.tk, 'id%x' % id(ev), *htag))
#        circle = self.canvas.create_oval(
#            x1 - 3, y - 3, x1 + 3, y + 3,
#            fill=color, outline=CL_OUTLINE, width=1,
#            tags=('ctrl', 'head', 'tk%d' % ev.tk, 'id%x' % id(ev), *htag))
        self.bind_item_actions(rect, ev)
#        self.bind_item_actions(circle, ev)

    def draw_ctrl_events(self):
        event_dict = {}
        for ev in sorted(self.master.evlist, key=lambda ev: (ev.tk, ev.t)):
            if (isinstance(ev, CtrlEvent) and ev.ctrlnum == self.ctrlnum) or \
               (isinstance(ev, TempoEvent) and self.ctrlnum == C_TEMPO):
                if isinstance(ev, TempoEvent):
                    key = ()
                elif isinstance(ev, KeyPressureEvent):
                    key = (ev.tk, ev.ch, ev.n)
                else:
                    key = (ev.tk, ev.ch)
                prev = event_dict.get(key)
                if prev:
                    self.draw_ctrl_event(prev, ev.t)
                event_dict[key] = ev
        for ev in event_dict.values():
            self.draw_ctrl_event(ev, max(self.master.evlist.duration, ev.t))
        self.bind_common_item_actions('ctrl')


def get_tracklist(evlist):
    # イベントが全く無いトラックは None, イベントはあるが Track/Inst name が
    # ないトラックは空文字列になる。
    tracklist = []
    for ev in evlist:
        for i in range(len(tracklist), ev.tk + 1):
            tracklist.append(None)
        if tracklist[ev.tk] is None:
            tracklist[ev.tk] = ''
        if not tracklist[ev.tk] and \
           isinstance(ev, MetaEvent) and ev.mtype in (M_TRACKNAME, M_INSTNAME):
            tracklist[ev.tk] = ev.value
    return tracklist


class XRulerPane(ViewPaneBase):
    def __init__(self, master):
        super().__init__(master, XRULER_HEIGHT, XRULER_HEIGHT, no_yscroll=True)
        self.canvas.bind("<Motion>", lambda e: self.xr_motion_action(e, True))
        self.canvas.bind("<Shift-Motion>",
                         lambda e: self.xr_motion_action(e, False))
        self.canvas.bind("<Leave>", lambda e: self.xr_leave_action(e))
        self.canvas.bind("<Button-1>", lambda e: self.xr_button1_action(e))
        self.canvas.bind("<Shift-Button-1>",
                         lambda e: self.xr_button1_action(e))
        self.canvas.bind("<ButtonRelease-1>",
                         lambda e: self.xr_button1_release_action(e, True))
        self.canvas.bind("<Shift-ButtonRelease-1>",
                         lambda e: self.xr_button1_release_action(e, False))
        self.canvas.bind("<B1-Motion>",
                         lambda e: self.xr_button1_motion_action(e, True))
        self.canvas.bind("<Shift-B1-Motion>",
                         lambda e: self.xr_button1_motion_action(e, False))
        self.pack(side=tkinter.TOP, fill='x')

    def draw(self):
        super().draw()
        self.yruler.create_line(YRULER_WIDTH - 1, 0, YRULER_WIDTH - 1,
                                self.height, fill=CL_VLINE_ORG)
        first_meas = self.master.tsigmap.ticks2mbt(0)[0]
        for measure in range(first_meas,
                             first_meas + self.master.tsigmap.num_measures()):
            time = self.master.tsigmap.mbt2ticks(measure)
            x = time * self.pixels_per_tick
            self.canvas.create_text(x + 4, self.height, font=XRULER_FONT,
                                    text='%d' % measure, anchor='sw')

    def vert_zoom(self, center, zoom):  # no vertical zoom
        pass

    def snapped_ticks(self, ticks):
        td = SNAP_PIXELS / (self.pixels_per_tick * self.master.xzoom)
        candidates = [ev.t for ev in self.master.evlist
                      if (isinstance(ev, NoteEvent) and
                          abs(ev.t - ticks) <= td)]
        (m, _, b, _) = self.master.tsigmap.ticks2mbt(ticks)
        candidates.append(self.master.tsigmap.mbt2ticks(m, b, 0))
        candidates.append(self.master.tsigmap.mbt2ticks(m, b+1, 0))
        t = min(candidates, key=lambda x: abs(x - ticks))
        return t if abs(t - ticks) <= td else ticks

    def _intersect(self, ticks, cursorpos):
        if cursorpos is None:
            return False
        d = (XRULER_CURSOR_WIDTH * 0.75) / \
            (self.pixels_per_tick * self.master.xzoom)
        return ticks - d <= cursorpos <= ticks + d

    def _get_ticks(self, tkevent):
        return (self.canvas.canvasx(tkevent.x) /
                (self.pixels_per_tick * self.master.xzoom))

    def xr_motion_action(self, tkevent, snap=True):
        ticks = self._get_ticks(tkevent)
        if self._intersect(ticks, self.master.playstart):
            ticks = self.master.playstart
            self.master.playstart_tmp = None
        elif self._intersect(ticks, self.master.playingpos):
            ticks = self.master.playingpos
            self.master.playstart_tmp = None
        else:
            ticks = self.snapped_ticks(ticks) if snap else ticks
            self.master.playstart_tmp = ticks
        self.update_cursors()
        self.master.msgpane.clear()
        self.master.msgpane.showmsg(0, 't=%s' % std_time_repr(ticks))

    def xr_leave_action(self, tkevent):
        self.master.playstart_tmp = None
        self.update_cursors()
        self.master.msgpane.clear()

    def xr_button1_action(self, tkevent):
        ticks = self._get_ticks(tkevent)
        if self._intersect(ticks, self.master.playstart):
            self.dragging = 'playstart'
        elif self._intersect(ticks, self.master.playingpos):
            self.dragging = 'playingpos'
        else:
            self.dragging = 'playstart_tmp'

    def xr_button1_motion_action(self, tkevent, snap=True):
        ticks = self._get_ticks(tkevent)
        ticks = max(0, self.snapped_ticks(ticks) if snap else ticks)
        setattr(self.master, self.dragging, ticks)
        self.update_cursors()
        self.master.msgpane.clear()
        self.master.msgpane.showmsg(0, 't=%s' % std_time_repr(ticks))

    def xr_button1_release_action(self, tkevent, snap=True):
        ticks = self._get_ticks(tkevent)
        ticks = max(0, self.snapped_ticks(ticks) if snap else ticks)
        if self.dragging == 'playingpos':
            self.master.playingpos = ticks
        else:
            self.master.playstart = ticks
            self.master.playingpos = None
        self.update_cursors()


class DummyScrollbar(tkinter.Canvas):  # 小節番号表示バーの右端
    def __init__(self, master, width):
        dw = 4 if sys.platform == 'win32' else \
             6 if sys.platform == 'darwin' else 0
        super().__init__(master, height=width, width=width-dw)
        self.config(highlightbackground=CL_VLINE_DASHED)

    def set(self, *args, **kwargs):
        pass

    def config(self, command=None, **kwargs):
        super().config(**kwargs)


class XScrollPane(tkinter.Frame):
    def __init__(self, master):
        super().__init__(master, borderwidth=PANE_BORDER_WIDTH,
                         relief=tkinter.RIDGE)
        self.xscroll = tkinter.Scrollbar(self, orient=tkinter.HORIZONTAL,
                                         width=SCROLLBAR_WIDTH)
        self.yruler = tkinter.Canvas(self, width=YRULER_WIDTH,
                                     highlightthickness=0, background=CL_BACK,
                                     height=SCROLLBAR_WIDTH)
        self.yruler.create_line(YRULER_WIDTH - 1, 0,
                                YRULER_WIDTH - 1, SCROLLBAR_WIDTH,
                                fill=CL_VLINE_ORG)
        self.yruler.pack(side=tkinter.LEFT)
        self.xscroll.pack(padx=(0, SCROLLBAR_WIDTH + 2), fill='x')
        self.pack(side=tkinter.BOTTOM, fill='x')


class MessagePane(tkinter.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.master = master
        self.labels = []
        for i in range(0, 3):
            label = tkinter.Label(self, font=MSG_FONT, width=1, anchor='w',
                                  borderwidth=PANE_BORDER_WIDTH,
                                  background=CL_BACK, relief=tkinter.RIDGE)
            label.grid(row=0, column=i, sticky='ew')
            self.columnconfigure(i, weight=(8, 1, 6)[i], uniform='a')
            self.labels.append(label)
            label.bind(RIGHTBUTTON,
                       lambda e: self.master.mainmenu.tk_popup(e.x_root,
                                                               e.y_root))
        self.pack(side=tkinter.BOTTOM, fill='x')

    def showmsg(self, i, string):
        self.labels[i].configure(text=string)

    def showtrack(self, tracks):
        def trkname(tk):
            s = self.master.tracklist[tk]
            return (' "%s"' % s) if s else ''
        self.showmsg(
            2, ' '.join(("Track(s): %d%s" % (tk, trkname(tk)) if i == 0
                         else "+%d" % tk if i == 1 else str(tk))
                        for i, tk in enumerate(tracks)))

    def clear(self):
        for label in self.labels:
            label.configure(text='')


# ボタンの動作:
#   トラック番号ボタンを押すと、ソロ状態 (自分以外すべて非選択)になる。
#   もう一度押すと、ソロ操作(他のトラックに対するソロ操作を含む)以前の
#   状態に戻る（直近の2つ以上のトラックが選択されていた時の状態へ戻る）。
#   ALLボタンを押すと、すべてのトラックが表示状態になる。もう一度押すと、
#   元の状態に戻る。
#   SHIFTまたはCTRL+トラック番号を押すと、そのトラックの表示/非表示状態が
#   逆になる。
class TrackButtonPane(tkinter.Frame):
    def __init__(self, master):
        super().__init__(master, borderwidth=PANE_BORDER_WIDTH,
                         relief=tkinter.RIDGE, background=CL_BACK)
        self.tracklist = master.tracklist
        self.currentstate = [True for i in range(len(self.tracklist))]
        self.savedstate = [True for i in range(len(self.tracklist))]
        self.create_widgets()
        self.bind(RIGHTBUTTON,
                  lambda e: self.master.mainmenu.tk_popup(e.x_root, e.y_root))
        self.pack(side=tkinter.TOP, fill='x')

    def create_widgets(self):
        self.allbutton = tkinter.Button(self, text="ALL",
                                        font=TRACK_BUTTON_FONT,
                                        borderwidth=BUTTON_BORDER,
                                        padx=BUTTON_BORDER*2,
                                        pady=BUTTON_BORDER)
        self.allbutton.pack(side=tkinter.LEFT, fill='y')
        self.bind_actions(self.allbutton, -1)
        self.buttons = [None for i in range(len(self.tracklist))]
        count = 0
        for i, trackname in enumerate(self.tracklist):
            color = TRACK_COLORS[i % len(TRACK_COLORS)]
            if trackname is not None:
                self.buttons[i] = \
                    tkinter.Button(self, text="%d" % i,
                                   background=color, activebackground=color,
                                   # macの場合、何故かdisabledにしておかないと
                                   # スリープから復帰したときに色がなくなる。
                                   **({'highlightbackground': color,
                                       'highlightthickness': 2,
                                       'disabledforeground': 'black',
                                       'state': 'disabled'}
                                      if sys.platform == 'darwin' else {}),
                                   font=TRACK_BUTTON_FONT, relief='raised',
                                   borderwidth=BUTTON_BORDER, width=1,
                                   padx=BUTTON_BORDER*2, pady=BUTTON_BORDER)
                self.buttons[i].pack(side=tkinter.LEFT, fill='y')
                self.bind_actions(self.buttons[i], i)
                count += 1
                if count >= MAX_TRACK_BUTTONS:
                    break
        #
        self.pausebutton = tkinter.Button(
            self, image=self.master.bitmaps['continue'],
            borderwidth=BUTTON_BORDER, width=PLAY_BUTTON_WIDTH,
            command=lambda: self.master.pause())
        self.pausebutton.pack(side=tkinter.RIGHT, fill='y')
        self.playbutton = tkinter.Button(
            self, image=self.master.bitmaps['play'],
            borderwidth=BUTTON_BORDER, width=PLAY_BUTTON_WIDTH,
            command=lambda: self.master.play())
        self.playbutton.pack(side=tkinter.RIGHT, fill='y')
        self.ts_tkvar = tkinter.DoubleVar()
        self.ts_tkvar.set(self.master.temposcale)
        self.ts_spinbox = tkinter.Spinbox(
            self, width=3, borderwidth=BUTTON_BORDER, takefocus=None,
            from_=MIN_TEMPO_SCALE, to=MAX_TEMPO_SCALE, format="%3.1f",
            increment=TEMPO_SCALE_STEP,
            textvariable=self.ts_tkvar, font=TEMPO_SCALE_SPINBOX_FONT,
            command=lambda: self.spinbox_action())
        self.ts_spinbox.bind("<Return>", lambda e: self.spinbox_action())
        self.ts_spinbox.pack(side=tkinter.RIGHT, padx=10)

    def bind_actions(self, widget, tk):
        if tk >= 0:
            widget.bind("<Enter>",
                        lambda e: self.master.msgpane.showtrack((tk,)))
        widget.bind("<Leave>", lambda e: self.master.msgpane.clear())
        widget.bind("<Button-1>", lambda e: self.button_click_action(tk))
        widget.bind("<Control-Button-1>",
                    lambda e: self.button_ctrl_click_action(tk))
        widget.bind("<Shift-Button-1>",
                    lambda e: self.button_ctrl_click_action(tk))

    def button_click_action(self, tk):
        if tk < len(self.tracklist):
            oldstate = self.currentstate[:]
            target = [tk == i or tk == -1 for i in range(len(self.tracklist))]
            if self.currentstate == target:
                self.currentstate[:] = self.savedstate
            else:
                if tk == -1 or sum(self.currentstate) != 1:
                    self.savedstate[:] = self.currentstate
                self.currentstate = target
                if tk != -1:
                    for pane in self.master.panelist:
                        pane.canvas.tkraise('tk%d' % tk)
            self.master.mute_control(oldstate, self.currentstate)
            self.update_panes()
        return 'break'

    def button_ctrl_click_action(self, tk):
        if 0 <= tk < len(self.tracklist):
            oldstate = self.currentstate[:]
            self.currentstate[tk] = not self.currentstate[tk]
            if self.currentstate[tk]:
                for pane in self.master.panelist:
                    pane.canvas.tkraise('tk%d' % tk)
            self.savedstate[:] = self.currentstate
            self.master.mute_control(oldstate, self.currentstate)
            self.update_panes()
        return 'break'

    def spinbox_action(self):
        try:
            scale = min(MAX_TEMPO_SCALE,
                        max(MIN_TEMPO_SCALE,
                            round(float(self.ts_tkvar.get()), 1)))
            self.master.change_tempo_scale(scale)
        except ValueError:
            pass
        self.ts_tkvar.set(self.master.temposcale)

    def tempo_scale_up(self):
        self.ts_tkvar.set(self.ts_tkvar.get() + TEMPO_SCALE_STEP)
        self.spinbox_action()

    def tempo_scale_down(self):
        self.ts_tkvar.set(self.ts_tkvar.get() - TEMPO_SCALE_STEP)
        self.spinbox_action()

    def tempo_scale_reset(self):
        self.ts_tkvar.set(1)
        self.spinbox_action()

    def update_panes(self):
        for i, state in enumerate(self.currentstate):
            if self.tracklist[i] is not None:
                if self.buttons[i] is not None:
                    color = TRACK_COLORS[i % len(TRACK_COLORS)]
                    if sys.platform == 'darwin':
                        self.buttons[i].configure(
                            highlightbackground=color if state else 'gray10')
                    else:
                        self.buttons[i].configure(
                            relief='raised' if state else 'flat',
                            background=color if state else 'gray80')
                for pane in self.master.panelist:
                    pane.canvas.itemconfigure(
                        'tk%d && !nohide' % i,
                        state='normal' if state else 'hidden')

    def update_pause_button(self):
        self.pausebutton.configure(
            image=self.master.bitmaps['pause' if self.master.status ==
                                      'playing' else 'continue'])


class ViewerMain(tkinter.Frame):
    def __init__(self, master, score, velocity, ctrlnums, limit, render,
                 bar0len, width, height, pixels_per_tick, pixels_per_notenum):
        self.evlist_org = EventList(score, limit=limit)\
            .Filter(NoteEventClass, CtrlEvent, SysExEvent, MetaEvent)\
            .ConnectTies().PairNoteEvents()
        if render:
            rend = Render()
            self.evlist = EventList((rend(ev) for ev in self.evlist_org),
                                    duration=self.evlist_org.duration)
        else:
            self.evlist = self.evlist_org
        self.save_event_repr()
        if not self.evlist.active_events_at(0, TempoEvent):
            self.evlist.insert(0, TempoEvent(0, current_tempo()))
        self.tsigmap = TimeSignatureMap(self.evlist, bar0len)
        self.tracklist = get_tracklist(self.evlist)
        self.master = master
        self.viewwidth = width
        self.pixels_per_tick = pixels_per_tick
        self.pixels_per_notenum = pixels_per_notenum
        self.xzoom = 1.0
        self.panelist = []
        self.status = 'stop'
        self.playstart = 0
        self.playstart_tmp = None
        self.playingpos = None
        self.temposcale = 1.0
        velocity = self.parse_velocity(velocity)
        ctrlnums = self.parse_ctrlnums(ctrlnums)
        super().__init__(master)
        self.create_bitmaps()
        self.create_widgets(height, velocity, ctrlnums)
        self.create_menus()
        self.bind_keys()
        self.pack(expand=1, fill='both')
        self.notepane.canvas.update()
        self.notepane.ycenter()

    def parse_velocity(self, velocity):
        if isinstance(velocity, str):
            if velocity == 'auto':
                events = self.evlist.Filter(NoteEvent)
                return events and \
                    min(ev.v for ev in events) != max(ev.v for ev in events)
            else:
                raise Exception("Unrecognized description '%s'" % velocity)
        else:
            return velocity

    def get_auto_ctrlnums(self):
        if not hasattr(self, '_auto_ctrlnums'):
            events = self.evlist.Filter(CtrlEvent, TempoEvent)
            result_auto = set()
            result_verbose = set()
            ctrldict = {}  # key=(ctrlnum, tk, ch)
            tempo = None
            for ev in events:
                result_verbose.add(C_TEMPO if isinstance(ev, TempoEvent)
                                   else ev.ctrlnum)
                if isinstance(ev, TempoEvent):
                    if tempo is not None and tempo != ev.value:
                        result_auto.add(C_TEMPO)
                    tempo = ev.value
                else:
                    key = (ev.ctrlnum, ev.tk, ev.ch)
                    if key in ctrldict and ctrldict[key] != ev.value:
                        result_auto.add(ev.ctrlnum)
                    ctrldict[key] = ev.value
            self._auto_ctrlnums = (sorted(result_auto), sorted(result_verbose))
        return self._auto_ctrlnums

    def parse_ctrlnums(self, ctrlnums):
        if isinstance(ctrlnums, str):
            ctrlnums = (ctrlnums,)
        result = []
        for ctrlnum in ctrlnums:
            if ctrlnum in ('auto', 'verbose'):
                for c in self.get_auto_ctrlnums()[ctrlnum == 'verbose']:
                    if c not in result:
                        result.append(c)
            elif isinstance(ctrlnum, int):
                if ctrlnum < 0:
                    try:
                        result.remove(-ctrlnum & 0xff)
                    except ValueError:
                        pass
                else:
                    if ctrlnum not in result:
                        result.append(ctrlnum)
            else:
                raise Exception("Unrecognized entry '%r' in ctrlnums" %
                                ctrlnum)
        return result

    def save_event_repr(self):
        for ev, ev_org in zip(self.evlist, self.evlist_org):
            if ev is not ev_org:
                ev.org_repr = repr(ev_org)

    def create_widgets(self, notepane_viewheight, velocity, ctrlnums):
        self.msgpane = MessagePane(self)
        self.xscroll = XScrollPane(self).xscroll
        self.trackbuttonpane = TrackButtonPane(self)
        self.xruler = XRulerPane(self)
        self.notepane = NoteViewPane(self, notepane_viewheight)
        self.ctrlpanedict = {}  # 現在表示されているpaneの辞書
        if velocity:
            self.ctrlpanedict[-1] = VelocityViewPane(self,
                                                     CTRL_PANE_VIEW_HEIGHT)
        for i in ctrlnums:
            self.ctrlpanedict[i] = CtrlEventViewPane(self,
                                                     CTRL_PANE_VIEW_HEIGHT, i)

    def create_menus(self):
        viewmenuctrls = [-1] + self.get_auto_ctrlnums()[1]
        for ctrlnum in self.ctrlpanedict:
            if ctrlnum not in viewmenuctrls:
                viewmenuctrls.append(ctrlnum)
        viewmenuctrls.sort()
        self.mainmenu = tkinter.Menu(self, tearoff=False, font=MENU_FONT)
        self.viewmenu = tkinter.Menu(self.mainmenu, tearoff=False,
                                     font=MENU_FONT)
        self.zoommenu = self.create_zoommenu(self.mainmenu)
        self.midimenu = self.create_midimenu(self.mainmenu)
        self.viewmenu.add_command(label='Show all actively used controllers',
                                  accelerator='c',
                                  command=lambda: self.open_all_ctrlpanes(0))
        self.viewmenu.add_command(label='Show all used controllers',
                                  command=lambda: self.open_all_ctrlpanes(1))
        self.viewmenu.add_command(label='Hide all controllers',
                                  accelerator='x',
                                  command=lambda: self.close_all_ctrlpanes())
        self.viewmenu.add_separator()
        self.viewmenu.add_separator()
        self.viewmenu.add_command(label='Other controller',
                                  command=lambda: self.viewmenu_other_action())
        self.viewmenuvars = {}
        for ctrlnum in viewmenuctrls:
            self.add_viewmenuitem(ctrlnum)
        self.mainmenu.add_cascade(label='Add/Delete Pane',
                                  menu=self.viewmenu)
        self.mainmenu.add_separator()
        self.mainmenu.add_command(
            label='Close Pane', accelerator='Ctrl+D',
            command=lambda: self.close_ctrlpane(self.popupwidget.ctrlnum))
        self.mainmenu.add_separator()
        self.mainmenu.add_cascade(label='Zoom', menu=self.zoommenu)
        self.mainmenu.add_separator()
        self.mainmenu.add_cascade(label='MIDI I/F', menu=self.midimenu)
        self.mainmenu.add_separator()
        self.mainmenu.add_command(label='Play', accelerator='p',
                                  command=self.play)
        self.mainmenu.add_command(label='Pause/Continue', accelerator='Space',
                                  command=self.pause)
        self.mainmenu.add_command(label='Reset Cursors', accelerator='r',
                                  command=self.reset_cursors)
        self.mainmenu.add_separator()
        self.mainmenu.add_command(label='Close Window', accelerator='Ctrl+W',
                                  command=lambda: self.after(0, self.quit))
        # 直接self.quitを呼ぶと、macでエラーメッセージが出てしまう ↑

    def add_viewmenuitem(self, ctrlnum):
        tkvar = tkinter.IntVar(value=ctrlnum in self.ctrlpanedict)
        label = "Velocity" if ctrlnum == -1 else \
                "Pitch bend" if ctrlnum == C_BEND else \
                "Key Pressure" if ctrlnum == C_KPR else \
                "Channel Pressure" if ctrlnum == C_CPR else \
                "Program Change" if ctrlnum == C_PROG else \
                "Tempo" if ctrlnum == C_TEMPO else \
                "Controller #%d (%s)" % (ctrlnum,
                                         CONTROLLERS.get(ctrlnum, '')[2:])
        self.viewmenuvars[ctrlnum] = tkvar
        self.viewmenu.insert_checkbutton(
            self.viewmenu.index('end') - 1, label=label, variable=tkvar,
            command=(lambda: self.viewmenu_action(ctrlnum, tkvar)))

    def open_ctrlpane(self, ctrlnum):
        if ctrlnum not in self.ctrlpanedict:
            self.ctrlpanedict[ctrlnum] = (
                VelocityViewPane(self, CTRL_PANE_VIEW_HEIGHT) if ctrlnum == -1
                else CtrlEventViewPane(self, CTRL_PANE_VIEW_HEIGHT, ctrlnum))
            self.viewmenuvars[ctrlnum].set(True)
            self.trackbuttonpane.update_panes()

    def open_all_ctrlpanes(self, verbose):
        act = False
        for cnum in self.get_auto_ctrlnums()[verbose]:
            if cnum not in self.ctrlpanedict:
                self.open_ctrlpane(cnum)
                act = True
        if not act:
            print("show: All such controllers are already shown",
                  file=sys.stderr)

    def close_ctrlpane(self, ctrlnum):
        if ctrlnum in self.ctrlpanedict:
            self.ctrlpanedict[ctrlnum].destroy()
            del self.ctrlpanedict[ctrlnum]
            self.viewmenuvars[ctrlnum].set(False)

    def close_all_ctrlpanes(self):
        act = False
        for cnum in list(self.ctrlpanedict):
            if cnum != -1:
                self.close_ctrlpane(cnum)
                act = True
        if not act:
            print("show: All controllers are already hidden", file=sys.stderr)

    def viewmenu_action(self, ctrlnum, tkvar):
        if tkvar.get():
            self.open_ctrlpane(ctrlnum)
        else:
            self.close_ctrlpane(ctrlnum)

    def viewmenu_other_action(self):
        ctrlnum = tkinter.simpledialog.askinteger(
            "Add Pane", "Enter a controller number:")
        if ctrlnum is not None:
            if 0 <= ctrlnum < 256:
                if ctrlnum not in self.viewmenuvars:
                    self.add_viewmenuitem(ctrlnum)
                tkvar = self.viewmenuvars[ctrlnum]
                tkvar.set(True)
                self.viewmenu_action(ctrlnum, tkvar)
            else:
                print("show: Controller number out of range", file=sys.stderr)

    def toggle_velocity_pane(self):
        tkvar = self.viewmenuvars[-1]
        tkvar.set(not tkvar.get())
        self.viewmenu_action(-1, tkvar)

    def create_zoommenu(self, parentmenu):
        zoommenu = tkinter.Menu(parentmenu, tearoff=False, font=MENU_FONT)
        zoommenu.add_command(
            label='Zoom In', accelerator='Ctrl++',
            command=lambda: self.popupwidget.zoom_in(*self.popupcoords))
        zoommenu.add_command(
            label='Zoom Out', accelerator='Ctrl+-',
            command=lambda: self.popupwidget.zoom_out(*self.popupcoords))
        zoommenu.add_command(
            label='Reset Zoom', accelerator='Ctrl+=',
            command=lambda: self.popupwidget.reset_zoom(self.popupcoords[0]))
        zoommenu.add_command(
            label='Horizontal Zoom In',
            command=lambda: self.popupwidget.zoom_in(*self.popupcoords, 'x'))
        zoommenu.add_command(
            label='Horizontal Zoom Out',
            command=lambda: self.popupwidget.zoom_out(*self.popupcoords, 'x'))
        zoommenu.add_command(
            label='Vertical Zoom In',
            command=lambda: self.popupwidget.zoom_in(*self.popupcoords, 'y'))
        zoommenu.add_command(
            label='Vertical Zoom Out',
            command=lambda: self.popupwidget.zoom_out(*self.popupcoords, 'y'))
        return zoommenu

    def create_midimenu(self, parentmenu):
        self.outdevvar = tkinter.IntVar(value=midiio.current_output_device())
        midimenu = tkinter.Menu(parentmenu, tearoff=False, font=MENU_FONT)
        for i, dev in enumerate(midiio.output_devices()):
            midimenu.add_radiobutton(
                label=dev, variable=self.outdevvar, value=i,
                command=lambda:
                (midiio.set_output_device(self.outdevvar.get()),
                 midiio.open_output_device()))
        return midimenu

    def menu_popup(self, widget, x, y):
        self.mainmenu.entryconfigure(
            'Close Pane',
            state='normal' if isinstance(widget, CtrlViewPaneBase)
            else 'disabled')
        self.popupwidget = widget
        self.popupcoords = (x, y)
        self.mainmenu.tk_popup(x, y)

    def quit(self):
        self.stop()
        midiio.set_tempo_scale(1.0)
        self.master.destroy()

    def bind_keys(self):
        self.master.bind("<Escape>", lambda e: self.quit())
        self.master.bind("<Control-q>", lambda e: self.quit())
        self.master.bind("<Control-w>", lambda e: self.quit())
        self.master.protocol("WM_DELETE_WINDOW", lambda: self.quit())
        for i in range(0, 20):
            self.master.bind_class(
                "Frame",  # Frame限定でbindしないと、spinboxの文字入力に反応
                "<Alt-Key-%d>" % (i % 10) if i >= 10 else str(i),
                lambda e, i=i: self.trackbuttonpane.button_click_action(i))
            self.master.bind_class(
                "Frame",
                "<Control-Alt-Key-%d>" % (i % 10) if i >= 10 else
                ("<Control-Key-%d>" % i),
                lambda e, i=i:
                self.trackbuttonpane.button_ctrl_click_action(i))
        self.master.bind_class(
            "Frame", 'a',
            lambda e: self.trackbuttonpane.button_click_action(-1))
        self.master.bind_class("Frame", 'p', lambda e: self.play())
        self.master.bind_class("Frame", '<space>', lambda e: self.pause())
        self.master.bind_class("Frame", 'r', lambda e: self.reset_cursors())
        self.master.bind_class("Frame", 'c',
                               lambda e: self.open_all_ctrlpanes(0))
        self.master.bind_class("Frame", 'x',
                               lambda e: self.close_all_ctrlpanes())
        self.master.bind_class("Frame", 'v',
                               lambda e: self.toggle_velocity_pane())
        self.master.bind_class("Frame", '<Prior>', lambda e:
                               self.trackbuttonpane.tempo_scale_up())
        self.master.bind_class("Frame", '<Next>', lambda e:
                               self.trackbuttonpane.tempo_scale_down())

    #
    def update_playing_cursor(self):
        self.playingpos = midiio.current_time() - self.toffset
        if self.playingpos >= self.evlist.duration:
            # 曲の終わりに到達
            self.status = 'stop'
            self.trackbuttonpane.update_pause_button()
            self.playingpos = None
            self.notepane.update_cursors(True)
            return
        self.notepane.update_cursors(True)
        cx = self.playingpos / self.evlist.duration
        vrange = self.notepane.canvas.xview()
        if cx < vrange[0] or \
           cx >= vrange[0] + (vrange[1] - vrange[0]) * AUTO_SCROLL_THRES:
            self.notepane.xview_moveto_all(cx - (vrange[1] - vrange[0]) *
                                           (1 - AUTO_SCROLL_THRES))
        self.update_idletasks()  # 負荷が重いときにTkへの要求が貯まるのを防ぐ
        self.after_id = self.after(CURSOR_UPDATE_PERIOD,
                                   self.update_playing_cursor)

    def _queue_evlist(self, evlist, lbtime):
        for ev in evlist:
            if ev.t > lbtime:
                midiio.queue_event(ev, ev.t + self.toffset)

    def play(self, pos=None):
        if self.status == 'playing':
            self.stop()
        pos = self.playstart if pos is None else pos
        filtered = self.evlist.Filter(
            lambda ev: self.trackbuttonpane.currentstate[ev.tk] or
            isinstance(ev, TempoEvent))
        initial_events = filtered.active_events_at(pos)
        current_time = midiio.current_time()
        self.toffset = current_time - pos
        midiio.set_tempo_scale(self.temposcale)
        # midiio.playのようにtempo_scaleを一時的に0にしなくても出だしが
        # もたつかないのは、予め全イベントが時間順にソートされているから。
        for ev in initial_events:
            midiio.queue_event(ev, current_time)
        for ev in filtered:
            if ev.t > pos:
                midiio.queue_event(ev, ev.t + self.toffset)
        self.status = 'playing'
        self.trackbuttonpane.update_pause_button()
        self.update_playing_cursor()

    def pause(self):
        if self.status == 'playing':
            self.stop()
        else:
            if self.playingpos is None:
                self.playingpos = self.playstart
            self.play(self.playingpos)

    def stop(self):
        if self.status == 'playing':
            self.playingpos = midiio.current_time() - self.toffset
            self.notepane.update_cursors()
            self.after_cancel(self.after_id)
        midiio.stop()
        self.status = 'stop'
        self.trackbuttonpane.update_pause_button()

    def reset_cursors(self):
        if self.status == 'playing':
            self.stop()
        self.playstart = 0
        self.playstart_tmp = None
        self.playingpos = None
        self.notepane.update_cursors()
        self.notepane.xview_moveto_all(0)

    def mute_control(self, old_mute_state, new_mute_state):
        if self.status == 'playing':
            current_time = midiio.current_time()
            pos = current_time - self.toffset
            for tk in range(len(self.tracklist)):
                if old_mute_state[tk] and not new_mute_state[tk]:
                    midiio.cancel_events(tk)
                    # テンポイベントは消すべきでないので再挿入する
                    filtered = self.evlist.Filter(
                        lambda ev: ev.tk == tk and isinstance(ev, TempoEvent))
                    self._queue_evlist(filtered, pos)
                if not old_mute_state[tk] and new_mute_state[tk]:
                    filtered = self.evlist.Filter(
                        lambda ev: ev.tk == tk and
                        not isinstance(ev, TempoEvent))
                    initial_events = filtered.active_events_at(pos)
                    for ev in initial_events:
                        midiio.queue_event(ev, current_time)
                    self._queue_evlist(filtered, pos)

    def change_tempo_scale(self, scale):
        self.temposcale = scale
        midiio.set_tempo_scale(self.temposcale)

    def create_bitmaps(self):
        self.bitmaps = {}
        self.bitmaps['play'] = tkinter.BitmapImage(data="""
            #define play_width 16 #define play_height 16
            static unsigned char play_bits[] = {
                0x00, 0x00, 0x00, 0x00, 0x73, 0x00, 0xf3, 0x00, 0xf3, 0x03,
                0xf3, 0x07, 0xf3, 0x1f, 0xf3, 0x7f, 0xf3, 0xff, 0xf3, 0x7f,
                0xf3, 0x1f, 0xf3, 0x07, 0xf3, 0x03, 0xf3, 0x00, 0x73, 0x00,
                0x00, 0x00};""")
        self.bitmaps['pause'] = tkinter.BitmapImage(data="""
            #define pause_width 16 #define pause_height 16
            static unsigned char pause_bits[] = {
                0x00, 0x00, 0x00, 0x00, 0x78, 0x1e, 0x78, 0x1e, 0x78, 0x1e,
                0x78, 0x1e, 0x78, 0x1e, 0x78, 0x1e, 0x78, 0x1e, 0x78, 0x1e,
                0x78, 0x1e, 0x78, 0x1e, 0x78, 0x1e, 0x78, 0x1e, 0x78, 0x1e,
                0x00, 0x00};""")
        self.bitmaps['continue'] = tkinter.BitmapImage(data="""
            #define pause_width 16 #define pause_height 16
            static unsigned char continue_bits[] = {
                0x00, 0x00, 0x00, 0x00, 0x04, 0x00, 0x1c, 0x00, 0x7c, 0x00,
                0xfc, 0x01, 0xfc, 0x07, 0xfc, 0x1f, 0xfc, 0x3f, 0xfc, 0x1f,
                0xfc, 0x07, 0xfc, 0x01, 0x7c, 0x00, 0x1c, 0x00, 0x04, 0x00,
                0x00, 0x00};""")


def show(score, velocity='auto', ctrlnums='auto', limit=SHOW_LIMIT,
         render=True, bar0len=None, magnify=MAGNIFY, geometry=GEOMETRY,
         title="Pytakt") -> None:
    """
    スコア `score` についてのピアノロールを表示します。

    Args:
        score(Score): 表示するスコア。
        velocity(bool or str, optional): Trueならば、ベロシティーPaneを
            表示します。Falseなら表示しません。'auto' の場合、何らかの変化が
            あるときに限り表示を行います。
        ctrlnums(iterable of int or str, or str, optional):
            表示するコントローラPaneの種類を指定します
            (例: ``show(s, ctrlnums=[C_VOL])``) 。
            'auto' を指定すると、同一トラック同一チャネルに値の異なる
            2つ以上のイベントを含むようなコントローラをすべて表示します。
            'verbose' を指定すると、イベントが存在するコントローラをすべて
            表示します。'auto' や　'verbose' は iterable の中に含めることも
            でき、それに対してさらに追加、あるは符号反転したコントローラ番号を
            指定して削除することができます
            (例: ``ctrlnums=('auto', C_PROG, -C_DATA)``) 。
            0番(C_BANK)のコントローラを削除したいときは、-256を指定します。
        limit(ticks, optional):
            スコアの長さを制限します。
            制限の詳細については、:meth:`.Score.stream` の同名の引数
            の項目を見てください。
        render(bool, optional):
            デフォルト(True)の場合、演奏上の時間に従ってイベントを表示します。
            Falseの場合は、楽譜上の時間で表示します。
        bar0len(ticks, optional):
            指定すると、小節番号 0 の小節の長さをこのティック数に修正します。
        magnify(float, optional):
            全体の拡大率を指定します。
        geometry(str, optional):
            ウィンドウのサイズ、位置を指定します (例: "800x600+0+0")
        title(str, optional): ウィンドウのタイトル文字列を指定します。

    magnify と geoemtry 引数のデフォルト値は、環境変数 PYTAKT_MAGNIFY と
    PYTAKT_GEOMETRY によってそれぞれ指定することができます。

    .. rubric:: ウィンドウにおける操作

    - **トラックボタン**: 上部のALLおよび番号ボタンはトラックごとの
      選択・非選択を切り替えます。
      番号ボタンを押すと、ソロ状態 (自分以外すべて非選択)になります。
      もう一度押すと、 直近の2つ以上のトラックが選択されていた時の状態へ戻り
      ます。ALLボタンを押すと、すべてのトラックが選択状態になり、
      もう一度押すと、元の状態に戻ります。SHIFTまたはCTRL+トラック番号を
      押すと、そのトラックの選択状態が逆になります。
    - **テンポスケール**: 右上の数字ボックスによりテンポの倍率を変更できます。
    - **Playボタン** (\\|▶): 赤いカーソルの位置から演奏を開始します。
      赤いカーソルは上部の小節番号ルーラーをクリックすることで移動できます。
    - **Pause/Continueボタン** (⏸, ▶): 演奏の停止と
      以前停止した位置 (緑カーソルの位置) からの再開を交互に行います。
    - **右ボタンメニュー**: マウスの右ボタンでメニューが表示され、そこから
      コントローラPaneの追加/削除、ズーム、出力デバイスの切り替えなどが
      行えます。
    - **ノートPane**:
      各ノートをクリックすると、その発音とともに、最前面に移動します。
      SHIFT+クリックなら最背面に移動します。CTRL+クリックの場合は、
      トラックボタンを押したのと同じ動作になります。何もないところで
      ドラッグすると水平スクロール（+SHIFTで垂直・水平スクロール) します。
      マウスホイール、SHIFT+マウスホイールはスクロール (方向はプラットフォーム
      依存) を行います。CTRL+マウスホイールはズームを行い、小節番号ルーラー部分
      で行うと水平のみズーム、鍵盤表示部分で行うと垂直のみズームになります。
    - **コントローラPane**:
      右メニューでon/offできます。マウスホイールの動作はノートPaneと同じです。
    - **ステータス表示**:
      画面下の左部はイベント内容の表示、中央部はピッチの表示、右部は
      トラック番号と(あれば)トラック名の表示です。複数のノートが重なっている
      場合、トラック番号は "+ 2 3" のような表示になります。
    - **ショートカットキー**:
        - p: Playボタンと同じ
        - space: Pause/Continueボタンと同じ
        - r: カーソルのリセット
        - a: ALLボタンと同じ
        - c: 値に動きのあるすべてのコントローラPaneを表示
          (ctrlnums='auto'と同等)
        - x: すべてのコントローラPaneを消去
        - v: ベロシティpaneの表示/消去
        - 0-9: トラック番号ボタンと同じ (+ALT で トラック10～19)
        - 矢印キー: スクロール (+SHIFT でページ単位)
        - Home/End: 曲の先頭/末尾へ移動
        - PageUp/PageDown: テンポスケールの増減
        - CTRL+'+', CTRL+'-': ズームUp/Down
        - CTRL+'=': ズームリセット
        - CTRL+d: コントローラPaneのクローズ
        - CTRL+w, CTRL+q, ESC: 終了

    """
    setup_globals(magnify)
    root = tkinter.Tk()
    if geometry is not None:
        root.geometry(geometry)
    root.title(title)
    midiio.open_output_device()
    try:
        ViewerMain(root, score, velocity, ctrlnums, limit, render, bar0len,
                   VIEW_WIDTH, NOTE_PANE_VIEW_HEIGHT,
                   PIXELS_PER_QUARTER_NOTE / TICKS_PER_QUARTER,
                   PIXELS_PER_NOTE_NUM).mainloop()
    except Exception:
        root.update()
        root.destroy()  # これを行わないと再度ウィンドウを開けなくなる
        raise
