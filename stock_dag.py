# -*- coding: utf-8 -*-
"""stock_dag.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1TvMUpr6dX8YbR0zPutw3r56rhpH0Q42K
"""

from airflow import DAG
from airflow.models import Variable
from airflow.decorators import task
from airflow.providers.snowflake.hooks.snowflake import SnowflakeHook

from datetime import timedelta
from datetime import datetime
import snowflake.connector
import requests

def return_snowflake_conn():

    # Initialize the SnowflakeHook
    hook = SnowflakeHook(snowflake_conn_id='snowflake_conn')

    # Execute the query and fetch results
    conn = hook.get_conn()
    return conn.cursor()


@task
def return_last_90day_price(symbol):
  vantage_api_key = Variable.get('alpha_vantage_api_key')
  url = f'https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol={symbol}&apikey={vantage_api_key}'
  r = requests.get(url)
  data = r.json()

  results = []

  for d in data["Time Series (Daily)"]:
    stock_info = data["Time Series (Daily)"][d]
    stock_info["date"] = d
    results.append(stock_info)

  return results

@task
def combine_data(*args):
    combined_results = []
    
    # Combine the returned 90day price for each symbol
    for data in args:
        combined_results.extend(data)

    return combined_results


@task
def transform(dict_list):

  records = []

  for i in dict_list:
    symbol = i["symbol"]
    timestamp = i["date"]
    open = i["1. open"]
    high = i["2. high"]
    low = i["3. low"]
    close = i["4. close"]
    volume = i["5. volume"]
    records.append([symbol, timestamp, open, high, low, close, volume])

  return records

@task
def load(con, records):
  target_table = "dev.raw_data.time_series_daily"
  try:
    con.execute("BEGIN;")
    con.execute(f"""
    CREATE OR REPLACE TABLE {target_table} (
      symbol varchar,
      date timestamp_ntz primary key,
      open number,
      high number,
      low number,
      close number,
      volume number
    )""")
    for r in records:
      symbol, timestamp, open, high, low, close, volume = r
      sql = f"""INSERT INTO {target_table} (symbol, date, open, high, low, close, volume)
          VALUES ('{symbol}', '{timestamp}','{open}','{high}','{low}','{close}','{volume}')"""
      con.execute(sql)
    con.execute("COMMIT;")

  except Exception as e:
    con.execute("ROLLBACK;")
    raise e


with DAG(
    dag_id = 'stock_price',
    start_date = datetime(2024,10,8),
    catchup=False,
    tags=['ETL'],
    schedule = '30 2 * * *'
) as dag:

    symbols = ["IBM", "AAPL", "NVDA"]
    cur = return_snowflake_conn()

    fetch_tasks = []

    # First, fetch the price data for each symbol
    for symbol in symbols:
        task = return_last_90day_price(symbol)
        fetch_tasks.append(task.output)

    # Then, combine the returned 90day price data for each symbol to transform and load
    days_records = combine_data(*fetch_tasks)
    lines = transform(days_records)
    load(cur, lines)
