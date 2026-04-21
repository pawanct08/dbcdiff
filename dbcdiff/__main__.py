import sys


def _hide_console() -> None:
    """Hide the console window when running as a packaged GUI app on Windows.

    This is needed because we build without --windowed so the CLI path can
    write to the terminal.  When the user double-clicks the exe or uses the
    --file-a flag we hide the console so it doesn't flash on screen.
    """
    try:
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE
    except Exception:
        pass  # Non-Windows or no console attached


# If the only argument is --file-a <path> (launched from Explorer context menu)
# open the GUI with that file pre-loaded; otherwise fall through to the CLI.
if len(sys.argv) == 3 and sys.argv[1] == "--file-a":
    _hide_console()
    from dbcdiff.gui import launch_gui
    launch_gui(preload_a=sys.argv[2])
elif len(sys.argv) > 1:
    from dbcdiff.cli import main
    sys.exit(main())
else:
    _hide_console()
    from dbcdiff.gui import launch_gui
    launch_gui()
