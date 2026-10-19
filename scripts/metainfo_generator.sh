#!/bin/bash
# Regenerate the committed metainfo file from NEWS and the template.
# Requires appstreamcli (appstream package).
set -e
cd "$(dirname "$0")/.."
appstreamcli news-to-metainfo --limit=3 NEWS \
  data/io.github.ch0305.Postrophe.metainfo.xml.in.in \
  data/io.github.ch0305.Postrophe.metainfo.xml.in
