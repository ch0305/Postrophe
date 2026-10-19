# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-

"""Line parsing helpers for Markdown lists and task items.

Pure-stdlib module (no GTK imports): unit-testable without a display.
Always check task items before plain list items: PLAIN_LIST also
matches "- [ ] foo" (the bullet is followed by "["), so callers must
try TASK_ITEM first.
"""

import re

# Optional indentation plus blockquote markers ("> ", "> > ", ...).
QUOTE_PREFIX = r"\s*(?:\s*>\s*)*"

# "- ", "* ", "+ " unordered list item.
PLAIN_LIST = re.compile(r"^(" + QUOTE_PREFIX + r")([-*+]) ")

# "1. " or "1)" ordered list item.
ORDERED_ITEM = re.compile(r"^(" + QUOTE_PREFIX + r")(\d+)([.)]) ")

# "- [ ] " / "- [x] " GFM task item.
#   group 1: indent + blockquote prefix
#   group 2: bullet
#   group 3: checkbox state char
#   group 4: content, or None when the marker has no content
#
# The marker must be followed by whitespace or the end of the line.
# This mirrors pandoc: "- [x]text" is a plain list, not a task item,
# while a bare "- [x]" is still a (content-less) task item.
TASK_ITEM = re.compile(
    r"^(" + QUOTE_PREFIX + r")([-*+])[ \t]+\[([ xX])\](?:[ \t]+(.*))?$")


def parse_plain_list_line(line):
    """Return the regex match for an unordered list line, or None."""
    return PLAIN_LIST.match(line)


def parse_ordered_line(line):
    """Return the regex match for an ordered list line, or None."""
    return ORDERED_ITEM.match(line)


def parse_task_line(line):
    """Return the regex match for a GFM task line, or None."""
    return TASK_ITEM.match(line)


def task_marker_end(match):
    """End offset of the task marker ("- [x] ") within the matched line.

    group(4) is None for a bare marker ("- [x]" with no content); the
    marker then ends at the end of the match."""
    if match.group(4) is None:
        return match.end()
    return match.start(4)


def line_prefix_length(line):
    """Character length of the leading indentation + blockquote markers.

    Used to insert a new list marker after an existing "> " prefix
    instead of before it."""
    match = re.match(r"^" + QUOTE_PREFIX, line)
    return match.end() if match else 0


def next_ordered_prefix(line):
    """Return the next marker for an ordered list line ("3. " -> "4. ").

    Returns None when the line is not an ordered list item."""
    match = ORDERED_ITEM.match(line)
    if not match:
        return None
    return "{}{}{} ".format(match.group(1),
                            int(match.group(2)) + 1,
                            match.group(3))


def _fence_text(line):
    """Line content with indentation and blockquote markers removed.

    Used for fence detection so that a code block inside a blockquote
    is recognised as a fence too."""
    stripped = line.lstrip()
    return re.sub(r"^(?:>[ \t]*)+", "", stripped)


def in_code_block(text):
    """Return True when text ends inside a fenced code block.

    Used to avoid list continuation inside ``` / ~~~ fences."""

    fences = 0
    for line in text.splitlines():
        fence = _fence_text(line)
        if fence.startswith("```") or fence.startswith("~~~"):
            fences += 1
    return fences % 2 == 1


def visual_indent(line):
    """Width of the leading whitespace, counting a tab as up to 4.

    Returns 0 for lines starting with a blockquote marker."""

    column = 0
    for char in line:
        if char == " ":
            column += 1
        elif char == "\t":
            column = column - column % 4 + 4
        else:
            break
    return column


def nth_task_line_offset(text, n):
    """Character offset of the (n + 1)th task item line in text, or None.

    Counts GFM task lines in document order, mirroring what pandoc's
    task-list.lua sees when rendering the preview (it assigns
    data-task-index in that same order).

    Fenced code blocks are skipped. Lines indented by 4+ columns are
    only counted when they continue an open list: otherwise pandoc
    treats them as indented code or as a lazy paragraph continuation,
    and counting them would shift every later index.

    Offsets are in characters (GtkTextBuffer units)."""

    offset = 0
    count = 0
    in_fence = False
    list_open = False
    after_blank = True
    for line in text.splitlines(keepends=True):
        fence = _fence_text(line)
        if fence.startswith("```") or fence.startswith("~~~"):
            in_fence = not in_fence
            after_blank = False
        elif in_fence:
            if line.strip():
                after_blank = False
        elif not line.strip():
            after_blank = True
        else:
            match = TASK_ITEM.match(line)
            indent = visual_indent(line)
            if match:
                # Flat items always count; deeply indented ones only
                # while a list is open (see docstring).
                if indent < 4 or (list_open and indent <= 5):
                    if count == n:
                        return offset
                    count += 1
                    list_open = True
            elif PLAIN_LIST.match(line) or ORDERED_ITEM.match(line):
                if indent < 4 or list_open:
                    list_open = True
            elif indent == 0 and after_blank:
                # Top-level text after a blank line ends the list.
                list_open = False
            after_blank = False
        offset += len(line)
    return None
