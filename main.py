import urllib.request

import pika

from AssetMetaData import Asset
from time import time

from bs4 import BeautifulSoup

headers = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) '
                         'AppleWebKit/537.11 (KHTML, like Gecko) '
                         'Chrome/23.0.1271.64 Safari/537.11',
           'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
           'Accept-Charset': 'ISO-8859-1,utf-8;q=0.7,*;q=0.3',
           'Accept-Encoding': 'none',
           'Accept-Language': 'en-US,en;q=0.8',
           'Connection': 'keep-alive'}

PRICE_CLASS = "Overflowreact__OverflowContainer-sc-7qr9y8-0 jPSCbX Price--amount"


def scrape_asset_data(asset_from_queue):
    # start = time()

    req = urllib.request.Request(url=asset_from_queue.url, headers=headers)
    page = urllib.request.urlopen(req).read()

    soup = BeautifulSoup(page, features="html.parser")

    asset_from_queue.price = soup.find_all("div", class_=PRICE_CLASS)[0].contents[0]

    print(asset_from_queue.to_json())

    return asset_from_queue

    # print(f'It took {time() - start} seconds!')


def push_to_queue(asset):
    connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
    channel = connection.channel()

    channel.queue_declare(queue='assets_Q')

    channel.basic_publish(exchange='',
                          routing_key='assets_Q',
                          body=asset.to_json())
    print(" [x] Sent 'Hello World!'")


if __name__ == '__main__':
    asset_from_queue = Asset('https://opensea.io/assets/0x99ecdf17ded4fcb6c5f0fe280d21f832af464f67/150',
                             ["1", "2", "3"])

    print(asset_from_queue.to_json())

    asset_updated = scrape_asset_data(asset_from_queue)
    push_to_queue(asset_updated)
