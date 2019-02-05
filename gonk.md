# Gecko on Gonk

This is an experiment to see what it takes to build current Gecko on Gonk (M base).

Currently the setup is:
- get an Android M clone of B2G
  `git clone --branch emulator-m https://github.com/gabrielesvelto/B2G`
  `git clone --branch emulator-m https://github.com/gabrielesvelto/b2g-manifest`
  `cd B2G`
  `env REPO_INIT_FLAGS="--depth=1" REPO_SYNC_FLAGS="-j16 --force-sync" GITREPO=../b2g-manifest BRANCH=emulator-m ./config.sh emulator-m`

- modify mozconfig-b2g to point to an android NDK r17b & SDK
- `export MOZCONFIG=mozconfig-b2g`
- `export GONK_PATH=../B2G`
- run `./mach build`

I tried to setup the build more manually with the toolchain flags as environment variables in the `build-b2g.sh` script. This may be the right path but that doesn't work either yet.

Note that Gecko now builds with clang > 3.8 instead of gcc. It's unclear if it's mandatory for now but it's likely that gcc builds will break sooner or later.
