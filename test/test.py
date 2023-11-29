import json
import matplotlib.pyplot as plt

# Загрузка данных из JSON-файла
with open('/Users/dr0ozd/coding/ekg_analyzer/test/result_dr0ozd_2023-11-29-015414.json', 'r') as file:
    data = json.load(file)

# Получение данных для построения графика
x = data['ecg']['data'][0]['x']
y = data['ecg']['data'][0]['y']

# Создание графика
plt.figure(figsize=(10, 6))
plt.plot(x, y, label='ECG')
plt.xlabel('Время')
plt.ylabel('Значение')
plt.title('ЭКГ')
plt.legend()
plt.grid(True)

# Отображение графика
plt.show()
