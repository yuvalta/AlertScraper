import json
import os
import threading
import time
import urllib.request
import pika
import validators

from AssetMetaData import Asset
from MongodbConnection import MongodbConnection
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from flask import Flask, request

from consts import PRICE_CLASS, HEADERS, URL_PREFIX, BUTTON_TYPE_CLASS
from flask_cors import cross_origin, CORS

load_dotenv()

app = Flask(__name__)

# cors = CORS(app, resources={r"/*": {"origins": ["http://localhost:3000",
#                                                 "http://yuvalta.github.io/*",
#                                                 "https://yuvalta.github.io/*",
#                                                 "http://yuvalta.github.io",
#                                                 "https://yuvalta.github.io"]}})

CORS(app)

app.config['CORS_HEADERS'] = 'Content-Type'

loop_flag = True


# when user adding new asset from UI
def validate_input_url(string_to_validate):
    if len(str(string_to_validate)) == 0:
        return False
    if not validators.url(string_to_validate):
        return False

    return True


def validate_input_email(string_to_validate):
    if len(str(string_to_validate)) == 0:
        return False
    if not validators.email(string_to_validate):
        return False

    return True


@app.route('/upsert_asset/', methods=['POST'])
def upsert_asset():
    # TODO: validate args
    asset_url = request.json["url"]
    user_email = request.json["user_email"]

    if not validate_input_url(asset_url):
        return {"error": "error in input"}
    if not validate_input_email(user_email):
        return {"error": "error in input"}

    app.logger.info("upsert_asset() %s %s", asset_url, user_email)

    return add_user_to_asset(asset_url, user_email)


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
                sublist = []

                asset_from_db = Asset(asset["url"], asset["users"], asset["price"], asset["error_message"],
                                      asset["need_to_notify"], asset["action"])
                sublist.append(asset_from_db)

                if full_assets_list.alive:
                    next_asset = full_assets_list.next()
                else:
                    mapped_assets_list.append(sublist)
                    break

                asset_from_db = Asset(next_asset["url"], next_asset["users"], next_asset["price"],
                                      next_asset["error_message"],
                                      next_asset["need_to_notify"], next_asset["action"])
                sublist.append(asset_from_db)

                mapped_assets_list.append(sublist)

            # scrape assets price
            app.logger.info("scraping " + str(len(mapped_assets_list) * 2) + " assets prices")
            threads = [threading.Thread(target=scrape_asset_data, args=(mapped_asset,)) for mapped_asset in
                       mapped_assets_list]

            [t.start() for t in threads]
            [t.join() for t in threads]

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


@app.route('/get_assets_for_user/', methods=['POST'])
def get_assets_for_user():
    app.logger.info("get_assets_for_user")
    user_email = request.json["user_email"]
    app.logger.info(user_email)

    col = MongodbConnection.get_instance()
    asset_query = {"users": user_email}

    cursor = col.find(asset_query)
    assets_list = []
    for asset in cursor:
        assets_list.append({"url": asset["url"], "price": asset["price"], "action": asset["action"]})

    return json.dumps(assets_list)


@app.route('/test/')
def test():
    return {"uv": "stam"}


@app.route('/delete_all/')
def delete_all():
    col = MongodbConnection.get_instance()
    col.delete_many({})
    return {"delete_all": "deleted"}


