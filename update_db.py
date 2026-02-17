from database import db_query

def update_database():
    print("⏳ جاري تحديث قاعدة البيانات...")
    try:
        # إضافة عمود التنبيهات لجدول المتابعة
        db_query("ALTER TABLE follows ADD COLUMN notify_games BOOLEAN DEFAULT 0", commit=True)
        print("✅ تمت إضافة عمود notify_games بنجاح.")
    except Exception as e:
        print(f"⚠️ عمود notify_games قد يكون موجوداً مسبقاً: {e}")

    try:
        # إضافة عمود سماح الطلبات لجدول المستخدمين
        db_query("ALTER TABLE users ADD COLUMN allow_invites BOOLEAN DEFAULT 1", commit=True)
        print("✅ تمت إضافة عمود allow_invites بنجاح.")
    except Exception as e:
        print(f"⚠️ عمود allow_invites قد يكون موجوداً مسبقاً: {e}")

    print("🚀 انتهى التحديث!")

if __name__ == "__main__":
    update_database()
