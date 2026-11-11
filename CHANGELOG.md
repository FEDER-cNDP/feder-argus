# Changelog

Published images are `kaiucsd/argus-feder:<version>`. A version listed here is a
**release**; `-rc` tags are internal development builds, are not published as
releases, and are not listed.

## A note on what came before 0.2.0

This file starts at 0.2.0 because that is as far back as the record goes. The
earlier versions were built before the build inputs were kept in this
repository, and much of what changed in them lived in a skills tree that was
not under version control — between 0.1.17 and 0.1.19 there is not a single
commit covering it. Rather than reconstruct those entries from image dates and
guesswork, they are listed below with their publication dates and nothing else.
An invented changelog is worse than an absent one.

---

## 0.2.0 — 2026-11-02

**The `%%ask` progress trail now folds away once the answer is rendered.**

Before this, a long agent run left its entire progress trail expanded above the
answer, so the thing the reader wanted was pushed off the screen by the record
of how it was reached. The trail is now collapsed once the answer appears, with
a control to reopen it.

Getting that right took most of the release, because folding content in a
notebook output fights the browser:

- the trail is hidden by attribute rather than by moving it into `<details>`,
  which was reflowing the output
- the fold control is shown only after the answer exists, not for the whole run
- collapsing no longer throws the view to the end of the notebook, and no
  longer moves the reader at all when they are looking somewhere else
- the scroll correction is no longer erased before the browser runs it
- the fold survives a notebook reopened in a new pod, where saved output is
  untrusted and no JavaScript runs
- the item count stays stable across repeated collapses
- the fold no longer folds seconds before the answer arrives

Also in this release:

- `%fdp_login` no longer prints a bare `True` under its own message
- the build script's rc cleanup no longer misses a tag when the other name in
  the pair had already been removed by hand, which was leaving a 7 GB image
  behind on a shared machine

## Earlier releases

Publication dates only; see the note above.

| Version | Published |
|---|---|
| 0.1.19 | 2026-10-29 |
| 0.1.18 | 2026-10-21 |
| 0.1.17 | 2026-10-06 |
| 0.1.16 | 2026-10-06 |
| 0.1.14 | 2026-09-29 |
| 0.1.13 | 2026-09-29 |
| 0.1.12 | 2026-09-25 |
| 0.1.11 | 2026-09-24 |
| 0.1.10 | 2026-09-22 |
| 0.1.9 | 2026-09-22 |
| 0.1.8 | 2026-09-21 |
| 0.1.7 | 2026-09-08 |
| 0.1.5 | 2026-08-16 |
| 0.1.4 | 2026-08-12 |
| 0.1.3 | 2026-08-09 |

---

## Keeping this file

A release sync prints the sequence that includes editing this file:

```
scripts/sync_feder_argus.sh --release=X.Y.Z
```

Add the new version at the top before committing, so the `vX.Y.Z` tag points at
a tree whose changelog already describes it. Entries say what changed for
someone using the image, not which files moved.
