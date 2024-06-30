#!/bin/bash 

REPO_URL="https://github.com/Yi-Zaha/Useless.git"
DESTINATION="/root/bot"

setup_git_credentials() {
    echo "https://Yi-Zaha:$(echo "$GITHUB_TOKEN" | base64 -d)@github.com" > ~/.git-credentials
    git config --global credential.helper store
}

clone_repo() {
    if git clone --quiet "$REPO_URL" "$DESTINATION"; then
        echo "Cloned to $DESTINATION."
    else
        if [ -z "$GITHUB_TOKEN" ]; then
            echo "Error: GITHUB_TOKEN not set."
            exit 1
        fi

        setup_git_credentials

        if git clone --quiet "$REPO_URL" "$DESTINATION"; then
            echo "Cloned private repo to $DESTINATION."
            unset GITHUB_TOKEN
        else
            echo "Error: Failed to clone repo."
            exit 1
        fi
    fi
}

update_repo() {
    cd "$DESTINATION" || exit

    if git pull --quiet; then
        echo "Updated repo."
    else
        echo "Error: Failed to pull changes."
        exit 1
    fi
}

main() {
    clone_repo
    update_repo
}

main
