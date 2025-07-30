# VanilleCUP Discord Bot

### Overview
Bot to manage Teeworlds Vanille CUP tournaments with group and knockout phases.

### Launching servers
You can use the `scripts/process_monitor.sh` bash script to run servers with custom config.
Before running, create your own `.env` file (not committed) to set environment variables, e.g.:
```.env
DISCORD_BOT_TOKEN=MTM5Nzk1…
DISCORD_BOT_TEST_TOKEN=MTM…

# Server script env
PROCESS_NAME=DDNet-Server
BASE_DIR=/home/ubuntu/ddnet-insta-server
CFG_DIR=/home/ubuntu/vanillecup_servers
LOG_FILE=/home/ubuntu/vanillecup_servers/log/launch_servers.log
INSTANCE_COUNT=1
COMMAND_BASE=/home/ubuntu/ddnet-insta-server/DDNet-Server
```
Then execute:
```bash
git clone https://github.com/yourusername/Vanille-CUP.git
cd Vanille-CUP
./scripts/launch_servers.sh
```

### Setup Instructions
1. Clone the repo & install python bot
```bash
git clone https://github.com/yourusername/VanilleCUPBot.git
cd VanilleCUPBot
export DISCORD_BOT_TOKEN=your_actual_token
pip install -r requirements.txt
python3 bot_vanilleCUP2.py
```

2. Bot current commands:
#### Register a team, usage: !register teamname @captain @player2 @player3
!register
#### Reload teams from teams.json file, according this you can manually update it
!reloadteams
#### Start Group Phase, usage: !startgroups 1 (by default which means you will only have 1 round, so 1 game for each team)
!startgroups
#### Display or update standings even if it's automaticaly forces when you launch Group phases
!standings
#### Force knockout bracket if Group phase are not finished (for instance: a team gave up during tournament), usage: !startknockout 2/3 (by default which means you only get 2/3*total_team_number of teams qualified for bracket)
!startknockout

### Contribution
Feel free to open issues or pull requests!
