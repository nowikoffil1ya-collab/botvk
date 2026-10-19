import os
import json
import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
from vk_api.utils import get_random_id

# --- НАСТРОЙКИ ---
TOKEN = os.getenv('VK_TOKEN') or "ТВОЙ_ТОКЕН_ЗДЕСЬ"

# ⚠️ ВАЖНО: Сюда впиши ID ВКонтакте преподавателей (или старосты), которые могут давать задания.
# Узнать свой ID можно здесь: vk.com/app5846215 (или просто открыть свою страницу, цифры в ссылке)
ADMIN_IDS = [123456789, 987654321] 

# Файл, куда бот будет сохранять задания
TASKS_FILE = "tasks.json"
user_states = {}

# --- ФУНКЦИИ ДЛЯ РАБОТЫ С ФАЙЛОМ ЗАДАНИЙ ---
def load_tasks():
    """Загружает задания из файла. Если файла нет, возвращает пустой список."""
    if os.path.exists(TASKS_FILE):
        with open(TASKS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_tasks(tasks):
    """Сохраняет задания в файл."""
    with open(TASKS_FILE, "w", encoding="utf-8") as f:
        json.dump(tasks, f, ensure_ascii=False, indent=4)

# --- КЛАВИАТУРА ---
def get_main_keyboard(user_id):
    """Генерирует клавиатуру. Если зашел админ — добавляет кнопку 'Добавить задание'."""
    keyboard = VkKeyboard(one_time=False)
    
    keyboard.add_button('Задания', color=VkKeyboardColor.POSITIVE)
    keyboard.add_button('Сдать работу', color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button('Помощь', color=VkKeyboardColor.SECONDARY)
    
    # Если пользователь — админ (преподаватель), добавляем красную кнопку
    if user_id in ADMIN_IDS:
        keyboard.add_button('Добавить задание', color=VkKeyboardColor.NEGATIVE)
        
    return keyboard.get_keyboard()

# --- ОТПРАВКА СООБЩЕНИЙ ---
def send_msg(vk, user_id, message, keyboard=None, attachment=None):
    vk.messages.send(
        user_id=user_id,
        message=message,
        random_id=get_random_id(),
        keyboard=keyboard,
        attachment=attachment
    )

# --- ОСНОВНАЯ ЛОГИКА ---
def main():
    vk_session = vk_api.VkApi(token=TOKEN)
    vk = vk_session.get_api()
    longpoll = VkLongPoll(vk_session)
    print("Бот успешно запущен и слушает сообщения...")

    for event in longpoll.listen():
        if event.type == VkEventType.MESSAGE_NEW and event.to_me:
            request = event.text.lower().strip()
            user_id = event.user_id
            
            # Обработка команды /start
            if request in ['/start', 'начать', 'привет']:
                user_states[user_id] = None
                send_msg(
                    vk, user_id, 
                    "Привет! Я бот-помощник для сдачи работ по направлению СМИ. Выбери действие на клавиатуре ниже 👇", 
                    keyboard=get_main_keyboard(user_id)
                )

            # Просмотр заданий (доступен всем)
            elif request == 'задания':
                user_states[user_id] = None
                tasks = load_tasks()
                
                if not tasks:
                    text = "📭 На данный момент активных заданий нет. Преподаватель скоро их добавит!"
                else:
                    text = "📋 **Актуальные задания по СМИ:**\n\n"
                    for i, task in enumerate(tasks, 1):
                        text += f"{i}️⃣ **{task['title']}**\n"
                        text += f"Описание: {task['desc']}\n"
                        text += f"⏳ Дедлайн: {task['deadline']}\n\n"
                
                send_msg(vk, user_id, text, keyboard=get_main_keyboard(user_id))

            # Помощь (доступна всем)
            elif request == 'помощь':
                user_states[user_id] = None
                help_text = (
                    "📞 **Контакты и правила:**\n\n"
                    "Преподаватель: Иванов И.И.\n"
                    "ВКонтакте: @id12345678\n"
                    "Кабинет: 302\n\n"
                    "📌 **Правила сдачи:**\n"
                    "1. Сдавать работы только через этого бота.\n"
                    "2. Тексты присылать сообщением, фото и видео — вложениями.\n"
                    "3. В сообщении обязательно указывайте название задания!"
                )
                send_msg(vk, user_id, help_text, keyboard=get_main_keyboard(user_id))

            # Сдать работу (доступно всем)
            elif request == 'сдать работу':
                user_states[user_id] = 'waiting_for_work'
                send_msg(
                    vk, user_id, 
                    "Отправьте текст выполненного задания сообщением или прикрепите файл (фото/видео/документ).", 
                    keyboard=get_main_keyboard(user_id)
                )

            # =========================================================
            # БЛОК ДЛЯ ПРЕПОДАВАТЕЛЕЙ (ДОБАВЛЕНИЕ ЗАДАНИЙ)
            # =========================================================
            elif request == 'добавить задание' and user_id in ADMIN_IDS:
                user_states[user_id] = 'waiting_for_new_task'
                send_msg(
                    vk, user_id, 
                    "Введите задание в формате:\n\n"
                    "**Название задания** | **Описание задания** | **Дедлайн**\n\n"
                    "Пример:\n"
                    "Написать заметку | Сделать репортаж с концерта (до 2000 знаков) | Пятница 18:00",
                    keyboard=get_main_keyboard(user_id)
                )

            # Обработка текста, если админ вводит новое задание
            elif user_states.get(user_id) == 'waiting_for_new_task' and user_id in ADMIN_IDS:
                try:
                    # Разделяем текст по символу |
                    parts = [p.strip() for p in event.text.split('|')]
                    if len(parts) == 3:
                        tasks = load_tasks()
                        tasks.append({
                            "title": parts[0],
                            "desc": parts[1],
                            "deadline": parts[2]
                        })
                        save_tasks(tasks)
                        
                        user_states[user_id] = None
                        send_msg(vk, user_id, "✅ Задание успешно добавлено и сохранено!", keyboard=get_main_keyboard(user_id))
                    else:
                        send_msg(vk, user_id, "❌ Ошибка формата. Убедитесь, что вы использовали два разделителя | (как в примере). Попробуйте еще раз.", keyboard=get_main_keyboard(user_id))
                except Exception as e:
                    send_msg(vk, user_id, f"❌ Ошибка при сохранении: {e}", keyboard=get_main_keyboard(user_id))

            # =========================================================
            # ОБРАБОТКА СДАЧИ РАБОТЫ СТУДЕНТАМИ
            # =========================================================
            elif user_states.get(user_id) == 'waiting_for_work':
                attachments = event.attachments
                
                if attachments:
                    print(f"--- НОВАЯ РАБОТА ---")
                    print(f"Студент ID {user_id} сдал работу (вложение): {attachments}")
                    print(f"--------------------")
                    send_msg(vk, user_id, "✅ Файл получен! Работа принята на проверку.", keyboard=get_main_keyboard(user_id))
                    user_states[user_id] = None
                    
                elif event.text:
                    print(f"--- НОВАЯ РАБОТА ---")
                    print(f"Студент ID {user_id} сдал работу (текст): {event.text}")
                    print(f"--------------------")
                    send_msg(vk, user_id, "✅ Текст получен! Работа принята на проверку.", keyboard=get_main_keyboard(user_id))
                    user_states[user_id] = None

            # Ответ на непонятные команды
            else:
                if user_states.get(user_id) == 'waiting_for_work':
                     send_msg(vk, user_id, "Пожалуйста, отправьте текст работы или прикрепите файл.")
                else:
                     send_msg(vk, user_id, "Я не понимаю эту команду. Используйте кнопки ниже 👇", keyboard=get_main_keyboard(user_id))

if __name__ == '__main__':
    main()
