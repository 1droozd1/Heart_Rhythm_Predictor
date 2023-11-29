import boto3, requests
import zipfile, shutil
import io
import os
from ml_part.model.pipline import BasePipeline, EcgPipelineDataset1D
import base64
import json
import torch
from openai import OpenAI
from dotenv import load_dotenv
import sys
sys.path.append('/Users/dr0ozd/coding/ekg_analyzer')
sys.path.append('/Users/dr0ozd/coding/ekg_analyzer/model')
from model import ECGnet
from config import *

load_dotenv()
client_open_ai = OpenAI(api_key=API_OPENAI_KEY)

model = ECGnet()
model.load_state_dict(torch.load('./model/model.pth', map_location='cpu'))

# Данные сервисного аккаунта
AWS_PUBLIC_KEY = 'YCAJEb70IUVPJLAFTDB7lKqVG'
AWS_SECRET_KEY = 'YCN0ZDeHYA-CN1HAMdxwD3bnZ5Gj2DN5ZB4NX2oM'

# Данные очередей
YMQ_QUEUE_URL = 'https://message-queue.api.cloud.yandex.net/b1gtsqicrr868m6jmjbu/dj60000000137fn104bi/heartbeat'

# Данные S3
ENDPOINT = "https://storage.yandexcloud.net"
BUCKET_NAME = 'ekg-analyzer'

# Данные DynamoDB
USER_STORAGE_URL = 'https://docapi.serverless.yandexcloud.net/ru-central1/b1gtsqicrr868m6jmjbu/etnh2vnqifbkgugfvcoo'

# Настройка сессии AWS для работы с Yandex S3
boto3_session = boto3.Session(
    aws_access_key_id=AWS_PUBLIC_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
    region_name="ru-central1",
)

# Клиент для работы с S3
s3 = boto3_session.client(
    "s3", endpoint_url=ENDPOINT)

# Клиент для работы с очередями сообщений YMQ
client = boto3.client(
    service_name='sqs',
    aws_access_key_id=AWS_PUBLIC_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
    endpoint_url='https://message-queue.api.cloud.yandex.net',
    region_name='ru-central1'
)

# Настройка ресурса DynamoDB для работы с базой данных
dynamodb = boto3.resource(
    'dynamodb',
    endpoint_url = USER_STORAGE_URL,
    region_name = 'ru-central1',
    aws_access_key_id =AWS_PUBLIC_KEY, 
    aws_secret_access_key =AWS_SECRET_KEY
)

USERS = dynamodb.Table('users') # Таблица пользователей в DynamoDB

# Получаем сообщения очереди
messages = client.receive_message(
    QueueUrl=YMQ_QUEUE_URL,
    MaxNumberOfMessages=10,
    VisibilityTimeout=60,
    WaitTimeSeconds=20
).get('Messages')

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
      return base64.b64encode(image_file.read()).decode('utf-8')
    
def request_chatgpt(image_path):
    base64_image = encode_image(image_path)
    
    completion = client_open_ai.chat.completions.create(
        model = "gpt-4-vision-preview",
        messages = [
            {
                "role": "system", 
                 "content": "Привет, я - MedAI, специализированный на анализе ЭКГ. \
             Пожалуйста, отправьте мне обработанный график ЭКГ с метками вашей AI-модели \
             (например, стрелки и буквы, где пустота означает 'Норма'). Моя задача - предоставить \
             анализ и рекомендации по этому графику [хотя бы примерный]. Я сосредоточусь на \
             выявлении потенциальных проблем и дискомфорта, связанных с этим графиком, \
             исключительно на основе представленных данных, без упоминания о необходимости \
             дополнительной информации. На графике по оси X каждые 8 миллисекунд соответствуют\
              одной временной единице. Все ответы будут предоставлены строго на русском языке."
            },
				{
               "role": "user", 
     			 "content": 
                 [
                    {
                        "type":"text",
                        "text":"Опиши фотографию."
						  },
                    {
							 	"type":"image_url",
                        "image_url": 
                           {
                            "url":f"data:image/jpeg;base64,{base64_image}",
                            "detail": "low"
									}
						  }
                  ]
				}
		  ]
	 )
    print(completion)
    return completion['choices'][0]['message']['content']


for msg in messages:
    profile_username = msg['Body'].split('_')[1]
    file_name_s3_without_format = msg['Body'].split('.')[0]
    
    # Ссылка для загрузки архива
    presigned_url = s3.generate_presigned_url(
            ClientMethod='get_object',
            Params={
                'Bucket': BUCKET_NAME,
                'Key': msg['Body']
            },
            ExpiresIn=3600  # Срок действия ссылки в секундах (1 час)
        )

    # Отправляем GET-запрос для загрузки zip-архива
    response = requests.get(presigned_url)

    # Выбор директории для загрузки файла (zip-архива)
    output_dir = 'extracted_files'

    if response.status_code == 200:
        # Создаем временный объект ZipFile в памяти
        zip_buffer = io.BytesIO(response.content)

        # Разархивируем zip-архив в указанную директорию
        with zipfile.ZipFile(zip_buffer, 'r') as zipf:
            zipf.extractall(output_dir)

    else:
        print(f"Не удалось загрузить архив. Код состояния: {response.status_code}")

    # Создаем директорию, если её нет
    os.makedirs(output_dir, exist_ok=True)

    path_list_files = os.listdir(output_dir)

    ''' 
    ML - part
    '''
    file_name = './' + output_dir + '/' + path_list_files[0].split('.')[0]
    data_loader = EcgPipelineDataset1D(file_name)
                              
    pipline = BasePipeline(model, data_loader, file_name, beats = 5)

    pipline.run_pipeline()

    figure_content = json.load(open(file_name+'.json', 'r'))
    text_content = "skjfdgkdfjgk"#request_chatgpt(file_name+'.jpeg')

    result_file = {"ecg": figure_content, "text":text_content}
    with open(file_name+'1.json', 'w') as file:
        json.dump(result_file, file)

    # Путь к файлу, который хотим загрузить
    file_name = file_name+'1.json' # Пример

    # Имя, под которым файл будет сохранен в бакете
    object_name = 'result_' + file_name_s3_without_format + '.json'

    s3.upload_file(file_name, BUCKET_NAME, object_name)

    # Получение ссылки на S3 (файл загруженный пользователем)
    s3_url = s3.generate_presigned_url(
        ClientMethod='get_object',
        Params={
            'Bucket': BUCKET_NAME,
            'Key': object_name
        },
        ExpiresIn=3600  # Срок действия ссылки в секундах (1 час)
    )

    # Добавляем результат работы в DynamoDB
    USERS.put_item(
        Item={
            'username': profile_username,
            'data_type': 'result_users_data_ekg',
            'file_name': object_name,
            'ekg_profile_url': s3_url
        }
    )
    # Удаление задачи из очереди
    client.delete_message(
        QueueUrl=YMQ_QUEUE_URL,
        ReceiptHandle=msg.get('ReceiptHandle')
    )
    # Удаляем временную директорию
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
