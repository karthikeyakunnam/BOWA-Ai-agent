#!/bin/bash
# Cline + Groq Setup Script
# This script helps install and configure Cline with Groq Llama 3

set -e

echo "🚀 VS Code + Cline + Groq Setup"
echo "================================"
echo ""

# Step 1: Verify VS Code
if ! command -v code &> /dev/null; then
    echo "❌ VS Code not found. Please install VS Code."
    exit 1
fi

VS_CODE_VERSION=$(code --version | head -1)
echo "✓ VS Code found: $VS_CODE_VERSION"
echo ""

# Step 2: Verify clean environment
echo "🧹 Checking for conflicting extensions..."
EXTENSIONS_DIR="$HOME/.vscode/extensions"

if ls "$EXTENSIONS_DIR" | grep -qi "codeium\|chatgpt\|windsurf"; then
    echo "⚠️  Found conflicting extensions. Run Step 1 cleanup first."
    exit 1
fi

echo "✓ No conflicting extensions found"
echo ""

# Step 3: Create Cline config directory
echo "📁 Setting up Cline configuration..."
CONFIG_DIR="$HOME/.config/Cline"
mkdir -p "$CONFIG_DIR"
echo "✓ Config directory created: $CONFIG_DIR"
echo ""

# Step 4: Check for Groq API key
echo "🔑 Groq API Key Setup"
echo "--------------------"
echo "Get your free Groq API key from: https://console.groq.com/"
echo ""

if [ -z "$GROQ_API_KEY" ]; then
    read -p "Enter your Groq API key (leave blank to skip): " GROQ_API_KEY
fi

if [ ! -z "$GROQ_API_KEY" ]; then
    cat > "$CONFIG_DIR/cline_config.json" << EOF
{
  "apiProvider": "openai-compatible",
  "apiModelId": "llama3-8b-8192",
  "apiKey": "$GROQ_API_KEY",
  "customApiUrl": "https://api.groq.com/openai/v1",
  "theme": "dark"
}
EOF
    echo "✓ Configuration saved to: $CONFIG_DIR/cline_config.json"
else
    echo "⚠️  Skipped API key configuration"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Environment Ready!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📋 Next Steps:"
echo "1. Open VS Code"
echo "2. Press Cmd+Shift+X to open Extensions"
echo "3. Search for 'Cline' (official)"
echo "4. Click Install"
echo "5. Reload VS Code"
echo "6. Press Cmd+Shift+P → 'Cline: Open Chat'"
echo "7. Type 'hello' to test"
echo ""
echo "📚 Full guide: ./SETUP_CLINE_GROQ.md"
