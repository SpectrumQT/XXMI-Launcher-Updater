import sys
import logging
import multiprocessing

from pathlib import Path


if __name__ == '__main__':
    # Multiprocessing support for Pyinstaller
    multiprocessing.freeze_support()

    if '__compiled__' in globals():
        # Nuitka (release build): `XXMI Updater\XXMI Updater.exe`
        root_path = Path(sys.executable).parent
    elif getattr(sys, 'frozen', False):
        # Pyinstaller (debug build): `XXMI Updater\XXMI Updater.exe`
        root_path = Path(sys.executable).parent
    else:
        # Python (native): `XXMI Updater\src\xxmi_updater\app.py`
        root_path = Path(__file__).resolve().parent.parent.parent

    logging.basicConfig(filename=root_path / f'XXMI Updater Log.txt',
                        encoding='utf-8',
                        filemode='a',
                        format='%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s',
                        level=logging.DEBUG)

    logging.debug(f'App Start')

    try:
        import core.path_manager as Paths
        Paths.initialize(root_path)

        from gui.windows.main.main_window import MainWindow
        gui = MainWindow()

        import core.event_manager as Events

        from core.application import Application
        Application(gui)

    except Exception as e:
        logging.exception(e)

        gui.show_messagebox(Events.Application.ShowError(
            modal=True,
            screen_center=True,
            lock_master=False,
            message=str(e),
        ))
