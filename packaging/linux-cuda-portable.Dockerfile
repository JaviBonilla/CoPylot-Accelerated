# Build linux-portable.Dockerfile as copilot-linux-portable first.
FROM copilot-linux-portable
RUN dnf -y --setopt=install_weak_deps=False install curl-minimal xz && dnf clean all
COPY install_cuda_linux.sh /tmp/install_cuda_linux.sh
RUN /tmp/install_cuda_linux.sh /opt/copilot-cuda && rm /tmp/install_cuda_linux.sh
