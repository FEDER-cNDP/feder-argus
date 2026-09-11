# The runtime image

The notebooks in this repository assume the agent, TokSearch and the DIII-D
skills are already installed. That environment is a container image, published
as `kaiucsd/argus-feder`.

**The build inputs are not in this repository yet.** This directory is where
they go. It is documented here so the layout is settled before the files
arrive, rather than after.

## Intended layout

    image/
      Dockerfile          the build recipe; build context is the repository root
      runtime/            files the image installs into the running kernel
        sage_magic.py         defines the %%ask cell magic: runs the agent,
                              streams its progress, and renders the review panel
        sage_kernel_backend.py    the agent's view of the notebook kernel
        deeptok_pelican.py        Pelican token discovery and activation
        apply_sage_patch.py       provider configuration applied at build time
      preflight/
        pod_preflight.py    checks a running pod can reach every data source
      build.sh            tag, build, push

`skills/` at the repository root is copied into the image as-is; it is content
rather than build machinery, so it stays where it is rather than moving under
`image/`.

## What the image contains

- TokSearch and the DIII-D data stack, with the Pelican client configured
- The agent runtime and its provider configuration
- The skills from `skills/`
- JupyterLab

## What the image does NOT contain, by policy

- **Credentials.** The LLM API key and the DIII-D Pelican token are supplied at
  run time. Neither is ever baked in or committed here.
- **DIII-D data.** No shot database, no signal archive, no sample data is
  included or redistributed. Every notebook reads its data live from the
  services it is given access to.

## Building, once the files are here

    docker build -t argus-feder:<version> -f image/Dockerfile .

The build context is the repository root so that `skills/` is reachable.
