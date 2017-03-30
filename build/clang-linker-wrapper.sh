#!/bin/bash

topsrcdir=$(dirname $0)

$topsrcdir/clang/bin/clang -B$topsrcdir/cctools/bin $*
