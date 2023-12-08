import io, json
import shutil
from flask import Flask, flash, render_template, request, session, redirect, url_for, jsonify
import requests
import base64
import torch
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
import boto3, sys, zipfile, os, tempfile

from boto3.dynamodb.conditions import Key

script_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(script_dir)
sys.path.append(project_dir)
sys.path.append(project_dir + '/ml_part/model')

import threading, time
from pipline import BasePipeline, EcgPipelineDataset1D
from openai import OpenAI
from dotenv import load_dotenv
from model import ECGnet

load_dotenv()

client_open_ai = OpenAI(
    api_key=os.getenv("API_PROXY_KEY"),
    base_url="https://api.proxyapi.ru/openai/v1"
    )

model = ECGnet()
model.load_state_dict(torch.load('./ml_part/model/model.pth', map_location='cpu'))

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
      return base64.b64encode(image_file.read()).decode('utf-8')

def request_chatgpt(image_path):
    base64_image = encode_image(image_path)
    
    completion = client_open_ai.chat.completions.create(
        model = "gpt-4-vision-preview",
        messages = [
				{
                "role": "user", 
     		    "content": 
                    [
                        {
                        "type":"text",
                        "text":"You are an cardiologist. Describe the image and provide commentart"
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
		  ], max_tokens=600, temperature=0.6
	)
	
    return completion.choices[0].message.content

def process_queue():
    while True:
        # Получаем сообщения из очереди
        messages = client.receive_message(
            QueueUrl=os.getenv("YMQ_QUEUE_URL"),
            MaxNumberOfMessages=10,
            VisibilityTimeout=60,
            WaitTimeSeconds=10
        ).get('Messages')

        if messages:
            for msg in messages:
                profile_username = msg['Body'].split('_')[0]
                file_name_s3_without_format = msg['Body'].split('.')[0]

                # Ссылка для загрузки архива
                presigned_url = s3.generate_presigned_url(
                        ClientMethod='get_object',
                        Params={
                            'Bucket': os.getenv("BUCKET_NAME"),
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

                figure_content = json.load(open(file_name + '.json', 'r'))
                text_content = request_chatgpt(file_name + '.jpeg')

                result_file = {"ecg": figure_content, "text": text_content}
                
                with open(file_name+'1.json', 'w') as file:
                    json.dump(result_file, file)

                # Путь к файлу, который хотим загрузить
                file_name = file_name+'1.json' # Пример

                # Имя, под которым файл будет сохранен в бакете
                object_name = 'result_' + file_name_s3_without_format + '.json'

                s3.upload_file(file_name, os.getenv("BUCKET_NAME"), object_name)

                # Получение ссылки на S3 (файл загруженный пользователем)
                s3_url = s3.generate_presigned_url(
                    ClientMethod='get_object',
                    Params={
                        'Bucket': os.getenv("BUCKET_NAME"),
                        'Key': object_name
                    },
                    ExpiresIn=3600  # Срок действия ссылки в секундах (1 час)
                )

                # Добавляем результат работы в DynamoDB
                USERS.put_item(
                    Item={
                        'username': profile_username,
                        'data_type': f'result_users_data_ekg_{file_name_s3_without_format}',
                        'file_name': object_name,
                        'ekg_profile_url': s3_url
                    }
                )
                # Удаление задачи из очереди
                client.delete_message(
                    QueueUrl=os.getenv("YMQ_QUEUE_URL"),
                    ReceiptHandle=msg.get('ReceiptHandle')
                )
                # Удаляем временную директорию
                if os.path.exists(output_dir):
                    shutil.rmtree(output_dir)
        else:
            time.sleep(5)

def waiting_answers(file_name):
    file_name_result = 'result_' + file_name + '.json'
    while True:
        # Получить объект
        presigned_url = s3.generate_presigned_url(
            ClientMethod='get_object',
            Params={
                'Bucket': os.getenv("BUCKET_NAME"),
                'Key': file_name_result
            },
            ExpiresIn=3600  # Срок действия ссылки в секундах (1 час)
        )
        response = requests.head(presigned_url)  # Используем HEAD-запрос для проверки доступности ссылки
        if response.status_code == 200:
            break
    return True

# Инициализация Flask приложения
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY") # Установка секретного ключа для сессии

# Настройка сессии AWS для работы с Yandex S3
boto3_session = boto3.Session(
    aws_access_key_id=os.getenv("AWS_PUBLIC_KEY"),
    aws_secret_access_key=os.getenv("AWS_SECRET_KEY"),
    region_name="ru-central1",
)

# Клиент для работы с S3
s3 = boto3_session.client(
    "s3", endpoint_url=os.getenv("ENDPOINT"))

# Клиент для работы с очередями сообщений YMQ
client = boto3.client(
    service_name='sqs',
    aws_access_key_id=os.getenv("AWS_PUBLIC_KEY"),
    aws_secret_access_key=os.getenv("AWS_SECRET_KEY"),
    endpoint_url='https://message-queue.api.cloud.yandex.net',
    region_name='ru-central1'
)

# Настройка ресурса DynamoDB для работы с базой данных
dynamodb = boto3.resource(
    'dynamodb',
    endpoint_url = os.getenv("USER_STORAGE_URL"),
    region_name = 'ru-central1',
    aws_access_key_id =os.getenv("AWS_PUBLIC_KEY"), 
    aws_secret_access_key =os.getenv("AWS_SECRET_KEY")
)

USERS = dynamodb.Table('users') # Таблица пользователей в DynamoDB

# Запускаем функцию process_queue в отдельном потоке
queue_thread = threading.Thread(target=process_queue)
queue_thread.daemon = True  # Поток будет работать как демон (завершится при завершении основного процесса)
queue_thread.start()

# Маршрут и обработчик для главной страницы
@app.route('/')
def index():
    return render_template('index.html') # Отображение главной страницы

# Маршрут и обработчик для страницы входа по логину
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # Получение данных пользователя из формы
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Запрос информации о пользователе из DynamoDB
        response = USERS.get_item(Key={'username': username, 'data_type': 'profile'})

        if 'Item' in response:
            user = response['Item']
            if check_password_hash(user['password_hash'], password):
                session['user'] = username  # Запоминаем пользователя в сессии
                flash('Вход успешно выполнен', 'success')
                return redirect(url_for('dashboard'))  # Переход на страницу личного аккаунта после входа

        flash('Неверный логин или пароль', 'danger')

    return render_template('index.html') # Отображение страницы входа

# Маршрут и обработчик для страницы регистрации
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Получение данных пользователя из формы
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Проверяем, что username уникален
        response = USERS.get_item(Key={'username': username, 'data_type': 'profile'})

        # Обработка случая существующего пользователя
        if 'Item' in response:
            flash('Пользователь с таким именем уже существует', 'danger')
        else:
            # Хэшируем пароль
            password_hash = generate_password_hash(password)

            # Создаем нового пользователя
            new_user = {
                'username': username,
                'data_type': 'profile',
                'password_hash': password_hash,
            }

            # Вставляем пользователя в таблицу 'users'
            USERS.put_item(Item=new_user)

            session['user'] = username  # Запоминаем пользователя в сессии

            flash('Регистрация успешно завершена', 'success')
            return redirect(url_for('login'))

    return render_template('register.html')

# Маршрут и обработчик для страницы личного кабинета
@app.route('/dashboard')
def dashboard():
    # Проверяем, вошел ли пользователь
    if 'user' not in session:
        flash('Вы должны войти, чтобы получить доступ к панели управления', 'danger')
        return redirect(url_for('login'))
    
    username = session['user']
    
    response = USERS.query(
        KeyConditionExpression=Key('username').eq(username) & Key('data_type').begins_with(f'result_users_data_ekg_{username}')
    )
    
    items = response.get('Items', [])
    
    ecg_data_list = []
    
    for item in items:
        presigned_url = item['ekg_profile_url']
        file_name_result = item['file_name']

        presigned_url = s3.generate_presigned_url(
            ClientMethod='get_object',
            Params={
                'Bucket': os.getenv("BUCKET_NAME"),
                'Key': file_name_result
            },
            ExpiresIn=3600  # Срок действия ссылки в секундах (1 час)
        )
        response = requests.get(presigned_url)
        
        if response.status_code == 200:
            with open(file_name_result, 'wb') as file:
                # Записываем содержимое ответа в файл
                file.write(response.content)
        
        with open(file_name_result, 'r') as file:
            ecg_data = json.load(file)
            ecg_data_list.append([ecg_data, file_name_result])
            os.remove(file_name_result)

    has_ecg_data=bool(ecg_data_list)
    has_selected_ecg_data = False
    selected_ecg_data = False

    if has_ecg_data:
        has_selected_ecg_data = True
        selected_ecg_data = ecg_data_list[-1][0]
    # Передаем данные в шаблон Flask
    return render_template('dashboard.html', ecg_data_list=ecg_data_list, has_ecg_data=has_ecg_data, selected_ecg_data=selected_ecg_data, has_selected_ecg_data=has_selected_ecg_data)

# Маршрут и обработчик для страницы просмотра выбранного ЭКГ файла
@app.route('/dashboard/<filename>')
def show_ecg(filename):
    presigned_url = s3.generate_presigned_url(
            ClientMethod='get_object',
            Params={
                'Bucket': os.getenv("BUCKET_NAME"),
                'Key': filename
            },
            ExpiresIn=3600  # Срок действия ссылки в секундах (1 час)
        )
    response = requests.get(presigned_url)

    # Ваш код загрузки данных и обработки
    if response.status_code == 200:
        has_selected_ecg_data = True
        with open(filename, 'wb') as file:
            # Записываем содержимое ответа в файл
            file.write(response.content)
    
    with open(filename, 'r') as file:
        selected_ecg_data = json.load(file)
        os.remove(filename)
    
    if has_selected_ecg_data:
        return jsonify(selected_ecg_data)
    else:
        return jsonify({})
    
# Функция для загрузки файла на Yandex S3
def upload_to_s3(file, username_session):
    '''
    Логика функции довольна просто:
        1) получаем расширение исходного файла
        2) создаем новый filename: 
            <логин пользователя>_<время загрузки файла>.<расширение исходного файла>
        3) добавляем файл в Yandex S3
    '''
    filename = secure_filename(username_session + '_' + f'{datetime.now().strftime("%Y-%m-%d-%H:%M:%S")}.zip')
    s3.upload_fileobj(file, os.getenv("BUCKET_NAME"), filename)
    return filename

# Функция для добавления информации о файле в DynamoDB
def add_file_info_to_dynamodb(username, file_name, s3_url):
    file_name_without_format = file_name.split('.')[0]
    USERS.put_item(
        Item={
            'username': username,
            'data_type': f'users_data_ekg_{file_name_without_format}',
            'file_name': file_name,
            'ekg_profile_url': s3_url
        }
    )

# Создает zip-архив из списка файлов
def create_zip_archive(files, output_filename):
    with zipfile.ZipFile(output_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file_path in files:
            # Получаем имя файла из пути
            file_name = os.path.basename(file_path)
            # Добавляем файлы в архив, указывая их имя в архиве
            zipf.write(file_path, arcname=file_name)

# Маршрут и обработчик для загрузки файла
@app.route('/upload', methods=['POST'])
def upload_file():
    if 'files[]' not in request.files:
        flash('Файлы не выбраны', 'danger')
        return redirect(request.url)

    files = request.files.getlist('files[]')

    if len(files) == 0:
        flash('Файлы не выбраны', 'danger')
        return redirect(request.url)
    
    # Создаем временную директорию для сохранения файлов
    temp_dir = tempfile.mkdtemp()
    
    # Сохраняем файлы во временной директории и получаем пути к ним
    file_paths = []
    for file in files:
        file_path = os.path.join(temp_dir, secure_filename(file.filename))
        file.save(file_path)
        file_paths.append(file_path)
    
    # Имя для zip архива
    output_zip_filename = str(session['user']) + '.zip'

    # Создаем zip-архив и помещаем файла в него
    create_zip_archive(file_paths, output_zip_filename)

    # Загрузка в S3 и получение обновленного имени файла
    file_name = upload_to_s3(open(output_zip_filename, 'rb'), session['user'])

    # Удаляем созданный архив после загрузки
    os.remove(output_zip_filename)

    # Получение ссылки на S3 (файл загруженный пользователем)
    s3_url = s3.generate_presigned_url(
        ClientMethod='get_object',
        Params={
            'Bucket': os.getenv("BUCKET_NAME"),
            'Key': file_name
        },
        ExpiresIn=3600  # Срок действия ссылки в секундах (1 час)
    )
    # Добавляем информацию о файле в DynamoDB
    add_file_info_to_dynamodb(session['user'], file_name, s3_url)
    flash('Файл успешно загружен на Yandex S3 и добавлен в DynamoDB', 'success')

    # Удаляем временную директорию и файлы после завершения
    for file_path in file_paths:
        os.remove(file_path)
    os.rmdir(temp_dir)

    # Отправка задачи в YMQ - очередь
    client.send_message(
        QueueUrl=os.getenv("YMQ_QUEUE_URL"),
        MessageBody=file_name,
    )
    flash('Задача успешно добавлена в очередь', 'success')

    if waiting_answers(file_name.split('.')[0]):
        return redirect(url_for('dashboard'))

# Маршрут для выхода
@app.route('/logout')
def logout():
    session.pop('user', None)  # Удаляем пользователя из сессии
    flash('Выход выполнен', 'success')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
