# Official AlmaLinux 9, linux/amd64. The EL9 repositories supply GCC 11.
FROM almalinux:9@sha256:465a5007813f19b5ac8a88cd161f3d8dcc6b1958e0c03c31f7c9a1b079d0a7da
RUN dnf -y --setopt=install_weak_deps=False install \
      gcc gcc-c++ git-core make binutils python3.12 python3.12-pip tar gzip \
    && dnf clean all \
    && python3.12 -m venv /opt/copilot-build \
    && /opt/copilot-build/bin/python -m pip install --no-cache-dir --only-binary=:all: \
      cmake==3.30.5 ninja==1.11.1.4
ENV PATH=/opt/copilot-build/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
WORKDIR /workspace
