#!/bin/bash

repo_url="https://github.com/Yi-Zaha/Useless.git"
destination="/root/bot"

# Function to set up git credentials
setup_git_credentials() {
    git config --global credential.helper store
    echo "https://Yi-Zaha:$(echo "$GITHUB_TOKEN" | base64 -d)@github.com" > ~/.git-credentials
}

# Try to clone the repository
if git clone --quiet "$repo_url" "$destination"; then
    echo "Useless repository cloned successfully to $destination."
else
    # Check if GITHUB_TOKEN is set
    if [ -z "$GITHUB_TOKEN" ]; then
        echo "Error: GITHUB_TOKEN not set. Please set the token correctly and try again."
        exit 1
    fi

    # Set up git credentials and try again
    setup_git_credentials
    if git clone --quiet "$repo_url" "$destination"; then
        echo "Private Useless repository cloned successfully to $destination."
        mv ~/.git-credentials "$destination"
        cd "$destination"

        # Set local credential helper for the repository
        git config credential.helper store

        # Unset GITHUB_TOKEN environment variable
        unset GITHUB_TOKEN

        # Ensure .git-credentials is ignored by git
        echo ".git-credentials" >> .gitignore
    else
        echo "Error: Unable to clone the Useless repository. Please check the repository URL and GitHub token."
        exit 1
    fi
fi


cd "$destination" || exit

if git pull --quiet; then
    echo "Successfully pulled latest changes."
else
    echo "Error: Unable to pull changes. Please check your git credentials."
    exit 1
fi