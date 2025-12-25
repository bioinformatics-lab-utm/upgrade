# DeepARG with GPU support (Python 2.7 + CUDA 11.0)
# Using CUDA 11.0 on Ubuntu 18.04 for Python 2.7 compatibility
FROM nvidia/cuda:11.0.3-cudnn8-runtime-ubuntu18.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Install system dependencies including Python 2.7
RUN apt-get update && apt-get install -y \
    python2.7 \
    python-pip \
    python-dev \
    git \
    wget \
    procps \
    libhdf5-dev \
    pkg-config \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip for Python 2.7
RUN python2.7 -m pip install --upgrade pip setuptools wheel

# Install BLAST+ (required for DeepARG)
RUN wget https://ftp.ncbi.nlm.nih.gov/blast/executables/blast+/2.14.0/ncbi-blast-2.14.0+-x64-linux.tar.gz && \
    tar -xzf ncbi-blast-2.14.0+-x64-linux.tar.gz && \
    cp ncbi-blast-2.14.0+/bin/* /usr/local/bin/ && \
    rm -rf ncbi-blast-2.14.0+*

# Install DeepARG from source (this will install all Python dependencies)
RUN git clone https://github.com/gaarangoa/deeparg.git /opt/deeparg && \
    cd /opt/deeparg && \
    python2.7 -m pip install --no-cache-dir -e .

# Add DeepARG to PATH
ENV PATH="/opt/deeparg:${PATH}"

# Configure Theano for GPU (will be overridden by containerOptions in nextflow)
ENV THEANO_FLAGS='floatX=float32,device=cuda,force_device=True,base_compiledir=/tmp/.theano'

# Set working directory
WORKDIR /data

CMD ["/bin/bash"]
