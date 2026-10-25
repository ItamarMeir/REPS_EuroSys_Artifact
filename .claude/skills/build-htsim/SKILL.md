---
name: build-htsim
description: Docker build/run details and fixes for htsim_uec crashes, GLIBCXX errors, or "Failed to load connection matrix".
---

`htsim_uec` must be built and run through Docker, never on the host or WSL (WSL `/mnt/c/...` builds hit `Clock skew detected`; host-built binaries fail in containers with `GLIBCXX_*`/`GLIBC_*` "version not found"). `Dockerfile` (repo root) builds Ubuntu 22.04 with the C++17 toolchain, `libgraphviz-dev`, Python 3 + `requirements.txt`, and a pre-built `htsim_uec`.

```bash
docker build -t reps-artifact .
docker run -it --rm reps-artifact                              # image's own copy of the repo
docker run -it --rm -v "$(pwd):/workspace" reps-artifact        # live bind-mount
```

## Gotchas

**Bind-mount overlays host build artifacts.** Host-built `.o` / `htsim_uec` fail in the container with `GLIBCXX_*`/`GLIBC_*` errors. Always rebuild inside the container after mounting:
```bash
cd htsim/sim && make clean && cd datacenter && make clean && cd .. \
  && make -j$(nproc) && cd datacenter && make -j$(nproc)
```
`.o`/binaries are gitignored, so this never touches tracked files. See README.md §"Running in Docker".

**`.cm` / dockerignored files missing from the image.** `.dockerignore` excludes `**/*.cm` (generated connection matrices) plus `.o`/`.a`/binaries/`.csv`/`.png`/`.pdf`. `Failed to load connection matrix ...` means the file is not in the image. Fix: `docker cp <host-file> <container>:<path>` into the running container, or regenerate in-container via `traffic_gen/`. Same for locally generated, gitignored topology files.

**Stale `.o` after `docker cp` + incremental `make`.** Copying updated source into an already-running container across several edits without `make clean` can leave stale objects whose dependency tracking misses a change, giving a binary that segfaults reproducibly and identically across CC/LB algos, so it looks like a pre-existing bug. If a crash reproduces identically on untouched baseline code inside a container you have been iterating in, `make clean` in both `htsim/sim/` and `htsim/sim/datacenter/` and rebuild before trusting the crash. (Found verifying `dual-window-reps-mprdma`; see `experiments/MODIFICATIONS.md`.)

## docker-compose

`docker-compose.yml` wraps the bind-mount workflow (service `reps-artifact-dev`, image `reps-artifact`, `.` at `/workspace`):
```bash
docker compose build
docker compose run --rm reps-artifact-dev
```
Rebuild `htsim/sim` inside the container before running anything. `docker exec -it reps-artifact-dev bash` opens a second shell. Verified end to end (build, compose run, in-container rebuild, single-flow sim on `fat_tree_16_1os_3t_400g.topo`) on 2026-08-13.

## Plain build (inside the container)

```bash
cd htsim/sim && make -j 8
cd datacenter && make -j 8
cd ../../..
test -x htsim/sim/datacenter/htsim_uec || echo "BUILD FAILED"
```
Binary: `htsim/sim/datacenter/htsim_uec`. Build warnings are safe to ignore.
