import unittest

from postrophe import task_list


class TestParseTaskLine(unittest.TestCase):
    def test_unchecked_dash(self):
        match = task_list.parse_task_line("- [ ] buy milk")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "")
        self.assertEqual(match.group(2), "-")
        self.assertEqual(match.group(3), " ")
        self.assertEqual(match.group(4), "buy milk")

    def test_checked_dash(self):
        match = task_list.parse_task_line("- [x] done")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(3), "x")
        self.assertEqual(match.group(4), "done")

    def test_checked_uppercase(self):
        match = task_list.parse_task_line("- [X] done")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(3), "X")

    def test_indent_asterisk(self):
        match = task_list.parse_task_line("  * [ ] indented")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "  ")
        self.assertEqual(match.group(2), "*")
        self.assertEqual(match.group(4), "indented")

    def test_plus_bullet(self):
        self.assertIsNotNone(task_list.parse_task_line("+ [ ] item"))

    def test_empty_content(self):
        match = task_list.parse_task_line("- [ ] ")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(4), "")

    def test_bare_unchecked_marker(self):
        # pandoc still renders "- [ ]" (no content) as a task item.
        match = task_list.parse_task_line("- [ ]")
        self.assertIsNotNone(match)
        self.assertIsNone(match.group(4))

    def test_bare_checked_marker(self):
        match = task_list.parse_task_line("- [x]")
        self.assertIsNotNone(match)
        self.assertIsNone(match.group(4))

    def test_trailing_spaces_only(self):
        match = task_list.parse_task_line("- [x]   ")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(4), "")

    def test_multiple_spaces_after_bullet(self):
        match = task_list.parse_task_line("-  [ ] two spaces")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(4), "two spaces")

    def test_tab_after_marker(self):
        match = task_list.parse_task_line("- [ ]\ttabbed")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(4), "tabbed")

    def test_blockquote(self):
        match = task_list.parse_task_line("> - [ ] quoted")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "> ")
        self.assertEqual(match.group(4), "quoted")

    def test_nested_blockquote(self):
        match = task_list.parse_task_line(">> - [x] quoted")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), ">> ")

    def test_indented_blockquote(self):
        match = task_list.parse_task_line("  > - [ ] quoted")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "  > ")

    def test_plain_list_is_not_task(self):
        self.assertIsNone(task_list.parse_task_line("- plain item"))
        self.assertIsNone(task_list.parse_task_line("* also plain"))

    def test_missing_space_after_bracket(self):
        # pandoc only treats "- [x] text" as a task; without the space
        # the marker is literal text.
        self.assertIsNone(task_list.parse_task_line("- [x]text"))
        self.assertIsNone(task_list.parse_task_line("- [ ]text"))

    def test_checkbox_without_bullet(self):
        self.assertIsNone(task_list.parse_task_line("[ ] no bullet"))


class TestTaskMarkerEnd(unittest.TestCase):
    def test_with_content(self):
        match = task_list.parse_task_line("- [ ] buy milk")
        self.assertEqual(task_list.task_marker_end(match), 6)

    def test_empty_content(self):
        match = task_list.parse_task_line("- [ ] ")
        self.assertEqual(task_list.task_marker_end(match), 6)

    def test_bare_marker(self):
        match = task_list.parse_task_line("- [x]")
        self.assertEqual(task_list.task_marker_end(match), 5)

    def test_blockquote_marker_end(self):
        match = task_list.parse_task_line("> - [ ] quoted")
        self.assertEqual(task_list.task_marker_end(match), 8)


class TestLinePrefixLength(unittest.TestCase):
    def test_no_prefix(self):
        self.assertEqual(task_list.line_prefix_length("- item"), 0)

    def test_indent(self):
        self.assertEqual(task_list.line_prefix_length("  - item"), 2)

    def test_quote(self):
        self.assertEqual(task_list.line_prefix_length("> item"), 2)

    def test_indent_quote(self):
        self.assertEqual(task_list.line_prefix_length("  > item"), 4)

    def test_text_line(self):
        self.assertEqual(task_list.line_prefix_length("plain text"), 0)


class TestParsePlainAndOrdered(unittest.TestCase):
    def test_plain_list(self):
        match = task_list.parse_plain_list_line("- item")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(2), "-")
        self.assertIsNone(task_list.parse_plain_list_line("no list"))

    def test_plain_list_in_blockquote(self):
        match = task_list.parse_plain_list_line("> - item")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "> ")

    def test_ordered_line_dot(self):
        match = task_list.parse_ordered_line("3. item")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(2), "3")
        self.assertEqual(match.group(3), ".")

    def test_ordered_line_paren(self):
        match = task_list.parse_ordered_line("12) item")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(2), "12")
        self.assertEqual(match.group(3), ")")

    def test_ordered_line_in_blockquote(self):
        match = task_list.parse_ordered_line("> 3. item")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "> ")

    def test_ordered_line_not_ordered(self):
        self.assertIsNone(task_list.parse_ordered_line("1.item"))
        self.assertIsNone(task_list.parse_ordered_line("- item"))


class TestNextOrderedPrefix(unittest.TestCase):
    def test_increments(self):
        self.assertEqual(task_list.next_ordered_prefix("3. item"), "4. ")

    def test_double_digit(self):
        self.assertEqual(task_list.next_ordered_prefix("9. item"), "10. ")

    def test_paren_delimiter(self):
        self.assertEqual(task_list.next_ordered_prefix("2) item"), "3) ")

    def test_indent_preserved(self):
        self.assertEqual(task_list.next_ordered_prefix("  1. item"), "  2. ")

    def test_quote_preserved(self):
        self.assertEqual(task_list.next_ordered_prefix("> 3. item"), "> 4. ")

    def test_not_ordered(self):
        self.assertIsNone(task_list.next_ordered_prefix("- item"))


