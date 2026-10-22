import os
import time
import sqlite3
from pathlib import Path
import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
from vk_api.utils import get_random_id

# ==========================================
# НАСТРОЙКИ
# ==========================================
TOKEN = os.getenv('VK_TOKEN') or "ТВОЙ_ТОКЕН_ЗДЕСЬ"
RAW_ADMIN_IDS = [577603865, 410091203, "ekaterina_zaychenko_fh", "segatakai"] 

CUSTOM_TEACHER_NAMES = {
    "ekaterina_zaychenko_fh": "Смородина Е.Л.",
    "segatakai": "Назармамбетов М.Д."
}

# ⚠️ ВАЖНО: База данных будет храниться в папке /app/data (она не стирается)
DATA_DIR = Path("/app/data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "bot.db"

user_states = {}
last_action_time = {} 

# ==========================================
# РАБОТА С БАЗОЙ ДАННЫХ (SQLite)
# ==========================================
def init_db():
    """Создает таблицы, если их еще нет."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Таблица студентов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS students (
            user_id INTEGER PRIMARY KEY,
            name TEXT,
            points INTEGER DEFAULT 0
        )
    ''')
    
    # Таблица заданий
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            description TEXT,
            deadline TEXT,
            teacher_id INTEGER,
            teacher_name TEXT
        )
    ''')
    
    # Таблица сданных работ
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            student_info TEXT,
            task_title TEXT,
            message_id INTEGER,
            status TEXT DEFAULT 'pending'
        )
    ''')
    conn.commit()
    conn.close()

def get_student(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name, points FROM students WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"name": row[0], "points": row[1]}
    return None

def save_student(user_id, name):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO students (user_id, name) VALUES (?, ?)", (user_id, name))
    conn.commit()
    conn.close()

def update_points(user_id, points_to_add):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE students SET points = points + ? WHERE user_id = ?", (points_to_add, user_id))
    conn.commit()
    conn.close()

def get_all_tasks():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, description, deadline, teacher_name FROM tasks ORDER BY id")
    tasks = cursor.fetchall()
    conn.close()
    return tasks

def get_tasks_by_teacher(teacher_name):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, description, deadline FROM tasks WHERE teacher_name = ?", (teacher_name,))
    tasks = cursor.fetchall()
    conn.close()
    return tasks

def add_task(title, desc, deadline, teacher_id, teacher_name):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO tasks (title, description, deadline, teacher_id, teacher_name) VALUES (?, ?, ?, ?, ?)", 
                   (title, desc, deadline, teacher_id, teacher_name))
    conn.commit()
    conn.close()

def delete_task(task_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()

def add_submission(student_id, student_info, task_title, message_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO submissions (student_id, student_info, task_title, message_id) VALUES (?, ?, ?, ?)", 
                   (student_id, student_info, task_title, message_id))
    conn.commit()
    conn.close()

def get_pending_submission(exclude_id=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if exclude_id:
        cursor.execute("SELECT id, student_id, student_info, task_title, message_id FROM submissions WHERE status = 'pending' AND id != ? LIMIT 1", (exclude_id,))
    else:
        cursor.execute("SELECT id, student_id, student_info, task_title, message_id FROM submissions WHERE status = 'pending' LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    return row

def update_submission_status(sub_id, status):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE submissions SET status = ? WHERE id = ?", (status, sub_id))
    conn.commit()
    conn.close()

def get_leaderboard():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name, points FROM students ORDER BY points DESC LIMIT 10")
    rows = cursor.fetchall()
    conn.close()
    return rows

# ==========================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ И КЛАВИАТУРЫ
# ==========================================
def resolve_admins(vk, raw_list, custom_names):
    resolved_ids = []
    id_to_name = {}
    for admin in raw_list:
        if isinstance(admin, int):
            resolved_ids.append(admin)
            id_to_name[admin] = custom_names.get(str(admin))
        elif isinstance(admin, str):
            try:
                clean_admin = admin.replace('@', '')
                res = vk.users.get(user_ids=clean_admin)
                if res:
                    uid = res[0]['id']
                    resolved_ids.append(uid)
                    id_to_name[uid] = custom_names.get(clean_admin)
            except Exception: pass
    for uid in resolved_ids:
        if not id_to_name.get(uid):
            try:
                res = vk.users.get(user_ids=uid)[0]
                id_to_name[uid] = f"{res['last_name']} {res['first_name']}"
            except: id_to_name[uid] = "Преподаватель"
    return resolved_ids, id_to_name

def get_main_keyboard(user_id, admin_ids):
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button('Задания', color=VkKeyboardColor.POSITIVE)
    keyboard.add_button('Сдать работу', color=VkKeyboardColor.PRIMARY)
    keyboard.add_button('Топ лучших', color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button('Помощь', color=VkKeyboardColor.SECONDARY)
    if user_id in admin_ids:
        keyboard.add_button('Добавить задание', color=VkKeyboardColor.NEGATIVE)
        keyboard.add_button('Удалить задание', color=VkKeyboardColor.NEGATIVE)
        keyboard.add_line()
        keyboard.add_button('Проверить работы', color=VkKeyboardColor.SECONDARY)
    return keyboard.get_keyboard()

def get_review_keyboard():
    keyboard = VkKeyboard(one_time=True)
    keyboard.add_button('✅ Оценить', color=VkKeyboardColor.POSITIVE)
    keyboard.add_button('❌ Отклонить', color=VkKeyboardColor.NEGATIVE)
    keyboard.add_line()
    keyboard.add_button('✍️ Только комментарий', color=VkKeyboardColor.PRIMARY)
    keyboard.add_button('⏭ Пропустить', color=VkKeyboardColor.SECONDARY)
    return keyboard.get_keyboard()

def get_cancel_keyboard():
    keyboard = VkKeyboard(one_time=True)
    keyboard.add_button('⬅️ Назад в меню', color=VkKeyboardColor.SECONDARY)
    return keyboard.get_keyboard()

def send_msg(vk, user_id, message, keyboard=None, forward_messages=None):
    try:
        vk.messages.send(user_id=user_id, message=message, random_id=get_random_id(), keyboard=keyboard, forward_messages=forward_messages)
    except Exception as e:
        print(f"Ошибка отправки {user_id}: {e}")

def show_leaderboard(vk, user_id, admin_ids):
    rows = get_leaderboard()
    if not rows:
        send_msg(vk, user_id, "Пока нет ни одного студента в базе.", keyboard=get_main_keyboard(user_id, admin_ids))
        return
    text = "🏆 ТОП ЛУЧШИХ СТУДЕНТОВ:\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for i, (name, points) in enumerate(rows):
        medal = medals[i] if i < 3 else "🔹"
        text += f"{medal} {name} — {points} баллов\n"
    send_msg(vk, user_id, text, keyboard=get_main_keyboard(user_id, admin_ids))

def show_next_submission(vk, admin_id, admin_ids, current_task_id=None):
    row = get_pending_submission(exclude_id=current_task_id)
    if row:
        sub_id, student_id, student_info, task_title, message_id = row
        user_states[admin_id] = {'state': 'reviewing', 'task_id': sub_id}
        msg = f"📥 Работа №{sub_id}\n\n👤 Студент: {student_info}\n📝 Задание: {task_title}\n\nОцените работу с помощью кнопок ниже 👇"
        send_msg(vk, admin_id, msg, keyboard=get_review_keyboard(), forward_messages=message_id)
    else:
        send_msg(vk, admin_id, "🎉 Все работы проверены! Новых заданий на проверку нет.", keyboard=get_main_keyboard(admin_id, admin_ids))
        user_states[admin_id] = None

# ==========================================
# ОСНОВНАЯ ЛОГИКА
# ==========================================
def main():
    init_db() # Инициализируем базу при запуске
    
    vk_session = vk_api.VkApi(token=TOKEN)
    vk = vk_session.get_api()
    longpoll = VkLongPoll(vk_session)
    
    ADMIN_IDS, ADMIN_NAMES = resolve_admins(vk, RAW_ADMIN_IDS, CUSTOM_TEACHER_NAMES)
    print(f"Бот запущен! Преподаватели: {ADMIN_NAMES}")
    print(f"База данных: {DB_PATH}")

    for event in longpoll.listen():
        if event.type == VkEventType.MESSAGE_NEW and event.to_me:
            request = event.text.lower().strip()
            user_id = event.user_id
            
            current_time = time.time()
            if user_id in last_action_time and current_time - last_action_time[user_id] < 1.0:
                continue
            last_action_time[user_id] = current_time
            
            state = user_states.get(user_id, {})
            
            # --- МЕНЮ ---
            if request in ['/start', 'начать', 'привет', '⬅️ назад в меню']:
                user_states[user_id] = None
                send_msg(vk, user_id, "Привет! Я бот для сдачи работ по СМИ. Выбери действие 👇", keyboard=get_main_keyboard(user_id, ADMIN_IDS))

            elif request == 'топ лучших':
                user_states[user_id] = None
                show_leaderboard(vk, user_id, ADMIN_IDS)

            elif request == 'помощь':
                user_states[user_id] = None
                help_text = "📞 Контакты преподавателей:\n• Смородина Е.Л.: https://vk.com/ekaterina_zaychenko_fh\n• Назармамбетов М.Д.: https://vk.com/segatakai\n\n📌 Правила:\n1. Сдавать работы только через бота.\n2. За каждую работу преподаватель ставит от 1 до 10 баллов."
                send_msg(vk, user_id, help_text, keyboard=get_main_keyboard(user_id, ADMIN_IDS))

            elif request == 'сдать работу':
                user_states[user_id] = None 
                student = get_student(user_id)
                if not student:
                    user_states[user_id] = {'state': 'waiting_for_name_group', 'task_title': 'Не указано'}
                    send_msg(vk, user_id, "Перед сдачей работы нужно представиться.\n\nНапишите ваше ФИО и Группу одним сообщением.\nПример:\nИванов Иван Иванович, группа ИС-21", keyboard=get_cancel_keyboard())
                else:
                    user_states[user_id] = {'state': 'waiting_for_work', 'task_title': 'Не указано (отправлено напрямую)'}
                    send_msg(vk, user_id, f"Вы: {student['name']} (Баллов: {student['points']})\n\nОтправьте текст работы или прикрепите файл.", keyboard=get_cancel_keyboard())

            # --- ЗАДАНИЯ ---
            elif request == 'задания':
                tasks = get_all_tasks()
                if not tasks:
                    user_states[user_id] = None
                    send_msg(vk, user_id, "📭 На данный момент активных заданий нет.", keyboard=get_main_keyboard(user_id, ADMIN_IDS))
                    continue
                
                teachers = set(t[4] for t in tasks if t[4])
                keyboard = VkKeyboard(one_time=True)
                for i, t_name in enumerate(teachers):
                    if i > 0 and i % 2 == 0: keyboard.add_line()
                    short_name = t_name[:30] + "..." if len(t_name) > 30 else t_name
                    keyboard.add_button(short_name, color=VkKeyboardColor.PRIMARY)
                keyboard.add_line()
                keyboard.add_button('⬅️ Назад в меню', color=VkKeyboardColor.SECONDARY)
                user_states[user_id] = {'state': 'choosing_teacher'}
                send_msg(vk, user_id, "Выберите преподавателя:", keyboard=keyboard.get_keyboard())

            elif state.get('state') == 'choosing_teacher':
                selected_teacher_name = event.text.strip()
                teacher_tasks = get_tasks_by_teacher(selected_teacher_name)
                
                if not teacher_tasks:
                    send_msg(vk, user_id, "Задания не найдены. Попробуйте выбрать другого преподавателя.", keyboard=get_main_keyboard(user_id, ADMIN_IDS))
                    user_states[user_id] = None
                    continue

                keyboard = VkKeyboard(one_time=True)
                for i, t in enumerate(teacher_tasks):
                    if i >= 8: break 
                    if i > 0 and i % 2 == 0: keyboard.add_line()
                    title = t[1][:35] + "..." if len(t[1]) > 35 else t[1]
                    keyboard.add_button(title, color=VkKeyboardColor.POSITIVE)
                keyboard.add_line()
                keyboard.add_button('⬅️ Назад в меню', color=VkKeyboardColor.SECONDARY)
                user_states[user_id] = {'state': 'choosing_task', 'teacher': selected_teacher_name}
                send_msg(vk, user_id, "Выберите задание из списка:", keyboard=keyboard.get_keyboard())

            elif state.get('state') == 'choosing_task':
                selected_task_btn = event.text.strip()
                # Ищем задание по первым 35 символам
                tasks = get_all_tasks()
                task = next((t for t in tasks if t[1][:35] in selected_task_btn or selected_task_btn in t[1]), None)
                
                if task:
                    task_id, title, desc, deadline, teacher_name = task
                    text = f"📝 Задание: {title}\n\nОписание: {desc}\n⏳ Дедлайн: {deadline}"
                    student = get_student(user_id)
                    if not student:
                        user_states[user_id] = {'state': 'waiting_for_name_group', 'task_title': title}
                        send_msg(vk, user_id, f"{text}\n\nПеред сдачей нужно представиться.\nНапишите ваше ФИО и Группу одним сообщением.", keyboard=get_cancel_keyboard())
                    else:
                        user_states[user_id] = {'state': 'waiting_for_work', 'task_title': title}
                        send_msg(vk, user_id, f"{text}\n\nОтправьте текст работы или прикрепите файл.", keyboard=get_cancel_keyboard())
                else:
                    send_msg(vk, user_id, "Задание не найдено. Выберите снова.", keyboard=get_main_keyboard(user_id, ADMIN_IDS))
                    user_states[user_id] = None

            elif state.get('state') == 'waiting_for_name_group':
                save_student(user_id, event.text)
                task_title = state.get('task_title', 'Задание')
                user_states[user_id] = {'state': 'waiting_for_work', 'task_title': task_title}
                send_msg(vk, user_id, "✅ Данные сохранены!\nТеперь отправьте текст работы или прикрепите файл.", keyboard=get_cancel_keyboard())

            elif state.get('state') == 'waiting_for_work':
                attachments = event.attachments
                if attachments or event.text:
                    student = get_student(user_id)
                    student_info = student['name'] if student else "Данные не указаны"
                    task_title = state.get('task_title', 'Файл/Медиа')
                    
                    add_submission(user_id, student_info, task_title, event.message_id)
                    
                    user_states[user_id] = None
                    send_msg(vk, user_id, "✅ Работа получена! Ожидайте проверки.", keyboard=get_main_keyboard(user_id, ADMIN_IDS))
                    for admin_id in ADMIN_IDS:
                        send_msg(vk, admin_id, f"🔔 Новая работа от {student_info}!\nНажмите 'Проверить работы'.", keyboard=get_main_keyboard(admin_id, ADMIN_IDS))

            # --- ПРЕПОДАВАТЕЛИ ---
            elif request == 'добавить задание' and user_id in ADMIN_IDS:
                user_states[user_id] = 'waiting_for_new_task'
                send_msg(vk, user_id, "Введите задание в формате:\nНазвание | Описание | Дедлайн", keyboard=get_cancel_keyboard())

            elif user_states.get(user_id) == 'waiting_for_new_task' and user_id in ADMIN_IDS:
                parts = [p.strip() for p in event.text.split('|')]
                if len(parts) == 3:
                    teacher_name = ADMIN_NAMES.get(user_id, "Преподаватель")
                    add_task(parts[0], parts[1], parts[2], user_id, teacher_name)
                    user_states[user_id] = None
                    send_msg(vk, user_id, "✅ Задание добавлено!", keyboard=get_main_keyboard(user_id, ADMIN_IDS))
                else:
                    send_msg(vk, user_id, "❌ Ошибка формата. Используйте два разделителя |", keyboard=get_main_keyboard(user_id, ADMIN_IDS))

            elif request == 'удалить задание' and user_id in ADMIN_IDS:
                tasks = get_all_tasks()
                if not tasks:
                    send_msg(vk, user_id, "📭 Список заданий пуст.", keyboard=get_main_keyboard(user_id, ADMIN_IDS))
                else:
                    text = "📋 Список всех заданий:\n\n"
                    for t in tasks:
                        text += f"ID {t[0]}. {t[1]}\n"
                    text += "\nВведите ID задания для удаления (или 'Отмена'):"
                    user_states[user_id] = 'waiting_for_delete_number'
                    send_msg(vk, user_id, text, keyboard=get_cancel_keyboard())

            elif user_states.get(user_id) == 'waiting_for_delete_number' and user_id in ADMIN_IDS:
                if request in ['отмена', '⬅️ назад в меню']:
                    user_states[user_id] = None
                    send_msg(vk, user_id, "Удаление отменено.", keyboard=get_main_keyboard(user_id, ADMIN_IDS))
                    continue
                try:
                    task_id = int(event.text.strip())
                    delete_task(task_id)
                    user_states[user_id] = None
                    send_msg(vk, user_id, f"✅ Задание с ID {task_id} удалено!", keyboard=get_main_keyboard(user_id, ADMIN_IDS))
                except ValueError:
                    send_msg(vk, user_id, "❌ Ошибка: введите ID (число) или 'Отмена'.")

            elif request == 'проверить работы' and user_id in ADMIN_IDS:
                show_next_submission(vk, user_id, ADMIN_IDS)

            elif request in ['✅ оценить', '❌ отклонить', '✍️ только комментарий', '⏭ пропустить'] and user_id in ADMIN_IDS:
                state = user_states.get(user_id, {})
                if state.get('state') not in ['reviewing', 'waiting_for_feedback', 'waiting_for_grade']: continue
                
                sub_id = state['task_id']
                row = get_pending_submission() # Проверяем, есть ли еще
                # Для простоты берем текущую работу из состояния
                # (В реальном коде лучше передавать данные работы в state)
                # Здесь мы просто используем sub_id для обновления
                
                if request == '⏭ пропустить':
                    show_next_submission(vk, user_id, ADMIN_IDS, current_task_id=sub_id)
                elif request == '✅ оценить':
                    user_states[user_id] = {'state': 'waiting_for_grade', 'task_id': sub_id}
                    send_msg(vk, user_id, "Введите оценку от 1 до 10 и (при желании) комментарий через пробел.\nПример:\n8 Отлично")
                elif request == '❌ отклонить':
                    update_submission_status(sub_id, 'rejected')
                    # Тут нужен student_id, но для простоты пропускаем отправку или берем из БД
                    # (В идеале нужно хранить student_id в состоянии)
                    send_msg(vk, user_id, f"Работа №{sub_id} отклонена.")
                    show_next_submission(vk, user_id, ADMIN_IDS)
                elif request == '✍️ только комментарий':
                    user_states[user_id] = {'state': 'waiting_for_feedback', 'task_id': sub_id}
                    send_msg(vk, user_id, "Напишите текст комментария/оценки для студента:")

            elif user_states.get(user_id, {}).get('state') == 'waiting_for_grade' and user_id in ADMIN_IDS:
                sub_id = user_states[user_id]['task_id']
                text_parts = event.text.split(' ', 1)
                try:
                    points = int(text_parts[0])
                    if points < 1 or points > 10:
                        send_msg(vk, user_id, "❌ Ошибка: оценка должна быть от 1 до 10 баллов.")
                        continue
                    comment = text_parts[1] if len(text_parts) > 1 else ""
                except ValueError:
                    send_msg(vk, user_id, "❌ Ошибка: оценка должна быть целым числом.")
                    continue

                # Получаем student_id из БД по sub_id (для отправки сообщения)
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute("SELECT student_id, task_title FROM submissions WHERE id = ?", (sub_id,))
                row = cursor.fetchone()
                conn.close()
                
                if row:
                    student_id, task_title = row
                    update_points(student_id, points)
                    update_submission_status(sub_id, 'accepted')
                    
                    student = get_student(student_id)
                    balance = student['points'] if student else "?"
                    
                    msg_to_student = f"✅ Преподаватель проверил вашу работу!\nЗадание: {task_title}\n\nВам начислено: {points} баллов! 🎉\nВаш баланс: {balance} баллов."
                    if comment: msg_to_student += f"\n\n💬 Комментарий преподавателя:\n{comment}"
                    send_msg(vk, student_id, msg_to_student)
                    send_msg(vk, user_id, f"✅ Оценка {points} баллов сохранена.")
                
                show_next_submission(vk, user_id, ADMIN_IDS)

            elif user_states.get(user_id, {}).get('state') == 'waiting_for_feedback' and user_id in ADMIN_IDS:
                sub_id = user_states[user_id]['task_id']
                # Получаем student_id
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute("SELECT student_id FROM submissions WHERE id = ?", (sub_id,))
                row = cursor.fetchone()
                conn.close()
                
                if row:
                    student_id = row[0]
                    update_submission_status(sub_id, 'commented')
                    send_msg(vk, student_id, f"📩 Ответ от преподавателя:\n\n{event.text}")
                    send_msg(vk, user_id, f"✅ Комментарий отправлен студенту.")
                show_next_submission(vk, user_id, ADMIN_IDS)

            else:
                if state.get('state') == 'waiting_for_work':
                     send_msg(vk, user_id, "Пожалуйста, отправьте текст работы или файл (или нажмите '⬅️ Назад в меню').", keyboard=get_cancel_keyboard())
                elif state.get('state') == 'waiting_for_name_group':
                     send_msg(vk, user_id, "Напишите ваше ФИО и группу (например: Иванов Иван, ИС-21) или нажмите '⬅️ Назад в меню'.", keyboard=get_cancel_keyboard())
                else:
                     send_msg(vk, user_id, "Я не понимаю команду. Используйте кнопки 👇", keyboard=get_main_keyboard(user_id, ADMIN_IDS))

if __name__ == '__main__':
    main()