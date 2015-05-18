import os
import sqlite3 as lite
import contextlib
import logging
import re

import pg8000

__all__ = ['connect_openwisdb', 'connect_wismondb',
           'sql_schema_wismon_metadata',
           'sql_query_to_openwis', 'sql_save_snapshot',
           'sql_global_stats', 'sql_amdcn_stats',
           'sql_md_total_GISC_specific', 'sql_md_insert_modify', 'sql_md_deleted',
           'sql_json_get', 'sql_json_del', 'sql_save_json',
           'sql_event_add', 'sql_event_get', 'sql_event_del',
           'sql_remarks_set', 'sql_remarks_get']


sql_schema_wismon_metadata = """
CREATE TABLE wismon_metadata (
    id integer NOT NULL PRIMARY KEY,
    uuid varchar(255) NOT NULL UNIQUE,
    localimportdate datetime NOT NULL,
    category varchar(32),
    n_mapped_files integer NOT NULL,
    cache_size_bytes integer NOT NULL,
    is_stopgap bool NOT NULL,
    createdate datetime NOT NULL,
    owner varchar(255),
    timestamp datetime DEFAULT CURRENT_TIMESTAMP
);"""

schema_wismon_rest = """
-- Events
CREATE TABLE wismon_events (
    id integer NOT NULL PRIMARY KEY,
    title varchar(255) NOT NULL,
    text text,
    startdatetime datetime NOT NULL,
    enddatetime datetime NOT NULL,
    timestamp datetime DEFAULT CURRENT_TIMESTAMP
);

-- Remarks
CREATE TABLE wismon_remarks (
    id integer NOT NULL PRIMARY KEY,
    text text NOT NULL,
    timestamp datetime DEFAULT CURRENT_TIMESTAMP
);

-- JSON messages
CREATE TABLE wismon_json (
    id integer NOT NULL PRIMARY KEY,
    date date NOT NULL,
    monitor_json text NOT NULL,
    centres_json text NOT NULL,
    events_json text NOT NULL,
    timestamp datetime DEFAULT CURRENT_TIMESTAMP
);"""

sql_query_to_openwis = """
SELECT
  m.id,
  m.uuid,
  m.localimportdate,
  ct.name    AS category,
  COALESCE(mc.n_mapped_files, 0),
  COALESCE(mc.cache_size_bytes, 0),
  ct.name='draft' AS is_stopgap,
  m.createdate,
  m.owner
FROM metadata m FULL JOIN openwis_product_metadata p
ON m.uuid = p.urn
FULL JOIN (SELECT mm.product_metadata_id, count(*) AS n_mapped_files, CAST(sum(cf.filesize) AS bigint) AS cache_size_bytes
FROM openwis_mapped_metadata mm FULL JOIN openwis_cached_file cf
ON mm.cached_file_id = cf.cached_file_id
GROUP BY mm.product_metadata_id) AS mc
ON p.product_metadata_id = mc.product_metadata_id
FULL JOIN categories ct
ON m.category = ct.id
WHERE m.istemplate='n'
ORDER BY m.id;
"""

sql_save_snapshot = """
INSERT INTO wismon_metadata (id,
                             uuid,
                             localimportdate,
                             category,
                             n_mapped_files,
                             cache_size_bytes,
                             is_stopgap,
                             createdate,
                             owner)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);"""

sql_global_stats = """
SELECT
  count(uuid),
  coalesce(sum(n_mapped_files), 0),
  coalesce(sum(cache_size_bytes), 0),
  is_stopgap
FROM wismon_metadata
GROUP BY is_stopgap
ORDER BY is_stopgap;"""

sql_amdcn_stats = """
SELECT
  count(uuid),
  sum(n_mapped_files),
  sum(cache_size_bytes),
  is_stopgap
FROM wismon_metadata
WHERE %s
GROUP BY is_stopgap
ORDER BY is_stopgap;"""

# Query for number of metadata
sql_md_total_GISC_specific = """
SELECT count(*)
FROM wismon_metadata
WHERE category LIKE 'WIS-GISC-%%' OR category = '%s'
"""

sql_md_insert_modify = """
SELECT count(*)
FROM wismon_metadata m
  LEFT OUTER JOIN old_wismon_metadata o
    ON m.id = o.id
WHERE (o.id IS NULL OR m.localimportdate > o.localimportdate)
AND (m.category like 'WIS-GISC-%%' OR m.category = '%s')
"""

sql_md_deleted = """
SELECT count(*)
FROM old_wismon_metadata o
  LEFT OUTER JOIN wismon_metadata m
    ON o.id = m.id
WHERE m.id IS NULL
AND (o.category LIKE 'WIS-GISC-%%' OR o.category = '%s')"""

sql_json_get = """
SELECT id, monitor_json, centres_json, events_json
FROM wismon_json
WHERE date = ?"""

sql_json_del = """
DELETE FROM wismon_json WHERE date = ?;
"""

sql_save_json = """
INSERT OR REPLACE INTO wismon_json (
  date,
  monitor_json,
  centres_json,
  events_json)
VALUES (?, ?, ?, ?);"""

sql_remarks_set = """
INSERT INTO wismon_remarks (text)
VALUES (?);"""

sql_remarks_get = """
SELECT text
FROM wismon_remarks
ORDER BY id DESC LIMIT 1;"""

sql_event_add = """
INSERT INTO wismon_events (title, text, startdatetime, enddatetime)
VALUES (?, ?, ?, ?);"""

sql_event_get = """
SELECT id, title, text, startdatetime, enddatetime
FROM wismon_events
WHERE enddatetime >= ?;"""

sql_event_del = """
DELETE FROM wismon_events WHERE id = ?;"""


def regexp(expr, item):
    pattern = re.compile(expr, re.IGNORECASE)
    return pattern.search(item) is not None


@contextlib.contextmanager
def connect_wismondb(wismon_db_file):
    logger = logging.getLogger('wismon')

    first_run = not os.path.exists(wismon_db_file)

    logger.info('Connecting to: %s' % wismon_db_file)
    conn = lite.connect(wismon_db_file)

    cursor = conn.cursor()

    if first_run:
        logger.info('Setting up new database file')
        conn.execute(sql_schema_wismon_metadata)
        conn.executescript(schema_wismon_rest)

    # Case-insensitive regex
    conn.create_function('REGEXP', 2, regexp)

    yield conn, cursor, first_run

    logger.info('Disconnecting from %s' % wismon_db_file)
    cursor.close()
    conn.close()


@contextlib.contextmanager
def connect_openwisdb(host='', port=5432, database='OpenWIS', user=None, password=None):
    logger = logging.getLogger('wismon')

    logger.info('Connecting to %s' % host)
    conn = pg8000.connect(host=host,
                          port=port,
                          database=database,
                          user=user,
                          password=password)
    cursor = conn.cursor()

    yield conn, cursor

    logger.info('Disconnecting from %s' % host)
    cursor.close()
    conn.close()
