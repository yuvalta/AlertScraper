import pika, os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()


def callback(ch, method, properties, body):
    add_asset_to_mongodb(body)


rabbitmq_url = str(os.environ.get('STACKHERO_RABBITMQ_AMQP_URL_TLS'))
params = pika.URLParameters(rabbitmq_url)
connection = pika.BlockingConnection(params)
channel = connection.channel()  # start a channel
channel.queue_declare(queue='scrape_results')  # Declare a queue

channel.basic_consume('scrape_results',
                      callback,
                      auto_ack=True)

channel.start_consuming()
connection.close()


def add_asset_to_mongodb(asset):
    uri = str(os.environ.get('MONGODB_URI'))
    client = MongoClient(uri)
    db = client["AlertNFT"]
    col = db["AssetsCol"]

    col.insert_one(asset)
