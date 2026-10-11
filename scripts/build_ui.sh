#!/bin/bash
set -e

echo "🚀 Building EXAMEN Next.js Frontend with Bun..."

# Navigate to the web_ui directory relative to this script
cd "$(dirname "$0")/../src/web_ui"

# Install dependencies if node_modules doesn't exist
if [ ! -d "node_modules" ]; then
    echo "📦 Installing dependencies with Bun..."
    bun install
fi

# Build the Next.js project
echo "🏗️  Running Next.js build..."
bun run build

echo "✅ Build complete! Static assets are ready in src/web_ui/out/"
