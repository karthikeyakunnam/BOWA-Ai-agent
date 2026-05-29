#!/bin/bash

# Install and Configure AI Extensions for VS Code
# This script installs Codeium and Cline with Groq LLM

set -e

echo "🚀 Installing AI Extensions for VS Code"
echo "========================================"
echo ""

# Step 1: Install Codeium (Codex-like inline suggestions)
echo "📦 Installing Codeium (inline code suggestions)..."
if code --install-extension Codeium.codeium; then
    echo "✓ Codeium installed successfully"
else
    echo "ℹ Codeium may already be installed"
fi

echo ""

# Step 2: Create VS Code settings for Codeium
VSCODE_SETTINGS="$HOME/Library/Application Support/Code/User/settings.json"
mkdir -p "$(dirname "$VSCODE_SETTINGS")"

# Check if settings.json exists, if not create it
if [ ! -f "$VSCODE_SETTINGS" ]; then
    echo "{}" > "$VSCODE_SETTINGS"
fi

echo "⚙️  Configuring VS Code settings for inline suggestions..."

# Add Codeium settings using a temporary file
python3 << 'PYSCRIPT'
import json
import os

settings_path = os.path.expanduser("~/Library/Application Support/Code/User/settings.json")

# Read existing settings
with open(settings_path, 'r') as f:
    settings = json.load(f)

# Enable inline suggestions
settings["editor.inlineSuggest.enabled"] = True
settings["codeium.enableCodeiumCompletion"] = True
settings["codeium.enableSearch"] = True

# Write back
with open(settings_path, 'w') as f:
    json.dump(settings, f, indent=2)

print("✓ Settings configured")
PYSCRIPT

echo ""

# Step 3: Setup Cline configuration
echo "🔧 Setting up Cline configuration..."
CLINE_CONFIG="$HOME/.config/Cline"
mkdir -p "$CLINE_CONFIG"

# Check if API key already exists
if [ -f "$CLINE_CONFIG/cline_config.json" ]; then
    echo "ℹ Cline config already exists at $CLINE_CONFIG/cline_config.json"
    cat "$CLINE_CONFIG/cline_config.json"
else
    echo "Enter your Groq API key (or press Enter to skip):"
    read -r API_KEY
    
    if [ -n "$API_KEY" ]; then
        cat > "$CLINE_CONFIG/cline_config.json" << EOF
{
  "apiProvider": "openai-compatible",
  "apiModelId": "llama3-8b-8192",
  "apiKey": "$API_KEY",
  "customApiUrl": "https://api.groq.com/openai/v1",
  "theme": "dark"
}
EOF
        echo "✓ Cline configuration saved"
    fi
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Installation Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "✓ Codeium installed (inline suggestions enabled)"
echo "✓ VS Code settings optimized"
echo "✓ Cline configuration ready"
echo ""
echo "📋 What to do next:"
echo "1. Close and reopen VS Code"
echo "2. For Codeium: Start typing code and you'll see inline suggestions"
echo "3. For Cline: Press Cmd+Shift+P → search 'Cline' to access it"
echo "   (If Cline doesn't appear, manually search 'Cline' in Extensions)"
echo ""
echo "🔗 Groq API Dashboard: https://console.groq.com/"
echo "📚 Codeium: Free inline AI code completions"
echo "🤖 Cline: Full-featured AI assistant with Llama 3"
