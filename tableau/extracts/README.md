# Tableau extracts

Four of the five extracts are committed here. `mart_customer_segments.csv`
(96,096 rows, 14.6 MB) is not, it is too large to belong in git and is fully
regenerable:

```bash
python python/export_tableau.py
```

That rebuilds all five extracts from the DuckDB warehouse, so the workbook
described in `../BUILD_GUIDE.md` can be reproduced from a clean clone.
