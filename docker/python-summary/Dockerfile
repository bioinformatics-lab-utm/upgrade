FROM python:3.11

# Install required packages
RUN pip install --no-cache-dir pandas numpy scipy scikit-learn

# Create user with UID 1003 (nicolaedrabcinski)
RUN useradd -u 1003 -m -s /bin/bash analyzer

# Switch to analyzer user
USER analyzer
WORKDIR /home/analyzer

CMD ["python3"]
