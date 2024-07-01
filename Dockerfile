# Use a smaller base image that is still suitable for Python applications
FROM python:3.11-slim

# Set the timezone to Asia/Kolkata
ENV TZ=Asia/Kolkata

# Update the package list, set the timezone, and install required packages in one RUN command
RUN apt-get update && \
apt-get install -y --no-install-recommends \
tzdata \
mediainfo \
ffmpeg \
aria2 \
git && \
ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone && \
apt-get clean && \
rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Copy the script to clone the repository and perform the repository cloning
COPY clone-repo.sh ./
ARG GITHUB_TOKEN
RUN GITHUB_TOKEN=$GITHUB_TOKEN sh clone-repo.sh && rm -f clone-repo.sh

# Set the working directory to the cloned repository
WORKDIR /root/bot

# Upgrade pip and install required Python packages
RUN pip install --no-cache-dir -U pip wheel && \
pip install --no-cache-dir -r requirements.txt

# Set the default command to start the application
CMD ["bash", "start"]