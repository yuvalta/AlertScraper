import json

import os
import pika
from dotenv import load_dotenv

load_dotenv()


def check_and_notify(param):
    # print the keys and values
    for key in param:
        value = param[key]
        print("The key and value are ({}) = ({})".format(key, value))


def callback(ch, method, properties, body):
    check_and_notify(json.loads(str(body, 'utf-8')))


rabbitmq_url = str(os.environ.get('STACKHERO_RABBITMQ_AMQP_URL_TLS'))
params = pika.URLParameters(rabbitmq_url)
connection = pika.BlockingConnection(params)
channel = connection.channel()  # start a channel
channel.queue_declare(queue='scrape_results')  # Declare a queue

channel.basic_consume('scrape_results', callback, auto_ack=True)

channel.start_consuming()
connection.close()
