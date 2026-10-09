"""All-calendar-month Task 1 summaries. Missing observations are never imputed.

Outputs are small audit/analysis tables; all observation-level work runs in Spark.
The legacy four-station panel is deliberately not a primary analysis input.
"""
from pyspark import StorageLevel
from pyspark.sql import functions as F
from functools import reduce
from rainfall.data import YEARS


def paired_periods(frame, period_keys):
    """All year pairs, matched within station and period, stable pair coordinates.

    Match first and aggregate second: unequal station compositions cannot create
    a paired difference. Pair panels differ and must not form a chained trend.
    """
    a, b = frame.alias('a'), frame.alias('b')
    condition = (F.col('a.station_id') == F.col('b.station_id')) & (F.col('a.year') < F.col('b.year'))
    for key in period_keys:
        condition = condition & (F.col('a.'+key) == F.col('b.'+key))
    condition = condition & (F.abs(F.col('a.latitude')-F.col('b.latitude')) <= .005) & (F.abs(F.col('a.longitude')-F.col('b.longitude')) <= .005)
    pairs = a.join(b, condition).select(
        F.col('a.year').alias('year_a'), F.col('b.year').alias('year_b'),
        *[F.col('a.'+k).alias(k) for k in period_keys],
        F.col('a.station_id').alias('station_id'),
        F.col('a.rainfall_total_mm').alias('amount_a'), F.col('b.rainfall_total_mm').alias('amount_b'))
    return (pairs.groupBy('year_a','year_b',*period_keys).agg(
        F.count('*').alias('stations'), F.avg('amount_a').alias('mean_a_mm'), F.avg('amount_b').alias('mean_b_mm'),
        F.avg(F.col('amount_b')-F.col('amount_a')).alias('mean_change_mm'))
        .withColumn('change_percent', F.when(F.col('mean_a_mm')>0,100*F.col('mean_change_mm')/F.col('mean_a_mm'))))


