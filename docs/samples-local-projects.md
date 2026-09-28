# Projets locaux de samples

Le travail est conservé dans `~/.rx3-toolbox/sample-projects/` : un projet par
chemin de clé et des copies audio nommées par leur empreinte. Les nouveaux sons
et les pads lus depuis une clé sont copiés sur cet ordinateur. Le projet reste
récupérable même si le fichier audio d’origine disparaît. Aucun accès réseau.

Chaque modification est transmise à la sauvegarde locale ; les requêtes sont
sérialisées et les dernières modifications regroupées. Une copie immédiate dans
le stockage du navigateur protège les changements en attente. L’interface
distingue sauvegarde en cours, sauvegarde locale réussie, échec et état envoyé
sur la clé. Un échec propose Réessayer et empêche de changer de clé avant la
sauvegarde locale. Les projets se retrouvent en sélectionnant le même chemin ;
un changement de nom de volume n’est pas identifié automatiquement.

La création, le changement de banque, le nom, les pads, le volume, SHIFT, la
suppression et la banque active restent locaux. « Enregistrer sur la clé USB »
envoie toutes les banques modifiées, sélectionne l’active puis applique les
suppressions. La modification des samples est suspendue pendant cet envoi.
La sauvegarde locale n’est déclarée synchronisée qu’après succès complet.
L’écriture est protégée banque par banque par le service existant ; un échec
entre deux banques peut laisser un export partiel, signalé comme non synchronisé.
Le projet reste intact pour réessayer. Les copies audio locales sont conservées.

Validation : `test_sample_drafts.py`, `samples_drafts.cjs`, tests des banques
et de préécoute existants ; parcours synthétique pywebview ciblé dans `verify_samples.py`.
