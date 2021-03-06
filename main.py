import logging
from os import getenv

import docker
from fastapi import FastAPI, Response
from requests import post

from util import log, notify_discord, create_bot, crypto_validate, stock_validate, get_new_bot


app = FastAPI()


@app.get("/")
def read_root():
    return {"goto": "https://rssnyder.github.io/discord-stock-ticker"}


@app.get('/crypto/{id}')
def crypto(id: str, response: Response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Cache-Control"] = "Private"

    # Validate crypto id with cg
    crypto_details = crypto_validate(id.lower())

    if not crypto_details:
        log(f'unable to validate coin id: {id}')
        return {'error': f'unable to validate coin id: {id}'}

    # Query db for client_id and token
    bot_details = get_new_bot(crypto_details[0])

    # No new bots avalible
    if not bot_details:
        log('no more new bots avalible')
        return {'error': 'no more new bots avalible'}
    
    # Bot already existed
    if not bot_details[1]:
        log(f'existing bot requested: {id}')
        return {
            'client_id': bot_details[0],
            'existing': True
        }

    # Create new bot instance
    log(f'attempting to create new bot: {id}')
    container = create_bot(
        'CRYPTO',
        crypto_details[1],
        crypto_details[0],
        bot_details[0],
        bot_details[1]
    )

    if container:
        if getenv('DISCORD_WEBHOOK'):
            notify_discord(crypto_details[0], bot_details[0])

        return {'client_id': bot_details[0]}
    else:
        return {'error': 'having trouble starting new bot'}


@app.get('/stock/{id}')
def stock(id: str, response: Response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Cache-Control"] = "Private"

    # Validate stock id with yahoo
    stock_details = stock_validate(id.lower())

    if not stock_details:
        log(f'unable to validate stock id: {id}')
        return {'error': f'unable to validate stock id: {id}'}

    # Query db for client_id and token
    bot_details = get_new_bot(stock_details[0])

    # No new bots avalible
    if not bot_details:
        log('no more new bots avalible')
        return {'error': 'no more new bots avalible'}
    
    # Bot already existed
    if not bot_details[1]:
        log(f'existing bot requested: {id}')
        return {
            'client_id': bot_details[0],
            'existing': True
        }

    # Create new bot instance
    log(f'attempting to create new bot: {id}')
    container = create_bot(
        'STOCK',
        stock_details[1],
        stock_details[0],
        bot_details[0],
        bot_details[1]
    )

    if container:
        if getenv('DISCORD_WEBHOOK'):
            notify_discord(stock_details[0], bot_details[0])

        return {'client_id': bot_details[0]}
    else:
        return {'error': 'having trouble starting new bot'}
