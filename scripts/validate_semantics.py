#!/usr/bin/env python3
"""Synthetic NRQL aggregation counterexamples; does not execute NRQL."""
import sqlite3
import unittest


class CommonSemantics(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.addCleanup(self.db.close)
        self.db.executescript("""
            CREATE TABLE logs(service, severity, trace_id);
            INSERT INTO logs VALUES
              ('a', 'ERROR', 't1'), ('a', 'INFO', 't1'), ('a', 'INFO', 't1'),
              ('b', 'ERROR', 't2'), ('b', 'ERROR', 't3');
        """)

    def test_combined_aggregates_preserve_results(self):
        expressions = ["COUNT(*)", "COUNT(DISTINCT trace_id)"]
        individual = [self.db.execute('SELECT '+e+' FROM logs').fetchone()[0] for e in expressions]
        combined = self.db.execute('SELECT '+', '.join(expressions)+' FROM logs').fetchone()
        self.assertEqual(tuple(individual), combined)
        self.assertEqual(combined, (5, 3))

    def test_filter_must_not_change_denominator(self):
        correct = self.db.execute("SELECT SUM(severity='ERROR')*100.0/COUNT(*) FROM logs").fetchone()[0]
        wrong = self.db.execute("SELECT SUM(severity='ERROR')*100.0/COUNT(*) FROM logs WHERE severity='ERROR'").fetchone()[0]
        self.assertEqual((correct, wrong), (60.0, 100.0))

    def test_facet_rankings_can_differ(self):
        by_count = self.db.execute('SELECT service FROM logs GROUP BY service ORDER BY COUNT(*) DESC LIMIT 1').fetchone()[0]
        by_traces = self.db.execute('SELECT service FROM logs GROUP BY service ORDER BY COUNT(DISTINCT trace_id) DESC LIMIT 1').fetchone()[0]
        self.assertEqual((by_count, by_traces), ('a', 'b'))

    def test_missing_population_is_not_zero_percent(self):
        value = self.db.execute("SELECT SUM(severity='ERROR')*100.0/COUNT(*) FROM logs WHERE service='missing'").fetchone()[0]
        self.assertIsNone(value)


if __name__ == '__main__':
    unittest.main(verbosity=2)
