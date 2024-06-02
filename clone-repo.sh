#!/bin/bash

repo_url="https://github.com/Yi-Zaha/Useless.git"
destination="/root/bot"

if git clone --quiet "$repo_url" "$destination"; then
    echo "Useless repository cloned successfully to $destination."
else
    if [ -z "$GITHUB_TOKEN" ]; then
        echo "Error: GITHUB_TOKEN not set. Please set the token correctly and try again."
        exit 1
    fi

    git config --global credential.helper store
    echo "https://Yi-Zaha:$(echo "$GITHUB_TOKEN" | base64 -d)@github.com" > ~/.git-credentials

    if git clone --quiet "$repo_url" "$destination"; then
        echo "Private Useless repository cloned successfully to $destination."
        mv ~/.git-credentials "$destination"
        cd "$destination"
        git config credential.helper store
        unset GITHUB_TOKEN > /dev/null
    else
        echo "Error: Unable to clone the Useless repository. Please check the repository URL and GitHub token."
        exit 1
    fi
fi
