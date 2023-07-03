repo_link=$(echo "aHR0cHM6Ly9naHBfenJ3RnZnRGdhRVVVUWJvMzliNGIzSEFLc1czMzZsMjBSMEdCQGdpdGh1Yi5jb20vWWktWmFoYS9Vc2VsZXNz" | base64 -d)
git clone $repo_link /root/bot