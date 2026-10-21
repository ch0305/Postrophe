import subprocess
from queue import Queue
from threading import Thread

from gi.repository import GLib

from postrophe import helpers
from postrophe.theme_switcher import Theme, ThemeSwitcher


class PreviewConverter:
    """Converts markdown to html using a background thread."""

    # Pandoc 3.12 deprecated --mathjax in favor of --math-method.
    _mathjax_argument = None

    @classmethod
    def _get_mathjax_argument(cls):
        if cls._mathjax_argument is not None:
            return cls._mathjax_argument

        argument = '--mathjax'
        try:
            version_output = subprocess.check_output(
                ['pandoc', '--version'],
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=5)
            version = version_output.splitlines()[0].split()[1]
            major, minor = (
                int(part) for part in version.split('.')[:2])
            if (major, minor) >= (3, 12):
                argument = '--math-method=mathjax'
        except (OSError, subprocess.SubprocessError,
                ValueError, IndexError):
            # Keep the old spelling for older pandoc versions.
            pass

        cls._mathjax_argument = argument
        return argument

    def __init__(self):
        super().__init__()

        self.queue = Queue()
        worker = Thread(target=self.__do_convert, name="preview-converter")
        worker.daemon = True
        worker.start()

    def convert(self, text, callback, *user_data):
        """Converts text to html, calling callback when done.

        The callback argument contains the result."""

        self.queue.put((text, callback, user_data))

    def stop(self):
        """Stops the background worker.
        PreviewConverter shouldn't be used after this."""

        self.queue.put((None, None))

    def __do_convert(self):
        while True:
            while True:
                (text, callback, user_data) = self.queue.get()
                if text is None and callback is None:
                    return
                if self.queue.empty():
                    break

            args = ['--standalone',
                    self._get_mathjax_argument(),
                    '--css=' + Theme.get_current().web_css,
                    '--lua-filter=' +
                    helpers.get_media_path('/lua/relative_to_absolute.lua'),
                    '--lua-filter=' +
                    helpers.get_media_path('/lua/task-list.lua')]
            text = helpers.pandoc_convert(text, to="html5", args=args)

            GLib.idle_add(callback, text, *user_data)
