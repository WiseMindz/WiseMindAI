# WiseMind AI Trading Bot

En AI-driven trading-assistent som integrerar med TradingView webhooks, Telegram och Claude AI.

## Funktioner
- 📊 **Webhook-receiver** för TradingView alerts
- 🤖 **Telegram-bot** med Claude AI-integration
- 💰 **Auto lot-size** beräkning
- 🧠 **Konversationsminne** per chat
- 📈 **Trade-sparning** i SQLite-databas

## Setup
1. Klona repo
2. `pip install -r requirements.txt`
3. Kopiera `.env.example` till `.env` och fyll i API-nycklar
4. `python bot.py`

## Deployment
- Railway: Deploy från GitHub
- Environment variables krävs för Railway
- Railway använder `PORT` för att exponera din webhook-server

## API Keys Required
- `CLAUDE_API_KEY` - Anthropic Claude
- `TELEGRAM_BOT_TOKEN` - Telegram Bot Father
- `TELEGRAM_CHAT_ID` - Din Telegram-grupp ID
- `WEBHOOK_SECRET` - Samma som i TradingView