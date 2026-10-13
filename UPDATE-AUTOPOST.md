# Publicare continuă: 3 oferte pe zi pe fiecare cont

Actualizarea pregătește automat 3 videoclipuri cu oferte diferite pe fiecare pagină/cont selectat, zilnic, la 10:00, 15:00 și 20:00, ora României. Orele sunt editabile. Selectarea prioritizează ofertele folosite cel mai rar pe contul respectiv, astfel încât ofertele noi intră în rotație. Aceeași ofertă la două locații nu ocupă două dintre cele trei poziții ale aceleiași zile.

Workerul rulează pe server, fără să ții browserul deschis, actualizează catalogul la 15 minute și pregătește restul zilei curente plus ziua următoare. Nu recuperează orele trecute prin publicări în rafală. Dacă există mai puțin de 3 oferte active și eligibile, nu repetă aceeași ofertă în aceeași zi. Ofertele expirate/inactive nu sunt selectate; programările viitoare create de automatizare sunt anulate dacă oferta se dezactivează, se schimbă sau expiră înainte de publicare.

Instalarea nu activează publicarea. După configurare, mergi în Content → Planificări & rotație → Publicare automată zilnică, selectează paginile/conturile și apasă Activează publicarea automată. Facebook publică la orele alese. Oprirea anulează programările viitoare create de automatizare; trimiterile în curs sau cu rezultat incert trebuie verificate în calendar.

TikTok Sandbox este pentru testarea încărcării în inbox. Nu oferă publicare publică complet automată. Cu `TIKTOK_UPLOAD_ONLY="true"`, integrarea cere doar `user.info.basic` și `video.upload`, folosește profilul de bază și forțează încărcarea în inbox, inclusiv dacă un client trimite accidental DIRECT_POST. Captionul video nu este acceptat de endpointul de inbox; rămâne în Postiz pentru copiere în TikTok. Conturile TikTok pot fi selectate pentru 3 trimiteri automate pe zi în inbox. Utilizatorul trebuie să deschidă notificările și să finalizeze publicarea în TikTok. Limita TikTok este de 5 trimiteri în așteptare în 24 de ore; dacă este atinsă, verifică eroarea în calendar.

Pentru TikTok complet automat trebuie configurată/aprobată aplicația Production pentru Direct Post și folosite cheile ei, apoi `TIKTOK_UPLOAD_ONLY="false"`. Integrarea standard continuă să ceară scope-urile sale existente: `user.info.basic`, `user.info.profile`, `user.info.stats`, `video.list`, `video.publish`, `video.upload`. Nu schimba flag-ul doar pentru a ocoli limitele Sandbox. Aprobările și accesul la publicare publică se verifică separat cu TikTok.

## Ce chei completezi

În `/opt/pinfers-postiz/config/postiz.env`:

```dotenv
TIKTOK_CLIENT_ID="CLIENT_KEY_DIN_SANDBOX"
TIKTOK_CLIENT_SECRET="CLIENT_SECRET_DIN_SANDBOX"
TIKTOK_UPLOAD_ONLY="true"
POSTIZ_AUTOMATION_API_KEY="CHEIA_API_A_ORGANIZATIEI_POSTIZ"
```

`TIKTOK_CLIENT_ID` este **Client key**, nu App ID. Cheile TikTok se copiază din Pinfers Content → Sandbox → Pinfers Postiz Test → Credentials. Conturile din Target users trebuie conectate încă o dată ca Channels în Postiz pentru a putea încărca drafturi.

Cheia Postiz se găsește în Settings → Agents → API Key: `https://pinferspostiz.bcmenu.ro/settings?tab=agents`. Folosește cheia existentă; nu o roti dacă este deja utilizată. Este o cheie privată și trebuie să aparțină organizației unde sunt conectate paginile. Workerul o trimite numai backendului Postiz local. Păstrează valorile Facebook existente (`FACEBOOK_APP_ID` și `FACEBOOK_APP_SECRET`). Nu pune cheile în Git sau chat.

## Instalare pe server

Pe Mac, transferă arhiva:

```bash
scp /Users/bodronc/Documents/Codex/2026-10-13/nea/outputs/pinfers-autopost-update.tar.gz root@91.98.20.36:/tmp/
```

