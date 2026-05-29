# VS Code + Cline + Groq Setup Guide

## ✅ Step 1: Clean Environment - COMPLETED
- ✓ Removed Codeium extensions (v1.48.2, v1.49.2)
- ✓ Removed OpenAI ChatGPT extensions (2 versions)
- ✓ Removed Claude Dev extension
- ✓ Created Cline config directory: `~/.config/Cline/`

---

## Step 2: Manual Cline Installation

Since VS Code CLI marketplace access is limited, install Cline manually:

### Option A: Via VS Code UI (Recommended)
1. Open VS Code
2. Press `Cmd+Shift+X` to open Extensions
3. Search for: `"Cline"`
4. Look for: **Cline** by official publisher (verified badge, ~3.8M downloads)
5. Click **Install**
6. Wait for installation to complete

### Option B: Direct Download & Install
```bash
# Navigate to extensions folder
cd ~/.vscode/extensions

# Download Cline VSIX (if available)
# Or clone from: https://github.com/cline/cline-vscode

# Unzip into extensions folder
unzip cline-latest.vsix -d cline.cline-X.X.X
```

---

## Step 3: Verify Installation

After installation:
1. Reload VS Code: `Cmd+Shift+P` → "Developer: Reload Window"
2. Press `Cmd+Shift+P`
3. Type: `"Cline: Open Chat"`
4. Cline chat panel should appear on right side

---

## Step 4: Configure Groq LLM

### 4a. Get Groq API Key
1. Go to: https://console.groq.com/
2. Sign up / Log in
3. Create API key
4. Copy the key

### 4b. Configure in Cline

**Method 1: Via Chat Command**
1. Open Cline chat
2. Type: `/config`
3. Select "LLM Settings"

**Method 2: Via Settings**
1. In Cline chat, look for settings icon (⚙️) in top-right
2. Click settings
3. Fill in:
   - **Provider**: OpenAI-compatible
   - **Base URL**: `https://api.groq.com/openai/v1`
   - **Model**: `llama3-8b-8192`
   - **API Key**: `[Your Groq API key]`

**Method 3: VS Code Settings (settings.json)**
```json
{
  "cline.apiProvider": "openai-compatible",
  "cline.apiModelId": "llama3-8b-8192",
  "cline.apiKey": "YOUR_GROQ_API_KEY",
  "cline.customApiUrl": "https://api.groq.com/openai/v1"
}
```

---

## Step 5: Test Connection

In Cline chat:
```
hello
```

**Expected Response:**
- Cline responds with a greeting
- No errors in console
- Proper formatting and text

**If it fails:**
- Check API key is correct
- Verify internet connection
- Check Groq API status: https://status.groq.com/
- Try refreshing the window

---

## Step 6: Available Groq Models

You can use any of these Llama models:
- `llama3-8b-8192` ← Recommended (fast, balanced)
- `llama3-70b-8192` (larger, slower, better quality)
- `mixtral-8x7b-32768` (mixture of experts)

Change model in Cline settings.

---

## Step 7: Optional - Windsurf for Autocomplete

If you want autocomplete (after Cline works):
1. `Cmd+Shift+X` → Search "Windsurf"
2. Install (optional, doesn't conflict with Cline)
3. Configure only for autocomplete, not chat
4. Do NOT login to Windsurf unless needed

---

## ⚙️ Configuration Files Created

**Location**: `~/.config/Cline/cline_config.json`

**Update with your API key:**
```json
{
  "apiProvider": "openai-compatible",
  "apiModelId": "llama3-8b-8192",
  "apiKey": "YOUR_ACTUAL_GROQ_API_KEY",
  "customApiUrl": "https://api.groq.com/openai/v1",
  "theme": "dark"
}
```

---

## ✅ Verification Checklist

- [ ] No conflicting AI extensions installed
- [ ] Cline extension installed and visible
- [ ] Cline chat opens with `/Cline: Open Chat` command
- [ ] Groq API key configured in Cline
- [ ] Test message ("hello") works
- [ ] No console errors
- [ ] Cline responds with Llama 3 model

---

## 🆘 Troubleshooting

**"Cline: Open Chat" not found**
- Reload window: `Cmd+Shift+P` → "Developer: Reload Window"
- Restart VS Code entirely
- Check extension is actually installed in extensions folder

**API connection fails**
- Verify API key: https://console.groq.com/keys
- Check Base URL (should be: `https://api.groq.com/openai/v1`)
- Verify model name: `llama3-8b-8192`
- Test Groq API: `curl https://api.groq.com/openai/v1/models -H "Authorization: Bearer YOUR_KEY"`

**Slow responses**
- Use `llama3-8b-8192` (fastest)
- Check internet connection
- Groq API might have high load (rare)

**Extension won't install**
- Delete `~/.vscode/extensions/.obsolete`
- Restart VS Code
- Try installing again

---

## Commands Reference

```bash
# Check VS Code extensions
ls ~/.vscode/extensions

# View Cline config
cat ~/.config/Cline/cline_config.json

# Reload VS Code from CLI
code --folder-uri /Users/karthikeyaunnam/bowa

# Clear VS Code cache if issues persist
rm -rf ~/Library/Application\ Support/Code/Cache/*
```

---

## Resources

- Cline GitHub: https://github.com/cline/cline
- Groq Console: https://console.groq.com/
- Groq API Docs: https://console.groq.com/docs
- VS Code Extensions: https://marketplace.visualstudio.com/VSCode
