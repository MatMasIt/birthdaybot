
# Birthday Reminder Bot
A simple telegram bot that reminds you of your friends' birthdays.


- Birthday list (current age, time to birthday, sorted)
- Monthly, weekly, daily reminders

> I made this bot for my personal use, but you can use it too. Just follow the instructions below.


## Installation

1. Clone the repository
```bash
git clone git@github.com:MatMasIt/birthdaybot.git
```

2. Create a virtual environment
```bash
python3 -m venv venv
```

3. Activate the virtual environment
```bash
source venv/bin/activate
```

4. Install the requirements
```bash
pip install -r requirements.txt
```

5. Create a `.env` file in the root directory and add the following variables
```bash
TOKEN=YOUR_TELEGRAM_BOT_TOKEN
```

6. Run the bot
```bash
python bot.py
```