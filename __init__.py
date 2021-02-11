import sys
import datetime
import os

IS_WIN = os.name=='nt'
IS_MAC = sys.platform=='darwin'

from time import sleep, time
from subprocess import Popen, PIPE, STDOUT
from threading import Thread, Lock
from collections import namedtuple
import json

if not IS_WIN:
    import pty # Pseudo terminal utilities
    import signal

import cudatext_keys as keys
import cudatext_cmd as cmds
from cudatext import *

from .pyte import *

fn_icon = os.path.join(os.path.dirname(__file__), 'terminal.png')
fn_config = os.path.join(app_path(APP_DIR_SETTINGS), 'cuda_terminal_plus.ini')
fn_state = os.path.join(app_path(APP_DIR_SETTINGS), 'cuda_terminal_plus_state.json')

fn_icon_normal = os.path.join(os.path.dirname(__file__), 'terminal_normal.png')
fn_icon_dim = os.path.join(os.path.dirname(__file__), 'terminal_dim.png')
fn_icon_pluss = os.path.join(os.path.dirname(__file__), 'cuda_pluss.png')
fn_icon_cross = os.path.join(os.path.dirname(__file__), 'cuda_cross.png')

MAX_BUFFER = 100*1000
IS_UNIX_ROOT = not IS_WIN and os.geteuid()==0
SHELL_UNIX = 'bash'
SHELL_MAC = 'bash'
SHELL_WIN = 'cmd.exe'
ENC = 'cp866' if IS_WIN else 'utf8'
BASH_CHAR = '#' if IS_UNIX_ROOT else '$'
BASH_PROMPT = 'echo [$USER:$PWD]'+BASH_CHAR+' '
BASH_CLEAR = 'clear';
MSG_ENDED = "\nConsole process was terminated.\n"
READSIZE = 4*1024
HOMEDIR = os.path.expanduser('~')
INPUT_H = 26
#stop_t = False # stop thread

ColorRange = namedtuple('ColorRange', 'start length fgcol bgcol isbold')
DEFAULT_FGCOL = 'default' # 37
DEFAULT_BGCOL = 'default' # 40

#DONE tab reorder

#TODO self.memo width options
#TODO implement apply_theme()
#TODO hover statusbar migrate to proper
#TODO terminal history


def log(s):
    # Change conditional to True to log messages in a Debug process
    if False:
        now = datetime.datetime.now()
        print(now.strftime("%H:%M:%S ") + s)
    pass

def bool_to_str(v):
    return '1' if v else '0'

def str_to_bool(s):
    return s=='1'

def pretty_path(s):
    if not IS_WIN:
        s = s.rstrip('\n')
        if s==HOMEDIR:
            s = '~'
        elif s.startswith(HOMEDIR+'/'):
            s = '~'+s[len(HOMEDIR):]
    return s


class ControlTh(Thread):
    def __init__(self, Cmd):
        Thread.__init__(self)
        self.Cmd = Cmd

    def add_buf(self, s, clear):
        self.Cmd.block.acquire()
        self.Cmd.btextchanged = True
        # limit the buffer size!
        self.Cmd.btext = (self.Cmd.btext+s)[-MAX_BUFFER:]
        if clear:
            self.Cmd.p=None
            self.Cmd.ch_pid = -1
            self.Cmd.ch_out.close()
        self.Cmd.block.release()

    def run(self):
        if not IS_WIN:
            while True:
                if self.Cmd.stop_t: return
                if not self.Cmd.ch_out:
                    sleep(0.5)
                    continue
                try:
                    s = self.Cmd.ch_out.read(READSIZE)
                except OSError:
                    self.add_buf('', clear=True)
                    # don't break, shell will be restarted
                else: # no exception
                    if s != '':
                        self.add_buf(s, clear=False)
                    
        else:
            while True:
                if self.Cmd.stop_t: return
                if not self.Cmd.p:
                    sleep(0.5)
                    continue
                pp1 = self.Cmd.p.stdout.tell()
                self.Cmd.p.stdout.seek(0, 2)
                pp2 = self.Cmd.p.stdout.tell()
                self.Cmd.p.stdout.seek(pp1)
                if self.Cmd.p.poll() != None:
                    s = MSG_ENDED.encode(ENC)
                    self.add_buf(s, True)
                    # don't break, shell will be restarted
                elif pp2!=pp1:
                    s = self.Cmd.p.stdout.read(pp2-pp1)
                    self.add_buf(s, False)
                sleep(0.02)

