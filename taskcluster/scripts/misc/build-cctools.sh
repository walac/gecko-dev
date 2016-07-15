#!/bin/bash
set -x -e -v

# This script is for building cctools (Apple's binutils) for Linux using
# crosstool-ng (https://github.com/diorcety/crosstool-ng).

WORKSPACE=$HOME/workspace
UPLOAD_DIR=$WORKSPACE/artifacts

# Repository info
: CROSSTOOL_NG_REPOSITORY    ${CROSSTOOL_NG_REPOSITORY:=https://github.com/crosstool-ng/crosstool-ng}
: CROSSTOOL_NG_REV           ${CROSSTOOL_NG_REV:=master}

# hacky
ln -s /usr/bin/gcc ~/bin/x86_64-linux-gnu-gcc
export PATH=$PATH:~/bin:~/workspace/cctools/bin

# Set some crosstools-ng directories
CT_TOP_DIR=$WORKSPACE/crosstool-ng-build
CT_PREFIX_DIR=$WORKSPACE/cctools
CT_INSTALL_DIR=${CT_PREFIX_DIR}
CT_SRC_DIR=$CT_TOP_DIR/src
CT_TARBALLS_DIR=$CT_TOP_DIR
CT_WORK_DIR=$CT_SRC_DIR
CT_LIB_DIR=$WORKSPACE/crosstool-ng
CT_BUILD_DIR=$CT_TOP_DIR/build
CT_LLVM_DIR=$WORKSPACE/clang
CT_BUILDTOOLS_PREFIX_DIR=$CT_PREFIX_DIR
CC_CC="clang"
CT_CC_CORE_STATIC_PREFIX_DIR="${CT_BUILD_DIR}/${CC_CC}-core-static"
CT_CC_CORE_SHARED_PREFIX_DIR="${CT_BUILD_DIR}/${CC_CC}-core-shared"

# Create our directories
rm -rf $CT_TOP_DIR
mkdir $CT_TOP_DIR
rm -rf $CT_PREFIX_DIR
mkdir $CT_PREFIX_DIR
mkdir -p $CT_SRC_DIR

# Clone the crosstool-ng repo
# Building cctools is not a task we do often, so forcing a clone in
# we don't find a cached repo won't kill us
tc-vcs checkout --force-clone $CT_LIB_DIR $CROSSTOOL_NG_REPOSITORY $CROSSTOOL_NG_REPOSITORY $CROSSTOOL_NG_REV

# Fetch clang from tooltool
cd $WORKSPACE
wget -O tooltool.py https://raw.githubusercontent.com/mozilla/build-tooltool/master/tooltool.py
chmod +x tooltool.py
: TOOLTOOL_CACHE                ${TOOLTOOL_CACHE:=/home/worker/tooltool-cache}
export TOOLTOOL_CACHE

wget ${GECKO_HEAD_REPOSITORY}/raw-file/${GECKO_HEAD_REV}/browser/config/tooltool-manifests/linux64/clang.manifest

python tooltool.py -v --manifest=clang.manifest fetch

# Copy clang into the crosstools-ng srcdir
cp -Rp $CT_LLVM_DIR $CT_SRC_DIR

# Configure crosstools-ng
sed=sed
CT_CONNECT_TIMEOUT=5
CT_PATCH_ORDER=bundled
CT_BUILD=x86_64-linux-gnu
CT_HOST=x86_64-linux-gnu
CT_TARGET=x86_64-apple-darwin10
CT_LLVM_FULLNAME=clang

#
# GNU binutils
#
CT_BINUTILS_VERSION="2.22"
CT_BINUTILS_FOR_TARGET=y
CT_BINUTILS_FOR_TARGET_IBERTY=y
# CT_BINUTILS_FOR_TARGET_BFD=y
CT_BINUTILS_2_22_or_later=y
CT_BINUTILS_2_21_or_later=y
CT_BINUTILS_2_20_or_later=y
CT_BINUTILS_2_19_or_later=y
CT_BINUTILS_2_18_or_later=y
CT_BINUTILS_HAS_HASH_STYLE=y
CT_BINUTILS_HAS_GOLD=y
CT_BINUTILS_GOLD_SUPPORTS_ARCH=y
CT_BINUTILS_HAS_PLUGINS=y
CT_BINUTILS_HAS_PKGVERSION_BUGURL=y
CT_BINUTILS_LINKER_LD=y
CT_BINUTILS_LINKER_GOLD=y
# CT_BINUTILS_LINKER_LD_GOLD is not set
# CT_BINUTILS_LINKER_GOLD_LD is not set
CT_BINUTILS_LINKERS_LIST="gold,ld"
CT_BINUTILS_LINKER_DEFAULT="bfd"
# CT_BINUTILS_PLUGINS is not set
CT_BINUTILS_EXTRA_CONFIG_ARRAY=""
patch=patch

cd $CT_TOP_DIR

# gets a bit too verbose here
set +x

. $CT_LIB_DIR/scripts/functions
. $CT_LIB_DIR/scripts/build/binutils/binutils.sh

# Build cctools
do_binutils_get
do_binutils_extract
do_binutils_for_build
do_binutils_for_host
do_binutils_for_target

set -x

strip $CT_PREFIX_DIR/bin/*

# Put a tarball in the artifacts dir
mkdir -p $UPLOAD_DIR
tar czf $UPLOAD_DIR/cctools.tar.gz -C $WORKSPACE `basename $CT_PREFIX_DIR`
