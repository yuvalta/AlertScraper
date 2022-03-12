import os
import threading
import urllib.request
import pika
import json

from time import time
from bs4 import BeautifulSoup
from flask import Flask, request
from dotenv import load_dotenv

from AssetMetaData import Asset
from MongodbConnection import MongodbConnection

load_dotenv()

app = Flask(__name__)

headers = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) '
                         'AppleWebKit/537.11 (KHTML, like Gecko) '
                         'Chrome/23.0.1271.64 Safari/537.11',
           'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
           'Accept-Charset': 'ISO-8859-1,utf-8;q=0.7,*;q=0.3',
           'Accept-Encoding': 'none',
           'Accept-Language': 'en-US,en;q=0.8',
           'Connection': 'keep-alive'}

PRICE_CLASS = "Overflowreact__OverflowContainer-sc-7qr9y8-0 jPSCbX Price--amount"


@app.route('/asset/', methods=['POST'])
def asset():
    # TODO: validate args
    asset_url = request.form["url"]
    user_phone = request.form["user_phone"]

    app.logger.info("asset() %s %s", asset_url, user_phone)

    add_user_to_asset(asset_url, user_phone)

    return "Added!"


@app.route('/', methods=['POST'])
def get_price():
    asset_url = request.form["url"]
    asset_from_db = Asset(asset_url, ["1", "2", "3"])

    app.logger.info("get_price()")

    threading.Thread(target=scrape_asset_data, args=(asset_from_db,)).start()

    return "Started!"


# check if asset url in db. if so, add user to this asset. if not, add new asset to db
def add_user_to_asset(asset_url, user):
    try:
        col = MongodbConnection.get_instance()

        app.logger.info(col)

        asset_query = {"url": asset_url}
        retrieved_asset_from_db = col.find_one(asset_query)

        app.logger.info(retrieved_asset_from_db)

        if retrieved_asset_from_db is None:
            add_new_asset(col, Asset(asset_url, user, "", ""))
            app.logger.info("added new user")
        else:
            app.logger.info("updating existing asset")
            new_user_list = list(retrieved_asset_from_db["users"].split(","))
            new_user_list.append(user)

            new_values = {"$set": {"users": new_user_list}}
            col.update_one(asset_query, new_values)

    except Exception as e:
        app.logger.info("Exception in add_user_to_asset: " + str(e))


def add_new_asset(col, new_asset):
    app.logger.info("add_new_asset: " + new_asset.to_json())
    col.insert_one(new_asset.__dict__)


def scrape_asset_data(asset_from_queue):
    start = time()
    try:
        req = urllib.request.Request(url=asset_from_queue.url, headers=headers)
        page = urllib.request.urlopen(req).read()

        soup = BeautifulSoup(page, features="html.parser")

        asset_from_queue.price = soup.find_all("div", class_=PRICE_CLASS)[0].contents[0]
    except IndexError:
        asset_from_queue.price = "No price!"
    except Exception as e:
        asset_from_queue.error_message = str(e)

    app.logger.info("Current asset is " + asset_from_queue.to_json())
    push_to_queue(asset_from_queue)

    app.logger.info(f'It took {time() - start} seconds!')


def push_to_queue(asset):
    rabbitmq_url = str(os.environ.get('STACKHERO_RABBITMQ_AMQP_URL_TLS'))

    params = pika.URLParameters(rabbitmq_url)
    connection = pika.BlockingConnection(params)
    channel = connection.channel()  # start a channel
    channel.queue_declare(queue='scrape_results')  # Declare a queue
    channel.basic_publish(exchange='',
                          routing_key='scrape_results',
                          body=asset.to_json())

    app.logger.info("Sent: " + asset.to_json())
    connection.close()


port = os.environ.get("PORT", 5000)
app.run(debug=True, host="0.0.0.0", port=port)

# TODO: why do i need flask? why not just get assets from db and loop on them?
# TODO: and a web ui for entering and validating urls and users to db
# TODO: maybe split into 2 dbs and once in a while compare it