def explore_full(clean, out, mode='errorifexists', monthly_coverage=.90, raw_path=None):
    if not 0 < monthly_coverage <= 1:
        raise ValueError('monthly_coverage must be in (0, 1]')
    spark=clean.sparkSession
    spark.conf.set('spark.sql.session.timeZone','Asia/Singapore')
    calendar=spark.createDataFrame([(y,m) for y in YEARS for m in range(1,13)], 'year int, month int').withColumn(
        'expected_intervals', F.dayofmonth(F.last_day(F.make_date('year','month',F.lit(1))))*288)
    observed=clean.groupBy('station_id','year','month').agg(
        F.count('*').alias('observed_intervals'), F.sum('rainfall').alias('rainfall_total_mm'),
        F.sum((F.col('rainfall')>0).cast('long')).alias('wet_intervals'),
        F.max('station_name').alias('station_name'),F.avg('latitude').alias('latitude'),F.avg('longitude').alias('longitude'),
        (F.max('latitude')-F.min('latitude')).alias('latitude_span'),
        (F.max('longitude')-F.min('longitude')).alias('longitude_span'))
    monthly=(clean.select('station_id').distinct().crossJoin(calendar).join(observed,['station_id','year','month'],'left')
        .fillna(0,subset=['observed_intervals','wet_intervals']).withColumn('coverage',F.col('observed_intervals')/F.col('expected_intervals'))
        .persist(StorageLevel.MEMORY_AND_DISK))
    qualified=monthly.where(F.col('coverage')>=monthly_coverage)
    stable=qualified.where((F.col('latitude_span')<=.005)&(F.col('longitude_span')<=.005))
    yearly=(monthly.groupBy('station_id','year').agg(
        F.sum('observed_intervals').alias('observed_intervals'),F.sum('expected_intervals').alias('expected_intervals'),
        F.sum('rainfall_total_mm').alias('rainfall_total_mm'),F.sum('wet_intervals').alias('wet_intervals'),
        F.min('coverage').alias('min_month_coverage'),F.avg('latitude').alias('latitude'),F.avg('longitude').alias('longitude'),
        F.max('station_name').alias('station_name'),
        (F.max(F.col('latitude')+F.col('latitude_span'))-F.min(F.col('latitude')-F.col('latitude_span'))).alias('latitude_span'),
        (F.max(F.col('longitude')+F.col('longitude_span'))-F.min(F.col('longitude')-F.col('longitude_span'))).alias('longitude_span'))
        .withColumn('coverage',F.col('observed_intervals')/F.col('expected_intervals')))
    eligible_year=yearly.where((F.col('coverage')>=.95)&(F.col('min_month_coverage')>=monthly_coverage))
    def summary(d,keys):
        return d.groupBy(*keys).agg(F.count('*').alias('stations'),F.avg('rainfall_total_mm').alias('mean_station_rainfall_mm'),
            F.min('rainfall_total_mm').alias('min_station_rainfall_mm'),F.max('rainfall_total_mm').alias('max_station_rainfall_mm'),
            F.avg('coverage').alias('mean_coverage'),F.sum('wet_intervals').alias('wet_intervals'),F.sum('observed_intervals').alias('observed_intervals'),
            F.sum('rainfall_total_mm').alias('observed_mm')).withColumn('wet_fraction',F.col('wet_intervals')/F.col('observed_intervals')).withColumn(
            'mean_wet_interval_mm',F.when(F.col('wet_intervals')>0,F.col('observed_mm')/F.col('wet_intervals')))
    coverage=monthly.groupBy('year','month').agg(
        F.sum((F.col('observed_intervals')>0).cast('int')).alias('active_stations'),
        F.sum((F.col('coverage')>=monthly_coverage).cast('int')).alias('qualified_stations'),
        F.percentile_approx(F.when(F.col('observed_intervals')>0,F.col('coverage')),.5,10000).alias('median_active_coverage'))
    available=clean.join(qualified.select('station_id','year','month'),['station_id','year','month'],'left_semi')
    hours=(available.withColumn('hour',F.hour('timestamp')).groupBy('year','month','hour').agg(
        F.count('*').alias('observed_intervals'),F.sum((F.col('rainfall')>0).cast('long')).alias('wet_intervals'),
        F.sum('rainfall').alias('observed_mm'),F.countDistinct('station_id').alias('stations'))
        .withColumn('wet_fraction',F.col('wet_intervals')/F.col('observed_intervals'))
        .withColumn('mean_wet_interval_mm',F.when(F.col('wet_intervals')>0,F.col('observed_mm')/F.col('wet_intervals'))))
    daily=(available.withColumn('date',F.to_date('timestamp')).groupBy('station_id','year','month','date').agg(
        F.count('*').alias('observed_intervals'),F.sum('rainfall').alias('rainfall_total_mm'))
        .where(F.col('observed_intervals')>=.95*288))
    daily_summary=daily.groupBy('year','month').agg(F.count('*').alias('station_days'),
        F.sum((F.col('rainfall_total_mm')>0).cast('long')).alias('wet_days'),
        F.percentile_approx('rainfall_total_mm',[.5,.95,.99],10000).alias('quantiles'),F.max('rainfall_total_mm').alias('max_daily_mm'))
    daily_summary=(daily_summary.withColumn('p50_mm',F.col('quantiles')[0]).withColumn('p95_mm',F.col('quantiles')[1])
        .withColumn('p99_mm',F.col('quantiles')[2]).drop('quantiles').withColumn('wet_day_fraction',F.col('wet_days')/F.col('station_days')))
    profile=clean.groupBy('year').agg(F.count('*').alias('observations'),F.countDistinct('station_id').alias('stations'),
        F.sum((F.col('rainfall')==0).cast('long')).alias('zero_observations'),F.sum((F.col('rainfall')>0).cast('long')).alias('positive_observations'),
        F.avg('rainfall').alias('mean_all_mm'),F.max('rainfall').alias('max_mm'),
        F.percentile_approx(F.when(F.col('rainfall')>0,F.col('rainfall')),[.5,.95,.99,.999],100000).alias('q'))
    for i,n in enumerate(['positive_p50_mm','positive_p95_mm','positive_p99_mm','positive_p999_mm']): profile=profile.withColumn(n,F.col('q')[i])
    profile=profile.drop('q').withColumn('zero_fraction',F.col('zero_observations')/F.col('observations'))
    # Fine log-spaced positive-value bins (zero is reported separately).
    hist=clean.where(F.col('rainfall')>0).withColumn('log_bin',F.floor(F.log10('rainfall')*10)/10).groupBy('log_bin').count()
    hist=hist.withColumn('lower_mm',F.pow(F.lit(10.),'log_bin')).withColumn('upper_mm',F.pow(F.lit(10.),F.col('log_bin')+.1))
    sensitivity=reduce(lambda a,b:a.unionByName(b),[summary(monthly.where(F.col('coverage')>=c),['year','month']).withColumn('threshold',F.lit(c)) for c in (.8,.9,.95)])
    # Calendar skeleton exposes dates absent across the entire network.
    days=spark.sql("SELECT explode(sequence(to_date('2017-01-01'),to_date('2024-12-31'),interval 1 day)) AS date")
    clean_daily=clean.groupBy(F.to_date('timestamp').alias('date')).agg(F.count('*').alias('clean_records'),F.countDistinct('station_id').alias('clean_stations'))
    audit=days.join(clean_daily,'date','left').fillna(0,subset=['clean_records','clean_stations'])
    if raw_path:
        raw=spark.read.option('header',True).csv(raw_path.rstrip('/')+'/year=*/rainfall.csv')
        raw_dates=raw.withColumn('parsed_time',F.to_timestamp('timestamp'))
        raw_counts=raw_dates.groupBy(F.to_date('parsed_time').alias('date')).agg(F.count('*').alias('raw_records'))
        audit=audit.join(raw_counts,'date','left').fillna(0,subset=['raw_records'])
        raw_quality=raw_dates.agg(F.count('*').alias('raw_records'),F.sum(F.col('parsed_time').isNull().cast('long')).alias('unparsed_timestamps'))
    else: raw_quality=None
    outputs={'station_month':monthly,'station_year':yearly,'monthly_available_qualified':summary(qualified,['year','month']),
        'annual_available_qualified':summary(eligible_year,['year']),'annual_station_qualified':eligible_year,
        'monthly_pair_comparisons':paired_periods(stable,['month']),
        'annual_pair_comparisons':paired_periods(eligible_year.where((F.col('latitude_span')<=.005)&(F.col('longitude_span')<=.005)),[]),
        'coverage':coverage,'hourly_available':hours,'daily_distribution_available':daily_summary,
        'rainfall_distribution':profile,'positive_histogram':hist,'coverage_sensitivity_results':sensitivity,
        'daily_record_audit':audit,'spatial_month_available':stable,
        'station_locations':observed.select('station_id','year','month','station_name','latitude','longitude')}
    if raw_quality is not None: outputs['raw_quality']=raw_quality
    for name,d in outputs.items():
        if len(set(d.columns))!=len(d.columns): raise ValueError('Duplicate columns: '+name)
        # Spark CSV cannot store array/struct fields; summaries above flatten them.
        d.coalesce(1).write.mode(mode).option('header',True).csv(out.rstrip('/')+'/'+name)
        print('Saved all-month table:',name,flush=True)
    monthly.unpersist()