class TestVisualIndent(unittest.TestCase):
    def test_spaces(self):
        self.assertEqual(task_list.visual_indent("  - item"), 2)

    def test_tab(self):
        self.assertEqual(task_list.visual_indent("\t- item"), 4)

    def test_space_then_tab(self):
        self.assertEqual(task_list.visual_indent("  \t- item"), 4)

    def test_quote_marker_is_zero(self):
        self.assertEqual(task_list.visual_indent("> - item"), 0)


class TestInCodeBlock(unittest.TestCase):
    def test_open_fence(self):
        self.assertTrue(task_list.in_code_block("text\n```\ncode"))

    def test_closed_fence(self):
        self.assertFalse(task_list.in_code_block("```\ncode\n```\ntext"))

    def test_no_fence(self):
        self.assertFalse(task_list.in_code_block("just text"))

    def test_tilde_fence(self):
        self.assertTrue(task_list.in_code_block("~~~\ncode"))

    def test_quoted_fence(self):
        self.assertTrue(task_list.in_code_block("> ```\n> code"))


class TestNthTaskLineOffset(unittest.TestCase):
    def test_first_task(self):
        text = "intro\n- [ ] first\n- [x] second\n"
        self.assertEqual(task_list.nth_task_line_offset(text, 0), 6)

    def test_second_task(self):
        text = "intro\n- [ ] first\n- [x] second\n"
        offset = task_list.nth_task_line_offset(text, 1)
        self.assertEqual(text[offset:], "- [x] second\n")

    def test_index_out_of_range(self):
        text = "- [ ] only one\n"
        self.assertIsNone(task_list.nth_task_line_offset(text, 1))
        self.assertIsNone(task_list.nth_task_line_offset(text, 99))

    def test_empty_text(self):
        self.assertIsNone(task_list.nth_task_line_offset("", 0))

    def test_task_in_code_fence_ignored(self):
        text = "```\n- [ ] code\n```\n- [ ] real\n"
        offset = task_list.nth_task_line_offset(text, 0)
        self.assertEqual(text[offset:], "- [ ] real\n")
        self.assertIsNone(task_list.nth_task_line_offset(text, 1))

    def test_plain_list_ignored(self):
        text = "- plain\n- [ ] task\n"
        offset = task_list.nth_task_line_offset(text, 0)
        self.assertEqual(text[offset:], "- [ ] task\n")

    def test_bare_markers_counted(self):
        text = "- [x]\n- [ ] second\n"
        self.assertEqual(task_list.nth_task_line_offset(text, 0), 0)
        self.assertEqual(task_list.nth_task_line_offset(text, 1), 6)

    def test_blockquote_task_counted(self):
        text = "> - [ ] quoted\n- [ ] flat\n"
        self.assertEqual(task_list.nth_task_line_offset(text, 0), 0)
        self.assertEqual(task_list.nth_task_line_offset(text, 1),
                         text.index("- [ ] flat"))

    def test_nested_task_counted(self):
        text = "- [ ] parent\n    - [ ] child\n"
        self.assertEqual(task_list.nth_task_line_offset(text, 1),
                         text.index("    - [ ] child"))

    def test_nested_task_under_plain_parent(self):
        text = "- parent\n    - [ ] child\n"
        self.assertEqual(task_list.nth_task_line_offset(text, 0),
                         text.index("    - [ ] child"))

    def test_indented_code_at_document_start_ignored(self):
        text = "    - [ ] code\n\n- [ ] real\n"
        self.assertEqual(task_list.nth_task_line_offset(text, 0),
                         text.index("- [ ] real"))
        self.assertIsNone(task_list.nth_task_line_offset(text, 1))

    def test_indented_code_after_text_ignored(self):
        text = "text\n\n    - [ ] code\n"
        self.assertIsNone(task_list.nth_task_line_offset(text, 0))

    def test_lazy_paragraph_continuation_ignored(self):
        text = "text\n    - [ ] lazy\n\n- [ ] real\n"
        self.assertEqual(task_list.nth_task_line_offset(text, 0),
                         text.index("- [ ] real"))

    def test_deep_indent_after_list_ignored(self):
        # 8 columns: pandoc treats this as an indented code block.
        text = "- parent\n\n        - [ ] deep\n"
        self.assertIsNone(task_list.nth_task_line_offset(text, 0))

    def test_four_space_nested_after_blank_counted(self):
        # 4 columns: pandoc parses this as a nested list item.
        text = "- parent\n\n    - [ ] four\n"
        self.assertEqual(task_list.nth_task_line_offset(text, 0),
                         text.index("    - [ ] four"))

    def test_quoted_code_fence_ignored(self):
        text = "> ```\n> - [ ] x\n> ```\n- [ ] real\n"
        self.assertEqual(task_list.nth_task_line_offset(text, 0),
                         text.index("- [ ] real"))

    def test_task_after_blank_text_not_counted(self):
        text = "- [ ] a\n\ntext\n    - [ ] b\n"
        self.assertEqual(task_list.nth_task_line_offset(text, 0), 0)
        self.assertIsNone(task_list.nth_task_line_offset(text, 1))


if __name__ == "__main__":
    unittest.main()
