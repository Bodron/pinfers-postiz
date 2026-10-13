# Content Pinfers în Postiz local

Deschide https://pinferspostiz.bcmenu.ro/media după autentificarea în Postiz.

38 oferte distincte și 182 variante ofertă–locație în snapshot-ul inițial. Logo-ul și clipul sunt separate pentru fiecare locație. Catalogul este preluat numai prin GET din API-ul public Pinfers; MongoDB și proiectul Pinfers nu sunt modificate.

## Ce funcționează
- Biblioteca, căutarea, selecția locației, previzualizarea și descrierea provizorie.
- Generarea variantelor și importul în Media prin API-ul autentificat Postiz.
- Istoric de publicări confirmate, legat prin ID-urile fișierelor Media.
- Planuri locale repetate per cont, cu date în Europe/Bucharest.
- Propuneri de rotație pe conturi, pe baza numărului și datei publicărilor.

## Limita curentă
Conturile sociale nu sunt încă conectate. Planurile sunt locale și nu sunt trimise automat pentru publicare. Template-ul descrierii și integrarea muzicii rămân de stabilit. Postările sunt numărate ca publicate numai când Postiz raportează PUBLISHED.

Butonul Actualizează ofertele citește din nou catalogul; clipurile schimbate intră în coadă. Importă clipurile în Media încarcă variantele gata prin sesiunea utilizatorului. Nu există acces direct la volumul de uploads. Variantele vechi importate anterior sunt păstrate în Media originală; Content Pinfers folosește asocierea curentă.

## Pornire
În acest repository modulul pornește prin PM2. Datele SQLite și clipurile sunt în LIBRARY_DATA_DIR (implicit state/ în configurația serverului), separat de sursa versionată. Vezi README.md din rădăcină pentru pașii de instalare. Biblioteca originală Postiz este accesibilă la /media?native=1.

Nginx direcționează /media și /pinfers/ către modulul Python; fișierul nginx-site.conf se include într-un vhost separat. Biblioteca verifică autentificarea prin /api/user/self, nu păstrează parole și nu generează chei API. Secretele Pinfers nu sunt copiate.
