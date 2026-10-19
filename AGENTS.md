# AGENTS.md

## What this is

Postrophe: a GTK **3** + Python (PyGObject) distraction-free Markdown editor. It is a
fork of Apostrophe 2.4. `pandoc` does all Markdown conversion; the preview renders in
WebKit2GTK. Meson build system.

Layout:

- `postrophe/` — the entire Python package (one flat package, no subpackages)
  - entry chain: `postrophe.in` → `Application` (`postrophe/application.py`) →
    `main_window.py` → `text_view*.py` (editing) and `preview_*.py` (pandoc → WebKit)
- `data/` — GResources: GtkBuilder `.ui` files, SCSS themes, web-preview CSS, pandoc
  Lua filters (`data/lua/`), GSchema, desktop/metainfo files
- `tests/` — plain `unittest`, not wired into Meson
- `.github/workflows/build.yml` — CI: builds a `.deb` on every push, publishes tagged
  releases and a rolling `latest` pre-release
- `build-aux/flatpak/` — inherited from upstream Apostrophe, unmaintained here

## Build and run

```bash
./run-dev.sh                     # development build + local run
# or manually:
meson setup builddir --prefix=/usr -Dprofile=development
ninja -C builddir
./builddir/local-postrophe       # run from source tree, no install needed
sudo ninja -C builddir install   # then: postrophe
```

- `local-postrophe` is the launcher to use during development. It prepends the source
  tree to `sys.path` and points `XDG_DATA_DIRS` at `builddir/data` for compiled schemas.
- `-Dprofile=development` appends `.Devel` to the app id
  (`io.github.ch0305.Postrophe.Devel`). The GSettings schema id stays
  `io.github.ch0305.Postrophe` for both profiles.
- Release build and Debian package:

```bash
./make-deb.sh
sudo apt install ./postrophe_<version>_amd64.deb
```

The package `Conflicts`/`Replaces` both `apostrophe` and `apostrophe-devel`.
`make-deb.sh` wipes and reconfigures `builddir` with the release profile.

## Generated files — edit the source, never the output

| Do not edit | Edit instead |
|---|---|
| `postrophe/config.py` (build output; local-run convenience copy) | `config.py.in` |
| `builddir/...`, `local-postrophe`, `postrophe` launcher | `postrophe.in` |
| `data/media/css/gtk/Adwaita*.css` (sassc builds them at compile time) | `data/media/css/gtk/*.scss` |
| `data/io.github.ch0305.Postrophe.metainfo.xml.in` (regenerated from `.in.in` + `NEWS`) | `…metainfo.xml.in.in` + `NEWS`, then `scripts/metainfo_generator.sh` (needs `appstreamcli`) |

Adding a new `data/ui/*.ui` file requires **both** adding it to
`data/postrophe.gresource.xml` and to `po/POTFILES.in`.

Translation workflow: `ninja -C builddir postrophe-pot` then
`ninja -C builddir postrophe-update-po` (same as `po/update_translations.sh`).

## Tests, lint, verification

From the **repo root**:

```bash
/usr/bin/python3 -m unittest discover -s tests        # run all tests
/usr/bin/python3 -m unittest tests.test_task_list     # the fork's task-list tests
pylint -E postrophe                                   # config: postrophe/.pylintrc
```

- Tests must run from the repo root: they do `from postrophe import …`, relying on the
  cwd being on `sys.path`.
- Use `/usr/bin/python3` (the system Python with PyGObject), not a uv/conda python.
- **Pre-existing failures — do not chase them:** `test_bold` fails against
  `markup_regex.BOLD` (upstream issue); the header tests pass. `test_lint.py` needs
  `pylint` on `PATH`.
- GUI verification needs a display; there is no headless UI test harness.

## Code conventions

- GTK **3** + `libhandy-1`, not GTK4/libadwaita.
- Pandoc is invoked with explicit `--lua-filter=` args pointing at
  `data/lua/relative_to_absolute.lua` and `data/lua/task-list.lua` — keep both
  `preview_converter.py` and `export_dialog.py` in sync.
- The preview update path (`preview_handler.py` + `preview_web_view.py`): after the first
  `load_html()`, edits only replace `<body>` via `update_html()` to avoid a white flash.
  Keep the document head (CSS, scripts, MathJax) alive when changing this.
- `data/lua/task-list.lua` injects `data-task-index` attributes and the checkbox click
  handler; `postrophe/task_list.py` maps those indices back to source lines.
