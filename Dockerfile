FROM python:3.11

# Set the timezone to Asia/Kolkata
ENV TZ=Asia/Kolkata
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Clone the master branch from our repository
COPY clone-repo.sh ./
ARG GITHUB_TOKEN
RUN GITHUB_TOKEN=$GITHUB_TOKEN sh clone-repo.sh && rm -f clone-repo.sh /root/bot/clone-repo.sh

# Update the package list and install required packages
RUN apt-get -y update && \
    apt-get install -y --no-install-recommends mediainfo ffmpeg aria2 && \
    rm -rf /var/lib/apt/lists/*

# Set the working directory to the cloned repository
WORKDIR /root/bot

# Upgrade pip and install required Python packages
RUN pip install -U pip wheel && \
    pip install -r requirements.txt

# Set the default command to start the application
CMD ["bash", "start"]
