import db
c = db.connect()
print(c.execute("SELECT COUNT(*), MIN(date), MAX(date) FROM fx_rates").fetchone()[:])
for r in c.execute("""SELECT country, series, tenor, COUNT(*) n, MIN(date), MAX(date)
                      FROM interest_rates GROUP BY country, series, tenor
                      ORDER BY country, series, n DESC"""):
    print(tuple(r))