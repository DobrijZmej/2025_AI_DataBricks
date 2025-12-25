spark.sql(f"CREATE DATABASE IF NOT EXISTS {database_name}")

spark.sql(f"""
  CREATE TABLE IF NOT EXISTS {database_name}.movies_delta
  USING DELTA
  LOCATION '{movies_delta_path}'
""")

spark.sql(f"""
  CREATE TABLE IF NOT EXISTS {database_name}.ratings_delta
  USING DELTA
  LOCATION '{ratings_delta_path}'
""")

spark.sql(f"""
  CREATE TABLE IF NOT EXISTS {database_name}.persons_delta
  USING DELTA
  LOCATION '{persons_delta_path}'
""")

spark.sql(f"""
  CREATE TABLE IF NOT EXISTS {database_name}.principals_delta
  USING DELTA
  LOCATION '{principals_delta_path}'
""")

spark.sql(f"""
  CREATE OR REPLACE VIEW {database_name}.movies_with_ratings AS
  SELECT
      m.tconst,
      m.primaryTitle,
      m.originalTitle,
      m.titleType,
      m.isAdult,
      m.startYear,
      m.endYear,
      m.runtimeMinutes,
      m.genres,
      r.averageRating,
      r.numVotes
  FROM {database_name}.movies_delta m
  LEFT JOIN {database_name}.ratings_delta r
    ON m.tconst = r.tconst
""")

spark.sql(f"""
  CREATE OR REPLACE VIEW {database_name}.movie_cast AS
  SELECT
      pr.tconst,
      m.primaryTitle,
      pr.nconst,
      pe.primaryName,
      pr.category,
      pr.job,
      pr.characters
  FROM {database_name}.principals_delta pr
  LEFT JOIN {database_name}.movies_delta m
    ON pr.tconst = m.tconst
  LEFT JOIN {database_name}.persons_delta pe
    ON pr.nconst = pe.nconst
""")
