# Third-party notices

The source, scripts and documentation in this repository are released under the
MIT License (see `LICENSE`). The binaries produced by the `build-dropbear-arm`
workflow are **derived works of third-party software** and remain under their
own licenses, which are permissive and compatible with MIT. This file records
what is in the Release so the attribution obligations are actually met.

## dropbear

* Upstream: <https://github.com/mkj/dropbear> — the official repository, linked
  from the project site <https://matt.ucc.asn.au/dropbear/dropbear.html> and vice
  versa.
* Pinned commit built by CI: `28216cd9af822732a1549b78621c2ea9a76a0fe5`
  (release 2026.94).
* License: MIT-style, verbatim in the upstream `LICENSE` file:

  > Copyright (c) 2002-2020 Matt Johnston
  > Portions copyright (c) 2004 Mihnea Stoenescu
  > All rights reserved.
  >
  > Permission is hereby granted, free of charge, to any person obtaining a copy
  > of this software and associated documentation files (the "Software"), to deal
  > in the Software without restriction, including without limitation the rights
  > to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
  > copies of the Software, and to permit persons to whom the Software is
  > furnished to do so, subject to the following conditions:
  >
  > The above copyright notice and this permission notice shall be included in all
  > copies or substantial portions of the Software.

  GitHub reports `NOASSERTION` for this file only because upstream concatenates
  several permissive licenses in it, not because the terms are restrictive.
* Bundled components inside dropbear: LibTomCrypt and LibTomMath (Tom St Denis
  and others, public domain / permissive), and `sshpty.c` taken from OpenSSH
  3.5p1 (BSD-style). Each carries its own notice in the upstream tree.

## musl

* Upstream: <https://musl.libc.org>, released under the MIT license.
* Version built by CI: recorded per run in `SHA256SUMS.txt` together with the
  SHA256 of the downloaded tarball.
* The authoritative copyright lines travel inside the fetched
  `musl-<version>.tar.gz` (`COPYRIGHT` file); they are not re-transcribed here so
  that this file cannot drift from what was actually built.

## Meeting the attribution condition

The MIT-style condition is "include the copyright and permission notice in all
copies or substantial portions". Anyone redistributing the Release bundle should
keep this file alongside `be5000_bins/`. The CI bundle includes it, and
`SHA256SUMS.txt` pins exactly which upstream commit and which musl tarball the
binaries came from, so the provenance travels with the artifact.

## Not included

No firmware, binaries or configuration from the target router are redistributed
here. Xiaomi MiWiFi firmware is the vendor's proprietary work and is not part of
this repository; the firmware analysed to write this tool was obtained by the
device owner from Xiaomi's own update channel.
