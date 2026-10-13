# Pinfers + Postiz — instalare fără Docker

Sursă Postiz inclusă în `postiz/`, modulul Content Pinfers în `pinfers-library/`, configurații PM2 și Nginx. Un singur `git clone`; nu sunt necesare submodule Git. Versiunea upstream este fixată în `UPSTREAM.md`.

**Nu există publicare automată în modulul Pinfers.** Biblioteca generează clipuri, importă fișiere în Postiz, citește istoricul și păstrează planuri locale. Conectarea conturilor, aprobările TikTok și publicarea se configurează separat. Descrierile sunt încă provizorii. Muzica nu se selectează automat în această versiune.

## Ce este inclus și ce rămâne privat

- Cod complet, designul cu 3 scene, fontul Outfit, logo Pinfers, badge-uri de download și tranziția roșie.
- Exemple de configurare cu valori demonstrative. **Nicio parolă sau cheie reală.**
- Nu sunt incluse contul local Postiz, volumele Docker, SQLite, clipurile generate, sesiuni sau tokenuri. Pe o instalare nouă ofertele publice se sincronizează și clipurile se regenerează.
- `config/`, `.env`, baza locală, uploadurile, logurile și datele generate sunt ignorate de Git. Nu folosi `git add -f` pentru acestea.

Comenzile de mai jos sunt pentru **Ubuntu 24.04 / Debian compatibil, acces sudo**, instalare în `/opt/pinfers-postiz`, rulate ca utilizator normal cu sudo. Nu sunt executate automat pe serverul tău. Dacă ai alte aplicații, verifică întâi porturile și resursele. Nu înlocui nginx.conf global și nu folosi baza de date Pinfers din producție.

## 1. Clone și cerințe

```bash
sudo install -d -o "$USER" -g "$(id -gn)" /opt/pinfers-postiz
git clone https://github.com/Bodron/pinfers-postiz.git /opt/pinfers-postiz
cd /opt/pinfers-postiz
sudo apt-get update
sudo apt-get install -y git build-essential python3 python3-venv ffmpeg tzdata postgresql postgresql-client redis-server nginx golang-go certbot python3-certbot-nginx
```

Este necesar **Node 22.12+ din seria 22**. Dacă folosești deja NVM pe server:

```bash
nvm install 22
nvm use 22
npm install -g pnpm@10.6.1 pm2
node --version
pnpm --version
```

