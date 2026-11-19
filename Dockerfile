# Optional Linux environment for running and checking the software.
# Build: docker build -t mic-50-90 .
# Check: docker run --rm mic-50-90
# When mounting your own data, run with the uid/gid that owns the mounted directory.
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim@sha256:4f5d923c9dcea037f57bda425dd209f3ec643da2f0b74227f68d09dab0b3bb36

ENV PYTHONHASHSEED=0 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 UV_PYTHON_INSTALL_DIR=/opt/uv-python
WORKDIR /work
COPY . /work
RUN uv sync --frozen --all-extras && \
    (chmod -R a+rX /work/.venv /opt/uv-python 2>/dev/null || chmod -R a+rX /work/.venv)
ENV PATH="/work/.venv/bin:${PATH}" PYTHONPATH=/work HOME=/tmp MPLCONFIGDIR=/tmp/matplotlib
VOLUME ["/data"]
CMD ["bash", "verify.sh"]
