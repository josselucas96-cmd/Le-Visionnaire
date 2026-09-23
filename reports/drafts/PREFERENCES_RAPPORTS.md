# Préférences de rédaction : rapports mensuels

À lire avant de rédiger un commentaire. À compléter au fil des retours.
Dernière mise à jour : 23/09/2026.

## Langue et ton

- Rapports et posts LinkedIn en anglais.
- Ton neutre et professionnel. Pas d'emphase, pas d'effet de style.
- Phrases simples, de longueur moyenne. Pas de phrases courtes « choc » en fin de paragraphe.
- Jamais d'autocritique, jamais de prétention.
- Pas d'intertitres en gras (« Construction discipline », « Positioning », etc.).
- À éviter : le tiret cadratin (—), la tournure « not X but Y », les énumérations par trois pour l'effet, les phrases méta (« nothing here should be read as… »).

## Contenu du commentaire de gestion

1. Performance du mois contre l'indice, en %, et l'écart en points. Le cash en % seulement.
2. Transactions :
   - s'il n'y en a pas : « No transactions were made during the month. » et rien d'autre ;
   - jamais de prix ;
   - vente totale : donner le % réalisé depuis l'entrée ;
   - réduction, achat ou renforcement : simplement le dire.
3. Les mouvements importants : les un ou deux titres qui ont nettement surperformé ou sous-performé, avec la raison vérifiée (résultats, procès, annonce…).
4. Si l'écart avec l'indice est notable, l'expliquer après analyse : quelles lignes l'ont créé (en points), ou quelle exposition l'indice avait et pas nous (secteur, grosse valeur non détenue).

## À ne pas mettre

- La NAV en dollars.
- Du remplissage quand il ne s'est rien passé.

## Méthode

- `python scripts/explain_month.py --month AAAA-MM` : décomposition de l'écart par ligne et par secteur, secteurs de l'indice, grosses valeurs non détenues.
- Le benchmark est toujours mesuré sur la même période que le portefeuille (mois de lancement : depuis la veille du lancement, pas le mois calendaire).
- Toute raison citée est vérifiée en source, jamais de mémoire.
- Un rapport déjà publié ne se retouche pas.

## Historique des retours

- 23/09/2026 : version 1 rejetée (style IA) ; version 2 rejetée (trop de style) ; version 3 : pas de NAV, pas de prix de transaction, % depuis l'entrée pour les ventes, écarts expliqués.
