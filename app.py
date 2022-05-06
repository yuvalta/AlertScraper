import logging
import os
import time

import requests
from dotenv import load_dotenv
from flask import request

from AssetMetaData import Asset
from MongodbConnection import MongodbConnection
from consts import SCRAPE_MODE_COLLECTIONS

load_dotenv()


# start loop
def start():
    logging.info("start looping")

    while True:
        try:
            # scrape floor price
            collection_col = MongodbConnection.get_instance()["CollectionsCol"]
            # cursor from mongodb
            full_collections_list = collection_col.find({})

            mapped_floor_list, bulk_contracts_list = create_mapped_assets_list(full_collections_list)
            logging.info("bulk_contracts_list")
            logging.info(bulk_contracts_list)

            response = get_bulk_floor_price_api(bulk_contracts_list)
            if response["response"] != 200:
                logging.info("error in api call")
                time.sleep(30)
                continue

            logging.info("scraping " + str(len(mapped_floor_list)) + " collections floor prices")

            # dict with contract id as Key and floor price as Value
            # this dict is helping me to compare price in more efficient way
            updated_price_chart = create_response_dict(response)

            compare_floor_price_with_chart(updated_price_chart, mapped_floor_list)

            logging.info("finished loop, sleeping...")
            time.sleep(90)

        except Exception as e:
            logging.info("Exception in loop " + str(e))
            time.sleep(90)

    return "Finished loop!"


def compare_floor_price_with_chart(updated_price_chart, mapped_floor_list):
    for asset_db in mapped_floor_list:
        try:
            logging.info(asset_db.to_json())
            asset_db.action = SCRAPE_MODE_COLLECTIONS
            if asset_db.price != updated_price_chart[str(asset_db.contract_id).lower()]:
                logging.info("in compare_floor_price_response - need to notify")
                asset_db.need_to_notify = True
                asset_db.price = updated_price_chart[asset_db.contract_id]
            else:
                logging.info("in compare_floor_price_response - no need to notify")
                asset_db.need_to_notify = False

        except Exception as e:
            logging.error("Except in scrape " + str(e) + " contract - " + asset_db.contract_id)
            asset_db.error_message = str(e)
        finally:
            if asset_db.need_to_notify:
                update_asset_in_asset_col_db(asset_db)


def create_response_dict(response):
    price_chart = {}
    for contract in response["data"]:
        contract_id = contract["asset_contract"]
        new_floor_price = contract["floor_price"][1]["floor_price"]

        price_chart[str(contract_id).lower()] = new_floor_price

    logging.info("create_response_dict")
    logging.info(price_chart)
    return price_chart


def get_bulk_floor_price_api(bulk_contracts_list):
    headers = {
        'x-api-key': str(os.environ.get('NFTBANK_API_KEY')),
    }

    json_data = {
        'chain_id': 'ETHEREUM',
        'asset_contracts':
            bulk_contracts_list,
    }

    response = requests.post('https://api.nftbank.ai/estimates-v2/floor_price/bulk', headers=headers, json=json_data)
    logging.info(response.json()["response"])

    return response.json()


def delete_all_from_assets_col():
    col = MongodbConnection.get_instance()["AssetsCol"]
    col.delete_many({})
    return {"delete_all": "deleted"}


def delete_user_from_asset():
    user_email = request.json["user_email"]
    asset_url = request.json["contract_id"]
    logging.info("delete_user_from_asset: " + user_email + " " + asset_url)

    error_message = ""

    col = MongodbConnection.get_instance()["AssetsCol"]

    asset_query = {"contract_id": asset_url}
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


# mapping db objects to AssetMetaData object and append to truncated list
def create_mapped_assets_list(full_assets_list):
    mapped_assets_list = []
    bulk_contracts_list = []
    try:
        for asset in full_assets_list:
            mapped_assets_list.append(
                Asset(asset["contract_id"], asset["users"], asset["price"], asset["error_message"],
                      asset["need_to_notify"], asset["action"]))
            bulk_contracts_list.append(asset["contract_id"])

    except Exception as e:
        logging.info("Exception in create_mapped_assets_list - " + str(e))
    return mapped_assets_list, bulk_contracts_list


# check if asset url in db. if so, add user to this asset. if not, add new asset to db
def add_user_to_asset(asset_url, user, mode):
    try:
        if mode == SCRAPE_MODE_COLLECTIONS:
            col = MongodbConnection.get_instance()["CollectionsCol"]
        else:
            col = MongodbConnection.get_instance()["AssetsCol"]

        logging.info("add_user_to_asset - " + mode)

        asset_query = {"contract_id": asset_url}
        retrieved_asset_from_db = col.find_one(asset_query)

        logging.info(retrieved_asset_from_db)

        if retrieved_asset_from_db is None:
            logging.info("adding new " + mode)
            new_asset_user_list = [user]
            add_new_asset(col, Asset(asset_url, new_asset_user_list, "new asset", "", False, ""))
            return {"response": "added new " + mode}
        else:
            logging.info("updating existing " + mode)
            new_user_list = set(retrieved_asset_from_db["users"])

            if len(new_user_list) > 20:
                error_msg = "Too many users on this url"
                logging.info(error_msg)
                return {"response": "", "error": error_msg}

            if user in new_user_list:
                return {"response": "", "error": "User already Exist in " + mode}

            new_user_list.add(user)

            new_values = {"$set": {"users": list(new_user_list)}}
            col.update_one(asset_query, new_values)
            return {"response": "updating existing " + mode}

    except Exception as e:
        logging.info(str(e))
        return str(e)


def add_new_asset(col, new_asset):
    logging.info("add_new_asset: " + new_asset.to_json())
    col.insert_one(new_asset.__dict__)


def update_asset_in_asset_col_db(asset_to_queue):
    try:
        logging.info("Updating asset: " + asset_to_queue.contract_id + " to price: "
                     + asset_to_queue.price + " Action: " + asset_to_queue.action)
    except:
        logging.info("update_asset_in_asset_col_db")

    asset_query = {"contract_id": asset_to_queue.contract_id}
    new_values = {"$set": {"price": asset_to_queue.price, "action": asset_to_queue.action,
                           "need_to_notify": asset_to_queue.need_to_notify}}

    if asset_to_queue.action == SCRAPE_MODE_COLLECTIONS:
        col = MongodbConnection.get_instance()["CollectionsCol"]
    else:
        col = MongodbConnection.get_instance()["AssetsCol"]

    col.update_one(asset_query, new_values)


start()