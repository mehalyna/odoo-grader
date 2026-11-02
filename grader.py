import getpass
import xmlrpc.client

URL = "https://edu-grandmas.odoo.com"
DB = "edu-grandmas"  # Якщо назва бази інша, потрібно замінити.

login = input("Email Odoo: ").strip()
password = getpass.getpass("Пароль Odoo: ")

try:
    common = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common")
    print("Версія:", common.version()["server_version"])

    uid = common.authenticate(DB, login, password, {})
    if not uid:
        print("Авторизація не вдалася. Перевір назву бази, email і пароль.")
    else:
        print("Авторизація успішна.")

        models = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object")
        count = models.execute_kw(
            DB, uid, password,
            "res.partner", "search_count", [[]]
        )
        print("Читання даних успішне.")
        print("Кількість доступних контактів:", count)

except xmlrpc.client.Fault as error:
    print("Помилка Odoo:", error.faultString)
except Exception as error:
    print(f"Помилка підключення: {type(error).__name__}: {error}")
finally:
    password = None