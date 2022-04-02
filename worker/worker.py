import json

import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pika
import smtplib
from dotenv import load_dotenv

load_dotenv()


def send_changed_asset_to_email(user_email, data):
    try:
        # think how to send DM to user
        print("sent!")
    except Exception as e:
        print(str(e))


def check_and_notify(param):
    if param["need_to_notify"]:
        [send_changed_asset_to_email(user_email, param) for user_email in param["users"]]


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
