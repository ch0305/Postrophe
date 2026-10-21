import json
import webbrowser

import gi

try:
    gi.require_version('WebKit2', '4.1')
except ValueError:
    gi.require_version('WebKit2', '4.0')
from gi.repository import WebKit2, GLib, GObject


class PreviewWebView(WebKit2.WebView):
    """A WebView that provides read/write access to scroll.

    It does so using JavaScript, by continuously monitoring it while loaded.
    The alternative is using a WebExtension and C-bindings (see reference),
    but that is more complicated implementation-wise,
    as well as build-wise until we start building with Meson.

    Reference: https://github.com/aperezdc/webkit2gtk-python-webextension-example
    """

    SYNC_SCROLL_SCALE_JS = """
scale = {:.16f};
write = {};

// Configure MathJax. MathJax 2 exposes MathJax.Hub, while MathJax 3+
// only exposes MathJax.startup / MathJax.typesetPromise. Calling
// MathJax.Hub.queue on version 3 throws and used to stop the scroll
// synchronization loop for the rest of the page's lifetime.
if (typeof hasMathJax === "undefined") {{
    hasMathJax = false;
    mathJaxReady = false;
}}
if (!hasMathJax && typeof MathJax !== "undefined") {{
    hasMathJax = true;
    if (MathJax.Hub && MathJax.Hub.Config) {{
        MathJax.Hub.Config({{ messageStyle: "none" }});
        mathJaxReady = true;
    }} else if (MathJax.startup && MathJax.startup.promise) {{
        MathJax.startup.promise.then(function () {{
            mathJaxReady = true;
        }}).catch(function () {{
            mathJaxReady = true;
        }});
    }} else {{
        mathJaxReady = true;
    }}
}}

// Figure out if scrollable and rendered.
e = document.documentElement;
canScroll = e.scrollHeight > e.clientHeight;
wasRendered = typeof isRendered !== "undefined" && isRendered;
mathJaxBusy = false;
if (hasMathJax) {{
    if (MathJax.Hub && MathJax.Hub.queue) {{
        mathJaxBusy = MathJax.Hub.queue.running != 0 ||
                MathJax.Hub.queue.pending != 0;
    }} else {{
        mathJaxBusy = !mathJaxReady;
    }}
}}
isRendered = wasRendered || !hasMathJax || !mathJaxBusy;

// Write the current scroll if instructed or if it was just rendered.
// scale < 0 means "unknown"; writing it would clamp to the top.
if (scale >= 0 && canScroll && (write || isRendered && !wasRendered)) {{
    e.scrollTop = (e.scrollHeight - e.clientHeight) * scale;
}}

// Return the current scroll if scrollable and rendered, or -1.
if (canScroll && isRendered) {{
    e.scrollTop / (e.scrollHeight - e.clientHeight);
}} else {{
    -1;
}}
""".strip()

    __gsignals__ = {
        "scroll-scale-changed": (GObject.SIGNAL_RUN_LAST, None, (float,)),
        "task-toggled": (GObject.SIGNAL_RUN_LAST, None, (int,)),
    }

    UPDATE_BODY_JS = """
(function () {
    var doc = document.documentElement;
    var max = doc.scrollHeight - doc.clientHeight;
    var scale = max > 0 ? doc.scrollTop / max : 0;

    document.body.innerHTML = %s;

    // Typeset the new content if the page uses MathJax. Mark MathJax
    // as busy until typesetting finishes, so scroll synchronization
    // waits for the final layout (version 2 uses its queue instead).
    if (typeof MathJax !== "undefined") {
        if (MathJax.typesetPromise) {
            window.mathJaxReady = false;
            MathJax.typesetPromise().then(function () {
                window.mathJaxReady = true;
            }).catch(function () {
                window.mathJaxReady = true;
            });
        } else if (MathJax.Hub) {
            MathJax.Hub.Queue(["Typeset", MathJax.Hub]);
        }
    }

    // Keep the reading position when the body is replaced.
    var newMax = doc.scrollHeight - doc.clientHeight;
    if (newMax > 0) {
        doc.scrollTop = scale * newMax;
    }
})();
""".strip()

    def update_html(self, body_html):
        """Replace the page body without reloading the document.

        A full load_html() blanks the web view and re-runs all page
        setup, which shows up as a white flash. Keeping the document
        and only swapping its body avoids that entirely."""

        self.run_javascript(
            self.UPDATE_BODY_JS % json.dumps(body_html),
            None, self.finish_update_html)

    def finish_update_html(self, _web_view, result):
        try:
            self.run_javascript_finish(result)
        except GLib.Error:
            pass

    def __init__(self):
        # Receive checkbox clicks injected by task-list.lua.
        self.user_content_manager = WebKit2.UserContentManager()
        self.user_content_manager.register_script_message_handler(
            "postropheTaskToggle")
        self.user_content_manager.connect(
            "script-message-received", self.on_script_message_received)

        super().__init__(
            user_content_manager=self.user_content_manager)

        self.connect("size-allocate", self.on_size_allocate)
        self.connect("decide-policy", self.on_decide_policy)
        self.connect("load-changed", self.on_load_changed)
        self.connect("load-failed", self.on_load_failed)
        self.connect("destroy", self.on_destroy)
        self.connect("map", self.on_map)
        self.connect("unmap", self.on_unmap)

        self.props.expand = True

        self.scroll_scale = -1

        self.state_loaded = False
        self.state_load_failed = False
        self.state_discard_read = False
        self.state_dirty = False
        self.state_waiting = False

        # Adaptive polling: back off from ~60hz to 500ms once the
        # scroll position has been stable for a few reads.
        self.idle_reads = 0

        self.timeout_id = None

    def can_scroll(self):
        return self.scroll_scale != -1

    def get_scroll_scale(self):
        return self.scroll_scale

    def set_scroll_scale(self, scale):
        # scale == -1 means "unknown / not scrollable". Never write it
        # to the page: the JS would compute a negative scrollTop, which
        # the browser clamps to 0, jumping the preview to the top.
        if scale < 0:
            return
        self.state_dirty = scale != self.scroll_scale
        self.scroll_scale = scale
        self.state_loop()

    def on_script_message_received(self, _manager, result):
        """Handle a checkbox click posted by the preview page.

        Emits task-toggled with the task item's index (document order,
        as assigned by task-list.lua)."""

        try:
            value = result.get_js_value().to_int32()
        except (AttributeError, GLib.Error):
            return
        self.emit("task-toggled", value)

    def on_size_allocate(self, *_):
        self.set_scroll_scale(self.scroll_scale)

    def on_decide_policy(self, _web_view, decision, decision_type):
        if decision_type == WebKit2.PolicyDecisionType.NAVIGATION_ACTION and \
                decision.get_navigation_action().is_user_gesture():
            webbrowser.open(decision.get_request().get_uri())
            decision.ignore()       # Do not follow the link in the WebView
            return True
        return False

    def on_load_changed(self, _web_view, event):
        self.state_loaded = event >= WebKit2.LoadEvent.COMMITTED and not self.state_load_failed
        self.state_load_failed = False
        self.state_discard_read = event == WebKit2.LoadEvent.STARTED and self.state_waiting
        self.state_dirty = True
        self.state_loop()

    def on_load_failed(self, _web_view, _event, *_args):
        self.state_loaded = False
        self.state_load_failed = True
        self.state_loop()

    def on_destroy(self, _widget):
        self.state_loaded = False
        self.state_loop()

    def on_map(self, *_):
        # Polling is paused until the view is visible. Start it as soon
        # as the preview is actually mapped.
        if self.state_loaded:
            self.state_loop(delay=0)

    def on_unmap(self, *_):
        if self.timeout_id:
            GLib.source_remove(self.timeout_id)
            self.timeout_id = None

    def sync_scroll_scale(self, scroll_scale, write):
        self.state_waiting = True
        self.run_javascript(
            self.SYNC_SCROLL_SCALE_JS.format(
                scroll_scale, "true" if write else "false"),
            None, self.finish_sync_scroll_scale)

    def finish_sync_scroll_scale(self, _web_view, result):
        self.state_waiting = False
        try:
            result = self.run_javascript_finish(result)
            scroll_scale = result.get_js_value().to_double()
        except GLib.Error:
            # A JavaScript error must not stop scroll synchronization
            # for the rest of the page's lifetime. Retry slowly.
            if self.state_loaded and not self.state_load_failed:
                self.timeout_id = GLib.timeout_add(
                    250, self._retry_sync_scroll)
            return
        self.state_loop(scroll_scale)

    def _retry_sync_scroll(self):
        self.timeout_id = None
        self.state_loop()
        return False

    def state_loop(self, scroll_scale=None, delay=16):  # 16ms ~ 60hz
        # Remove any pending callbacks
        if self.timeout_id:
            GLib.source_remove(self.timeout_id)
            self.timeout_id = None

        # Do not run JavaScript while the preview is not visible.
        # PreviewHandler destroys the view on hide; this also covers
        # the short period before the view is inserted and mapped.
        if self.state_loaded and not self.get_mapped():
            return

        # Set scroll scale if specified, and the state is not dirty
        if not self.state_discard_read and scroll_scale not in (
                None, self.scroll_scale):
            self.scroll_scale = scroll_scale
            if self.scroll_scale != -1:
                self.emit("scroll-scale-changed", self.scroll_scale)
        self.state_discard_read = False

        # Handle the current state
        if not self.state_loaded or self.state_load_failed or self.state_waiting:
            return
        elif self.state_dirty or delay == 0:
            # Never write scale -1 into the page (see set_scroll_scale).
            write = self.state_dirty and self.scroll_scale >= 0
            self.sync_scroll_scale(self.scroll_scale, write)
            self.state_dirty = False
        else:
            # Back off the polling interval while the scroll position
            # stays unchanged (-1: not scrollable/not rendered counts
            # as stable too), and speed back up as soon as it moves.
            if scroll_scale is not None and scroll_scale == self.scroll_scale:
                self.idle_reads += 1
            else:
                self.idle_reads = 0
            if self.idle_reads >= 4:  # ~64ms of no movement
                delay = 250
            self.timeout_id = GLib.timeout_add(delay, self.state_loop, None, 0)
