# This file is part of webmacs.
#
# webmacs is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# webmacs is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with webmacs.  If not, see <http://www.gnu.org/licenses/>.

import os
import sys
import logging

from PyQt5.QtCore import pyqtSlot as Slot

from PyQt5.QtWebEngineWidgets import QWebEngineSettings
from PyQt5.QtWebEngineCore import QWebEngineUrlRequestInterceptor
from PyQt5.QtWidgets import QApplication
from PyQt5.QtNetwork import QNetworkAccessManager

from . import require
from .version import opengl_vendor
from .adblock import Adblocker, AdblockUpdateRunner
from .download_manager import DownloadManager
from .profile import default_profile
from .minibuffer.right_label import init_minibuffer_right_labels
from .keyboardhandler import LOCAL_KEYMAP_SETTER
from .spell_checking import SpellCheckingUpdateRunner, \
    spell_checking_dictionaries
from .runnable import run


if sys.platform.startswith("linux"):
    # workaround for a nvidia issue
    # see https://bugs.launchpad.net/ubuntu/+source/python-qt4/+bug/941826
    import ctypes
    import ctypes.util
    ctypes.CDLL(ctypes.util.find_library("GL"), mode=ctypes.RTLD_GLOBAL)


THIS_DIR = os.path.dirname(os.path.realpath(__file__))


class UrlInterceptor(QWebEngineUrlRequestInterceptor):
    def __init__(self, app):
        QWebEngineUrlRequestInterceptor.__init__(self)
        self._adblock = Adblocker(app.adblock_path()).local_adblock()
        self._use_adblock = True

    @Slot(object)
    def update_adblock(self, adblock):
        self._adblock = adblock

    def toggle_use_adblock(self):
        self._use_adblock = not self._use_adblock

    def interceptRequest(self, request):
        url = request.requestUrl()
        url_s = url.toString()
        if self._use_adblock and self._adblock.matches(
                url_s,
                request.firstPartyUrl().toString(),):
            logging.info("filtered: %s", url_s)
            request.block(True)


def app():
    return Application.INSTANCE


def _app_requires():
    require(".keymaps.global")
    require(".keymaps.caret_browsing")
    require(".keymaps.content_edit")
    require(".keymaps.fullscreen")

    require(".commands.follow")
    require(".commands.buffer_history")
    require(".commands.global")
    require(".commands.isearch")
    require(".commands.webbuffer")
    require(".commands.caret_browsing")
    require(".commands.content_edit")

    require(".default_webjumps")


class Application(QApplication):
    INSTANCE = None

    def __init__(self, args):
        QApplication.__init__(self, args)
        self.__class__.INSTANCE = self

        if (opengl_vendor() == 'nouveau' and
            not (os.environ.get('LIBGL_ALWAYS_SOFTWARE') == '1'
                 or 'QT_XCB_FORCE_SOFTWARE_OPENGL' in os.environ)):
            sys.exit(
                "You are using the nouveau graphics driver but it"
                " has issues with multithreaded opengl. You must"
                " use another driver or set the variable environment"
                " QT_XCB_FORCE_SOFTWARE_OPENGL to force software"
                " opengl. Note that it might be slow, depending"
                " on your hardware."
            )

        self._setup_conf_paths()

        self._interceptor = UrlInterceptor(self)

        self._download_manager = DownloadManager(self)

        self.profile = default_profile()
        self.profile.enable(self)

        settings = QWebEngineSettings.globalSettings()
        settings.setAttribute(
            QWebEngineSettings.LinksIncludedInFocusChain, False,
        )
        settings.setAttribute(
            QWebEngineSettings.PluginsEnabled, True,
        )
        settings.setAttribute(
            QWebEngineSettings.FullScreenSupportEnabled, True,
        )
        settings.setAttribute(
            QWebEngineSettings.JavascriptCanOpenWindows, True,
        )

        self.installEventFilter(LOCAL_KEYMAP_SETTER)

        self.setQuitOnLastWindowClosed(False)

        self.network_manager = QNetworkAccessManager(self)

        _app_requires()

    def _setup_conf_paths(self):
        self._conf_path = os.path.join(os.path.expanduser("~"), ".webmacs")

        def mkdir(path):
            if not os.path.isdir(path):
                os.makedirs(path)

        mkdir(self.conf_path())
        mkdir(self.profiles_path())

    def conf_path(self):
        return self._conf_path

    def profiles_path(self):
        return os.path.join(self.conf_path(), "profiles")

    def adblock_path(self):
        return os.path.join(self.conf_path(), "adblock")

    def visitedlinks(self):
        return self.profile.visitedlinks

    def bookmarks(self):
        return self.profile.bookmarks

    def autofill(self):
        return self.profile.autofill

    def url_interceptor(self):
        return self._interceptor

    def download_manager(self):
        return self._download_manager

    def ignored_certs(self):
        return self.profile.ignored_certs

    def adblock_update(self):
        def adblock_thread_finished(error, adblock):
            if adblock:
                self._interceptor.update_adblock(adblock)

        generator = Adblocker(self.adblock_path())
        runner = AdblockUpdateRunner(generator,
                                     on_finished=adblock_thread_finished)
        run(runner)

    def update_spell_checking(self):
        if not bool(spell_checking_dictionaries.value):
            return

        spell_check_path = os.path.join(self.applicationDirPath(),
                                        "qtwebengine_dictionaries")

        def spc_finished(*a):
            self.profile.update_spell_checking()

        runner = SpellCheckingUpdateRunner(spell_check_path,
                                           on_finished=spc_finished)
        run(runner)

    def post_init(self):
        self.adblock_update()
        self.update_spell_checking()
        init_minibuffer_right_labels()