class Terminal:
    memo_count = 0
    
    def __init__(self, h_dlg, filepath, shell, font_size, colmapfg, colmapbg, state=None):
        self.h_dlg = h_dlg
        
        if state: # from state
            self.name = state.get('name')
            self.filepath = state.get('filepath')
            self.cwd = state.get('cwd')
            self.lastactive = state.get('lastactive')
        else: # new
            if filepath:
                self.filepath = filepath
                self.name = os.path.split(filepath)[1]
                self.cwd = os.path.split(filepath)[0]
            else:
                self.filepath = ''
                self.name = ''
                self.cwd = ''
            self.lastactive = time()
        
        #TODO implement
        self.icon = 'TODO'
        self.history = 'TODO'
        
        self.colmapfg = colmapfg
        self.colmapbg = colmapbg
        self.shell = shell
        self.font_size = font_size
        
        self._ansicache = {}
        #self.p = ...
        
        self.stop_t = False # stop thread
        self.btext = b''
        self.btextchanged = False
        self.block = Lock()
        self.block.acquire()
        
        self.ch_out = None
        self.ch_pid = -1
        self.p = None
        
        self.memo = None
        
    def _init_memo(self):
        self.memo_wgt_name = Terminal._get_memo_name()
        
        n = dlg_proc(self.h_dlg, DLG_CTL_ADD, 'editor')
        dlg_proc(self.h_dlg, DLG_CTL_PROP_SET, index=n, prop={
            'name': self.memo_wgt_name,
            'a_t': ('', '['),
            'a_l': ('', '['),
            'a_r': ('', ']'),
            'a_b': ('statusbar', '['),
            'font_size': self.font_size,
            })
        self.memo = Editor(dlg_proc(self.h_dlg, DLG_CTL_HANDLE, index=n))

        self.memo.set_prop(PROP_RO, True)
        self.memo.set_prop(PROP_CARET_VIRTUAL, False)
        self.memo.set_prop(PROP_GUTTER_ALL, False)
        self.memo.set_prop(PROP_UNPRINTED_SHOW, False)
        self.memo.set_prop(PROP_MARGIN, 2000)
        self.memo.set_prop(PROP_MARGIN_STRING, '')
        self.memo.set_prop(PROP_LAST_LINE_ON_TOP, False)
        self.memo.set_prop(PROP_HILITE_CUR_LINE, False)
        self.memo.set_prop(PROP_HILITE_CUR_COL, False)
        self.memo.set_prop(PROP_MODERN_SCROLLBAR, True)
        self.memo.set_prop(PROP_MINIMAP, False)
        self.memo.set_prop(PROP_MICROMAP, False)
        self.memo.set_prop(PROP_COLOR, (COLOR_ID_TextBg, self.colmapbg['default']))
        self.memo.set_prop(PROP_COLOR, (COLOR_ID_TextFont, self.colmapfg['default']))
        
    def _open_terminal(self, columns=80, lines=24):
        #shell = self.shell_mac if IS_MAC else self.shell_unix
        
        # child gets pid=0, fd=invalid;   
        # parent: pid=child's, fd=connected to child's terminal
        p_pid, master_fd = pty.fork()   
        
        if p_pid == 0:  # Child.
            if IS_MAC:
                env['PATH'] += ':/usr/local/bin:/usr/local/sbin:/opt/local/bin:/opt/local/sbin'
            
            if self.cwd:
                os.chdir(self.cwd)
                
            env = dict(TERM="xterm-color", LC_ALL="en_GB.UTF-8",
                        COLUMNS=str(columns), LINES=str(lines))
            if 'HOME' in os.environ:
                env['HOME'] = os.environ['HOME']
            
            os.execvpe(self.shell, [self.shell], env)

        # File-like object for I/O with the child process aka command.
        self.ch_out = os.fdopen(master_fd, "w+b", 0)
        self.ch_pid = p_pid

    def _open_process(self):
        env = os.environ
        if IS_MAC:
            env['PATH'] += ':/usr/local/bin:/usr/local/sbin:/opt/local/bin:/opt/local/sbin'

        self.p = Popen(
            os.path.expandvars(self.shell),
            stdin = PIPE,
            stdout = PIPE,
            stderr = STDOUT,
            shell = IS_WIN,
            bufsize = 0,
            env = env
            )
        
    def show(self):
        if not self.memo:
            self._init_memo()
        
            if IS_WIN:
                self._open_process()
            else:
                self._open_terminal()
        
            print(f' -- opened terminal: {self.name}')

            self.CtlTh = ControlTh(self)
            self.CtlTh.start()
            print(f' -- started thread: {self.name}')
        
        self.lastactive = time()
        
        h_ed = self.memo.get_prop(PROP_HANDLE_SELF)
        dlg_proc(self.h_dlg, DLG_CTL_PROP_SET, name=self.memo_wgt_name, prop={'vis':True})
        
    def hide(self):
        if self.memo:
            h_ed = self.memo.get_prop(PROP_HANDLE_SELF)
            dlg_proc(self.h_dlg, DLG_CTL_PROP_SET, name=self.memo_wgt_name, prop={'vis':False})
            
    def close(self):
        self.stop_t = True # stop thread
        if self.block.locked():     self.block.release()
        if self.ch_pid >= 0:        os.kill(self.ch_pid, signal.SIGTERM)
        if self.ch_out:             self.ch_out.close()
        if self.p:                  
            self.p.terminate()
            self.p.wait()
            
    def get_state(self):
        state = {}
        state['filepath'] = self.filepath
        state['name'] = self.name
        state['cwd'] = self.cwd
        state['lastactive'] = self.lastactive
        
        state['icon'] = self.icon
        state['history'] = self.history
        
        return state
        

    def _get_memo_name():
        ind = Terminal.memo_count
        Terminal.memo_count += 1
        return 'memo' + str(ind) 
        
            
