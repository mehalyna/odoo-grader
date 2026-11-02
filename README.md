# Odoo grader

Read-only autograder for Odoo 19 tasks, using XML-RPC.

## Setup

1. Install the dependencies:

   ```powershell
   python -m pip install -r requirements.txt
   ```

2. Create your local settings file by copying the template:

   ```powershell
   Copy-Item .env.example .env
   ```

3. Edit `.env` and fill in `ODOO_LOGIN` and `ODOO_PASSWORD`.

   Quote any value that contains spaces or `#`, because an unquoted `#` starts a comment:

   ```dotenv
   ODOO_PASSWORD="my pass #1"
   ```

   Do not commit `.env`. It is listed in `.gitignore`.

Settings are read in this order: existing environment variables, then `.env`. Missing login or password values are prompted for, and the password is entered with hidden input.

## Run

```powershell
python task_1_1.py             # grade task 1.1; JSON on stdout, summary on stderr
python task_1_1.py --diagnose  # print field metadata only (no record data)
```

## Tests (offline)

```powershell
python -m unittest test_domain_logic test_task_1_1 -v
```
