from pymongo import MongoClient
import os


class MongodbConnection:
    __instance = None

    @staticmethod
    def get_instance():
        if MongodbConnection.__instance is None:
            MongodbConnection()
        return MongodbConnection.__instance

    def __init__(self):
        try:
            uri = str(os.environ.get('MONGODB_URI'))
            client = MongoClient(uri)
            db = client["AlertNFT"]
            MongodbConnection.__instance = db["AssetsCol"]
        except Exception as e:
            print("Error in connection to db: " + str(e))
