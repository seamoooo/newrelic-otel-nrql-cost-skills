#!/usr/bin/env python3
"""Synthetic aggregation counterexamples; does not execute NRQL or an agent."""
import sqlite3
import unittest


class OTelSemantics(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.addCleanup(self.db.close)
        self.db.executescript('''
            CREATE TABLE metrics(bucket, entity, service, observations, seconds_sum, error_type);
            INSERT INTO metrics VALUES
              (0, 'otel-prod', 'checkout', 90, 18.0, NULL),
              (0, 'otel-prod', 'checkout', 10, 8.0, 'timeout'),
              (1, 'otel-prod', 'checkout', 20, 6.0, NULL),
              (0, 'agent-prod', 'checkout', 100, 26.0, NULL),
              (0, 'otel-staging', 'checkout', 7, 14.0, NULL);
            CREATE TABLE spans(kind, parent, duration_ms, status);
            INSERT INTO spans VALUES
              ('server', NULL, 200, 'OK'),
              ('server', 'upstream', 800, 'ERROR'),
              ('client', 'local', 100, 'ERROR'),
              ('internal', 'local', 30, 'OK');
            CREATE TABLE logs(severity_text, message);
            INSERT INTO logs VALUES ('ERROR', 'timeout'), ('FATAL', 'crash'), ('INFO', 'ready');
        ''')

    def rows(self, sql):
        return self.db.execute(sql).fetchall()

    def test_combined_histogram_aggregation_matches_separate_queries(self):
        # Model count(metric), rate(..., 1 minute), average(metric), filtered error rate.
        scope = "FROM metrics WHERE entity = 'otel-prod' GROUP BY bucket ORDER BY bucket"
        expressions = ['SUM(observations)', 'SUM(observations) / 5.0',
                       'SUM(seconds_sum) / SUM(observations)',
                       '100.0 * SUM(CASE WHEN error_type IS NOT NULL THEN observations ELSE 0 END) / SUM(observations)']
        separate = [self.rows('SELECT bucket, ' + expr + ' ' + scope) for expr in expressions]
        combined = self.rows('SELECT bucket, ' + ', '.join(expressions) + ' ' + scope)
        for index, results in enumerate(separate, 1):
            self.assertEqual(results, [(row[0], row[index]) for row in combined])
        self.assertEqual(combined, [(0, 100, 20.0, 0.26, 10.0), (1, 20, 4.0, 0.3, 0.0)])

    def test_histogram_average_must_be_weighted(self):
        weighted, naive = self.rows("SELECT SUM(seconds_sum)/SUM(observations), AVG(seconds_sum/observations) FROM metrics WHERE entity='otel-prod' AND bucket=0")[0]
        self.assertAlmostEqual(weighted, 0.26)
        self.assertAlmostEqual(naive, 0.5)
        self.assertNotEqual(weighted, naive)

    def test_generated_apm_duration_cannot_assume_seconds(self):
        # Same population expressed in seconds and milliseconds by two source versions.
        seconds = self.rows("SELECT SUM(seconds_sum)/SUM(observations) FROM metrics WHERE entity='otel-prod' AND bucket=0")[0][0]
        milliseconds = self.rows("SELECT SUM(seconds_sum*1000)/SUM(observations) FROM metrics WHERE entity='otel-prod' AND bucket=0")[0][0]
        self.assertAlmostEqual(milliseconds, 260)
        self.assertAlmostEqual(milliseconds / 1000, seconds)
        self.assertNotEqual(milliseconds, seconds)

    def test_span_event_join_uses_span_id_and_trace_id(self):
        self.db.executescript("""
            CREATE TABLE span_identity(trace_id, id);
            CREATE TABLE span_events(trace_id, span_id, name);
            INSERT INTO span_identity VALUES ('trace-a', 'span-1');
            INSERT INTO span_events VALUES
              ('trace-a', 'span-1', 'exception'),
              ('trace-b', 'span-1', 'exception'),
              ('trace-a', 'span-2', 'exception');
        """)
        self.assertEqual(self.rows('SELECT COUNT(*) FROM span_identity s JOIN span_events e ON s.id=e.span_id AND s.trace_id=e.trace_id'), [(1,)])
        self.assertEqual(self.rows('SELECT COUNT(*) FROM span_identity s JOIN span_events e ON s.id=e.span_id'), [(2,)])

    def test_wrong_denominator_and_point_count_change_results(self):
        self.assertEqual(self.rows("SELECT COUNT(*), SUM(observations) FROM metrics WHERE entity='otel-prod' AND bucket=0"), [(2, 100)])
        wrong = self.rows("SELECT 100.0 * SUM(observations) / SUM(observations) FROM metrics WHERE entity='otel-prod' AND bucket=0 AND error_type IS NOT NULL")
        self.assertEqual(wrong, [(100.0,)])  # Correct error rate is 10%.

    def test_service_name_alone_double_counts_and_mixes_environments(self):
        self.assertEqual(self.rows("SELECT SUM(observations) FROM metrics WHERE service='checkout' AND bucket=0"), [(207,)])
        self.assertEqual(self.rows("SELECT SUM(observations) FROM metrics WHERE entity='otel-prod' AND bucket=0"), [(100,)])

    def test_spans_root_filter_units_and_population(self):
        self.assertEqual(self.rows("SELECT COUNT(*), AVG(duration_ms), SUM(status='ERROR') FROM spans WHERE kind='server'"), [(2, 500.0, 1)])
        self.assertEqual(self.rows("SELECT COUNT(*) FROM spans WHERE kind='server' AND parent IS NULL"), [(1,)])
        self.assertEqual(self.rows('SELECT COUNT(*) FROM spans'), [(4,)])
        self.assertEqual(self.rows("SELECT AVG(duration_ms)/1000 FROM spans WHERE kind='server'"), [(0.5,)])
        # Observed spans: 2 and 50% error; metric population: 100 and 10% error.

    def test_missing_bucket_is_not_zero_errors(self):
        rows = self.rows('''WITH buckets(bucket) AS (VALUES(0),(1),(2))
            SELECT b.bucket, SUM(m.observations),
              100.0 * SUM(CASE WHEN m.error_type IS NOT NULL THEN m.observations ELSE 0 END) / SUM(m.observations)
            FROM buckets b LEFT JOIN metrics m ON b.bucket=m.bucket AND m.entity='otel-prod'
            GROUP BY b.bucket ORDER BY b.bucket''')
        self.assertEqual(rows, [(0, 100, 10.0), (1, 20, 0.0), (2, None, None)])

    def test_exact_error_text_does_not_include_fatal(self):
        self.assertEqual(self.rows("SELECT message FROM logs WHERE severity_text='ERROR'"), [('timeout',)])
        self.assertEqual(self.rows("SELECT COUNT(*) FROM logs WHERE severity_text IN ('ERROR','FATAL')"), [(2,)])

    def test_db_snapshots_are_not_execution_counts(self):
        self.db.executescript('''
            CREATE TABLE query_samples(scrape, execution_id);
            INSERT INTO query_samples VALUES (0, 'long-query'), (1, 'long-query'), (2, 'long-query');
            CREATE TABLE top_queries(scrape, query_id, calls_delta, duration_ms_delta);
            INSERT INTO top_queries VALUES (0, 'a', 90, 900), (0, 'b', 10, 1000);
        ''')
        self.assertEqual(self.rows('SELECT COUNT(*), COUNT(DISTINCT execution_id) FROM query_samples'), [(3, 1)])
        self.assertEqual(self.rows('SELECT COUNT(*), SUM(calls_delta), SUM(duration_ms_delta)*1.0/SUM(calls_delta), AVG(duration_ms_delta*1.0/calls_delta) FROM top_queries'), [(2, 100, 19.0, 55.0)])
        # Even DISTINCT execution IDs cannot recover short queries never sampled.

    def test_top_n_collection_cannot_be_recovered_by_query_limit(self):
        self.db.executescript('''
            CREATE TABLE db_population(query_id, duration_ms);
            INSERT INTO db_population VALUES ('a', 100), ('b', 90), ('c', 80);
            CREATE TABLE collected_top AS SELECT * FROM db_population ORDER BY duration_ms DESC LIMIT 2;
        ''')
        self.assertEqual(self.rows('SELECT SUM(duration_ms) FROM collected_top LIMIT 5000'), [(190,)])
        self.assertEqual(self.rows('SELECT SUM(duration_ms) FROM db_population'), [(270,)])

    def test_proxy_observation_points_do_not_equal_business_requests(self):
        self.db.executescript('''
            CREATE TABLE proxy_counts(location, requests);
            INSERT INTO proxy_counts VALUES ('frontend', 100), ('backend', 100);
        ''')
        self.assertEqual(self.rows('SELECT SUM(requests) FROM proxy_counts'), [(200,)])
        self.assertEqual(self.rows("SELECT SUM(requests) FROM proxy_counts WHERE location='frontend'"), [(100,)])


if __name__ == '__main__':
    unittest.main(verbosity=2)
