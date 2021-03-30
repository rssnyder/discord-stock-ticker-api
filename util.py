import logging
from os import getenv
from sqlite3 import connect

import docker
from requests import get
from discord_webhook import DiscordWebhook, DiscordEmbed


COINGECKO_URL = 'https://api.coingecko.com/api/v3/'
YAHOO_URL = 'https://query1.finance.yahoo.com/v10/finance/'
HEADERS = {
    'User-Agent': 'Mozilla/5.0',
    'accept': 'application/json'
}


def log(message: str) -> None:
    '''
    Send message to discord
    '''

    logging.info(message)

    discord_msg = DiscordWebhook(
        url=getenv('DISCORD_ADMIN_WEBHOOK')
    )

    discord_msg.add_embed(
        DiscordEmbed(
            title='API Log',
            description=message,
            color='ffb300'
        )
    )

    return discord_msg.execute().status_code


def notify_admin_docker(symbol: str, symbol_safe: str, name: str, client_id: str,  token: str):
    '''
    Send message to the admins with compose information
    '''

    # Compose information
    message = f'  ticker-{symbol_safe}:\n'
    message += '    image: ghcr.io/rssnyder/discord-stock-ticker:1.5.1\n    restart: unless-stopped\n    links:\n      - redis\n'
    message += f'    container_name: ticker-{symbol_safe}\n'
    message += '    environment:\n'
    message += f'      - DISCORD_BOT_TOKEN={token}\n'
    message += f'      - TICKER={symbol}\n'
    message += f'      - STOCK_NAME={name}\n'
    message += '      - FREQUENCY=30\n      - TZ=America/Chicago\n      - REDIS_URL=redis\n\n\n'

    # Readme information
    message += f'[![{symbol}](https://logo.clearbit.com/xxxxxxx.com)]'
    message += f'(https://discord.com/api/oauth2/authorize?client_id={client_id}&permissions=0&scope=bot)\n'

    log(message)


def notify_discord(ticker: str, client_id: str) -> int:
    '''
    Post new bot to discord server
    '''

    discord_msg = DiscordWebhook(
        url=getenv('DISCORD_WEBHOOK')
    )

    discord_msg.add_embed(
        DiscordEmbed(
            title=ticker.upper(),
            description=f'https://discord.com/api/oauth2/authorize?client_id={client_id}&permissions=0&scope=bot',
            color='3333ff'
        )
    )

    return discord_msg.execute().status_code


def create_bot(type: str, ticker: str, name: str, client_id: str, token: str):
    '''
    Create a new bot instance
    Returns a container instance of the bot
    '''

    docker_name = ticker.replace('^', '_').replace('=', '_')

    client = docker.from_env()

    instance = client.containers.run(
        image=getenv('IMAGE_NAME'),
        name=f'ticker-{docker_name}',
        detach=True,
        environment={
            'DISCORD_BOT_TOKEN': token,
            'TICKER': ticker,
            f'{type}_NAME': name,
            'FREQUENCY': 30,
            'TZ': 'America/Chicago',
            'REDIS_URL': 'cache'
        }
    )

    notify_admin_docker(ticker, docker_name, name, client_id, token)

    return instance


def crypto_validate(id: str) -> tuple:
    '''
    Validate a crypto ticker
    Returns crypto id and name
    '''

    resp = get(
        COINGECKO_URL + f'coins/{id}',
        headers=HEADERS
    )

    try:
        resp.raise_for_status()
        data = resp.json()
    except:
        logging.error('Bad response from CG')
        return ()

    return (data['id'], data['symbol'])


def stock_validate(id: str) -> tuple:
    '''
    Validate a stock ticker
    Returns stock id and name
    '''

    resp = get(
        YAHOO_URL + f'quoteSummary/{id}?modules=price',
        headers=HEADERS
    )

    try:
        resp.raise_for_status()
        data = resp.json()
    except:
        logging.error('Bad response from yahoo')
        return None
    
    if data['quoteSummary']['error']:
        logging.error(f'not a valid ticker: {id}')
        return None

    symbol = data['quoteSummary']['result'][0]['price']['symbol'].lower()
    return (symbol, symbol)


def check_existing_bot(ticker: str) -> str:
    '''
    Check if a bot already exists for the given ticker
    Returns the client id of the existing bot
    '''

    db_client = connect(getenv('DB_PATH'))

    # Get an unused bot
    get_cur = db_client.cursor()
    get_cur.execute(
        'SELECT client_id FROM newbots WHERE ticker = ?',
        (ticker,)
    )

    try:
        existing_bot = get_cur.fetchone()
        db_client.close()
    except TypeError:
        logging.info(f'No bot exists for {ticker}')
        return None
    
    db_client.close()

    if not existing_bot:
        logging.info(f'We already have a bot for {ticker}')
        return None

    return existing_bot[0]


def get_new_bot(ticker: str) -> tuple:
    '''
    Get a new bot from the DB
    Returns the new bots id and token, or just id if bot already existed
    '''

    # If we already have a bot, return the client id
    client_id = check_existing_bot(ticker)
    if client_id:
        return (client_id, None)

    db_client = connect(getenv('DB_PATH'))

    # Get an unused bot
    get_cur = db_client.cursor()
    get_cur.execute(
        'SELECT client_id, token FROM newbots WHERE ticker IS NULL'
    )

    try:
        new_bot = get_cur.fetchone()
    except TypeError:
        log('Unable to get new bot from db')
        return ()
    
    # Before we use the new bot, claim it
    claim_cur = db_client.cursor()
    claim_cur.execute(
        'UPDATE newbots SET ticker = ? WHERE client_id = ?',
        (ticker.lower(), new_bot[0])
    )

    if claim_cur.rowcount == 0:
        log('Unable to claim new bot in db')
        return ()

    db_client.commit()

    return new_bot
