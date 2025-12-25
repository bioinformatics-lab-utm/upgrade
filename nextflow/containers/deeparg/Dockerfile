FROM gaarangoa/deeparg:latest

# Switch to Debian archive repositories (Stretch is EOL)
RUN sed -i 's|http://deb.debian.org|http://archive.debian.org|g' /etc/apt/sources.list && \
    sed -i 's|http://security.debian.org|http://archive.debian.org|g' /etc/apt/sources.list && \
    sed -i '/stretch-updates/d' /etc/apt/sources.list

# Install procps and build-essential (g++ required by Theano)
RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends --allow-unauthenticated \
        procps \
        build-essential \
        g++ \
        gcc && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set Theano compile directory to /tmp (writable)
ENV THEANO_FLAGS='base_compiledir=/tmp/.theano'

# Keep the original entrypoint and workdir
WORKDIR /data
