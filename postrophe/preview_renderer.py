from gettext import gettext as _

from gi.repository import Gdk, Gtk, GLib

from postrophe import headerbars
from postrophe.settings import Settings


class PreviewRenderer:
    """Renders the preview according to the user selected mode."""

    # Must match the order/index defined in gschema.xml
    FULL_WIDTH = 0
    HALF_WIDTH = 1
    HALF_HEIGHT = 2
    WINDOWED = 3

    # Room left for the window frame/shadow when fitting a split preview
    # inside the monitor work area. Without this, a split view can request
    # more than the screen (the editor minimum is based on characters per
    # line and is doubled for side-by-side previews).
    WORKAREA_MARGIN = 32
    MIN_SPLIT_EDITOR_WIDTH = 180
    MIN_SPLIT_EDITOR_HEIGHT = 160

    def __init__(
            self, main_window, content, editor, text_view):
        self.main_window = main_window
        self.main_window.connect("delete-event", self.on_window_closed)
        self.content = content
        self.editor = editor
        self.text_view = text_view

        self.settings = Settings.new()
        self.popover = None
        self.window = None
        self.headerbar = None

        # The editor scrolled window's minimum size is changed while a
        # split preview is visible. Remember the original request so it
        # can be restored when the preview is hidden.
        self._editor_scroller = None
        self._editor_original_size = None
        self._repaint_timeout_id = None

        self.mode = self.settings.get_enum("preview-mode")
        self.update_mode()

    def _get_workarea(self):
        """Return the work area of the monitor containing the main window."""

        display = self.main_window.get_display()
        if display is None:
            return None

        window = self.main_window.get_window()
        monitor = display.get_monitor_at_window(window) if window else None
        if monitor is None:
            monitor = display.get_primary_monitor()
        return monitor.get_workarea() if monitor is not None else None

    def _remember_editor_size(self):
        """Save the editor scrolled window's minimum size."""

        if self._editor_original_size is not None:
            return

        scroller = self.text_view.get_parent()
        if scroller is None:
            return

        width, height = scroller.get_size_request()
        if width <= 0:
            width = int(self.text_view.get_min_width())
        if height <= 0:
            height = 500

        self._editor_scroller = scroller
        self._editor_original_size = (width, height)

    def _restore_editor_size(self):
        """Restore the editor scrolled window's original minimum size."""

        if (self._editor_scroller is not None
                and self._editor_original_size is not None):
            self._editor_scroller.set_size_request(
                *self._editor_original_size)
        self._editor_scroller = None
        self._editor_original_size = None

    def _clamp_main_window(self):
        """Shrink the main window if a split preview left it oversized."""

        window = self.main_window.get_window()
        if window is None:
            return
        state = window.get_state()
        if state & (Gdk.WindowState.FULLSCREEN
                    | Gdk.WindowState.MAXIMIZED):
            return

        workarea = self._get_workarea()
        if workarea is None:
            return

        max_width = max(400, workarea.width - self.WORKAREA_MARGIN)
        max_height = max(300, workarea.height - 48)
        width, height = self.main_window.get_size()
        if width > max_width or height > max_height:
            self.main_window.resize(
                min(width, max_width), min(height, max_height))

    def _cancel_repaint_timeout(self):
        if self._repaint_timeout_id:
            GLib.source_remove(self._repaint_timeout_id)
            self._repaint_timeout_id = None

    def _repaint_preview(self, web_view):
        """Make sure WebKit paints after the window has been mapped."""

        try:
            if web_view.get_parent() is None:
                return False
        except (RuntimeError, TypeError):
            return False

        web_view.queue_resize()
        web_view.queue_draw()
        return False

    def _delayed_repaint_preview(self, web_view):
        self._repaint_timeout_id = None
        return self._repaint_preview(web_view)

    def _on_preview_window_map(self, _window, web_view):
        # WebKitGTK can leave the surface of a newly mapped toplevel
        # black until it receives a resize/draw. Give it both an idle
        # repaint and a slightly delayed one.
        GLib.idle_add(self._repaint_preview, web_view)
        self._repaint_timeout_id = GLib.timeout_add(
            120, self._delayed_repaint_preview, web_view)
        return False

    def show(self, web_view):
        """Show the preview, depending on the currently selected mode."""

        # Windowed preview: create a window and show the preview in it.
        if self.mode == self.WINDOWED:
            self.window = Gtk.ApplicationWindow(
                application=self.main_window.get_application())
            self.window.set_title(_("Preview"))
            self.window.set_transient_for(self.main_window)
            self.window.set_destroy_with_parent(True)
            self.window.set_position(Gtk.WindowPosition.CENTER_ON_PARENT)
            self.window.connect("delete-event", self.on_window_closed)

            # Create a custom header bar and move the mode button there.
            headerbar = headerbars.PreviewHeaderbar()
            self.headerbar = headerbar.hb
            self.headerbar.set_title(_("Preview"))
            self.window.set_titlebar(headerbar.hb_container)

            # Never create the preview larger than the monitor. If the
            # main window was previously enlarged by a split preview,
            # copying its size would put most of this window off-screen
            # (and can leave WebKit with an invalid surface).
            width, height = self.main_window.get_size()
            workarea = self._get_workarea()
            if workarea is not None:
                max_width = max(400, workarea.width - self.WORKAREA_MARGIN)
                max_height = max(300, workarea.height - 64)
                width = min(width, max_width)
                height = min(height, max_height)
            width = max(320, width)
            height = max(240, height)
            self.window.set_default_size(width, height)

            # Add webview and show.
            self.window.add(web_view)
            self.window.connect(
                "map", self._on_preview_window_map, web_view)
            self.window.show_all()

        else:
            self.content.pack_start(web_view, True, True, 0)

            # Full-width preview: swap editor with preview.
            if self.mode == self.FULL_WIDTH:
                self.content.remove(self.editor)

            # Half-width preview: set horizontal orientation & add the
            # preview. The editor's minimum width is based on the number
            # of characters per line, which can exceed half of a small
            # or scaled monitor. Clamp both children so the window (and
            # its headerbar buttons) stay reachable.
            elif self.mode == self.HALF_WIDTH:
                self.content.set_orientation(Gtk.Orientation.HORIZONTAL)
                self._remember_editor_size()

                min_width = int(self.text_view.get_min_width())
                workarea = self._get_workarea()
                if workarea is not None:
                    available = max(
                        320, workarea.width - self.WORKAREA_MARGIN)
                else:
                    available = max(
                        640, self.main_window.get_allocated_width())

                editor_width = min(
                    min_width,
                    max(self.MIN_SPLIT_EDITOR_WIDTH,
                        (available - 16) // 2))
                content_width = min(available, editor_width * 2)
                original_size = self._editor_original_size \
                    or (min_width, 500)
                editor_height = original_size[1]

                if self._editor_scroller is not None:
                    self._editor_scroller.set_size_request(
                        editor_width, editor_height)
                self.content.set_size_request(content_width, -1)

            # Half-height preview: set vertical orientation & add the
            # preview. Keep the stack inside the work area as well.
            elif self.mode == self.HALF_HEIGHT:
                self.content.set_orientation(Gtk.Orientation.VERTICAL)
                self._remember_editor_size()

                min_width = int(self.text_view.get_min_width())
                workarea = self._get_workarea()
                if workarea is not None:
                    available = max(
                        240, workarea.height - 96)
                else:
                    available = max(
                        480, self.main_window.get_allocated_height())

                content_height = min(768, available)
                original_size = self._editor_original_size \
                    or (min_width, 500)
                editor_width = original_size[0]

                if self._editor_scroller is not None:
                    self._editor_scroller.set_size_request(
                        editor_width, self.MIN_SPLIT_EDITOR_HEIGHT)
                self.content.set_size_request(-1, content_height)

            else:
                raise ValueError("Unknown preview mode {}".format(self.mode))

        web_view.show()

    def hide(self, web_view):
        """Hide the preview, depending on the currently selected mode."""

        self._cancel_repaint_timeout()

        # Windowed preview: remove preview and hide window.
        if self.mode == self.WINDOWED:
            self.main_window.present()
            if self.window is not None:
                window = self.window
                self.window = None
                self.headerbar = None
                if web_view.get_parent() is window:
                    window.remove(web_view)
                # Destroying a mapped WebKit toplevel immediately can
                # leave a queued GTK event pointing at the destroyed
                # GdkWindow (BadDrawable in WebKitGTK). Hide it first,
                # then destroy it after the event queue has drained.
                window.hide()
                GLib.timeout_add(
                    500, self._destroy_preview_window, window)

        else:
            if web_view.get_parent() is self.content:
                self.content.remove(web_view)

            # Full-width preview: swap preview with editor.
            if self.mode == self.FULL_WIDTH:
                if self.editor.get_parent() is None:
                    self.content.add(self.editor)

            # Half-width/height previews: restore the editor's minimum
            # size and reset the content size request.
            elif self.mode == self.HALF_WIDTH or self.mode == self.HALF_HEIGHT:
                self._restore_editor_size()

            else:
                raise ValueError("Unknown preview mode {}".format(self.mode))

            self.content.set_size_request(-1, -1)
            self._clamp_main_window()

    def update_mode(self, web_view=None):
        """Update preview mode, adjusting the mode button
        and the preview itself."""

        mode = self.settings.get_enum("preview-mode")
        if web_view is not None and mode != self.mode:
            self.hide(web_view)
            self.mode = mode
            self.show(web_view)
        else:
            self.mode = mode

    def on_window_closed(self, window, _event):
        application = window.get_application()
        preview_action = (application.lookup_action("preview")
                          if application is not None else None)
        if preview_action is None:
            return False

        # Destroying the preview toplevel from inside its own
        # delete-event can upset X11/WebKit. Let the event finish, then
        # toggle the preview off (which destroys the window).
        if window is self.window:
            GLib.idle_add(self._deactivate_preview, preview_action)
            return True

        # Ignore a stale preview window that is already being disposed.
        if window is not self.main_window:
            return False

        preview_action.change_state(GLib.Variant.new_boolean(False))
        return False

    @staticmethod
    def _deactivate_preview(preview_action):
        preview_action.change_state(GLib.Variant.new_boolean(False))
        return False

    @staticmethod
    def _destroy_preview_window(window):
        window.destroy()
        return False

    def get_text_for_preview_mode(self, mode):
        if mode == self.FULL_WIDTH:
            return _("Full-Width")
        elif mode == self.HALF_WIDTH:
            return _("Half-Width")
        elif mode == self.HALF_HEIGHT:
            return _("Half-Height")
        elif mode == self.WINDOWED:
            return _("Windowed")
        else:
            raise ValueError("Unknown preview mode {}".format(mode))
