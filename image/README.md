# The runtime image

The notebooks in this repository assume the agent, TokSearch and the DIII-D
skills are already installed. That environment is a container image, published
as `kaiucsd/argus-feder`.

**The build inputs are now in this repository.** A clone of this repository is
everything the build needs; nothing is fetched from a private host and no
credential is required to build.

## This repository builds releases, not development images

`main` here is the release line. An image built from it is immediately
available to users, so what lands here is a version that has been decided on,
not work in progress. Development happens in a separate tree and is synced in
deliberately, at the moment a release is cut.

Two things follow for anything automated:

- **Version with a release number, not an rc.** The build script's own usage
  examples show `-rc` tags because it is also used during development. Those
  belong to the development tree. A build from this repository should carry the
  version being released.
- **A sync into this repository is the release event.** It is not continuous.
  If builds here start tracking development commits, users get development
  images, which is the thing this split exists to prevent.

## Building

    ./scripts/build_argus_feder.sh <version>            # build and verify
    ./scripts/build_argus_feder.sh <version> --push     # also push

The script builds `argus-feder:<version>` and `kaiucsd/argus-feder:<version>`,
then runs its checks against the built image and exits non-zero if any fail.
It does not push unless `--push` is given, so a failed verification cannot
publish.

After a successful push it deletes the superseded release-candidate tags **from
the local Docker daemon**, so a 7 GB image does not accumulate once per rc on a
shared machine. It does not, and cannot, delete anything from a registry:
`docker rmi` is local, and the only remote operation in the script is the push
itself. Published rc tags therefore stay published until someone removes them by
hand. That is deliberate — deletion from a registry is irreversible, and these
images are development builds whose storage cost is not worth automating a
destructive permission for.

The build context is the repository root, and `.dockerignore` narrows it to the
roughly 2 MB the Dockerfile actually copies. Without that file the context is
the whole repository, which is sent to the daemon on every build.

## Where the build inputs are

    scripts/Dockerfile.argus          the build recipe
    scripts/build_argus_feder.sh      build, verify, push, tidy
    scripts/sage_magic.py             the %%ask cell magic: runs the agent,
                                      streams its progress, renders the review panel
    scripts/sage_kernel_backend.py    the agent's view of the notebook kernel
    scripts/deeptok_pelican.py        Pelican token discovery and activation
    scripts/apply_sage_patch.py       provider configuration applied at build time
    feder/lakehouse_api/tests/
      pod_preflight.py                checks a running pod can reach every data source
    skills/                           copied into the image as-is
    review_rules.md                   the criteria the agent's answers are checked against

These paths mirror the development repository exactly, so a release is a file
copy rather than a path rewrite. That is deliberate: every stale copy this
repository has carried came from a layout that had to be translated by hand.
`skills/` and `review_rules.md` sit at the root because `install.py` serves
them to Colab and local users from there, so the image and the installer read
one copy and cannot disagree.

## The verification step

`build_argus_feder.sh` asserts 77 properties of the built image before it will
push. Each one is something that has silently been wrong in a shipped image and
was invisible until a notebook run failed. Among them:

- the review rubric has the expected number of criteria
- every skill the notebooks depend on is present and installed
- the agent packages are at their pinned versions
- the default model is the NRP one, and no external LLM provider is baked in
- the Pelican and lakehouse helpers are the current ones

A build whose checks fail exits non-zero and publishes nothing. That exit code
is the signal an automated pipeline should gate on.

## What the image contains

- TokSearch and the DIII-D data stack, with the Pelican client configured
- The agent runtime and its provider configuration
- The skills from `skills/`
- JupyterLab

## What the image does NOT contain, by policy

- **Credentials.** The LLM API key and the DIII-D Pelican token are supplied at
  run time. Neither is ever baked in or committed here. The build itself needs
  no secret.
- **An external LLM provider.** The image ships with the NRP provider only.
  This is a governance requirement, not a preference, and the build asserts it.
- **DIII-D data.** No shot database, no signal archive, no sample data is
  included or redistributed. Every notebook reads its data live from the
  services it is given access to.

## Notes for an automated build

- The finished image is about 7 GB, and the build needs considerably more than
  that in intermediate space: it creates a second conda environment for
  `disruption-py` alongside the main one. Disk, not time, is the constraint to
  check first on a hosted runner.
- One external repository is cloned during the build, `GA-FDP/disruption-py` at
  a named branch. It is public; no token is needed.
- `--push` authenticates to Docker Hub as whatever the local Docker config
  holds. A pipeline publishing elsewhere changes the `HUB` variable near the
  top of the build script.