"""
#TODO
    on_show -> file -> terminal (path, name, icon, lastactive, history)
        + Term(): .memo (Editor), .btext(-changed), .lock, .p, .history, .ansicache,
    session?

#Actions:
    ? Open only terminals from currenly opened files, remove terminals older than a week
    * Open Terminal -
        * Current file hast terminal - open that
 
#Changes:
    add Terminal (internal - refresh all)
    close T  (internal - refresh all)
    select T  (internal ...)
    Select Editor-Tab  (EXTernal - refresh all)
    Reorder Tabs  (ext - refresh all)
"""
class TerminalBar:
    def __init__(self, h_dlg, plugin, state, font_size):
        print(f' 0 initting terminal bar')

        self.Cmd = plugin
        self.h_dlg = h_dlg
        self.state = state # list of dicts
        self.font_size = font_size
        
        self.terminals = [] # list of Terminal()
        self.sidebar_names = []
        self.active_term = None # Terminal()
        self._init_terms(state)
        
        self.h_sb, self.h_iml = self.open_init()
        
        print(f' ~~~ initted termbar')
        self.refresh()
        self._start_time = time() # ignore shot_term 0.5 sec after start (to not override active_term by initial panel)
        
        #callback = lambda tag: (self.refresh(),
                                #app_proc(PROC_BOTTOMPANEL_REMOVE, 'Terminal'))
        #timer_proc(TIMER_START_ONE, callback, interval=150)

        
    def _init_terms(self, state):
        if state:
            # which to activate: 
            #   * last active for current tab
            #   * not current tab => just last active
            
            currentfilepath = ed.get_filename()
            if currentfilepath:
                currenttab_states = [ts for ts in self.state  if ts['filepath'] == currentfilepath]
                if currenttab_states:
                    max_lastactive = max((termstate['lastactive'] for termstate in currenttab_states))
                else:
                    max_lastactive = max((termstate['lastactive'] for termstate in state))
            else: # no-file tab
                max_lastactive = max((termstate['lastactive'] for termstate in state))
            
            for termstate in self.state:
                # create terminal
                shell = SHELL_UNIX #TODO fix temp
                term = Terminal(self.h_dlg, filepath=None, shell=SHELL_UNIX, font_size=self.font_size, 
                                    colmapfg=self.Cmd.colmapfg, colmapbg=self.Cmd.colmapbg, state=termstate)
                self.terminals.append(term)
                
                if termstate['lastactive'] == max_lastactive:
                    self.active_term = term
                
        else: # no state 
            # create no-file terminal
            term = Terminal(self.h_dlg, filepath=None, shell=SHELL_UNIX, font_size=self.font_size, 
                                colmapfg=self.Cmd.colmapfg, colmapbg=self.Cmd.colmapbg)
            self.terminals.append(term)
            self.active_term = term
            
        self._sort_terms(self.terminals)
        
        
    def open_init(self):
        colors = app_proc(PROC_THEME_UI_DICT_GET,'')
        color_btn_back = colors['ButtonBgPassive']['color']
        color_tab_passive = colors['TabPassive']['color']
        
        print(f' 1 initting terminal bar')
        n = dlg_proc(self.h_dlg, DLG_CTL_ADD, 'statusbar')
        dlg_proc(self.h_dlg, DLG_CTL_PROP_SET, index=n, prop={
            'name': 'statusbar',
            #'a_t': None,
            #'a_t': ('', '['),
            'a_l': ('', '['),
            'a_r': ('', ']'),
            #'a_b': ('input', '['),
            'sp_b': INPUT_H,
            'h': 20,
            'font_size': self.font_size,
            'color': color_btn_back,
            
            #'on_change': lambda *args,**vargs: print(f'  // statusbar: change: [{args}], [{vargs}]'), # no workee
            #'on_click': lambda *args,**vargs: ... # [(140617069637616, 2)], [{'data': (84, 10)}]
            
            # [(140617069637616, 2)], [{'data': {'btn': 1, 'state': '', 'x': 60, 'y': 9}}]
            'on_menu': f'module=cuda_terminal_plus;cmd=on_statusbar_menu;'
            })
        h_sb = dlg_proc(self.h_dlg, DLG_CTL_HANDLE, index=n)
        print(f' 2 initting terminal bar')

        ### Icons ###
        h_iml = imagelist_proc(-1, IMAGELIST_CREATE, value=self.h_dlg)
        statusbar_proc(h_sb, STATUSBAR_SET_IMAGELIST, value=h_iml)
        
        imagelist_proc(h_iml, IMAGELIST_SET_SIZE, (20,20))
        #self.sb_ics = {}
        self.statusbar_ic_inds = {} # name to imagelist idnex
        self.statusbar_ic_inds['ic_norm'] = imagelist_proc(h_iml, IMAGELIST_ADD, fn_icon_normal)
        self.statusbar_ic_inds['ic_dim'] = imagelist_proc(h_iml, IMAGELIST_ADD, fn_icon_dim)
        self.statusbar_ic_inds['ic_pluss'] = imagelist_proc(h_iml, IMAGELIST_ADD, fn_icon_pluss)
        self.statusbar_ic_inds['ic_cross'] = imagelist_proc(h_iml, IMAGELIST_ADD, fn_icon_cross)

        ### Plus, Spacer, Close ###
        # pluss
        cellind = statusbar_proc(h_sb, STATUSBAR_ADD_CELL, index=-1)
        statusbar_proc(h_sb, STATUSBAR_SET_CELL_IMAGEINDEX, index=cellind, value=self.statusbar_ic_inds['ic_pluss'])
        statusbar_proc(h_sb, STATUSBAR_SET_CELL_AUTOSIZE, index=cellind, value=True)
        statusbar_proc(h_sb, STATUSBAR_SET_CELL_COLOR_BACK, index=cellind, value=color_tab_passive)
        statusbar_proc(h_sb, STATUSBAR_SET_CELL_ALIGN, index=cellind, value='C')
        callback = f'module=cuda_terminal_plus;cmd=on_statusbar_cell_click;info=new_term;'
        statusbar_proc(h_sb, STATUSBAR_SET_CELL_CALLBACK, index=cellind, value=callback)
        
        # spacer
        cellind = statusbar_proc(h_sb, STATUSBAR_ADD_CELL, index=-1)
        statusbar_proc(h_sb, STATUSBAR_SET_CELL_AUTOSTRETCH, index=cellind, value=True)
        # cross
        cellind = statusbar_proc(h_sb, STATUSBAR_ADD_CELL, index=-1)
        statusbar_proc(h_sb, STATUSBAR_SET_CELL_IMAGEINDEX, index=cellind, value=self.statusbar_ic_inds['ic_cross'])
        statusbar_proc(h_sb, STATUSBAR_SET_CELL_AUTOSIZE, index=cellind, value=True)
        statusbar_proc(h_sb, STATUSBAR_SET_CELL_COLOR_BACK, index=cellind, value=color_tab_passive)
        statusbar_proc(h_sb, STATUSBAR_SET_CELL_ALIGN, index=cellind, value='C')
        callback = f'module=cuda_terminal_plus;cmd=close_all_terms_dlg;'
        statusbar_proc(h_sb, STATUSBAR_SET_CELL_CALLBACK, index=cellind, value=callback)
        
        self.sidebar_ic_inds = {}
        h_sbim = app_proc(PROC_SIDEPANEL_GET_IMAGELIST, '')
        self.sidebar_ic_inds['ic_normal'] = imagelist_proc(h_sbim, IMAGELIST_ADD, value=fn_icon_normal)
        self.sidebar_ic_inds['ic_dim'] = imagelist_proc(h_sbim, IMAGELIST_ADD, value=fn_icon_dim)
        
        return h_sb, h_iml
        
    def refresh(self):
        start_extras = 1 # non-terminal cells at start
        end_extras = 2 # at end
        
        needtermsn = len(self.terminals)
        termsn = statusbar_proc(self.h_sb, STATUSBAR_GET_COUNT) - start_extras - end_extras
        ####
        
        # proper number of cells
        if needtermsn > termsn: # need more terminals
            for i in range(needtermsn - termsn):
                add_ind = start_extras + termsn + i
                termind = add_ind - start_extras
                cellind = statusbar_proc(self.h_sb, STATUSBAR_ADD_CELL, index=add_ind, tag=termind)
                
                statusbar_proc(self.h_sb, STATUSBAR_SET_CELL_AUTOSIZE, index=cellind, value=True)
                callback = f'module=cuda_terminal_plus;cmd=on_statusbar_cell_click;info={termind};'
                statusbar_proc(self.h_sb, STATUSBAR_SET_CELL_CALLBACK, index=cellind, value=callback)
                statusbar_proc(self.h_sb, STATUSBAR_SET_CELL_ALIGN, index=cellind, value='C')
            
        elif needtermsn < termsn: # need less terms
            rem_ind = start_extras + needtermsn
            for i in range(termsn - needtermsn):
                statusbar_proc(self.h_sb, STATUSBAR_DELETE_CELL, index=rem_ind)
                
        for termind in range(len(self.terminals)):
            cellind = termind + start_extras
            hint = 'Terminal+: ' + self.terminals[termind].filepath
            statusbar_proc(self.h_sb, STATUSBAR_SET_CELL_HINT, index=cellind, value=hint)
        
        #statusbar_proc(h_sb, STATUSBAR_SET_CELL_TEXT, index=2, value='dbg')
        self._update_term_icons()
        self._update_statusbar_cells_bg()

    # [(140617069637616, 2, 2, 'ind2')], [{}]
    def on_statusbar_cell_click(self, id_dlg, id_ctl, data='', info=''):
        print(f' cell click:{id_dlg}, {id_ctl};; {data};; {info}')

        if info == 'new_term':
            self.new_term()
        else:
            clicked_ind = data
            print(f'clicked: {clicked_ind}({type(clicked_ind)}')
            self._show_terminal(clicked_ind)
        
    # data:{'btn': 1, 'state': '', 'x': 19, 'y': 6}
    def on_statusbar_menu(self, id_dlg, id_ctl, data='', info=''):
        #clicked_ind = data
        #print(f'clicked: id_ctl:{id_ctl};  data:{data};  info:{info}')
        click_x = data.get('x', 0)
        x = 0
        count = statusbar_proc(self.h_sb, STATUSBAR_GET_COUNT)
        for i in range(count):
            w = statusbar_proc(self.h_sb, STATUSBAR_GET_CELL_SIZE, index=i)
            if click_x <= (x + w):
                h_menu = menu_proc(0, MENU_CREATE)
                menu_proc(h_menu, MENU_ADD, command=2700, caption=f'Terminal {i-1} menu')
                menu_proc(h_menu, MENU_ADD, command=2700, caption='Rename')
                menu_proc(h_menu, MENU_ADD, command=2700, caption='Close')
                menu_proc(h_menu, MENU_SHOW)
                return
            x += w
            
    # force - if active terminal changed
    def _update_term_icons(self):
        start_extras = 1 # non-terminal cells at start
        end_extras = 2 # at end

        # delete extra panels
        if len(self.terminals) < len(self.sidebar_names):
            print(f' ==== removins sidebars: {len(self.sidebar_names)}: {self.sidebar_names}')
            todeln = len(self.sidebar_names) - len(self.terminals)
            for i in range(todeln):
                if len(self.sidebar_names) == 1: # to not remove last sidebar icon
                    break
                sidebar_name = self.sidebar_names.pop()
                app_proc(PROC_BOTTOMPANEL_REMOVE, sidebar_name)
            print(f'      new sidebar count: {len(self.sidebar_names)}: {self.sidebar_names}')
        
        taken_names = set()
                
        #active_term_sidebar_name = None
        # update cell icons  and add sidebar icons
        for i,term in enumerate(self.terminals):
            cellind = start_extras + i

            icon = self.statusbar_ic_inds['ic_norm']  if term == self.active_term else  self.statusbar_ic_inds['ic_dim']
            
            print(f' giving iucon to:{cellind} :: {icon}')
            statusbar_proc(self.h_sb, STATUSBAR_SET_CELL_IMAGEINDEX, index=cellind, value=icon)
            
            # sidebar
            
            panelname = 'Terminal+' if i == 0 else 'Terminal+'+str(i)
            tooltip = 'Terminal: '+term.filepath
            ind = 2
            while tooltip in taken_names:
                tooltip = 'Terminal '+ str(ind) + ": " + term.filepath
                ind += 1
            taken_names.add(tooltip)
            
            icon_path = fn_icon_normal if term == self.active_term else fn_icon_dim 
            if i >= len(self.sidebar_names):
                app_proc(PROC_BOTTOMPANEL_ADD_DIALOG, (panelname, self.h_dlg, icon_path))
                self.sidebar_names.append(panelname)
                
            sidebar_icon = self.sidebar_ic_inds['ic_normal']  if term == self.active_term else self.sidebar_ic_inds['ic_dim']
            app_proc(PROC_BOTTOMPANEL_SET_PROP, (panelname, sidebar_icon, tooltip))
            
        if not self.terminals:
            app_proc(PROC_BOTTOMPANEL_SET_PROP, 
                    (self.sidebar_names[0], self.sidebar_ic_inds['ic_normal'], 'Terminal+'))
            
            
    def _update_statusbar_cells_bg(self):
        if not hasattr(self, 'h_sb'):
            print(f' !! NO h_sb on cells bg update')
            return
            
        start_extras = 1 # non-terminal cells at start
        end_extras = 2 # at end
        
        colors = app_proc(PROC_THEME_UI_DICT_GET,'')
        color_tab_active = colors['TabActive']['color']
        color_tab_hover = colors['TabOver']['color']
        
        editor_filepath = ed.get_filename()
        
        for i,term in enumerate(self.terminals):
            cellind = i + start_extras
            is_for_cur_editor = term.filepath == editor_filepath
            col = color_tab_hover  if is_for_cur_editor else  color_tab_active
            statusbar_proc(self.h_sb, STATUSBAR_SET_CELL_COLOR_BACK, index=cellind, value=col)
            
            
    def _show_terminal(self, ind):
        self.Cmd.memo = None
        changing_term = False
        if self.active_term  and self.active_term != self.terminals[ind]:
            self.active_term.hide()
            changing_term = True
        
        self.active_term = self.terminals[ind]
        if not self.active_term.memo  or self.Cmd.memo != self.active_term.memo:
            self.active_term.show()
            self.Cmd.memo = self.active_term.memo
            
            # do not update sidebar if same term selected, otherwise - ACTIVATE -> show_terminal - loop
            #if changing_term:
            self._update_term_icons()

    
    # result of mouse click
    # ques action for later        
    def show_terminal(self, ind=None, name=None):
        if not self.terminals:
            print(f'termbar: show_terminal: NO TERMINALS')
            return
        if time() - self._start_time < 0.5:
            if self.terminals and self.active_term:
                self._show_terminal(self.terminals.index(self.active_term))
            return
        
        print(f' -- Show Term:{ind}, [{name}]')
        #if name == 'Terminal+': # first click
            #ind = self.terminals.index(self.active_term)
        #elif ind == None:
            #ind = self.sidebar_names.index(name)
        ind = 0  if name == 'Terminal+' else  int(name.split('Terminal+')[1])
        print(f'   => Show Term:{ind}, {name}')
        
        self._show_terminal(ind)
        
    def remove_term(self, term):
        term.close()
        if term.memo:
            dlg_proc(self.h_dlg, DLG_CTL_DELETE, name=term.memo_wgt_name)
            
        if term in self.terminals:
            self.terminals.remove(term)
            
        if self.active_term == term:
            self.active_term = None
        
    def close_all(self):
        for term in [*self.terminals]:
            self.remove_term(term)
        self.refresh()
        app_proc(PROC_BOTTOMPANEL_ACTIVATE, self.sidebar_names[0])
            
            
    def new_term(self):
        print(f' new term: curent file:{ed.get_filename()}')

        curfilepath = ed.get_filename()
        term = Terminal(self.h_dlg, filepath=curfilepath, shell=SHELL_UNIX, font_size=self.font_size, 
                            colmapfg=self.Cmd.colmapfg, colmapbg=self.Cmd.colmapbg)
        self.terminals.append(term)
        self._sort_terms(self.terminals)
        self.refresh()
        self._show_terminal(self.terminals.index(term))
        
    def _sort_terms(self, l):
        # sort no-file terms | terms with editor tabs | terms without editor tabs
        fileinds = {}
        for i,h in enumerate(ed_handles()):
            filepath = Editor(h).get_filename()
            fileinds[filepath] = i
        
        l.sort(key=lambda term: fileinds.get(term.filepath, (-1  if not term.filepath else 1000)))
        
    def timer_update(self):
        if not self.active_term:
            return False # do not update memo
            
        self.active_term.btextchanged = False
        if self.active_term.block.locked():
            self.active_term.block.release()
        sleep(0.03)
        self.active_term.block.acquire()
        return self.active_term.btextchanged
        
    def get_active_term(self):
        return self.active_term

    # list of term-dicts
    def get_state(self):
        l = []
        for term in self.terminals:
            l.append(term.get_state())
        return l

    def on_tab_reorder(self):
        self._sort_terms(self.terminals)
        self.refresh()
        self._show_terminal(self.terminals.index(term))
        
    def on_exit(self):
        for term in self.terminals:
            term.close()

