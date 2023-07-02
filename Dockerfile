FROM python:latest

# Set the timezone to Asia/Kolkata
ENV TZ=Asia/Kolkata
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Update the package list and install required packages
RUN apt-get -y update && \
    apt-get install -y --no-install-recommends mediainfo ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Clone the master branch from our repository
RUN git clone https://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@github.com/Yi-Zaha/Useless /root/bot

# Set the working directory to the cloned repository
WORKDIR /root/bot

# Upgrade pip and install required Python packages
RUN pip install -U pip wheel && \
    pip install -r requirements.txt

# Set the default command to start the application
CMD ["bash", "start"]
