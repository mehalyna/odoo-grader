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
python -m cli.task_1_1             # grade task 1.1; JSON on stdout, summary on stderr
python -m cli.task_1_1 --diagnose  # print field metadata only (no record data)
```

## Several student databases

1. Copy the template and list the students. The JSON holds only the *names* of environment variables, never credentials:

   ```powershell
   Copy-Item students.example.json students.json
   ```

   Required per student: `id` (letters, digits, `_`, `-`; used as a directory name), `url` (https), `db`,
   `login_env`, `password_env`. Optional: `share_user_id` or `share_user_login` (the user checked in 1.1.6; the id
   wins if both are set) and `contacts_action_xmlid` (default `contacts.action_contacts`). Without these, the same
   defaults as single-database mode apply. The `ODOO_*` variables are not used in this mode.

2. Put each student's credentials in `.env` or the environment, using the variable names from the JSON
   (`STUDENT_01_LOGIN`, `STUDENT_01_PASSWORD`, see `.env.example`). Only selected students' variables are read.

3. Run (exactly one of `--student` or `--all` is required):

   ```powershell
   python -m cli.task_1_1 --config students.json --student student_01
   python -m cli.task_1_1 --config students.json --all
   python -m cli.task_1_1 --config students.json --all --output-dir results
   ```

The configuration is validated before any connection. Each student gets a separate connection and a report at
`results/<run_id>/<student_id>/task_1_1.json` (UTF-8, written atomically) with `schema_version`, `run_id`,
`student_id`, `database` (URL and name), `checked_at` (UTC) and the usual `task_report`. A student who cannot be
reached gets an `ERROR` report (6 pending points) and the others continue. The exit code is `2` for invalid
configuration or usage and `1` if any report could not be saved; grading outcomes do not change it. `students.json`
and `results/` are git-ignored.

## Tests (offline)

```powershell
python -m unittest discover -s tests -t . -v
```
