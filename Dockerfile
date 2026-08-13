# REPS EuroSys Artifact — containerized build/run environment
#
# Builds htsim_uec (and the other htsim datacenter binaries) plus the Python
# analysis environment used by artifact_scripts/ and state_aware_experiments/.
#
# Usage (from repo root):
#   docker build -t reps-artifact .
#   docker run -it --rm -v "$(pwd):/workspace" reps-artifact
#
# See CLAUDE.md / README.md "Running in Docker" section for details.

FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1

# Build toolchain (C++17 compiler + make), Python 3, and libgraphviz-dev
# (required by reps_pkg_install.sh / some analysis scripts).
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        g++ \
        make \
        git \
        libgraphviz-dev \
        python3 \
        python3-pip \
        python3-venv \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# Install Python dependencies first so this layer is cached independent of
# source changes. requirements.txt is copied ahead of the rest of the repo.
COPY requirements.txt /workspace/requirements.txt
RUN python3 -m pip install --no-cache-dir -r requirements.txt

# Copy the full repository into the image. When developing, mount the repo
# over this with `-v "$(pwd):/workspace"` so edits on the host are reflected
# without rebuilding the image.
COPY . /workspace

# Build htsim (core lib + all datacenter binaries, including htsim_uec).
RUN cd htsim/sim && \
    make clean && \
    cd datacenter && make clean && cd .. && \
    make -j"$(nproc)" && \
    cd datacenter && make -j"$(nproc)"

# Sanity check: fail the build if htsim_uec wasn't produced.
RUN test -x htsim/sim/datacenter/htsim_uec || (echo "BUILD FAILED: htsim_uec missing" && exit 1)

CMD ["/bin/bash"]
