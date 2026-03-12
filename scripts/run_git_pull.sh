#!/bin/bash
cd ~/insider-cluster-watch
git stash --quiet
git pull origin main
git stash pop --quiet 2>/dev/null
