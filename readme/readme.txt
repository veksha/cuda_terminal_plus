Plugin for CudaText.
"Terminal Plus" gives Terminal emulation, it's continuation of plugin "Terminal".
On Linux (maybe other Unixes too) it supports colored output in terminal.
On Windows colors are not supported, because it's not needed much
(only few PowerShell commands give colored output).

Plugin gives its panel in the CudaText bottom panel.
Plugin shows its own statusbar (inside its panel) with cells for all opened terminals.
Additionally plugin shows buttons on CudaText sidebar, one button per terminal.
Ie it shows 2 equal rows of buttons, but it may be useful if CudaText sidebar is hidden.

Plugin maps its terminals to documents: it remembers which terminal is opened for which document, 
so toggling of terminal will activate current document's terminal.

Plugin commands
---------------
- Add free terminal (not bound to any document, opens in user's home directory)
- Add terminal for current document (document may have multiple terminals)

- Close active terminal
- Close last used terminal for current document
- Close all terminals.
    
- Focus next terminal
- Focus previous terminal
  
- Rename terminal
- Switch focus between current document and its last used terminal
- Run selected text in the active terminal
    Ignores multi-line selection.
    Ignores multi-carets.
    If no selection, runs current line and moves editor caret to the next line. 
    
- Rename active terminal.
- Search for command in global history


Plugin features
---------------

Plugin loads ~/.bashrc if Bash is used, so Bash aliases must work.

Terminal context menu allows to rename terminal, change its icon and wrap mode, or close it.

Custom icons with the resolution of 20x20 may be placed into CudaText directory: 'data/terminalicons'

Plugin shows special cells in the statusbar:
    "+": runs command "Add terminal for current document",
    "x": runs command "Close all terminals".

Terminals are restored after program restart, the state is saved to file 'cuda_terminal_plus_state.json'
in the CudaText 'settings' directory.


Plugin options
--------------

- 'shell_windows', 'shell_unix', 'shell_macos': shell start command for designated OS types. May include arguments.
- 'start_dir': working directory of new terminals. 
    Possible values:
        * 'file' - in document's directory
        * 'project' - in current project's main-file's directory 
        * 'user' - in user's home directory

- 'floating_window': show plugin in a separate window.
+ 'floating_window_topmost': should floating window be 'always on top'.
- 'layout_horizontal': places terminals bar to the right of the input. Values are 0 to disable, 1 to enable.
- 'font_size': terminal font size
- 'shell_theme_fg': terminal text colors: comma separated list of html colors in this order:
    * black,red,green,brown,blue,magenta,cyan,white,brightblack,brightred,brightgreen,brightbrown,brightblue,brightmagenta,brightcyan,brightwhite,default
- 'shell_theme_bg': terminal background colors. same format as 'shell_theme_fg'.
- 'terminal_bg_zebra': difference in "brightness" between adjacent groups of terminal tabs of different inactive documents. Accepted values are between 0 (no difference in color) and 50.
- 'wrap': 

- 'max_buffer_size': limit amount of text displayed in the terminal at once (in bytes)
- 'local_history': max number of commands saved in the terminal's local history. 0 to disable.
- 'global_history': max number of commands saved in plugin's global history (Accessed via command: 'Search for command in global history')


About
-----

Author: Shovel (CudaText forum user, https://github.com/halfbrained/ )
Based on some parts of "Terminal" by Artem Gavrilov & Alexey Torgashin.
License: MIT