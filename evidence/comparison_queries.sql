-- portfolio
SELECT version, 'All' AS cohort, COUNT(*) AS series_count,
 SUM(demand) AS demand, SUM(cost) AS holding_cost,
 SUM(served) / NULLIF(SUM(demand), 0) AS unit_fill,
 SUM(stockouts) AS stockout_weeks, SUM(backlog) AS end_backlog
 FROM outcomes GROUP BY version, 'All' ORDER BY version, cohort;

-- site
SELECT version, site AS cohort, COUNT(*) AS series_count,
 SUM(demand) AS demand, SUM(cost) AS holding_cost,
 SUM(served) / NULLIF(SUM(demand), 0) AS unit_fill,
 SUM(stockouts) AS stockout_weeks, SUM(backlog) AS end_backlog
 FROM outcomes GROUP BY version, site ORDER BY version, cohort;

-- criticality
SELECT version, criticality AS cohort, COUNT(*) AS series_count,
 SUM(demand) AS demand, SUM(cost) AS holding_cost,
 SUM(served) / NULLIF(SUM(demand), 0) AS unit_fill,
 SUM(stockouts) AS stockout_weeks, SUM(backlog) AS end_backlog
 FROM outcomes GROUP BY version, criticality ORDER BY version, cohort;

-- family
SELECT version, family AS cohort, COUNT(*) AS series_count,
 SUM(demand) AS demand, SUM(cost) AS holding_cost,
 SUM(served) / NULLIF(SUM(demand), 0) AS unit_fill,
 SUM(stockouts) AS stockout_weeks, SUM(backlog) AS end_backlog
 FROM outcomes GROUP BY version, family ORDER BY version, cohort;