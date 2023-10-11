FROM python:3.11.5

# Set the timezone to Asia/Kolkata
ENV TZ=Asia/Kolkata
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Update the package list and install required packages
RUN apt-get -y update && \
    apt-get install -y --no-install-recommends mediainfo ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Clone the master branch from our repository
COPY clone-repo.sh ./
RUN sh clone-repo.sh

# Set the working directory to the cloned repository
WORKDIR /root/bot

# Upgrade pip and install required Python packages
RUN pip install -U pip wheel && \
    pip install -r requirements.txt

# Set the default command to start the application
CMD ["bash", "start"]
