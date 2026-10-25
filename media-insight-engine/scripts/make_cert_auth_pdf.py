"""Generate a PDF explaining how/where certificate-based DB auth works in the code.

Run:  python scripts/make_cert_auth_pdf.py
Out:  docs/db-cert-auth-explained.pdf
"""
from pathlib import Path

from fpdf import FPDF

OUT = Path(__file__).resolve().parent.parent / "docs" / "db-cert-auth-explained.pdf"

INK = (28, 28, 30)
MUTED = (90, 90, 96)
ACCENT = (24, 92, 168)
CODE_BG = (244, 245, 247)
RULE = (210, 212, 216)


class Doc(FPDF):
    def header(self):
        if self.page_no() == 1:
            return
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*MUTED)
        self.cell(0, 8, "Media Insight Engine - Certificate-based DB Auth", align="L")
        self.cell(0, 8, f"{self.page_no()}", align="R", new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "", 7)
        self.set_text_color(*MUTED)
        self.cell(0, 8, "Generated from the repo - mutual TLS between server and Postgres", align="C")


def h1(pdf, text):
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 15)
    pdf.set_text_color(*INK)
    pdf.multi_cell(0, 8, text, new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(*ACCENT)
    pdf.set_line_width(0.6)
    y = pdf.get_y() + 1
    pdf.line(pdf.l_margin, y, pdf.l_margin + 55, y)
    pdf.ln(4)


def h2(pdf, text):
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 11.5)
    pdf.set_text_color(*ACCENT)
    pdf.multi_cell(0, 6, text, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)


def body(pdf, text):
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*INK)
    pdf.multi_cell(0, 5.2, text, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)