@app.route('/delete_user_from_asset/', methods=['POST'])
def delete_user_from_asset():
    user_email = request.json["user_email"]
    asset_url = request.json["url"]
    app.logger.info("delete_user_from_asset: " + user_email + " " + asset_url)

    error_message = ""

    col = MongodbConnection.get_instance()

    asset_query = {"url": asset_url}
    retrieved_asset_from_db = col.find_one(asset_query)

    user_list = set(retrieved_asset_from_db["users"])

    if len(user_list) == 1 and user_email in user_list:
        # only this user in asset, delete asset
        try:
            col.delete_one(asset_query)
        except Exception as e:
            error_message = str(e)
        return {"response": "Asset deleted!", "error": error_message}

    if len(user_list) > 0:
        user_list.remove(user_email)

    new_values = {"$set": {"users": list(user_list)}}
    try:
        col.update_one(asset_query, new_values)
    except Exception as e:
        error_message = str(e)

    return {"response": "User deleted from asset!", "error": error_message}


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
            add_new_asset(col, Asset(asset_url, new_asset_user_list, "new asset", "", False, ""))
            return {"response": "added new user"}
        else:
            app.logger.info("updating existing asset")
            new_user_list = set(retrieved_asset_from_db["users"])

            if len(new_user_list) > 20:
                error_msg = "Too many users on this url"
                app.logger.info(error_msg)
                return {"response": "", "error": error_msg}

            if user in new_user_list:
                return {"response": "", "error": "User already Exist in asset"}

            new_user_list.add(user)

            new_values = {"$set": {"users": list(new_user_list)}}
            col.update_one(asset_query, new_values)
            return {"response": "updating existing asset"}

    except Exception as e:
        app.logger.info(str(e))
        return str(e)


def add_new_asset(col, new_asset):
    app.logger.info("add_new_asset: " + new_asset.to_json())
    col.insert_one(new_asset.__dict__)


def update_asset_in_db(asset_to_queue):
    app.logger.info("Updating asset: " + asset_to_queue.url + " to price: "
                    + asset_to_queue.price + " Action: " + asset_to_queue.action)

    asset_query = {"url": asset_to_queue.url}
    new_values = {"$set": {"price": asset_to_queue.price, "action": asset_to_queue.action}}

    col = MongodbConnection.get_instance()
    col.update_one(asset_query, new_values)


def scrape_asset_data(assets_to_queue):
    for asset_to_queue in assets_to_queue:
        is_new_asset = (asset_to_queue.price == "new asset")
        try:
            full_url = asset_to_queue.url
            content_price, content_button = get_page_content(full_url)

            # no price found
            if content_price is None:
                # same as last iteration
                if asset_to_queue.price == "No price!":
                    continue

                # price changed to No price, need to update + notify
                asset_to_queue.need_to_notify = True
                asset_to_queue.price = "No price!"
                asset_to_queue.action = content_button

            # price found
            else:
                new_price = content_price.contents[0]

                # same price
                if new_price == asset_to_queue.price:
                    continue

                # new price, need to update + notify
                asset_to_queue.need_to_notify = True
                asset_to_queue.action = content_button
                asset_to_queue.price = new_price

        except Exception as e:
            app.logger.error("Except in scrape asset " + str(e))
            asset_to_queue.error_message = str(e)

        finally:
            if asset_to_queue.need_to_notify:
                update_asset_in_db(asset_to_queue)
                if not is_new_asset:
                    push_to_queue(asset_to_queue)


def detect_action(action):
    if str(action) == "account_balance_wallet":
        return "Buy Now"
    if str(action) == "local_offer":
        return "Bid"

    return "No Action Detected"


def get_page_content(full_url):
    try:
        req = urllib.request.Request(url=full_url, headers=HEADERS)
        page = urllib.request.urlopen(req).read()

        soup = BeautifulSoup(page, features="html.parser")

        try:
            content_button = soup.find_all("div", class_=BUTTON_TYPE_CLASS)[0].contents[0].contents[0]
        except Exception as e:
            app.logger.error("Except in content_button" + str(e))
            return None

        try:
            content_price = soup.find_all("div", class_=PRICE_CLASS)[0]
        except IndexError:  # if no price found
            return None, detect_action(content_button)
        except Exception as e:
            app.logger.error("Except in content_button" + str(e))
            return None

        return content_price, detect_action(content_button)

    except Exception as e:  # general exception
        app.logger.error("Except in get_page_content" + str(e))
        return None


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
