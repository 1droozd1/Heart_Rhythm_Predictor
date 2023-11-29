import json
import boto3

AWS_PUBLIC_KEY = 'YCAJEb70IUVPJLAFTDB7lKqVG'
AWS_SECRET_KEY = 'YCN0ZDeHYA-CN1HAMdxwD3bnZ5Gj2DN5ZB4NX2oM'
YMQ_QUEUE_URL = 'https://message-queue.api.cloud.yandex.net/b1gtsqicrr868m6jmjbu/dj60000000137fn104bi/heartbeat'

'''boto_session = boto3.Session(
    aws_access_key_id=AWS_PUBLIC_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
)

ymq_queue = boto_session.resource(
    service_name='sqs',
    endpoint_url='https://message-queue.api.cloud.yandex.net',
    region_name='ru-central1'
).Queue(YMQ_QUEUE_URL)'''

'''ymq_queue.send_message(
    MessageBody=json.dumps({'username':'test_username', 'file_name': 'test_file_name'})
)'''

client = boto3.client(
        service_name='sqs',
        aws_access_key_id=AWS_PUBLIC_KEY,
        aws_secret_access_key=AWS_SECRET_KEY,
        endpoint_url='https://message-queue.api.cloud.yandex.net',
        region_name='ru-central1'
    )
'''# Send message to queue
client.send_message(
    QueueUrl=YMQ_QUEUE_URL,
    MessageBody='попытка номер 2'
)
print('Successfully sent test message to queue')'''

# Receive sent message
messages = client.receive_message(
    QueueUrl=YMQ_QUEUE_URL,
    MaxNumberOfMessages=10,
    VisibilityTimeout=60,
    WaitTimeSeconds=20
).get('Messages')
for msg in messages:
    print('Received message: "{}"'.format(msg.get('Body')))

# Delete processed messages
for msg in messages:
    client.delete_message(
        QueueUrl=YMQ_QUEUE_URL,
        ReceiptHandle=msg.get('ReceiptHandle')
    )
    print('Successfully deleted message by receipt handle "{}"'.format(msg.get('ReceiptHandle')))