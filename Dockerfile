FROM ubuntu:22.04

ENV TZ=Asia/Kolkata

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3.11 \
        python3.11-venv \
        python3.11-dev \
        tzdata \
        mediainfo \
        ffmpeg \
        aria2 \
        zlib1g-dev \
        git && \
    ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

RUN ln -s /usr/bin/python3.11 /usr/bin/python && ln -s /usr/bin/pip3 /usr/bin/pip

COPY clone-repo.sh ./
ARG GITHUB_TOKEN
RUN GITHUB_TOKEN=$GITHUB_TOKEN sh clone-repo.sh && rm -f clone-repo.sh

WORKDIR /root/bot

RUN python -m pip install --no-cache-dir -U pip wheel && \
    python -m pip install --no-cache-dir -r requirements.txt

CMD ["bash", "start"]