Dacă nu ai NVM, instalează Node 22 din [sursele oficiale Node.js](https://nodejs.org/en/download). Nu actualiza la întâmplare versiunea folosită de celelalte aplicații. PM2 instalat sub NVM trebuie configurat pentru repornire cu versiunea corectă Node.

Verifică porturile înainte de pornire:

```bash
sudo ss -lntp
```

Acest proiect folosește local 13100 (backend), 13102 (orchestrator), 14200 (frontend), 14011 (bibliotecă), 14007 (Nginx intern), 7233–7239 și 6933–6939 (Temporal); PostgreSQL 5432 și Redis 6379. Pe internet se expun numai 80/443. Dacă sunt ocupate, modifică valorile și configurațiile corespunzătoare înainte să continui.

## 2. Baze dedicate, fără resetarea altor aplicații

Dacă serviciile există deja, păstrează configurația lor. Creează **baze noi și roluri separate**. Comenzile cer parole interactiv; nu le scrie în Git sau în comenzi salvate.

```bash
sudo systemctl enable --now postgresql redis-server
sudo -u postgres createuser --pwprompt postiz
sudo -u postgres createdb --owner=postiz postiz
sudo -u postgres createuser --pwprompt temporal
sudo -u postgres createdb --owner=temporal temporal
sudo -u postgres createdb --owner=temporal temporal_visibility
```

Dacă numele există deja, oprește-te și alege altele; adaptează config-ul. Nu șterge baze existente. PostgreSQL și Redis trebuie să rămână accesibile doar local sau în rețeaua privată.

## 3. Fișierul ENV privat

```bash
mkdir -p config
chmod 700 config
cp deploy/postiz.env.example config/postiz.env
chmod 600 config/postiz.env
nano config/postiz.env
```

Completează local:

| Variabilă | Valoare |
|---|---|
| `DATABASE_URL` | `postgresql://postiz:PAROLA_TA@127.0.0.1:5432/postiz`; caracterele speciale din parolă trebuie codificate pentru URL |
| `JWT_SECRET` | Secret nou, lung; poți genera local cu `openssl rand -hex 48`. Nu-l trimite în chat/Git |
| `REDIS_URL` | Adresa Redis locală; adaugă autentificarea dacă serverul o cere |
| `FRONTEND_URL`, `MAIN_URL`, `PUBLIC_ORIGIN` | `https://pinferspostiz.bcmenu.ro` |
| `NEXT_PUBLIC_BACKEND_URL` | `https://pinferspostiz.bcmenu.ro/api` |
| `BACKEND_INTERNAL_URL` | `http://127.0.0.1:13100` |
| `POSTIZ_BASE` | `http://127.0.0.1:14007` |
| `UPLOAD_DIRECTORY` | `/opt/pinfers-postiz/uploads` |
| `LIBRARY_DATA_DIR` | `/opt/pinfers-postiz/state` |
| `TEMPORAL_ADDRESS` | `127.0.0.1:7233` pentru pașii de mai jos |
| `NOT_SECURED` | `false`, fiindcă domeniul va folosi HTTPS |
| `RENDER_WORKERS` | `1` inițial; crește la 2–3 numai dacă ai CPU/RAM suficient |
| `TIKTOK_CLIENT_ID`, `TIKTOK_CLIENT_SECRET` | Goale până configurăm aplicația TikTok; apoi cheile reale, numai local |
| `TIKTOK_BUSINESS_CLIENT_ID`, `TIKTOK_BUSINESS_CLIENT_SECRET` | Goale; integrare separată TikTok Business |
| `FACEBOOK_APP_ID`, `FACEBOOK_APP_SECRET` | Goale până configurăm aplicația Meta |

Lasă celelalte valori ca în exemplu dacă folosești aceste porturi și calea `/opt/pinfers-postiz`. Fișierul acceptă câte un `KEY="value"` pe linie, fără substituții shell sau valori pe mai multe linii.

## 4. Build Postiz + modul Pinfers

```bash
bash scripts/build.sh
cd postiz
pnpm exec dotenv -e .env -- pnpm run prisma-db-push
cd ..
```

Comanda de schemă se rulează **numai asupra noii baze Postiz dedicate**, după verificarea `DATABASE_URL`. Nu adăuga `--accept-data-loss`, `--force-reset` și nu folosi `prisma-reset`. Pentru actualizări viitoare se face backup înainte de schimbarea schemei.

## 5. Temporal nativ cu PostgreSQL, fără Docker

Folosește serviciu persistent, nu `temporal server start-dev`. Scriptul descarcă sursa oficială `temporalio/temporal`, tag **v1.28.1**, și compilează serverul și utilitarul SQL. Go descarcă toolchain-ul cerut de versiune (1.24.5); build-ul poate dura și consuma RAM.

```bash
bash scripts/build-temporal.sh
python3 scripts/configure-temporal.py
python3 scripts/init-temporal.py
pm2 start ecosystem.temporal.cjs
pm2 logs pinfers-temporal --lines 40
```

Introdu parola rolului PostgreSQL `temporal` în cele două scripturi interactive. Configurația rezultată este `config/temporal/production.yaml`, privată și ignorată de Git. `init-temporal.py` este doar pentru baze proaspete; pentru un cluster existent se urmează procedura oficială de upgrade, nu se repetă inițializarea.

După ce logul arată că Temporal rulează:

```bash
node scripts/init-namespace.cjs
```

Acest exemplu este pentru un singur server. Backupurile PostgreSQL sunt necesare pentru a păstra programările. [Documentație Temporal](https://docs.temporal.io/self-hosted-guide).

## 6. Nginx și HTTPS

Setează în DNS înregistrarea A pentru `pinferspostiz.bcmenu.ro` către IP-ul serverului. Nu adăuga AAAA dacă IPv6 nu este configurat.

```bash
sudo ln -s /opt/pinfers-postiz/deploy/nginx-site.conf /etc/nginx/sites-enabled/pinfers-postiz.conf
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d pinferspostiz.bcmenu.ro
sudo nginx -t
sudo systemctl reload nginx
```

Nu înlocui un vhost care există deja. Dacă folosești alt panou/configuration layout, include aceste rute într-un vhost separat prin metoda panoului. Modulele Nginx standard trebuie să includă `http_sub_module` pentru linkul Media din Postiz (`nginx -V`).

## 7. Pornire și verificare

```bash
pm2 start ecosystem.config.cjs
pm2 save
pm2 startup
```

Rulează comanda specifică afișată de `pm2 startup` pentru utilizatorul tău. Apoi:

```bash
pm2 status
curl --fail http://127.0.0.1:14011/health
curl -I https://pinferspostiz.bcmenu.ro/auth
```

Deschide domeniul, creează contul Postiz local al acestei instalări, intră la Media/Content și apasă **Actualizează ofertele**. După generare, apasă **Importă clipurile în Media**. Catalogul Pinfers este citit prin API-ul public; nu este necesară și nu este folosită conexiunea MongoDB din producție.

Nu este încă autorizată nicio publicare TikTok/Facebook. Conturile se conectează separat. Pentru TikTok, redirect URI va fi `https://pinferspostiz.bcmenu.ro/integrations/social/tiktok`, domeniul media trebuie verificat, iar vizibilitatea publică depinde de aprobările TikTok.

## Actualizări

```bash
git pull --ff-only
bash scripts/build.sh
pm2 restart ecosystem.config.cjs --update-env
```

`config/postiz.env` este ignorat și rămâne local. Backup înainte de upgrade sau migrarea schemelor. Nu actualiza Temporal fără procedura de upgrade a serverului și schemelor.

## Mutarea datelor existente de pe Mac

Git transferă codul, nu datele. Poți porni curat și regenera clipurile. Pentru păstrarea contului și Media existente se transferă separat, securizat: dump PostgreSQL Postiz, fișierele uploads și `library.sqlite3` + directorul clips. SQLite se exportă cu backup API, nu prin copierea unui WAL activ. Secretul JWT se transferă privat dacă dorești continuitatea sesiunilor. Nu pune backupurile în GitHub și nu restaura tabelele de planificare înainte să verifici programările existente.

## Validare și limite

Configurațiile/scripturile au verificări locale de sintaxă și teste pentru mutarea datelor bibliotecii și originea HTTPS. Instalarea completă fără Docker nu a fost încă executată pe serverul tău; verificarea PostgreSQL, Temporal, build Next/Nest, certificat și login se face acolo înainte de conectarea conturilor. Nu trata acest repo ca o integrare TikTok deja aprobată.
