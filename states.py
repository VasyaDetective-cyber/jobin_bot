from aiogram.fsm.state import State, StatesGroup


# ---------- клієнт ----------
class OrderFSM(StatesGroup):
    waiting_receipt = State()       # чекаємо скріншот/фото квитанції
    waiting_vacancy_text = State()  # чекаємо текст вакансії


class CartFSM(StatesGroup):
    waiting_code = State()          # клієнт вводить промокод


class ChatFSM(StatesGroup):
    chatting = State()              # клієнт пише менеджеру в боті


class ReviewFSM(StatesGroup):
    waiting_comment = State()       # коментар до оцінки


# ---------- редактор ----------
class EditorFSM(StatesGroup):
    waiting_link = State()          # посилання на опублікований пост


# ---------- адмін ----------
class AdminRejectFSM(StatesGroup):
    waiting_reason = State()


class AdminChatFSM(StatesGroup):
    waiting_message = State()       # адмін відповідає клієнту


class AdminCatalogFSM(StatesGroup):
    waiting_new_product_name = State()
    waiting_field_value = State()


class BroadcastFSM(StatesGroup):
    waiting_content = State()
    waiting_confirm = State()


class AdminPromoFSM(StatesGroup):
    code = State()
    percent = State()
    max_uses = State()


class AdminManagerFSM(StatesGroup):
    name = State()
    username = State()
    code = State()
    waiting_value = State()         # редагування існуючого менеджера