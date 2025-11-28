import pandas as pd
import sqlite3
from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.metrics import (
    confusion_matrix, precision_score, recall_score, f1_score, roc_auc_score
)
import matplotlib.pyplot as plt
import seaborn as sns
import os

DB_PATH = "data/news.db"

def entrenar_y_evaluar():
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"No se encontró la base de datos: {DB_PATH}")

    # 🔹 Conexión a la base de datos SQLite
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 🔹 Detectar tablas disponibles
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tablas = [t[0] for t in cursor.fetchall()]
    if not tablas:
        raise ValueError("No hay tablas en la base de datos.")

    print(f"🔍 Tablas encontradas: {tablas}")

    # 🔹 Intentar detectar la tabla que contiene noticias
    tabla_objetivo = None
    for t in tablas:
        if any(k in t.lower() for k in ["news", "article", "noticia"]):
            tabla_objetivo = t
            break

    if not tabla_objetivo:
        raise ValueError("No se encontró una tabla que parezca contener noticias.")

    # 🔹 Leer la tabla y detectar columnas
    df = pd.read_sql_query(f"SELECT * FROM {tabla_objetivo}", conn)
    conn.close()

    print(f"📋 Columnas disponibles: {list(df.columns)}")

    # 🔹 Detectar columnas de título, contenido y categoría
    posibles_titulos = [c for c in df.columns if c.lower() in ["title", "titulo", "headline"]]
    posibles_contenidos = [c for c in df.columns if c.lower() in ["content", "contenido", "texto"]]
    posibles_categorias = [c for c in df.columns if c.lower() in ["category", "categoria", "label"]]

    if not posibles_titulos or not posibles_contenidos:
        raise ValueError("No se encontraron columnas de título o contenido en la base de datos.")

    if not posibles_categorias:
        raise ValueError("No se encontró ninguna columna de categoría en la base de datos.")

    title_col = posibles_titulos[0]
    content_col = posibles_contenidos[0]
    category_col = posibles_categorias[0]

    # 🔹 Combinar texto
    df["texto"] = df[title_col].fillna('') + " " + df[content_col].fillna('')

    # 🔹 Verificar categorías
    df = df.dropna(subset=[category_col])
    if df[category_col].nunique() < 2:
        raise ValueError("No hay suficientes categorías distintas para entrenar el modelo.")

    # 🔹 Vectorización
    vectorizer = TfidfVectorizer(stop_words="spanish", max_features=5000)
    X_vec = vectorizer.fit_transform(df["texto"])
    y = df[category_col]

    # 🔹 División entrenamiento/prueba
    X_train, X_test, y_train, y_test = train_test_split(X_vec, y, test_size=0.2, random_state=42, stratify=y)

    # 🔹 Entrenamiento del modelo
    model = MultinomialNB()
    model.fit(X_train, y_train)

    # 🔹 Predicciones y métricas
    y_pred = model.predict(X_test)
    cm = confusion_matrix(y_test, y_pred, labels=y.unique())
    precision = precision_score(y_test, y_pred, average="weighted", zero_division=0)
    recall = recall_score(y_test, y_pred, average="weighted", zero_division=0)
    f1 = f1_score(y_test, y_pred, average="weighted", zero_division=0)

    # 🔹 ROC-AUC (opcional para multiclase)
    auc = None
    try:
        y_prob = model.predict_proba(X_test)
        auc = roc_auc_score(pd.get_dummies(y_test), y_prob, average="weighted", multi_class="ovr")
    except Exception:
        pass

    # 🔹 Guardar matriz de confusión
    os.makedirs("data/metrics", exist_ok=True)
    plt.figure(figsize=(8, 6))
    sns.heatmap(cm, annot=True, fmt="d", cmap="Blues", xticklabels=y.unique(), yticklabels=y.unique())
    plt.title("Matriz de Confusión")
    plt.xlabel("Predicción")
    plt.ylabel("Real")
    plt.tight_layout()
    plt.savefig("data/metrics/confusion_matrix.png")
    plt.close()

    print("✅ Entrenamiento completado correctamente.")

    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "auc": auc,
        "image": "/images/confusion_matrix.png"
    }

# 🔹 Ejemplo de ejecución
if __name__ == "__main__":
    resultados = entrenar_y_evaluar()
    print(resultados)
