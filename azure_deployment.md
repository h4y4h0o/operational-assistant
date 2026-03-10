# Déploiement Azure — Architecture cible

## Vue d'ensemble

```
Internet
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│                    Azure (Resource Group: ops-rg)           │
│                                                             │
│  ┌──────────────┐     ┌──────────────┐   ┌──────────────┐  │
│  │   Azure      │     │   AKS        │   │   Azure      │  │
│  │   Container  │────►│  (Kubernetes)│   │   Database   │  │
│  │   Registry   │     │              │   │   PostgreSQL  │  │
│  │   (images)   │     │  ┌────────┐  │   │              │  │
│  └──────────────┘     │  │  API   │  │──►│  flights     │  │
│                       │  │  Pod   │  │   │  incidents   │  │
│  ┌──────────────┐     │  └────────┘  │   │  ai_insights │  │
│  │   Azure Key  │     │  ┌────────┐  │   └──────────────┘  │
│  │   Vault      │────►│  │  n8n   │  │                     │
│  │  (secrets)   │     │  │  Pod   │  │                     │
│  └──────────────┘     │  └────────┘  │                     │
│                       └──────────────┘                     │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Azure Virtual Network (VNet) — tout est isolé       │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## Les 4 services Azure utilisés

### 1. Azure Database for PostgreSQL (Flexible Server)

**Rôle :** Héberge les 3 tables (flights, incidents, ai_insights)

**Pourquoi Flexible Server ?**
- Scalable automatiquement (CPU/RAM à la demande)
- Backups automatiques toutes les heures
- Pas besoin de gérer le serveur Postgres manuellement

**Configuration minimale (prototype) :**
```
SKU       : Standard_B1ms (1 vCore, 2GB RAM)
Storage   : 32 GB SSD
Backup    : 7 jours de rétention
SSL       : obligatoire (enforce_ssl = ON)
Réseau    : accessible uniquement depuis le VNet privé (pas d'IP publique)
```

**Variables d'environnement générées :**
```
POSTGRES_HOST     = ops-postgres.postgres.database.azure.com
POSTGRES_DB       = opsdb
POSTGRES_USER     = opsadmin
POSTGRES_PASSWORD = → stocké dans Azure Key Vault (jamais en clair)
POSTGRES_PORT     = 5432
```

---

### 2. Azure Kubernetes Service (AKS)

**Rôle :** Orchestre les conteneurs Docker (API + n8n)

**Pourquoi Kubernetes pour un prototype ?**
- Redémarrage automatique si un pod plante
- Mise à jour sans interruption (rolling update)
- Scalabilité horizontale (ajouter des pods sous charge)

**Structure des pods :**

```yaml
# Deployment de l'API
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ops-api
spec:
  replicas: 2                  # 2 instances pour la haute disponibilité
  selector:
    matchLabels:
      app: ops-api
  template:
    spec:
      containers:
      - name: ops-api
        image: opsregistry.azurecr.io/ops-api:1.0.0
        ports:
        - containerPort: 8000
        env:
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: ops-secrets    # Secret Kubernetes (alimenté depuis Key Vault)
              key: postgres-password
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 30
```

```yaml
# Deployment de n8n
apiVersion: apps/v1
kind: Deployment
metadata:
  name: n8n
spec:
  replicas: 1                  # n8n ne scale pas horizontalement (état local)
  template:
    spec:
      containers:
      - name: n8n
        image: n8nio/n8n:latest
        ports:
        - containerPort: 5678
        env:
        - name: N8N_ENCRYPTION_KEY
          valueFrom:
            secretKeyRef:
              name: ops-secrets
              key: n8n-encryption-key
        - name: DB_TYPE
          value: "postgresdb"
        volumeMounts:
        - name: n8n-data
          mountPath: /home/node/.n8n   # Persistance des workflows
      volumes:
      - name: n8n-data
        persistentVolumeClaim:
          claimName: n8n-pvc           # Azure Disk pour la persistance
```

---

### 3. Azure Container Registry (ACR)

**Rôle :** Stocke les images Docker construites

```bash
# Construire et pousser l'image
docker build -t ops-api:1.0.0 .
docker tag ops-api:1.0.0 opsregistry.azurecr.io/ops-api:1.0.0
docker push opsregistry.azurecr.io/ops-api:1.0.0

# AKS pull automatiquement depuis ACR (même Resource Group = accès natif)
```

---

### 4. Azure Key Vault

**Rôle :** Centralise TOUS les secrets (mots de passe, tokens, clés API)

```
Azure Key Vault : ops-keyvault
├── postgres-password     → mot de passe Postgres
├── n8n-encryption-key    → clé de chiffrement n8n
├── api-bearer-token      → token d'auth de l'API
├── slack-bot-token       → token Slack
└── llm-api-key           → clé Claude/OpenAI
```

Les pods Kubernetes accèdent à Key Vault via **Managed Identity** :
- Aucun secret dans le code
- Aucun secret dans les variables d'environnement en clair
- Rotation automatique des secrets possible

---

## Réponse à la question : Secrets & Redéploiement

### Où stocker les secrets ?

```
DEV      → fichier .env local (jamais commité, dans .gitignore)
STAGING  → Kubernetes Secrets (chiffrés dans etcd)
PROD     → Azure Key Vault (chiffré, audité, rotation automatique)
```

**Règle d'or :** Un secret ne doit JAMAIS apparaître dans :
- Le code source
- Les Dockerfiles
- Les fichiers de workflow n8n exportés
- Les logs applicatifs

### Que se passe-t-il lors d'un redéploiement ?

**Avec AKS rolling update (stratégie par défaut) :**

```
Avant : [Pod v1.0] [Pod v1.0]
                              ↓ kubectl apply (v1.1)
Pendant: [Pod v1.0] [Pod v1.1]   ← les 2 coexistent brièvement
                              ↓ santé de v1.1 confirmée
Après : [Pod v1.1] [Pod v1.1]   ← aucune interruption de service
```

1. AKS lance le nouveau pod (v1.1)
2. Attend que le health check `/health` réponde 200
3. Seulement alors, coupe l'ancien pod (v1.0)
4. **Zéro downtime** pour les utilisateurs

**Les données Postgres ?**
- Ne sont jamais affectées par un redéploiement de l'API
- Les migrations SQL sont exécutées via un **init container** avant le démarrage

**Les workflows n8n ?**
- Stockés dans la base Postgres de n8n (sur Azure Disk)
- Persistent même si le pod n8n redémarre
