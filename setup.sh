#!/usr/bin/env bash
# merinaukri — one-time setup script
# Run this after cloning: bash setup.sh

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo ""
echo "========================================="
echo "  merinaukri — Job Application Assistant"
echo "========================================="
echo ""

# ── 1. Check Python ──────────────────────────────────────────────────────────
echo -n "Checking Python... "
if command -v python3 &>/dev/null; then
    PY_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
    echo -e "${GREEN}found Python ${PY_VERSION}${NC}"
else
    echo -e "${RED}Python 3 not found!${NC}"
    echo ""
    echo "Install Python 3.10+ from https://www.python.org/downloads/"
    echo "  macOS:   brew install python3"
    echo "  Ubuntu:  sudo apt install python3 python3-venv python3-pip"
    echo "  Windows: Download from python.org"
    exit 1
fi

# ── 2. Create virtual environment ────────────────────────────────────────────
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
    echo -e "${GREEN}Created .venv${NC}"
else
    echo -e "${GREEN}Virtual environment already exists${NC}"
fi

# Activate it
source .venv/bin/activate
echo -e "${GREEN}Activated .venv${NC}"

# ── 3. Install dependencies ──────────────────────────────────────────────────
echo ""
echo "Installing Python packages..."
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo -e "${GREEN}All packages installed${NC}"

# ── 4. Check for pango (needed for PDF export) ──────────────────────────────
echo ""
echo -n "Checking pango (for PDF export)... "
if command -v pango-view &>/dev/null || pkg-config --exists pangocairo 2>/dev/null; then
    echo -e "${GREEN}found${NC}"
else
    echo -e "${YELLOW}not found${NC}"
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "  PDF export needs pango. Install with: brew install pango"
    elif [[ "$OSTYPE" == "linux"* ]]; then
        echo "  PDF export needs pango. Install with: sudo apt install libpango-1.0-0 libpangocairo-1.0-0"
    fi
    echo "  (You can skip this — everything else works without it)"
fi

# ── 5. Copy config files if they don't exist ─────────────────────────────────
echo ""
echo "Setting up configuration files..."

copy_if_missing() {
    local src="$1"
    local dst="$2"
    local label="$3"
    if [ ! -f "$dst" ]; then
        cp "$src" "$dst"
        echo -e "  ${GREEN}Created${NC} $dst — ${YELLOW}edit this with your $label${NC}"
    else
        echo -e "  ${GREEN}Already exists:${NC} $dst"
    fi
}

copy_if_missing "config/profile.example.yaml" "config/profile.yaml" "resume/profile info"
copy_if_missing "config/settings.example.yaml" "config/settings.yaml" "API keys and preferences"
copy_if_missing "config/trusted_connections.example.yaml" "config/trusted_connections.yaml" "trusted LinkedIn contacts"

if [ ! -f ".env" ]; then
    cp .env.example .env
    echo -e "  ${GREEN}Created${NC} .env — ${YELLOW}add your GROQ_API_KEY${NC}"
else
    echo -e "  ${GREEN}Already exists:${NC} .env"
fi

# ── 6. Create data directories ───────────────────────────────────────────────
mkdir -p data/jobs data/resumes data/cover_letters
echo -e "  ${GREEN}Data directories ready${NC}"

# ── 7. Print next steps ──────────────────────────────────────────────────────
echo ""
echo "========================================="
echo -e "${GREEN}  Setup complete!${NC}"
echo "========================================="
echo ""
echo "Next steps — fill in these 3 files:"
echo ""
echo -e "  1. ${YELLOW}.env${NC}"
echo "     Add your Groq API key (free: https://console.groq.com)"
echo "     GROQ_API_KEY=gsk_your_key_here"
echo ""
echo -e "  2. ${YELLOW}config/profile.yaml${NC}"
echo "     Your resume info (name, experience, skills, education)"
echo "     Tip: Use ChatGPT/Claude to generate it from your LinkedIn!"
echo "     See README.md → 'Building Your Profile with AI'"
echo ""
echo -e "  3. ${YELLOW}config/settings.yaml${NC}"
echo "     Your job search preferences (location, job titles, sources)"
echo "     Telegram bot token is optional — only if you want the bot"
echo ""
echo "Then run:"
echo ""
echo -e "  ${GREEN}source .venv/bin/activate${NC}        # activate Python environment"
echo -e "  ${GREEN}python dashboard.py${NC}              # start the web dashboard"
echo ""
echo "Dashboard will be at: http://127.0.0.1:8080"
echo ""
echo -e "The Telegram bot is ${YELLOW}optional${NC}. The web dashboard works on its own."
echo "If you want the bot too, run in a separate terminal:"
echo -e "  ${GREEN}python main.py${NC}"
echo ""
