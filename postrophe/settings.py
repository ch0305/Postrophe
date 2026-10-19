# BEGIN LICENSE
# Copyright (C) 2019, Wolf Vollprecht <w.vollprecht@gmail.com>
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranties of
# MERCHANTABILITY, SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR
# PURPOSE.  See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program.  If not, see <http://www.gnu.org/licenses/>.
# END LICENSE

"""Postrophe settings.

The GSettings schema id changed from Apostrophe's
``org.gnome.gitlab.somas.Apostrophe`` to ``io.github.ch0305.Postrophe``.
On the first start with the new schema the old dconf values are copied
over once, so that existing users keep their preferences.
"""

import subprocess

from gi.repository import Gio, GLib

from postrophe import config


LEGACY_SCHEMA_PATH = "/org/gnome/gitlab/somas/Apostrophe/"


class Settings(Gio.Settings):

    """
        Postrophe Settings
    """

    def __init__(self):
        """
            Init Settings
        """
        Gio.Settings.__init__(self)

    @classmethod
    def new(cls):
        """
            Return a new Settings object
        """
        settings = Gio.Settings.new(config.SCHEMA_ID)
        settings.__class__ = Settings
        settings._migrate_legacy_settings()
        return settings

    def _migrate_legacy_settings(self):
        """Copy the old Apostrophe settings on the first run."""
        schema = Gio.SettingsSchemaSource.get_default().lookup(
            config.SCHEMA_ID, True)
        if schema is None:
            return
        if any(self.get_user_value(key) is not None
               for key in schema.list_keys()):
            return

        try:
            dump = subprocess.run(
                ["dconf", "dump", LEGACY_SCHEMA_PATH],
                capture_output=True, text=True, timeout=2, check=False)
        except (OSError, subprocess.SubprocessError):
            return
        if dump.returncode != 0 or not dump.stdout.strip():
            return

        for line in dump.stdout.splitlines():
            if "=" not in line or line.startswith("["):
                continue
            key, raw = line.split("=", 1)
            key = key.strip()
            if not schema.has_key(key):
                continue
            try:
                value = GLib.Variant.parse(
                    schema.get_key(key).get_value_type(), raw, None, None)
            except GLib.Error:
                continue
            self.set_value(key, value)
