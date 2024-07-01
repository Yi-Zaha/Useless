FROM python:3.11-slim

ENV TZ=Asia/Kolkata

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        mediainfo \
        ffmpeg \
        aria2 \
        zlib1g-dev \
        git && \
    ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

COPY clone-repo.sh ./
ARG GITHUB_TOKEN
RUN GITHUB_TOKEN=$GITHUB_TOKEN sh clone-repo.sh && rm -f clone-repo.sh

WORKDIR /root/bot

RUN pip install --no-cache-dir -U pip wheel && \
    pip install --no-cache-dir -r requirements.txt

CMD ["bash", "start"]
