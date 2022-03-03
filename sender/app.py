import os
import threading
import urllib.request
from time import time

import pika
from bs4 import BeautifulSoup
from flask import Flask, request
from dotenv import load_dotenv

from AssetMetaData import Asset

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


@app.route('/', methods=['POST'])
def get_price():
    # https://opensea.io/assets/0x99ecdf17ded4fcb6c5f0fe280d21f832af464f67/150

    asset_url = request.form["url"]
    asset_from_queue = Asset("https://opensea.io/assets/" + asset_url,
                             ["1", "2", "3"])

    app.logger.info("Sent asset is: " + asset_from_queue.to_json())

    threading.Thread(target=scrape_asset_data, args=(asset_from_queue,)).start()

    return "Started!"


def scrape_asset_data(asset_from_queue):
    start = time()
    try:
        req = urllib.request.Request(url=asset_from_queue.rabbitmq_url, headers=headers)
        page = urllib.request.urlopen(req).read()

        soup = BeautifulSoup(page, features="html.parser")

        asset_from_queue.price = soup.find_all("div", class_=PRICE_CLASS)[0].contents[0]
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
