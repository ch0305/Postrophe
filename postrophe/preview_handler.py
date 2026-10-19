import json
import math
import re
import webbrowser
from enum import auto, IntEnum

import gi

from postrophe.preview_renderer import PreviewRenderer
from postrophe.settings import Settings

try:
    gi.require_version('WebKit2', '4.1')
except ValueError:
    gi.require_version('WebKit2', '4.0')
from gi.repository import WebKit2, GLib, Gtk

from postrophe import task_list
from postrophe.helpers import user_action
from postrophe.preview_converter import PreviewConverter
from postrophe.preview_web_view import PreviewWebView


class Step(IntEnum):
    CONVERT_HTML = auto()
    LOAD_WEBVIEW = auto()
    RENDER = auto()


_BODY_RE = re.compile(r"<body[^>]*>(.*?)</body>", re.DOTALL | re.IGNORECASE)


def extract_body(html):
    """Return the contents of the <body> element, or None."""
    match = _BODY_RE.search(html)
    return match.group(1) if match else None


class PreviewHandler:
    """Handles showing/hiding the preview, and allows the user to toggle between modes.

    The rendering itself is handled by `PreviewRendered`. This class handles conversion/loading and
    connects it all together (including synchronization, ie. text changes, scroll)."""

    # Wait this long after the last edit before rebuilding the preview.
    # Converting on every keystroke makes the preview reload constantly,
    # which is expensive enough to make typing feel sluggish.
    CONVERT_DELAY = 250  # ms

    def __init__(self, window, content, editor, text_view):
        self.text_view = text_view

        self.web_view = None
        self.web_view_pending_html = None

        self.preview_converter = PreviewConverter()
        self.preview_renderer = PreviewRenderer(
            window, content, editor, text_view)

        self.text_changed_handler_id = None
        self.convert_timeout_id = None

        self.settings = Settings.new()
        self.web_scroll_handler_id = None
        self.text_scroll_handler_id = None

        self.loading = False
        self.shown = False
        self.page_ready = False
        self.web_view_pending_partial = False

        # Editor text the currently displayed preview was built from.
        self.preview_source_text = None

    def show(self):
        self.__cancel_pending_conversion()
        self.__show()

    def __cancel_pending_conversion(self):
        if self.convert_timeout_id:
            GLib.source_remove(self.convert_timeout_id)
            self.convert_timeout_id = None

    def on_text_changed(self, *_args):
        """Rebuild the preview once the user pauses typing."""
        self.__cancel_pending_conversion()
        self.convert_timeout_id = GLib.timeout_add(
            self.CONVERT_DELAY, self.__debounced_show)

    def __debounced_show(self):
        self.convert_timeout_id = None
        self.__show(partial=True)
        return False

    def __show(self, html=None, step=Step.CONVERT_HTML, partial=False):
        if step == Step.CONVERT_HTML:
            # First step: convert text to HTML.
            buf = self.text_view.get_buffer()
            text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
            # Snapshot of what the preview will show, used to verify
            # checkbox clicks map onto up-to-date text.
            self.preview_source_text = text
            self.preview_converter.convert(
                text, self.__show, Step.LOAD_WEBVIEW, partial)

        elif step == Step.LOAD_WEBVIEW:
            # Second step: load HTML, or patch the current page.

            if not self.web_view:
                self.web_view = PreviewWebView()
                self.web_view.get_settings().set_allow_universal_access_from_file_urls(True)
                #TODO: enable devtools on Devel profile
                # self.web_view.get_settings().set_enable_developer_extras(True)

                # Show preview once the load is finished
                self.web_view.connect("load-changed", self.on_load_changed)

                # All links will be opened in default browser, but local files are opened in apps.
                self.web_view.connect("decide-policy", self.on_click_link)

                self.web_view.connect("context-menu", self.on_right_click)

                # Checkbox clicks in the preview toggle the editor text.
                self.web_view.connect("task-toggled", self.on_task_toggled)

            if self.web_view.is_loading():
                self.web_view_pending_html = html
                self.web_view_pending_partial = partial
            else:
                self.__apply_html(html, partial)

        elif step == Step.RENDER:
            # Last step: show the preview. This is a one-time step.
            if self.shown:
                return
            self.shown = True

            self.text_changed_handler_id = \
                self.text_view.get_buffer().connect(
                    "changed", self.on_text_changed)

            GLib.idle_add(self.web_view.set_scroll_scale, self.text_view.get_scroll_scale())

            self.preview_renderer.show(self.web_view)

            if self.settings.get_boolean("sync-scroll"):
                self.web_scroll_handler_id = \
                    self.web_view.connect("scroll-scale-changed", self.on_web_view_scrolled)
                self.text_scroll_handler_id = \
                    self.text_view.connect("scroll-scale-changed", self.on_text_view_scrolled)

    def __apply_html(self, html, partial):
        """Patch the already loaded page, or load a fresh one.

        Replacing the body keeps the document, its CSS and its event
        listeners alive. A full load_html() paints the web view white
        for a moment, which is exactly the flash we want to avoid
        while typing."""

        if partial and self.page_ready:
            body = extract_body(html)
            if body is not None:
                self.web_view.update_html(body)
                return

        self.page_ready = False
        self.loading = True
        self.web_view.load_html(html, "file://localhost/")

    def on_task_toggled(self, _web_view, index):
        """Write a checkbox click from the preview back to the editor."""

        buf = self.text_view.get_buffer()
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)

        # The index refers to the snapshot the preview was built from.
        # If the editor changed since (the preview may lag a beat
        # behind typing), discard the click and re-render instead of
        # toggling the wrong item.
        if text != self.preview_source_text:
            self.show()
            return

        offset = task_list.nth_task_line_offset(text, index)
        if offset is None:
            # Unknown index: the preview is out of sync. Re-render so
            # the checkbox visual state matches the source again.
            self.show()
            return

        with user_action(buf):
            self.text_view.shortcut.toggle_task_at_offset(
                self.text_view, offset)

    def reload(self, *_widget, reshow=False):
        if self.shown:
            if reshow:
                self.hide()
            self.show()

    def hide(self):
        if self.shown:
            self.shown = False

            self.__cancel_pending_conversion()
            self.text_view.get_buffer().disconnect(self.text_changed_handler_id)

            # Carry the preview's scroll position back into the editor.
            # -1 means "preview not scrollable / not rendered"; writing
            # it would scroll the editor to the top.
            scale = self.web_view.get_scroll_scale()
            if scale >= 0:
                GLib.idle_add(self.text_view.set_scroll_scale, scale)

            self.preview_renderer.hide(self.web_view)

            if self.text_scroll_handler_id:
                self.text_view.disconnect(self.text_scroll_handler_id)
                self.text_scroll_handler_id = None
            if self.web_scroll_handler_id:
                self.web_view.disconnect(self.web_scroll_handler_id)
                self.web_scroll_handler_id = None

        if self.loading:
            self.loading = False
            self.page_ready = False
            self.web_view_pending_html = None
            self.web_view.destroy()
            self.web_view = None

    def update_preview_mode(self):
        self.preview_renderer.update_mode(self.web_view)

    def on_load_changed(self, _web_view, event):
        if event == WebKit2.LoadEvent.STARTED:
            self.page_ready = False
        elif event == WebKit2.LoadEvent.FINISHED:
            self.page_ready = True
            self.loading = False
            if self.web_view_pending_html:
                pending = self.web_view_pending_html
                partial = self.web_view_pending_partial
                self.web_view_pending_html = None
                self.web_view_pending_partial = False
                self.__show(html=pending, step=Step.LOAD_WEBVIEW,
                            partial=partial)
            else:
                self.__show(step=Step.RENDER)

    def on_text_view_scrolled(self, _text_view, scale):
        if self.shown and not math.isclose(scale,
                                           self.web_view.get_scroll_scale(),
                                           rel_tol=1e-4):
            self.web_view.set_scroll_scale(scale)

    def on_web_view_scrolled(self, _web_view, scale):
        if self.shown and self.text_view.get_mapped() and not math.isclose(
                scale, self.text_view.get_scroll_scale(), rel_tol=1e-1):
            self.text_view.set_scroll_scale(scale)

    @staticmethod
    def on_click_link(web_view, decision, _decision_type):
        if web_view.get_uri().startswith(("http://", "https://", "www.")):
            webbrowser.open(web_view.get_uri())
            decision.ignore()
            return True

    @staticmethod
    def on_right_click(web_view, context_menu, _event, _hit_test):
        # disable some context menu option
        for item in context_menu.get_items():
            if item.get_stock_action() in [WebKit2.ContextMenuAction.RELOAD,
                                           WebKit2.ContextMenuAction.GO_BACK,
                                           WebKit2.ContextMenuAction.GO_FORWARD,
                                           WebKit2.ContextMenuAction.STOP]:
                context_menu.remove(item)
