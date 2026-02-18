from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

# Create a single-button ReplyKeyboardMarkup with '/start' only
persistent_kb = ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton('/start'))

# Other handlers that need to be removed or disabled
# (You would create handlers for '/start' accordingly)

def quick_start_button():
    show_main_menu()

# Ensure show_main_menu does not send unwanted messages
async def show_main_menu():
    # Removed unwanted print statements
    pass
