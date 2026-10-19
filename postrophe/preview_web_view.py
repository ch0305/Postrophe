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

// Configure MathJax.
if (typeof hasMathJax === "undefined") {{
    hasMathJax = typeof MathJax !== "undefined";
    if (hasMathJax) {{
        MathJax.Hub.Config({{ messageStyle: "none" }});
    }}
}}

// Figure out if scrollable and rendered.
e = document.documentElement;
canScroll = e.scrollHeight > e.clientHeight;
wasRendered = typeof isRendered !== "undefined" && isRendered;
isRendered = wasRendered ||
        !hasMathJax ||
        MathJax.Hub.queue.running == 0 && MathJax.Hub.queue.pending == 0;

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

    // Typeset the new content if the page uses MathJax.
    if (typeof MathJax !== "undefined") {
        if (MathJax.typesetPromise) {
            MathJax.typesetPromise();
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

    def sync_scroll_scale(self, scroll_scale, write):
        self.state_waiting = True
        self.run_javascript(
            self.SYNC_SCROLL_SCALE_JS.format(
                scroll_scale, "true" if write else "false"),
            None, self.finish_sync_scroll_scale)

    def finish_sync_scroll_scale(self, _web_view, result):
        self.state_waiting = False
        result = self.run_javascript_finish(result)
        self.state_loop(result.get_js_value().to_double())

    def state_loop(self, scroll_scale=None, delay=16):  # 16ms ~ 60hz
        # Remove any pending callbacks
        if self.timeout_id:
            GLib.source_remove(self.timeout_id)
            self.timeout_id = None

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
