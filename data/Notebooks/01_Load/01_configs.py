from pyspark.sql.functions import col, split

storage_account_name = "imdblakehouse"
raw_container_name   = "imdb-raw"
lake_container_name  = "imdb-lake"

kv_scope  = "imdb-scope"
kv_secret = "storage-key-imdblakehouse"

database_name = "imdb"

storage_key = dbutils.secrets.get(kv_scope, kv_secret)

spark.conf.set(
    f"fs.azure.account.key.{storage_account_name}.blob.core.windows.net",
    storage_key
)
spark.conf.set(
    f"fs.azure.account.key.{storage_account_name}.dfs.core.windows.net",
    storage_key
)

raw_root  = f"wasbs://{raw_container_name}@{storage_account_name}.blob.core.windows.net"
lake_root = f"abfss://{lake_container_name}@{storage_account_name}.dfs.core.windows.net"

print("RAW root :", raw_root)
print("LAKE root:", lake_root)
