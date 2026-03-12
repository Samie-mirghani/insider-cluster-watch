#!/bin/bash
cd ~/insider-cluster-watch
git pull origin main >> logs/git_pull.log 2>&1
