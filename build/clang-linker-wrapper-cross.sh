#!/bin/bash

topsrcdir=$(dirname $0)

$topsrcdir/clang/bin/clang \
    -B$topsrcdir/cctools/bin \
    -target x86_64-apple=darwin11.2.0 \
    -isysroot $topsrcdir/MacOSX10.7.sdk $*
