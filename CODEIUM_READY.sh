#!/bin/bash

# Quick Setup - Cline Manual Installation Guide
# Since CLI marketplace has limited access, use this guide instead

clear

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "   AI Extensions Setup Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Show Codeium status
CODEIUM_PATH="$HOME/.vscode/extensions/codeium.codeium-1.48.2"
if [ -d "$CODEIUM_PATH" ]; then
    echo "✅ CODEIUM - READY (Inline suggestions)"
    echo "   Location: $CODEIUM_PATH"
    echo ""
fi

# Groq API Key
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📋 Your Groq API Configuration"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "API Key: <your_groq_api_key_here>"
echo "Provider: Groq (llama3-8b-8192)"
echo "URL: https://api.groq.com/openai/v1"
echo ""

# Instructions for Cline
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🤖 CLINE - Manual Installation"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Since CLI marketplace has limited access, install manually:"
echo ""
echo "1️⃣  Open VS Code"
echo "2️⃣  Press Cmd+Shift+X (Extensions)"
echo "3️⃣  Search for 'cline'"
echo "4️⃣  Install the extension (usually by 'saoudrizwan' or 'cline')"
echo "5️⃣  Reload VS Code"
echo "6️⃣  Press Cmd+Shift+P → 'Cline: Open Chat'"
echo ""
echo "Alternative: Direct marketplace URL"
echo "https://marketplace.visualstudio.com/"
echo ""

# Test instructions
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✨ Test Your Setup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "🧪 Test Codeium:"
echo "   1. Restart VS Code"
echo "   2. Open any .py or .js file"
echo "   3. Start typing code"
echo "   4. You should see inline suggestions"
echo ""
echo "🧪 Test Cline (after manual install):"
echo "   1. Press Cmd+Shift+P"
echo "   2. Type 'Cline: Open Chat'"
echo "   3. Type 'hello' and hit enter"
echo "   4. You should see a response from Llama 3"
echo ""

# Open link if possible
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📱 Quick Links"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "🔑 Groq API: https://console.groq.com/"
echo "🛒 VS Code Marketplace: https://marketplace.visualstudio.com/"
echo "📖 Full Guide: ./AI_EXTENSIONS_SETUP.md"
echo ""

# Check system
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔍 System Status"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# VS Code version
if command -v code &> /dev/null; then
    CODE_VERSION=$(code --version 2>/dev/null | head -1)
    echo "✓ VS Code: $CODE_VERSION"
fi

# Python version
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version 2>/dev/null)
    echo "✓ Python: $PYTHON_VERSION"
fi

# Node (if available)
if command -v node &> /dev/null; then
    NODE_VERSION=$(node --version)
    echo "✓ Node.js: $NODE_VERSION"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✨ You're all set! Restart VS Code now. 🚀"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
