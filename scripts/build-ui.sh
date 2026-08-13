#!/bin/bash
# Build UI and copy to app-ui/static/ui/

set -e

echo "Building Svelte UI..."
cd ui
npm run build

echo "Copying build output to app-ui/static/ui/..."
cd ..
mkdir -p app-ui/static/ui
rm -rf app-ui/static/ui/*
cp -r ui/build/* app-ui/static/ui/

echo "Build complete! UI files are in app-ui/static/ui/"
