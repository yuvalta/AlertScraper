import os
import threading
import time
import urllib.request

import pika
from AssetMetaData import Asset
from MongodbConnection import MongodbConnection
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from flask import Flask, request

from consts import PRICE_CLASS, HEADERS, URL_PREFIX

load_dotenv()

app = Flask(__name__)

loop_flag = True


# when user adding new asset from UI
@app.route('/upsert_asset/', methods=['POST'])
def upsert_asset():
    # TODO: validate args
    asset_url = request.form["url"]
    user_phone = request.form["user_email"]

    app.logger.info("upsert_asset() %s %s", asset_url, user_phone)

    return add_user_to_asset(asset_url, user_phone)


#
# # happens every x seconds from db
# @app.route('/', methods=['POST'])
# def get_price_external():
#     asset_url = request.form["url"]
#
#     get_price_internal(Asset(asset_url, "", "", "", False))
#
#     return "Started!"


# start loop
@app.route('/start/', methods=['GET'])
def start():
    app.logger.info("start looping")
    global loop_flag

    try:
        while loop_flag:
            mapped_assets_list = []
            col = MongodbConnection.get_instance()
            full_assets_list = col.find({})
            for asset in full_assets_list:
                asset_from_db = Asset(asset["url"], asset["users"], asset["price"], asset["error_message"],
                                      asset["need_to_notify"])
                mapped_assets_list.append(asset_from_db)

            app.logger.info("scraping " + str(len(mapped_assets_list)) + " assets")
            threads = [threading.Thread(target=scrape_asset_data, args=(mapped_asset,)) for mapped_asset in
                       mapped_assets_list]

            [t.start() for t in threads]
            [t.join() for t in threads]

            app.logger.info("finished loop, sleeping...")
            time.sleep(30)

    except Exception as e:
        app.logger.info(str(e))

    return "Finished loop!"


# start loop
@app.route('/stop/', methods=['GET'])
def stop():
    app.logger.info("stop looping")

    global loop_flag
    loop_flag = False

    return "Stopped!"


@app.route('/get_assets_for_user/')
def get_assets_for_user():
    app.logger.info("get_assets_for_user")
    user_email = request.args.get("user_email")

    col = MongodbConnection.get_instance()

    asset_query = {"users": user_email}
    return col.find(asset_query)


# check if asset url in db. if so, add user to this asset. if not, add new asset to db
def add_user_to_asset(asset_url, user):
    try:
        col = MongodbConnection.get_instance()

        app.logger.info(col)

        asset_query = {"url": asset_url}
        retrieved_asset_from_db = col.find_one(asset_query)

        app.logger.info(retrieved_asset_from_db)

        if retrieved_asset_from_db is None:
            app.logger.info("added new user")
            new_asset_user_list = [user]
            add_new_asset(col, Asset(asset_url, new_asset_user_list, "", "", False))
            return "added new user"
        else:
            app.logger.info("updating existing asset")
            new_user_list = list(retrieved_asset_from_db["users"])

            if len(new_user_list) > 20:
                error_msg = "Too much users on this url"
                app.logger.info(error_msg)
                return error_msg

            new_user_list.append(user)

            new_values = {"$set": {"users": new_user_list}}
            col.update_one(asset_query, new_values)
            return "updating existing asset"

    except Exception as e:
        app.logger.info(str(e))
        return str(e)


def add_new_asset(col, new_asset):
    app.logger.info("add_new_asset: " + new_asset.to_json())
    col.insert_one(new_asset.__dict__)


def scrape_asset_data(asset_from_queue):
    try:
        full_url = URL_PREFIX + asset_from_queue.url
        req = urllib.request.Request(url=full_url, headers=HEADERS)
        page = urllib.request.urlopen(req).read()

        soup = BeautifulSoup(page, features="html.parser")

        new_price = soup.find_all("div", class_=PRICE_CLASS)[0].contents[0]

        # need to notify user
        if new_price != asset_from_queue.price:
            asset_from_queue.price = new_price
            asset_from_queue.need_to_notify = True

            # split to update function
            asset_query = {"url": asset_from_queue.url}
            new_values = {"$set": {"price": new_price}}

            col = MongodbConnection.get_instance()
            col.update_one(asset_query, new_values)

            push_to_queue(asset_from_queue)
        else:
            asset_from_queue.need_to_notify = False

    except IndexError:
        asset_from_queue.price = "No price!"
    except Exception as e:
        asset_from_queue.error_message = str(e)


def push_to_queue(asset):
    rabbitmq_url = str(os.environ.get('STACKHERO_RABBITMQ_AMQP_URL_TLS'))

    params = pika.URLParameters(rabbitmq_url)
    try:
        connection = pika.BlockingConnection(params)
    except Exception as e:
        app.logger.info("Error in BlockingConnection: " + str(e))
        return

    channel = connection.channel()  # start a channel
    channel.queue_declare(queue='scrape_results')  # Declare a queue
    channel.basic_publish(exchange='',
                          routing_key='scrape_results',
                          body=asset.to_json())

    app.logger.info("Sent: " + asset.to_json())
    connection.close()


port = os.environ.get("PORT", 5000)
app.run(debug=True, host="0.0.0.0", port=port)
