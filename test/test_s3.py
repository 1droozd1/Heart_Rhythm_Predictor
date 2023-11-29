import boto3
import requests
from werkzeug.utils import secure_filename
import json

AWS_PUBLIC_KEY = 'YCAJEb70IUVPJLAFTDB7lKqVG'
AWS_SECRET_KEY = 'YCN0ZDeHYA-CN1HAMdxwD3bnZ5Gj2DN5ZB4NX2oM'

BUCKET_NAME = 'ekg-analyzer'

ENDPOINT = "https://storage.yandexcloud.net"

session = boto3.Session(
    aws_access_key_id=AWS_PUBLIC_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
    region_name="ru-central1",
)

s3 = session.client(
    "s3", endpoint_url=ENDPOINT)

for key in s3.list_objects(Bucket=BUCKET_NAME)['Contents']:
    print(key['Key'])

def waiting_answers(file_name):
    file_name_result = 'result_' + file_name
    while True:
        # Получить объект
        presigned_url = s3.generate_presigned_url(
            ClientMethod='get_object',
            Params={
                'Bucket': BUCKET_NAME,
                'Key': file_name_result
            },
            ExpiresIn=3600  # Срок действия ссылки в секундах (1 час)
        )
        response = requests.get(presigned_url)
        if response.status_code == 200:
            with open(file_name_result, 'wb') as file:
                # Записываем содержимое ответа в файл
                file.write(response.content)
                break

waiting_answers('dr0ozd_2023-11-29-103848.json')
'''
# Получить объект
presigned_url = s3.generate_presigned_url(
        ClientMethod='get_object',
        Params={
            'Bucket': BUCKET_NAME,
            'Key': 'resut_dr0ozd_2023-11-29-103848.json'
        },
        ExpiresIn=3600  # Срок действия ссылки в секундах (1 час)
    )
response = requests.get(presigned_url)
# Проверяем, что запрос был успешным (код ответа 200)
if response.status_code == 200:
    # Открываем файл для записи в бинарном режиме
    with open('result_dr0ozd_2023-11-29-103848.json', 'wb') as file:
        # Записываем содержимое ответа в файл
        file.write(response.content)

file_name = '/Users/dr0ozd/coding/ekg_analyzer/requirements.txt'  # Путь к файлу, который вы хотите загрузить
object_name = 'requirements.txt'     # Имя, под которым файл будет сохранен в бакете

s3.upload_file(file_name, BUCKET_NAME, object_name)
'''