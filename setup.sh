#!/bin/bash
# Setup script for Trading Discord Bots on Ubuntu VPS
# Run as: bash setup.sh

set -e

echo "📦 Installing dependencies..."
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git

echo "📂 Cloning repository..."
cd /home/ubuntu
git clone https://github.com/YOUR_USERNAME/trading-discord-bots.git
cd trading-discord-bots

echo "🐍 Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

echo "📝 Creating .env file..."
cat > .env << 'EOF'
DISCORD_WEBHOOK_URL=your_news_webhook_here
DISCORD_WEBHOOK_SESSIONS=your_sessions_webhook_here
EOF

echo ""
echo "⚠️  IMPORTANT: Edit your .env file with real webhook URLs:"
echo "   nano /home/ubuntu/trading-discord-bots/.env"
echo ""

echo "🔧 Installing systemd service..."
sudo cp tradingbots.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable tradingbots

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Edit .env:  nano /home/ubuntu/trading-discord-bots/.env"
echo "  2. Start bots: sudo systemctl start tradingbots"
echo "  3. Check logs: sudo journalctl -u tradingbots -f"
echo ""
