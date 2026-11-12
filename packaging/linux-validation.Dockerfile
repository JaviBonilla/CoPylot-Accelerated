ARG BASE_IMAGE=ubuntu:22.04@sha256:8a2321a92b438238f93b4346fff61bc4259c99fdd4d9b52ee86f153fee0c344f
FROM ${BASE_IMAGE}

COPY requirements.txt /tmp/package-validation-requirements.txt
RUN set -eu; \
    if command -v dnf >/dev/null; then \
        dnf -y --setopt=install_weak_deps=False install \
            ca-certificates python3.12 python3.12-pip libstdc++ libgcc binutils git-core; \
        dnf clean all; \
        python=python3.12; \
    else \
        apt-get update -o APT::Update::Error-Mode=any; \
        DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
            ca-certificates python3 python3-venv libstdc++6 libgcc-s1 binutils git; \
        rm -rf /var/lib/apt/lists/*; \
        python=python3; \
    fi; \
    "$python" -m venv /opt/package-validation; \
    /opt/package-validation/bin/python -m pip install --no-cache-dir --only-binary=:all: \
        -r /tmp/package-validation-requirements.txt; \
    rm /tmp/package-validation-requirements.txt
