# Content Pinfers în Postiz local

Deschide http://localhost:4007/media după autentificarea în Postiz.

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
Modulul pinfers-library pornește cu Docker Compose împreună cu Postiz. Datele și clipurile sunt în acest folder; se păstrează la restart. Biblioteca originală Postiz este accesibilă la /media?native=1.

Configurația Nginx este montată read-only în Postiz. Biblioteca verifică autentificarea prin /api/user/self, nu păstrează parole și nu generează chei API. Secretele Pinfers nu sunt copiate.
