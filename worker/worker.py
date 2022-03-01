import pika, os
from dotenv import load_dotenv

load_dotenv()

url = str(os.environ.get('STACKHERO_RABBITMQ_AMQP_URL_TLS'))
print(url)

params = pika.URLParameters(url)
connection = pika.BlockingConnection(params)
channel = connection.channel()  # start a channel
channel.queue_declare(queue='hello')  # Declare a queue


def callback(ch, method, properties, body):
    print(" [x] Received " + str(body))


channel.basic_consume('hello',
                      callback,
                      auto_ack=True)

print(' [*] Waiting for messages:')
channel.start_consuming()
connection.close()
