import boto3
from boto3.dynamodb.conditions import Attr
from boto3.dynamodb.conditions import Key
from werkzeug.security import generate_password_hash, check_password_hash
USER_STORAGE_URL = 'https://docapi.serverless.yandexcloud.net/ru-central1/b1gtsqicrr868m6jmjbu/etnh2vnqifbkgugfvcoo'
AWS_PUBLIC_KEY = 'YCAJEb70IUVPJLAFTDB7lKqVG'
AWS_SECRET_KEY = 'YCN0ZDeHYA-CN1HAMdxwD3bnZ5Gj2DN5ZB4NX2oM'


database = boto3.resource(
    'dynamodb',
    endpoint_url = USER_STORAGE_URL,
    region_name = 'ru-central1',
    aws_access_key_id =AWS_PUBLIC_KEY, 
    aws_secret_access_key =AWS_SECRET_KEY
)


users = database.Table('users')

'''response = users.put_item(
    Item = {
        'username': 'test_username',
        'data_type': 'profile',
        'password_hash': '1234',
        'is_admin': 'f',
        'first_name': 'test_name',
        'surname': 'test_surname',
        'patronymic': 'test_patronymic',
        'sex': 'male',
        'DateOfBirth': '2000-01-01',
        'email': 'test@mail.ru'
    },
    ConditionExpression='attribute_not_exists(user_id)'
)'''

'''scan = users.scan(
    FilterExpression= Attr('dr0ozd').contains('result_users_data_ekg')
)'''

'''response = users.get_item(Key={'username': 'dr0ozd', 'data_type': 'result_users_data_ekg'})

print(response)'''

# print(check_password_hash(response, '123456789'))

# удаление всех элементов

'''scan = users.scan()
with users.batch_writer() as batch:
    for each in scan['Items']:
        batch.delete_item(
            Key={
                'username': each['username'],
                'data_type': each['data_type'],
            }
        )'''

#print(scan['Items'])

#вывод всей базы

response = users.query(
    KeyConditionExpression=Key('username').eq('dr0ozd') & Key('data_type').eq('profile')
)

# Вывод результатов
items = response.get('Items')
for item in items:
    print(item)