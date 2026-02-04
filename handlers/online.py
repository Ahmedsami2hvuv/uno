import random
from aiogram import Router, F, types
from database import db_query

router = Router()

# تحديث محرك الأوراق لإضافة الجوكر +1 و +2
def generate_deck():
    colors = ["🔴", "🔵", "🟡", "🟢"]
    deck = []
    for c in colors:
        deck.append(f"{c} 0")
        for n in range(1, 10): deck.extend([f"{c} {n}", f"{c} {n}"])
        for a in ["🚫", "🔄", "➕2"]: deck.extend([f"{c} {a}", f"{c} {a}"])
    
    # إضافة الأوراق الخاصة الجديدة (4 من كل نوع)
    deck.extend(["🌈"] * 4)       # ملونة عادية (50 نقطة)
    deck.extend(["🌈➕1"] * 4)     # جوكر سحب 1 (10 نقاط)
    deck.extend(["🌈➕2"] * 4)     # جوكر سحب 2 (20 نقطة)
    deck.extend(["🌈➕4"] * 4)     # جوكر سحب 4 (50 نقطة)
    
    random.shuffle(deck)
    return deck

# (بقية كود الأونلاين والبحث عن لاعب...)