class Command:
    
    def __init__(self):
        self.title = 'Terminal+'
        self.title_float = 'CudaText Terminal'
        self.hint_float = 'Terminal opened in floating window'
        self.h_dlg = None
    
        #terminal_w = 80
        self.terminal_w = 2048 # - unlimited?
        self.termbar = None
        
        if IS_WIN:
            global ENC
            ENC = ini_read(fn_config, 'op', 'encoding_windows', ENC)

        global MAX_BUFFER
        try:
            MAX_BUFFER = int(ini_read(fn_config, 'op', 'max_buffer_size', str(MAX_BUFFER)))
        except:
            pass

        self.shell_unix = ini_read(fn_config, 'op', 'shell_unix', SHELL_UNIX)
        self.shell_mac = ini_read(fn_config, 'op', 'shell_macos', SHELL_MAC)
        self.shell_win = ini_read(fn_config, 'op', 'shell_windows', SHELL_WIN)
        self.add_prompt = str_to_bool(ini_read(fn_config, 'op', 'add_prompt_unix', '1'))
        self.dark_colors = str_to_bool(ini_read(fn_config, 'op', 'dark_colors', '1'))
        self.floating = str_to_bool(ini_read(fn_config, 'op', 'floating_window', '0'))
        self.floating_topmost = str_to_bool(ini_read(fn_config, 'op', 'floating_window_topmost', '0'))

        try:
            self.font_size = int(ini_read(fn_config, 'op', 'font_size', '9'))
        except:
            pass

        try:
            self.max_history = int(ini_read(fn_config, 'op', 'max_history', '10'))
        except:
            pass

        self.load_history()
        self.h_menu = menu_proc(0, MENU_CREATE)

        #for-loop don't work here
        self.menu_calls = []
        self.menu_calls += [ lambda: self.run_cmd_n(0) ]
        self.menu_calls += [ lambda: self.run_cmd_n(1) ]
        self.menu_calls += [ lambda: self.run_cmd_n(2) ]
        self.menu_calls += [ lambda: self.run_cmd_n(3) ]
        self.menu_calls += [ lambda: self.run_cmd_n(4) ]
        self.menu_calls += [ lambda: self.run_cmd_n(5) ]
        self.menu_calls += [ lambda: self.run_cmd_n(6) ]
        self.menu_calls += [ lambda: self.run_cmd_n(7) ]
        self.menu_calls += [ lambda: self.run_cmd_n(8) ]
        self.menu_calls += [ lambda: self.run_cmd_n(9) ]
        self.menu_calls += [ lambda: self.run_cmd_n(10) ]
        self.menu_calls += [ lambda: self.run_cmd_n(11) ]
        self.menu_calls += [ lambda: self.run_cmd_n(12) ]
        self.menu_calls += [ lambda: self.run_cmd_n(13) ]
        self.menu_calls += [ lambda: self.run_cmd_n(14) ]
        self.menu_calls += [ lambda: self.run_cmd_n(15) ]
        self.menu_calls += [ lambda: self.run_cmd_n(16) ]
        self.menu_calls += [ lambda: self.run_cmd_n(17) ]
        self.menu_calls += [ lambda: self.run_cmd_n(18) ]
        self.menu_calls += [ lambda: self.run_cmd_n(19) ]
        self.menu_calls += [ lambda: self.run_cmd_n(20) ]
        self.menu_calls += [ lambda: self.run_cmd_n(21) ]


    def open_init(self):

        self.h_dlg = self.init_form()

        if self.floating:
            self.load_pos()
            dlg_proc(self.h_dlg, DLG_PROP_SET, prop={
                'border': DBORDER_SIZE,
                'cap': self.title_float,
                'x': self.wnd_x,
                'y': self.wnd_y,
                'w': self.wnd_w,
                'h': self.wnd_h,
                'topmost': self.floating_topmost,
            })
            dlg_proc(self.h_dlg, DLG_SHOW_NONMODAL)
            h_embed = dlg_proc(0, DLG_CREATE)
            n = dlg_proc(h_embed, DLG_CTL_ADD, prop='panel')
            dlg_proc(h_embed, DLG_CTL_PROP_SET, index=n, prop={
                'color': 0xababab,
                'cap': self.hint_float,
                'align': ALIGN_CLIENT,
            })
        else:
            h_embed = self.h_dlg

        app_proc(PROC_BOTTOMPANEL_ADD_DIALOG, (self.title, h_embed, fn_icon))

        #self.p = None
        #self.block = Lock() # locked by main mainly,  temporarily unlocked to let thread update .btext
        #return
        
        """self.block.acquire()
        self.btext = b''

        if IS_WIN:
            self.open_process()
            self.p.stdin.flush()
        else:
            # ch_pid - chilc process pid
            # ch_out - File-like object for I/O with the child process aka command.
            self.ch_pid, self.ch_out = self.open_terminal()
        
        self.CtlTh = ControlTh(self)
        self.CtlTh.start()"""

        timer_proc(TIMER_START, self.timer_update, 200, tag='')

    def init_form(self):

        colors = app_proc(PROC_THEME_UI_DICT_GET,'')
        color_btn_back = colors['ButtonBgPassive']['color']
        color_btn_font = colors['ButtonFont']['color']
        #color_tab_active = colors['TabActive']['color']
        color_tab_passive = colors['TabPassive']['color']
        #color_tab_hover = colors['TabOver']['color']

        cur_font_size = self.font_size

        h = dlg_proc(0, DLG_CREATE)
        dlg_proc(h, DLG_PROP_SET, prop={
            'border': False,
            'keypreview': True,
            'on_key_down': self.form_key_down,
            'on_show': self.form_show,
            'on_hide': self.form_hide,
            'color': color_btn_back,
            })

        n = dlg_proc(h, DLG_CTL_ADD, 'button_ex')
        dlg_proc(h, DLG_CTL_PROP_SET, index=n, prop={
            'name': 'break',
            'a_l': None,
            'a_t': None,
            'a_r': ('', ']'),
            'a_b': ('', ']'),
            'w': 90,
            'h': INPUT_H,
            'cap': 'Break',
            'hint': 'Hotkey: Break',
            'on_change': self.button_break_click,
            })

        n = dlg_proc(h, DLG_CTL_ADD, 'editor_combo')
        dlg_proc(h, DLG_CTL_PROP_SET, index=n, prop={
            'name': 'input',
            'border': True,
            'h': INPUT_H,
            'a_l': ('', '['),
            'a_r': ('break', '['),
            'a_t': ('break', '-'),
            'font_size': cur_font_size,
            'texthint': 'Enter command here',
            })
        self.input = Editor(dlg_proc(h, DLG_CTL_HANDLE, index=n))

        self.input.set_prop(PROP_ONE_LINE, True)
        self.input.set_prop(PROP_GUTTER_ALL, True)
        self.input.set_prop(PROP_GUTTER_NUM, False)
        self.input.set_prop(PROP_GUTTER_FOLD, False)
        self.input.set_prop(PROP_GUTTER_BM, False)
        self.input.set_prop(PROP_GUTTER_STATES, False)
        self.input.set_prop(PROP_UNPRINTED_SHOW, False)
        self.input.set_prop(PROP_MARGIN, 2000)
        self.input.set_prop(PROP_MARGIN_STRING, '')
        self.input.set_prop(PROP_HILITE_CUR_LINE, False)
        self.input.set_prop(PROP_HILITE_CUR_COL, False)

        self.upd_history_combo()
        
        termsstate = self._load_state()
        self.termbar = TerminalBar(h, plugin=self, state=termsstate, font_size=self.font_size)

        dlg_proc(h, DLG_SCALE)
        return h
        
        
    def open(self):
        print(f'CMD:open(')


        #dont init form twice!
        if not self.h_dlg:
            self.open_init()

        dlg_proc(self.h_dlg, DLG_CTL_FOCUS, name='input')

        if self.floating:
            # form can be hidden before, show
            dlg_proc(self.h_dlg, DLG_SHOW_NONMODAL)
            # via timer, to support clicking sidebar button
            timer_proc(TIMER_START, self.dofocus, 300, tag='')
        # WTF - Fatal Python error: Cannot recover from stack overflow.
        else:
            app_proc(PROC_BOTTOMPANEL_ACTIVATE, (self.title, True)) #True - set focus


    def exec(self, s):
        term = self.termbar.get_active_term()
        
        if IS_WIN:
            if term.p and s:
                term.p.stdin.write((s+'\n').encode(ENC))
                term.p.stdin.flush()
        else:
            if term.ch_out and s:
                term.ch_out.write((s+'\n').encode(ENC))


    def config(self):

        ini_write(fn_config, 'op', 'shell_windows', self.shell_win)
        ini_write(fn_config, 'op', 'shell_unix', self.shell_unix)
        ini_write(fn_config, 'op', 'shell_macos', self.shell_mac)
        ini_write(fn_config, 'op', 'add_prompt_unix', bool_to_str(self.add_prompt))
        ini_write(fn_config, 'op', 'dark_colors', bool_to_str(self.dark_colors))
        ini_write(fn_config, 'op', 'floating_window', bool_to_str(self.floating))
        ini_write(fn_config, 'op', 'floating_window_topmost', bool_to_str(self.floating_topmost))
        ini_write(fn_config, 'op', 'max_history', str(self.max_history))
        ini_write(fn_config, 'op', 'font_size', str(self.font_size))
        ini_write(fn_config, 'op', 'max_buffer_size', str(MAX_BUFFER))
        if IS_WIN:
            ini_write(fn_config, 'op', 'encoding_windows', ENC)

        file_open(fn_config)


    def _load_state(self):
        if os.path.exists(fn_state):
            with open(fn_state, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []
        
    def _save_state(self):
        state = self.termbar.get_state()
        
        with open(fn_state, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2)


    def timer_update(self, tag='', info=''):
        changed = self.termbar.timer_update()
        
        # log("Entering in timer_update")
        if changed:
            #self.update_output(self.btext.decode(ENC))
            self.update_output()

    def show_history(self):

        menu_proc(self.h_menu, MENU_CLEAR)
        for (index, item) in enumerate(self.history):
            menu_proc(self.h_menu, MENU_ADD,
                index=0,
                caption=item,
                command=self.menu_calls[index],
                )

        prop = dlg_proc(self.h_dlg, DLG_CTL_PROP_GET, name='input')
        x, y = prop['x'], prop['y']
        x, y = dlg_proc(self.h_dlg, DLG_COORD_LOCAL_TO_SCREEN, index=x, index2=y)
        menu_proc(self.h_menu, MENU_SHOW, command=(x, y))


    #def is_sudo_input(self):

    def run_cmd(self, text):

        text = text.lstrip(' ')

        if text==BASH_CLEAR:
            self.btext = b''
            #self.memo.set_prop(PROP_RO, False)
            #self.memo.set_text_all('')
            #self.memo.set_prop(PROP_RO, True)
            #return

        while len(self.history) >= self.max_history:
            del self.history[0]

        try:
            n = self.history.index(text)
            del self.history[n]
        except:
            pass

        self.history += [text]
        self.upd_history_combo()
        self.input.set_text_all('')

        sudo = not IS_WIN and text.startswith('sudo ')
        if sudo:
            text = 'sudo --stdin '+text[5:]

        self.exec(text)

        #sleep(0.05)


    def run_cmd_n(self, n):

        if n<len(self.history):
            s = self.history[n]
            self.input.set_text_all(s)
            self.input.set_caret(len(s), 0)


    # called on timer, if .btext changed
    def update_output(self):
        full_text, range_lists = self.parse_ansi_lines()
        
        self.memo.set_prop(PROP_RO, False)
        self.memo.set_text_all(full_text)
        self.apply_colors(range_lists)
        self.memo.set_prop(PROP_RO, True)

        self.memo.cmd(cmds.cCommand_GotoTextEnd)
        self.memo.set_prop(PROP_LINE_TOP, self.memo.get_line_count()-3)

    def apply_colors(self, range_lists):
        # range_lists - map: (fg,bg,isbold) -> (xs,ys,lens)
        for (fg,bg,isbold),(xs,ys,lens) in range_lists.items():
            fgcol = self.colmapfg.get(fg, self.broke_col)
            bgcol = self.colmapbg.get(bg, self.broke_col)
            font_bold = 1 if isbold else 0
            
            self.memo.attr(MARKERS_ADD_MANY, x=xs, y=ys, len=lens,
                        color_font=fgcol, color_bg=bgcol, font_bold=font_bold)

    
    # cache - save parsed lines
    _ansicache = {} # byte line -> [(plain_str, color_ranges), ...]  # splitted by terminal width
    '!!! clear cache'
    def parse_ansi_lines(self):
        """ parses terminal output bytes line-by-line, caching parsing-results per line
        """
        term = self.termbar.get_active_term()
        blines = term.btext.split(b'\n')
        
        res = []          
        for bline in blines:
            if bline in term._ansicache:
                collines_l = term._ansicache[bline]
                res.extend(collines_l)
            else:
                if not bline: #TODO do better
                    continue
                    
                line = bline.decode(ENC)
                
                terminal = AnsiParser(columns=len(line), lines=1, p_in=None)
                terminal.screen.dirty.clear()
                terminal.feed(bline)
                tiles = terminal.get_line_tiles() # (data, fg, bg, bold, reverse) 
                
                collines_l = []
                nlines = (len(tiles)-1) // self.terminal_w + 1
                for i in range(nlines):
                    line_tiles = tiles[i*self.terminal_w : (i+1)*self.terminal_w]
                  
                    plain_str = ''.join((tile[0] for tile in line_tiles)).rstrip()
                    color_ranges = self._get_color_ranges(line_tiles)
                
                    colored_line = (plain_str, color_ranges)
                    res.append(colored_line)
                    collines_l.append(colored_line)
                    
                term._ansicache[bline] = collines_l 
        
        full_text = '\n'.join((item[0] for item in res))
        
        # for MARKERS_ADD_MANY
        range_lists = {} # (fg,bg,isbold) -> (xs,ys,lens)
        for i,(s,crs) in enumerate(res):
            for cr in crs:
                key = (cr.fgcol, cr.bgcol, cr.isbold)
                xs,ys,lens = range_lists.setdefault(key, ([],[],[])) 
                xs.append(cr.start)
                ys.append(i)
                lens.append(cr.length)
        
        return full_text, range_lists
        
        
    def _get_color_ranges(self, tiles):
        range_start = -1
        fg = DEFAULT_FGCOL
        bg = DEFAULT_BGCOL
        isbold = False
        l = []
        for i,(ch, tfg, tbg, tbold, treverse) in enumerate(tiles):
            if fg != tfg  or bg != tbg  or tbold != isbold: # new color range
                # finish previous color range
                if fg != DEFAULT_FGCOL  or bg != DEFAULT_BGCOL  or isbold: # wasnt plain text-range
                    l.append(ColorRange(start=range_start, length=i-range_start, fgcol=fg, bgcol=bg, isbold=isbold))
                range_start = i
                fg = tfg
                bg = tbg
                isbold = tbold
        # add last range  if any
        if fg != DEFAULT_FGCOL  or bg != DEFAULT_BGCOL  or isbold:
            l.append(ColorRange(start=range_start, length=len(tiles)-range_start, fgcol=fg, bgcol=bg, isbold=isbold))
        return l    
        
    tag = 123456
    broke_col = 0xff007f # pink
    
    colmapfg = { # xterm... https://en.wikipedia.org/wiki/ANSI_escape_code#Colors
        'black': 0x36342e, # black     0 0 0
        'red': 0x0000cc, # red       205,0,0
        'green': 0x69a4e, # green     0 205 0
        'brown': 0x00a0c4, # yellow    205 205 0
        'blue': 0xa46534, # blue      0 0 238
        'magenta': 0x7b5075, # magenta   205 0 205
        'cyan': 0x9a9806, # cyan      0 205 205
        'white': 0xcfd7d3, # white     229 229 229
        
        'brightblack': 0x535755, #### bblack 127 127 127 (bright)
        'brightred': 0x2929ef, # bred      255 0 0
        'brightgreen': 0x34e28a, # bgreen    0 255 0
        'brightbrown': 0x4fe9fc, # byellow   255 255 0
        'brightblue': 0xcf9f72, # bblue     92 92 255
        'brightmagenta': 0xa87fad, # bmagenta  255 0 255
        'brightcyan': 0xe2e234, # bcyan     0 255 255
        'brightwhite': 0xeceeee, # bwhite    255 255 255
        
        'default': 0xcfd7d3, # white     229 229 229
    }
    colmapbg = { 
        'black': 0x36342e, 
        'red':  0x0000cc,
        'green':  0x69a4e,
        'brown':  0x00a0c4,
        'blue':  0xa46534,
        'magenta':  0x7b5075,
        'cyan':  0x9a9806,
        'white':  0xcfd7d3,
        
        'brightblack': 0x535755,
        'brightred': 0x2929ef,
        'brightgreen': 0x34e28a,
        'brightbrown': 0x4fe9fc,
        'brightblue': 0xcf9f72,
        'bfightmagenta': 0xa87fad,
        'brightcyan': 0xe2e234,
        'brightwhite': 0xeceeee,
        
        'default': 0x240a30, # purple from ubuntu theme
    }

    def load_pos(self):

        if not self.floating:
            return
        self.wnd_x = int(ini_read(fn_config, 'pos', 'x', '20'))
        self.wnd_y = int(ini_read(fn_config, 'pos', 'y', '20'))
        self.wnd_w = int(ini_read(fn_config, 'pos', 'w', '700'))
        self.wnd_h = int(ini_read(fn_config, 'pos', 'h', '400'))


    def save_pos(self):

        if not self.floating:
            return

        p = dlg_proc(self.h_dlg, DLG_PROP_GET)
        x = p['x']
        y = p['y']
        w = p['w']
        h = p['h']

        ini_write(fn_config, 'pos', 'x', str(x))
        ini_write(fn_config, 'pos', 'y', str(y))
        ini_write(fn_config, 'pos', 'w', str(w))
        ini_write(fn_config, 'pos', 'h', str(h))


    def upd_history_combo(self):

        self.input.set_prop(PROP_COMBO_ITEMS, '\n'.join(self.history))


    def load_history(self):

        self.history = []
        for i in range(self.max_history):
            s = ini_read(fn_config, 'history', str(i), '')
            if s:
                self.history += [s]


    def save_history(self):

        ini_proc(INI_DELETE_SECTION, fn_config, 'history')
        for (i, s) in enumerate(self.history):
            ini_write(fn_config, 'history', str(i), s)


    def stop(self):
        if IS_WIN:    
            try:
                if self.p:
                    self.p.terminate()
                    self.p.wait()
            except:
                pass
        
        
    def on_statusbar_cell_click(self, id_dlg, id_ctl, data='', info=''):
        self.termbar.on_statusbar_cell_click(id_dlg, id_ctl, data, info)
        
    def on_statusbar_menu(self, id_dlg, id_ctl, data='', info=''):
        self.termbar.on_statusbar_menu(id_dlg, id_ctl, data, info)

    def close_all_terms_dlg(self, id_dlg, id_ctl, data='', info=''):
        answer = msg_box('Close all terminals?', MB_OK|MB_OKCANCEL |MB_ICONWARNING)
        if answer == ID_OK:
            self.termbar.close_all()


    # active editor tab changed
    def on_tab_change(self, ed_self):
        if not self.termbar:
            return
            
        active_panel = app_proc(PROC_BOTTOMPANEL_GET, '')
        
        if active_panel not in self.termbar.sidebar_names:
            return
        
        self.termbar._update_statusbar_cells_bg()
        self.termbar._update_term_icons()

    # on_tab_move(self, ed_self)
    def on_tab_move(self, ed_self):
        if self.termbar:
            self.termbar.on_tab_reorder()
        
    def form_key_down(self, id_dlg, id_ctl, data='', info=''):

        #Enter
        if (id_ctl==keys.VK_ENTER) and (data==''):
            text = self.input.get_text_line(0)
            self.input.set_text_all('')
            self.input.set_caret(0, 0)
            self.run_cmd(text)
            return False

        #Up/Down: scroll memo
        if (id_ctl==keys.VK_UP) and (data==''):
            self.memo.cmd(cmds.cCommand_ScrollLineUp)
            return False

        if (id_ctl==keys.VK_DOWN) and (data==''):
            self.memo.cmd(cmds.cCommand_ScrollLineDown)
            return False

        #PageUp/PageDown: scroll memo
        if (id_ctl==keys.VK_PAGEUP) and (data==''):
            self.memo.cmd(cmds.cCommand_ScrollPageUp)
            return False

        if (id_ctl==keys.VK_PAGEDOWN) and (data==''):
            self.memo.cmd(cmds.cCommand_ScrollPageDown)
            return False

        #Ctrl+Down: history menu
        if (id_ctl==keys.VK_DOWN) and (data=='c'):
            self.show_history()
            return False

        #Escape: go to editor
        if (id_ctl==keys.VK_ESCAPE) and (data==''):
            # Stops the timer
            timer_proc(TIMER_STOP, self.timer_update, 0)
            ed.focus()
            ed.cmd(cmds.cmd_ToggleBottomPanel)
            return False

        #Break (cannot react to Ctrl+Break)
        if (id_ctl==keys.VK_PAUSE):
            self.button_break_click(0, 0)
            return False


    def form_hide(self, id_dlg, id_ctl, data='', info=''):
        timer_proc(TIMER_STOP, self.timer_update, 0)


    def form_show(self, id_dlg, id_ctl, data='', info=''):
        term_name = app_proc(PROC_BOTTOMPANEL_GET, "")
        print(f'!on FORM_SHOW: term show: {term_name}')
        if self.termbar:
            self.termbar.show_terminal(name=term_name)

        timer_proc(TIMER_START, self.timer_update, 300, tag='')

    #TODO add on_show
    """def on_resize(self, id_dlg, id_ctl, data='', info=''):
        info = self.memo.get_prop(PROP_SCROLL_HORZ_INFO)
        new_term_w = info['page']
        if new_term_w != self.terminal_w:
            self.terminal_w = new_term_w
            print(f'resize: term_w:{self.terminal_w}')
            self._ansicache.clear()
            self.update_output('') #TODO fix arg, remove call decode, encoding ENC?"""
 

    def on_exit(self, ed_self):
        self._save_state()

        timer_proc(TIMER_STOP, self.timer_update, 0)
        self.stop()
        
        self.termbar.on_exit()
        
        self.save_pos()
        self.save_history()


    #TODO implement
    def button_break_click(self, id_dlg, id_ctl, data='', info=''):
        self.stop()
        self.open_process()


    def dofocus(self, tag='', info=''):

        timer_proc(TIMER_STOP, self.dofocus, 0)
        dlg_proc(self.h_dlg, DLG_FOCUS)


class AnsiParser:

    def __init__(self, columns, lines, p_in):
        '!!! investigate init'
        self.screen = HistoryScreen(columns, lines)
        self.screen.set_mode(pyte.modes.LNM)
        self.screen.write_process_input = lambda data: p_in.write(data.encode())
            
        #self.stream = pyte.ByteStream()
        self.stream = ByteStream()
        self.stream.attach(self.screen)

    def feed(self, data):
        self.stream.feed(data)

    # char:  bg, bold, count, data, fg, index, italics, reverse, strikethrough, underscore
    def get_indexed_lines(self, ):
        cursor = self.screen.cursor
        lines = []
        for y in self.screen.dirty:
            line = self.screen.buffer[y]
            data = [(char.data, char.fg, char.bg, char.bold, char.reverse)
                    for char in (line[x] for x in range(self.screen.columns))]
            lines.append((y, data))

        self.screen.dirty.clear()
        return lines

    def get_line_tiles(self):
        tiles = [(char.data, char.fg, char.bg, char.bold, char.reverse)
                    for char in self.screen.buffer[0].values()]
        return tiles
