local List = require 'pandoc.List'

local M = {}

local function is_html (format)
  return format == 'html' or format == 'html4' or format == 'html5'
end

--- Create a ballot box for the given output format.
function M.ballot_box (format)
  if is_html(format) then
    return pandoc.RawInline(
      'html',
      '<input type="checkbox" class="task-list-item-checkbox" />'
    )
  elseif format == 'gfm' then
    -- GFM includes raw HTML
    return pandoc.RawInline('html', '[ ]')
  elseif format == 'org' then
    return pandoc.RawInline('org', '[ ]')
  elseif format == 'latex' then
    return pandoc.RawInline('tex', '$\\square$')
  else
    return pandoc.Str '☐'
  end
end

--- Create a checked ballot box for the given output format.
function M.ballot_box_with_check (format)
  if is_html(format) then
    return pandoc.RawInline(
      'html',
      '<input type="checkbox" class="task-list-item-checkbox" checked />'
    )
  elseif format == 'gfm' then
    -- GFM includes raw HTML
    return pandoc.RawInline('html', '[x]')
  elseif format == 'org' then
    return pandoc.RawInline('org', '[X]')
  elseif format == 'latex' then
    return pandoc.RawInline('tex', '$\\rlap{$\\checkmark$}\\square$')
  else
    return pandoc.Str '☑'
  end
end

--- Replace a Github-style task indicator with a bullet box representation
--- suitable for the given output format.
function M.todo_marker (inlines, format)
  if (inlines[1] and inlines[1].text == '[' and
      inlines[2] and inlines[2].t == 'Space' and
      inlines[3] and inlines[3].text == ']') then
    return M.ballot_box(format), 3
  elseif (inlines[1] and
            (inlines[1].text == '[x]' or
             inlines[1].text == '[X]')) then
    return M.ballot_box_with_check(format), 1
  elseif (inlines[1] and inlines[1].text == '☐') then
    -- Pandoc >= 2.15 (with task_lists on) pre-parses the marker into
    -- a sentinel character instead of leaving "[", Space, "]" as
    -- separate inlines.
    return M.ballot_box(format), 1
  elseif (inlines[1] and inlines[1].text == '☒') then
    return M.ballot_box_with_check(format), 1
  else
    return nil, 0
  end
end

M.css_styles = [[
<style>
  .task-list-item {
    list-style-type: none;
  }
  .task-list-item-checkbox {
    margin-left: -1.6em;
    cursor: pointer;
  }
</style>
]]

-- Posts the clicked task item's index (in document order, matching
-- task_list.nth_task_line_offset on the Python side) to the app.
M.click_script = [[
<script>
  document.addEventListener('click', function (event) {
    var target = event.target;
    if (!target || !target.classList ||
        !target.classList.contains('task-list-item-checkbox')) {
      return;
    }
    var item = target.closest('li[data-task-index]');
    if (item && window.webkit && window.webkit.messageHandlers &&
        window.webkit.messageHandlers.postropheTaskToggle) {
      window.webkit.messageHandlers.postropheTaskToggle.postMessage(
        parseInt(item.getAttribute('data-task-index'), 10));
    }
  });
</script>
]]

--- Add task-list CSS styles and the click script to the header.
function M.add_task_list_css(meta)
  local header_includes
  if meta['header-includes'] and meta['header-includes'].t == 'MetaList' then
    header_includes = meta['header-includes']
  else
    header_includes = pandoc.MetaList{meta['header-includes']}
  end
  header_includes[#header_includes + 1] =
    pandoc.MetaBlocks{pandoc.RawBlock('html', M.css_styles)}
  header_includes[#header_includes + 1] =
    pandoc.MetaBlocks{pandoc.RawBlock('html', M.click_script)}
  meta['header-includes'] = header_includes
  return meta
end

--- Replace the todo marker in the given block, if any.
function M.replace_todo_markers (blk, format)
  if not blk or blk.t ~= 'Para' and blk.t ~= 'Plain' then
    return blk
  end
  local inlines = blk.content
  local box, num_inlines = M.todo_marker(inlines, format)
  if box == nil then
    return blk
  end
  local new_inlines = List:new{box}
  for j = 1, #inlines do
    new_inlines[j + 1] = inlines[j + num_inlines]
  end
  return pandoc[blk.t](new_inlines) -- create Plain or Para
end

--- Convert Github- and org-mode-style task markers in a BulletList.
function M.modifyBulletList (list)
  if not is_html(FORMAT) then
    for _, item in ipairs(list.content) do
      item[1] = M.replace_todo_markers(item[1], FORMAT)
    end
    return list
  else
    local res = List:new{pandoc.RawBlock('html', '<ul>')}
    local task_index = 0
    for _, item in ipairs(list.content) do
      local blk = M.replace_todo_markers(item[1], FORMAT)
      if blk == item[1] then -- does not have a todo marker
        res[#res + 1] = pandoc.RawBlock('html', '<li>')
      else
        -- data-task-index lets the click script tell Python which
        -- source line to toggle; document order only.
        res[#res + 1] = pandoc.RawBlock(
          'html',
          '<li class="task-list-item" data-task-index="' ..
          task_index .. '">')
        task_index = task_index + 1
        item[1] = blk
      end
      res:extend(item)
      res[#res + 1] = pandoc.RawBlock('html', '</li>')
    end
    res[#res + 1] = pandoc.RawBlock('html', '</ul>')
    return res
  end
end

--- Renumber data-task-index attributes in document order.
--- modifyBulletList runs once per list (nested and quoted lists each
--- get their own numbering), so indices are renumbered here over the
--- fully transformed AST, in the same order Python's
--- task_list.nth_task_line_offset counts source lines.
local function renumber_task_items (doc)
  local counter = 0
  local function renumber_raw (raw)
    if raw.format ~= 'html' then
      return raw
    end
    local text = raw.text:gsub('data%-task%-index="%d+"', function ()
      local replacement = 'data-task-index="' .. counter .. '"'
      counter = counter + 1
      return replacement
    end)
    return pandoc.RawBlock('html', text)
  end
  local div = pandoc.walk_block(pandoc.Div(doc.blocks),
                                { RawBlock = renumber_raw })
  return pandoc.Pandoc(div.content, doc.meta)
end

M[1] = {
  BulletList = M.modifyBulletList,
  Pandoc = is_html(FORMAT) and renumber_task_items or nil,
  Meta = is_html(FORMAT) and M.add_task_list_css or nil
}

return M
