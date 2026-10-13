# Pinfers + Postiz — instalare fără Docker

Sursă Postiz inclusă în `postiz/`, modulul Content Pinfers în `pinfers-library/`, configurații PM2 și Nginx. Un singur `git clone`; nu sunt necesare submodule Git. Versiunea upstream este fixată în `UPSTREAM.md`.

**Nu există publicare automată în modulul Pinfers.** Biblioteca generează clipuri, importă fișiere în Postiz, citește istoricul și păstrează planuri locale. Conectarea conturilor, aprobările TikTok și publicarea se configurează separat. Descrierile sunt încă provizorii. Muzica nu se selectează automat în această versiune.

## Ce este inclus și ce rămâne privat

- Cod complet, designul cu 3 scene, fontul Outfit, logo Pinfers, badge-uri de download și tranziția roșie.
- Exemple de configurare cu valori demonstrative. **Nicio parolă sau cheie reală.**
- Nu sunt incluse contul local Postiz, volumele Docker, SQLite, clipurile generate, sesiuni sau tokenuri. Pe o instalare nouă ofertele publice se sincronizează și clipurile se regenerează.
- `config/`, `.env`, baza locală, uploadurile, logurile și datele generate sunt ignorate de Git. Nu folosi `git add -f` pentru acestea.

Acesta este un server partajat cu alte aplicații, deci începe cu verificările numai în citire. Nu instala pachete de sistem, nu porni/opri servicii, nu schimba nginx.conf și nu salva configurația PM2 până nu am verificat împreună porturile, procesele și serviciile deja existente. Instalarea se va face în `/opt/pinfers-postiz`; nu folosim baza de date Pinfers din producție.

## 0. Inventar sigur pe serverul nou

După clone, rulează comenzile de inventar una câte una și trimite-mi rezultatul înainte să continuăm. Fiecare comandă de inventar doar citește starea serverului și nu modifică aplicațiile.

```bash
cat /etc/os-release
node --version
pm2 list
sudo ss -lntp
df -h /
free -h
```

Trimite-mi rezultatele înainte de instalarea dependențelor. Dacă `node` sau `pm2` nu există, spune-mi; nu instala încă versiuni globale fiindcă pot schimba mediul celorlalte aplicații.

## 1. Clone

```bash
sudo install -d -o "$USER" -g "$(id -gn)" /opt/pinfers-postiz
git clone https://github.com/Bodron/pinfers-postiz.git /opt/pinfers-postiz
cd /opt/pinfers-postiz
```

Clone-ul nu pornește nimic. Repo-ul este privat în momentul acesta; utilizatorul GitHub al serverului trebuie să aibă acces la el. Alege un director nou al tău și folosește acea cale în loc de `/opt` dacă nu ai acces acolo.

Este necesar **Node 22.12+ din seria 22**. Înainte de schimbarea versiunii, verifică ce Node folosesc aplicațiile existente. Dacă serverul are deja NVM:

```bash
nvm install 22
nvm use 22
npm install -g pnpm@10.6.1
node --version
pnpm --version
```

Nu instala Node global și nu modifica PM2 startup pe serverul comun până nu verificăm configurația existentă. PM2 instalat sub NVM trebuie pornit cu versiunea potrivită după reboot.

Fișierele de exemplu au porturi de pornire pentru Postiz, Redis, PostgreSQL și Temporal. Pe serverul tău alegem porturi după inventarul real, schimbând toate adresele corespunzătoare înainte de pornire. Niciun port al Postiz, Redis, PostgreSQL sau Temporal nu se expune public; Nginx folosește numai loopback. Porturile publice 80/443 rămân sub controlul Nginx deja instalat.

## 2. Baze dedicate, fără resetarea altor aplicații

Nu instala și nu porni PostgreSQL ori Redis prin comenzile generice `apt install` / `systemctl enable --now` pe serverul partajat. După inventar, alegem varianta izolată potrivită: roluri și baze noi în instanța PostgreSQL existentă ori servicii dedicate pe porturi libere. Nu reutiliza instanța MongoDB Pinfers. Comenzile SQL se rulează numai după verificarea portului și a destinației.

Nu șterge, nu reseta și nu modifica baze existente. PostgreSQL și Redis trebuie să rămână accesibile doar local sau în rețeaua privată.

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
```

Pe serverul comun, **nu rula `pm2 save` și `pm2 startup`** până nu verificăm ce procese și configurații de startup există deja. Acestea operează asupra întregului set PM2 al utilizatorului, nu numai asupra Pinfers. După pornire:

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
