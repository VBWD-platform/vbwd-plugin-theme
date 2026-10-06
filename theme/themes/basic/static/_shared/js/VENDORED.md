# Vendored runtime scripts (S152 D2)

Third-party files shipped unmodified with the `basic` theme. No Node build: the
theme serves them as-is from `/_render/_theme/static/<theme>/_shared/js/`.

`tests/unit/test_basic_theme.py::test_vendored_manifest_checksums_match_the_shipped_files`
recomputes each sha256 below and fails if a file and this table disagree.

| file | package | version | sha256 | license |
|---|---|---|---|---|
| `htmx.min.js` | htmx.org | 2.0.11 | `d6fdc75f204e6bdefa99b69bf1e6d4ac69b8a364f77929f45c13476b4000f717` | 0BSD |
| `sse.js` | htmx-ext-sse | 2.2.4 | `3b5992a541619babefc4c169505af474df5c3039da51e59b96ccf9241ecd61d2` | 0BSD |

## Provenance

- `htmx.min.js`: `https://unpkg.com/htmx.org@2.0.11/dist/htmx.min.js`, the same bytes as
  `dist/htmx.min.js` in the npm tarball `htmx.org-2.0.11.tgz` (npm integrity
  `sha512-Thx/WtpeOQqSrqBCw/A1cwGJGg4UrVa3+sW0GmrM3p4gJgO89ecH4qtbnyzDDWFvBTqjnIMCgELTNt636dtamA==`,
  checked on download).
- `sse.js`: `https://unpkg.com/htmx-ext-sse@2.2.4/dist/sse.js`, the same bytes as
  `dist/sse.js` in `htmx-ext-sse-2.2.4.tgz` (npm integrity
  `sha512-LJmxVhykyflBWgh5PvbRidcyuqMHlgfajmmzumvKctv9puvsufeH6OaejSMZTNTnEI8O2wXXn4ZZtBdpEMqmEQ==`).
  The SSE extension is versioned separately from htmx; 2.2.4 is its latest release and
  supports htmx `^2.0.2`.

## Licence

Both packages are released under the **BSD Zero Clause License (0BSD)**: htmx (Big Sky
Software) and the SSE extension (Copyright (c) 2023, Alexander Petros). 0BSD needs no
attribution; the notice is kept here for provenance:

> Permission to use, copy, modify, and/or distribute this software for any purpose with
> or without fee is hereby granted.
>
> THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH REGARD TO
> THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS. IN NO
> EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL
> DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER
> IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN
> CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

## Upgrading

Download the new files from the same unpkg paths, verify them against the npm tarball
integrity, replace them here and update the version and sha256 cells. The checksum test
then confirms the table.
