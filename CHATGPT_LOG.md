# CHATGPT_LOG.md — Journal d'utilisation de l'IA

> Outils utilisés : Claude (Anthropic) et CHATGPT
> Ce journal documente quelques-uns des prompts réellement utilisés, ce qui a bien fonctionné,
> ce qui a été corrigé, et les décisions où je n'ai PAS suivi l'IA.

---

## Prompt 1

**Prompt envoyé :**

Dans mon workflow n8n, est-ce une bonne idee de parralleliser le chargement de données et leur stockage dans postgres pour flights et incendies?


**Réponse de l'IA :**

Ces deux opérations sont **totalement indépendantes** — il n'existe aucune
relation entre le chargement des vols et le chargement des incidents à ce
stade. Les exécuter en parallèle réduit le temps d'exécution de ~2s à ~1s.

Le node **Merge (Append)** garantit que les deux branches sont terminées
avant de passer à l'analyse IA — évitant ainsi les erreurs de clé étrangère
(un incident référence un flight_id qui doit exister en base).


**Pourquoi je n'ai pas suivi l:IA:**
- En raison du "foreign key constraint" (flight_id), ce parallélisme est incorecte, et il faut d'abord rajouter les flights ensuite les incendits.

---
