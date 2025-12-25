import json

# Widget для SQL
dbutils.widgets.text("sql_text", "")

sql_text = dbutils.widgets.get("sql_text")

# Базова валідація
sql_text_lower = sql_text.strip().lower()
assert sql_text_lower.startswith("select"), "Only SELECT queries allowed"

try:
    # Виконання SQL
    df = spark.sql(sql_text)
    
    # Відображення для debugging в Databricks UI
    display(df)
    
    # Конвертація результатів в JSON для повернення
    # Обмеження до 1000 рядків для безпеки
    results_json = df.limit(1000).toJSON().collect()
    
    # Парсинг JSON рядків в Python об'єкти
    results_list = [json.loads(row) for row in results_json]
    
    # Повернення результатів через notebook output
    # Це дозволить Azure Functions отримати дані через Jobs API
    dbutils.notebook.exit(json.dumps(results_list, ensure_ascii=False))
    
except Exception as e:
    # Повернення помилки через notebook output
    error_result = {
        "error": str(e),
        "error_type": type(e).__name__
    }
    dbutils.notebook.exit(json.dumps(error_result, ensure_ascii=False))