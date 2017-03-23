#!/bin/bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Install yasm

tooltool_fetch <<'EOF'
[
  {
    "size": 1492156,
    "digest": "572d3b45568b10f58e48f1188c2d6bcbdd16429c8afaccc8c6d37859b45635e106885d679e41d0bee78c23822108c7ae75aa7475eed5ba58057e0a6fe1b68645",
    "algorithm": "sha512",
    "filename": "yasm-1.3.0.tar.gz",
    "unpack": true
  }
]
EOF

cd yasm-1.3.0
./configure --prefix=/usr
make
make install
yasm --version
