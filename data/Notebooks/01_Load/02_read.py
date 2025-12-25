# Шляхи до IMDb файлів
path_title_basics     = f"{raw_root}/title.basics.tsv.gz"
path_title_ratings    = f"{raw_root}/title.ratings.tsv.gz"
path_name_basics      = f"{raw_root}/name.basics.tsv.gz"
path_title_principals = f"{raw_root}/title.principals.tsv.gz"

common_read_opts = {
    "header": "true",
    "sep": "\t",
    "quote": "\u0000"
}

df_title_basics_raw = spark.read.options(**common_read_opts).csv(path_title_basics)
df_title_ratings_raw = spark.read.options(**common_read_opts).csv(path_title_ratings)
df_name_basics_raw = spark.read.options(**common_read_opts).csv(path_name_basics)
df_title_principals_raw = spark.read.options(**common_read_opts).csv(path_title_principals)

df_movies = (
    df_title_basics_raw
        .na.replace("\\N", None)
        .withColumn("startYear",      col("startYear").cast("int"))
        .withColumn("endYear",        col("endYear").cast("int"))
        .withColumn("runtimeMinutes", col("runtimeMinutes").cast("int"))
        .withColumn("genres", split(col("genres"), ","))
        .select(
            "tconst",
            "titleType",
            "primaryTitle",
            "originalTitle",
            "isAdult",
            "startYear",
            "endYear",
            "runtimeMinutes",
            "genres"
        )
)

movies_delta_path = f"{lake_root}/delta/movies_delta"

(
    df_movies
        .write
        .format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .save(movies_delta_path)
)

# ratings_delta
df_ratings = (
    df_title_ratings_raw
        .na.replace("\\N", None)
        .withColumn("averageRating", col("averageRating").cast("double"))
        .withColumn("numVotes",      col("numVotes").cast("int"))
        .select("tconst", "averageRating", "numVotes")
)

ratings_delta_path = f"{lake_root}/delta/ratings_delta"

(
    df_ratings
        .write
        .format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .save(ratings_delta_path)
)

# persons_delta
df_persons = (
    df_name_basics_raw
        .na.replace("\\N", None)
        .withColumn("birthYear",   col("birthYear").cast("int"))
        .withColumn("deathYear",   col("deathYear").cast("int"))
        .withColumn("primaryProfession", split(col("primaryProfession"), ","))
        .withColumn("knownForTitles",    split(col("knownForTitles"), ","))
        .select(
            "nconst",
            "primaryName",
            "birthYear",
            "deathYear",
            "primaryProfession",
            "knownForTitles"
        )
)

persons_delta_path = f"{lake_root}/delta/persons_delta"

(
    df_persons
        .write
        .format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .save(persons_delta_path)
)

# principals_delta
df_principals = (
    df_title_principals_raw
        .na.replace("\\N", None)
        .withColumn("ordering", col("ordering").cast("int"))
        .select(
            "tconst",
            "ordering",
            "nconst",
            "category",
            "job",
            "characters"
        )
)

principals_delta_path = f"{lake_root}/delta/principals_delta"

(
    df_principals
        .write
        .format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .save(principals_delta_path)
)
