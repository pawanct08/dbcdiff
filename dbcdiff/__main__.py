import sys

# If the only argument is --file-a <path> (launched from Explorer context menu)
# open the GUI with that file pre-loaded; otherwise fall through to the CLI.
if len(sys.argv) == 3 and sys.argv[1] == "--file-a":
    from dbcdiff.gui import launch_gui
    launch_gui(preload_a=sys.argv[2])
elif len(sys.argv) > 1:
    from dbcdiff.cli import main
    sys.exit(main())
else:
    from dbcdiff.gui import launch_gui
    launch_gui()
