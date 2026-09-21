-- analysis_queries.sql
--
-- Reference queries against a `feedback_daily` table loaded from
-- data/feedback_data.csv (one row per day). Written for a generic
-- ANSI-SQL / Redshift-style engine -- the kind of thing a Business
-- Analyst would be asked to write or talk through in an Amazon BA
-- interview (SQL is a core bar-raiser topic for that loop).
--
-- Suggested DDL to load the CSV, if you want to run these for real
-- (e.g. in SQLite, Redshift, Postgres, or BigQuery):
--
-- CREATE TABLE feedback_daily (
--   date DATE,
--   total_feedback INT,
--   positive INT,
--   negative INT,
--   neutral INT,
--   avg_recognition_accuracy NUMERIC,
--   avg_resolution_time_hours NUMERIC,
--   uploads_processed INT,
--   cat__blurry_low_res INT,
--   cat__false_positive_tag INT,
--   cat__missed_object INT,
--   cat__wrong_label INT,
--   cat__duplicate_upload INT,
--   cat__slow_processing INT,
--   cat__upload_failed INT,
--   cat__correct_result INT,
--   region__NA INT,
--   region__EU INT,
--   region__APAC INT,
--   region__LATAM INT
-- );


-- 1. Weekly negative feedback rate, with week-over-week change.
-- (The single most common "so what changed" question a BA gets asked.)
WITH weekly AS (
  SELECT
    DATE_TRUNC('week', date)                    AS week_start,
    SUM(negative)                                AS negative_feedback,
    SUM(total_feedback)                          AS total_feedback,
    SUM(negative)::NUMERIC / NULLIF(SUM(total_feedback), 0) AS negative_rate
  FROM feedback_daily
  GROUP BY 1
)
SELECT
  week_start,
  total_feedback,
  negative_feedback,
  ROUND(negative_rate * 100, 2)                          AS negative_rate_pct,
  ROUND((negative_rate - LAG(negative_rate) OVER (ORDER BY week_start)) * 100, 2)
                                                          AS pct_point_change_wow
FROM weekly
ORDER BY week_start;


-- 2. Which feedback categories are driving negative sentiment, ranked.
SELECT
  category,
  SUM(volume) AS total_volume,
  ROUND(100.0 * SUM(volume) / SUM(SUM(volume)) OVER (), 1) AS pct_of_all_feedback
FROM feedback_daily
CROSS JOIN LATERAL (VALUES
  ('Blurry / low-res detection', cat__blurry_low_res),
  ('False positive object tag',  cat__false_positive_tag),
  ('Missed object in image',     cat__missed_object),
  ('Wrong label applied',        cat__wrong_label),
  ('Duplicate upload not caught',cat__duplicate_upload),
  ('Slow processing time',       cat__slow_processing),
  ('Upload failed / crashed',    cat__upload_failed)
) AS c(category, volume)
GROUP BY category
ORDER BY total_volume DESC;


-- 3. Correlation check: does recognition accuracy move with negative rate?
-- (Simple version -- bucket accuracy into bands and compare avg negative rate.)
SELECT
  CASE
    WHEN avg_recognition_accuracy < 85 THEN 'Below 85%'
    WHEN avg_recognition_accuracy < 90 THEN '85-90%'
    WHEN avg_recognition_accuracy < 95 THEN '90-95%'
    ELSE '95%+'
  END                                                   AS accuracy_band,
  COUNT(*)                                               AS days,
  ROUND(AVG(negative::NUMERIC / NULLIF(total_feedback,0)) * 100, 2) AS avg_negative_rate_pct
FROM feedback_daily
GROUP BY 1
ORDER BY 1;


-- 4. Regional feedback mix and where negative sentiment concentrates.
-- (Region columns hold total feedback, not negative-only, in this dataset;
--  shown here as share-of-volume by region -- swap in a negative-only
--  breakdown if/when that's tracked at the row level.)
SELECT
  'NA'    AS region, SUM(region__NA)    AS feedback_volume FROM feedback_daily
UNION ALL
SELECT 'EU',    SUM(region__EU)    FROM feedback_daily
UNION ALL
SELECT 'APAC',  SUM(region__APAC)  FROM feedback_daily
UNION ALL
SELECT 'LATAM', SUM(region__LATAM) FROM feedback_daily
ORDER BY feedback_volume DESC;


-- 5. Resolution-time SLA tracking: % of days above an 8-hour target.
SELECT
  COUNT(*) FILTER (WHERE avg_resolution_time_hours > 8)::NUMERIC
    / NULLIF(COUNT(*), 0) * 100                          AS pct_days_over_sla,
  ROUND(AVG(avg_resolution_time_hours), 2)                AS avg_resolution_hours,
  MAX(avg_resolution_time_hours)                          AS worst_day_hours
FROM feedback_daily;


-- 6. 7-day moving average of positive feedback rate (smooths day-to-day noise
--    for a trend line -- the same math the dashboard's chart is built on).
SELECT
  date,
  ROUND(
    AVG(positive::NUMERIC / NULLIF(total_feedback,0))
      OVER (ORDER BY date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) * 100
  , 2) AS positive_rate_7d_avg
FROM feedback_daily
ORDER BY date;
