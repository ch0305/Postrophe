from gettext import gettext as _

from postrophe import task_list
from postrophe.helpers import user_action


class FormatInserter:
    """Manages insertion of formatting.

    Methods can be called directly, as well as be used as signal callbacks."""

    def insert_italic(self, text_view, _data=None):
        """Insert italic or mark a selection as bold"""

        self.__wrap(text_view, "_", _("italic text"))

    def insert_bold(self, text_view, _data=None):
        """Insert bold or mark a selection as bold"""

        self.__wrap(text_view, "**", _("bold text"))

    def insert_strikethrough(self, text_view, _data=None):
        """Insert strikethrough or mark a selection as strikethrough"""

        self.__wrap(text_view, "~~", _("strikethrough text"))

    def insert_horizontal_rule(self, text_view, _data=None):
        """Insert horizontal rule"""

        text_buffer = text_view.get_buffer()
        with user_action(text_buffer):
            text_buffer.insert_at_cursor("\n\n---\n")
        text_view.scroll_mark_onscreen(text_buffer.get_insert())

    def insert_list_item(self, text_view, _data=None):
        """Insert list item or mark a selection as list item"""

        text_buffer = text_view.get_buffer()
        if text_buffer.get_has_selection():
            (start, end) = text_buffer.get_selection_bounds()
            if start.starts_line():
                with user_action(text_buffer):
                    text = text_buffer.get_text(start, end, False)
                    if text.startswith(("- ", "* ", "+ ")):
                        delete_end = start.copy()
                        delete_end.forward_chars(2)
                        text_buffer.delete(start, delete_end)
                    else:
                        text_buffer.insert(start, "- ")
        else:
            helptext = _("Item")
            text_length = len(helptext)

            cursor_mark = text_buffer.get_insert()
            cursor_iter = text_buffer.get_iter_at_mark(cursor_mark)

            start_ext = cursor_iter.copy()
            start_ext.backward_lines(3)
            text = text_buffer.get_text(cursor_iter, start_ext, False)
            lines = text.splitlines()

            with user_action(text_buffer):
                for line in reversed(lines):
                    if line and line.startswith(("- ", "* ", "+ ")):
                        if cursor_iter.starts_line():
                            text_buffer.insert_at_cursor(line[:2] + helptext)
                        else:
                            text_buffer.insert_at_cursor(
                                "\n" + line[:2] + helptext)
                        break
                    else:
                        if not lines[-1] and not lines[-2]:
                            text_buffer.insert_at_cursor("- " + helptext)
                        elif not lines[-1]:
                            if cursor_iter.starts_line():
                                text_buffer.insert_at_cursor("- " + helptext)
                            else:
                                text_buffer.insert_at_cursor("\n- " + helptext)
                        else:
                            text_buffer.insert_at_cursor("\n\n- " + helptext)
                        break

            self.__select_text(text_view, 0, text_length)

    def insert_ordered_list_item(self, text_view, _data=None):
        """Insert an ordered list item or mark a selection as ordered list"""

        text_buffer = text_view.get_buffer()
        if text_buffer.get_has_selection():
            (start, end) = text_buffer.get_selection_bounds()
            with user_action(text_buffer):
                for offset in reversed(self.__line_start_offsets(start, end)):
                    line_iter = text_buffer.get_iter_at_offset(offset)
                    line_end = line_iter.copy()
                    line_end.forward_to_line_end()
                    text = text_buffer.get_text(line_iter, line_end, False)
                    match = task_list.parse_ordered_line(text)
                    if match:
                        # Remove the existing marker (incl. trailing space),
                        # keeping indentation and blockquote markers.
                        marker_start = line_iter.copy()
                        marker_start.forward_chars(match.start(2))
                        marker_end = line_iter.copy()
                        marker_end.forward_chars(match.end())
                        text_buffer.delete(marker_start, marker_end)
                    elif text.strip():
                        self.__insert_list_marker(
                            text_buffer, line_iter, text,
                            "{}. ".format(self.__ordered_number(
                                text_buffer, line_iter)))
        else:
            helptext = _("Item")
            text_length = len(helptext)

            cursor_mark = text_buffer.get_insert()
            cursor_iter = text_buffer.get_iter_at_mark(cursor_mark)

            line_start = cursor_iter.copy()
            line_start.set_line_offset(0)
            line_end = cursor_iter.copy()
            line_end.forward_to_line_end()
            line_text = text_buffer.get_text(line_start, line_end, False)

            match = task_list.parse_ordered_line(line_text)
            prefix_len = task_list.line_prefix_length(line_text)
            with user_action(text_buffer):
                if match and line_text[match.end():].strip():
                    # Continue numbering on the next line.
                    text_buffer.insert_at_cursor(
                        "\n" + task_list.next_ordered_prefix(line_text))
                else:
                    if cursor_iter.starts_line() or \
                            not line_text[prefix_len:].strip():
                        # Empty line (possibly indented/quoted) or the
                        # cursor sits before the text.
                        insert_iter = line_start.copy()
                        insert_iter.forward_chars(prefix_len)
                        text_buffer.place_cursor(insert_iter)
                        text_buffer.insert_at_cursor("1. " + helptext)
                    else:
                        text_buffer.insert_at_cursor("\n1. " + helptext)
                    self.__select_text(text_view, 0, text_length)

    def insert_task_item(self, text_view, _data=None):
        """Insert a task item or mark a selection as task items"""

        text_buffer = text_view.get_buffer()
        if text_buffer.get_has_selection():
            (start, end) = text_buffer.get_selection_bounds()
            with user_action(text_buffer):
                for offset in reversed(self.__line_start_offsets(start, end)):
                    line_iter = text_buffer.get_iter_at_offset(offset)
                    line_end = line_iter.copy()
                    line_end.forward_to_line_end()
                    text = text_buffer.get_text(line_iter, line_end, False)
                    match = task_list.parse_task_line(text)
                    if match:
                        # Remove the marker "- [x] ", keeping indentation
                        # and blockquote markers.
                        marker_start = line_iter.copy()
                        marker_start.forward_chars(match.start(2))
                        marker_end = line_iter.copy()
                        marker_end.forward_chars(
                            task_list.task_marker_end(match))
                        text_buffer.delete(marker_start, marker_end)
                    elif text.strip():
                        self.__insert_list_marker(
                            text_buffer, line_iter, text, "- [ ] ")
        else:
            helptext = _("Item")
            text_length = len(helptext)

            cursor_mark = text_buffer.get_insert()
            cursor_iter = text_buffer.get_iter_at_mark(cursor_mark)

            line_start = cursor_iter.copy()
            line_start.set_line_offset(0)
            line_end = cursor_iter.copy()
            line_end.forward_to_line_end()
            line_text = text_buffer.get_text(line_start, line_end, False)

            match = task_list.parse_task_line(line_text)
            prefix_len = task_list.line_prefix_length(line_text)
            with user_action(text_buffer):
                if match and (match.group(4) or "").strip():
                    # Continue the task list; new items start unchecked.
                    text_buffer.insert_at_cursor(
                        "\n" + match.group(1) + match.group(2) + " [ ] ")
                else:
                    if cursor_iter.starts_line() or \
                            not line_text[prefix_len:].strip():
                        # Empty line (possibly indented/quoted) or the
                        # cursor sits before the text.
                        insert_iter = line_start.copy()
                        insert_iter.forward_chars(prefix_len)
                        text_buffer.place_cursor(insert_iter)
                        text_buffer.insert_at_cursor("- [ ] " + helptext)
                    else:
                        text_buffer.insert_at_cursor("\n- [ ] " + helptext)
                    self.__select_text(text_view, 0, text_length)

    def toggle_task(self, text_view, _data=None):
        """Toggle the checked state of the task item at the cursor,
           or of every task item in the selection"""

        text_buffer = text_view.get_buffer()
        if text_buffer.get_has_selection():
            (start, end) = text_buffer.get_selection_bounds()
            offsets = self.__line_start_offsets(start, end)
        else:
            cursor_iter = text_buffer.get_iter_at_mark(
                text_buffer.get_insert())
            line_start = cursor_iter.copy()
            line_start.set_line_offset(0)
            offsets = [line_start.get_offset()]

        with user_action(text_buffer):
            for offset in offsets:
                self.toggle_task_at_offset(text_view, offset)

    def toggle_task_at_offset(self, text_view, offset):
        """Toggle the task item on the line starting at offset.

        Does nothing when the line is not a task item. Must be called
        within a user_action block for undo support."""

        text_buffer = text_view.get_buffer()
        line_iter = text_buffer.get_iter_at_offset(offset)
        line_end = line_iter.copy()
        line_end.forward_to_line_end()
        text = text_buffer.get_text(line_iter, line_end, False)

        match = task_list.parse_task_line(text)
        if not match:
            return

        # Replace the checkbox state character in place.
        state_iter = line_iter.copy()
        state_iter.forward_chars(match.start(3))
        state_end = line_iter.copy()
        state_end.forward_chars(match.end(3))
        new_state = " " if match.group(3).lower() == "x" else "x"
        text_buffer.delete(state_iter, state_end)
        text_buffer.insert(state_iter, new_state)

    @staticmethod
    def __list_marker_end(text):
        """End offset of an existing list marker on the line, or 0."""

        task = task_list.parse_task_line(text)
        if task:
            return task_list.task_marker_end(task)
        ordered = task_list.parse_ordered_line(text)
        if ordered:
            return ordered.end()
        plain = task_list.parse_plain_list_line(text)
        if plain:
            return plain.end()
        return 0

    @staticmethod
    def __insert_list_marker(text_buffer, line_iter, text, marker):
        """Insert marker after the line prefix, replacing any existing
        list marker (plain, ordered or task) instead of nesting one."""

        prefix_end = task_list.line_prefix_length(text)
        marker_end = FormatInserter.__list_marker_end(text)

        insert_iter = line_iter.copy()
        insert_iter.forward_chars(prefix_end)
        if marker_end > prefix_end:
            end_iter = line_iter.copy()
            end_iter.forward_chars(marker_end)
            text_buffer.delete(insert_iter, end_iter)
        text_buffer.insert(insert_iter, marker)

    @staticmethod
    def __line_start_offsets(start, end):
        """Offsets of the start of every line intersecting the
        selection [start, end). A line whose start lies exactly at end
        is not included (empty trailing line)."""

        offsets = []
        line_iter = start.copy()
        line_iter.set_line_offset(0)
        while line_iter.get_offset() < end.get_offset():
            offsets.append(line_iter.get_offset())
            if not line_iter.forward_line():
                break
        return offsets

    @staticmethod
    def __ordered_number(text_buffer, line_iter):
        """The number the current line would get if numbered in
        order: one plus the number of preceding ordered items."""

        count = 0
        it = text_buffer.get_start_iter()
        while it.get_offset() < line_iter.get_offset():
            line_end = it.copy()
            line_end.forward_to_line_end()
            text = text_buffer.get_text(it, line_end, False)
            if task_list.parse_ordered_line(text):
                count += 1
            if not it.forward_line():
                break
        return count + 1

    def insert_header(self, text_view, _data=None):
        """Insert header or mark a selection as a list header"""

        text_buffer = text_view.get_buffer()
        with user_action(text_buffer):
            if text_buffer.get_has_selection():
                (start, end) = text_buffer.get_selection_bounds()
                text = text_buffer.get_text(start, end, False)
                text_buffer.delete(start, end)
            else:
                text = _("Header")

            text_buffer.insert_at_cursor("#" + " " + text)

        self.__select_text(text_view, 0, len(text))

    @staticmethod
    def __wrap(text_view, wrap, helptext=""):
        """Inserts wrap format to the selected text
        (helper text when nothing selected)"""
        text_buffer = text_view.get_buffer()
        with user_action(text_buffer):
            if text_buffer.get_has_selection():
                # Find current highlighting
                (start, end) = text_buffer.get_selection_bounds()
                moved = False
                if (start.get_offset() >= len(wrap) and
                        end.get_offset() <= text_buffer.get_char_count() - len(wrap)):
                    moved = True
                    ext_start = start.copy()
                    ext_start.backward_chars(len(wrap))
                    ext_end = end.copy()
                    ext_end.forward_chars(len(wrap))
                    text = text_buffer.get_text(ext_start, ext_end, True)
                else:
                    text = text_buffer.get_text(start, end, True)

                if moved and text.startswith(wrap) and text.endswith(wrap):
                    text = text[len(wrap):-len(wrap)]
                    new_text = text
                    text_buffer.delete(ext_start, ext_end)
                    move_back = 0
                else:
                    if moved:
                        text = text[len(wrap):-len(wrap)]
                    new_text = text.lstrip().rstrip()
                    text = text.replace(new_text, wrap + new_text + wrap)

                    text_buffer.delete(start, end)
                    move_back = len(wrap)

                text_buffer.insert_at_cursor(text)
                text_length = len(new_text)

            else:
                text_buffer.insert_at_cursor(wrap + helptext + wrap)
                text_length = len(helptext)
                move_back = len(wrap)

        cursor_mark = text_buffer.get_insert()
        cursor_iter = text_buffer.get_iter_at_mark(cursor_mark)
        cursor_iter.backward_chars(move_back)
        text_buffer.move_mark_by_name('selection_bound', cursor_iter)
        cursor_iter.backward_chars(text_length)
        text_buffer.move_mark_by_name('insert', cursor_iter)

    @staticmethod
    def __select_text(text_view, offset, length):
        """Selects text starting at the current cursor
        minus offset, length characters."""

        text_buffer = text_view.get_buffer()
        cursor_mark = text_buffer.get_insert()
        cursor_iter = text_buffer.get_iter_at_mark(cursor_mark)
        cursor_iter.backward_chars(offset)
        text_buffer.move_mark_by_name('selection_bound', cursor_iter)
        cursor_iter.backward_chars(length)
        text_buffer.move_mark_by_name('insert', cursor_iter)