Pe serverul Ubuntu:

```bash
cd /opt/pinfers-postiz
tar -xzf /tmp/pinfers-autopost-update.tar.gz scripts/install-autopost-update.sh
bash scripts/install-autopost-update.sh /tmp/pinfers-autopost-update.tar.gz
nano config/postiz.env
bash scripts/build.sh
pm2 restart ecosystem.config.cjs --update-env
curl --fail http://127.0.0.1:14011/health
pm2 logs pinfers-library --lines 30 --nostream
```

Este necesar Node 22.12+ din seria 22, ca la instalarea inițială. Scriptul face backup la sursele existente, configurația privată și SQLite cu backup API; nu copiază un WAL activ. Arhiva nu conține chei, baze de date sau uploaduri și nu modifică Nginx/Temporal. Nu este necesar `prisma-db-push`; schema PostgreSQL Postiz nu se schimbă. SQLite primește doar tabele/coloane noi, păstrând istoricul și planurile existente.

## Facebook și verificare

Pentru Facebook se creează separat `clip-facebook.mp4`, de 1080 × 1920, cu conținutul centrat de 1062 × 1888. Marginile sunt simetrice: 9 pixeli stânga/dreapta și 16 pixeli sus/jos, fără decupare sau schimbarea proporțiilor. Clipul TikTok original nu este modificat. Copiile Facebook pentru clipurile deja generate se pregătesc automat în fundal; nu este necesară regenerarea ofertelor. La fiecare ofertă poți previzualiza și descărca ambele variante.

Înainte să activezi, verifică previzualizarea Facebook. După activare, verifică în calendar că apar trei programări pe fiecare pagină pe zi. Istoricul publicărilor automate este sincronizat în fundal; încărcarea într-un inbox TikTok nu este numărată ca publicare publică. În cazul unui timeout după acceptarea unei programări, starea devine „în verificare” și nu se retrimite automat, evitând postările duplicate.

Verificări locale:

```bash
python3 scripts/validate-library.py
python3 scripts/validate-automation.py
node scripts/validate-tiktok.cjs
```

Testele folosesc API simulat și date temporare; nu publică nimic. Au fost verificate rotația pe conturi/zile, ofertele noi, evitarea duplicatelor, oprirea, expirarea și istoricul, sintaxa TypeScript/JavaScript și comportamentul upload-only TikTok. Build-ul complet Nest/Next și publicarea reală se verifică pe server după instalarea dependențelor.


## Muzică în clipurile Facebook

Configurați `FACEBOOK_MUSIC_FILE="/opt/pinfers-postiz/state/music/facebook-house.mp3"` în `config/postiz.env`, apoi reporniți serviciile PM2. Fișierul MP3 se transferă separat pe server. Nu este inclus în repository-ul public, deoarece licența Pixabay nu permite redistribuirea piesei ca fișier de sine stătător.

Piesa aleasă: **House Energetic Upbeat**, PaulYudin / Pavel Bekirov, https://pixabay.com/music/edm-house-energetic-upbeat-456608/. Licența: https://pixabay.com/service/terms/. Piesa este marcată Content ID Registered. Dovada descărcării se păstrează separat; certificatul de licență poate fi descărcat după autentificarea în Pixabay.

Copiile Facebook existente se refac în fundal cu muzica inclusă, la 65% din nivelul piesei și cu fade la început/sfârșit. Originalul TikTok nu este modificat. Dacă fișierul configurat lipsește, varianta Facebook nu este considerată gata; nu se produce intenționat o copie fără muzică.

Când noua copie este gata, automatizarea înlocuiește doar propriile programări Facebook viitoare, aflate la peste 5 minute distanță, care folosesc versiunea veche. Publicările confirmate rămân în istoric; clipurile deja publicate și programările prea apropiate nu sunt modificate. Cache-ul media Postiz este invalidat pe baza versiunii fișierului. Migrarea SQLite adaugă două coloane, fără să șteargă date.

Verificare audio locală: `python3 scripts/validate-facebook-audio.py`. Nu este necesar build Nest/Next pentru această actualizare Python.
