#!/bin/bash
cd ~/insider-cluster-watch
git checkout -- data/company_profiles_cache.json 2>/dev/null
git pull origin main
