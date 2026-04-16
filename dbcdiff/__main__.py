import sys

if len(sys.argv) > 1:
    from dbcdiff.cli import main
    sys.exit(main())
else:
    from dbcdiff.gui import launch_gui
    launch_gui()
