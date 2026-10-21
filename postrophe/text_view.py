import gi

from postrophe import task_list
from postrophe.helpers import user_action
from postrophe.inline_preview import InlinePreview
from postrophe.text_view_drag_drop_handler import DragDropHandler,\
                                                   TARGET_URI, TARGET_TEXT
from postrophe.text_view_format_inserter import FormatInserter
from postrophe.text_view_markup_handler import MarkupHandler
from postrophe.text_view_scroller import TextViewScroller
from postrophe.text_view_undo_redo_handler import UndoRedoHandler

gi.require_version('Gtk', '3.0')
gi.require_version('Gspell', '1')
from gi.repository import Gtk, Gdk, GObject, GLib, Gspell

import logging

LOGGER = logging.getLogger('postrophe')


class TextView(Gtk.TextView):
    """PostropheTextView encapsulates all the features around the editor.

    It combines the following:
    - Undo / redo (via TextBufferUndoRedoHandler)
    - Format shortcuts (via TextBufferShortcutInserter)
    - Markup (via TextBufferMarkupHandler)
    - Preview popover (via TextBufferMarkupHandler)
    - Drag and drop (via TextViewDragDropHandler)
    - Scrolling (via TextViewScroller)
    - The various modes supported by Postrophe (e. Focus Mode, Hemingway Mode)
    """

    __gsignals__ = {
        'insert-italic': (GObject.SignalFlags.ACTION, None, ()),
        'insert-bold': (GObject.SignalFlags.ACTION, None, ()),
        'insert-hrule': (GObject.SignalFlags.ACTION, None, ()),
        'insert-listitem': (GObject.SignalFlags.ACTION, None, ()),
        'insert-ordered-listitem': (GObject.SignalFlags.ACTION, None, ()),
        'insert-taskitem': (GObject.SignalFlags.ACTION, None, ()),
        'toggle-task': (GObject.SignalFlags.ACTION, None, ()),
        'insert-header': (GObject.SignalFlags.ACTION, None, ()),
        'insert-strikethrough': (GObject.SignalFlags.ACTION, None, ()),
        'undo': (GObject.SignalFlags.ACTION, None, ()),
        'redo': (GObject.SignalFlags.ACTION, None, ()),
        'scroll-scale-changed': (GObject.SIGNAL_RUN_LAST, None, (float,)),
    }

    # Must match CSS selectors in gtk/base.css
    font_sizes = [18, 17, 16, 15, 14]

    def __init__(self, line_chars):
        super().__init__()

        # Appearance
        self.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.set_pixels_above_lines(4)
        self.set_pixels_below_lines(4)
        self.set_pixels_inside_wrap(8)
        self.get_style_context().add_class('postrophe-editor')

        # TODO: remove this (AND the left margin from the scrolled_window)
        #       when Handy.Window is implemented

        # self.set_margin_left(8)
        self.set_margin_right(8)

        # Text sizing
        self.props.halign = Gtk.Align.FILL
        self.line_chars = line_chars
        self.font_size = 16
        self.get_style_context().add_class('size16')

        # General behavior
        self.connect('size-allocate', self.on_size_allocate)
        self.get_buffer().connect('changed', self.on_text_changed)
        self.get_buffer().connect('paste-done', self.on_paste_done)

        # Spell checking
        self.spellcheck = True
        self.gspell_view = Gspell.TextView.get_from_gtk_text_view(self)
        self.gspell_view.basic_setup()

        # Undo / redo
        self.undo_redo = UndoRedoHandler()
        self.get_buffer().connect('begin-user-action',
                                  self.undo_redo.on_begin_user_action)
        self.get_buffer().connect('end-user-action',
                                  self.undo_redo.on_end_user_action)
        self.get_buffer().connect('insert-text',
                                  self.undo_redo.on_insert_text)
        self.get_buffer().connect('delete-range',
                                  self.undo_redo.on_delete_range)
        self.connect('undo', self.undo_redo.undo)
        self.connect('redo', self.undo_redo.redo)

        # Format shortcuts
        self.shortcut = FormatInserter()
        self.connect('insert-italic', self.shortcut.insert_italic)
        self.connect('insert-bold', self.shortcut.insert_bold)
        self.connect('insert-strikethrough', self.shortcut.insert_strikethrough)
        self.connect('insert-hrule', self.shortcut.insert_horizontal_rule)
        self.connect('insert-listitem', self.shortcut.insert_list_item)
        self.connect('insert-ordered-listitem',
                     self.shortcut.insert_ordered_list_item)
        self.connect('insert-taskitem', self.shortcut.insert_task_item)
        self.connect('toggle-task', self.shortcut.toggle_task)
        self.connect('insert-header', self.shortcut.insert_header)

        # Markup
        self.markup = MarkupHandler(self)
        self.connect('style-updated', self.markup.on_style_updated)
        self.connect('destroy', self.markup.stop)

        # Preview popover
        self.preview_popover = InlinePreview(self)

        # Drag and drop
        self.drag_drop = DragDropHandler(self, TARGET_URI, TARGET_TEXT)

        # Scrolling
        self.scroller = None
        self.connect('parent-set', self.on_parent_set)
        self.get_buffer().connect('mark-set', self.on_mark_set)

        # Focus mode
        self.focus_mode = False
        self.connect('button-release-event', self.on_button_release_event)

        # Hemingway mode
        self.hemingway_mode = False
        self.connect('key-press-event', self._on_key_press_event)

        # While resizing the TextView or changing its top margin, GTK3
        # scrolls the view upwards on its own. When a size allocation or
        # margin change is detected, this variable holds the absolute
        # scroll position (in pixels) to re-assert until a short delay
        # after the last reallocation has passed.
        # Storing pixels instead of a scroll ratio is deliberate: the
        # ratio changes when the margin (i.e. the scrollable extent)
        # changes, so restoring a ratio after a margin change lands at
        # the wrong position. GTK3 also finishes its own scrolling after
        # the next idle pass, so a single idle_add restore loses the
        # race; we keep re-asserting for a short timeout instead.

        # TODO: Find a better way to handle unwanted scroll.
        self.frozen_scroll_value = None
        self._unfreeze_source_id = None

    def get_text(self):
        text_buffer = self.get_buffer()
        start_iter = text_buffer.get_start_iter()
        end_iter = text_buffer.get_end_iter()
        return text_buffer.get_text(start_iter, end_iter, False)

    def set_text(self, text):
        """Set text and clear undo history"""

        text_buffer = self.get_buffer()
        with user_action(text_buffer):
            text_buffer.set_text(text)
        self.undo_redo.clear()

    def can_scroll(self):
        return self.scroller.can_scroll()

    def get_scroll_scale(self):
        return self.scroller.get_scroll_scale() if self.scroller else 0

    def set_scroll_scale(self, scale):
        if self.scroller:
            self.scroller.set_scroll_scale(scale)

    def on_size_allocate(self, *_):
        self.update_horizontal_margin()
        self.markup.update_margins_indents()
        self.queue_draw()

        # TODO: Find a better way to handle unwanted scroll on resize.
        self.freeze_scroll()

    def freeze_scroll(self):
        """Hold the current scroll position in absolute pixels.

        GTK3 scrolls the view upwards on its own when the size
        allocation or the top margin changes. Re-assert the saved
        position on every adjustment change and unfreeze a short delay
        after the last freeze, so we also win against GTK3's delayed
        scrolling (which happens after the idle pass)."""

        parent = self.get_parent()
        if not parent:
            return
        self.frozen_scroll_value = parent.get_vadjustment().get_value()

        if self._unfreeze_source_id:
            GLib.source_remove(self._unfreeze_source_id)
        self._unfreeze_source_id = GLib.timeout_add(
            100, self.unfreeze_scroll)

    def on_text_changed(self, *_):
        self.markup.apply()
        self.smooth_scroll_to()

    def on_paste_done(self, *_):
        self.smooth_scroll_to()

    def on_parent_set(self, *_):
        parent = self.get_parent()
        if parent:
            parent.set_size_request(self.get_min_width(), 500)
            self.scroller = TextViewScroller(self, parent)
            parent.get_vadjustment().connect("changed",
                                             self.on_vadjustment_changed)
            parent.get_vadjustment().connect("value-changed",
                                             self.on_vadjustment_changed)
        else:
            self.scroller = None

    def on_mark_set(self, _text_buffer, _location, mark, _data=None):
        if mark.get_name() == 'selection_bound':
            # Only focus mode reacts to cursor movement: it has to move
            # the gray tag to the new sentence. Reapplying all markup
            # here would needlessly inspect the whole buffer (and queue
            # another parse while typing), because the text-change
            # handler already does the full markup update.
            if self.focus_mode:
                self.markup.apply_focus()
            if not self.get_buffer().get_has_selection():
                self.smooth_scroll_to(mark)
        elif mark.get_name() == 'gtk_drag_target':
            self.smooth_scroll_to(mark)
        return True

    def on_button_release_event(self, _widget, _event):
        if self.focus_mode:
            self.markup.apply_focus()
        return False

    def on_vadjustment_changed(self, *_):
        if self.frozen_scroll_value is not None:
            parent = self.get_parent()
            if parent:
                adjustment = parent.get_vadjustment()
                if adjustment.get_value() != self.frozen_scroll_value:
                    adjustment.set_value(self.frozen_scroll_value)
        elif self.can_scroll():
            self.emit("scroll-scale-changed", self.get_scroll_scale())

    def unfreeze_scroll(self):
        self.frozen_scroll_value = None
        self._unfreeze_source_id = None
        self.queue_draw()
        return False

    def set_focus_mode(self, focus_mode, hb_height):
        """Toggle focus mode.

        When in focus mode, the cursor sits in the middle of the text view,
        and the surrounding text is greyed out."""

        self.focus_mode = focus_mode
        self.update_vertical_margin(hb_size=hb_height)
        self.markup.apply()
        self.smooth_scroll_to()
        self.set_spellcheck(self.spellcheck)

    def set_spellcheck(self, spellcheck):
        self.spellcheck = spellcheck
        self.gspell_view.set_inline_spell_checking(
            self.spellcheck and not self.focus_mode)

    def update_horizontal_margin(self):
        width = self.get_allocation().width

        # Ensure the appropriate font size is being used
        for font_size in self.font_sizes:
            if width >= self.get_min_width(font_size) or font_size == self.font_sizes[-1]:
                if font_size != self.font_size:
                    self.font_size = font_size
                    for fs in self.font_sizes:
                        self.get_style_context().remove_class("size{}".format(fs))
                    self.get_style_context().add_class("size{}".format(font_size))
                break

        # Apply margin with the remaining space to allow for markup
        line_width = (self.line_chars + 1) *\
            int(self.get_char_width(self.font_size)) - 1
        horizontal_margin = (width - line_width) / 2
        self.props.left_margin = horizontal_margin
        self.props.right_margin = horizontal_margin

    def update_vertical_margin(self, top_margin=0, hb_size=0):
        # Changing the margins triggers GTK3's own (buggy) re-scrolling;
        # freeze the position before touching them.
        self.freeze_scroll()

        if self.focus_mode:
            height = self.get_allocation().height + top_margin + hb_size
            # The height/6 may seem strange. It's a workaround for a GTK bug
            # If a top-margin is larger than a certain amount of
            # the TextView height, jumps may occur when pressing enter.
            self.set_top_margin(height / 2 + top_margin - height/6)
            self.set_bottom_margin(height / 2)
        else:
            self.props.top_margin = 80 + top_margin
            self.props.bottom_margin = 64

    def set_hemingway_mode(self, hemingway_mode):
        """Toggle hemingway mode.

        When in hemingway mode, the backspace and delete keys are ignored."""

        self.hemingway_mode = hemingway_mode

    def clear(self):
        """Clear text and undo history"""

        self.set_text('')

    def smooth_scroll_to(self, mark=None):
        """Scrolls if needed to ensure mark is visible.

        If mark is unspecified, the cursor is used."""

        if self.scroller is None:
            return
        if mark is None:
            mark = self.get_buffer().get_insert()
        GLib.idle_add(self.scroller.smooth_scroll_to_mark,
                      mark, self.focus_mode)

    def get_min_width(self, font_size=None):
        """Returns the minimum width of this text view."""

        if font_size is None:
            font_size = self.font_sizes[-1]
        return (self.line_chars + self.get_pad_chars(font_size) + 1) \
            * self.get_char_width(font_size) - 1

    def get_pad_chars(self, font_size):
        """Returns the amount of character padding for font_size.

        Markup can use up to 7 in normal conditions."""

        return 8 * (1 + font_size - self.font_sizes[-1])

    @staticmethod
    def get_char_width(font_size):
        """Returns the font width for a given size.
        Note: specific to Fira Mono!"""

        return font_size * 1 / 1.6

    def _on_key_press_event(self, _widget, event):
        if self.hemingway_mode:
            return event.keyval == Gdk.KEY_BackSpace or event.keyval == Gdk.KEY_Delete

        if event.state & Gdk.ModifierType.SHIFT_MASK == Gdk.ModifierType.SHIFT_MASK \
                and event.keyval == Gdk.KEY_ISO_Left_Tab:  # Capure Shift-Tab
            self._on_shift_tab()
            return True

        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) \
                and not event.state & (Gdk.ModifierType.SHIFT_MASK |
                                       Gdk.ModifierType.CONTROL_MASK |
                                       Gdk.ModifierType.MOD1_MASK) \
                and self._continue_list_on_enter():
            return True

        return False

    def _continue_list_on_enter(self):
        """Continue the current list/task item on Enter.

        Returns True when the Enter press was handled (a new list
        marker was inserted or an empty item was cleared), so the
        default newline must be suppressed."""

        text_buffer = self.get_buffer()
        cursor_iter = text_buffer.get_iter_at_mark(
            text_buffer.get_insert())

        line_start = cursor_iter.copy()
        line_start.set_line_offset(0)
        line_end = cursor_iter.copy()
        line_end.forward_to_line_end()
        line_text = text_buffer.get_text(line_start, line_end, False)

        # Never continue lists inside fenced code blocks.
        text_before = text_buffer.get_text(
            text_buffer.get_start_iter(), cursor_iter, False)
        if task_list.in_code_block(text_before):
            return False

        # Marker prefix to repeat on the next line, or None.
        marker = None

        task = task_list.parse_task_line(line_text)
        ordered = None
        if not task:
            ordered = task_list.parse_ordered_line(line_text)

        current = task or ordered
        if current:
            # Empty item: remove the marker and leave a blank line.
            if task:
                rest = task.group(4) or ""
            else:
                rest = line_text[current.end():]
            if not rest.strip():
                with user_action(text_buffer):
                    text_buffer.delete(line_start, line_end)
                return True

            if task:
                # New items start unchecked, like GitHub/Typora.
                marker = task.group(1) + task.group(2) + " [ ] "
            else:
                marker = task_list.next_ordered_prefix(line_text)
        else:
            plain = task_list.parse_plain_list_line(line_text)
            if plain:
                if not line_text[plain.end():].strip():
                    with user_action(text_buffer):
                        text_buffer.delete(line_start, line_end)
                    return True
                marker = plain.group(1) + plain.group(2) + " "

        if marker is None:
            return False

        with user_action(text_buffer):
            text_buffer.insert_at_cursor("\n" + marker)
        return True

    def _on_shift_tab(self):
        """Delete last character if it is a tab"""
        text_buffer = self.get_buffer()
        pen_iter = text_buffer.get_end_iter()
        pen_iter.backward_char()
        end_iter = text_buffer.get_end_iter()

        if pen_iter.get_char() == "\t":
            with user_action(text_buffer):
                text_buffer.delete(pen_iter, end_iter)
