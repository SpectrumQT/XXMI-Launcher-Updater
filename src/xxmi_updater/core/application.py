import argparse
import sys
import logging
import traceback
import re
import os
import time

from typing import Union, Callable
from enum import Enum
from dataclasses import dataclass
from threading import Thread, current_thread, main_thread
from queue import Queue, Empty
from pathlib import Path

import core.path_manager as Paths
import core.event_manager as Events
import core.config_manager as Config

from core.package_manager import PackageManager

from core.packages.launcher_package import LauncherPackage


class Mode(Enum):
    Install = 'Installer'
    Update = 'Updater'

    def __str__(self):
        return self.value


class Channel(Enum):
    MSI = 'MSI'
    ZIP = 'ZIP'

    def __str__(self):
        return self.value


@dataclass
class ApplicationEvents:

    @dataclass
    class ConfigUpdate:
        pass

    @dataclass
    class Ready:
        pass

    @dataclass
    class Busy:
        pass

    @dataclass
    class StatusUpdate:
        status: str

    @dataclass
    class MoveWindow:
        offset_x: int
        offset_y: int

    @dataclass
    class Minimize:
        pass

    @dataclass
    class Maximize:
        pass

    @dataclass
    class Close:
        delay: int = 0

    @dataclass
    class Update:
        no_install: bool = False
        force: bool = False
        reinstall: bool = False
        packages: Union[list, None] = None
        silent: bool = False
        no_thread: bool = False

    @dataclass
    class CheckForUpdates:
        pass

    @dataclass
    class WaitForProcess:
        process_name: str

    @dataclass
    class WaitForProcessExit:
        process_name: str

    @dataclass
    class ShowMessage:
        modal: bool = False
        icon: str = 'info-icon.ico'
        title: str = 'Message'
        message: str = '< Text >'
        confirm_text: str = 'OK'
        confirm_command: Union[Callable, None] = None
        cancel_text: str = ''
        cancel_command: Union[Callable, None] = None
        lock_master: bool = None
        screen_center: bool = None

    @dataclass
    class ShowError(ShowMessage):
        icon: str = 'error-icon.ico'
        title: str = 'Error'

    @dataclass
    class ShowWarning(ShowMessage):
        icon: str = 'warning-icon.ico'
        title: str = 'Warning'

    @dataclass
    class ShowInfo(ShowMessage):
        icon: str = 'info-icon.ico'
        title: str = 'Info'

    @dataclass
    class ShowDialogue(ShowMessage):
        confirm_text: str = 'Confirm'
        cancel_text: str = 'Cancel'

    @dataclass
    class VerifyFileAccess:
        path: Path
        abs_path: bool = True
        read: bool = True
        write: bool = False
        exe: bool = False

    @dataclass
    class InstallLauncher:
        pass


class Application:
    def __init__(self, app_gui):
        self.is_alive = True
        self.gui = app_gui
        self.instance = self.get_instance()

        parser = argparse.ArgumentParser(description='Installs and updates XXMI Launcher')
        parser.add_argument('-m', '--mode', type=Mode, choices=list(Mode), default=Mode.Install,
                            help='Switch between "Installer" and "Updater" modes')
        parser.add_argument('-c', '--channel', type=Channel, choices=list(Channel), default=Channel.MSI,
                            help='Switch between "MSI" and "ZIP" installation channels')
        parser.add_argument('-d', '--dist_dir', type=str, default=Path.home() / 'AppData' / 'Roaming' / 'XXMI Launcher',
                            help='Launcher installation directory')
        parser.add_argument('-s', '--shortcut', type=bool, default=True,
                            help='Default state of "Create Desktop Shortcut" checkbox')
        self.args = parser.parse_args()

        Config.Config.load()

        Config.Launcher.update_channel = str(self.args.channel)
        Config.Launcher.installation_dir = str(self.args.dist_dir)
        # Config.Launcher.create_shortcut = self.args.shortcut and self.args.mode != Mode.Update
        Config.Launcher.instance = self.instance

        self.threads = []
        self.error_queue = Queue()

        self.mode = self.args.mode

        self.packages = [
            LauncherPackage(),
        ]

        self.package_manager = PackageManager(self.packages)

        Events.Subscribe(Events.Application.InstallLauncher, lambda event: self.install_launcher())

        self.gui.initialize()

        if self.args.mode == Mode.Install:
            Events.Fire(Events.Application.Ready())
        elif self.args.mode == Mode.Update:
            self.install_launcher()

        self.check_threads()

        self.gui.open()

        self.exit()

    def install_launcher(self):
        self.run_as_thread(self.package_manager.update_packages, force=True, reinstall=True, packages=['Launcher'])

    def in_updater_mode(self):
        return self.mode == Mode.Update

    def get_instance(self):
        instances = {
            r'.*(WW).*': 'WWMI',
            r'.*(ZZZ).*': 'ZZMI',
            r'.*(HSR).*': 'SRMI',
            r'.*(GI).*': 'GIMI',
        }
        exe_name = Path(sys.executable).name
        for pattern, instance in instances.items():
            if len(re.compile(pattern).findall(exe_name)):
                return instance
        return None

    def run_as_thread(self, callback, *args, **kwargs):
        def wrap_errors(func, *func_args, **func_kwargs):
            try:
                func(*func_args, **func_kwargs)
            except Exception as e:
                self.error_queue.put_nowait((e, traceback.format_exc()))
        thread = Thread(target=wrap_errors, args=(callback, *args), kwargs=kwargs)
        self.threads.append(thread)
        thread.start()

    def check_threads(self):
        self.gui.after(50, self.check_threads)
        # Remove finished threads from the list
        self.threads = [thread for thread in self.threads if thread.is_alive()]
        # Raise exceptions sent to error queue by threads
        try:
            if self.gui.state() != 'normal':
                return
            self.report_thread_error()
            # raise exception
        except Empty:
            pass

    def report_thread_error(self):
        (error, trace) = self.error_queue.get_nowait()
        logging.error(trace)
        self.gui.show_messagebox(Events.Application.ShowError(
            modal=True,
            screen_center=not self.gui.is_shown(),
            lock_master=self.gui.is_shown(),
            message=str(error),
        ))
        if self.gui.is_shown():
            self.gui.after(100, Events.Fire, Events.Application.Ready())

    def watchdog(self, timeout: int = 15):
        timeout = time.time() + timeout
        while True:
            time.sleep(0.1)
            if not self.is_alive:
                return
            if time.time() > timeout:
                break
        logging.error('[WATCHDOG]: Shutting down stuck process...')
        os._exit(os.EX_OK)

    def exit(self):
        try:
            assert current_thread() is main_thread()
        except Exception as e:
            self.error_queue.put_nowait((e, traceback.format_exc()))
        # Start watchdog to forcefully shutdown process in 5 seconds
        watchdog_thread = Thread(target=self.watchdog, kwargs={'timeout': 5})
        watchdog_thread.start()
        # Join active threads
        logging.debug(f'Joining threads...')
        for thread in self.threads:
            thread.join()
        # Join watchdog thread
        logging.debug(f'Joining watchdog thread...')
        self.is_alive = False
        watchdog_thread.join()
        # Report any errors left in queue
        while True:
            try:
                self.report_thread_error()
            except Empty:
                break
        logging.debug(f'App Exit')
        os._exit(os.EX_OK)
