import logging
import os
import time

import requests
from dotenv import load_dotenv
from flask import request

from AssetMetaData import Asset
from MongodbConnection import MongodbConnection
from consts import SCRAPE_MODE_COLLECTIONS

MAX_HISTORY_PRICES = 20


# start loop
def start():
    print("start looping")

    while True:
        try:
            # scrape floor price
            collection_col = MongodbConnection.get_instance()["CollectionsCol"]
            # cursor from mongodb
            full_collections_list = collection_col.find({})

            mapped_floor_list, bulk_contracts_list = create_mapped_assets_list(full_collections_list)
            print("bulk_contracts_list")
            print(bulk_contracts_list)

            response = get_bulk_floor_price_api(bulk_contracts_list)
            if response["response"] != 200:
                print("error in api call")
                time.sleep(30)
                continue

            print("scraping " + str(len(mapped_floor_list)) + " collections floor prices")

            # dict with contract id as Key and floor price as Value
            # this dict is helping me to compare price in more efficient way
            updated_price_chart = create_response_dict(response)

            compare_floor_price_with_chart(updated_price_chart, mapped_floor_list)

            print("finished loop, sleeping...")
            time.sleep(90)

        except Exception as e:
            print("Exception in loop " + str(e))
            time.sleep(90)

    return "Finished loop!"


def compare_floor_price_with_chart(updated_price_chart, mapped_floor_list):
    for asset_db in mapped_floor_list:
        try:
            print(asset_db.to_json())
            asset_db.action = SCRAPE_MODE_COLLECTIONS
            if asset_db.price != updated_price_chart[str(asset_db.contract_id).lower()]:
                print("in compare_floor_price_response - need to notify")
                asset_db.need_to_notify = True
                asset_db.price = updated_price_chart[asset_db.contract_id]
                asset_db.price_history.append(asset_db.price)

                # keep only 10 last records of prices
                if len(asset_db.price_history) > MAX_HISTORY_PRICES:
                    asset_db.price_history.pop(0)
            else:
                print("in compare_floor_price_response - no need to notify")
                asset_db.need_to_notify = False

        except Exception as e:
            print("Except in scrape " + str(e) + " contract - " + asset_db.contract_id)
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

    print("create_response_dict")
    print(price_chart)
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
    print(response.json()["response"])

    return response.json()


def delete_all_from_assets_col():
    col = MongodbConnection.get_instance()["AssetsCol"]
    col.delete_many({})
    return {"delete_all": "deleted"}


def delete_user_from_asset():
    user_email = request.json["user_email"]
    asset_url = request.json["contract_id"]
    print("delete_user_from_asset: " + user_email + " " + asset_url)

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
                      asset["need_to_notify"], asset["action"], asset["name"], asset["price_history"]))
            bulk_contracts_list.append(asset["contract_id"])

    except Exception as e:
        print("Exception in create_mapped_assets_list - " + str(e))
    return mapped_assets_list, bulk_contracts_list


def update_asset_in_asset_col_db(asset_to_queue):
    try:
        print("Updating asset: " + asset_to_queue.contract_id + " to price: "
              + asset_to_queue.price + " Action: " + asset_to_queue.action)
    except:
        print("update_asset_in_asset_col_db")

    asset_query = {"contract_id": asset_to_queue.contract_id}
    new_values = {"$set": {"price": asset_to_queue.price,
                           "action": asset_to_queue.action,
                           "need_to_notify": asset_to_queue.need_to_notify,
                           "price_history": asset_to_queue.price_history}}

    if asset_to_queue.action == SCRAPE_MODE_COLLECTIONS:
        col = MongodbConnection.get_instance()["CollectionsCol"]
    else:
        col = MongodbConnection.get_instance()["AssetsCol"]

    col.update_one(asset_query, new_values)


print("Starting!")
load_dotenv()
start()
