from openai import AzureOpenAI

storage_key = dbutils.secrets.get("imdb-scope", "storage-key-imdblakehouse")

spark.conf.set(
    "fs.azure.account.key.imdblakehouse.dfs.core.windows.net",
    storage_key
)

AZURE_OPENAI_ENDPOINT = dbutils.secrets.get(
    "imdb-scope", "azure-openai-endpoint"
)
AZURE_OPENAI_KEY = dbutils.secrets.get(
    "imdb-scope", "azure-openai-key"
)
AZURE_OPENAI_DEPLOYMENT = dbutils.secrets.get(
    "imdb-scope", "azure-openai-deployment"
)


def summarize_movie(
    title: str,
    endpoint: str,
    api_key: str,
    deployment: str
) -> str:
    if title is None:
        return None

    client = AzureOpenAI(
        api_key=api_key,
        api_version="2024-12-01-preview",
        azure_endpoint=endpoint
    )

    response = client.chat.completions.create(
        model=deployment,
        messages=[
            {"role": "system", "content": "You summarize movies in one sentence."},
            {"role": "user", "content": f"Describe the movie {title} in one sentence."}
        ]
    )
    return response.choices[0].message.content

from pyspark.sql.functions import udf
from pyspark.sql.types import StringType

summarize_movie_udf = udf(
    lambda title: summarize_movie(
        title,
        AZURE_OPENAI_ENDPOINT,
        AZURE_OPENAI_KEY,
        AZURE_OPENAI_DEPLOYMENT
    ),
    StringType()
)

spark.udf.register("ai_movie_summary", summarize_movie_udf)