def bullet(pdf, text, bold_lead=None):
    pdf.set_x(pdf.l_margin + 3)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*ACCENT)
    pdf.cell(4, 5.2, "-")
    start_x = pdf.get_x()
    if bold_lead:
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*INK)
        pdf.write(5.2, bold_lead + "  ")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*INK)
    pdf.set_x(start_x if not bold_lead else pdf.get_x())
    pdf.multi_cell(0, 5.2, text, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(0.5)


def code(pdf, ref, lines):
    """Code block with a file:line caption."""
    if ref:
        pdf.set_font("Helvetica", "BI", 8.5)
        pdf.set_text_color(*MUTED)
        pdf.multi_cell(0, 4.5, ref, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Courier", "", 8.3)
    line_h = 4.3
    text = "\n".join(lines)
    x0, y0 = pdf.get_x(), pdf.get_y()
    w = pdf.w - pdf.l_margin - pdf.r_margin
    n = len(lines)
    pdf.set_fill_color(*CODE_BG)
    pdf.set_draw_color(*RULE)
    pdf.rect(x0, y0, w, n * line_h + 3, style="DF")
    pdf.set_xy(x0 + 2, y0 + 1.5)
    pdf.set_text_color(*INK)
    pdf.multi_cell(w - 4, line_h, text, new_x="LMARGIN", new_y="NEXT")
    pdf.set_y(y0 + n * line_h + 3)
    pdf.ln(3)


def step(pdf, num, title, text):
    pdf.set_font("Helvetica", "B", 10.5)
    pdf.set_text_color(*ACCENT)
    pdf.cell(7, 5.5, f"{num}.")
    pdf.set_text_color(*INK)
    pdf.multi_cell(0, 5.5, title, new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(pdf.l_margin + 7)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*INK)
    pdf.multi_cell(pdf.w - pdf.l_margin - pdf.r_margin - 7, 5.2, text,
                   new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1.5)


pdf = Doc()
pdf.set_auto_page_break(auto=True, margin=16)
pdf.add_page()

# ---- Cover ----
pdf.ln(18)
pdf.set_font("Helvetica", "B", 24)
pdf.set_text_color(*INK)
pdf.multi_cell(0, 11, "Certificate-Based Database Authentication", new_x="LMARGIN", new_y="NEXT")
pdf.set_font("Helvetica", "", 13)
pdf.set_text_color(*MUTED)
pdf.multi_cell(0, 7, "How and where mutual TLS between the backend and Postgres works in the code",
               new_x="LMARGIN", new_y="NEXT")
pdf.ln(4)
pdf.set_draw_color(*ACCENT)
pdf.set_line_width(0.8)
pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + 70, pdf.get_y())
pdf.ln(8)
pdf.set_font("Helvetica", "", 10)
pdf.set_text_color(*INK)
pdf.multi_cell(0, 5.4,
    "Project: media-insight-engine\n"
    "Scope: the containerized (Docker) path, where the server authenticates to\n"
    "Postgres with a client certificate instead of a password.",
    new_x="LMARGIN", new_y="NEXT")
pdf.ln(6)

# ---- TL;DR ----
h2(pdf, "In one sentence")
body(pdf,
    "Instead of logging in with a password, the backend presents a client certificate over an "
    "encrypted TLS connection. Postgres checks that the certificate was signed by a trusted CA and "
    "that its name (CN=mie) matches the database role, and that IS the login. The certificate is "
    "handed to the backend at startup by HashiCorp Vault and lives only in RAM.")

h2(pdf, "The four moving parts")
bullet(pdf, "generates the CA, the server cert, and the client cert; seeds Vault.", "cert-init (one-shot)")
bullet(pdf, "the safe that stores the client cert + private key.", "Vault")
bullet(pdf, "runs with TLS on and checks client certs instead of passwords.", "Postgres (db)")
bullet(pdf, "fetches its cert from Vault and connects with it.", "Backend (server)")

# ---- Page 2: the flow ----
pdf.add_page()
h1(pdf, "The flow, step by step (with code)")

step(pdf, 1, "Certificates are created and stored",
    "cert-init runs openssl to create a CA, a server cert, and a client cert whose CN is 'mie'. "
    "The client bundle is pushed into Vault; Postgres gets its server cert on a shared volume.")
code(pdf, "scripts/cert-init.sh:30-31  (client cert, CN=mie)", [
    'openssl req -new -nodes -newkey rsa:2048 \\',
    '  -keyout "$SRC/client.key" -out /tmp/client.csr -subj "/CN=mie"',
    'openssl x509 -req -in /tmp/client.csr -CA "$SRC/ca.crt" ...',
])

step(pdf, 2, "Postgres comes up in TLS mode",
    "docker-compose starts Postgres with ssl=on plus a server cert, key, and CA. All DB "
    "connections can now be encrypted, and the server can request a client cert.")
code(pdf, "docker-compose.yml:37-46", [
    'command:',
    '  - postgres',
    '  - -c',
    '  - ssl=on',
    '  - -c',
    '  - ssl_cert_file=/etc/postgres/certs/server.crt',
    '  - -c',
    '  - ssl_key_file=/etc/postgres/certs/server.key',
    '  - -c',
    '  - ssl_ca_file=/etc/postgres/certs/ca.crt',
])

step(pdf, 3, "The auth rule says 'use the certificate, not a password'",
    "pg_hba.conf is Postgres's rulebook. The hostssl line matches TLS connections to the mie "
    "database and authenticates them by client certificate (method 'cert'). clientcert=verify-full "
    "means the cert's CN must equal the role name. No password is involved on this path.")
code(pdf, "postgres/pg_hba.conf:8-9", [
    '# TYPE     DATABASE  USER  ADDRESS  METHOD',
    'hostssl    mie       mie   all      cert clientcert=verify-full',
    'host       mie       mie   all      scram-sha-256   # non-TLS fallback',
])

pdf.add_page()
step(pdf, 4, "The backend is told to use cert auth, with no password in the URL",
    "The server container runs with DB_AUTH=cert and a DATABASE_URL that has a username but NO "
    "password - the certificate is the credential.")
code(pdf, "docker-compose.yml:64-70", [
    'environment:',
    '  DB_AUTH: cert',
    '  DATABASE_URL: postgresql://mie@db:5432/mie   # no password',
    '  VAULT_ADDR: http://vault:8200',
    '  VAULT_TOKEN_FILE: /certs-shared/vault-token',
    '  VAULT_DB_CERT_PATH: mie/db-client',
    '  DB_CERT_DIR: /run/mie-certs',
])
body(pdf,
    "Note: /run/mie-certs is a tmpfs mount (docker-compose.yml:74-75), so the private key lives in "
    "RAM and never touches disk.")

step(pdf, 5, "At startup the backend fetches its cert from Vault",
    "init_db() sees db_auth == 'cert' and calls secrets.ensure_db_certs(). That function reads the "
    "bundle from Vault over HTTP, writes ca.crt / client.crt / client.key into the tmpfs dir at 0600 "
    "(libpq rejects a world-readable key), and returns the libpq SSL parameters.")
code(pdf, "server/app/db.py:17-21  (the decision + the connect)", [
    '# Mutual-TLS cert auth: fetch the client cert from Vault and',
    '# connect with sslmode=verify-full.',
    'ssl = secrets.ensure_db_certs() if settings.db_auth == "cert" else {}',
    'with psycopg.connect(settings.database_url,',
    '                     autocommit=True, **ssl) as conn:',
])
code(pdf, "server/app/secrets.py:16-17, 54-60  (filename -> libpq param)", [
    '_CERT_FILES = {"ca.crt": "sslrootcert",',
    '               "client.crt": "sslcert",',
    '               "client.key": "sslkey"}',
    '...',
    'ssl = {"sslmode": "verify-full"}',
    'for filename, param in _CERT_FILES.items():',
    '    path = cert_dir / filename',
    '    path.write_text(data[filename])',
    '    path.chmod(0o600)        # libpq rejects world-readable key',
    '    ssl[param] = str(path)',
    'return ssl',
])

pdf.add_page()
step(pdf, 6, "The TLS handshake authenticates both sides",
    "psycopg/libpq connects with sslmode=verify-full and the three files. verify-full means the "
    "backend also verifies the SERVER's identity (correct CA + hostname 'db'), while it presents its "
    "own client cert. Postgres validates the client cert against the CA, reads CN=mie, maps it to the "
    "mie role, and authorizes the connection - all without a password.")

step(pdf, 7, "Every pooled connection reuses the same TLS settings",
    "The same ssl kwargs are passed into the connection pool, so each connection the app borrows is "
    "a mutual-TLS connection.")
code(pdf, "server/app/db.py:26-28", [
    '_pool = ConnectionPool(settings.database_url,',
    '    min_size=1, max_size=10, open=True,',
    '    kwargs={"autocommit": True, "row_factory": dict_row, **ssl},',
    '    configure=register_vector)',
])

h1(pdf, "The one caveat to mention")
body(pdf,
    "Certificate auth only runs when DB_AUTH == 'cert', which is the Docker/production-style path. "
    "For local, non-Docker development there is a password fallback: the Makefile target connects "
    "with DB_AUTH=password and sslmode=disable, which deliberately matches the plaintext 'host ... "
    "scram-sha-256' rule in pg_hba.conf instead of the 'hostssl' cert rule.")
code(pdf, "Makefile:25  (local dev fallback)", [
    'DATABASE_URL="postgresql://mie:$$POSTGRES_PASSWORD@localhost:5437/mie?sslmode=disable"',
    'DB_AUTH=password',
])
body(pdf,
    "Also worth noting: the Vault container runs in dev mode (in-memory, auto-unsealed, root token), "
    "so the certificate DELIVERY mechanism is dev-grade, even though the DB auth itself is real "
    "mutual TLS. Production hardening (persistent Vault, auto-unseal, cert rotation) is listed as "
    "future work in docs/superpowers/specs/2026-10-21-db-cert-auth-vault-design.md.")

h1(pdf, "Where to look - file map")
bullet(pdf, "the openssl bootstrap that mints the CA, server, and client certs.", "scripts/cert-init.sh")
bullet(pdf, "wires up Vault, cert-init, Postgres (ssl=on), and the server (DB_AUTH=cert).", "docker-compose.yml")
bullet(pdf, "the auth rule: hostssl ... cert clientcert=verify-full.", "postgres/pg_hba.conf")
bullet(pdf, "chooses cert vs password and makes the actual connection / pool.", "server/app/db.py")
bullet(pdf, "fetches the cert bundle from Vault and returns the libpq SSL params.", "server/app/secrets.py")
bullet(pdf, "the design rationale and the production-hardening TODO list.", "docs/.../db-cert-auth-vault-design.md")

OUT.parent.mkdir(parents=True, exist_ok=True)
pdf.output(str(OUT))
print(f"wrote {OUT}")
