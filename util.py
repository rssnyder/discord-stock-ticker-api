import logging
from os import getenv
from sqlite3 import connect

import docker
from requests import get, post


COINGECKO_URL = 'https://api.coingecko.com/api/v3/'
YAHOO_URL = 'https://query1.finance.yahoo.com/v10/finance/'
HEADERS = {
    'User-Agent': 'Mozilla/5.0',
    'accept': 'application/json'
}


def log(message: str) -> None:
    '''
    Send message to telegram, or stdout
    '''

    data = {
        'chat_id': getenv('TELEGRAM_CHAT_ID'),
        'text': message,
        'parse_mode': 'HTML'
    }
    
    response = post(
        f"https://api.telegram.org/bot{getenv('TELEGRAM_BOT_TOKEN')}/sendMessage",
        json=data
    )

    logging.info(message)

    if response.status_code != 200:
        logging.error(f'Telegram Error: {response.text}')


def create_bot(type: str, ticker: str, name: str, token: str) -> docker.Container:
    '''
    Create a new bot instance
    Returns a container instance of the bot
    '''

    docker_name = ticker.replace('^', '_')

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
        },
        network='jack_default',
        links={
            'redis': 'redis'
        }
    )

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
